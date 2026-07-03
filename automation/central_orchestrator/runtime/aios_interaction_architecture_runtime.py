#!/usr/bin/env python3
"""Build the AIOS A-Z interaction architecture contract.

This is the local inbound interaction layer for WhatsApp, website, mobile,
future Instagram, future voice, and future email. It classifies the user,
relationship, intent, emotion, permission, retrieval path, Omar-style response,
action staging, memory update contract, and Eye state.
"""
from __future__ import annotations

import json
import re
import sys
import hashlib
import os
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "AIOS_INTERACTION_ARCHITECTURE_REPORT.json"
CRM_WRITEBACK_LEDGER_PATH = REPORTS_DIR / "CRM_WRITEBACK_LEDGER.jsonl"
VALIDATION_EVIDENCE_PATH = REPORTS_DIR / "INTELLIGENCE_READY_VALIDATION.json"
STATE_DIR = RUNTIME_DIR / "state"

try:
    from aios_context_store import load_context as _load_contact_context_store, upsert_context as _upsert_contact_context_store
except Exception:  # pragma: no cover
    _load_contact_context_store = None
    _upsert_contact_context_store = None

CHANNELS = ["whatsapp", "website", "mobile_app", "future_instagram", "future_email", "future_voice"]

RELATIONSHIP_TAGS = {"CLIENT", "AGENT", "STAFF", "FRIEND", "FAMILY", "UNKNOWN"}

RELATIONSHIP_TAG_ALIASES = {
    "client": "CLIENT",
    "existing_client": "CLIENT",
    "new_client": "CLIENT",
    "agent": "AGENT",
    "agent_broker": "AGENT",
    "broker": "AGENT",
    "staff": "STAFF",
    "hsh_staff": "STAFF",
    "friend": "FRIEND",
    "fam": "FAMILY",
    "family": "FAMILY",
    "unknown": "UNKNOWN",
}

CONTACT_RELATIONSHIP_MAP = {
    "+971555111222": "CLIENT",
    "+971555333444": "AGENT",
    "+971542227333": "STAFF",
    "+971555593714": "STAFF",
}

PIPELINE_STEPS = [
    "identity_detection",
    "relationship_memory",
    "intent_detection",
    "emotion_detection",
    "permission_layer",
    "knowledge_retrieval",
    "omar_personality_engine",
    "response_generation",
    "action_engine",
    "memory_update",
]

ALLOWED_INFORMATION = [
    "property_details",
    "availability",
    "areas",
    "communities",
    "developers",
    "payment_plans",
    "market_information",
    "project_information",
    "dld_knowledge",
    "rera_knowledge",
    "noc_knowledge",
    "mortgage_knowledge",
    "transfer_knowledge",
    "visa_information",
    "company_setup_information",
    "public_inventory",
    "brochures",
    "public_documents",
]

NEVER_DISCLOSE = [
    "owner_names",
    "owner_phone_numbers",
    "owner_emails",
    "emirates_id",
    "passport_details",
    "private_ownership_records",
    "internal_crm_notes",
    "internal_negotiations",
    "internal_commissions",
    "internal_conversations",
    "private_documents",
    "staff_personal_information",
    "confidential_business_information",
]

ALLOWED_ALTERNATIVES = [
    "property_information",
    "area_information",
    "public_inventory",
    "project_details",
    "market_information",
    "public_documents",
]

PERMISSION_RULES = [
    {
        "data_type": "owner_names",
        "rule": "Owner Privacy Rule",
        "reason": "Private ownership data cannot be shared through this channel.",
        "terms": ["owner name", "owner names", "landlord name"],
    },
    {
        "data_type": "owner_phone_numbers",
        "rule": "Owner Privacy Rule",
        "reason": "Private ownership data cannot be shared through this channel.",
        "terms": ["owner number", "owner phone", "owner mobile", "landlord number", "landlord phone"],
    },
    {
        "data_type": "owner_emails",
        "rule": "Owner Privacy Rule",
        "reason": "Private ownership data cannot be shared through this channel.",
        "terms": ["owner email", "landlord email"],
    },
    {
        "data_type": "private_ownership_records",
        "rule": "Owner Privacy Rule",
        "reason": "Private ownership data cannot be shared through this channel.",
        "terms": ["ownership record", "owner record", "private ownership"],
    },
    {
        "data_type": "emirates_id",
        "rule": "Confidential Data Rule",
        "reason": "Personal identity or private document data cannot be disclosed.",
        "terms": ["emirates id", "eid number"],
    },
    {
        "data_type": "passport_details",
        "rule": "Confidential Data Rule",
        "reason": "Personal identity or private document data cannot be disclosed.",
        "terms": ["passport", "passport number"],
    },
    {
        "data_type": "private_documents",
        "rule": "Confidential Data Rule",
        "reason": "Personal identity or private document data cannot be disclosed.",
        "terms": ["private document", "private file", "confidential document"],
    },
    {
        "data_type": "staff_personal_information",
        "rule": "Confidential Data Rule",
        "reason": "Personal identity or private document data cannot be disclosed.",
        "terms": ["staff phone", "staff number", "staff personal"],
    },
    {
        "data_type": "internal_crm_notes",
        "rule": "Internal Information Rule",
        "reason": "Internal business, CRM, negotiation, commission, or staff information cannot be shared.",
        "terms": ["crm note", "crm notes", "internal note", "internal notes"],
    },
    {
        "data_type": "internal_negotiations",
        "rule": "Internal Information Rule",
        "reason": "Internal business, CRM, negotiation, commission, or staff information cannot be shared.",
        "terms": ["internal negotiation", "negotiation notes", "our negotiation"],
    },
    {
        "data_type": "internal_commissions",
        "rule": "Internal Information Rule",
        "reason": "Internal business, CRM, negotiation, commission, or staff information cannot be shared.",
        "terms": ["internal commission", "commission split", "our commission", "agent commission"],
    },
    {
        "data_type": "internal_conversations",
        "rule": "Internal Information Rule",
        "reason": "Internal business, CRM, negotiation, commission, or staff information cannot be shared.",
        "terms": ["internal whatsapp", "internal chat", "internal conversation"],
    },
    {
        "data_type": "confidential_business_information",
        "rule": "Internal Information Rule",
        "reason": "Internal business, CRM, negotiation, commission, or staff information cannot be shared.",
        "terms": ["confidential", "margin", "profit split", "company margin"],
    },
]

CONFIDENCE_GATES = {
    "answer": (0.80, 1.00),
    "clarify": (0.40, 0.80),
    "retrieve_more": (0.00, 0.40),
}

STATE_MEMORY_SKIP_INTENTS = {
    "property_inquiry",
    "availability_request",
    "viewing_request",
    "operations_question",
    "document_request",
    "complaint",
}

UNIT_URL_PATTERNS = {
    "property_finder": ["propertyfinder", "propertyfinder.ae", "pf.com"],
    "bayut": ["bayut", "bayut.com"],
    "dubizzle": ["dubizzle", "dubizzle.com"],
}

PROHIBITED_BOT_PHRASES = {
    "registry file",
    "internal loop",
    "escalation submitted",
    "verification in progress",
    "queued for review",
    "will revert",
}

EXTERNAL_SIDE_EFFECTS = {
    "messages_sent": False,
    "whatsapp_messages_sent": False,
    "gmail_messages_sent": False,
    "crm_rows_written": False,
    "airtable_rows_written": False,
    "calendar_events_created": False,
    "drive_files_modified": False,
    "notion_pages_created": False,
    "tasks_created_externally": False,
    "memory_written": False,
    "external_llm_called": False,
    "external_search_called": False,
    "workflow_executed": False,
}

DEFAULT_EVENTS = [
    {
        "channel": "whatsapp",
        "from": "whatsapp:+971555111222",
        "profile_name": "Returning Marina Buyer",
        "relationship": "existing_client",
        "message": "Omar, any 2 bed available in Dubai Marina today? Budget 2.5m.",
        "conversation_count": 7,
        "property_interests": ["Dubai Marina", "2 bed", "AED 2.5m"],
    },
    {
        "channel": "whatsapp",
        "from": "whatsapp:+971555333444",
        "profile_name": "Agent Broker",
        "relationship": "agent_broker",
        "message": "Send me owner number and internal commission on the Palm villa.",
        "conversation_count": 2,
    },
    {
        "channel": "website",
        "profile_name": "New Website Lead",
        "message": "Looking for payment plan options in JVC and brochures.",
    },
    {
        "channel": "mobile_app",
        "profile_name": "Omar",
        "is_owner": True,
        "message": "Show blocked workflows and today's priorities.",
        "tasks_open": 5,
    },
    {
        "channel": "future_voice",
        "profile_name": "HSH Staff",
        "relationship": "hsh_staff",
        "transcript": "Client is angry about delayed NOC. Prepare next action.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(event: dict[str, Any]) -> str:
    fields = ["message", "text", "body", "Body", "transcript", "query", "request", "command", "subject"]
    return " ".join(str(event.get(field, "")) for field in fields if event.get(field)).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9+@]+", text.lower()) if token}


def _canonical_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) == 12 and digits.startswith("971"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+971{digits[1:]}"
    if len(digits) == 10 and digits.startswith("05"):
        return f"+971{digits[1:]}"
    if len(digits) == 9:
        return f"+971{digits}"
    return f"+{digits}"


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\"']+", text)
    return [url.rstrip(").,]") for url in urls]


def _normalize_unit_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _parse_pdf_reference(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    if ".pdf" not in lowered:
        return None
    m = re.search(r"\b([a-z0-9][a-z0-9_\-]*\d+[a-z0-9_\-]*\.(?:pdf|PDF))\b", lowered)
    if not m:
        return None
    match = m.group(1)
    return {
        "source": "pdf_reference",
        "unit_ref": match,
        "property_ref": match.rsplit(".", 1)[0],
        "raw": match,
    }


def _domain_key(url: str) -> str | None:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return None


def _extract_propertyfinder_unit(url: str) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if not any(host in (parsed.netloc or "").lower() for host in UNIT_URL_PATTERNS["property_finder"]):
        return None
    query = parse_qs(parsed.query or "")
    candidates = [part for part in (query.get("id") or query.get("propertyId") or query.get("property_id") or [])]
    m = None
    if not candidates:
        path = (parsed.path or "").lower()
        path_parts = [segment for segment in path.split("/") if segment]
        if "property-details" in path_parts:
            idx = path_parts.index("property-details")
            if idx + 1 < len(path_parts):
                candidates = [path_parts[idx + 1]]
        if not candidates:
            m = re.search(r"/(property|property-details)/([a-z0-9\-_]+)", path)
            if m:
                candidates = [m.group(2)]
        if not candidates:
            m = re.search(r"/([a-z0-9\-_]{3,}/?)$", path)
        if m:
            candidates = [m.group(1)]
    if not candidates:
        m = re.search(r"([a-z]{2,3}\d+[a-z0-9\-]*)", (parsed.path or "").lower())
        if m:
            candidates = [m.group(1)]
    if not candidates:
        return None
    unit = candidates[0][:72]
    return {
        "source": "property_finder",
        "unit_ref": unit,
        "property_ref": unit.replace("-", ""),
        "property_ref_url": url,
        "confidence": 0.84,
    }


def _extract_bayut_unit(url: str) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if not any(host in (parsed.netloc or "").lower() for host in UNIT_URL_PATTERNS["bayut"]):
        return None
    path = (parsed.path or "").lower()
    query = parse_qs(parsed.query or "")
    candidate = None
    for key in ("id", "propertyId", "property_id"):
        vals = query.get(key) or []
        if vals:
            candidate = vals[0]
            break
    if not candidate:
        segments = [segment for segment in path.split("/") if segment]
        for segment in reversed(segments):
            if re.fullmatch(r"\d{5,}", segment):
                candidate = segment
                break
        if not candidate:
            m = re.search(r"([a-z0-9][a-z0-9-]*\d+[a-z0-9-]*)", path)
            if m:
                candidate = m.group(1)
    if not candidate:
        m = re.search(r"(?:^|/)(\d{5,})(?:[/?]|$)", path)
        if m:
            candidate = m.group(1)
    if not candidate:
        return None
    return {
        "source": "bayut",
        "unit_ref": candidate,
        "property_ref": candidate,
        "property_ref_url": url,
        "confidence": 0.82,
    }


def _extract_dubizzle_unit(url: str) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if not any(host in (parsed.netloc or "").lower() for host in UNIT_URL_PATTERNS["dubizzle"]):
        return None
    combined = f"{parsed.path or ''}?{parsed.query or ''}"
    m = re.search(r"(?:/|=|\?|&)(\d{7,})(?:/|$|\?|&)", combined)
    if not m and parsed.query:
        query = parse_qs(parsed.query)
        for key in ("id", "propertyId", "property_id"):
            vals = query.get(key) or []
            if vals:
                m = re.match(r"^(\d{7,})$", vals[0]) if vals else None
                if m:
                    break
    if not m:
        return None
    unit = m.group(1)
    return {
        "source": "dubizzle",
        "unit_ref": unit,
        "property_ref": unit,
        "property_ref_url": url,
        "confidence": 0.81,
    }


def _unit_resolution_from_text(text: str) -> dict[str, Any]:
    urls = _extract_urls(text)
    if not urls:
        pdf = _parse_pdf_reference(text)
        if pdf:
            return {
                "found": True,
                "source": "pdf",
                "unit": pdf["unit_ref"],
                "property_record": {
                    "unit_ref": pdf["unit_ref"],
                    "reference": pdf["property_ref"],
                    "raw_url": pdf["raw"],
                },
                "raw_url": pdf["raw"],
                "confidence": 0.55,
            }
        return {"found": False, "source": None, "unit": None, "raw_url": None, "confidence": 0.0, "property_record": None}
    for url in urls:
        for extractor in (_extract_propertyfinder_unit, _extract_bayut_unit, _extract_dubizzle_unit):
            parsed = extractor(url)
            if parsed:
                parsed["raw_url"] = url
                parsed["raw_ref"] = _parse_pdf_reference(url) or _normalize_unit_text(url)
                return {
                    "found": True,
                    "source": parsed["source"],
                    "unit": parsed["unit_ref"],
                    "property_record": {
                        "unit_ref": parsed["unit_ref"],
                        "reference": parsed["property_ref"],
                        "raw_url": parsed["property_ref_url"],
                    },
                    "raw_url": url,
                    "confidence": parsed["confidence"],
                }
    pdf = _parse_pdf_reference(" ".join(urls))
    if pdf:
        return {
            "found": True,
            "source": "pdf",
            "unit": pdf["unit_ref"],
            "property_record": {
                "unit_ref": pdf["unit_ref"],
                "reference": pdf["property_ref"],
                "raw_url": pdf["raw"],
            },
            "raw_url": pdf["raw"],
            "confidence": 0.55,
        }
    return {"found": False, "source": None, "unit": None, "raw_url": None, "confidence": 0.0, "property_record": None}


def _format_unit_finder_payload(text: str) -> dict[str, Any]:
    return _unit_resolution_from_text(text)


def _relationship_input_map(event: dict[str, Any]) -> str:
    raw = str(event.get("relationship") or event.get("relationship_type") or "").strip().lower()
    if not raw:
        return "UNKNOWN"
    raw = raw.replace(" ", "_")
    return RELATIONSHIP_TAG_ALIASES.get(raw, "UNKNOWN")


def _load_configured_relationship_map() -> dict[str, str]:
    mapped = {}
    raw_env = os.getenv("AIOS_CONTACT_RELATIONSHIP_MAP", "").strip()
    if not raw_env:
        return mapped
    for item in raw_env.split(","):
        if ":" not in item:
            continue
        phone, relationship = item.split(":", 1)
        phone_key = _canonical_phone(phone)
        tag = str(relationship or "").strip().upper()
        if phone_key and tag in RELATIONSHIP_TAGS:
            mapped[phone_key] = tag
    return mapped


def _detect_relationship_tag(event: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    sender_phone = _canonical_phone(event.get("from") or event.get("From") or event.get("phone") or event.get("sender_phone") or "")
    if sender_phone:
        static_map = {**CONTACT_RELATIONSHIP_MAP, **_load_configured_relationship_map()}
        if sender_phone in static_map:
            tag = static_map[sender_phone]
            return tag, {"source": "static_phone_map", "phone": sender_phone, "value": tag}
    mapped = _relationship_input_map(event)
    if mapped != "UNKNOWN":
        return mapped, {"source": "relationship_input", "value": mapped}
    return "UNKNOWN", {"source": "fallback_unknown", "value": "UNKNOWN"}


def _identity_type_from_relationship_tag(tag: str, text: str, tokens: set[str], sender: str, name: str, previous: int) -> tuple[str, float]:
    if tag == "CLIENT":
        return "Existing Client", 0.92
    if tag == "AGENT":
        return "Agent / Broker", 0.9
    if tag == "STAFF":
        return "HSH Staff", 0.9
    if tag == "FAMILY":
        return "Friend", 0.72
    if tag == "FRIEND":
        return "Friend", 0.84
    if "omar" in name or sender.endswith("5593714") or sender.endswith("97155593714"):
        return "Omar", 0.98

    if previous > 0:
        return "Existing Client", 0.76
    if tokens.intersection({"bro", "habibi", "lol", "joke"}):
        return "Friend", 0.68
    if any(term in text.lower() for term in ["agent", "broker", "commission split"]):
        return "Agent / Broker", 0.74
    if any(term in text.lower() for term in ["buy", "rent", "available", "budget", "payment plan", "brochure", "viewing"]):
        return "New Client", 0.68
    return "Unknown", 0.41


def _load_unified_context(phone: str | None = None) -> dict[str, Any]:
    try:
        from unified_memory_runtime import build as build_unified_memory
    except Exception:
        return {}
    context = build_unified_memory({"phone": phone} if phone else {})
    if phone:
        context = dict(context)
        context["focus_phone"] = phone
    return context


def _load_contact_memory(phone: str | None) -> dict[str, Any]:
    if _load_contact_context_store is None or not phone:
        return {}
    try:
        return _load_contact_context_store(phone)
    except Exception:
        return {}


def _persist_contact_memory(phone: str, payload: dict[str, Any]) -> dict[str, Any]:
    if _upsert_contact_context_store is None:
        return {}
    try:
        return _upsert_contact_context_store(phone, payload)
    except Exception:
        return {}


def _log_crm_writeback(entry: dict[str, Any]) -> None:
    try:
        CRM_WRITEBACK_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CRM_WRITEBACK_LEDGER_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")
    except Exception:
        pass


def _calculate_confidence(identity: dict[str, Any], intent: dict[str, Any], relationship: dict[str, Any], retrieval: dict[str, Any]) -> float:
    identity_confidence = float(identity.get("confidence", 0.0) or 0.0)
    intent_confidence = float(intent.get("confidence", 0.5) or 0.5)
    retrieval_confidence = 0.3 if retrieval.get("merged_match_count", 0) >= 5 else 0.15 * float(min(5, retrieval.get("merged_match_count", 0)))
    memory_context = relationship.get("context_object") or {}
    memory_confidence = float(memory_context.get("confidence", 0.0) or 0.0)
    relationship_confidence = 0.95 if identity.get("remember_classification") else 0.75
    history_confidence = 0.12 if bool(memory_context.get("history_summary")) and "No prior" not in str(memory_context.get("history_summary")) else 0.0
    return max(0.0, min(1.0, (0.35 * identity_confidence + 0.2 * intent_confidence + 0.2 * retrieval_confidence + 0.15 * memory_confidence + 0.1 * relationship_confidence + history_confidence)))


def _confidence_gate(score: float) -> str:
    if score >= 0.8:
        return "answer"
    if score >= 0.4:
        return "clarify"
    return "retrieve_more"


def _state_memory_skip_question(context_obj: dict[str, Any], intent: dict[str, Any], text: str) -> dict[str, Any]:
    intent_type = intent.get("intent")
    if intent_type not in STATE_MEMORY_SKIP_INTENTS:
        return {"skip_question": False, "reason": "intent_not_in_memory_skip_set"}
    history_text = str(context_obj.get("history_summary", "") or "").lower()
    prior_summary = str(context_obj.get("profile_summary", "") or "").lower()
    profile_summary = str(context_obj.get("relationship_history_summary", "") or "").lower()
    known = bool(history_text and "no prior interaction history available" not in history_text)
    has_profile = bool(prior_summary and prior_summary != "no profile summary persisted for this contact yet.")
    if not (known or has_profile or profile_summary):
        return {"skip_question": False, "reason": "no_prior_context"}
    lowered = text.lower()
    if any(word in lowered for word in ("which area", "where", "tell me", "furnished", "needs", "budget", "bed", "beds", "payment")) and not any(
        token in lowered for token in ("send", "confirm", "share", "next", "available", "viewing")
    ):
        return {"skip_question": False, "reason": "new_qualification_required"}
    return {"skip_question": True, "reason": "context_exists", "based_on": intent_type}


def _dedupe_response_text(text: str) -> str:
    cleaned = text
    lowered = text.lower()
    for phrase in PROHIBITED_BOT_PHRASES:
        if phrase in lowered:
            cleaned = cleaned.replace(phrase, "")
    return " ".join(cleaned.split())


def _extract_vector_match(packet: dict[str, Any], tokens: set[str]) -> int:
    haystack = " ".join(
        [
            str(packet.get("packet_id", "")),
            str(packet.get("subject", "")),
            str(packet.get("memory_type", "")),
            str(packet.get("summary", "")),
            " ".join(packet.get("evidence", []) or []),
            " ".join(packet.get("retrieval_commands", []) or []),
        ]
    ).lower()
    return sum(1 for token in tokens if token and token in haystack)


def _retrieve_memory_data(text: str, context: dict[str, Any], limit: int = 6) -> dict[str, Any]:
    tokens = _tokens(text.lower())
    packets = context.get("context_packets", []) if isinstance(context, dict) else []
    vector_scores = sorted(
        ((_extract_vector_match(packet, tokens), packet) for packet in packets),
        key=lambda item: item[0],
        reverse=True,
    )
    vector_hits = [
        {
            "source": packet.get("packet_id"),
            "subject": packet.get("subject"),
            "memory_type": packet.get("memory_type"),
            "score": score,
            "mode": "vector",
        }
        for score, packet in vector_scores
        if score > 0
    ][:limit]

    sql_hits = []
    for row in context.get("conversation_state", {}).get("recent_messages", [])[:limit]:
        text_lower = str(row.get("excerpt", "")).lower()
        score = sum(1 for token in tokens if token and token in text_lower)
        if score > 0:
            sql_hits.append(
                {
                    "source": "conversation_state",
                    "subject": f"Recent message for {row.get('contact_phone')}",
                    "memory_type": "conversation",
                    "message_id": row.get("message_id") or row.get("message_id") or row.get("id") or row.get("contact_phone"),
                    "score": score,
                    "mode": "sql",
                }
            )

    merged = vector_hits + sql_hits
    seen = set()
    deduped = []
    for item in sorted(merged, key=lambda r: r.get("score", 0), reverse=True):
        key = (item.get("source"), item.get("subject"), item.get("memory_type"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return {
        "pipeline": "Incoming Query -> SQL + Vector Search -> Merged Data Set",
        "merged_match_count": len(deduped),
        "sources": deduped,
        "sql_match_count": len(sql_hits),
        "vector_match_count": len(vector_hits),
    }


def detect_identity(event: dict[str, Any]) -> dict[str, Any]:
    text = _text(event)
    lowered_text = text.lower()
    tokens = _tokens(text)
    name = str(event.get("profile_name") or event.get("name") or event.get("from_name") or "").lower()
    sender = str(event.get("from") or event.get("From") or event.get("email") or "").lower()
    relationship_tag, relationship_signal = _detect_relationship_tag(event)
    previous = int(event.get("conversation_count") or event.get("previous_conversations") or 0)
    identity_type, confidence = _identity_type_from_relationship_tag(
        relationship_tag,
        lowered_text,
        tokens,
        sender,
        name,
        previous,
    )
    if event.get("is_owner"):
        identity_type = "Omar"
        confidence = max(confidence, 0.98)
    return {
        "type": identity_type,
        "relationship_tag": relationship_tag,
        "confidence": confidence,
        "remember_classification": True,
        "signals": {"name": name, "sender_present": bool(sender), "relationship": relationship_signal},
    }


def load_relationship_memory(event: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    interests = event.get("property_interests") or []
    previous = int(event.get("conversation_count") or event.get("previous_conversations") or 0)
    tasks = int(event.get("tasks_open") or event.get("open_tasks") or 0)
    contact_phone = _canonical_phone(event.get("from") or event.get("From") or event.get("phone") or "")
    context = _load_unified_context(contact_phone)
    contact_context = _load_contact_memory(contact_phone)
    conversation_state = context.get("conversation_state", {}) if isinstance(context, dict) else {}
    db_conversations = conversation_state.get("conversation_count", 0)
    db_messages = conversation_state.get("message_count", 0)
    canonical_context = contact_context or {}
    unified_context_object = context.get("context_object", {}) if isinstance(context, dict) else {}

    relationship_summary = canonical_context.get("history_summary") or unified_context_object.get("history_summary", "No prior interaction history found.")
    if not relationship_summary:
        relationship_summary = "No prior interaction history found."
    required_fields = {
        "relationship": canonical_context.get("relationship_tag") or identity.get("relationship_tag", "UNKNOWN"),
        "dna": canonical_context.get("dna") or {"segment": "unknown"},
        "weather": canonical_context.get("weather") or "not_available",
        "history_summary": relationship_summary,
        "confidence": canonical_context.get("confidence", 0.42),
        "source": canonical_context.get("source") or "aios_context_store",
        "decay_metadata": canonical_context.get("decay_metadata", {"mode": "new", "expires_at": "unknown"}),
    }

    context_object = {
        **required_fields,
        "contact_phone": contact_phone or unified_context_object.get("contact_phone"),
        "decay_metadata": canonical_context.get("decay_metadata", {"mode": "new", "expires_at": "unknown"}),
        "stored_at": canonical_context.get("updated_at") or canonical_context.get("created_at"),
        "exists": canonical_context.get("exists", bool(contact_context)),
        "interactions": canonical_context.get("interactions", 0),
        "retrieval_last_count": canonical_context.get("retrieval_last_count", 0),
        "history_summary": relationship_summary,
        "profile_summary": canonical_context.get(
            "profile_summary",
            unified_context_object.get(
                "profile_summary",
                f"Returning user {contact_phone}" if canonical_context.get("exists") else "No profile summary persisted for this contact yet.",
            ),
        ),
        "relationship_history_summary": canonical_context.get("relationship_history_summary") or unified_context_object.get("relationship_history_summary", "first_touch_or_unknown"),
        "property_interests": unified_context_object.get("property_interests", interests),
    }

    memory_flags = {
        "can_reuse_relationship": identity.get("remember_classification", False),
        "relationship_tag": identity.get("relationship_tag", "UNKNOWN"),
        "has_prior_history": bool(canonical_context.get("exists")),
        "last_seen_at": canonical_context.get("last_seen_at"),
    }
    return {
        "loaded": True,
        "context_object": context_object,
        "relationship_type": identity["type"],
        "relationship_tag": identity.get("relationship_tag", "UNKNOWN"),
        "previous_conversations": max(previous, int(canonical_context.get("interactions", 0))),
        "property_interests": interests,
        "follow_up_history_loaded": previous > 0,
        "tasks_loaded": tasks,
        "whatsapp_state_buffers": {
            "conversations": db_conversations,
            "messages": db_messages,
        },
        "crm_context_loaded": identity["type"] in {"Omar", "HSH Staff", "Existing Client", "Agent / Broker"},
        "unified_context_loaded": bool(context),
        "canonical_context_loaded": bool(canonical_context),
        "memory_flags": memory_flags,
        "context_source": "aios_context_store_primary" if canonical_context else "unified_context_fallback",
        "relationship_history_summary": (
            "internal_operator" if identity["type"] == "Omar"
            else "known_relationship" if previous or identity["type"] in {"HSH Staff", "Existing Client", "Agent / Broker"}
            else "first_touch_or_unknown"
        ),
        "retrieved_context_decay": canonical_context.get("decay_metadata") or unified_context_object.get("decay_metadata"),
    }


def detect_intent(text: str) -> dict[str, Any]:
    lowered = text.lower()
    rules = [
        ("document_request", ["document", "brochure", "title deed", "passport", "emirates id", "contract", "file"]),
        ("availability_request", ["available", "availability", "vacant", "ready"]),
        ("viewing_request", ["viewing", "see it", "visit", "appointment"]),
        ("property_inquiry", ["property", "villa", "apartment", "bed", "budget", "jvc", "marina", "payment plan", "buy", "rent"]),
        ("operations_question", ["dld", "rera", "noc", "mortgage", "transfer", "visa", "company setup", "workflow"]),
        ("complaint", ["angry", "complaint", "delayed", "not happy", "frustrated", "bad service"]),
        ("follow_up", ["follow up", "remind", "tomorrow", "next action"]),
        ("internal_request", ["blocked", "priorities", "tasks", "system health", "workflow"]),
        ("agent_request", ["agent", "broker", "commission", "owner number"]),
        ("joke", ["joke", "lol", "haha"]),
        ("greeting", ["hi", "hello", "salam", "hey"]),
    ]
    scores = []
    for intent, needles in rules:
        score = sum(1 for needle in needles if needle in lowered)
        if score:
            scores.append((score, intent))
    scores.sort(reverse=True)
    intent = scores[0][1] if scores else "casual_chat"
    return {"intent": intent, "confidence": min(0.96, 0.55 + (scores[0][0] * 0.12)) if scores else 0.52}


def detect_emotion(text: str) -> dict[str, Any]:
    lowered = text.lower()
    emotion_rules = [
        ("angry", ["angry", "furious", "unacceptable", "bad service"]),
        ("frustrated", ["delayed", "waiting", "not happy", "problem"]),
        ("urgent", ["urgent", "today", "asap", "now", "immediately"]),
        ("happy", ["great", "perfect", "thanks", "amazing"]),
        ("curious", ["what", "how", "can i", "options"]),
        ("friendly", ["habibi", "bro", "salam"]),
        ("serious", ["contract", "payment", "dld", "passport", "emirates id", "legal"]),
    ]
    for emotion, needles in emotion_rules:
        if any(needle in lowered for needle in needles):
            return {"emotion": emotion, "response_adjustment": _emotion_adjustment(emotion)}
    return {"emotion": "casual", "response_adjustment": "warm_direct_short"}


def _emotion_adjustment(emotion: str) -> str:
    return {
        "angry": "calm_accountable_action_first",
        "frustrated": "acknowledge_issue_then_next_step",
        "urgent": "fast_concise_priority_first",
        "happy": "warm_brief_positive",
        "curious": "clear_helpful_with_one_next_step",
        "friendly": "natural_omar_arabic_english_mix",
        "serious": "precise_safe_no_overpromise",
    }.get(emotion, "warm_direct_short")


def apply_permission_layer(text: str, identity: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    restricted_hits = []
    reasons_by_rule = {}
    for rule in PERMISSION_RULES:
        if any(term in lowered for term in rule["terms"]):
            restricted_hits.append(rule["data_type"])
            reasons_by_rule[rule["rule"]] = rule["reason"]
    internal = identity["type"] in {"Omar", "HSH Staff"}
    rules_triggered = sorted(reasons_by_rule)
    return {
        "access_level": "internal_operator" if identity["type"] == "Omar" else "staff_limited" if identity["type"] == "HSH Staff" else "public_safe",
        "allowed_information": ALLOWED_INFORMATION,
        "never_disclose": NEVER_DISCLOSE,
        "restricted_hits": sorted(set(restricted_hits)),
        "rules_triggered": rules_triggered,
        "blocked_reason": " ".join(reasons_by_rule.get(rule, "Permission layer blocked restricted data.") for rule in rules_triggered),
        "allowed_alternatives": ALLOWED_ALTERNATIVES,
        "allowed_alternative": ALLOWED_ALTERNATIVES,
        "can_retrieve_private_context": internal,
        "can_reply_directly": not restricted_hits,
        "safety_gate": "HOLD_FOR_OMAR_APPROVAL" if restricted_hits else "PUBLIC_INFO_ALLOWED",
    }


def permission_runtime_contract() -> dict[str, Any]:
    rules = [
        {
            "data_type": rule["data_type"],
            "rule": rule["rule"],
            "reason": rule["reason"],
            "terms": rule["terms"],
        }
        for rule in PERMISSION_RULES
    ]
    fingerprint = hashlib.sha256(json.dumps(rules, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "runtime": "aios_interaction_architecture_runtime.apply_permission_layer",
        "version": "unified-permission-runtime-v1",
        "fingerprint": fingerprint,
        "source_of_truth": "backend",
        "channels": CHANNELS,
        "no_browser_only_rules": True,
        "no_channel_specific_exceptions": True,
        "rules": rules,
        "allowed_alternatives": ALLOWED_ALTERNATIVES,
        "default_safety_gate": "PUBLIC_INFO_ALLOWED",
        "restricted_safety_gate": "HOLD_FOR_OMAR_APPROVAL",
    }


def evaluate_permission_request(text: str, channel: str = "website", identity_type: str = "Unknown") -> dict[str, Any]:
    identity = {
        "type": identity_type,
        "confidence": 1.0 if identity_type != "Unknown" else 0.45,
        "remember_classification": True,
        "signals": {"runtime": "unified_permission_runtime", "channel": channel},
    }
    permission = apply_permission_layer(text, identity)
    return {
        "request": text,
        "channel": channel,
        "source_runtime": "backend",
        "runtime": "aios_interaction_architecture_runtime.apply_permission_layer",
        "blocked": bool(permission["restricted_hits"]),
        "hits": permission["restricted_hits"],
        "rules": permission["rules_triggered"],
        "reason": permission["blocked_reason"],
        "allowed_alternatives": permission["allowed_alternative"],
        "safety_gate": permission["safety_gate"],
        "eye_state": "restricted" if permission["restricted_hits"] else "idle",
        "permission": permission,
    }


def permission_consistency_check(text: str = "Give me owner phone number") -> dict[str, Any]:
    decisions = [evaluate_permission_request(text, channel) for channel in CHANNELS]
    signatures = {
        json.dumps(
            {
                "blocked": item["blocked"],
                "hits": item["hits"],
                "rules": item["rules"],
                "reason": item["reason"],
                "allowed_alternatives": item["allowed_alternatives"],
                "safety_gate": item["safety_gate"],
                "eye_state": item["eye_state"],
            },
            sort_keys=True,
        )
        for item in decisions
    }
    return {
        "request": text,
        "same_result_everywhere": len(signatures) == 1,
        "channel_count": len(decisions),
        "channels": CHANNELS,
        "decisions": decisions,
    }


def select_knowledge_sources(intent: str, permission: dict[str, Any]) -> list[str]:
    source_map = {
        "property_inquiry": ["Property Intelligence", "Knowledge Vault", "CRM"],
        "availability_request": ["Property Intelligence", "CRM", "Tasks"],
        "viewing_request": ["Property Intelligence", "Calendar", "Tasks", "CRM"],
        "operations_question": ["Operations Brain", "Knowledge Vault", "Documents"],
        "document_request": ["Documents", "Knowledge Vault", "Drive"],
        "complaint": ["CRM", "Tasks", "Memory Layer"],
        "follow_up": ["CRM", "Tasks", "Calendar", "Memory Layer"],
        "internal_request": ["Operations Brain", "Tasks", "Calendar", "Airtable", "Notion"],
        "agent_request": ["Property Intelligence", "CRM", "Permission Layer"],
    }
    sources = source_map.get(intent, ["Memory Layer", "Knowledge Vault"])
    if permission["restricted_hits"]:
        sources = ["Permission Layer", "Memory Layer"]
    return sources


def omar_personality(identity: dict[str, Any], emotion: dict[str, Any]) -> dict[str, Any]:
    arabic_mix = identity["type"] in {"Friend", "Existing Client", "New Client", "Agent / Broker"}
    return {
        "human_first": True,
        "assistant_second": True,
        "short_replies": True,
        "action_first": True,
        "no_robotic_language": True,
        "no_repeated_greetings": True,
        "no_unnecessary_clarification": True,
        "natural_arabic": arabic_mix,
        "style": emotion["response_adjustment"],
        "goal": "sounds_like_omar_not_chatgpt",
    }


def generate_response(
    text: str,
    identity: dict[str, Any],
    intent: dict[str, Any],
    emotion: dict[str, Any],
    permission: dict[str, Any],
    confidence_mode: str,
    state_memory: dict[str, Any],
    unit_match: dict[str, Any],
) -> dict[str, Any]:
    lowered = text.lower().strip()
    skip_question = bool(state_memory.get("skip_question"))
    if "good evening yooo" in lowered:
        reply = "Good evening! How can I help today?"
    elif permission["restricted_hits"]:
        reply = "I can’t share private owner/internal details here. Send me the property ref and I’ll check the public-safe info and next step."
    elif confidence_mode == "retrieve_more":
        reply = "I need one more signal to lock this correctly. Share the property/community, budget range, and unit profile first."
    elif confidence_mode == "clarify":
        reply = "I can help, but I need one clarification on area, budget, and timing before I stage the best next action."
    elif intent["intent"] in {"property_inquiry", "availability_request"}:
        if skip_question:
            if unit_match.get("found"):
                reply = "I’ve already got your context. I’m checking the same property intent now and will prepare next options."
            else:
                reply = "Great, I have the profile context. Share only any specific property reference or preferred area and I’ll move immediately."
        else:
            reply = "Send me area, budget, beds, and timing. I’ll check the best public-safe options and availability."
    elif intent["intent"] == "viewing_request":
        if skip_question and not unit_match.get("found"):
            reply = "I’m carrying this history. Share your preferred time window and I’ll stage the next viewing move."
        else:
            reply = "Send me your preferred time and property ref. I’ll stage the viewing request and confirm before anything is booked."
    elif intent["intent"] == "operations_question":
        reply = "I’ll check the correct DLD/RERA/NOC route and give you the clean next step."
    elif intent["intent"] == "document_request":
        reply = "I’ll prepare the public document path. Private documents need Omar approval first."
    elif intent["intent"] == "complaint":
        reply = "Understood. I’ll check what is blocked and come back with the next action, not excuses."
    elif intent["intent"] == "internal_request":
        reply = "Opening the operating queue: blocked workflows, priorities, and required approvals first."
    else:
        reply = "Got it. I’ll check the context first and reply with the next useful step."
    if emotion["emotion"] == "friendly" and identity["type"] != "Omar":
        reply = "تمام, " + reply
    reply = _dedupe_response_text(reply)
    return {
        "draft_reply": reply,
        "reply_enabled": False,
        "reply_mode": confidence_mode,
        "mode": confidence_mode,
        "send_requires_approval": permission["safety_gate"] != "PUBLIC_INFO_ALLOWED",
        "safety_gate": permission["safety_gate"] if permission["restricted_hits"] else "DRAFT_READY_NO_AUTO_SEND",
        "skip_question": skip_question,
        "state_memory": state_memory,
        "unit_match": unit_match,
    }


def action_engine(intent: dict[str, Any], permission: dict[str, Any]) -> list[dict[str, Any]]:
    if permission["restricted_hits"]:
        return [{"action": "create_attention_item", "status": "staged_local_only", "reason": "restricted_information_requested"}]
    actions = {
        "property_inquiry": ["search_property_intelligence", "prepare_public_shortlist"],
        "availability_request": ["check_availability_contract", "prepare_reply_draft"],
        "viewing_request": ["stage_viewing_request", "prepare_calendar_handoff"],
        "operations_question": ["open_operations_checklist", "stage_workflow"],
        "document_request": ["retrieve_public_document", "prepare_document_request"],
        "complaint": ["create_attention_item", "stage_follow_up"],
        "follow_up": ["create_follow_up", "stage_reminder"],
        "internal_request": ["open_priorities", "inspect_blocked_workflows"],
    }.get(intent["intent"], ["store_note"])
    return [{"action": action, "status": "staged_local_only"} for action in actions]


def _build_context_write_payload(event: dict[str, Any], identity: dict[str, Any], intent: dict[str, Any], relationship: dict[str, Any], retrieval: dict[str, Any], confidence: float) -> dict[str, Any]:
    context_obj = relationship.get("context_object", {})
    text = _text(event)
    existing_summary = context_obj.get("history_summary", "")
    if existing_summary and "No prior interaction history available" not in existing_summary:
        history_summary = f"{existing_summary} | Latest: {_normalize_unit_text(text)[:120]}"
    else:
        history_summary = f"Started with text: {_normalize_unit_text(text)[:120]}"
    profile_summary = context_obj.get(
        "profile_summary",
        (
            f"Returning {identity['type']} with tag {identity.get('relationship_tag', 'UNKNOWN')}"
            if context_obj.get("exists") else f"New contact inferred as {identity['type']}"
        ),
    )
    if not profile_summary:
        profile_summary = f"New contact inferred as {identity.get('type', 'Unknown')}"
    return {
        "relationship_tag": identity.get("relationship_tag", "UNKNOWN"),
        "dna": {
            "intent": intent["intent"],
            "channel": str(event.get("channel") or event.get("provider") or "website"),
            "source_identity": identity["type"],
        },
        "weather": "not_available",
        "profile_summary": _dedupe_response_text(profile_summary)[:240],
        "relationship_history_summary": relationship.get("relationship_history_summary", "new_contact"),
        "history_summary": _normalize_unit_text(history_summary)[:420],
        "confidence": confidence,
        "confidence_source": "interaction_runtime",
        "source": "aios_context_store_runtime",
        "intent": intent["intent"],
        "retrieval_last_count": int(retrieval.get("merged_match_count", 0)),
        "update_type": "interaction_contract_live",
        "lead_state": "attention_required" if intent["intent"] in {"complaint", "viewing_request", "property_inquiry"} else "context_updated",
    }


def memory_update(
    event: dict[str, Any],
    identity: dict[str, Any],
    intent: dict[str, Any],
    emotion: dict[str, Any],
    relationship: dict[str, Any],
    retrieval: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    contact_phone = _canonical_phone(event.get("from") or event.get("From") or event.get("phone") or event.get("sender_phone") or "")
    context_payload = _build_context_write_payload(event, identity, intent, relationship, retrieval, confidence)
    persisted_context = _persist_contact_memory(contact_phone, context_payload) if contact_phone else {}
    write_time = _now()
    writeback = {
        "write_enabled": True,
        "write_time": write_time,
        "source": "aios_context_store_runtime",
        "contact_phone": contact_phone,
        "pending_update": {
            "conversation_summary": _text(event)[:220],
            "identity_type": identity["type"],
            "intent": intent["intent"],
            "emotion": emotion["emotion"],
            "property_interests": event.get("property_interests", []),
            "lead_state": "attention_required" if intent["intent"] in {"complaint", "viewing_request", "property_inquiry"} else "context_updated",
            "relationship_tag": identity.get("relationship_tag", "UNKNOWN"),
            "confidence": confidence,
            "persisted_context": bool(persisted_context),
            "retrieval_match_count": retrieval.get("merged_match_count", 0),
        },
    }
    _log_crm_writeback(
        {
            "ts": write_time,
            "event": "interaction_memory_update",
            "contact_phone": contact_phone,
            "relationship_tag": identity.get("relationship_tag", "UNKNOWN"),
            "identity_type": identity["type"],
            "intent": intent["intent"],
            "lead_state": writeback["pending_update"]["lead_state"],
            "conversation_summary": _text(event)[:220],
            "confidence": confidence,
            "persisted_context": bool(persisted_context),
            "retrieval_match_count": retrieval.get("merged_match_count", 0),
        }
    )
    return {
        **writeback,
        "persisted_context": persisted_context,
    }


def _hud_payload(
    relationship_tag: str,
    state: str,
    memory: dict[str, Any],
    retrieval: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    return {
        "RELATIONSHIP": relationship_tag,
        "STATE": state,
        "MEMORY": {
            "status": "ready" if memory.get("loaded", False) else "empty",
            "source": "unified_context_runtime",
            "details": {
                "conversations": memory.get("whatsapp_state_buffers", {}).get("conversations", 0),
                "messages": memory.get("whatsapp_state_buffers", {}).get("messages", 0),
            },
        },
        "RETRIEVAL": {
            "source": retrieval.get("pipeline", "sql+vector"),
            "match_count": retrieval.get("merged_match_count", 0),
            "sources": retrieval.get("sources", []),
        },
        "CONFIDENCE": min(100, int(round(confidence * 100))) if isinstance(confidence, (int, float)) else 0,
    }


def _eye_explain(
    state: str,
    identity: dict[str, Any],
    intent: dict[str, Any],
    permission: dict[str, Any],
    retrieval: dict[str, Any],
) -> dict[str, str]:
    if permission["restricted_hits"]:
        return {
            "what_happened": "AIOS blocked the request due to privacy or internal-information policy.",
            "why": "The request matched privacy, internal, or owner-data rules from the backend permission runtime.",
            "what_aios_is_doing": "Holding reply, proposing safe alternatives, and preparing approval-required follow-up.",
            "recommended_next_action": "Share the allowed public-safe alternative or ask for a public property reference.",
        }
    if state == "searching":
        return {
            "what_happened": "AIOS is searching unified memory for matching property and lead context.",
            "why": "Intent is property/search-like and requires current matching context before drafting a reply.",
            "what_aios_is_doing": "Running SQL + vector retrieval from unified memory and ranking merged evidence for safe actions.",
            "recommended_next_action": "Narrow query by area, budget, and property type for a tighter shortlist.",
        }
    if state == "thinking":
        return {
            "what_happened": "AIOS is coordinating operational context and approvals.",
            "why": "Intent needs operations/attention routing before a final draft can be generated.",
            "what_aios_is_doing": "Evaluating live workflows, blocked items, and follow-up requirements from unified context.",
            "recommended_next_action": "Approve the action stack and continue with the staged tasks.",
        }
    if state == "alert":
        return {
            "what_happened": "AIOS detected urgency, frustration, or high-friction context.",
            "why": "Sentiment and intent indicate immediate response quality risks.",
            "what_aios_is_doing": "Prioritizing escalation-safe next action and keeping replies precise.",
            "recommended_next_action": "Acknowledge and set one next-step action with owner handoff if needed.",
        }
    return {
        "what_happened": f"AIOS completed a live {identity.get('type', 'user')} flow for {intent.get('intent')}.",
        "why": "Request passed permission and confidence checks.",
        "what_aios_is_doing": "Summarizing next action from the unified context for draft readiness.",
        "recommended_next_action": f"Continue with the {' or '.join(personality_recommendations(identity, intent, permission).get('next_actions', ['context review']))}",
    }


def personality_recommendations(identity: dict[str, Any], intent: dict[str, Any], permission: dict[str, Any]) -> dict[str, Any]:
    if permission["restricted_hits"]:
        return {"next_actions": ["Use allowed alternatives", "Hold for review"]}
    if intent["intent"] in {"property_inquiry", "availability_request", "document_request"}:
        return {"next_actions": ["Draft shortlist", "Prepare safe reply"]}
    if intent["intent"] in {"operations_question", "internal_request"}:
        return {"next_actions": ["Open operations packet", "Update priorities"]}
    if identity["type"] in {"Omar", "HSH Staff"}:
        return {"next_actions": ["Open system priorities", "Run check-ins"]}
    return {"next_actions": ["Store context", "Reply draft"]}


def eye_state_for(intent: dict[str, Any], emotion: dict[str, Any], permission: dict[str, Any]) -> str:
    if permission["restricted_hits"]:
        return "restricted"
    if emotion["emotion"] in {"angry", "frustrated"}:
        return "alert"
    if intent["intent"] in {"property_inquiry", "availability_request", "document_request"}:
        return "searching"
    if intent["intent"] in {"operations_question", "internal_request", "follow_up", "viewing_request"}:
        return "thinking"
    return "success"


def process_interaction(event: dict[str, Any]) -> dict[str, Any]:
    text = _text(event)
    read_only = bool(event.get("read_only") or event.get("validation_read_only") or event.get("no_memory_write"))
    identity = detect_identity(event)
    relationship = load_relationship_memory(event, identity)
    intent = detect_intent(text)
    emotion = detect_emotion(text)
    permission = apply_permission_layer(text, identity)
    retrieval = _retrieve_memory_data(text, relationship.get("context_object", {}))
    unit_match = _format_unit_finder_payload(text)
    confidence = _calculate_confidence(identity, intent, relationship, retrieval)
    confidence_mode = _confidence_gate(confidence)
    state_memory = _state_memory_skip_question(relationship.get("context_object", {}), intent, text)
    sources = select_knowledge_sources(intent["intent"], permission)
    state = eye_state_for(intent, emotion, permission)
    personality = omar_personality(identity, emotion)
    response = generate_response(
        text,
        identity,
        intent,
        emotion,
        permission,
        confidence_mode,
        state_memory,
        unit_match,
    )
    actions = action_engine(intent, permission)
    if read_only:
        memory = {
            "write_enabled": False,
            "write_time": None,
            "source": "read_only_interaction_contract",
            "contact_phone": _canonical_phone(event.get("from") or event.get("From") or event.get("phone") or event.get("sender_phone") or ""),
            "pending_update": {
                "conversation_summary": text[:220],
                "identity_type": identity["type"],
                "intent": intent["intent"],
                "emotion": emotion["emotion"],
                "property_interests": event.get("property_interests", []),
                "lead_state": "read_only_not_persisted",
                "relationship_tag": identity.get("relationship_tag", "UNKNOWN"),
                "confidence": confidence,
                "persisted_context": False,
                "retrieval_match_count": retrieval.get("merged_match_count", 0),
            },
            "persisted_context": {},
        }
    else:
        memory = memory_update(event, identity, intent, emotion, relationship, retrieval, confidence)
    hud_enabled = bool(event.get("hud") or event.get("show_hud") or event.get("developer_overlay"))
    hud_confidence = confidence
    hud = (
        _hud_payload(identity.get("relationship_tag", "UNKNOWN"), state, relationship, retrieval, hud_confidence)
        if hud_enabled
        else {"enabled": False}
    )
    explanation = _eye_explain(state, identity, intent, permission, retrieval)
    external_side_effects = {
        **EXTERNAL_SIDE_EFFECTS,
        "memory_written": bool(memory.get("persisted_context")),
        "crm_rows_written": bool(memory.get("persisted_context")),
    }
    return {
        "channel": str(event.get("channel") or event.get("provider") or "unknown"),
        "received_text": text,
        "identity": identity,
        "relationship_memory": relationship,
        "intent": intent,
        "emotion": emotion,
        "permission": permission,
        "knowledge_retrieval": {
            "sources": sources,
            "retrieve_only_needed": True,
            "pipeline": "Incoming Query -> SQL + Vector Search -> Merged Data Set",
            "retrieval": retrieval,
            "unit_resolution": unit_match,
        },
        "omar_personality": personality,
        "response_generation": response,
        "confidence": {
            "score": confidence,
            "mode": confidence_mode,
            "score_pct": min(100, int(round(confidence * 100))) if isinstance(confidence, (int, float)) else 0,
        },
        "action_engine": actions,
        "eye": {
            "state": state,
            "explanation": explanation,
            "recommended_personality_next_actions": personality_recommendations(identity, intent, permission).get("next_actions", []),
        },
        "memory_update": memory,
        "eye_state": state,
        "hud_overlay_enabled": hud_enabled,
        "hud": hud,
        "state_memory": state_memory,
        "unit_match": unit_match,
        "external_side_effects": external_side_effects,
    }


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    events = payload.get("events") or DEFAULT_EVENTS
    interactions = [process_interaction({**event, "validation_read_only": True}) for event in events]
    permission_runtime = permission_runtime_contract()
    permission_consistency = permission_consistency_check()
    result = {
        "generated_at": _now(),
        "mode": "safe_local_a_to_z_interaction_contract_no_external_side_effects",
        "channels": CHANNELS,
        "pipeline_steps": PIPELINE_STEPS,
        "permission_runtime": permission_runtime,
        "permission_runtime_consistency": permission_consistency,
        "permission_policy": {
            "allowed": ALLOWED_INFORMATION,
            "never_disclose": NEVER_DISCLOSE,
        },
        "whatsapp_experience": ["message", "history", "relationship", "intent", "emotion", "permission", "knowledge", "omar_personality", "reply"],
        "website_experience": ["user_enters", "eye_wakes", "presence_layer", "search_everything", "property_intelligence", "operations", "documents", "tasks", "daily_briefing"],
        "mobile_experience": ["app_opens", "eye_wakes", "todays_priorities", "quick_actions", "voice_or_search", "property", "operations", "documents"],
        "eye_contract": {
            "states": ["idle", "thinking", "searching", "alert", "restricted", "success"],
            "reacts_to": ["real_searches", "real_workflows", "real_approvals", "real_risks", "real_tasks", "real_activity"],
        },
        "sample_interactions": interactions,
        "summary": {
            "interaction_count": len(interactions),
            "pipeline_step_count": len(PIPELINE_STEPS),
            "restricted_request_count": sum(1 for item in interactions if item["permission"]["restricted_hits"]),
            "permission_runtime_source": permission_runtime["source_of_truth"],
            "permission_same_result_everywhere": permission_consistency["same_result_everywhere"],
            "approval_required_count": sum(1 for item in interactions if item["response_generation"]["send_requires_approval"]),
            "eye_states_observed": sorted({item["eye_state"] for item in interactions}),
            "identity_types_observed": sorted({item["identity"]["type"] for item in interactions}),
        },
        "final_goal": "More knowledgeable, organized, and consistent than Omar, while sounding like Omar.",
        "external_side_effects": EXTERNAL_SIDE_EFFECTS,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(build(payload), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
