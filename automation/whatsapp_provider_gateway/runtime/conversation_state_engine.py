#!/usr/bin/env python3
"""AIOS WhatsApp Conversation State Engine.
Adds production controls after provider normalization:
- duplicate inbound message suppression
- human takeover switch
- safe auto-reply gate
- conversation audit state
- dashboard counters
No network calls. No secrets. No live messages sent.
"""
from __future__ import annotations
import json, sqlite3, sys, pathlib, datetime, hashlib
import re

DEFAULT_DB = pathlib.Path(__file__).resolve().parents[1] / "state" / "conversation_state.sqlite"
DEFAULT_WHATSAPP_CHAT_DB = pathlib.Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
DEFAULT_WHATSAPP_CONTACTS_DB = pathlib.Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ContactsV2.sqlite"
TAKEOVER_MINUTES = 120


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(dt):
    return dt.isoformat()


def connect(path: pathlib.Path = DEFAULT_DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        create table if not exists conversations (
            contact_phone text primary key,
            provider text,
            profile_name text,
            last_message_at text,
            last_lead_id text,
            human_takeover_until text,
            human_takeover_reason text,
            ai_enabled integer default 1,
            updated_at text not null
        );
        create table if not exists messages (
            message_id text primary key,
            contact_phone text not null,
            provider text,
            direction text,
            message_text text,
            lead_id text,
            received_at text,
            processed_at text,
            duplicate_of text
        );
        create table if not exists reply_decisions (
            decision_id text primary key,
            message_id text,
            contact_phone text,
            lead_id text,
            requested_mode text,
            final_mode text,
            reason text,
            reply_text text,
            created_at text
        );
        """
    )
    return db


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def decision_id(message_id: str, final_mode: str):
    return "DEC-" + hashlib.sha256(f"{message_id}:{final_mode}".encode()).hexdigest()[:12].upper()


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _clean_phone(value: str | None) -> str:
    digits = _digits(value)
    if len(digits) == 10 and digits.startswith("0"):
        # Normalize common UAE local mobile format 05xxxxxxxx to +9715xxxxxxxx.
        digits = "971" + digits[1:]
    return f"+{digits}" if digits else "UNKNOWN"


def _candidate_keys(*values: str | None) -> list[str]:
    keys = []
    seen = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        digits = _digits(raw)
        variants = [raw, raw.replace("whatsapp:", ""), digits, f"{digits}@s.whatsapp.net" if digits else "", f"{digits}@lid" if digits else ""]
        for variant in variants:
            item = str(variant or "").strip()
            if item and item not in seen:
                seen.add(item)
                keys.append(item)
    return keys


def _phone_match_clauses(phone: str, digits: str, aliases: list[str] | None = None) -> tuple[str, list[str]]:
    """Build exact-match clauses only.

    The previous implementation used broad `LIKE %digits%` matching, which can
    cross-link unrelated contacts whose numbers merely contain the same digit
    sequence. For WhatsApp continuity we want deterministic identity matching,
    so we only match exact stored phone/JID variants.
    """
    clauses = []
    params: list[str] = []
    variants = _candidate_keys(phone, digits, *(aliases or []))
    for variant in variants:
        clauses.append("contact_phone = ?")
        params.append(variant)
    return " or ".join(clauses) if clauses else "contact_phone = ?", params


def _phone_jid_variants(phone: str, digits: str, aliases: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Return exact phone/JID variants for WhatsApp inbox matching."""
    variants = _candidate_keys(phone, digits, *(aliases or []))
    jid_variants: list[str] = []
    seen = set()
    for variant in variants:
        raw = str(variant or "").strip()
        if not raw:
            continue
        normalized = raw.replace("whatsapp:", "")
        cleaned = _digits(normalized)
        options = [
            normalized,
            raw,
            cleaned,
            f"{cleaned}@s.whatsapp.net" if cleaned else "",
            f"{cleaned}@lid" if cleaned else "",
            f"whatsapp:{cleaned}" if cleaned else "",
        ]
        for option in options:
            item = str(option or "").strip()
            if item and item not in seen:
                seen.add(item)
                jid_variants.append(item)
    return variants, jid_variants


def _fetch_rows(db_path: pathlib.Path, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        try:
            return list(db.execute(sql, params).fetchall())
        finally:
            db.close()
    except Exception:
        return []


def _message_excerpt(text: str, limit: int = 96) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]


def _normalize_partner_name(value: str | None) -> str:
    return re.sub(r"[\u200e\u200f\s]+", " ", str(value or "")).strip().lower()


def load_contact_context(gateway: dict, db_path: pathlib.Path = DEFAULT_DB, whatsapp_chat_db: pathlib.Path = DEFAULT_WHATSAPP_CHAT_DB, whatsapp_contacts_db: pathlib.Path = DEFAULT_WHATSAPP_CONTACTS_DB, limit: int = 6) -> dict:
    event = gateway.get("provider_event", {})
    crm = gateway.get("crm", {})
    contact = crm.get("contact", {})
    phone = _clean_phone(event.get("from_phone") or contact.get("WhatsApp Phone"))
    digits = _digits(phone)
    profile_name = event.get("profile_name") or contact.get("Full Name") or "WhatsApp Contact"
    identifiers = _candidate_keys(
        phone,
        event.get("from_phone"),
        event.get("to_phone"),
        event.get("raw", {}).get("remoteJid") if isinstance(event.get("raw"), dict) else None,
        event.get("raw", {}).get("senderPn") if isinstance(event.get("raw"), dict) else None,
        event.get("raw", {}).get("cleanedSenderPn") if isinstance(event.get("raw"), dict) else None,
        event.get("raw", {}).get("cleanedParticipantPn") if isinstance(event.get("raw"), dict) else None,
        event.get("raw", {}).get("wa_id") if isinstance(event.get("raw"), dict) else None,
        event.get("raw", {}).get("contact", {}).get("phone") if isinstance(event.get("raw"), dict) and isinstance(event.get("raw", {}).get("contact"), dict) else None,
    )

    aios_clause, aios_params = _phone_match_clauses(phone, digits, identifiers)
    aios_conversation = _fetch_rows(
        db_path,
        f"select * from conversations where {aios_clause} order by updated_at desc limit 1",
        tuple(aios_params),
    )
    aios_messages = _fetch_rows(
        db_path,
        f"select * from messages where {aios_clause} order by coalesce(received_at, processed_at) desc limit ?",
        tuple(aios_params + [limit]),
    )
    aios_decisions = _fetch_rows(
        db_path,
        f"select * from reply_decisions where {aios_clause} order by created_at desc limit ?",
        tuple(aios_params + [limit]),
    )

    contact_rows = []
    _, jid_variants = _phone_jid_variants(phone, digits, identifiers)
    if jid_variants:
        placeholders = ",".join("?" for _ in jid_variants)
        contact_rows = _fetch_rows(
            whatsapp_contacts_db,
            """
            select ZFULLNAME, ZGIVENNAME, ZBUSINESSNAME, ZIDENTIFIER, ZINTEROPJID, ZLID, ZLOCALIZEDPHONENUMBER, ZPHONENUMBER, ZUSERNAME, ZWHATSAPPID, ZLASTUPDATED
            from ZWAADDRESSBOOKCONTACT
            where ZPHONENUMBER in ({0})
               or ZWHATSAPPID in ({0})
               or ZIDENTIFIER in ({0})
               or ZINTEROPJID in ({0})
               or ZLID in ({0})
               or ZLOCALIZEDPHONENUMBER in ({0})
               or ZUSERNAME in ({0})
               or ZFULLNAME in ({0})
            order by ZLASTUPDATED desc
            limit 1
            """.format(placeholders),
            tuple(jid_variants * 8),
        )

    whatsapp_messages = []
    whatsapp_sessions = []
    if jid_variants:
        placeholders = ",".join("?" for _ in jid_variants)
        whatsapp_messages = _fetch_rows(
            whatsapp_chat_db,
            """
            select ZFROMJID, ZTOJID, ZPUSHNAME, ZTEXT, ZMESSAGEDATE, ZSENTDATE, ZISFROMME, ZSTANZAID
            from ZWAMESSAGE
            where ZFROMJID in ({0}) or ZTOJID in ({0})
            order by coalesce(ZMESSAGEDATE, ZSENTDATE) desc
            limit ?
            """.format(placeholders),
            tuple(jid_variants + jid_variants + [limit]),
        )
        whatsapp_sessions = _fetch_rows(
            whatsapp_chat_db,
            """
            select ZCONTACTJID, ZPARTNERNAME, ZLASTMESSAGETEXT, ZLASTMESSAGEDATE
            from ZWACHATSESSION
            where ZCONTACTJID in ({0}) or ZPARTNERNAME in ({0})
            order by ZLASTMESSAGEDATE desc
            limit 1
            """.format(placeholders),
            tuple(jid_variants + jid_variants),
        )

    is_self_thread = False
    if whatsapp_sessions:
        partner_name = _normalize_partner_name(whatsapp_sessions[0]["ZPARTNERNAME"])
        if partner_name == "you" or partner_name.endswith(" (you)") or partner_name.endswith("you"):
            is_self_thread = True

    recent_messages = []
    for row in whatsapp_messages:
        recent_messages.append({
            "source": "whatsapp_business_app",
            "direction": "Outbound" if row["ZISFROMME"] else "Inbound",
            "contact_phone": phone,
            "peer_jid": row["ZFROMJID"] if row["ZISFROMME"] else row["ZTOJID"],
            "message_text": row["ZTEXT"] or "",
            "message_at": str(row["ZMESSAGEDATE"] or row["ZSENTDATE"] or ""),
            "message_id": row["ZSTANZAID"] or "",
        })
    for row in aios_messages:
        recent_messages.append({
            "source": "aios_state",
            "direction": "Inbound",
            "contact_phone": row["contact_phone"],
            "message_text": row["message_text"] or "",
            "message_at": row["received_at"] or row["processed_at"] or "",
            "message_id": row["message_id"] or "",
        })

    deduped_messages = []
    seen_messages = set()
    for message in recent_messages:
        key = (
            message.get("source"),
            message.get("message_id"),
            message.get("message_text"),
            message.get("message_at"),
            message.get("direction"),
        )
        if key in seen_messages:
            continue
        seen_messages.add(key)
        deduped_messages.append(message)

    recent_messages = deduped_messages[:limit]
    recent_messages.reverse()

    if contact_rows:
        contact_name = contact_rows[0]["ZFULLNAME"] or contact_rows[0]["ZBUSINESSNAME"] or profile_name
    elif whatsapp_sessions:
        contact_name = whatsapp_sessions[0]["ZPARTNERNAME"] or profile_name
    else:
        contact_name = profile_name

    history_bits = []
    if aios_conversation:
        convo = aios_conversation[0]
        if convo["last_lead_id"]:
            history_bits.append(f"last lead {convo['last_lead_id']}")
        if convo["human_takeover_until"]:
            history_bits.append(f"takeover until {convo['human_takeover_until']}")
    if aios_messages:
        history_bits.append(f"{len(aios_messages)} AIOS message(s)")
    if whatsapp_messages:
        history_bits.append(f"{len(whatsapp_messages)} WhatsApp inbox message(s)")
    if whatsapp_sessions:
        last_session = whatsapp_sessions[0]
        if last_session["ZLASTMESSAGETEXT"]:
            history_bits.append(f"last inbox text: {_message_excerpt(last_session['ZLASTMESSAGETEXT'])}")

    if is_self_thread:
        continuity_summary = "Self-chat or personal thread ignored."
    else:
        continuity_summary = " | ".join(history_bits) if history_bits else "No prior thread history found."

    return {
        "canonical_contact": {
            "phone": phone,
            "digits": digits,
            "identifiers": identifiers,
            "name": contact_name,
        },
        "is_self_thread": is_self_thread,
        "history": {
            "summary": continuity_summary,
            "recent_messages": recent_messages,
            "aios_conversation": [dict(row) for row in aios_conversation],
            "aios_messages": [dict(row) for row in aios_messages],
            "aios_decisions": [dict(row) for row in aios_decisions],
            "whatsapp_contact_rows": [dict(row) for row in contact_rows],
            "whatsapp_sessions": [dict(row) for row in whatsapp_sessions],
            "whatsapp_messages": [dict(row) for row in whatsapp_messages],
        },
        "known_contact_name": contact_name,
        "has_prior_history": bool(recent_messages or aios_conversation or whatsapp_sessions),
        "match_quality": {
            "exact_phone_match": bool(aios_conversation),
            "digit_match": bool(digits),
            "alias_match_count": len(identifiers),
        },
    }


def apply_state(gateway: dict, db_path: pathlib.Path = DEFAULT_DB) -> dict:
    db = connect(db_path)
    event = gateway.get("provider_event", {})
    classification = gateway.get("classification", {})
    crm = gateway.get("crm", {})
    reply = gateway.get("reply", {})
    phone = event.get("from_phone") or crm.get("contact", {}).get("WhatsApp Phone") or "UNKNOWN"
    msg_id = event.get("message_id") or crm.get("message", {}).get("Message ID") or "UNKNOWN"
    provider = event.get("provider") or "unknown"
    text = event.get("message_text") or crm.get("message", {}).get("Message Text") or ""
    lead_id = crm.get("lead", {}).get("Lead ID") or "LEAD-UNKNOWN"
    now = utcnow()
    is_group_or_channel = bool(event.get("is_group_or_channel") or classification.get("is_group_or_channel"))

    existing_msg = db.execute("select message_id from messages where message_id=?", (msg_id,)).fetchone()
    if existing_msg:
        final_mode = "DUPLICATE_SUPPRESSED"
        reason = "Duplicate inbound WhatsApp message ID already processed."
    elif is_group_or_channel:
        final_mode = "NON_ACTIONABLE_IGNORED"
        reason = "Group or channel WhatsApp event ignored."
    else:
        convo = db.execute("select * from conversations where contact_phone=?", (phone,)).fetchone()
        takeover_until = parse_dt(convo["human_takeover_until"]) if convo else None
        in_takeover = takeover_until is not None and takeover_until > now
        risky = bool(classification.get("risk_flags")) or classification.get("human_takeover_required") is True
        requested = reply.get("mode") or "OMAR_APPROVAL_REQUIRED"
        if requested == "NO_REPLY_NON_ACTIONABLE" or classification.get("actionable") is False:
            final_mode = "NON_ACTIONABLE_IGNORED"
            reason = "Non-actionable WhatsApp event (edit, reaction, or system message) ignored."
        elif in_takeover:
            final_mode = "HUMAN_TAKEOVER_ACTIVE"
            reason = f"Human takeover active until {iso(takeover_until)}. AI replies blocked."
        elif risky:
            final_mode = "OMAR_APPROVAL_REQUIRED"
            reason = "Risk flags present or unclear business/legal/payment context."
            takeover_until = now + datetime.timedelta(minutes=TAKEOVER_MINUTES)
        elif requested == "AUTO_REPLY_SAFE" and classification.get("safe_auto_reply") is True:
            final_mode = "AUTO_REPLY_ALLOWED"
            reason = "Safe category, no risk flags, no human takeover active."
        else:
            final_mode = "OMAR_APPROVAL_REQUIRED"
            reason = "Default approval gate."

        db.execute(
            "insert into messages(message_id,contact_phone,provider,direction,message_text,lead_id,received_at,processed_at,duplicate_of) values(?,?,?,?,?,?,?,?,?)",
            (msg_id, phone, provider, "Inbound", text, lead_id, event.get("timestamp"), iso(now), None),
        )
        db.execute(
            "insert into conversations(contact_phone,provider,profile_name,last_message_at,last_lead_id,human_takeover_until,human_takeover_reason,ai_enabled,updated_at) values(?,?,?,?,?,?,?,?,?) "
            "on conflict(contact_phone) do update set provider=excluded.provider, profile_name=excluded.profile_name, last_message_at=excluded.last_message_at, last_lead_id=excluded.last_lead_id, human_takeover_until=excluded.human_takeover_until, human_takeover_reason=excluded.human_takeover_reason, ai_enabled=excluded.ai_enabled, updated_at=excluded.updated_at",
            (phone, provider, event.get("profile_name"), event.get("timestamp"), lead_id, iso(takeover_until) if takeover_until and (classification.get("risk_flags") or classification.get("human_takeover_required")) else (convo["human_takeover_until"] if convo and in_takeover else None), reason if (takeover_until and final_mode in {"OMAR_APPROVAL_REQUIRED", "HUMAN_TAKEOVER_ACTIVE"}) else None, 0 if final_mode == "HUMAN_TAKEOVER_ACTIVE" else 1, iso(now)),
        )

    if existing_msg or is_group_or_channel:
        db.execute(
            "insert or ignore into reply_decisions(decision_id,message_id,contact_phone,lead_id,requested_mode,final_mode,reason,reply_text,created_at) values(?,?,?,?,?,?,?,?,?)",
            (decision_id(msg_id, "DUPLICATE_SUPPRESSED" if existing_msg else "NON_ACTIONABLE_IGNORED"), msg_id, phone, lead_id, reply.get("mode"), "DUPLICATE_SUPPRESSED" if existing_msg else "NON_ACTIONABLE_IGNORED", reason, "", iso(now)),
        )
    else:
        db.execute(
            "insert or replace into reply_decisions(decision_id,message_id,contact_phone,lead_id,requested_mode,final_mode,reason,reply_text,created_at) values(?,?,?,?,?,?,?,?,?)",
            (decision_id(msg_id, final_mode), msg_id, phone, lead_id, reply.get("mode"), final_mode, reason, reply.get("text") if final_mode == "AUTO_REPLY_ALLOWED" else "", iso(now)),
        )
    db.commit()

    metrics = {
        "total_conversations": db.execute("select count(*) c from conversations").fetchone()["c"],
        "total_messages": db.execute("select count(*) c from messages").fetchone()["c"],
        "auto_replies_allowed": db.execute("select count(*) c from reply_decisions where final_mode='AUTO_REPLY_ALLOWED'").fetchone()["c"],
        "approval_required": db.execute("select count(*) c from reply_decisions where final_mode='OMAR_APPROVAL_REQUIRED'").fetchone()["c"],
        "human_takeover_blocks": db.execute("select count(*) c from reply_decisions where final_mode='HUMAN_TAKEOVER_ACTIVE'").fetchone()["c"],
        "non_actionable_ignored": db.execute("select count(*) c from reply_decisions where final_mode='NON_ACTIONABLE_IGNORED'").fetchone()["c"],
        "duplicates_suppressed": db.execute("select count(*) c from reply_decisions where final_mode='DUPLICATE_SUPPRESSED'").fetchone()["c"],
    }
    return {
        **gateway,
        "state_decision": {
            "message_id": msg_id,
            "contact_phone": phone,
            "lead_id": lead_id,
            "final_mode": "DUPLICATE_SUPPRESSED" if existing_msg else final_mode,
            "reason": reason,
            "send_allowed": (not existing_msg) and final_mode == "AUTO_REPLY_ALLOWED",
            "reply_text": reply.get("text") if ((not existing_msg) and final_mode == "AUTO_REPLY_ALLOWED") else "",
        },
        "dashboard_metrics": metrics,
    }


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    db_arg = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    print(json.dumps(apply_state(payload, db_arg), indent=2, ensure_ascii=False))
