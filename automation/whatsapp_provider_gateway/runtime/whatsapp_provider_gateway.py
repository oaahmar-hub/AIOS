#!/usr/bin/env python3
"""AIOS WhatsApp Provider Gateway.
Normalizes inbound WhatsApp webhooks from Meta Cloud API, 360dialog, respond.io, WATI-style payloads,
Gupshup, Infobip/CEQUENS/Route Mobile-style managed BSP payloads, and Twilio Sandbox/Production into one AIOS event contract.

Safety: no network calls, no secret handling, no live message sending. Output is CRM/AI/pipeline ready.
"""
from __future__ import annotations
import json, os, sys, re, uuid, html
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs
from datetime import datetime, timezone, timedelta

from conversation_state_engine import (
    DEFAULT_DB,
    DEFAULT_WHATSAPP_CHAT_DB,
    DEFAULT_WHATSAPP_CONTACTS_DB,
    load_contact_context,
)

AR = re.compile(r"[\u0600-\u06FF]")
PROMPT_PATH = Path(__file__).resolve().parents[2] / "whatsapp_business_os" / "prompts" / "omar_real_estate_whatsapp_agent.txt"
HOT = {"today","urgent","asap","now","cash","ready","viewing","tonight","immediate","serious"}
RISKY = {
    "legal","contract","sign","poa","power of attorney","visa","payment","bank","banking",
    "refund","complaint","dld","ejari","government","final offer","deposit","transfer",
    "cheque copy","passport copy","emirates id","title deed","tenancy contract"
}
AUTO_SAFE_CATEGORIES = {
    "greeting","basic_property_inquiry","location_question","availability_question","price_range_question",
    "document_checklist","viewing_coordination","follow_up_reminder","simple_support"
}
NON_ACTIONABLE_MESSAGE_TYPES = {
    "reactionMessage",
    "protocolMessage",
    "secretEncryptedMessage",
}

NON_ACTIONABLE_EVENT_TOKENS = {
    "reaction",
    "delete",
    "receipt",
    "status",
    "qrcode",
    "edit",
    "group",
    "newsletter",
    "channel",
}

GROUP_CHAT_MARKERS = (
    "@g.us",
    "@newsletter",
    "group",
    "newsletter",
    "channel",
)


@lru_cache(maxsize=1)
def load_canonical_prompt() -> str:
    """Reuse the shared Omar WhatsApp tone/source prompt in the live router."""
    try:
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_raw(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        return json.loads(raw)
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(raw).items()}


def detect_provider(payload: dict) -> str:
    if "SmsMessageSid" in payload or str(payload.get("From", "")).startswith("whatsapp:"):
        return "twilio"
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    messages = data.get("messages") if isinstance(data.get("messages"), dict) else {}
    if (
        "messageBody" in messages
        or "key" in messages
        or "rawMessage" in messages
        or "message" in messages
    ) and (
        payload.get("event", "").startswith("messages.")
        or payload.get("event", "").startswith("message.")
        or payload.get("event", "").startswith("personal.")
        or payload.get("event", "").startswith("chat.")
        or payload.get("event", "").startswith("group.")
        or payload.get("event", "").startswith("newsletter.")
        or payload.get("sessionId")
    ):
        return "wasenderapi"
    if payload.get("object") == "whatsapp_business_account" or "entry" in payload:
        return "meta_cloud_api"
    if "messages" in payload and ("contacts" in payload or "statuses" in payload):
        return "360dialog_or_meta_passthrough"
    if "app" in payload and ("payload" in payload or "sender" in payload or "message" in payload):
        return "gupshup"
    if "type" in payload and payload.get("app") and payload.get("payload"):
        return "gupshup"
    if "results" in payload and isinstance(payload.get("results"), list):
        return "infobip_or_managed_bsp"
    if "message" in payload and isinstance(payload.get("message"), dict) and ("from" in payload["message"] or "to" in payload["message"]):
        return "cequens_or_managed_bsp"
    if "events" in payload and isinstance(payload.get("events"), list):
        return "route_mobile_or_managed_bsp"
    if "contact" in payload and ("message" in payload or "messages" in payload):
        return "respond_io_or_bsp"
    if "waId" in payload or "whatsappMessageId" in payload:
        return "wati_or_bsp"
    return "unknown"


def clean_phone(phone: str) -> str:
    p = str(phone or "").replace("whatsapp:", "").replace("+", "")
    digits = re.sub(r"\D", "", p)
    if len(digits) == 10 and digits.startswith("0"):
        # Normalize UAE local mobile format 05xxxxxxxx to +9715xxxxxxxx.
        digits = "971" + digits[1:]
    return "+" + digits if digits else "UNKNOWN"


def _is_non_1to1_chat(*values: object) -> bool:
    for value in values:
        raw = str(value or "").strip().lower()
        if raw and any(marker in raw for marker in GROUP_CHAT_MARKERS):
            return True
    return False


def _is_self_chat(from_phone: str, to_phone: str) -> bool:
    from_digits = re.sub(r"\D", "", str(from_phone or ""))
    to_digits = re.sub(r"\D", "", str(to_phone or ""))
    return bool(from_digits and to_digits and from_digits == to_digits)


def extract_twilio(p: dict) -> dict:
    from_phone = clean_phone(p.get("From"))
    to_phone = clean_phone(p.get("To"))
    return {
        "provider": "twilio",
        "from_phone": from_phone,
        "to_phone": to_phone,
        "profile_name": p.get("ProfileName") or "WhatsApp Client",
        "message_text": p.get("Body") or "",
        "message_id": p.get("MessageSid") or p.get("SmsMessageSid") or f"twilio-{uuid.uuid4()}",
        "timestamp": now_iso(),
        "message_type": "text",
        "is_self_chat": _is_self_chat(from_phone, to_phone),
        "raw": p,
    }


def _meta_value(p: dict) -> dict:
    if "entry" in p:
        return (((p.get("entry") or [{}])[0].get("changes") or [{}])[0].get("value") or {})
    return p


def extract_meta_like(p: dict, provider: str) -> dict:
    value = _meta_value(p)
    msg = (value.get("messages") or [{}])[0]
    contact = (value.get("contacts") or [{}])[0]
    profile = contact.get("profile") or {}
    phone = msg.get("from") or contact.get("wa_id") or value.get("wa_id") or p.get("waId")
    text = ((msg.get("text") or {}).get("body") or (msg.get("button") or {}).get("text") or
            (msg.get("interactive") or {}).get("button_reply", {}).get("title") or
            p.get("text") or p.get("message") or "")
    ts = msg.get("timestamp") or p.get("timestamp")
    try:
        timestamp = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else now_iso()
    except Exception:
        timestamp = now_iso()
    msg_type = msg.get("type") or ("text" if text else "unknown")
    from_phone = clean_phone(phone)
    to_phone = clean_phone((value.get("metadata") or {}).get("display_phone_number") or (value.get("metadata") or {}).get("phone_number_id"))
    return {
        "provider": provider,
        "from_phone": from_phone,
        "to_phone": to_phone,
        "profile_name": profile.get("name") or p.get("contact", {}).get("name") or p.get("name") or "WhatsApp Contact",
        "message_text": text,
        "message_id": msg.get("id") or p.get("whatsappMessageId") or f"wa-{uuid.uuid4()}",
        "timestamp": timestamp,
        "message_type": msg_type,
        "is_self_chat": _is_self_chat(from_phone, to_phone),
        "raw": p,
    }


def extract_bsp(p: dict, provider: str) -> dict:
    contact = p.get("contact") or p.get("customer") or {}
    message = p.get("message") or ((p.get("messages") or [{}])[0] if isinstance(p.get("messages"), list) else {}) or {}
    text = message.get("text") if isinstance(message, dict) else str(message or "")
    if isinstance(text, dict):
        text = text.get("body") or text.get("text") or ""
    from_phone = clean_phone(contact.get("phone") or contact.get("wa_id") or p.get("waId") or p.get("phone"))
    to_phone = clean_phone(p.get("to") or p.get("channelPhone") or "")
    return {
        "provider": provider,
        "from_phone": from_phone,
        "to_phone": to_phone,
        "profile_name": contact.get("name") or p.get("name") or "WhatsApp Contact",
        "message_text": text or p.get("text") or "",
        "message_id": p.get("id") or (message.get("id") if isinstance(message, dict) else None) or f"bsp-{uuid.uuid4()}",
        "timestamp": p.get("timestamp") or now_iso(),
        "message_type": (message.get("type") if isinstance(message, dict) else None) or "text",
        "is_self_chat": _is_self_chat(from_phone, to_phone),
        "raw": p,
    }





def extract_gupshup(p: dict) -> dict:
    """Normalize Gupshup WhatsApp inbound webhook payloads.

    Gupshup commonly sends app-level events containing sender/destination and a
    nested `payload` object for text, image, audio, document, and interactive
    messages. This parser is intentionally tolerant so the same AIOS workflow can
    accept sandbox, go-live, and support-enabled variants without rebuild.
    """
    payload = p.get("payload") if isinstance(p.get("payload"), dict) else {}
    sender_obj = p.get("sender") if isinstance(p.get("sender"), dict) else {}
    source = (
        p.get("source")
        or p.get("from")
        or sender_obj.get("phone")
        or sender_obj.get("phone_number")
        or sender_obj.get("wa_id")
        or payload.get("source")
        or payload.get("from")
    )
    destination = p.get("destination") or p.get("to") or payload.get("destination") or payload.get("to")
    text = (
        payload.get("text")
        or payload.get("body")
        or p.get("text")
        or p.get("message")
        or ""
    )
    if isinstance(text, dict):
        text = text.get("body") or text.get("text") or ""
    msg_type = payload.get("type") or p.get("type") or ("text" if text else "unknown")
    return {
        "provider": "gupshup",
        "from_phone": clean_phone(source),
        "to_phone": clean_phone(destination),
        "profile_name": sender_obj.get("name") or p.get("senderName") or p.get("name") or "WhatsApp Contact",
        "message_text": text,
        "message_id": payload.get("id") or p.get("messageId") or p.get("message_id") or p.get("id") or f"gupshup-{uuid.uuid4()}",
        "timestamp": p.get("timestamp") or payload.get("timestamp") or now_iso(),
        "message_type": msg_type,
        "raw": p,
    }

def extract_wasender(p: dict) -> dict:
    """Normalize WasenderAPI webhook payloads.

    WasenderAPI sends a flattened payload under `data.messages` with a unified
    `messageBody` field and recommended cleaned sender phone fields. This keeps
    AIOS compatible with the live provider session without needing a separate
    parser or n8n workflow branch.
    """
    data = p.get("data") if isinstance(p.get("data"), dict) else {}
    messages = data.get("messages") if isinstance(data.get("messages"), dict) else {}
    key = messages.get("key") if isinstance(messages.get("key"), dict) else {}
    raw_message = messages.get("message") if isinstance(messages.get("message"), dict) else {}
    event_name = str(p.get("event") or "").lower()
    from_me = bool(key.get("fromMe") or messages.get("fromMe") or p.get("fromMe"))
    sender = (
        key.get("cleanedSenderPn")
        or key.get("cleanedParticipantPn")
        or key.get("senderPn")
        or key.get("remoteJid")
        or p.get("from")
    )
    recipient = (
        key.get("cleanedReceiverPn")
        or key.get("receiverPn")
        or key.get("to")
        or p.get("to")
    )
    text = (
        messages.get("messageBody")
        or messages.get("body")
        or raw_message.get("conversation")
        or raw_message.get("extendedTextMessage", {}).get("text")
        or raw_message.get("conversation")
        or raw_message.get("imageMessage", {}).get("caption")
        or raw_message.get("videoMessage", {}).get("caption")
        or raw_message.get("documentMessage", {}).get("caption")
        or raw_message.get("ephemeralMessage", {}).get("message", {}).get("conversation")
        or ""
    )
    non_actionable_event = any(
        token in event_name
        for token in NON_ACTIONABLE_EVENT_TOKENS
    ) or ("update" in event_name and "upsert" not in event_name)
    is_group_or_channel = _is_non_1to1_chat(
        sender,
        recipient,
        key.get("remoteJid"),
        key.get("participantPn"),
        key.get("senderPn"),
        key.get("cleanedSenderPn"),
        key.get("cleanedParticipantPn"),
        p.get("from"),
        p.get("to"),
        event_name,
    )
    msg_type = (
        raw_message.get("type")
        or key.get("type")
        or messages.get("type")
        or (
            "reactionMessage" if "reaction" in event_name else
            "protocolMessage" if non_actionable_event else
            "conversation"
        )
    )
    actionable = bool(str(text or "").strip()) and msg_type not in NON_ACTIONABLE_MESSAGE_TYPES and not non_actionable_event and not is_group_or_channel
    is_self_chat = _is_self_chat(clean_phone(sender), clean_phone(recipient))
    return {
        "provider": "wasenderapi",
        "from_phone": clean_phone(sender),
        "to_phone": clean_phone(recipient),
        "profile_name": data.get("pushName") or messages.get("pushName") or p.get("pushName") or "WhatsApp Contact",
        "message_text": text,
        "message_id": key.get("id") or messages.get("messageId") or p.get("messageId") or f"wasender-{uuid.uuid4()}",
        "timestamp": p.get("timestamp") or messages.get("timestamp") or now_iso(),
        "message_type": msg_type,
        "is_self_chat": is_self_chat,
        "from_me": from_me,
        "is_group_or_channel": is_group_or_channel,
        "actionable": actionable and not is_self_chat and not from_me,
        "raw": p,
    }

def extract_managed_bsp(p: dict, provider: str) -> dict:
    """Normalize common managed-BSP webhook shapes without binding AIOS to one vendor.

    Covers Infobip-style `results[]`, CEQUENS-style `message`, and Route Mobile-style
    `events[]` payloads. Exact vendor mappings can be tightened after account activation,
    but this lets WA-07 accept the usual inbound message contracts immediately.
    """
    item = {}
    if isinstance(p.get("results"), list) and p["results"]:
        item = p["results"][0] or {}
    elif isinstance(p.get("events"), list) and p["events"]:
        item = p["events"][0] or {}
    elif isinstance(p.get("message"), dict):
        item = p.get("message") or {}
    else:
        item = p

    sender = item.get("from") or item.get("sender") or item.get("waId") or item.get("phone") or p.get("from")
    recipient = item.get("to") or item.get("receiver") or item.get("channelPhone") or p.get("to")
    contact = item.get("contact") or p.get("contact") or {}
    content = item.get("message") if isinstance(item.get("message"), dict) else item
    text = (
        item.get("text")
        or item.get("body")
        or (content.get("text") if isinstance(content, dict) else "")
        or ((content.get("content") or {}).get("text") if isinstance(content, dict) and isinstance(content.get("content"), dict) else "")
        or ((item.get("content") or {}).get("text") if isinstance(item.get("content"), dict) else "")
        or p.get("text")
        or ""
    )
    if isinstance(text, dict):
        text = text.get("body") or text.get("text") or ""
    return {
        "provider": provider,
        "from_phone": clean_phone(sender or contact.get("phone") or contact.get("wa_id")),
        "to_phone": clean_phone(recipient),
        "profile_name": contact.get("name") or item.get("profileName") or item.get("name") or p.get("name") or "WhatsApp Contact",
        "message_text": text,
        "message_id": item.get("messageId") or item.get("id") or item.get("message_id") or p.get("messageId") or f"managed-bsp-{uuid.uuid4()}",
        "timestamp": item.get("receivedAt") or item.get("timestamp") or p.get("timestamp") or now_iso(),
        "message_type": item.get("type") or (content.get("type") if isinstance(content, dict) else None) or "text",
        "raw": p,
    }

def normalize(payload: dict) -> dict:
    provider = detect_provider(payload)
    if provider == "twilio":
        return extract_twilio(payload)
    if provider == "wasenderapi":
        return extract_wasender(payload)
    if provider in {"meta_cloud_api", "360dialog_or_meta_passthrough"}:
        return extract_meta_like(payload, provider)
    if provider == "gupshup":
        return extract_gupshup(payload)
    if provider in {"infobip_or_managed_bsp", "cequens_or_managed_bsp", "route_mobile_or_managed_bsp"}:
        return extract_managed_bsp(payload, provider)
    if provider in {"respond_io_or_bsp", "wati_or_bsp"}:
        return extract_bsp(payload, provider)
    return extract_bsp(payload, provider)


def language(text: str) -> str:
    has_arabic = bool(AR.search(text or ""))
    has_latin = bool(re.search(r"[A-Za-z]", text or ""))
    if has_arabic and has_latin:
        return "Mixed"
    return "Arabic" if has_arabic else "English"


def reply_style(lang: str) -> dict:
    return {
        "short": True,
        "human": True,
        "premium": True,
        "business_correct": True,
        "not_too_slow": True,
        "not_too_long": True,
        "language_mode": lang,
    }


def build_tool_plan(intent: str, cat: str, flags: list[str], context: dict) -> dict:
    safe_to_reply = not flags and cat in AUTO_SAFE_CATEGORIES
    needs_calendar = cat == "viewing_coordination" or "appointment" in cat or "viewing" in cat
    needs_document_intake = cat == "document_checklist" or intent in {"NOC / Approval", "Seller / Valuation"} or bool(flags)
    needs_approval = bool(flags) or not safe_to_reply
    return {
        "load_contact_history": True,
        "upsert_crm_contact": True,
        "upsert_crm_lead": True,
        "append_comm_log": True,
        "create_follow_up_task": True,
        "calendar_hand_off": needs_calendar,
        "calendar_reason": "viewing_or_appointment" if needs_calendar else "",
        "file_database_lookup": needs_document_intake,
        "file_database_reason": "document_or_approval_context" if needs_document_intake else "",
        "human_review": needs_approval,
        "reply_allowed": safe_to_reply,
        "history_loaded": bool((context or {}).get("has_prior_history")),
    }


def intent_and_agent(text: str) -> tuple[str, str, str]:
    t = (text or "").lower()
    if any(w in t for w in ["buy", "purchase", "invest", "investment", "roi", "yield"]):
        return "Buyer", "Buyer / Investment", "@client @research"
    if any(w in t for w in ["rent", "lease", "tenant", "move in"]):
        return "Tenant", "Rental", "@client @contract"
    if any(w in t for w in ["sell", "valuation", "owner", "list my property"]):
        return "Seller", "Seller / Valuation", "@client @marketing"
    if any(w in t for w in ["noc", "nakheel", "approval", "modification"]):
        return "Owner", "NOC / Approval", "@noc"
    return "Unknown", "General Real Estate", "@client"


def category(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ["location", "where", "area", "community", "near", "map"]): return "location_question"
    if any(w in t for w in ["available", "availability", "vacant", "ready", "handover"]): return "availability_question"
    if any(w in t for w in ["price", "budget", "range", "cost", "rent", "aed"]): return "price_range_question"
    if any(w in t for w in ["documents", "checklist", "papers", "required docs"]): return "document_checklist"
    if any(w in t for w in ["view", "viewing", "appointment", "schedule", "visit", "meet"]): return "viewing_coordination"
    if re.search(r"(?<!\w)(hi|hello|salam|مرحبا|اهلا)(?!\w)", t) and len(t) < 40: return "greeting"
    if any(w in t for w in ["follow up", "remind", "reminder"]): return "follow_up_reminder"
    if any(w in t for w in ["thanks", "thank you", "support", "help"]): return "simple_support"
    return "basic_property_inquiry"


def risk_flags(text: str) -> list[str]:
    t = (text or "").lower()
    return sorted([w for w in RISKY if w in t])


def draft_reply(text: str, lang: str, intent: str, cat: str, context: dict | None = None) -> str:
    canonical_prompt = load_canonical_prompt()
    raw = (text or "").strip()
    words = raw.split()
    areaish = cat == "basic_property_inquiry" and len(words) <= 3 and len(raw) <= 24 and not any(ch in raw for ch in "?!.")
    prior_history = bool((context or {}).get("has_prior_history"))

    if lang == "Mixed":
        if prior_history and cat in {"greeting", "basic_property_inquiry", "follow_up_reminder", "simple_support"}:
            return "أكيد، عندي التفاصيل السابقة. Send the update or reference and I’ll continue from there."
        if areaish:
            return f"أكيد — {raw}. Send me buy, rent, or compare options and I’ll guide you."
        if cat == "viewing_coordination":
            return "أكيد. Send the preferred time, property, and number of viewers, and I’ll coordinate it."
        return "أكيد، وصلت رسالتك. Send area, budget, and property type and I’ll take it from there."

    if lang == "Arabic":
        if prior_history and cat in {"greeting", "basic_property_inquiry", "follow_up_reminder", "simple_support"}:
            return "أكيد، عندي تفاصيلك السابقة. إذا تغيّر شيء أرسل التحديث أو مرجع العقار، وأنا أكمل معك."
        if areaish:
            return f"ممتاز — {raw}. هل تبحث عن شراء أو إيجار؟"
        if cat == "viewing_coordination":
            return "أكيد. أرسل لي وقت المعاينة واسم العقار، وأنا أرتب الخطوة التالية."
        return "أهلًا — وصلت رسالتك. أرسل لي المنطقة والميزانية ونوع العقار، وأنا أجهز لك الخطوة التالية."

    if prior_history and cat in {"greeting", "basic_property_inquiry", "follow_up_reminder", "simple_support"}:
        return "Thanks — I have your earlier details. Send any update or property reference and I’ll take it from there."
    if areaish:
        return f"Got it — {raw}. Are you looking to buy, rent, or compare options?"
    if cat == "greeting":
        return "Hi — thanks for messaging HSH Global Dubai. What can I help with today?"
    if cat == "location_question":
        return "Send me the community or property name and I’ll share the location details."
    if cat == "availability_question":
        return "Send the property reference or community and I’ll check availability."
    if cat == "price_range_question":
        return "Send area, type, bedrooms, and budget in AED, and I’ll shortlist options."
    if cat == "document_checklist":
        return "Sure — tell me if it’s buying, renting, selling, Ejari, NOC, or handover and I’ll send the right checklist."
    if cat == "viewing_coordination":
        return "Sure — send the preferred time, property/community, and number of viewers, and I’ll coordinate it."
    if intent == "Buyer / Investment":
        return "Thanks — send your budget, area, and whether this is for end-use or investment, and I’ll shortlist options."
    if intent == "Rental":
        return "Thanks — send your area, budget, bedrooms, and move-in date, and I’ll check suitable options."
    if intent == "Seller / Valuation":
        return "Thanks — send the property, unit type, size, and expected price, and I’ll prepare the next step."
    if intent == "NOC / Approval":
        return "Thanks — send the community, property type, status, and any developer notice, and I’ll check the NOC path."
    if canonical_prompt:
        # The canonical prompt is loaded here so the live router stays aligned
        # with the same tone source used by the draft/hold flow.
        return "Thanks — send the area, budget, and what you need, and I’ll take it from there."
    return "Thanks — send the area, budget, and what you need, and I’ll take it from there."


def process(payload: dict) -> dict:
    event = normalize(payload)
    text = (event.get("message_text") or "").strip()
    context = load_contact_context(
        {
            "provider_event": event,
            "crm": {
                "contact": {
                    "Full Name": event["profile_name"],
                    "WhatsApp Phone": event["from_phone"],
                }
            },
        },
        db_path=Path(os.getenv("AIOS_CONVERSATION_DB", str(DEFAULT_DB))),
        whatsapp_chat_db=Path(os.getenv("AIOS_WHATSAPP_CHAT_DB", str(DEFAULT_WHATSAPP_CHAT_DB))),
        whatsapp_contacts_db=Path(os.getenv("AIOS_WHATSAPP_CONTACTS_DB", str(DEFAULT_WHATSAPP_CONTACTS_DB))),
    )
    self_thread = bool(context.get("is_self_thread"))
    actionable = bool(text) and event.get("message_type") not in NON_ACTIONABLE_MESSAGE_TYPES and event.get("actionable", True) and not event.get("is_group_or_channel", False) and not event.get("is_self_chat", False) and not self_thread
    if event.get("is_group_or_channel") or event.get("is_self_chat") or self_thread:
        context = {
            "canonical_contact": {
                "phone": event.get("from_phone", "UNKNOWN"),
                "digits": re.sub(r"\D", "", event.get("from_phone") or ""),
                "identifiers": [],
                "name": event.get("profile_name") or "WhatsApp Contact",
            },
            "history": {
                "summary": "Group, channel, or self-chat WhatsApp event ignored.",
                "recent_messages": [],
                "aios_conversation": [],
                "aios_messages": [],
                "aios_decisions": [],
                "whatsapp_contact_rows": [],
                "whatsapp_sessions": [],
                "whatsapp_messages": [],
            },
            "known_contact_name": event.get("profile_name") or "WhatsApp Contact",
            "has_prior_history": False,
            "is_self_thread": True,
            "match_quality": {
                "exact_phone_match": False,
                "digit_match": False,
                "alias_match_count": 0,
            },
        }
    lang = language(text)
    lead_type, intent, agent = intent_and_agent(text)
    cat = category(text)
    flags = risk_flags(text)
    pr = "Hot" if any(w in (text or "").lower() for w in HOT) else ("Warm" if intent != "General Real Estate" else "Normal")
    safe = actionable and cat in AUTO_SAFE_CATEGORIES and not flags
    reply = draft_reply(text, lang, intent, cat, context)
    if not actionable:
        reply = ""
    elif not safe:
        reply = "Thanks. I received your message and Omar will review it before replying because it may require approval or careful handling."
    canonical_digits = context.get("canonical_contact", {}).get("digits") or re.sub(r"\D", "", event["from_phone"])
    lead_id = "LEAD-" + canonical_digits[-6:] + "-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    due = datetime.now(timezone.utc) + timedelta(hours=1 if pr == "Hot" else 4 if pr == "Warm" else 24)
    tool_plan = build_tool_plan(intent, cat, flags, context)
    return {
        "provider_event": event,
        "conversation_context": context,
        "classification": {
            "language": lang,
            "lead_type": lead_type,
            "intent": intent,
            "category": "non_actionable_event" if (not actionable or event.get("is_group_or_channel") or event.get("is_self_chat") or self_thread) else cat,
            "priority": pr,
            "assigned_agent": agent,
            "risk_flags": flags,
            "safe_auto_reply": safe,
            "human_takeover_required": bool(flags) and actionable,
            "actionable": actionable,
            "is_self_chat": bool(event.get("is_self_chat")),
            "is_group_or_channel": bool(event.get("is_group_or_channel")),
            "is_self_thread": self_thread,
        },
        "crm": {
            "contact": {
                "Full Name": context.get("known_contact_name") or event["profile_name"],
                "WhatsApp Phone": event["from_phone"],
                "Language": lang,
                "Source": f"WhatsApp - {event['provider']}",
                "Last Message At": event["timestamp"],
                "Lead Temperature": pr,
                "Updated At": now_iso(),
                "Conversation Context": context.get("history", {}).get("summary", ""),
                "Has Prior History": context.get("has_prior_history", False),
            },
            "lead": {
                "Lead ID": lead_id,
                "Contact Phone": event["from_phone"],
                "Client Intent": intent,
                "Priority": pr,
                "Stage": "New WhatsApp Lead",
                "Assigned Agent": "Omar",
                "Agent Command": agent,
                "Last Touch": event["timestamp"],
                "Next Follow Up": due.isoformat(),
                "Summary": f"{intent}; {pr}; {text[:240]}",
                "Created At": now_iso(),
                "Updated At": now_iso(),
            },
            "message": {
                "Message ID": event["message_id"],
                "Direction": "Inbound",
                "Channel": "WhatsApp",
                "Provider": event["provider"],
                "Contact Phone": event["from_phone"],
                "Lead ID": lead_id,
                "Message Text": text,
                "Language": lang,
                "Received At": event["timestamp"],
                "Status": "Received",
                "Conversation Context": context.get("history", {}).get("summary", ""),
            },
            "task": {
                "Task ID": "TASK-" + str(uuid.uuid4())[:8].upper(),
                "Lead ID": lead_id,
                "Title": f"{pr}: WhatsApp {intent} follow-up",
                "Due At": due.isoformat(),
                "Owner": "Omar",
                "Status": "Open",
            },
            "dashboard_log": {
                "Metric ID": "MET-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "Lead ID": lead_id,
                "Provider": event["provider"],
                "Priority": pr,
                "Category": cat,
                "Safe Auto Reply": safe,
                "Logged At": now_iso(),
            },
        },
        "reply": {
            "mode": "AUTO_REPLY_SAFE" if safe else ("NO_REPLY_NON_ACTIONABLE" if not actionable else "OMAR_APPROVAL_REQUIRED"),
            "text": reply,
            "twiml": f"<Response><Message>{html.escape(reply)}</Message></Response>" if safe and event["provider"] == "twilio" else None,
            "cloud_api_payload": {
                "messaging_product": "whatsapp",
                "to": event["from_phone"].replace("+", ""),
                "type": "text",
                "text": {"body": reply},
            } if safe and event["provider"] != "twilio" else None,
        },
        "safety_gate": "AUTO_REPLY_ALLOWED" if safe else ("NO_REPLY_NON_ACTIONABLE" if not actionable else "HOLD_FOR_OMAR_APPROVAL"),
        "tool_plan": tool_plan,
        "reply_style": reply_style(lang),
        "canonical_prompt_loaded": bool(load_canonical_prompt()),
        "continuity": {
            "has_prior_history": context.get("has_prior_history", False),
            "recent_message_count": len((context.get("history") or {}).get("recent_messages") or []),
            "summary": (context.get("history") or {}).get("summary", ""),
        },
    }


if __name__ == "__main__":
    payload = parse_raw(sys.stdin.read())
    print(json.dumps(process(payload), ensure_ascii=False, indent=2))
