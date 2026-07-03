#!/usr/bin/env python3
import base64
import hmac
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import random
import uuid
import string
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Lock, Thread, Event
from dataclasses import asdict
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


AIOS_PROJECT_DIR = Path(os.getenv("AIOS_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))).resolve()


def _load_config_env():
    """Load simple KEY=VALUE runtime config without overwriting existing env vars."""
    if os.getenv("AIOS_SKIP_CONFIG_ENV", "").strip().lower() in {"1", "true", "yes", "on"}:
        return []
    candidate_paths = [
        os.getenv("AIOS_CONFIG_ENV", "").strip(),
        str(AIOS_PROJECT_DIR / "config.env"),
        str(AIOS_PROJECT_DIR / "transport" / "config.env"),
    ]
    loaded = []
    for raw_path in candidate_paths:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if not path.exists() or not path.is_file():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            loaded.append(str(path))
        except Exception as exc:
            print(json.dumps({"event": "config_env_load_failed", "path": str(path), "error": str(exc)}), flush=True)
    return loaded


LOADED_CONFIG_ENV_FILES = _load_config_env()


def _resolve_data_dir():
    configured = os.getenv("AIOS_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    project_data_dir = (AIOS_PROJECT_DIR / "data").resolve()
    container_data_dir = Path("/app/data")
    if str(AIOS_PROJECT_DIR).startswith("/app") and container_data_dir.exists():
        return container_data_dir.resolve()
    return project_data_dir


DATA_DIR = _resolve_data_dir()
PERSONALITY_DIR = os.getenv("AIOS_PERSONALITY_DIR", str(AIOS_PROJECT_DIR / "PersonalityEngine"))
KNOWLEDGE_BASE_DIR = os.getenv("AIOS_KNOWLEDGE_BASE_DIR", str(AIOS_PROJECT_DIR / "KnowledgeBase"))
POLICY_DIR = os.getenv("AIOS_POLICY_DIR", str(AIOS_PROJECT_DIR / "automation" / "whatsapp_provider_gateway" / "runtime"))
for module_path in (PERSONALITY_DIR, KNOWLEDGE_BASE_DIR, POLICY_DIR):
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

from omar_personality_engine import build_personality_context, detect_conversation_objective, detect_intent, detect_language, detect_social_context, special_contact_profile
from property_recommendation_agent import PropertyRecommendationAgent, inferred_price, parse_raw_json, norm
from aios_brain_router import classify_retrieval_intent
from aios_response_policy_layer import evaluate_response_policy
from hybrid_retriever import HybridRetriever
from human_identity_engine import (
    build_human_identity_context,
    build_human_identity_feedback,
    identity_context_to_contract,
)


HOST = "127.0.0.1"
PORT = int(os.environ.get("WA_SIMPLE_GATEWAY_PORT", "9010"))
OPENAI_ENDPOINT = os.environ.get(
    "WA_SIMPLE_OPENAI_ENDPOINT",
    "https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4",
)
AREA_FACT_SHEET_PATH = os.path.join(str(AIOS_PROJECT_DIR), "knowledge_base", "areas.json")
AREA_FACT_SHEET_ALT_PATHS = [
    os.path.join(str(KNOWLEDGE_BASE_DIR), "area_data.json"),
    os.path.join(str(KNOWLEDGE_BASE_DIR), "areas.json"),
    os.path.join(str(AIOS_PROJECT_DIR), "knowledge_base", "areas.json"),
    os.path.join(str(AIOS_PROJECT_DIR), "KnowledgeBase", "area_data.json"),
    os.path.join(str(AIOS_PROJECT_DIR), "KnowledgeBase", "areas.json"),
]
WASENDER_SEND_URL = "https://www.wasenderapi.com/api/send-message"
WASENDER_API_KEY = os.environ.get("WASENDER_API_KEY", "") or os.environ.get("AIOS_WASENDER_API_KEY", "")
WASENDER_SECRET_SERVICE = os.environ.get("WASENDER_SECRET_SERVICE", "AIOS Wasender API Key")
PSYCH_PROFILE_ENDPOINT = os.environ.get(
    "WA_SIMPLE_PSYCH_PROFILE_ENDPOINT",
    OPENAI_ENDPOINT,
)
PSYCH_PROFILE_NODE = os.environ.get("WA_SIMPLE_PSYCH_PROFILE_NODE", "transport/wa_simple_psych_profile_node.py")
try:
    from wa_simple_psych_profile_node import analyze_psych_profile_local, validate_psych_payload as _validate_psych_payload_node
except Exception:
    analyze_psych_profile_local = None
    _validate_psych_payload_node = None
WASENDER_TYPING_URL = os.environ.get("WASENDER_TYPING_URL", "https://www.wasenderapi.com/api/send-typing")
RESTRICTED_OUTBOUND_FALLBACK = "Got it, let me see."
REFLECTIVE_GATEWAY_DELAY_SECONDS = float(os.environ.get("WA_SIMPLE_REFLECTIVE_DELAY_SECONDS", "3"))
BUSY_REPLIES = ("One second", "Checking", "Got it, let me see.")
HUMAN_BRIDGE_REPLIES_AR = (
    "معك حق، كنت حاسس إني صار معي AI شوي. خلّيني أرجع للطريقة الطبيعية — كيفك؟",
    "أيوه صحيح، صراحة انحرفت شوي. خلّيني أرتّبها أبسط: شو الموضوع؟",
)
HUMAN_BRIDGE_REPLIES_EN = (
    "You’re right, that was sounding robotic. Let me fix it. What’s up?",
    "You’re right — I sounded off. I’ll keep it simple. What do you want to do next?",
)
NO_MATCH_REPLY = "I don’t see a verified matching record in the current inventory."
NO_MATCH_BRIDGE_REPLIES = (NO_MATCH_REPLY,)
TEST_TEXT_BLOCKLIST = (
    "AIOS delivery proof",
    "delivery proof test",
    "controlled test",
    "no action needed",
    "validation test",
    "readiness test",
    "proof test",
    "test message",
)
GENERIC_FALLBACK_BLOCKLIST = (
    "verified rental source is connected",
    "i don’t see a confirmed live option yet",
    "i don't see a confirmed live option yet",
    "i’ll confirm before sending",
    "i'll confirm before sending",
    "noted",
    "hello.",
    "source is connected",
)
CONTROLLED_AUTOPILOT_DECISIONS = {
    "SEND_NOW",
    "DRAFT_FOR_OMAR",
    "DO_NOT_SEND",
    "ASK_ONE_CLARIFYING_QUESTION",
    "ESCALATE_TO_OMAR",
}
PSYCHO_ENDPOINT_TIMEOUT = int(os.environ.get("WA_SIMPLE_PSYCH_PROFILE_TIMEOUT", "6"))
LOG_PATH = os.path.join(str(DATA_DIR), "transport", "simple_whatsapp_gateway.log.jsonl")
CHAT_DB_PATH = os.environ.get(
    "WA_SIMPLE_WHATSAPP_CHAT_DB_PATH",
    str(DATA_DIR / "WhatsAppChatStorage" / "ChatStorage.sqlite"),
)
PROPERTY_DB_PATH = os.environ.get(
    "WA_SIMPLE_PROPERTY_DB_PATH",
    str(Path(KNOWLEDGE_BASE_DIR) / "Property_Master_Database.sqlite"),
)
KNOWLEDGE_SEARCH_ROOTS = [
    os.path.join(KNOWLEDGE_BASE_DIR, "AIOS_Knowledge_Vault"),
    os.path.join(KNOWLEDGE_BASE_DIR, "Operations_Corpus", "text"),
    KNOWLEDGE_BASE_DIR,
]
RELATIONSHIP_ASSIGNMENT_STRATEGY = os.getenv("AIOS_RELATIONSHIP_ASSIGNMENT_STRATEGY", "manual_then_contextual").strip().lower()
ALLOW_UNKNOWN_WHATSAPP_REPLY = os.getenv("AIOS_ALLOW_UNKNOWN_WHATSAPP_REPLY", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
STRESS_RELATIONSHIP_OVERRIDE_RAW = os.getenv("AIOS_STRESS_RELATIONSHIP_TAG_MAP", "").strip()
RELATIONSHIP_STORE_PATH = os.path.join(str(DATA_DIR), "transport", "whatsapp_relationship_store.json")
RUNTIME_STATE_DB_PATH = os.path.join(str(DATA_DIR), "transport", "aios_runtime_state.sqlite")
DEDUP_WINDOW_SECONDS = 120
WORKER_QUEUE_MAXSIZE = int(os.environ.get("WA_SIMPLE_WORKER_QUEUE_MAXSIZE", "512"))
WORKER_POLL_SECONDS = float(os.environ.get("WA_SIMPLE_WORKER_POLL_SECONDS", "0.4"))
WORKER_QUEUE_TIMEOUT_SECONDS = float(os.environ.get("WA_SIMPLE_WORKER_QUEUE_TIMEOUT_SECONDS", "0.2"))
DISCOVERY_STALE_SECONDS = int(os.environ.get("AIOS_DISCOVERY_STALE_SECONDS", str(48 * 60 * 60)))
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("AIOS_DISCOVERY_CLEANUP_INTERVAL_SECONDS", str(5 * 60)))
PROMISE_SCAN_SECONDS = int(os.environ.get("AIOS_PROMISE_SCAN_SECONDS", "900"))
AUTOPILOT_DEFAULT_MODE = os.environ.get("AIOS_WHATSAPP_AUTOPILOT_MODE", "CONTROLLED").strip().upper()
AIOS_WHATSAPP_TEST_SENDERS = {
    item.strip()
    for item in os.environ.get("AIOS_WHATSAPP_TEST_SENDERS", "").split(",")
    if item.strip()
}
WEBHOOK_SECRET = os.getenv("AIOS_WEBHOOK_SECRET", "").strip()
ADMIN_SECRET = os.getenv("AIOS_ADMIN_SECRET", "").strip()
ADMIN_AUTH_USER = os.getenv("AIOS_BASIC_AUTH_USER", "").strip()
ADMIN_AUTH_PASSWORD = os.getenv("AIOS_BASIC_AUTH_PASSWORD", "").strip()
MAX_BODY_BYTES = int(os.getenv("AIOS_MAX_BODY_BYTES", "1048576"))
AIRTABLE_API_TOKEN = (
    os.environ.get("AIRTABLE_PAT", "")
    or os.environ.get("AIRTABLE_API_KEY", "")
    or os.environ.get("AIRTABLE_TOKEN", "")
    or os.environ.get("AIOS_AIRTABLE_API_KEY", "")
    or os.environ.get("AIOS_AIRTABLE_TOKEN", "")
)
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appnZ7RYBCt9wKgAT")
AIRTABLE_CONTACTS_TABLE_ID = os.environ.get("AIRTABLE_CONTACTS_TABLE", "tbl14JssgGXbigw7J")
AIRTABLE_LEADS_TABLE_ID = os.environ.get("AIRTABLE_LEADS_TABLE", "tbliAGMkhIydmPEak")
AIRTABLE_COMMS_TABLE_ID = os.environ.get("AIRTABLE_COMMS_TABLE", "tblnYS0Ogdh1G04JT")
AIRTABLE_API_BASE_URL = "https://api.airtable.com/v0"
AIRTABLE_REPLAY_INTERVAL_SECONDS = int(os.environ.get("AIOS_AIRTABLE_REPLAY_INTERVAL_SECONDS", "60"))
AIRTABLE_REPLAY_BATCH_SIZE = int(os.environ.get("AIOS_AIRTABLE_REPLAY_BATCH_SIZE", "25"))
HISTORY_LIMIT = 8
DB_HISTORY_LIMIT = 30
STATE_HISTORY_LIMIT = 30
DB_SUBJECT_SCAN_LIMIT = 60
PSYCHO_STATE_TIMEOUT_SECONDS = 40
DUPLICATE_TEXT_COOLDOWN_SECONDS = int(os.environ.get("WA_SIMPLE_TYPING_COOLDOWN_SECONDS", "2"))
RECENT_INBOUND = {}
CONVERSATION_HISTORY = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
RELATIONSHIP_STORE = {}
RELATIONSHIP_STORE_LOCK = Lock()
WORKER_QUEUE = Queue(maxsize=WORKER_QUEUE_MAXSIZE)
WORKER_STOP_EVENT = Event()
AIRTABLE_REPLAY_STOP_EVENT = Event()
LAST_DISCOVERY_CLEANUP_TS = 0.0
LAST_PROMISE_SCAN_TS = 0.0
WORKER_THREAD = None
AIRTABLE_REPLAY_THREAD = None
WORKER_STATS = {
    "started_at": 0,
    "processed": 0,
    "errors": 0,
    "queued": 0,
    "duplicate_suppressed": 0,
    "queue_full": 0,
}
AREA_FACT_SHEET = None
FACT_CLEANUP_REASONS = [
    "registry file",
    "internal loop",
    "escalation submitted",
    "verification in progress",
    "will revert",
    "i will check",
    "i will verify",
    "i will update",
    "i am escalating",
    "i'll escalate",
    "would you like me to",
    "human specialist",
    "support ticket",
]
RELATIONSHIP_PRIORITY = {
    "Unknown": 0,
    "New Client": 1,
    "Client": 2,
    "Existing Client": 2,
    "Friend": 3,
    "Agent": 4,
    "Staff": 5,
    "Omar": 6,
    "Trusted Partner": 6,
    "TRUSTED_PARTNER": 6,
}
RELATIONSHIP_TAGS = {
    "CLIENT",
    "AGENT",
    "STAFF",
    "FRIEND",
    "FAMILY",
    "TRUSTED_PARTNER",
    "UNKNOWN",
}

BUSINESS_RELEVANCE_RELATIONSHIPS = {"CLIENT", "AGENT", "STAFF", "FRIEND", "FAMILY"}
BUSINESS_RELEVANCE_KEYWORDS = {
    "investment",
    "roi",
    "unit",
    "price",
    "jvc",
    "dubai",
    "apartment",
    "villa",
    "rent",
    "sale",
    "buy",
    "sell",
    "lease",
    "commercial",
    "office",
    "warehouse",
    "plot",
    "sqm",
    "sqft",
    "bedroom",
    "studio",
    "handover",
    "developer",
    "dld",
    "rera",
    "noc",
    "mou",
    "transfer",
    "title deed",
    "valuation",
    "mortgage",
    "availability",
    "payment plan",
}
NON_BUSINESS_NOISE_KEYWORDS = {
    "delivery",
    "popeyes",
    "washing",
    "driver",
    "food",
    "talabat",
    "noon",
    "amazon",
    "courier",
}
PURE_ACK_MESSAGES = {"ok", "okay", "k", "thanks", "thank you", "thx", "👍"}
CASUAL_ONLY_KEYWORDS = {
    "lol",
    "haha",
    "😂",
    "😅",
    "😄",
    "bro",
    "buddy",
    "yoo",
    "yooo",
    "what's up",
    "whats up",
}
UNKNOWN_REPLY_TRIGGERS = {
    "hi",
    "hello",
    "hey",
    "hallo",
    "yoo",
    "yooo",
    "good morning",
    "good evening",
    "good night",
    "مرحبا",
    "السلام عليكم",
    "هلا",
    "هلو",
    "كيفك",
}
MIN_KNOWN_BUSINESS_WORDS = int(os.environ.get("AIOS_MIN_KNOWN_BUSINESS_WORDS", "5"))

CANONICAL_RELATIONSHIP_MAP = {
    "Client": "CLIENT",
    "New Client": "CLIENT",
    "Existing Client": "CLIENT",
    "Client / Buyer": "CLIENT",
    "Agent": "AGENT",
    "Staff": "STAFF",
    "Friend": "FRIEND",
    "Family": "FAMILY",
    "Omar": "UNKNOWN",
    "Trusted Partner": "TRUSTED_PARTNER",
    "New Friend": "FRIEND",
    "New": "UNKNOWN",
    "Unknown": "UNKNOWN",
}
AIOS_STRESS_RELATIONSHIP_TAG_MAP = {}


def _parse_relationship_override_map(raw):
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    normalized = {}
    for key, value in parsed.items():
        sender = re.sub(r"\D+", "", str(key))
        if not sender:
            continue
        tag_candidate = str(value).strip().upper().replace("-", " ")
        tag = CANONICAL_RELATIONSHIP_MAP.get(tag_candidate)
        if tag not in RELATIONSHIP_TAGS:
            mapped = CANONICAL_RELATIONSHIP_MAP.get(tag_candidate, None)
            if mapped in RELATIONSHIP_TAGS:
                tag = mapped
        if tag not in RELATIONSHIP_TAGS:
            if tag_candidate in RELATIONSHIP_TAGS:
                tag = tag_candidate
            else:
                continue
        normalized[sender] = tag
    return normalized


AIOS_STRESS_RELATIONSHIP_TAG_MAP = _parse_relationship_override_map(STRESS_RELATIONSHIP_OVERRIDE_RAW)
MANUAL_CONTACT_ALIASES = {
    "971542227333": {
        "relationship": "Trusted Partner",
        "known_contact_name": "Trusted Partner Permanent",
        "desktop_chat_name": "Trusted Partner Permanent",
        "known_chat": True,
        "notes": "Governance-trusted WhatsApp access. Relationship routing only; no permission/privacy bypass.",
    },
    "971545112616": {
        "relationship": "Trusted Partner",
        "known_contact_name": "Trusted Partner Temporary",
        "desktop_chat_name": "Trusted Partner Temporary",
        "known_chat": True,
        "notes": "Temporary trusted WhatsApp access valid through 2026-06-24 23:59:59 +04:00. Relationship routing only; no permission/privacy bypass.",
    },
    "971501900771": {
        "relationship": "Friend",
        "known_contact_name": "Hassan Kazzabel",
        "desktop_chat_name": "Hassan Kazabr Brother",
        "known_chat": True,
        "notes": "Executive / Inner Circle interaction style. Personality profile only; no permission/privacy bypass.",
    },
    "33644655014": {
        "relationship": "Staff",
        "known_contact_name": "Vetn",
        "desktop_chat_name": "Vetn Stuff",
        "known_chat": True,
        "notes": "Trusted internal contact interaction style. Personality profile only; privacy restrictions still apply.",
    },
    "971506794299": {
        "relationship": "Existing Client",
        "known_contact_name": "H M Hasaan Noc Palm",
        "desktop_chat_name": "H M Hasaan Noc Palm",
        "known_chat": True,
        "jid_aliases": ["14869344551137@lid"],
        "notes": "Old NOC/Palm/Nakheel chat. Load previous subject before reply.",
        "old_chat_subject_summary": "Nakheel/Palm portal or NOC case; portal/account access; urgent follow-up",
        "history_seed": "user: Nakheel Account Access\nassistant: On it now.\nuser: ضروري",
    }
}


def now_ms():
    return int(time.time() * 1000)


def _phone_last4(value):
    digits = re.sub(r"\D+", "", str(value or "").split("@", 1)[0])
    return digits[-4:] if digits else ""


def _sanitize_for_log(key, value):
    key_l = str(key or "").lower()
    if key_l in {"sender", "from", "from_phone", "to", "phone", "whatsapp_id", "contact_id", "original_target", "provider_target", "fallback_target"}:
        return {"phone_last4": _phone_last4(value)} if _phone_last4(value) else ""
    if key_l in {"text", "message", "body", "raw", "reply", "history", "original_reply", "rewritten_reply", "final_reply", "inbound_text", "source_message"}:
        return "[redacted]"
    if "traceback" in key_l:
        return "[redacted]"
    if isinstance(value, dict):
        sanitized = {}
        for child_key, child_value in value.items():
            child_key_l = str(child_key).lower()
            if child_key_l in {"message_id", "id", "event", "type", "ignored", "ignored_reason", "relationship_tag", "relationship_tag_source", "intent", "decision", "reason", "source"}:
                sanitized[child_key] = child_value
            elif child_key_l in {"sender", "from", "from_phone", "to", "phone", "chatid", "remotejid", "reply_target"}:
                sanitized[child_key] = {"phone_last4": _phone_last4(child_value)} if _phone_last4(child_value) else ""
            elif child_key_l in {"text", "message", "body", "raw", "messagebody", "conversation", "history", "reply", "final_reply", "payload", "parsed"}:
                sanitized[child_key] = "[redacted]"
            else:
                sanitized[child_key] = _sanitize_for_log(child_key, child_value)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_log(key, item) for item in value[:20]]
    if isinstance(value, str) and re.search(r"\+?\d[\d\s().@-]{7,}", value):
        return re.sub(r"\+?\d[\d\s().@-]{7,}", lambda m: f"***{_phone_last4(m.group(0))}", value)
    return value


def log_event(event, **fields):
    record = {"ts": now_ms(), "event": event, **{k: _sanitize_for_log(k, v) for k, v in fields.items()}}
    _ensure_parent_dir(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _airtable_queue_event(direction, sender, payload):
    init_runtime_state_db()
    try:
        con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
        con.execute(
            """
            INSERT INTO AIOS_AirtableWritebackQueue
                (created_ts, updated_ts, direction, sender, payload_json, status, last_error, attempts)
            VALUES (?, ?, ?, ?, ?, 'pending', '', 0)
            """,
            (
                _now_epoch(),
                _now_epoch(),
                str(direction or ""),
                normalize_phone(sender),
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        con.commit()
        queued_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.close()
        log_event("airtable_crm_writeback_queued", direction=direction, sender=normalize_phone(sender), queue_id=queued_id)
        return queued_id
    except Exception as exc:
        log_event("airtable_crm_writeback_queue_failed", direction=direction, sender=normalize_phone(sender), error=str(exc))
        return None


def airtable_queue_stats():
    init_runtime_state_db()
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    rows = con.execute(
        "SELECT status, COUNT(*) FROM AIOS_AirtableWritebackQueue GROUP BY status"
    ).fetchall()
    con.close()
    return {str(status): int(count) for status, count in rows}


def airtable_is_configured():
    return bool(AIRTABLE_API_TOKEN and AIRTABLE_BASE_ID)


def _airtable_headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _airtable_request(method, table_id, record_id="", payload=None, query=None):
    if not airtable_is_configured():
        raise RuntimeError("airtable_not_configured")
    path = f"{AIRTABLE_API_BASE_URL}/{AIRTABLE_BASE_ID}/{table_id}"
    if record_id:
        path = f"{path}/{record_id}"
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(path, data=data, headers=_airtable_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw[:800]}
        raise RuntimeError(f"airtable_http_{exc.code}:{parsed}") from exc


def _airtable_find_contact_by_phone(phone):
    phone = str(phone or "").strip()
    if not phone:
        return None
    formula = "{Phone} = '%s'" % phone.replace("'", "\\'")
    status, data = _airtable_request(
        "GET",
        AIRTABLE_CONTACTS_TABLE_ID,
        query={"filterByFormula": formula, "maxRecords": 1, "returnFieldsByFieldId": "true"},
    )
    records = data.get("records", []) if isinstance(data, dict) else []
    return records[0] if records else None


def _airtable_find_lead_by_ref(source_ref):
    source_ref = str(source_ref or "").strip()
    if not source_ref:
        return None
    formula = "{Source ref} = '%s'" % source_ref.replace("'", "\\'")
    status, data = _airtable_request(
        "GET",
        AIRTABLE_LEADS_TABLE_ID,
        query={"filterByFormula": formula, "maxRecords": 1, "returnFieldsByFieldId": "true"},
    )
    records = data.get("records", []) if isinstance(data, dict) else []
    return records[0] if records else None


def _airtable_contact_type_for_relationship(relationship_tag):
    tag = str(relationship_tag or "").upper()
    if tag in {"CLIENT", "UNKNOWN"}:
        return "Buyer"
    if tag == "AGENT":
        return "Vendor"
    if tag in {"STAFF", "FRIEND", "FAMILY", "TRUSTED_PARTNER"}:
        return "Other"
    return "Other"


def _airtable_lead_intent(intent):
    normalized_intent = str(intent or "").lower()
    if "rent" in normalized_intent:
        return "Rent"
    if "sell" in normalized_intent or "list" in normalized_intent:
        return "List"
    if "invest" in normalized_intent or "buy" in normalized_intent or "property" in normalized_intent:
        return "Buy"
    return "Invest"


def _airtable_property_type(text, intent=""):
    combined = f"{text or ''} {intent or ''}".lower()
    if "villa" in combined:
        return "Villa"
    if "townhouse" in combined:
        return "Townhouse"
    if "plot" in combined or "land" in combined:
        return "Plot"
    if "commercial" in combined or "office" in combined or "retail" in combined:
        return "Commercial"
    if "off-plan" in combined or "off plan" in combined:
        return "Off-plan"
    return "Apartment"


def _airtable_area_from_text(text, live_context=None):
    live_context = live_context or {}
    proof = live_context.get("retrieval_proof", {}) if isinstance(live_context, dict) else {}
    query = f"{text or ''} {proof.get('query_used', '')}".lower()
    known_areas = [
        ("JVC", "JVC"),
        ("jumeirah village circle", "JVC"),
        ("yas island", "Yas Island"),
        ("saadiyat", "Saadiyat Island"),
        ("dubai hills", "Dubai Hills"),
        ("downtown", "Downtown"),
        ("business bay", "Business Bay"),
        ("marina", "Dubai Marina"),
        ("al reem", "Al Reem Island"),
        ("al raha", "Al Raha"),
    ]
    for needle, area in known_areas:
        if needle in query:
            return area
    return ""


def _airtable_budget_from_text(text):
    text = str(text or "").lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(m|million)\b", text)
    if match:
        return float(match.group(1)) * 1_000_000
    match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", text)
    if match:
        return float(match.group(1)) * 1_000
    match = re.search(r"\b(\d{5,9})\b", text)
    if match:
        return float(match.group(1))
    return None


def _airtable_contact_payload(sender, relationship_tag, relationship, summary):
    phone = sender if str(sender or "").startswith("+") else f"+{normalize_phone(sender)}"
    return {
        "fldoA7s9UsknhzSJp": f"WhatsApp {phone}",
        "fldhxSwH2jyLvMXCY": phone,
        "fldm5ZVSQEoOXcTKn": _airtable_contact_type_for_relationship(relationship_tag),
        "fld1x2XoRFfJz12s1": "English",
        "fldjzptC5O1MOg9yk": "WhatsApp",
        "fld1jfRHFzLLvcNa8": True,
        "fld0EXHnxEqn9elT2": summary[:10000],
    }


def airtable_upsert_contact(sender, relationship_tag, relationship, summary):
    existing = _airtable_find_contact_by_phone(sender if str(sender or "").startswith("+") else f"+{normalize_phone(sender)}")
    fields = _airtable_contact_payload(sender, relationship_tag, relationship, summary)
    if existing:
        record_id = existing["id"]
        _airtable_request(
            "PATCH",
            AIRTABLE_CONTACTS_TABLE_ID,
            payload={"records": [{"id": record_id, "fields": fields}], "typecast": True},
        )
        return record_id, "updated"
    status, data = _airtable_request(
        "POST",
        AIRTABLE_CONTACTS_TABLE_ID,
        payload={"records": [{"fields": fields}], "typecast": True},
    )
    record = data.get("records", [{}])[0]
    return record.get("id", ""), "created"


def airtable_upsert_lead(contact_id, message_id, inbound_text, intent, decision, final_reply, live_context=None):
    source_ref = str(message_id or f"wa-{normalize_phone(contact_id)}-{int(time.time())}")[:120]
    budget = _airtable_budget_from_text(inbound_text)
    fields = {
        "fldSsZZPYV8q2OlRr": f"WhatsApp - {str(inbound_text or 'Conversation')[:80]}",
        "fldbCPMCjgHOVogua": "WhatsApp",
        "fldSIuL22DjuxiiRX": source_ref,
        "fldkq5XJdQjQ9W84v": _airtable_lead_intent(intent),
        "fldtS7Nog53hAiakC": _airtable_property_type(inbound_text, intent),
        "fldA61AyGkHZEc9S3": _airtable_area_from_text(inbound_text, live_context),
        "fldvWwrmxIsrfCUtN": "Contacted" if decision in {"SEND_NOW", "DRAFT_FOR_OMAR"} else "New",
        "fldqZlNoPSKcUaJuD": "Warm",
        "fldJ19U9cshxSkiPX": "Review AIOS WhatsApp conversation and send shortlist" if decision != "SEND_NOW" else "Continue WhatsApp follow-up",
        "fldvNWWs8LMXT5QWj": str(final_reply or "")[:10000],
        "fldo74pMpz8ZKMxND": f"AI decision={decision}; message_id={message_id}; conversation summary={str(inbound_text or '')[:500]}",
        "fldzykdJFGToo8JNn": [contact_id],
    }
    if budget is not None:
        fields["fldXB60ojzFE0HbD0"] = budget
    existing = _airtable_find_lead_by_ref(source_ref)
    if existing:
        record_id = existing["id"]
        _airtable_request(
            "PATCH",
            AIRTABLE_LEADS_TABLE_ID,
            payload={"records": [{"id": record_id, "fields": fields}], "typecast": True},
        )
        return record_id, "updated"
    status, data = _airtable_request(
        "POST",
        AIRTABLE_LEADS_TABLE_ID,
        payload={"records": [{"fields": fields}], "typecast": True},
    )
    record = data.get("records", [{}])[0]
    return record.get("id", ""), "created"


def airtable_create_comms(contact_id, direction, body, message_id="", decision="", sent_at_ts=None):
    sent_at_ts = sent_at_ts or time.time()
    iso_time = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(sent_at_ts))
    summary_prefix = "Inbound" if direction == "In" else "Outbound"
    fields = {
        "fldmSYnyRfYYdlzWn": f"{summary_prefix} WhatsApp - {str(message_id or '')[:80]}",
        "fldMf5SI1fknARqvy": "WhatsApp",
        "fldTjqDQJsDOT5fTC": direction,
        "fld3IHM0iEQioFNR1": "Service",
        "fldFn3aRmkYm1NS8j": str(body or "")[:10000],
        "fldZEvMILMlPwWvQD": iso_time,
        "fldwfohrjfJ4lPe4k": "Auto",
        "fld0Fr38wHEv3M99J": [contact_id],
    }
    status, data = _airtable_request(
        "POST",
        AIRTABLE_COMMS_TABLE_ID,
        payload={"records": [{"fields": fields}], "typecast": True},
    )
    record = data.get("records", [{}])[0]
    return record.get("id", "")


def airtable_writeback_inbound(parsed, gate_reason="", decision="inbound_received"):
    sender = normalize_phone((parsed or {}).get("sender"))
    if not sender:
        return {"ok": False, "reason": "missing_sender"}
    relationship_tag = (parsed or {}).get("relationship_tag") or "UNKNOWN"
    relationship = (parsed or {}).get("relationship") or relationship_tag
    inbound_text = (parsed or {}).get("text", "")
    message_id = (parsed or {}).get("message_id") or ""
    summary = (
        f"WhatsApp inbound. Relationship={relationship}; Relationship tag={relationship_tag}; "
        f"Lead status=New; Last message={inbound_text[:500]}; AI decision={decision}; "
        f"Conversation summary=inbound received before response gate. Gate reason={gate_reason or 'none'}."
    )
    queue_payload = {
        "direction": "In",
        "sender": sender,
        "parsed": parsed or {},
        "gate_reason": gate_reason or "",
        "decision": decision or "",
        "summary": summary,
    }
    if not airtable_is_configured():
        queued_id = _airtable_queue_event("In", sender, queue_payload)
        log_event(
            "airtable_crm_writeback_skipped",
            direction="In",
            sender=sender,
            reason="airtable_not_configured",
            queued_id=queued_id,
        )
        return {"ok": False, "reason": "airtable_not_configured", "queued_id": queued_id}
    try:
        contact_id, contact_action = airtable_upsert_contact(sender, relationship_tag, relationship, summary)
        comms_id = airtable_create_comms(
            contact_id,
            "In",
            f"message_id={message_id} | Sender=+{sender} | Relationship={relationship} | Last message={inbound_text} | AI decision={decision} | Gate reason={gate_reason or 'none'}",
            message_id=message_id,
        )
        result = {"ok": True, "contact_id": contact_id, "contact_action": contact_action, "comms_id": comms_id}
        log_event("airtable_crm_writeback", direction="In", sender=sender, **result)
        return result
    except Exception as exc:
        queue_payload["error"] = str(exc)
        queued_id = _airtable_queue_event("In", sender, queue_payload)
        log_event("airtable_crm_writeback_failed", direction="In", sender=sender, error=str(exc), queued_id=queued_id)
        return {"ok": False, "reason": str(exc), "queued_id": queued_id}


def airtable_writeback_outbound(payload, decision_result, final_reply, sent=False, send_result=None, outcome_label="", live_context=None):
    sender = normalize_phone((payload or {}).get("sender"))
    if not sender:
        return {"ok": False, "reason": "missing_sender"}
    relationship_tag = (payload or {}).get("relationship_tag") or "UNKNOWN"
    relationship = (payload or {}).get("relationship") or relationship_tag
    inbound_text = (payload or {}).get("inbound_text") or ""
    message_id = (payload or {}).get("message_id") or ""
    decision = (decision_result or {}).get("decision") or ""
    reason_codes = (decision_result or {}).get("reason_codes", [])
    provider_msg_id = ""
    if isinstance(send_result, dict):
        data = send_result.get("data") if isinstance(send_result.get("data"), dict) else {}
        provider_msg_id = str(data.get("msgId") or send_result.get("msgId") or "")
    summary = (
        f"WhatsApp outbound. Relationship={relationship}; Relationship tag={relationship_tag}; "
        f"Lead status={'Contacted' if decision in {'SEND_NOW', 'DRAFT_FOR_OMAR'} else 'New'}; "
        f"Last inbound={inbound_text[:500]}; Last outbound={str(final_reply or '')[:500]}; "
        f"AI decision={decision}; Sent={bool(sent)}; Outcome={outcome_label}; "
        f"Conversation summary=AIOS generated outbound decision and CRM audit record."
    )
    queue_payload = {
        "direction": "Out",
        "sender": sender,
        "payload": payload or {},
        "decision_result": decision_result or {},
        "final_reply": final_reply or "",
        "sent": bool(sent),
        "send_result": send_result or {},
        "outcome_label": outcome_label or "",
        "summary": summary,
        "live_context": live_context or {},
    }
    if not airtable_is_configured():
        queued_id = _airtable_queue_event("Out", sender, queue_payload)
        log_event(
            "airtable_crm_writeback_skipped",
            direction="Out",
            sender=sender,
            reason="airtable_not_configured",
            decision=decision,
            queued_id=queued_id,
        )
        return {"ok": False, "reason": "airtable_not_configured", "queued_id": queued_id}
    try:
        contact_id, contact_action = airtable_upsert_contact(sender, relationship_tag, relationship, summary)
        lead_id, lead_action = airtable_upsert_lead(contact_id, message_id, inbound_text, (payload or {}).get("intent"), decision, final_reply, live_context)
        body = (
            f"message_id={message_id} | Sender=+{sender} | Relationship={relationship} | "
            f"Lead status={'Contacted' if decision in {'SEND_NOW', 'DRAFT_FOR_OMAR'} else 'New'} | "
            f"Last inbound={inbound_text} | Last outbound={final_reply} | AI decision={decision} | "
            f"Reason codes={reason_codes} | Sent={bool(sent)} | Provider msgId={provider_msg_id} | Outcome={outcome_label}"
        )
        comms_id = airtable_create_comms(contact_id, "Out", body, message_id=message_id, decision=decision)
        result = {
            "ok": True,
            "contact_id": contact_id,
            "contact_action": contact_action,
            "lead_id": lead_id,
            "lead_action": lead_action,
            "comms_id": comms_id,
        }
        log_event("airtable_crm_writeback", direction="Out", sender=sender, decision=decision, sent=bool(sent), **result)
        return result
    except Exception as exc:
        queue_payload["error"] = str(exc)
        queued_id = _airtable_queue_event("Out", sender, queue_payload)
        log_event("airtable_crm_writeback_failed", direction="Out", sender=sender, decision=decision, error=str(exc), queued_id=queued_id)
        return {"ok": False, "reason": str(exc), "queued_id": queued_id}


def _airtable_replay_queue_row(row_id, direction, sender, payload):
    direction = str(direction or "")
    sender = normalize_phone(sender)
    payload = payload or {}
    if direction == "In":
        parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}
        relationship_tag = parsed.get("relationship_tag") or "UNKNOWN"
        relationship = parsed.get("relationship") or relationship_tag
        inbound_text = parsed.get("text", "")
        message_id = parsed.get("message_id") or ""
        gate_reason = payload.get("gate_reason") or ""
        decision = payload.get("decision") or "inbound_received"
        summary = payload.get("summary") or (
            f"WhatsApp inbound replay. Relationship={relationship}; Relationship tag={relationship_tag}; "
            f"Lead status=New; Last message={str(inbound_text)[:500]}; AI decision={decision}; "
            f"Conversation summary=replayed from local Airtable queue. Gate reason={gate_reason or 'none'}."
        )
        contact_id, contact_action = airtable_upsert_contact(sender, relationship_tag, relationship, summary)
        comms_id = airtable_create_comms(
            contact_id,
            "In",
            f"message_id={message_id} | Sender=+{sender} | Relationship={relationship} | "
            f"Last message={inbound_text} | AI decision={decision} | Gate reason={gate_reason or 'none'} | "
            f"Replayed queue row={row_id}",
            message_id=message_id,
        )
        return {
            "ok": True,
            "direction": "In",
            "contact_id": contact_id,
            "contact_action": contact_action,
            "comms_id": comms_id,
        }
    if direction == "Out":
        outbound_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        decision_result = payload.get("decision_result") if isinstance(payload.get("decision_result"), dict) else {}
        final_reply = payload.get("final_reply") or ""
        live_context = payload.get("live_context") if isinstance(payload.get("live_context"), dict) else {}
        relationship_tag = outbound_payload.get("relationship_tag") or "UNKNOWN"
        relationship = outbound_payload.get("relationship") or relationship_tag
        inbound_text = outbound_payload.get("inbound_text") or ""
        message_id = outbound_payload.get("message_id") or ""
        decision = decision_result.get("decision") or ""
        reason_codes = decision_result.get("reason_codes", [])
        outcome_label = payload.get("outcome_label") or ""
        summary = payload.get("summary") or (
            f"WhatsApp outbound replay. Relationship={relationship}; Relationship tag={relationship_tag}; "
            f"Lead status={'Contacted' if decision in {'SEND_NOW', 'DRAFT_FOR_OMAR'} else 'New'}; "
            f"Last inbound={str(inbound_text)[:500]}; Last outbound={str(final_reply)[:500]}; "
            f"AI decision={decision}; Sent={bool(payload.get('sent'))}; Outcome={outcome_label}; "
            f"Conversation summary=replayed from local Airtable queue."
        )
        contact_id, contact_action = airtable_upsert_contact(sender, relationship_tag, relationship, summary)
        lead_id, lead_action = airtable_upsert_lead(
            contact_id,
            message_id,
            inbound_text,
            outbound_payload.get("intent"),
            decision,
            final_reply,
            live_context,
        )
        body = (
            f"message_id={message_id} | Sender=+{sender} | Relationship={relationship} | "
            f"Lead status={'Contacted' if decision in {'SEND_NOW', 'DRAFT_FOR_OMAR'} else 'New'} | "
            f"Last inbound={inbound_text} | Last outbound={final_reply} | AI decision={decision} | "
            f"Reason codes={reason_codes} | Sent={bool(payload.get('sent'))} | Outcome={outcome_label} | "
            f"Replayed queue row={row_id}"
        )
        comms_id = airtable_create_comms(contact_id, "Out", body, message_id=message_id, decision=decision)
        return {
            "ok": True,
            "direction": "Out",
            "contact_id": contact_id,
            "contact_action": contact_action,
            "lead_id": lead_id,
            "lead_action": lead_action,
            "comms_id": comms_id,
        }
    return {"ok": False, "reason": f"unsupported_direction:{direction}"}


def airtable_replay_writeback_queue(limit=25, statuses=None):
    init_runtime_state_db()
    if not airtable_is_configured():
        log_event("airtable_crm_writeback_replay_skipped", reason="airtable_not_configured")
        return {"ok": False, "reason": "airtable_not_configured", "processed": 0, "results": []}
    statuses = statuses or ("pending", "failed")
    placeholders = ",".join("?" for _ in statuses)
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        f"""
        SELECT id, direction, sender, payload_json, attempts
        FROM AIOS_AirtableWritebackQueue
        WHERE status IN ({placeholders})
        ORDER BY created_ts ASC
        LIMIT ?
        """,
        [*statuses, int(limit)],
    ).fetchall()
    results = []
    for row in rows:
        row_id = int(row["id"])
        try:
            payload = json.loads(row["payload_json"] or "{}")
            result = _airtable_replay_queue_row(row_id, row["direction"], row["sender"], payload)
            if result.get("ok"):
                payload["airtable_replay"] = {"status": "PASS", "replayed_at_ts": _now_epoch(), "result": result}
                con.execute(
                    """
                    UPDATE AIOS_AirtableWritebackQueue
                    SET updated_ts=?, payload_json=?, status='replayed', last_error='', attempts=attempts+1
                    WHERE id=?
                    """,
                    (_now_epoch(), json.dumps(payload, ensure_ascii=False), row_id),
                )
                log_event("airtable_crm_writeback_replayed", queue_id=row_id, sender=row["sender"], **result)
            else:
                con.execute(
                    """
                    UPDATE AIOS_AirtableWritebackQueue
                    SET updated_ts=?, status='failed', last_error=?, attempts=attempts+1
                    WHERE id=?
                    """,
                    (_now_epoch(), str(result.get("reason") or "unknown_replay_failure")[:1000], row_id),
                )
                log_event("airtable_crm_writeback_replay_failed", queue_id=row_id, sender=row["sender"], direction=row["direction"], result=result)
            results.append({"queue_id": row_id, **result})
        except Exception as exc:
            con.execute(
                """
                UPDATE AIOS_AirtableWritebackQueue
                SET updated_ts=?, status='failed', last_error=?, attempts=attempts+1
                WHERE id=?
                """,
                (_now_epoch(), str(exc)[:1000], row_id),
            )
            log_event("airtable_crm_writeback_replay_exception", queue_id=row_id, sender=row["sender"], direction=row["direction"], error=str(exc))
            results.append({"queue_id": row_id, "ok": False, "reason": str(exc)})
    con.commit()
    con.close()
    return {
        "ok": all(item.get("ok") for item in results) if results else True,
        "processed": len(results),
        "results": results,
    }


def _airtable_replay_worker_loop():
    log_event(
        "airtable_crm_writeback_replay_worker_start",
        configured=airtable_is_configured(),
        interval_seconds=AIRTABLE_REPLAY_INTERVAL_SECONDS,
        batch_size=AIRTABLE_REPLAY_BATCH_SIZE,
    )
    while not AIRTABLE_REPLAY_STOP_EVENT.wait(max(5, AIRTABLE_REPLAY_INTERVAL_SECONDS)):
        try:
            if not airtable_is_configured():
                continue
            result = airtable_replay_writeback_queue(limit=AIRTABLE_REPLAY_BATCH_SIZE)
            if result.get("processed"):
                log_event(
                    "airtable_crm_writeback_replay_worker_result",
                    processed=result.get("processed", 0),
                    ok=result.get("ok"),
                    queue=airtable_queue_stats(),
                )
        except Exception as exc:
            log_event("airtable_crm_writeback_replay_worker_error", error=str(exc), traceback=traceback.format_exc())


def start_airtable_replay_worker():
    global AIRTABLE_REPLAY_THREAD
    if AIRTABLE_REPLAY_THREAD and AIRTABLE_REPLAY_THREAD.is_alive():
        return AIRTABLE_REPLAY_THREAD
    AIRTABLE_REPLAY_THREAD = Thread(target=_airtable_replay_worker_loop, name="airtable-replay-worker", daemon=True)
    AIRTABLE_REPLAY_THREAD.start()
    return AIRTABLE_REPLAY_THREAD


def init_runtime_state_db():
    _ensure_parent_dir(RUNTIME_STATE_DB_PATH)
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS AIOS_Promises (
            promise_id INTEGER PRIMARY KEY AUTOINCREMENT,
            whatsapp_id TEXT NOT NULL,
            task_description TEXT NOT NULL,
            source_message TEXT NOT NULL,
            target_deadline_ts INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_ts INTEGER NOT NULL,
            updated_ts INTEGER NOT NULL,
            last_action TEXT DEFAULT ''
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS AIOS_StateMachineSessions (
            whatsapp_id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            state TEXT NOT NULL,
            history_buffer TEXT NOT NULL DEFAULT '[]',
            last_sender_text TEXT DEFAULT '',
            last_urgency TEXT DEFAULT '',
            last_ego_style TEXT DEFAULT '',
            last_state_payload TEXT DEFAULT '{}',
            created_ts INTEGER NOT NULL,
            updated_ts INTEGER NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS AIOS_WhatsAppConversationState (
            sender TEXT PRIMARY KEY,
            last_inbound_message_id TEXT DEFAULT '',
            last_bot_reply_text TEXT DEFAULT '',
            last_bot_reply_time INTEGER DEFAULT 0,
            bot_reply_count_for_inbound INTEGER DEFAULT 0,
            recent_reply_fingerprints TEXT DEFAULT '[]',
            last_human_reply_time INTEGER DEFAULT 0,
            last_intent TEXT DEFAULT '',
            last_retrieval_summary TEXT DEFAULT '',
            autopilot_mode TEXT DEFAULT 'CONTROLLED',
            updated_ts INTEGER NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS AIOS_WhatsAppOutboundDecisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_ts INTEGER NOT NULL,
            sender TEXT NOT NULL,
            message_id TEXT DEFAULT '',
            relationship TEXT DEFAULT '',
            intent TEXT DEFAULT '',
            decision TEXT NOT NULL,
            reason_codes TEXT NOT NULL,
            original_reply TEXT DEFAULT '',
            rewritten_reply TEXT DEFAULT '',
            final_reply TEXT DEFAULT '',
            retrieval_used INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            provider_msg_id TEXT DEFAULT '',
            outcome_label TEXT DEFAULT ''
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS AIOS_AirtableWritebackQueue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_ts INTEGER NOT NULL,
            updated_ts INTEGER NOT NULL,
            direction TEXT NOT NULL,
            sender TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            last_error TEXT DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_aios_promises_due ON AIOS_Promises(status, target_deadline_ts)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_aios_promises_whatsapp ON AIOS_Promises(whatsapp_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_aios_state_sessions_updated ON AIOS_StateMachineSessions(updated_ts)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_aios_outbound_decisions_sender ON AIOS_WhatsAppOutboundDecisions(sender, created_ts)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_aios_airtable_queue_status ON AIOS_AirtableWritebackQueue(status, created_ts)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_aios_airtable_queue_sender ON AIOS_AirtableWritebackQueue(sender, created_ts)")
    con.commit()
    con.close()


def _safe_json_loads(raw, default):
    if raw is None:
        return default
    try:
        parsed = json.loads(raw)
    except Exception:
        return default
    return parsed if parsed is not None else default


def load_area_fact_sheet():
    global AREA_FACT_SHEET
    if AREA_FACT_SHEET is not None:
        return AREA_FACT_SHEET
    for candidate in [AREA_FACT_SHEET_PATH, *AREA_FACT_SHEET_ALT_PATHS]:
        if not candidate or not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            AREA_FACT_SHEET = parsed if isinstance(parsed, dict) else {"areas": parsed}
            normalized = _normalize_area_fact_sheet(AREA_FACT_SHEET)
            log_event("area_fact_sheet_loaded", path=candidate, area_count=len(normalized))
            return AREA_FACT_SHEET
        except Exception as exc:
            log_event("area_fact_sheet_load_error", path=candidate, error=str(exc))
    AREA_FACT_SHEET = {}
    return AREA_FACT_SHEET


def _normalize_area_fact_sheet(raw_sheet):
    if not isinstance(raw_sheet, dict):
        return {}
    if isinstance(raw_sheet.get("areas"), dict):
        return raw_sheet["areas"]
    if isinstance(raw_sheet.get("areas"), list):
        normalized = {}
        for item in raw_sheet["areas"]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("area") or "").strip()
            if name:
                normalized[name] = item
        return normalized
    normalized = {}
    for key, value in raw_sheet.items():
        if isinstance(value, dict):
            normalized[str(key)] = value
    return normalized


def _match_area_fact_sheet(text):
    sheet = _normalize_area_fact_sheet(load_area_fact_sheet())
    if not sheet:
        return {}
    lower = (text or "").lower()
    for name, data in sheet.items():
        if name.lower() in lower:
            return {name: data}
        aliases = data.get("aliases") if isinstance(data, dict) else []
        if isinstance(aliases, list) and any(str(alias).lower() in lower for alias in aliases):
            return {name: data}
    return {}


def _history_summary(history_text, limit=10):
    if not history_text or history_text == "No prior history":
        return "No prior history"
    lines = [line.strip() for line in str(history_text).splitlines() if line.strip()]
    if not lines:
        return "No prior history"
    return "\n".join(lines[-limit:])


def resolve_live_language(text, stored_memory=None, history=""):
    """Prefer the latest user message when clear; otherwise fall back to learned language."""
    latest = detect_language(text)
    stored_memory = stored_memory or {}
    preferred = str(stored_memory.get("preferred_language") or "").strip().lower()
    if latest not in {"neutral", "mixed"}:
        return latest
    if preferred in {"arabic", "english", "german", "russian"}:
        return preferred
    history_language = detect_language(history or "")
    if history_language in {"arabic", "english", "german", "russian"}:
        return history_language
    return "english"


def reply_violates_language_lock(reply, expected_language):
    reply = str(reply or "")
    if not reply or expected_language not in {"arabic", "english", "german", "russian"}:
        return False
    has_ar = bool(re.search(r"[\u0600-\u06FF]", reply))
    has_latin = bool(re.search(r"[A-Za-z]", reply))
    has_cyrillic = bool(re.search(r"[\u0400-\u04FF]", reply))
    if expected_language == "english":
        return has_ar or has_cyrillic
    if expected_language == "arabic":
        return has_latin and not has_ar
    if expected_language == "russian":
        return (has_ar or has_latin) and not has_cyrillic
    if expected_language == "german":
        return has_ar or has_cyrillic
    return False


def language_lock_fallback(text, live_context):
    social_reply = social_context_reply(text, live_context)
    if social_reply:
        return social_reply
    judgment_reply = business_judgment_reply(text, live_context)
    if judgment_reply:
        return judgment_reply
    language = live_context.get("latest_message_language") or "english"
    lower = (text or "").lower()
    if any(token in lower for token in ["tenant", "eviction", "notice", "case", "rent dispute"]):
        if language == "arabic":
            return "وصلت. أرسل لي التفاصيل أو الرسائل وأنا أرتب لك الخطوة الجاية."
        return "Understood. Send me the details or the messages and I’ll tell you the right next step."
    return human_bridge_reply(text)


def _profile_summary(relationship_tag, relationship, contact_context, relationship_memory, business_judgment):
    return {
        "relationship_tag": relationship_tag or "UNKNOWN",
        "relationship": relationship or "Unknown",
        "contact_name": contact_context.get("known_contact_name", ""),
        "known_chat": bool(contact_context.get("known_chat")),
        "preferred_language": relationship_memory.get("preferred_language", ""),
        "preferred_tone": relationship_memory.get("preferred_tone", ""),
        "preferred_detail_level": relationship_memory.get("preferred_detail_level", ""),
        "last_unresolved_topic": business_judgment.get("expected_next", ""),
        "last_requested_action": relationship_memory.get("last_next_action", ""),
        "special_contact_profile": contact_context.get("special_contact_profile") or {},
    }


def _identity_dna_label(system_context):
    if not isinstance(system_context, dict):
        return "Assistant"
    identity_dna = system_context.get("identity_dna") or system_context.get("identity") or {}
    if isinstance(identity_dna, dict):
        for key in ("value", "label", "persona", "role", "name"):
            candidate = str(identity_dna.get(key, "")).strip()
            if candidate:
                return candidate
        investor_profile = identity_dna.get("investor_profile") or {}
        if isinstance(investor_profile, dict):
            candidate = str(investor_profile.get("value", "")).strip()
            if candidate:
                return candidate
        communication_style = identity_dna.get("communication_style") or {}
        if isinstance(communication_style, dict):
            candidate = str(communication_style.get("value", "")).strip()
            if candidate:
                return candidate
    candidate = str(identity_dna).strip()
    return candidate or "Assistant"


def _normalize_weather_context(system_context):
    if not isinstance(system_context, dict):
        return {}
    weather = system_context.get("weather") or system_context.get("weather_context") or {}
    return weather if isinstance(weather, dict) else {}


def _restore_persisted_system_context(live_context, incoming_system_context):
    if incoming_system_context:
        return incoming_system_context
    stored_memory = (live_context or {}).get("stored_memory") or {}
    persisted = stored_memory.get("persisted_system_context") or {}
    return persisted if isinstance(persisted, dict) else {}


def context_merge(live_context, system_context=None):
    merged = dict(live_context or {})
    system_context = _restore_persisted_system_context(merged, system_context)
    if not isinstance(system_context, dict):
        system_context = {}
    if isinstance(system_context.get("system_context"), dict):
        system_context = system_context["system_context"]
    if not system_context and isinstance(merged.get("system_context"), dict):
        system_context = merged["system_context"]

    identity_dna = system_context.get("identity_dna") or system_context.get("identity") or {}
    working_memory = system_context.get("working_memory") or {}
    active_intent = working_memory.get("active_intent") or {}
    decay_metadata = working_memory.get("decay_metadata") or {}
    weather_context = _normalize_weather_context(system_context)
    persistence_meta = system_context.get("persistence_meta") or {}

    normalized_system_context = {
        "identity_dna": {
            "investor_profile": identity_dna.get("investor_profile", {}),
            "communication_style": identity_dna.get("communication_style", {}),
        },
        "working_memory": {
            "active_intent": {
                "area": active_intent.get("area", {}),
                "property_type": active_intent.get("property_type", {}),
                "budget": active_intent.get("budget", {}),
            },
            "decay_metadata": {
                "rate": decay_metadata.get("rate", decay_metadata.get("decay_rate", 0.05)),
                "last_sync": decay_metadata.get("last_sync", ""),
            },
        },
        "weather": weather_context,
        "persistence_meta": {
            "identity_dna": persistence_meta.get("identity_dna", {}),
            "weather": persistence_meta.get("weather", {}),
        },
    }

    merged["system_context"] = normalized_system_context
    merged["identity_dna_label"] = _identity_dna_label(normalized_system_context)
    profile_summary = dict(merged.get("profile_summary") or {})
    profile_summary["investor_profile"] = identity_dna.get("investor_profile", {}).get("value", "")
    profile_summary["communication_style"] = identity_dna.get("communication_style", {}).get("value", "")
    merged["profile_summary"] = profile_summary

    working_memory_summary = dict(merged.get("working_memory") or {})
    working_memory_summary["active_intent"] = {
        "area": active_intent.get("area", {}).get("value", ""),
        "property_type": active_intent.get("property_type", {}).get("value", ""),
        "budget": active_intent.get("budget", {}).get("value", ""),
    }
    working_memory_summary["decay_rate"] = decay_metadata.get("rate", decay_metadata.get("decay_rate", 0.05))
    working_memory_summary["last_sync"] = decay_metadata.get("last_sync", "")
    merged["working_memory"] = working_memory_summary
    merged["working_memory_decay"] = normalized_system_context["working_memory"]["decay_metadata"]
    if weather_context:
        merged["weather_context"] = weather_context
    return merged


def merge_system_context(live_context, system_context=None):
    return context_merge(live_context, system_context=system_context)


def _ensure_parent_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _parse_json_body(raw):
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, flags=re.S)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _validate_psych_profile(payload):
    if not isinstance(payload, dict):
        return None
    urgency = str(payload.get("urgency", "")).strip().title()
    ego_style = str(payload.get("ego_style", "")).strip()
    reasoning = str(payload.get("reasoning", "")).strip()
    if urgency not in {"High", "Medium", "Low"}:
        return None
    if ego_style not in {"Direct-Blunt", "Relationship-Oriented", "Analytical"}:
        return None
    if not reasoning:
        reasoning = "Inferred from user message and recent history."
    return {
        "urgency": urgency,
        "ego_style": ego_style,
        "reasoning": reasoning,
    }


def _normalize_psych_payload(payload):
    profile = _validate_psych_payload_node(payload) if callable(_validate_psych_payload_node) else _validate_psych_profile(payload)
    if profile:
        return profile
    return _validate_psych_profile(payload)


def _history_turns_for_metrics(session):
    if not session:
        return []
    return [turn for turn in session.get("history_buffer", []) if str(turn.get("role", "")).lower() == "user"]


def _state_machine_session(sender):
    init_runtime_state_db()
    if not sender:
        return {
            "whatsapp_id": sender,
            "session_token": "",
            "state": "UNKNOWN",
            "history_buffer": [],
            "contact_record_exists": False,
            "payload": {},
            "last_sender_text": "",
            "last_urgency": "",
            "last_ego_style": "",
        }
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.row_factory = sqlite3.Row
    record = con.execute(
        "SELECT * FROM AIOS_StateMachineSessions WHERE whatsapp_id = ?",
        (sender,),
    ).fetchone()
    if record:
        contact_row = find_chat_session(sender)
        session = {
            "whatsapp_id": sender,
            "session_token": record["session_token"],
            "state": record["state"],
            "history_buffer": _safe_json_loads(record["history_buffer"], []),
            "contact_record_exists": bool(contact_row),
            "payload": _safe_json_loads(record["last_state_payload"], {}),
            "created_ts": record["created_ts"],
            "updated_ts": record["updated_ts"],
            "last_sender_text": record["last_sender_text"],
            "last_urgency": record["last_urgency"],
            "last_ego_style": record["last_ego_style"],
        }
        con.close()
        return session

    contact_row = find_chat_session(sender)
    contact_known = bool(contact_row)
    now = int(time.time())
    state = "ACTIVE_CONTEXT" if contact_known else "DISCOVERY_RAPPORT"
    session = {
        "whatsapp_id": sender,
        "session_token": uuid.uuid4().hex,
        "state": state,
        "history_buffer": [],
        "contact_record_exists": contact_known,
        "payload": {},
        "created_ts": now,
        "updated_ts": now,
        "last_sender_text": "",
        "last_urgency": "",
        "last_ego_style": "",
    }
    try:
        con.execute(
            """
            INSERT INTO AIOS_StateMachineSessions
                (whatsapp_id, session_token, state, history_buffer, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sender, session["session_token"], state, "[]", now, now),
        )
        con.commit()
    except Exception as exc:
        log_event("runtime_session_init_failed", sender=sender, error=str(exc), state=state)
    con.close()
    log_event("state_session_init", sender=sender, state=state, contact_found=contact_known, session_token=session["session_token"])
    return session


def _build_marketing_reengagement_prompt(sender, session):
    return {
        "type": "marketing_reengagement",
        "sender": sender,
        "message": "Continue the thread as AIOS + Omar-style follow-up, with a warm reconnect and clear next step.",
        "created_ts": int(time.time()),
    }


def cleanup_stale_discovery_sessions(now_ts=None):
    if not os.path.exists(RUNTIME_STATE_DB_PATH):
        return []
    now_ts = now_ts or time.time()
    cutoff = int(now_ts - DISCOVERY_STALE_SECONDS)
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT whatsapp_id, state, history_buffer, last_state_payload, updated_ts FROM AIOS_StateMachineSessions WHERE state = 'DISCOVERY_RAPPORT' AND updated_ts < ?",
            (cutoff,),
        ).fetchall()
        upgraded = []
        for row in rows:
            payload = _safe_json_loads(row["last_state_payload"], {})
            payload = payload if isinstance(payload, dict) else {}
            payload["re_engagement_prompt"] = _build_marketing_reengagement_prompt(row["whatsapp_id"], dict(row))
            con.execute(
                """
                UPDATE AIOS_StateMachineSessions
                SET state = 'RE_ENGAGE_CAMPAIGN',
                    last_state_payload = ?,
                    updated_ts = ?
                WHERE whatsapp_id = ?
                """,
                (json.dumps(payload, ensure_ascii=False), int(now_ts), row["whatsapp_id"]),
            )
            upgraded.append(row["whatsapp_id"])
            log_event(
                "state_session_reengaged",
                sender=row["whatsapp_id"],
                previous_state=row["state"],
                next_state="RE_ENGAGE_CAMPAIGN",
            )
        con.commit()
        if upgraded:
            log_event("state_discovery_cleanup", count=len(upgraded), sender_count=upgraded)
        return upgraded
    finally:
        con.close()


def _persist_state_session(session):
    if not session or not session.get("whatsapp_id"):
        return
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.execute(
        """
        INSERT INTO AIOS_StateMachineSessions
            (whatsapp_id, session_token, state, history_buffer, last_sender_text, last_urgency, last_ego_style, last_state_payload, created_ts, updated_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(whatsapp_id) DO UPDATE SET
            session_token=excluded.session_token,
            state=excluded.state,
            history_buffer=excluded.history_buffer,
            last_sender_text=excluded.last_sender_text,
            last_urgency=excluded.last_urgency,
            last_ego_style=excluded.last_ego_style,
            last_state_payload=excluded.last_state_payload,
            updated_ts=excluded.updated_ts
        """,
        (
            session["whatsapp_id"],
            session.get("session_token") or uuid.uuid4().hex,
            session.get("state", "ACTIVE_CONTEXT"),
            json.dumps(session.get("history_buffer", []), ensure_ascii=False),
            str(session.get("last_sender_text", ""))[:500],
            str(session.get("last_urgency", "")),
            str(session.get("last_ego_style", "")),
            json.dumps(session.get("payload", {}), ensure_ascii=False),
            int(session.get("created_ts", int(time.time()))),
            int(time.time()),
        ),
    )
    con.commit()
    con.close()


def _append_to_state_history(session, role, text, max_turns=STATE_HISTORY_LIMIT):
    if not session or not text:
        return session
    buffer = list(session.get("history_buffer", []))
    buffer.append({"role": role, "text": str(text).strip()})
    if len(buffer) > max_turns:
        buffer = buffer[-max_turns:]
    session["history_buffer"] = buffer
    session["updated_ts"] = int(time.time())
    return session


def _build_psych_profile_prompt(text, history, session=None):
    payload = {
        "task": "Return strict JSON only with keys urgency, ego_style, reasoning.",
        "fields": {
            "urgency": "High | Medium | Low",
            "ego_style": "Direct-Blunt | Relationship-Oriented | Analytical",
            "reasoning": "Brief justification",
        },
        "input": {
            "new_message": text,
            "history": history,
            "session_state": session.get("state") if isinstance(session, dict) else "",
        },
    }
    return payload


def detect_psych_profile(text, sender=None, session=None, live_context=None):
    """Run lightweight psychological profiling step before completion."""
    history = state_history_text(session) if isinstance(session, dict) else ""
    fallback_profile = {
        "urgency": "Medium",
        "ego_style": "Relationship-Oriented",
        "reasoning": "Fallback rule from keyword heuristics.",
    }

    if callable(analyze_psych_profile_local):
        try:
            local_profile = analyze_psych_profile_local(message_text=text, sender=sender or "", history=history)
            validated_profile = _normalize_psych_payload(local_profile)
            if validated_profile:
                validated_profile["source"] = "psych_node"
                log_event(
                    "psych_profile_local_ok",
                    sender=sender,
                    urgency=validated_profile.get("urgency"),
                    ego_style=validated_profile.get("ego_style"),
                    reasoning=validated_profile.get("reasoning"),
                )
                return validated_profile
        except Exception as exc:
            log_event("psych_profile_local_error", sender=sender, error=str(exc))

    lower = (text or "").lower()
    if any(x in lower for x in ["urgent", "asap", "now", "immediately", "critical", "very urgent", "عاجل", "فوريا", "ضروري"]):
        fallback_profile["urgency"] = "High"
    elif any(x in lower for x in ["thank", "thanks", "مرحبا", "هلا", "hello", "hi", "مرحبا", "تمام"]):
        fallback_profile["urgency"] = "Low"
    if any(x in lower for x in ["facts", "data", "numbers", "analysis", "compare", "ROI", "roi", "analyze"]):
        fallback_profile["ego_style"] = "Analytical"
    elif any(x in lower for x in ["brother", "friend", "يا", "yalla", "شكرًا", "thanks", "ya"]):
        fallback_profile["ego_style"] = "Relationship-Oriented"

    try:
        prompt = _build_psych_profile_prompt(text, history, session)
        status, parsed, raw = post_json(
            PSYCH_PROFILE_ENDPOINT,
            {
                "instruction": "Return strict JSON only with keys urgency, ego_style, reasoning.",
                "payload": prompt,
                "latest_message": text,
                "sender": sender,
                "history": history,
            },
            timeout=PSYCHO_ENDPOINT_TIMEOUT,
        )
        if status >= 200 and status < 300:
            parsed_payload = _validate_psych_profile(_parse_json_body(parsed) or _parse_json_body(raw))
            if parsed_payload:
                parsed_payload["reasoning"] = str(parsed_payload.get("reasoning") or "").strip()[:320]
                parsed_payload["source"] = "psych_api"
                log_event(
                    "psych_profile_ok",
                    sender=sender,
                    urgency=parsed_payload.get("urgency"),
                    ego_style=parsed_payload.get("ego_style"),
                    reasoning=parsed_payload.get("reasoning"),
                )
                return parsed_payload
        log_event("psych_profile_non_json", sender=sender, status=status, raw=raw[:300])
    except Exception as exc:
        log_event("psych_profile_error", sender=sender, error=str(exc))

    log_event("psych_profile_fallback", sender=sender, urgency=fallback_profile["urgency"], ego_style=fallback_profile["ego_style"], reasoning=fallback_profile["reasoning"])
    return fallback_profile


def _transition_session_state(session, next_state, payload=None):
    if not session or not session.get("whatsapp_id"):
        return session
    prev_state = session.get("state")
    session["state"] = next_state
    if payload is not None:
        session["payload"] = payload
    session["updated_ts"] = int(time.time())
    if prev_state != next_state:
        log_event("session_state_transition", sender=session.get("whatsapp_id"), previous_state=prev_state, next_state=next_state)
    return session


def promise_deadline_from_text(text):
    lower = (text or "").lower()
    now = int(time.time())
    patterns = [
        (r"\b(?:in|within)\s+(\d+)\s*(minute|minutes|min|mins)\b", 60),
        (r"\b(?:in|within)\s+(\d+)\s*(hour|hours|hr|hrs)\b", 3600),
        (r"\b(?:in|within)\s+(\d+)\s*(day|days)\b", 86400),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, lower)
        if match:
            return now + int(match.group(1)) * multiplier
    if any(x in lower for x in ["tomorrow", "غداً", "غدا", "بكرا"]):
        return now + 86400
    if any(x in lower for x in ["later", "update you", "let you know", "أحدثك", "برجعلك", "بخبرك"]):
        return now + 7200
    return None


def detect_ai_promise(reply):
    text = str(reply or "").strip()
    lower = text.lower()
    commitment_markers = [
        "i'll let you know",
        "i will let you know",
        "i'll check",
        "i will check",
        "i'll update",
        "i will update",
        "let me update you",
        "tomorrow",
        "later",
        "within",
        "in 2 hours",
        "برجعلك",
        "بخبرك",
        "أحدثك",
        "بشيك",
    ]
    if not any(marker in lower for marker in commitment_markers):
        return None
    deadline = promise_deadline_from_text(text)
    if deadline is None:
        return None
    return {
        "task_description": re.sub(r"\s+", " ", text)[:500],
        "target_deadline_ts": int(deadline),
    }


RESTRICTED_PATTERN_MAP = {
    "owner_name": [
        r"\bowner\b",
        r"\bnamed\b",
        r"\bowner name\b",
        r"\bمالك\b",
    ],
    "owner_phone": [
        r"\+\d{1,4}[\s-]?\d{6,14}",
        r"\b05\d{8}\b",
        r"\b\+971\d{9}\b",
    ],
    "passport": [
        r"\bpassport\b",
        r"\bpassport id\b",
        r"\bID\s*[:\-]?\s*[A-Za-z0-9]{6,12}\b",
        r"\b[A-Z]{1,2}\d{7,9}\b",
    ],
    "buyer_email": [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ],
    "seller_email": [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ],
    "commissions_layout": [
        r"commission",
        r"commission fee",
        r"commission percentage",
        r"commission\s*rate",
        r"عمولة",
    ],
}


def _match_restricted_terms(text):
    lowered = (text or "").lower()
    if not lowered:
        return False, ""
    for key, patterns in RESTRICTED_PATTERN_MAP.items():
        for pattern in patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return True, key
    # semantic variation catches common Arabic transliteration/phrasing around sensitive entities
    sensitive_phrases = [
        "private owner",
        "owner info",
        "owner contact",
        "private ownership",
        "owner details",
        "buyer passport",
        "seller email",
        "owner email",
    ]
    if any(phrase in lowered for phrase in sensitive_phrases):
        return True, "semantic_variant"
    return False, ""


def sanitize_human_output(text):
    cleaned = str(text or "")
    replacements = [
        (r"(?i)registry\s+file", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)internal\s+analysis", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)\bloop\b", random.choice(BUSY_REPLIES)),
        (r"(?i)verification\s+in\s+progress", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)will\s+revert", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)i\s*will\s*check", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)i\s*will\s*verify", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)i\s*will\s*update", lambda m: random.choice(BUSY_REPLIES)),
        (r"(?i)i\s*(am|'m)\s*escalat\w*", lambda m: random.choice(HUMAN_BRIDGE_REPLIES_EN)),
        (r"(?i)escalation\s+submitted", lambda m: random.choice(HUMAN_BRIDGE_REPLIES_EN)),
        (r"(?i)support\s*ticket", lambda m: random.choice(HUMAN_BRIDGE_REPLIES_EN)),
        (r"(?i)human\s+specialist", lambda m: random.choice(HUMAN_BRIDGE_REPLIES_EN)),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement if callable(replacement) else replacement, cleaned)
    return cleaned.strip()


def resolve_relationship_override(sender):
    sender_clean = re.sub(r"\D+", "", str(sender or ""))
    if not sender_clean:
        return None
    mapped = AIOS_STRESS_RELATIONSHIP_TAG_MAP.get(sender_clean)
    if not mapped:
        return None
    return mapped


def _is_bridge_feedback(text):
    lowered = (text or "").lower()
    terms = [
        "robotic",
        "sounds robotic",
        "sounding robotic",
        "too robotic",
        "weird",
        "weirdly",
        "ai-ish",
        "ai assistant",
        "just AI",
        "not human",
        "robot",
        "مجنون",  # keep literal for Arabic casual detection
        "روبوت",
        "غريب",
        "غريب شوي",
        "صوت آلي",
    ]
    return any(term in lowered for term in terms)


def human_bridge_reply(text):
    language = detect_language(text)
    if language == "arabic":
        return random.choice(HUMAN_BRIDGE_REPLIES_AR)
    return random.choice(HUMAN_BRIDGE_REPLIES_EN)


def evaluate_relationship_tone_match(expected_tag, reply_text):
    if not expected_tag:
        return True
    lower = (reply_text or "").lower()
    if expected_tag == "FRIEND" or expected_tag == "FAMILY":
        casual = (
            "bro" in lower
            or "ya" in lower
            or "يا" in lower
            or "هلا" in lower
            or "yo" in lower
            or "yoo" in lower
            or "hey" in lower
            or "🙂" in lower
            or "😄" in lower
            or "!" in reply_text
            or "yo" in lower
            or "yooo" in lower
            or "ياا" in lower
            or "هلاا" in lower
        )
        formal_hits = ("dear" in lower or "sir" in lower or "madam" in lower or "kindly" in lower or "regards" in lower)
        if formal_hits:
            return False
        return bool(casual or "😂" in (reply_text or "") or "😄" in (reply_text or ""))
    if expected_tag in {"CLIENT", "AGENT", "STAFF", "TRUSTED_PARTNER"}:
        formal_only_hit = True
        if any(token in lower for token in ["bro", "ya ", "يا ", "habibi", "ياا", "حبيبي", "😄", "😂"]):
            formal_only_hit = False
        return formal_only_hit
    if expected_tag == "UNKNOWN":
        # Neutral acceptance: avoid clear mismatch to FRIEND casual or CLIENT formal.
        has_friend_signal = any(token in lower for token in ["يا", "ياا", "habibi", "😄", "😂", "yooo", "hahaha", "how's it going", "hey"])
        has_client_formal_signal = any(token in lower for token in ["regards", "sir", "madam", "kindly", "dear", "please", "thanks"])
        if has_friend_signal and has_client_formal_signal:
            return False
        return bool(reply_text)
    return True


def relationship_classifier_node(sender, text, contact_context):
    sender_clean = normalize_phone(sender)
    profile = contact_context.get("special_contact_profile") or {}
    if profile.get("relationship"):
        mapped_profile_relationship = CANONICAL_RELATIONSHIP_MAP.get(str(profile.get("relationship")), "UNKNOWN")
        if mapped_profile_relationship in RELATIONSHIP_TAGS:
            return mapped_profile_relationship, "special_contact_profile"

    strategy = RELATIONSHIP_ASSIGNMENT_STRATEGY

    if sender_clean in MANUAL_CONTACT_ALIASES and strategy in {"manual_only", "manual_then_contextual", "manual_then_dynamic"}:
        raw_tag = MANUAL_CONTACT_ALIASES[sender_clean].get("relationship")
        return CANONICAL_RELATIONSHIP_MAP.get(raw_tag, "UNKNOWN"), "manual_contact_alias"

    if strategy == "manual_only":
        return "UNKNOWN", "manual_only_default"

    stored = RELATIONSHIP_STORE.get(sender_clean, {})
    raw_tag = stored.get("relationship") or contact_context.get("relationship")
    if strategy in {"contextual", "manual_then_contextual", "manual_then_dynamic"} and raw_tag:
        return CANONICAL_RELATIONSHIP_MAP.get(str(raw_tag), "UNKNOWN"), "stored_memory"

    if strategy in {"dynamic", "manual_then_dynamic"}:
        if contact_context.get("known_chat") and any(
            token in (str(contact_context.get("known_contact_name") or "").lower()) for token in ["agent", "broker", "hsh", "omar"]
        ):
            return "STAFF", "dynamic_known_hint"
        if any(token in (text or "").lower() for token in ["friend", "bro", "يا", "ياا", "ياخ", "يااا", "habibi", "يلا", "yalla", "😂", "😄"]):
            return "FRIEND", "dynamic_text_signal"
        if any(token in (text or "").lower() for token in ["agent", "broker", "brokerage", "customer", "buyer", "tenant", "vendor", "client"]):
            return "CLIENT", "dynamic_text_signal"

    if strategy in {"contextual", "manual_then_contextual", "manual_then_dynamic"}:
        known_name = (contact_context.get("known_contact_name") or "").lower()
        if "group" in known_name or "agent" in known_name or "broker" in known_name:
            return "AGENT", "name_signal"
        if any(token in known_name for token in ["hsh", "omar", "internal", "staff", "team"]):
            return "STAFF", "name_signal"
        if contact_context.get("known_chat"):
            return "CLIENT", "known_chat"

    if any(token in (text or "").lower() for token in ["يا", "bro", "brother", "أخي", "صديق", "friend", "habibi", "yalla", "ياا"]):
        return "FRIEND", "text_signal"

    if strategy == "dynamic":
        if not contact_context.get("relationship_context_seeded"):
            return "UNKNOWN", "dynamic_pending"

    return "UNKNOWN", "default_unknown"


def bridge_no_match_reply(text):
    # No-Match must never be exposed as user text. Use a short bridge + continue-state.
    return random.choice(NO_MATCH_BRIDGE_REPLIES)


def apply_data_shield(text):
    blocked, reason = _match_restricted_terms(text)
    if not blocked:
        return str(text or "").strip(), False, ""
    return RESTRICTED_OUTBOUND_FALLBACK, True, reason


def estimate_human_delay(reply_text, urgency):
    text_length = len(str(reply_text or ""))
    lower_reply = str(reply_text or "").lower()
    complex_reply = text_length >= 150 or "analysis" in lower_reply or "compare" in lower_reply
    if text_length < 20:
        base = random.uniform(0.5, 1.0)
    elif text_length < 100:
        base = random.uniform(1.5, 2.5)
    elif complex_reply:
        base = random.uniform(3.0, 4.0)
    else:
        base = random.uniform(3.0, 4.0)
    return round(min(base, 8.0), 2)


def _derive_post_response_outcome(
    *,
    sender_text: str,
    reply_text: str,
    live_context: dict,
    send_status: int,
    send_result: dict,
) -> dict:
    if send_status < 200 or send_status >= 300:
        return {
            "outcome_label": "failed",
            "outcome_confidence": 0.9,
            "impact_level": "high",
            "notes": "Response failed to send",
        }

    lower_reply = (reply_text or "").lower()
    lower_text = (sender_text or "").lower()
    judgment = live_context.get("business_judgment", {}) if isinstance(live_context, dict) else {}
    next_action = str(judgment.get("next_action", "")).lower()
    expected_next = str(judgment.get("expected_next", "")).lower()
    intent = str(live_context.get("intent", "")).lower() if isinstance(live_context, dict) else ""

    if any(token in lower_reply for token in ("sorry", "sorry!", "can't help", "unable to", "will not share", "cannot share")):
        return {
            "outcome_label": "blocked",
            "outcome_confidence": 0.74,
            "impact_level": "medium",
            "notes": "Reply indicates restriction/boundary response",
        }

    if any(token in lower_reply for token in ("all set", "confirmed", "done", "agreed", "booked", "sent options", "scheduled", "yes", "great")):
        return {
            "outcome_label": "success",
            "outcome_confidence": 0.85,
            "impact_level": "high" if "booked" in lower_reply or "confirmed" in lower_reply else "medium",
            "notes": "Positive outcome signal in outbound reply",
        }

    if any(token in expected_next for token in ("shortlist_or_check_options", "developer_shortlist_or_options", "continue_buyer_search")):
        return {
            "outcome_label": "in_progress",
            "outcome_confidence": 0.62,
            "impact_level": "medium",
            "notes": f"Conversation moved to expected next: {expected_next}",
        }

    if next_action in {"recommend", "continue_buyer_requirement", "urgent_action_first", "calm_action_first"}:
        return {
            "outcome_label": "progress",
            "outcome_confidence": 0.6,
            "impact_level": "medium",
            "notes": f"Business action progressed: {next_action}",
        }

    if any(token in lower_text for token in ("thank", "شكرا", "thanks", "thank you", "تمام", "ممتاز", "great", "awesome")):
        return {
            "outcome_label": "satisfaction",
            "outcome_confidence": 0.66,
            "impact_level": "low",
            "notes": "Positive explicit user intent before reply",
        }

    if intent in {"complaint", "joke", "casual_greeting", "friend_chat"}:
        return {
            "outcome_label": "non_business",
            "outcome_confidence": 0.5,
            "impact_level": "low",
            "notes": "No direct outcome signal for core conversion path",
        }

    return {
        "outcome_label": "pending",
        "outcome_confidence": 0.35,
        "impact_level": "unknown",
        "notes": "Outcome not yet known; pending user response",
    }


def split_reply_message(text):
    body = str(text or "").strip()
    if not body:
        return []
    if "\n\n" in body:
        parts = [part.strip() for part in body.split("\n\n", 1) if part.strip()]
        if len(parts) == 2:
            return parts
    match = re.search(r"[.\n]", body)
    if not match or len(body) < 220:
        return [body]
    first = body[: match.end()].strip()
    second = body[match.end() :].strip()
    if not first or not second:
        return [body]
    return [first, second]


def send_typing_state(sender):
    if not sender:
        return
    token = keychain_secret("AIOS Wasender API Key")
    try:
        status, parsed, raw = post_json(
            WASENDER_TYPING_URL,
            {"to": sender, "state": "typing"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "AIOS-Simple-WhatsApp-Gateway/1.0",
            },
            timeout=8,
        )
        if status < 200 or status >= 300:
            log_event("typing_webhook_failed", sender=sender, status=status, raw=raw[:240])
    except Exception as exc:
        log_event("typing_webhook_error", sender=sender, error=str(exc))


def store_ai_promise(whatsapp_id, reply):
    promise = detect_ai_promise(reply)
    if not promise or not whatsapp_id:
        return None
    init_runtime_state_db()
    ts = int(time.time())
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    cur = con.execute(
        """
        INSERT INTO AIOS_Promises
            (whatsapp_id, task_description, source_message, target_deadline_ts, status, created_ts, updated_ts)
        VALUES (?, ?, ?, ?, 'open', ?, ?)
        """,
        (
            whatsapp_id,
            promise["task_description"],
            str(reply or "")[:1000],
            promise["target_deadline_ts"],
            ts,
            ts,
        ),
    )
    con.commit()
    promise_id = cur.lastrowid
    con.close()
    log_event(
        "ai_promise_tracked",
        promise_id=promise_id,
        whatsapp_id=whatsapp_id,
        task_description=promise["task_description"],
        target_deadline_ts=promise["target_deadline_ts"],
    )
    return promise_id


def log_retrieval_audit(sender, text, live_context, reply):
    proof = live_context.get("retrieval_proof", {}) if isinstance(live_context, dict) else {}
    if not proof.get("required"):
        return
    match_found = bool(proof.get("match_found"))
    reply_class = "no_match" if not match_found else "matched_reply"
    if reply:
        lower_reply = str(reply).lower()
        if any(x in lower_reply for x in ("no match found", "no matching record", "not found", "couldn't find")):
            reply_class = "no_match"
    log_event(
        "retrieval_audit_trail",
        sender=sender,
        user_visible=False,
        source_used=proof.get("source_used"),
        query_used=proof.get("query_used"),
        match_found=match_found,
        retrieval_intent=proof.get("retrieval_intent"),
        route=proof.get("route"),
        result_count=proof.get("result_count"),
        reply_class=reply_class,
        message_excerpt=str(text or "")[:180],
    )


def _now_epoch():
    return int(time.time())


def _json_list(value):
    parsed = _safe_json_loads(value, [])
    return parsed if isinstance(parsed, list) else []


def _reply_fingerprint(text):
    lowered = str(text or "").lower()
    lowered = lowered.translate(str.maketrans("", "", string.punctuation))
    tokens = [token for token in re.findall(r"\w+", lowered) if len(token) > 2]
    if not tokens:
        return ""
    return " ".join(tokens[:80])


def _semantic_overlap(a, b):
    left = set(_reply_fingerprint(a).split())
    right = set(_reply_fingerprint(b).split())
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def load_outbound_state(sender):
    init_runtime_state_db()
    if not sender:
        return {}
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM AIOS_WhatsAppConversationState WHERE sender = ?",
        (sender,),
    ).fetchone()
    con.close()
    if not row:
        return {
            "sender": sender,
            "last_inbound_message_id": "",
            "last_bot_reply_text": "",
            "last_bot_reply_time": 0,
            "bot_reply_count_for_inbound": 0,
            "recent_reply_fingerprints": [],
            "last_human_reply_time": 0,
            "last_intent": "",
            "last_retrieval_summary": "",
            "autopilot_mode": AUTOPILOT_DEFAULT_MODE if AUTOPILOT_DEFAULT_MODE in {"OFF", "DRAFT", "CONTROLLED", "FULL"} else "CONTROLLED",
        }
    state = dict(row)
    state["recent_reply_fingerprints"] = _json_list(state.get("recent_reply_fingerprints"))
    return state


def save_outbound_state(sender, state):
    if not sender:
        return
    init_runtime_state_db()
    now = _now_epoch()
    fingerprints = state.get("recent_reply_fingerprints") or []
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.execute(
        """
        INSERT INTO AIOS_WhatsAppConversationState
            (sender, last_inbound_message_id, last_bot_reply_text, last_bot_reply_time,
             bot_reply_count_for_inbound, recent_reply_fingerprints, last_human_reply_time,
             last_intent, last_retrieval_summary, autopilot_mode, updated_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sender) DO UPDATE SET
            last_inbound_message_id=excluded.last_inbound_message_id,
            last_bot_reply_text=excluded.last_bot_reply_text,
            last_bot_reply_time=excluded.last_bot_reply_time,
            bot_reply_count_for_inbound=excluded.bot_reply_count_for_inbound,
            recent_reply_fingerprints=excluded.recent_reply_fingerprints,
            last_human_reply_time=excluded.last_human_reply_time,
            last_intent=excluded.last_intent,
            last_retrieval_summary=excluded.last_retrieval_summary,
            autopilot_mode=excluded.autopilot_mode,
            updated_ts=excluded.updated_ts
        """,
        (
            sender,
            str(state.get("last_inbound_message_id", "")),
            str(state.get("last_bot_reply_text", ""))[:2000],
            int(state.get("last_bot_reply_time") or 0),
            int(state.get("bot_reply_count_for_inbound") or 0),
            json.dumps(fingerprints[-20:], ensure_ascii=False),
            int(state.get("last_human_reply_time") or 0),
            str(state.get("last_intent", ""))[:120],
            str(state.get("last_retrieval_summary", ""))[:1000],
            str(state.get("autopilot_mode") or "CONTROLLED"),
            now,
        ),
    )
    con.commit()
    con.close()


def record_human_reply_time(sender):
    if not sender:
        return
    state = load_outbound_state(sender)
    state["last_human_reply_time"] = _now_epoch()
    save_outbound_state(sender, state)


def _contains_any(text, needles):
    lowered = str(text or "").lower()
    return any(str(needle).lower() in lowered for needle in needles)


def _question_count(text):
    body = str(text or "")
    return body.count("?") + body.count("؟")


def _looks_like_private_owner_leak(text):
    lower = str(text or "").lower()
    if re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text or ""):
        return True
    if re.search(r"(?:\+971|00971|971|05)\D{0,3}\d{2}\D{0,3}\d{3}\D{0,3}\d{4}", text or ""):
        return True
    return any(phrase in lower for phrase in ["owner phone", "owner contact", "owner email", "passport", "emirates id"])


def rewrite_to_omar_style(proposed_reply, context=None):
    context = context or {}
    reply = sanitize_human_output(str(proposed_reply or "").strip())
    reply = re.sub(r"(?i)\bAIOS\b[:,]?\s*", "", reply).strip()
    reply = re.sub(r"(?i)\bthe verified rental source is connected,\s*but\s*", "", reply).strip()
    reply = re.sub(r"(?i)\bverified rental source is connected[, ]*", "", reply).strip()
    reply = re.sub(r"(?i)\bsource is connected[, ]*", "", reply).strip()
    reply = re.sub(r"(?i)\bI(?:'|’)?ll confirm before sending\.?", "I’ll check properly before sending anything.", reply).strip()
    reply = re.sub(r"(?i)\bI don(?:'|’)t see a confirmed live option yet\.?", "I don’t have a confirmed live match yet.", reply).strip()
    reply = re.sub(r"(?i)^noted[.! ]*$", "Got it.", reply).strip()
    reply = re.sub(r"(?i)^hello[.! ]*$", "Hey, what’s up?", reply).strip()
    reply = re.sub(r"(?i)^my brother hassan\s*[😄😅]*\s*tell me[.! ]*$", "Hassan, investment or personal use?", reply).strip()
    reply = re.sub(r"\bThe\s+but\b", "", reply).strip()
    if context.get("retrieval_used") is False:
        reply = re.sub(r"(?i)\bI checked\b", "I looked at the context", reply).strip()
    if _contains_any(reply, TEST_TEXT_BLOCKLIST):
        return reply
    if len(reply) > 450:
        reply = reply[:430].rsplit(" ", 1)[0].strip() + "..."
    return reply


def _autopilot_mode_for(relationship_tag, intent, sender, state):
    mode = str((state or {}).get("autopilot_mode") or AUTOPILOT_DEFAULT_MODE or "CONTROLLED").upper()
    if mode not in {"OFF", "DRAFT", "CONTROLLED", "FULL"}:
        mode = "CONTROLLED"
    relationship = str(relationship_tag or "").upper()
    if relationship in {"FRIEND", "FAMILY"} and str(intent or "").lower() in {"property", "retrieval", "business", "ownership"}:
        if normalize_phone(sender) not in {normalize_phone(x) for x in AIOS_WHATSAPP_TEST_SENDERS}:
            return "DRAFT"
    return mode


def outbound_safety_controller(input_payload):
    payload = dict(input_payload or {})
    sender = normalize_phone(payload.get("sender"))
    relationship = str(payload.get("relationship") or payload.get("relationship_tag") or "UNKNOWN")
    relationship_tag = str(payload.get("relationship_tag") or relationship or "UNKNOWN").upper()
    message_id = str(payload.get("message_id") or "")
    inbound_text = str(payload.get("inbound_text") or "")
    proposed_reply = str(payload.get("proposed_reply") or "")
    recent_replies = list(payload.get("recent_replies") or [])
    last_bot_reply = str(payload.get("last_bot_reply") or "")
    intent = str(payload.get("intent") or "").lower()
    state = payload.get("state") if isinstance(payload.get("state"), dict) else load_outbound_state(sender)
    reason_codes = []
    final_reply = proposed_reply
    decision = "SEND_NOW"
    now = _now_epoch()

    allowlisted_test_sender = sender in {normalize_phone(x) for x in AIOS_WHATSAPP_TEST_SENDERS}
    is_test_message = bool(payload.get("is_test_message")) or _contains_any(inbound_text, TEST_TEXT_BLOCKLIST) or _contains_any(proposed_reply, TEST_TEXT_BLOCKLIST)
    if is_test_message and not allowlisted_test_sender:
        reason_codes.append("blocked_test_text")
        decision = "DO_NOT_SEND"

    if message_id and state.get("last_inbound_message_id") == message_id and int(state.get("bot_reply_count_for_inbound") or 0) > 0:
        reason_codes.append("blocked_duplicate_inbound")
        decision = "DO_NOT_SEND"

    fingerprints = state.get("recent_reply_fingerprints") or []
    all_recent = recent_replies + [last_bot_reply, state.get("last_bot_reply_text", "")]
    proposed_fp = _reply_fingerprint(proposed_reply)
    if proposed_fp:
        for item in all_recent:
            if item and _semantic_overlap(proposed_reply, item) >= 0.78:
                reason_codes.append("blocked_duplicate_semantic_reply")
                decision = "DO_NOT_SEND"
                break
        if proposed_fp in fingerprints:
            reason_codes.append("blocked_duplicate_fingerprint")
            decision = "DO_NOT_SEND"

    last_human_reply_time = int(payload.get("last_human_reply_time") or state.get("last_human_reply_time") or 0)
    if last_human_reply_time and now - last_human_reply_time <= 90:
        reason_codes.append("blocked_human_recent")
        decision = "DO_NOT_SEND"

    if relationship_tag in {"FRIEND", "FAMILY"} and intent in {"property", "retrieval", "business", "ownership"} and not allowlisted_test_sender:
        reason_codes.append("friend_business_draft")
        if decision == "SEND_NOW":
            decision = "DRAFT_FOR_OMAR"

    original_reply = str(payload.get("original_reply") or proposed_reply)
    if _contains_any(original_reply, GENERIC_FALLBACK_BLOCKLIST) or _contains_any(proposed_reply, GENERIC_FALLBACK_BLOCKLIST) or (
        "i checked" in proposed_reply.lower() and not payload.get("retrieval_used")
    ):
        reason_codes.append("blocked_low_quality_fallback")
        if decision == "SEND_NOW":
            decision = "DRAFT_FOR_OMAR"

    private_flags = payload.get("private_or_sensitive_flags") or []
    if private_flags or _looks_like_private_owner_leak(proposed_reply):
        approved_private = relationship_tag in {"OMAR", "TRUSTED_PARTNER"} or allowlisted_test_sender
        if not approved_private:
            reason_codes.append("blocked_unsafe_private")
            decision = "ESCALATE_TO_OMAR"

    if _question_count(proposed_reply) > 1:
        reason_codes.append("too_many_questions")
        if decision == "SEND_NOW":
            decision = "DRAFT_FOR_OMAR"

    if len(proposed_reply) > 450:
        reason_codes.append("reply_over_450_chars")
        if decision == "SEND_NOW":
            decision = "DRAFT_FOR_OMAR"

    mode = _autopilot_mode_for(relationship_tag, intent, sender, state)
    if mode == "OFF":
        reason_codes.append("autopilot_off")
        decision = "DRAFT_FOR_OMAR"
    elif mode == "DRAFT" and decision == "SEND_NOW":
        reason_codes.append("autopilot_draft_mode")
        decision = "DRAFT_FOR_OMAR"

    if decision not in CONTROLLED_AUTOPILOT_DECISIONS:
        decision = "DRAFT_FOR_OMAR"
    return {
        "decision": decision,
        "reason_codes": list(dict.fromkeys(reason_codes)) or ["safe_controlled_send"],
        "final_reply": final_reply,
        "mode": mode,
        "sent": False,
    }


def log_outbound_decision(payload, decision_result, original_reply, rewritten_reply, final_reply, sent=False, send_result=None, outcome_label="", live_context=None):
    init_runtime_state_db()
    sender = normalize_phone(payload.get("sender"))
    msg_id = str(payload.get("message_id") or "")
    provider_msg_id = ""
    if isinstance(send_result, dict):
        data = send_result.get("data") if isinstance(send_result.get("data"), dict) else {}
        provider_msg_id = str(data.get("msgId") or send_result.get("msgId") or "")
    con = sqlite3.connect(RUNTIME_STATE_DB_PATH)
    con.execute(
        """
        INSERT INTO AIOS_WhatsAppOutboundDecisions
            (created_ts, sender, message_id, relationship, intent, decision, reason_codes,
             original_reply, rewritten_reply, final_reply, retrieval_used, sent, provider_msg_id, outcome_label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _now_epoch(),
            sender,
            msg_id,
            str(payload.get("relationship") or payload.get("relationship_tag") or ""),
            str(payload.get("intent") or ""),
            decision_result.get("decision"),
            json.dumps(decision_result.get("reason_codes", []), ensure_ascii=False),
            str(original_reply or "")[:4000],
            str(rewritten_reply or "")[:4000],
            str(final_reply or "")[:4000],
            1 if payload.get("retrieval_used") else 0,
            1 if sent else 0,
            provider_msg_id,
            outcome_label,
        ),
    )
    con.commit()
    con.close()
    log_event(
        "outbound_controller_decision",
        sender=sender,
        message_id=msg_id,
        decision=decision_result.get("decision"),
        reason_codes=decision_result.get("reason_codes", []),
        relationship=payload.get("relationship"),
        relationship_tag=payload.get("relationship_tag"),
        intent=payload.get("intent"),
        retrieval_used=bool(payload.get("retrieval_used")),
        sent=bool(sent),
        msgId=provider_msg_id,
    )
    log_event(
        "crm_writeback",
        sender=sender,
        message_id=msg_id,
        outcome_label=outcome_label or ("sent_success" if sent else "drafted_or_blocked"),
        controller_decision=decision_result.get("decision"),
        reason_codes=decision_result.get("reason_codes", []),
        sent=bool(sent),
        msgId=provider_msg_id,
    )
    airtable_result = airtable_writeback_outbound(
        payload,
        decision_result,
        final_reply,
        sent=sent,
        send_result=send_result,
        outcome_label=outcome_label or ("sent_success" if sent else "drafted_or_blocked"),
        live_context=live_context,
    )
    log_event(
        "crm_writeback_airtable_result",
        sender=sender,
        message_id=msg_id,
        ok=bool(airtable_result.get("ok")),
        result=airtable_result,
    )


def update_outbound_state_after_decision(sender, message_id, final_reply, live_context, decision_result, sent=False):
    state = load_outbound_state(sender)
    current_id = str(message_id or "")
    if current_id and state.get("last_inbound_message_id") != current_id:
        state["last_inbound_message_id"] = current_id
        state["bot_reply_count_for_inbound"] = 0
    if sent:
        state["last_bot_reply_text"] = final_reply
        state["last_bot_reply_time"] = _now_epoch()
        state["bot_reply_count_for_inbound"] = int(state.get("bot_reply_count_for_inbound") or 0) + 1
        fp = _reply_fingerprint(final_reply)
        fingerprints = state.get("recent_reply_fingerprints") or []
        if fp:
            fingerprints.append(fp)
        state["recent_reply_fingerprints"] = fingerprints[-20:]
    state["last_intent"] = str((live_context or {}).get("intent", ""))
    proof = (live_context or {}).get("retrieval_proof", {}) if isinstance(live_context, dict) else {}
    state["last_retrieval_summary"] = json.dumps(
        {
            "source_used": proof.get("source_used"),
            "query_used": proof.get("query_used"),
            "match_found": proof.get("match_found"),
            "result_count": proof.get("result_count"),
        },
        ensure_ascii=False,
    )
    save_outbound_state(sender, state)


def load_relationship_store():
    global RELATIONSHIP_STORE
    if not os.path.exists(RELATIONSHIP_STORE_PATH):
        RELATIONSHIP_STORE = {}
        return
    try:
        with open(RELATIONSHIP_STORE_PATH, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        RELATIONSHIP_STORE = parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        RELATIONSHIP_STORE = {}
        log_event("relationship_store_load_error", error=str(exc))


def save_relationship_store():
    _ensure_parent_dir(RELATIONSHIP_STORE_PATH)
    with RELATIONSHIP_STORE_LOCK:
        tmp_path = f"{RELATIONSHIP_STORE_PATH}.{os.getpid()}.{time.time_ns()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(RELATIONSHIP_STORE, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, RELATIONSHIP_STORE_PATH)


def store_relationship(sender, relationship, contact_context, source):
    if not sender:
        return
    if sender in MANUAL_CONTACT_ALIASES and RELATIONSHIP_PRIORITY.get(MANUAL_CONTACT_ALIASES[sender]["relationship"], 0) >= RELATIONSHIP_PRIORITY.get(relationship, 0):
        current = RELATIONSHIP_STORE.get(sender, {})
        current.update(MANUAL_CONTACT_ALIASES[sender])
        current.update({"source": "manual_contact_alias", "locked": True, "updated_at_ms": now_ms()})
        RELATIONSHIP_STORE[sender] = current
        save_relationship_store()
        return
    current = RELATIONSHIP_STORE.get(sender, {})
    if current.get("relationship") and current.get("locked"):
        return
    current_relationship = current.get("relationship")
    if current_relationship and RELATIONSHIP_PRIORITY.get(current_relationship, 0) > RELATIONSHIP_PRIORITY.get(relationship, 0):
        return
    current.update(
        {
            "relationship": relationship,
            "source": source,
            "known_contact_name": contact_context.get("known_contact_name", ""),
            "known_chat": bool(contact_context.get("known_chat")),
            "updated_at_ms": now_ms(),
        }
    )
    RELATIONSHIP_STORE[sender] = current
    save_relationship_store()


def update_relationship_memory(sender, text, live_context):
    if not sender or not live_context:
        return
    current = RELATIONSHIP_STORE.get(sender, {})
    manual = MANUAL_CONTACT_ALIASES.get(sender)
    relationship_memory = live_context.get("personality", {}).get("relationship_memory", {})
    social_context = live_context.get("social_context", {})
    business_judgment = live_context.get("business_judgment", {})
    system_context = live_context.get("system_context", {}) if isinstance(live_context, dict) else {}
    identity_dna = system_context.get("identity_dna") or {}
    weather_context = system_context.get("weather") or {}
    persistence_meta = system_context.get("persistence_meta") or {}
    current.update(
        {
            "last_seen_ms": now_ms(),
            "preferred_language": relationship_memory.get("preferred_language", current.get("preferred_language", "")),
            "preferred_tone": relationship_memory.get("preferred_tone", current.get("preferred_tone", "")),
            "preferred_detail_level": relationship_memory.get("preferred_detail_level", current.get("preferred_detail_level", "")),
            "last_social_context": social_context.get("category", ""),
            "last_expected_next": business_judgment.get("expected_next", ""),
            "last_next_action": business_judgment.get("next_action", ""),
            "last_unresolved_topic": business_judgment.get("expected_next", ""),
            "latest_message_language": relationship_memory.get("latest_message_language", ""),
            "last_message_excerpt": str(text or "")[:160],
        }
    )
    if identity_dna or weather_context:
        current["persisted_system_context"] = {
            "identity_dna": identity_dna if isinstance(identity_dna, dict) else {},
            "weather": weather_context if isinstance(weather_context, dict) else {},
            "persistence_meta": {
                "identity_dna": persistence_meta.get("identity_dna", {}),
                "weather": persistence_meta.get("weather", {}),
            },
        }
    profile = live_context.get("contact_context", {}).get("special_contact_profile") or {}
    if profile.get("id"):
        current["special_contact_profile_id"] = profile["id"]
        current["special_contact_profile_role"] = profile.get("role", "")
        if profile["id"] == "hassan_kazzabel":
            current["special_profile_intro_sent"] = True
    if manual:
        current.update(manual)
        current["source"] = "manual_contact_alias"
        current["locked"] = True
    RELATIONSHIP_STORE[sender] = current
    save_relationship_store()


def keychain_secret(service):
    if sys.platform != "darwin":
        return ""
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", service, "-w"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def normalize_phone(value):
    if not value:
        return ""
    text = str(value)
    text = text.split("@", 1)[0]
    text = re.sub(r"\D+", "", text)
    return text


def normalize_outbound_whatsapp_target(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw_lower = raw.lower()
    if "@" in raw:
        return raw
    digits = normalize_phone(raw)
    if not digits:
        return raw

    return digits


def normalize_outbound_target_candidates(value):
    raw = str(value or "").strip()
    if not raw:
        return [""]
    if "@" in raw:
        normalized = raw.strip()
        digits = normalize_phone(normalized)
        if digits:
            candidates = [
                digits,
                f"{digits}@s.whatsapp.net",
                f"{digits}@c.us",
            ]
            if normalized not in candidates:
                candidates.append(normalized)
            return list(dict.fromkeys(candidates))
        return [normalized]
    digits = normalize_phone(raw)
    if not digits:
        return [raw]
    return [digits, f"{digits}@s.whatsapp.net", f"{digits}@c.us"]


def _coalesce(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("id", "jid", "phone", "phone_number", "from", "to", "sender", "chatId", "cleanedSenderPn", "user"):
            candidate = value.get(key)
            if candidate:
                return str(candidate).strip()
    text = str(value)
    return text.strip()


def _collect_sender_candidates(payload, data, msg, key):
    candidates = []
    add = candidates.append

    if isinstance(msg, dict):
        add(msg.get("from"))
        add(msg.get("to"))
        add(msg.get("sender"))
        add(msg.get("sender_jid"))
        add(msg.get("senderPn"))
        add(msg.get("chatId"))
        if isinstance(msg.get("key"), dict):
            inner_key = msg.get("key") or {}
            add(inner_key.get("remoteJid"))
            add(inner_key.get("chat"))
            add(inner_key.get("from"))

    if isinstance(payload, dict):
        add(payload.get("from"))
        add(payload.get("to"))
        add(payload.get("sender"))
        add(payload.get("chatId"))
        add(payload.get("phone"))
        add(payload.get("message_from"))
        source = payload.get("source")
        if isinstance(source, dict):
            add(source.get("sender"))
            add(source.get("phone"))
            add(source.get("jid"))
        sender_info = payload.get("sender_info")
        if isinstance(sender_info, dict):
            add(sender_info.get("jid"))
            add(sender_info.get("phone_number"))
        if isinstance(data, dict):
            add(dig(data, "sender", "jid"))
            add(dig(data, "sender", "phone"))
            add(dig(data, "session", "from"))
    if key and isinstance(key, dict):
        add(dig(key, "sender", "user"))
        add(dig(key, "sender", "jid"))
        add(dig(key, "remoteJid"))
        add(key.get("cleanedSenderPn"))
        add(key.get("from"))
        add(key.get("chat"))

    for value in candidates:
        normalized = _coalesce(value)
        if normalized:
            return normalized, candidates
    return "", candidates


def dig(obj, *path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def extract_payload(payload):
    data = payload.get("data") if isinstance(payload, dict) else {}
    msg = data.get("messages") if isinstance(data, dict) else None
    if isinstance(msg, list) and msg:
        msg = msg[0]
    if not isinstance(msg, dict):
        msg = data if isinstance(data, dict) else payload

    key = msg.get("key") if isinstance(msg, dict) else {}
    if not isinstance(key, dict):
        key = {}

    from_me = bool(
        msg.get("fromMe")
        or key.get("fromMe")
        or dig(payload, "data", "messages", "key", "fromMe")
    )

    sender, sender_candidates = _collect_sender_candidates(payload, data, msg, key)
    if not sender:
        sender = _coalesce(key.get("cleanedSenderPn")) or _coalesce(payload.get("From"))

    sender_digits = normalize_phone(sender)
    message_id = (
        key.get("id")
        or msg.get("messageId")
        or msg.get("id")
        or payload.get("messageId")
        or payload.get("id")
        or ""
    )

    text = (
        msg.get("messageBody")
        or msg.get("body")
        or dig(msg, "message", "conversation")
        or dig(msg, "message", "extendedTextMessage", "text")
        or payload.get("message")
        or payload.get("text")
        or payload.get("Body")
        or ""
    )
    text = str(text or "").strip()
    typing_signal = bool(
        msg.get("type") == "typing"
        or msg.get("isTyping") is True
        or msg.get("is_typing") is True
        or payload.get("event") == "typing"
        or payload.get("is_typing") is True
    )

    raw_jid = str(sender or "")
    sender_lower = raw_jid.lower()
    is_na_sender = sender_lower in {"na", "n/a", "none", "null", "unknown"}
    if "@g.us" in sender_lower:
        sender_quality = "group"
    elif sender_digits:
        sender_quality = "digit"
    elif sender_lower.startswith("@") or sender_lower.endswith("@lid"):
        sender_quality = "jid"
    elif is_na_sender:
        sender_quality = "na"
    elif raw_jid:
        sender_quality = "textual"
    else:
        sender_quality = "missing"

    ignored = (
        from_me
        or "@g.us" in raw_jid
        or "newsletter" in raw_jid.lower()
        or "broadcast" in raw_jid.lower()
        or not text
    )
    ignored_reason = ""
    if from_me:
        ignored_reason = "from_me"
    elif "@g.us" in raw_jid:
        ignored_reason = "group"
    elif "newsletter" in raw_jid.lower():
        ignored_reason = "newsletter"
    elif "broadcast" in raw_jid.lower():
        ignored_reason = "broadcast"
    elif not text:
        ignored_reason = "empty_message"

    if "@g.us" in raw_jid:
        reply_target = raw_jid
    elif raw_jid and "@" in raw_jid:
        reply_target = raw_jid
    elif sender_digits:
        # Wasender expects a WhatsApp JID for outbound messages.
        # Prefer direct digits-only fallback as <digits>@c.us to avoid 422 errors.
        reply_target = f"{sender_digits}@c.us"
    else:
        reply_target = raw_jid

    return {
        "from_me": from_me,
        "sender": sender_digits or sender,
        "reply_target": reply_target,
        "sender_digits": sender_digits,
        "sender_quality": sender_quality,
        "sender_candidates": sender_candidates[:12],
        "text": text,
        "is_user_typing": typing_signal,
        "message_id": str(message_id or ""),
        "ignored": ignored,
        "ignored_reason": ignored_reason,
        "raw_jid": raw_jid,
        "is_na_sender": is_na_sender,
    }


def _has_business_intent(text):
    lower = str(text or "").lower()
    return any(keyword in lower for keyword in BUSINESS_RELEVANCE_KEYWORDS)


def _has_noise_signal(text):
    lower = str(text or "").lower()
    return any(keyword in lower for keyword in NON_BUSINESS_NOISE_KEYWORDS)


def _is_pure_ack_or_greeting(text):
    lower = str(text or "").strip().lower()
    if lower in PURE_ACK_MESSAGES:
        return True
    return any(lower == token or lower.startswith(f"{token} ") for token in UNKNOWN_REPLY_TRIGGERS)


def _is_casual_only(text):
    lower = str(text or "").strip().lower()
    if not lower:
        return True
    return any(token in lower for token in CASUAL_ONLY_KEYWORDS) and not _has_business_intent(lower)


def _looks_like_followup_context_signal(message, state_session):
    if not message:
        return False
    lower = str(message).lower().strip()
    has_followup_keyword = any(word in lower for word in {"budget", "price", "area", "unit", "br", "studio", "bedroom", "1br", "2br", "3br"})
    has_numeric = any(ch.isdigit() for ch in lower)
    state = str(state_session.get("state", "") or "").upper() if state_session else ""
    if state in {"ACTIVE_CONTEXT", "CONTEXT_GATHERING", "DISCOVERY_RAPPORT", "PROPERTY_PIPELINE"}:
        return has_followup_keyword or has_numeric
    return False


def should_i_respond(message, sender_id, relationship_tag=None, is_user_typing=False, state_session=None):
    text = str(message or "").strip()
    lower = text.lower()
    relationship = str(relationship_tag or "").upper().strip()
    has_business_intent = _has_business_intent(lower)
    has_noise_signal = _has_noise_signal(lower)
    is_ack_or_greeting = _is_pure_ack_or_greeting(lower)
    token_count = len(re.findall(r"\S+", text))
    stored_memory = RELATIONSHIP_STORE.get(str(sender_id or ""), {})
    last_expected_next = str(stored_memory.get("last_expected_next", "") or "").strip()
    has_active_followup_signal = _looks_like_followup_context_signal(text, state_session)
    has_prior_context = bool(
        last_expected_next
        and last_expected_next not in {"", "none", "na", "n/a"}
    ) or has_active_followup_signal

    if is_user_typing:
        return False, "user_typing"

    if has_noise_signal:
        return False, "non_business_noise"

    if is_ack_or_greeting:
        return False, "casual_greeting_suppressed"

    if _is_casual_only(lower):
        return False, "casual_non_business_suppressed"

    if token_count < 3 and not has_business_intent:
        if has_prior_context and not is_ack_or_greeting:
            return True, "context_followup_allowed"
        return False, "short_non_business_message"

    if relationship in BUSINESS_RELEVANCE_RELATIONSHIPS:
        if has_business_intent:
            return True, "known_relationship_business_intent"
        if token_count >= MIN_KNOWN_BUSINESS_WORDS and relationship in {"CLIENT", "AGENT", "STAFF"}:
            return True, "known_relationship_contextual_business"
        return False, "known_relationship_no_business_intent"

    if has_business_intent:
        return True, "business_intent"

    if relationship in {"UNKNOWN", "NA", "N/A", "NONE"}:
        return False, "unknown_no_business_intent"

    return False, "unknown_no_business_intent"


def post_json(url, body, headers=None, timeout=60):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return e.code, parsed, raw


def dedupe_key(parsed):
    if parsed.get("message_id"):
        return f"id:{parsed['message_id']}"
    text_key = re.sub(r"\s+", " ", parsed.get("text", "")).strip().lower()
    return f"soft:{parsed.get('sender')}:{text_key}"


def is_duplicate(parsed):
    key = dedupe_key(parsed)
    now = time.time()
    expired = [k for k, seen_at in RECENT_INBOUND.items() if now - seen_at > DEDUP_WINDOW_SECONDS]
    for item in expired:
        RECENT_INBOUND.pop(item, None)
    if key in RECENT_INBOUND:
        return True, key
    RECENT_INBOUND[key] = now
    return False, key


def history_text(sender):
    merged = []
    for source_history in [db_history_text(sender), log_history_text(sender)]:
        if source_history and source_history != "No prior history":
            merged.extend(source_history.splitlines())
            break
    runtime_turns = [f"{turn['role']}: {turn['text']}" for turn in list(CONVERSATION_HISTORY[sender])[-HISTORY_LIMIT:]]
    merged.extend(runtime_turns)
    if not merged:
        stored = RELATIONSHIP_STORE.get(sender, {}) if sender else {}
        history_seed = str(stored.get("history_seed", "")).strip()
        if not history_seed:
            manual = MANUAL_CONTACT_ALIASES.get(sender, {}) if sender else {}
            history_seed = str(manual.get("history_seed", "")).strip()
        if history_seed:
            merged.extend(history_seed.splitlines())
    if not merged:
        return "No prior history"
    deduped = []
    for line in merged:
        if line and (not deduped or deduped[-1] != line):
            deduped.append(line)
    return "\n".join(deduped[-DB_HISTORY_LIMIT:])


def state_history_text(session):
    if not session:
        return "No prior history"
    if session.get("history_buffer"):
        lines = []
        for turn in session.get("history_buffer", [])[-STATE_HISTORY_LIMIT:]:
            role = str(turn.get("role", "user"))
            text = str(turn.get("text", "")).strip()
            if text:
                lines.append(f"{role}: {text}")
        if lines:
            return "\n".join(lines)
    if session.get("contact_record_exists"):
        return db_history_text(session.get("whatsapp_id"))
    return "No prior history"


def stored_contact_aliases(sender):
    stored = RELATIONSHIP_STORE.get(sender, {}) if sender else {}
    manual = MANUAL_CONTACT_ALIASES.get(sender, {}) if sender else {}
    aliases = []
    for value in (stored.get("jid_aliases", []) or []) + (manual.get("jid_aliases", []) or []):
        if value:
            aliases.append(str(value))
    for value in [stored.get("known_contact_name"), stored.get("desktop_chat_name"), manual.get("known_contact_name"), manual.get("desktop_chat_name")]:
        if value:
            aliases.append(str(value))
    return aliases


def find_chat_session(sender):
    if not sender or not os.path.exists(CHAT_DB_PATH):
        return None
    aliases = stored_contact_aliases(sender)
    try:
        con = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        clauses = [
            "replace(replace(replace(coalesce(ZCONTACTJID,''), '@s.whatsapp.net', ''), '@c.us', ''), '+', '') like ?",
            "coalesce(ZCONTACTJID,'') like ?",
        ]
        params = [f"%{sender[-9:]}%", f"%{sender}%"]
        for alias in aliases:
            alias_digits = normalize_phone(alias)
            if "@" in alias:
                clauses.append("coalesce(ZCONTACTJID,'') = ?")
                params.append(alias)
            elif alias_digits:
                clauses.append("replace(replace(replace(coalesce(ZCONTACTJID,''), '@s.whatsapp.net', ''), '@c.us', ''), '+', '') like ?")
                params.append(f"%{alias_digits[-9:]}%")
            else:
                clauses.append("lower(coalesce(ZPARTNERNAME,'')) = ?")
                params.append(alias.lower())
        row = con.execute(
            f"""
            select Z_PK, ZPARTNERNAME, ZCONTACTJID, ZMESSAGECOUNTER, ZLASTMESSAGETEXT
            from ZWACHATSESSION
            where {' or '.join(clauses)}
            order by ZLASTMESSAGEDATE desc
            limit 1
            """,
            params,
        ).fetchone()
        con.close()
        return dict(row) if row else None
    except Exception as exc:
        log_event("chat_session_lookup_error", sender=sender, aliases=aliases, error=str(exc))
        return None


def log_history_text(sender):
    if not sender or not os.path.exists(LOG_PATH):
        return "No prior history"
    try:
        selected = deque(maxlen=DB_HISTORY_LIMIT)
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                event = record.get("event")
                parsed = record.get("parsed") if isinstance(record.get("parsed"), dict) else {}
                if event == "inbound_received" and parsed.get("sender") == sender and parsed.get("text"):
                    selected.append({"role": "user", "text": str(parsed.get("text", "")).strip()})
                elif event == "openai_reply" and record.get("sender") == sender and record.get("reply"):
                    selected.append({"role": "assistant", "text": str(record.get("reply", "")).strip()})
    except Exception as exc:
        log_event("log_history_lookup_error", sender=sender, error=str(exc))
        return "No prior history"
    if not selected:
        return "No prior history"
    return "\n".join(f"{turn['role']}: {turn['text']}" for turn in selected if turn.get("text"))


def db_history_text(sender):
    if not sender or not os.path.exists(CHAT_DB_PATH):
        return "No prior history"
    try:
        con = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        session_row = find_chat_session(sender)
        if not session_row:
            con.close()
            return "No prior history"
        rows = con.execute(
            """
            select m.ZISFROMME as is_from_me, m.ZTEXT as text, m.ZMESSAGEDATE as message_date
            from ZWAMESSAGE m
            where m.ZCHATSESSION = ?
              and coalesce(m.ZTEXT, '') != ''
            order by m.ZMESSAGEDATE desc
            limit ?
            """,
            (session_row["Z_PK"], DB_HISTORY_LIMIT),
        ).fetchall()
        con.close()
    except Exception as exc:
        log_event("db_history_lookup_error", sender=sender, error=str(exc))
        return "No prior history"
    if not rows:
        return "No prior history"
    turns = []
    for row in reversed(rows):
        role = "assistant" if int(row["is_from_me"] or 0) else "user"
        text = str(row["text"] or "").strip()
        if text:
            turns.append(f"{role}: {text}")
    return "\n".join(turns) if turns else "No prior history"


def db_subject_summary(sender):
    session_row = find_chat_session(sender)
    if not session_row:
        return ""
    try:
        con = sqlite3.connect(f"file:{CHAT_DB_PATH}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            select ZTEXT as text
            from ZWAMESSAGE
            where ZCHATSESSION = ?
              and coalesce(ZTEXT, '') != ''
            order by ZMESSAGEDATE desc
            limit ?
            """,
            (session_row["Z_PK"], DB_SUBJECT_SCAN_LIMIT),
        ).fetchall()
        con.close()
    except Exception as exc:
        log_event("db_subject_lookup_error", sender=sender, error=str(exc))
        return ""
    blob = "\n".join(str(row["text"] or "") for row in rows)
    lower = blob.lower()
    topics = []
    if any(x in lower for x in ["nakheel", "onlineservices.nakheel", "palm", "نخيل"]):
        topics.append("Nakheel/Palm portal or NOC case")
    if any(x in lower for x in ["noc", "no objection"]):
        topics.append("NOC")
    if any(x in lower for x in ["customer number", "account access", "password", "login"]):
        topics.append("portal/account access")
    if any(x in lower for x in ["ضروري", "urgent"]):
        topics.append("urgent follow-up")
    if any(x in lower for x in ["modification", "تعديل"]):
        topics.append("modification")
    if not topics:
        return ""
    return "; ".join(dict.fromkeys(topics))


def remember(sender, role, text):
    if sender and text:
        CONVERSATION_HISTORY[sender].append({"role": role, "text": str(text).strip()})


def get_contact_context(sender):
    context = {
        "phone": sender,
        "known_contact_name": "",
        "known_chat": False,
        "runtime_history_turns": len(CONVERSATION_HISTORY[sender]),
    }
    manual = MANUAL_CONTACT_ALIASES.get(sender)
    if manual:
        context.update(
            {
                "known_contact_name": manual.get("known_contact_name", ""),
                "known_chat": bool(manual.get("known_chat")),
                "manual_contact_alias": True,
            }
        )
    if not sender or not os.path.exists(CHAT_DB_PATH):
        stored = RELATIONSHIP_STORE.get(sender, {}) if sender else {}
        if stored:
            context.update(
                {
                    "known_contact_name": stored.get("known_contact_name", ""),
                    "known_chat": bool(stored.get("known_chat")),
                    "relationship_memory_store": stored,
                    "old_chat_subject_summary": stored.get("old_chat_subject_summary", ""),
                }
            )
        if manual:
            context.update(
                {
                    "known_contact_name": manual.get("known_contact_name", context.get("known_contact_name", "")),
                    "known_chat": bool(manual.get("known_chat", context.get("known_chat"))),
                    "manual_contact_alias": True,
                    "old_chat_subject_summary": manual.get("old_chat_subject_summary", context.get("old_chat_subject_summary", "")),
                }
            )
        profile = special_contact_profile(context, sender)
        if profile:
            context["special_contact_profile"] = profile
        return context
    try:
        row = find_chat_session(sender)
        if row:
            context.update(
                {
                    "known_contact_name": row["ZPARTNERNAME"] or "",
                    "known_chat": True,
                    "message_counter": row["ZMESSAGECOUNTER"],
                    "last_message_excerpt": str(row["ZLASTMESSAGETEXT"] or "")[:180],
                    "old_chat_subject_summary": db_subject_summary(sender),
                }
            )
    except Exception as exc:
        context["contact_lookup_error"] = str(exc)
    stored = RELATIONSHIP_STORE.get(sender, {}) if sender else {}
    if stored and not context.get("known_chat"):
        context.update(
            {
                "known_contact_name": stored.get("known_contact_name", ""),
                "known_chat": bool(stored.get("known_chat")),
            }
        )
    if manual:
        context.update(
            {
                "known_contact_name": manual.get("known_contact_name", context.get("known_contact_name", "")),
                "known_chat": True,
                "manual_contact_alias": True,
                "old_chat_subject_summary": manual.get("old_chat_subject_summary", context.get("old_chat_subject_summary", "")),
            }
        )
    profile = special_contact_profile(context, sender)
    if profile:
        context["special_contact_profile"] = profile
    return context


def relationship_detection(sender, text, contact_context, policy_decision):
    if sender in MANUAL_CONTACT_ALIASES:
        return MANUAL_CONTACT_ALIASES[sender]["relationship"], "manual_contact_alias"
    profile = contact_context.get("special_contact_profile") or special_contact_profile(contact_context, sender)
    if profile.get("relationship"):
        return profile["relationship"], "special_contact_profile"
    stored = RELATIONSHIP_STORE.get(sender, {}) if sender else {}
    sender_type = policy_decision.sender_type
    lower_blob = json.dumps(contact_context, ensure_ascii=False).lower() + " " + (text or "").lower()
    agent_signals = [
        "agent",
        "broker",
        "real estate",
        "properties",
        "propertys",
        "listings",
        "inquiries",
        "dxb group",
        "broker group",
        "agent group",
        "secondary group",
        "xp property",
        "aron and trisl",
        "trisl",
        "بروكر",
        "وسيط",
    ]
    if sender_type == "Omar":
        candidate = ("Omar", "policy")
    elif sender_type == "Trusted Partner":
        candidate = ("Trusted Partner", "policy")
    elif sender_type == "HSH Staff":
        candidate = ("Staff", "policy")
    elif any(token in lower_blob for token in ["hsh team", "hsh staff", "team tasks", "internal task", "staff", "الفريق"]):
        candidate = ("Staff", "staff_text")
    elif sender_type == "Agent" or any(token in lower_blob for token in agent_signals):
        candidate = ("Agent", "policy_or_text")
    elif any(token in lower_blob for token in ["friend", "brother", "boss", "حبيبي", "يا ملك", "الغالي"]):
        candidate = ("Friend", "relationship_language")
    elif any(token in lower_blob for token in ["client", "buyer", "seller", "tenant", "landlord", "عميل", "باير", "سيلر", "مستأجر"]):
        candidate = ("Existing Client" if contact_context.get("known_chat") else "New Client", "business_language")
    elif contact_context.get("known_chat") and contact_context.get("known_contact_name"):
        candidate = ("Existing Client", "known_chat")
    elif sender:
        candidate = ("New Client", "new_sender")
    else:
        candidate = ("Unknown", "missing_sender")

    stored_relationship = stored.get("relationship")
    if stored_relationship and RELATIONSHIP_PRIORITY.get(stored_relationship, 0) >= RELATIONSHIP_PRIORITY.get(candidate[0], 0):
        return stored_relationship, "stored"
    return candidate


def build_live_response_context(
    text,
    sender,
    state_session=None,
    seeded_relationship_tag=None,
    seeded_relationship_source=None,
    system_context=None,
):
    if state_session is None:
        state_session = {}
    use_state_history = bool(state_session and state_session.get("contact_record_exists"))
    history = state_history_text(state_session) if use_state_history else history_text(sender)
    if not history or history == "No prior history":
        history = history_text(sender)
    contact_context = get_contact_context(sender)
    stored_memory = RELATIONSHIP_STORE.get(sender, {}) if sender else {}
    if stored_memory:
        contact_context["relationship_memory_store"] = {
            "last_expected_next": stored_memory.get("last_expected_next", ""),
            "last_next_action": stored_memory.get("last_next_action", ""),
            "last_unresolved_topic": stored_memory.get("last_unresolved_topic", ""),
            "preferred_language": stored_memory.get("preferred_language", ""),
            "preferred_tone": stored_memory.get("preferred_tone", ""),
            "preferred_detail_level": stored_memory.get("preferred_detail_level", ""),
            "last_message_excerpt": stored_memory.get("last_message_excerpt", ""),
        }
    # Relationship classifier is intentionally executed before downstream policy/intent branching.
    relationship_tag, relationship_tag_source = seeded_relationship_tag, seeded_relationship_source
    if not relationship_tag:
        relationship_tag, relationship_tag_source = relationship_classifier_node(sender, text, contact_context)
    contact_context["relationship_tag"] = relationship_tag
    contact_context["relationship_tag_source"] = relationship_tag_source

    social_context = detect_social_context(text, history)
    latest_language = resolve_live_language(text, stored_memory=stored_memory, history=history)
    policy_decision = evaluate_response_policy(
        event={
            "from_phone": sender,
            "profile_name": contact_context.get("known_contact_name", ""),
        },
        message_text=text,
        context=contact_context,
    )
    relationship, relationship_source = relationship_detection(sender, text, contact_context, policy_decision)
    store_relationship(sender, relationship, contact_context, relationship_source)
    conversation_objective = detect_conversation_objective(text, history, relationship)
    relationship = CANONICAL_RELATIONSHIP_MAP.get(relationship, relationship)
    if relationship not in RELATIONSHIP_TAGS:
        relationship = relationship_tag
    intent = detect_intent(text, history, conversation_objective)
    psych_profile = detect_psych_profile(text, sender=sender, session=state_session, live_context={"conversation_objective": conversation_objective, "intent": intent})
    state_session["last_urgency"] = psych_profile.get("urgency", "")
    state_session["last_ego_style"] = psych_profile.get("ego_style", "")
    state_session["last_sender_text"] = str(text)
    personality_context = build_personality_context(
        text,
        history=history,
        sender_type=policy_decision.sender_type,
        relationship=relationship,
        contact_context=contact_context,
    )
    business_judgment = personality_context.get("business_judgment", {})
    relationship_memory = personality_context.get("relationship_memory", {})
    full_history_summary = _history_summary(history, limit=10)
    profile_summary = _profile_summary(relationship_tag, relationship, contact_context, relationship_memory, business_judgment)
    area_fact_sheet = _normalize_area_fact_sheet(load_area_fact_sheet()) if conversation_objective in {"property_inquiry", "active_deal"} or intent in {"property", "sensitive"} else {}
    area_fact_sheet_match = _match_area_fact_sheet(text) if area_fact_sheet else {}
    identity_context = identity_context_to_contract(
        build_human_identity_context(
            sender=sender or "",
            text=str(text),
            relationship=relationship,
            profile_summary=profile_summary,
            conversation_objective=conversation_objective,
            intent=intent,
            history_text=history,
            data_root=str(DATA_DIR),
            stored_memory=stored_memory,
        )
    )
    live_context = {
        "conversation_history": history,
        "full_history_summary": full_history_summary,
        "profile_summary": profile_summary,
        "human_identity": identity_context,
        "contact_context": contact_context,
        "relationship_tag": relationship_tag,
        "relationship": relationship,
        "relationship_source": relationship_source,
        "conversation_objective": conversation_objective,
        "intent": intent,
        "latest_message_language": latest_language,
        "social_context": social_context,
        "business_judgment": business_judgment,
        "relationship_memory": relationship_memory,
        "stored_memory": stored_memory,
        "permission": asdict(policy_decision),
        "personality": personality_context,
        "reply_contract": {
            "no_generic_openai": True,
            "no_fallback_reply": True,
            "no_answer_without_retrieval": True,
            "must_sound_like_omar": True,
            "knowledge_should_feel_like_aios": True,
            "must_match_expected_next": True,
        },
        "psych_profile": psych_profile,
        "area_fact_sheet": area_fact_sheet,
        "area_fact_sheet_match": area_fact_sheet_match,
    }
    live_context["retrieval_proof"] = build_retrieval_proof(text, live_context)
    live_context["knowledge_probe"] = build_knowledge_probe(text, live_context)
    return context_merge(live_context, system_context=system_context)


def format_live_prompt(text, live_context):
    identity_dna_label = live_context.get("identity_dna_label") or _identity_dna_label(live_context.get("system_context")) or "Assistant"
    relationship_tag = live_context.get("relationship_tag") or live_context.get("relationship")
    profile_summary = live_context.get("profile_summary") or {}
    full_history_summary = live_context.get("full_history_summary") or "No prior history"
    area_fact_sheet = live_context.get("area_fact_sheet") or {}
    return (
        "AIOS LIVE WHATSAPP RESPONSE CONTRACT\n"
        "Every inbound WhatsApp reply must pass through: MESSAGE -> Conversation History -> "
        "Conversation Objective Detection -> Relationship Detection -> Social Context Detection -> "
        "Intent Detection -> Permission Layer -> Knowledge Retrieval -> "
        "Omar Personality Engine -> Safe Reply Generation.\n"
        f"ACT AS: {identity_dna_label}.\n"
        "MANDATE: You are not a general assistant. You are an expert focused on ROI, Dubai real estate, and high-value investment. "
        "If the user asks for data (availability, price list), pull it from the context. "
        "If the user is vague, push for the ROI-focused objective. "
        "Do NOT reply to small talk, personal messages, or casual greetings unless this thread is already known as a relationship context (Friend/Family/Client/Agent/Staff).\n"
        "If relationship is UNKNOWN and message is casual or short with no business objective, stay silent.\n"
        "Do not say 'I will check', 'I will verify', or 'I need to escalate' unless an actual workflow was executed and logged.\n"
        f"You are {relationship_tag}. "
        f"Speak accordingly. Do not be overly formal if the tag is FRIEND/FAMILY. "
        f"Do not be overly casual if the tag is CLIENT/AGENT.\n"
        "Golden rule: understand what conversation is happening before deciding whether property mode applies. "
        "Property mode must never activate for casual greetings, friend chat, jokes, corrections, or staff identity messages. "
        "Allowed relationship tags are: CLIENT, AGENT, STAFF, FRIEND, FAMILY, UNKNOWN.\n"
        "No generic chatbot replies. No repeated welcome unless user greeted first. "
        "No repeated greeting loops. Reply language MUST equal latest_message_language. "
        "If latest_message_language is English, reply English. If Arabic, reply Arabic. If German, reply German. "
        "If Russian, reply Russian. Switch immediately when the user switches language. "
        "Use short natural Arabic/Gulf/Levant style when Arabic. "
        "MEMORY_INJECTION:\n"
        f"RELATIONSHIP_TAG: {relationship_tag}\n"
        f"PROFILE_SUMMARY: {json.dumps(profile_summary, ensure_ascii=False)}\n"
        f"LAST_10_MESSAGE_SUMMARY: {full_history_summary}\n"
        f"HUMAN_IDENTITY_CONTEXT: {json.dumps(live_context.get('human_identity', {}), ensure_ascii=False)}\n"
        "Use the injected profile summary and last 10 message summary before the newest user message. "
        "Knowledge-first rule: before asking any question, decide whether AIOS already knows the answer, unit, "
        "project, document, or inventory. Use knowledge_probe as proof of what was checked: memory, conversation "
        "history, Knowledge Vault, documents, and Property Database. If knowledge_probe.known_answer is true, "
        "answer with the known details or next action first. Do not ask what they want to know when they already "
        "named a unit/project/document. Do not restart discovery. "
        "If area facts exist in area_fact_sheet, use them before property answers. Do not invent unit types or "
        "availability that conflict with the fact sheet. "
        "No answer without retrieval: for any data-bearing request, retrieval_proof.required must be true, "
        "retrieval_proof.executed must be true, and retrieval_proof.match_found must decide the answer. "
        "If match_found is false for a data-bearing request, do not use generic apology text.\n"
        "Instead use a short context-bridging follow-up message and request the needed scope.\n"
        "Do not say I will check, I will verify, I will escalate, or I will update you unless an actual workflow "
        "was executed and logged. Human style comes after retrieval proof, not before. "
        "Only if conversation_objective is property_inquiry or active_deal should real estate qualification/search run. "
        "If enough property information exists, do not ask more questions: search, recommend, compare, or act. "
        "Use business_judgment.expected_next as the main instruction for what the person expects next. "
        "Use relationship_memory and stored_memory to continue last unresolved topic and last requested action. "
        "If social_context says correction, emoji reaction, joke, teasing, sarcasm, frustration, urgency, or misunderstanding, "
        "do not treat the message as a property inquiry. "
        "Behave like an experienced broker: recommend, push toward viewing, send options, and move to closing when appropriate. "
        "Apply the permission.retrieval_filter exactly. For Omar or Trusted Partner full-access senders, "
        "private/owner/internal retrieval is approved. For everyone else, never expose restricted data; "
        "if restricted data is requested, politely refuse and redirect.\n"
        "No automatic human handoff during normal conversation.\n\n"
        f"AREA_FACT_SHEET:\n{json.dumps(area_fact_sheet, ensure_ascii=False)}\n\n"
        f"LIVE_CONTEXT_JSON:\n{json.dumps(live_context, ensure_ascii=False)}\n\n"
        f"LATEST_MESSAGE:\n{text}"
    )


def is_generic_or_fallback_reply(reply):
    lowered = (reply or "").strip().lower()
    generic_patterns = [
        "hello, how can i help you",
        "how can i assist you",
        "i am an ai",
        "as an ai",
    ]
    return any(pattern in lowered for pattern in generic_patterns)


def compact_terms(text, limit=8):
    cleaned = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", (text or "").lower())
    stop = {
        "the",
        "and",
        "for",
        "you",
        "me",
        "please",
        "pls",
        "tell",
        "send",
        "show",
        "find",
        "need",
        "want",
        "details",
        "detail",
        "what",
        "where",
        "how",
        "ممكن",
        "ابغى",
        "اريد",
        "شو",
        "كيف",
    }
    terms = []
    for token in cleaned.split():
        if token in stop:
            continue
        if len(token) < 3 and not token.isdigit():
            continue
        terms.append(token)
    return terms[:limit]


def text_contains_terms(blob, terms):
    lower = (blob or "").lower()
    return all(term in lower for term in terms if term)


def search_knowledge_files(text, limit=5):
    terms = compact_terms(text, limit=6)
    if not terms:
        return []
    hits = []
    allowed_ext = {".md", ".txt", ".csv", ".json", ".xlsx", ".pdf", ".docx"}
    for root in KNOWLEDGE_SEARCH_ROOTS:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"Raw", "__pycache__"}]
            for filename in filenames:
                if len(hits) >= limit:
                    return hits
                ext = os.path.splitext(filename)[1].lower()
                if ext not in allowed_ext:
                    continue
                path = os.path.join(dirpath, filename)
                haystack = f"{filename} {path}"
                matched = any(term in haystack.lower() for term in terms)
                preview = ""
                if not matched and ext in {".md", ".txt", ".csv", ".json"}:
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            preview = f.read(12000)
                        matched = any(term in preview.lower() for term in terms)
                    except Exception:
                        preview = ""
                if matched:
                    hits.append(
                        {
                            "name": filename,
                            "path": path,
                            "type": ext.lstrip("."),
                            "preview": re.sub(r"\s+", " ", preview[:240]).strip() if preview else "",
                        }
                    )
    return hits


def retrieval_tokens(text, limit=10):
    cleaned = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", (text or "").lower())
    stop = {
        "who",
        "owns",
        "owner",
        "ownership",
        "tell",
        "me",
        "details",
        "detail",
        "of",
        "the",
        "unit",
        "units",
        "property",
        "properties",
        "building",
        "please",
        "pls",
        "find",
        "search",
        "show",
        "give",
        "price",
        "what",
        "where",
        "how",
        "هل",
        "من",
        "ما",
        "شو",
        "تفاصيل",
        "وحدة",
        "مالك",
    }
    tokens = []
    for token in cleaned.split():
        if token in stop:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens[:limit]


def explicit_retrieval_signal(text, decision, live_context):
    lower = (text or "").lower()
    if decision.retrieval_intent != "property_lookup":
        return True
    if decision.confidence > 0.62:
        return True
    if live_context.get("conversation_objective") in {
        "property_inquiry",
        "active_deal",
        "document_request",
        "complaint",
        "negotiation",
    }:
        return True
    if has_enough_property_info(text) or direct_inventory_lookup_signal(text):
        return True
    hard_signals = [
        "unit",
        "building",
        "tower",
        "project",
        "developer",
        "price",
        "availability",
        "inventory",
        "owner",
        "owns",
        "document",
        "contract",
        "noc",
        "dld",
        "rera",
        "mortgage",
        "visa",
        "وحدة",
        "مشروع",
        "مالك",
        "سعر",
        "متوفر",
    ]
    return any(signal in lower for signal in hard_signals)


def retrieval_required(text, live_context, decision):
    objective = live_context.get("conversation_objective")
    social = live_context.get("social_context", {}).get("category")
    if social in {"correction", "emoji_reaction", "banter", "sarcasm", "misunderstanding"}:
        return False
    if objective in {"casual_greeting", "friend_chat", "joke", "correction"}:
        return False
    if not explicit_retrieval_signal(text, decision, live_context):
        return False
    if decision.retrieval_intent in {
        "ownership_lookup",
        "property_lookup",
        "inventory_lookup",
        "document_lookup",
        "operations_lookup",
        "followup_lookup",
        "contact_lookup",
        "project_lookup",
        "developer_lookup",
    }:
        return True
    return False


def property_retrieval_proof_rows(text, retrieval_intent, limit=5):
    lower_text = (text or "").lower()
    tokens = retrieval_tokens(text)
    if not tokens:
        return []
    numeric_tokens = [t for t in tokens if t.isdigit()]
    word_tokens = [t for t in tokens if not t.isdigit()]
    clauses = []
    params = []
    exact_phrases = []
    if "dec tower" in lower_text or "dec towers" in lower_text or "d.e.c" in lower_text:
        exact_phrases.extend(["dec tower", "dec towers", "d.e.c"])
        word_tokens = [t for t in word_tokens if t not in {"dec", "tower", "towers"}]
    phrase_match = re.search(r"\b(?:project|building|tower)\s+([a-z0-9][a-z0-9 ]{2,40})", lower_text)
    if phrase_match:
        exact_phrases.append(phrase_match.group(1).strip())
    for phrase in dict.fromkeys(exact_phrases):
        clauses.append(
            "(lower(coalesce(p.name,'')) LIKE ? OR lower(coalesce(f.file_name,'')) LIKE ? OR lower(ir.raw_json) LIKE ?)"
        )
        params.extend([f"%{phrase}%"] * 3)
    if numeric_tokens and retrieval_intent in {"ownership_lookup", "inventory_lookup", "property_lookup"}:
        unit_clauses = []
        for token in numeric_tokens[:3]:
            unit_clauses.append("(coalesce(ir.unit_ref,'') LIKE ? OR ir.raw_json LIKE ?)")
            params.extend([f"%{token}%", f"%{token}%"])
        clauses.append("(" + " OR ".join(unit_clauses) + ")")
    for token in word_tokens[:5]:
        clauses.append(
            "(lower(coalesce(p.name,'')) LIKE ? OR lower(coalesce(a.name,'')) LIKE ? OR "
            "lower(coalesce(d.name,'')) LIKE ? OR lower(coalesce(pt.name,'')) LIKE ? OR "
            "lower(coalesce(f.file_name,'')) LIKE ? OR lower(ir.raw_json) LIKE ?)"
        )
        params.extend([f"%{token}%"] * 6)
    if not clauses:
        return []
    sql = f"""
        SELECT
            ir.inventory_row_id,
            ir.raw_json,
            ir.unit_ref,
            ir.bedrooms,
            ir.price,
            ir.status,
            ir.inventory_type,
            IFNULL(p.name, '') AS project_name,
            IFNULL(a.name, '') AS area_name,
            IFNULL(d.name, '') AS developer_name,
            IFNULL(pt.name, '') AS property_type_name,
            IFNULL(f.file_name, '') AS file_name,
            IFNULL(f.source_group, '') AS source_group,
            ir.sheet_name,
            ir.row_number
        FROM inventory_rows ir
        LEFT JOIN projects p ON ir.project_id = p.project_id
        LEFT JOIN areas a ON ir.area_id = a.area_id
        LEFT JOIN developers d ON ir.developer_id = d.developer_id
        LEFT JOIN property_types pt ON ir.property_type_id = pt.property_type_id
        LEFT JOIN inventory_files f ON ir.source_id = f.source_id
        WHERE {" AND ".join(clauses)}
        LIMIT {int(limit)}
    """
    try:
        con = sqlite3.connect(f"file:{PROPERTY_DB_PATH}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        return [dict(row) for row in rows]
    except Exception as exc:
        log_event("retrieval_property_query_error", error=str(exc), tokens=tokens, intent=retrieval_intent)
        return []


def build_retrieval_proof(text, live_context):
    decision = classify_retrieval_intent(text)
    proof = {
        "engine": "HYBRID_RETRIEVAL_INTELLIGENCE_V2",
        "retrieval_intent": decision.retrieval_intent,
        "route": decision.route,
        "source_used": decision.target,
        "query_used": text,
        "required": retrieval_required(text, live_context, decision),
        "executed": False,
        "match_found": False,
        "result_count": 0,
        "matches": [],
        "vector_matches": [],
        "hybrid_confidence": 0.0,
        "confidence": decision.confidence,
    }
    if not proof["required"]:
        proof.update(
            {
                "source_used": "Conversation History + Relationship Memory",
                "executed": True,
                "match_found": True,
                "result_count": 1,
                "matches": [{"type": "conversation_context", "history_loaded": live_context.get("conversation_history") != "No prior history"}],
            }
        )
        return proof

    hybrid_payload = {}
    try:
        hybrid_result = HybridRetriever().retrieve(text, limit=5)
        hybrid_payload = asdict(hybrid_result)
        proof["vector_matches"] = [
            row for row in hybrid_payload.get("merged_data", []) if row.get("type") == "semantic_chunk"
        ][:5]
        proof["hybrid_confidence"] = hybrid_payload.get("system_confidence_score", 0.0)
    except Exception as exc:
        proof["hybrid_error"] = str(exc)

    if decision.retrieval_intent in {"ownership_lookup", "inventory_lookup", "property_lookup", "project_lookup", "developer_lookup"}:
        rows = property_retrieval_proof_rows(text, decision.retrieval_intent, limit=5)
        if decision.retrieval_intent == "ownership_lookup" and not rows:
            proof.update({"executed": True, "match_found": False, "result_count": 0, "matches": []})
            return proof
        if not rows and hybrid_payload.get("merged_data"):
            semantic_rows = [
                row for row in hybrid_payload.get("merged_data", []) if row.get("type") == "semantic_chunk"
            ]
            proof.update(
                {
                    "executed": True,
                    "match_found": bool(semantic_rows),
                    "result_count": len(semantic_rows),
                    "matches": semantic_rows[:5],
                    "source_used": "HybridRetriever(SQLite + ChromaDB)",
                }
            )
            return proof
        proof.update({"executed": True, "match_found": bool(rows), "result_count": len(rows), "matches": rows})
        return proof

    if decision.retrieval_intent in {"document_lookup", "operations_lookup"}:
        hits = proof.get("vector_matches") or search_knowledge_files(text, limit=5)
        proof.update({"executed": True, "match_found": bool(hits), "result_count": len(hits), "matches": hits})
        return proof

    if decision.retrieval_intent in {"contact_lookup", "followup_lookup"}:
        history = live_context.get("conversation_history") or ""
        memory = live_context.get("stored_memory") or {}
        terms = retrieval_tokens(text, limit=5)
        matched = bool((terms and text_contains_terms(history, terms[:2])) or memory)
        proof.update(
            {
                "executed": True,
                "match_found": matched,
                "result_count": 1 if matched else 0,
                "matches": [{"type": decision.retrieval_intent, "history_loaded": history != "No prior history", "memory_loaded": bool(memory)}] if matched else [],
            }
        )
        return proof

    proof["executed"] = True
    return proof


def build_knowledge_probe(text, live_context):
    """Lightweight proof that AIOS checked known context before asking."""
    retrieval_proof = live_context.get("retrieval_proof", {})
    history = live_context.get("conversation_history") or ""
    stored = live_context.get("stored_memory") or {}
    objective = live_context.get("conversation_objective")
    intent = live_context.get("intent")
    terms = compact_terms(text)
    history_hit = bool(terms and text_contains_terms(history, terms[:3]))
    memory_blob = json.dumps(stored, ensure_ascii=False)
    memory_hit = bool(terms and text_contains_terms(memory_blob, terms[:3]))

    document_signal = objective == "document_request" or intent == "sensitive" and any(
        x in (text or "").lower() for x in ["document", "docs", "contract", "mou", "title deed", "noc", "pdf", "ملف", "عقد"]
    )
    process_signal = any(
        x in (text or "").lower()
        for x in ["noc", "dld", "rera", "transfer", "mortgage", "visa", "oqood", "trakheesi", "نقل", "رهن", "تسجيل"]
    )
    knowledge_hits = search_knowledge_files(text, limit=5) if document_signal or process_signal else []

    property_checked = inventory_knowledge_signal(text, live_context)
    direct_inventory_known = bool(direct_inventory_lookup_signal(text) and direct_inventory_rows(text, limit=1))

    known_answer = bool(
        retrieval_proof.get("match_found")
        or history_hit
        or memory_hit
        or knowledge_hits
        or direct_inventory_known
        or has_enough_property_info(text)
    )
    return {
        "engine": "KNOWLEDGE_FIRST_ENGINE_V1",
        "retrieval_proof": {
            "source_used": retrieval_proof.get("source_used"),
            "query_used": retrieval_proof.get("query_used"),
            "match_found": retrieval_proof.get("match_found"),
            "retrieval_intent": retrieval_proof.get("retrieval_intent"),
        },
        "searched": {
            "memory": True,
            "conversation_history": True,
            "knowledge_vault": bool(document_signal or process_signal),
            "documents": bool(document_signal),
            "property_database": bool(property_checked),
        },
        "known_answer": known_answer,
        "history_hit": history_hit,
        "memory_hit": memory_hit,
        "document_hits": knowledge_hits[:5],
        "property_database_checked": bool(property_checked),
        "direct_inventory_known": direct_inventory_known,
        "rule": "If known_answer is true, answer first and do not ask a qualification question.",
    }


def _proof_match_summary(match, permission=None):
    if not isinstance(match, dict):
        return ""
    permission = permission or {}
    restricted_owner = bool(permission.get("retrieval_filter", {}).get("exclude_owner_details"))
    inventory_type = str(match.get("inventory_type") or "").lower()
    parts = []
    for key, label in [
        ("project_name", "Project"),
        ("area_name", "Area"),
        ("developer_name", "Developer"),
        ("property_type_name", "Type"),
        ("unit_ref", "Unit"),
        ("price", "Price"),
        ("status", "Status"),
        ("file_name", "Source"),
    ]:
        if restricted_owner and key == "unit_ref" and "owner" in inventory_type:
            continue
        value = str(match.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    return " | ".join(parts[:8])


def data_retrieval_reply(text, live_context):
    proof = live_context.get("retrieval_proof", {})
    if not proof.get("required") or not proof.get("executed") or not proof.get("match_found"):
        return ""
    retrieval_intent = proof.get("retrieval_intent")
    matches = proof.get("matches") or []
    permission = live_context.get("permission", {})
    language = live_context.get("latest_message_language") or detect_language(text)

    if retrieval_intent == "ownership_lookup":
        first = matches[0] if matches else {}
        source = first.get("file_name", proof.get("source_used", "")) if isinstance(first, dict) else proof.get("source_used", "")
        owner_allowed = permission.get("sender_type") in {"Omar", "Trusted Partner"} or live_context.get("relationship") == "Trusted Partner"
        if permission.get("retrieval_filter", {}).get("exclude_owner_details") or not owner_allowed:
            if language == "arabic":
                return f"لقيت السجل، لكن بيانات المالك خاصة وما أقدر أشاركها هنا. المصدر: {source}"
            return f"Record found, but owner details are restricted and cannot be shared here. Source: {source}"
        raw = first.get("raw_json", "") if isinstance(first, dict) else ""
        if raw:
            try:
                parsed = json.loads(raw)
                raw_items = parsed.get("raw") if isinstance(parsed, dict) else None
                if raw_items:
                    return "Record found:\n" + json.dumps(raw_items, ensure_ascii=False)
            except Exception:
                pass
        return "Record found:\n" + (_proof_match_summary(first, permission) or str(first))

    if retrieval_intent in {"inventory_lookup", "property_lookup", "project_lookup", "developer_lookup"}:
        lines = [_proof_match_summary(match, permission) for match in matches[:5]]
        lines = [line for line in lines if line]
        if not lines:
            return ""
        if language == "arabic":
            return "لقيت هذه النتائج المؤكدة:\n- " + "\n- ".join(lines[:3])
        return "Found this in inventory:\n- " + "\n- ".join(lines[:3])

    if retrieval_intent in {"document_lookup", "operations_lookup"}:
        names = [m.get("name") or m.get("path") for m in matches[:5] if isinstance(m, dict)]
        names = [name for name in names if name]
        if not names:
            return ""
        if language == "arabic":
            return "لقيت عندي:\n- " + "\n- ".join(names[:3])
        return "Found:\n- " + "\n- ".join(names[:3])

    return ""


def has_enough_property_info(text):
    lower = (text or "").lower()
    has_area = any(area in lower for area in ["jvc", "yas", "saadiyat", "reem", "marina", "downtown", "business bay", "jumeirah"])
    has_type = (
        any(kind in lower for kind in ["studio", "bedroom", "villa", "apartment", "plot", "unit", "property", "properties", "propertys", "شقة", "فيلا", "غرفة"])
        or bool(re.search(r"\b[1-9]\s*br\b|\b[1-9]br\b|\bbr\b", lower))
    )
    has_budget = bool(re.search(r"\b\d+\s*(k|m|million|مليون|الف|ألف)?\b", lower))
    return has_area and has_type and has_budget


def money(value):
    if value is None:
        return ""
    try:
        return f"AED {int(value):,}"
    except Exception:
        return str(value)


def safe_inventory_price(payload, inventory_type):
    raw_price = inferred_price(payload, inventory_type)
    if raw_price and 100_000 <= int(raw_price) <= 100_000_000:
        return raw_price
    candidates = []
    raw = payload.get("raw")
    if isinstance(raw, list):
        for item in raw:
            try:
                num = int(float(str(item).replace(",", "").replace("AED", "").strip()))
            except Exception:
                continue
            if 100_000 <= num <= 100_000_000:
                candidates.append(num)
    return max(candidates) if candidates else None


def knowledge_query_tokens(text):
    lower = (text or "").lower()
    cleaned = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", lower)
    stop = {
        "tell",
        "me",
        "details",
        "detail",
        "of",
        "the",
        "unit",
        "property",
        "price",
        "photos",
        "photo",
        "current",
        "asking",
        "send",
        "what",
        "have",
        "you",
        "for",
        "about",
        "please",
        "pls",
    }
    tokens = []
    for token in cleaned.split():
        if token in stop:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens[:8]


def inventory_knowledge_signal(text, live_context):
    lower = (text or "").lower()
    objective = live_context.get("conversation_objective")
    social = live_context.get("social_context", {}).get("category")
    if objective in {"casual_greeting", "friend_chat", "joke", "correction"}:
        return False
    if social in {"identity_intro", "correction", "emoji_reaction", "banter", "sarcasm", "misunderstanding"}:
        return False
    direct_inventory_words = [
        "unit",
        "inventory",
        "availability",
        "price",
        "asking",
        "details of",
        "photos",
        "brochure",
        "payment plan",
    ]
    project_words = [
        "anwa",
        "creek harbour",
        "yas",
        "saadiyat",
        "jvc",
        "downtown",
        "business bay",
        "maritime city",
        "tiger",
        "eleven",
        "emaar",
        "nakheel",
        "aldar",
        "sobha",
    ]
    direct_unit_or_project = direct_inventory_lookup_signal(text)
    return direct_unit_or_project or has_enough_property_info(text)


def direct_inventory_lookup_signal(text):
    lower = (text or "").lower()
    direct_inventory_words = [
        "unit",
        "inventory",
        "availability",
        "price",
        "asking",
        "details of",
        "photos",
        "brochure",
        "payment plan",
    ]
    project_words = [
        "anwa",
        "creek harbour",
        "yas",
        "saadiyat",
        "jvc",
        "downtown",
        "business bay",
        "maritime city",
        "tiger",
        "eleven",
        "emaar",
        "nakheel",
        "aldar",
        "sobha",
    ]
    return (
        (any(x in lower for x in direct_inventory_words) and any(x in lower for x in project_words))
        or bool(re.search(r"\bunit\s*[a-z0-9-]*\s*\d+\b|\b\d{2,5}\s+[a-z][a-z0-9-]+\b", lower))
    )


def direct_inventory_rows(text, limit=5):
    tokens = knowledge_query_tokens(text)
    if not tokens:
        return []
    clauses = []
    params = []
    for token in tokens:
        clauses.append("lower(ir.raw_json) LIKE ?")
        params.append(f"%{token}%")
    sql = f"""
        SELECT
            ir.raw_json,
            ir.unit_ref,
            ir.bedrooms,
            ir.area_value,
            ir.price,
            ir.view,
            ir.status,
            ir.inventory_type,
            IFNULL(p.name, '') AS project_name,
            IFNULL(a.name, '') AS area_name,
            IFNULL(d.name, '') AS developer_name,
            IFNULL(pt.name, '') AS property_type_name,
            IFNULL(f.file_name, '') AS file_name,
            IFNULL(f.source_group, '') AS source_group
        FROM inventory_rows ir
        LEFT JOIN projects p ON ir.project_id = p.project_id
        LEFT JOIN areas a ON ir.area_id = a.area_id
        LEFT JOIN developers d ON ir.developer_id = d.developer_id
        LEFT JOIN property_types pt ON ir.property_type_id = pt.property_type_id
        LEFT JOIN inventory_files f ON ir.source_id = f.source_id
        WHERE {" AND ".join(clauses)}
        LIMIT {int(limit)}
    """
    try:
        con = sqlite3.connect(f"file:{PROPERTY_DB_PATH}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        filtered = []
        for row in rows:
            blob = " ".join(
                str(x or "")
                for x in [
                    row["raw_json"],
                    row["unit_ref"],
                    row["project_name"],
                    row["area_name"],
                    row["developer_name"],
                ]
            ).lower()
            if all(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", blob) for token in tokens):
                filtered.append(row)
        return filtered[:limit]
    except Exception as exc:
        log_event("knowledge_inventory_lookup_error", error=str(exc), tokens=tokens)
        return []


def format_inventory_row(row):
    payload = parse_raw_json(row["raw_json"])
    price = safe_inventory_price(payload, row["inventory_type"])
    project = norm(row["project_name"]) or norm(payload.get("project")) or "Unknown project"
    area = norm(row["area_name"]) or norm(payload.get("area"))
    developer = norm(row["developer_name"]) or norm(payload.get("developer"))
    unit = norm(row["unit_ref"]) or norm(payload.get("unit_ref")) or norm(payload.get("unit")) or norm(payload.get("area_value"))
    bedrooms = norm(row["bedrooms"]) or norm(payload.get("bedrooms"))
    ptype = norm(row["property_type_name"]) or norm(payload.get("property_type"))
    size = norm(payload.get("size")) or norm(payload.get("area_value"))
    status = norm(row["status"]) or norm(payload.get("status"))
    facts = []
    if unit:
        facts.append(f"Unit {unit}")
    if project and project != "Unknown project":
        facts.append(project)
    if area:
        facts.append(area)
    if developer:
        facts.append(developer)
    if bedrooms:
        facts.append(f"{bedrooms} bed")
    if ptype:
        facts.append(ptype)
    if price:
        facts.append(money(price))
    if size and size != unit and not re.fullmatch(r"\d{2,6}", size):
        facts.append(f"Size/area: {size}")
    if status:
        facts.append(f"Status: {status}")
    return " | ".join(facts[:8])


def format_knowledge_first_reply(text, direct_rows, matches, live_context):
    language = live_context.get("latest_message_language") or detect_language(text)
    wants_photos = any(x in (text or "").lower() for x in ["photo", "photos", "picture", "صور", "صورة"])
    rows_text = []
    for row in direct_rows[:3]:
        line = format_inventory_row(row)
        if line and line not in rows_text:
            rows_text.append(line)
    for match in matches[:3]:
        price = money(match.get("price")) if isinstance(match, dict) else money(getattr(match, "price", None))
        line = " | ".join(
            x
            for x in [
                match.get("project") if isinstance(match, dict) else getattr(match, "project", ""),
                match.get("area") if isinstance(match, dict) else getattr(match, "area", ""),
                match.get("developer") if isinstance(match, dict) else getattr(match, "developer", ""),
                match.get("property_type") if isinstance(match, dict) else getattr(match, "property_type", ""),
                price,
            ]
            if x
        )
        if line and line not in rows_text:
            rows_text.append(line)
    if not rows_text:
        return ""
    if language == "arabic":
        intro = "لقيت عندي هذا:"
        tail = "الصور غير موجودة في صف الإنفنتوري هذا." if wants_photos else "هذه أفضل النتائج المؤكدة عندي الآن."
    else:
        intro = "Found this in inventory:"
        tail = "Photos are not attached to this inventory row." if wants_photos else "These are the best verified matches I have now."
    return intro + "\n- " + "\n- ".join(rows_text[:3]) + f"\n{tail}"


def knowledge_first_reply(text, live_context):
    if live_context.get("permission", {}).get("decision") != "allow":
        return ""
    if not inventory_knowledge_signal(text, live_context):
        return ""
    direct_rows = []
    if direct_inventory_lookup_signal(text):
        direct_rows = direct_inventory_rows(text, limit=5)
        if direct_rows:
            reply = format_knowledge_first_reply(text, direct_rows, [], live_context)
            if reply:
                log_event("knowledge_first_reply", direct_rows=len(direct_rows), matches=0, text=text[:160])
            return reply
        language = live_context.get("latest_message_language") or detect_language(text)
        retrieval_intent = live_context.get("retrieval_proof", {}).get("retrieval_intent")
        permission = live_context.get("permission", {})
        owner_allowed = permission.get("sender_type") in {"Omar", "Trusted Partner"} or live_context.get("relationship") == "Trusted Partner"
        if retrieval_intent == "ownership_lookup" and not owner_allowed:
            if language == "arabic":
                return "بيانات المالك أو التواصل خاصة وما أقدر أشاركها هنا."
            return "Owner/contact details are restricted and cannot be shared here."
        if language == "arabic":
            return "ما لقيت تفاصيل مؤكدة لهذه الوحدة في الإنفنتوري الحالي."
        return "I don’t see verified details for this unit in the current inventory."
    matches = []
    if has_enough_property_info(text):
        lower = (text or "").lower()
        if any(x in lower for x in ["rent", "yearly", "annual", "ايجار", "إيجار"]):
            return rental_inventory_reply(text)
        try:
            matches = [m.__dict__ for m in PropertyRecommendationAgent().search(query_text=text, limit=3)]
        except Exception as exc:
            log_event("knowledge_property_search_error", error=str(exc), text=text)
        credible = []
        for match in matches:
            price = match.get("price")
            ptype = str(match.get("property_type") or "").lower()
            project = str(match.get("project") or "").lower()
            if price is not None and int(price) < 100_000:
                continue
            if any(x in ptype or x in project for x in ["parking", "commercial unit number"]):
                continue
            if "rent" in lower and price is not None and int(price) > 5_000_000:
                continue
            credible.append(match)
        matches = credible
        if not matches:
            return no_verified_inventory_reply(text)
    reply = format_knowledge_first_reply(text, direct_rows, matches, live_context)
    if reply:
        log_event("knowledge_first_reply", direct_rows=len(direct_rows), matches=len(matches), text=text[:160])
    return reply


def action_first_property_reply(text):
    if is_rental_request(text):
        return rental_inventory_reply(text)
    return no_verified_inventory_reply(text)


def no_verified_inventory_reply(text):
    language = detect_language(text)
    if language == "arabic" or re.search(r"[\u0600-\u06FF]", text or ""):
        return "ما لقيت خيار مؤكد مباشر في الإنفنتوري الحالي. أحتاج أتأكد قبل ما أرسل."
    return "I don’t see a confirmed live option in verified inventory yet. I’ll confirm before sending."


def is_rental_request(text):
    lower = (text or "").lower()
    return any(x in lower for x in ["rent", "rental", "yearly", "annual", "lease", "ايجار", "إيجار", "سنوي"])


def rental_inventory_reply(text):
    language = detect_language(text)
    if language == "arabic" or re.search(r"[\u0600-\u06FF]", text or ""):
        return "مصدر الإيجارات المؤكد متصل، بس ما لقيت خيار مباشر مؤكد الآن. أحتاج أتأكد قبل ما أرسل."
    return "The verified rental source is connected, but I don’t see a confirmed live option yet. I’ll confirm before sending."


def developer_shortlist_reply(text):
    language = detect_language(text)
    is_arabic_mixed = language == "arabic" or re.search(r"[\u0600-\u06FF]", text or "")
    lowered = (text or "").lower()
    named = []
    if "tiger" in lowered:
        named.append("Tiger")
    if "eleven" in lowered:
        named.append("Eleven")
    if named:
        if is_arabic_mixed:
            return f"{' و '.join(named)} تمام. ما لقيت خيارات مؤكدة مباشرة لهم في الإنفنتوري الحالي، أحتاج أتأكد قبل ما أرسل."
        return f"{' and '.join(named)} noted. I don’t see confirmed live options in verified inventory yet. I’ll confirm before sending."
    if is_arabic_mixed:
        return "ما لقيت خيارات مؤكدة مباشرة لهذا الديفلوبر في الإنفنتوري الحالي. أحتاج أتأكد قبل ما أرسل."
    return "I don’t see confirmed live options for that developer in verified inventory yet. I’ll confirm before sending."


def extract_identity_name(text):
    raw = str(text or "").strip()
    lower = raw.lower()
    arabic_match = re.search(r"([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+){0,3})\s+(?:انا|أنا)\b", raw)
    if arabic_match:
        return arabic_match.group(1).strip()
    arabic_with_match = re.search(r"(?:معك|اسمي)\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+){0,3})", raw)
    if arabic_with_match:
        return arabic_with_match.group(1).strip()
    english_match = re.search(r"(?:my name is|this is|it's|its)\s+([A-Za-z][A-Za-z .'-]{1,60})", lower, flags=re.I)
    if english_match:
        return english_match.group(1).strip().title()
    return ""


def group_access_reply(text, live_context):
    language = live_context.get("latest_message_language") or detect_language(text)
    lower = (text or "").lower()
    history = (live_context.get("conversation_history") or "").lower()
    contact_name = live_context.get("contact_context", {}).get("known_contact_name", "")
    first_name = ""
    if contact_name:
        first_name = str(contact_name).strip().split()[0]
    elif "sohaib" in (text or "").lower() or "sohaib" in history:
        first_name = "Sohaib"
    name_prefix = f"{first_name}, " if first_name and language == "english" else ""

    is_add_other = any(x in lower for x in ["add this person", "add him", "add her", "also add", "you can also add"]) or bool(re.search(r"\b0?5\d{8}\b", lower))
    mentions_display_name = "display name" in lower or "display name" in history
    has_share_context = any(x in lower for x in ["inquiries", "good properties", "share in the group", "properties"]) or any(
        x in history for x in ["inquiries", "good properties", "share in the group", "properties"]
    )
    wants_both = any(x in lower for x in ["both group", "both groups", "in both"]) or any(x in history for x in ["both group", "both groups"])

    if language == "arabic":
        if is_add_other:
            return "وصلني الرقم. من أي شركة؟ الإضافة تحتاج مراجعة عشان نحافظ على جودة الجروب."
        if "thank" in lower or "thanks" in lower:
            return "حاضر، ولا يهمك. الإضافة بعد المراجعة."
        if mentions_display_name and any(x in lower for x in ["don't know", "dont know", "no", "actually"]):
            return "ولا يهمك، اسم الواتساب يكفي."
        if has_share_context:
            return "ممتاز، هذا مناسب لجروب السيكندري. بس نخلي المشاركات جدية ونظيفة عشان جودة الجروب."
        if wants_both:
            return "تمام، الاثنين. الإضافة تكون بعد المراجعة، بدون ما نكرر أسئلة."
        return "تمام، تقصد جروب السيكندري/الوكلاء في دبي؟ الإضافة تحتاج مراجعة بسيطة."

    if is_add_other:
        return "Received the number. Which company is he with? Adding needs review so we keep the group clean."
    if "thank" in lower or "thanks" in lower:
        return "Anytime. Adding stays after review so the group stays proper."
    if mentions_display_name and any(x in lower for x in ["don't know", "dont know", "no", "actually"]):
        return "No issue, WhatsApp name is enough."
    if has_share_context:
        return "Good, that fits the secondary group. Keep it serious: clean units, real inquiries, no spam."
    if wants_both:
        return f"{name_prefix}noted — both groups. Your WhatsApp name is enough; adding stays after review."
    if "dxb group" in lower or "your group" in lower or "group" in lower:
        return f"{name_prefix}noted — you mean the DXB secondary/agent group. Adding depends on review/suitability."
    return "Noted. Adding depends on review so the group stays clean."


def buyer_search_reply(text):
    language = detect_language(text)
    if language == "arabic":
        return "تمام، شراء. أرسل المنطقة أو الديفلوبر المفضل."
    if language == "german":
        return "Alles klar, Kauf. Schick mir Gebiet oder Developer."
    if language == "russian":
        return "Хорошо, покупка. Пришли район или девелопера."
    return "Perfect, buying. Send the preferred area or developer."


def greeting_reply(text, live_context):
    language = live_context.get("latest_message_language") or detect_language(text)
    active_history = live_context.get("conversation_history") != "No prior history"
    relationship = live_context.get("relationship", "Unknown")
    lowered = (text or "").lower()
    profile = live_context.get("contact_context", {}).get("special_contact_profile") or {}
    profile_id = profile.get("id", "")
    if profile_id == "hassan_kazzabel":
        if language == "arabic" or language == "neutral":
            intro_sent = bool(live_context.get("stored_memory", {}).get("special_profile_intro_sent"))
            return profile.get("short_greeting_ar") if intro_sent else profile.get("first_greeting_ar")
        return profile.get("short_greeting_en") or "My brother Hassan 😄 tell me."
    if profile_id == "vetn":
        if language == "arabic":
            return profile.get("short_greeting_ar") or "هلا Vetn، تفضل."
        return profile.get("short_greeting_en") or "Hey Vetn — tell me."
    if language == "arabic":
        if any(x in (text or "") for x in ["وين مختفي", "وينك", "مختفي", "وين هالغيبة", "وين هالقطعة"]):
            return "موجود 😄 كان في ضغط شوي. شخبارك إنت؟"
        if any(x in (text or "") for x in ["كيفك", "شلونك", "شو اخبارك"]):
            return "الحمدلله بخير يا غالي، إنت كيفك؟"
        return (
            "هلا والله 🌹"
            if relationship in {"FRIEND", "FAMILY", "Friend", "friend", "Family"}
            else "وعليكم السلام، أهلاً."
        )
    if language == "german":
        return "Guten Morgen." if "morgen" in (text or "").lower() else "Hallo."
    if language == "russian":
        return "Доброе утро." if "утро" in (text or "").lower() else "Здравствуйте."
    if any(x in lowered for x in ["how is everything", "how's everything", "how everything"]):
        return "All good here. How’s everything with you?"
    if any(x in lowered for x in ["where have you been", "where you been", "missed in action"]):
        return "Here 😄 just been a bit busy. How are you?"
    if "what about you" in lowered or "how are you" in lowered:
        return "All good, thanks."
    if relationship in {"FRIEND", "FAMILY", "Friend", "friend", "Family"}:
        if active_history:
            return "Morning." if "morning" in (text or "").lower() else "Heya."
        return "Yo 👋"
    if active_history:
        return "Morning." if "morning" in (text or "").lower() else "Hi."
    return "Hello." if live_context.get("relationship") in {"CLIENT", "AGENT", "STAFF"} else "Hey."


def business_judgment_reply(text, live_context):
    judgment = live_context.get("business_judgment", {})
    next_action = judgment.get("next_action")
    expected_next = judgment.get("expected_next")
    language = live_context.get("latest_message_language") or detect_language(text)
    lower = (text or "").lower()
    history_lower = (live_context.get("conversation_history") or "").lower()
    if any(x in lower for x in ["high roi", "roi", "future growth", "no preference"]) and any(
        x in history_lower for x in ["1br", "bedroom", "buy", "sale", "resale", "property", "budget"]
    ):
        if language == "arabic":
            return "تمام. الأولوية تكون لأقوى خيارات ROI والنمو، حسب النتائج المؤكدة."
        if language == "german":
            return "Perfekt. Ich fokussiere auf die stärksten ROI- und Wachstum-Optionen und sende dir die besten Matches."
        if language == "russian":
            return "Отлично. Сфокусируюсь на лучших вариантах по ROI и росту и отправлю подходящие объекты."
        return "Perfect. I’ll focus on the strongest ROI options and send the top matches."
    if next_action == "casual_reply" or expected_next == "natural_social_reply_no_property_qualification":
        return greeting_reply(text, live_context)
    if next_action == "humor_reply" or expected_next == "playful_human_reply_no_property_route":
        if language == "arabic":
            return "هههه لا لا، عمر موجود بس عم يجرّب الذكاء شوي 😄"
        return "Haha no worries, Omar is here — just testing the AI a bit 😄"
    if next_action == "acknowledge_identity" or expected_next == "friendly_identity_ack_no_business_qualification":
        name = extract_identity_name(text)
        if language == "arabic":
            return f"يا هلا {name}، نورت." if name else "يا هلا، نورت."
        return f"Got it, {name}." if name else "Got it."
    if next_action == "verify_group_access" or expected_next == "agent_group_onboarding_no_fake_action":
        return group_access_reply(text, live_context)
    if next_action in {"calm_action_first", "urgent_action_first"}:
        if language == "arabic":
            return "تمام، وصلت."
        if language == "german":
            return "Verstanden."
        if language == "russian":
            return "Понял."
        return "Understood."
    if next_action == "acknowledge_correction":
        if language == "arabic":
            return "تمام، صححتها."
        if language == "german":
            return "Verstanden, korrigiert."
        if language == "russian":
            return "Понял, исправил."
        return "Got it, corrected."
    if next_action == "safe_answer_or_escalate" or expected_next == "safe_boundary_plus_next_step":
        if language == "arabic" or re.search(r"[\u0600-\u06FF]", text or ""):
            return "هذا الموضوع يحتاج مراجعة عمر قبل أي مشاركة أو إجراء."
        return "This needs Omar review before sharing or taking action."
    if next_action == "continue_buyer_requirement" or expected_next == "continue_buyer_search":
        return buyer_search_reply(text)
    if expected_next == "developer_shortlist_or_options":
        return developer_shortlist_reply(text)
    if next_action == "recommend" or expected_next == "shortlist_or_check_options":
        return action_first_property_reply(text)
    if next_action == "ask_one_missing_detail" and live_context.get("conversation_objective") in {"property_inquiry", "active_deal"}:
        return action_first_property_reply(text)
    if next_action == "answer_process":
        return ""
    return ""


def social_context_reply(text, live_context):
    social = live_context.get("social_context", {})
    relationship = live_context.get("relationship", "Unknown")
    category = social.get("category")
    language = live_context.get("latest_message_language") or detect_language(text)
    if category == "identity_intro":
        name = extract_identity_name(text)
        if language == "arabic":
            return f"يا هلا {name}، نورت." if name else "يا هلا، نورت."
        return f"Good to hear from you, {name}." if name else "Good to hear from you."
    if category == "correction":
        if language == "arabic":
            return "تمام، صححتها."
        if language == "german":
            return "Verstanden, korrigiert."
        if language == "russian":
            return "Понял, исправил."
        return "Got it, corrected."
    if category == "emoji_reaction":
        emoji_meaning = social.get("emoji_meaning")
        if emoji_meaning == "acknowledgement_or_approval":
            return "تمام."
        if emoji_meaning == "approval_or_excitement":
            return "🔥"
        if emoji_meaning == "laughing_or_light_embarrassment":
            return "😂 تمام"
        return "تمام."
    if category == "banter":
        lowered = (text or "").lower()
        raw = text or ""
        if language == "arabic" and any(x in raw for x in ["وين مختفي", "وينك", "مختفي", "وين هالغيبة", "وين هالقطعة"]):
            return "موجود 😄 كان في ضغط شوي. شخبارك إنت؟"
        if language == "english" and any(x in lowered for x in ["where have you been", "where you been", "missed in action"]):
            return "Here 😄 just been a bit busy. How are you?"
        if relationship == "Friend" and language == "arabic":
            return "هلا والله 😄"
        if relationship == "Friend" and language == "german":
            return "Haha, alles klar 😄"
        if relationship == "Friend" and language == "russian":
            return "Хаха, понял 😄"
        if relationship == "Friend":
            return "My man 😄"
        if language == "arabic":
            return "هههه موجود 😄 شخبارك؟"
        if language == "german":
            return "Haha, ich bin da 😄 was gibt’s?"
        if language == "russian":
            return "Хаха, я тут 😄 что нового?"
        return "Haha I’m here 😄 what’s up?"
    if category == "misunderstanding":
        if language == "arabic":
            return "تمام، وضحلي قصدك بس."
        if language == "german":
            return "Verstanden, erklär mir kurz, was du meinst."
        if language == "russian":
            return "Понял, уточни коротко, что ты имеешь в виду."
        return "Got it, tell me what you meant."
    if category == "frustration":
        if language == "arabic":
            return "معك حق."
        if language == "german":
            return "Du hast recht."
        if language == "russian":
            return "Ты прав."
        return "You’re right."
    if category == "urgency":
        if language == "arabic":
            return "تمام، عليها الآن."
        if language == "german":
            return "Bin dran."
        if language == "russian":
            return "Сейчас займусь."
        return "On it now."
    return ""


def fast_path_reply(text, live_context):
    """Safe speed path after all required context/permission layers have run."""
    permission = live_context.get("permission", {})
    retrieval_reply = data_retrieval_reply(text, live_context)
    if retrieval_reply:
        return retrieval_reply
    if permission.get("decision") != "allow":
        return ""
    knowledge_reply = knowledge_first_reply(text, live_context)
    if knowledge_reply:
        return knowledge_reply
    intent = live_context.get("intent")
    social = live_context.get("social_context", {}).get("category")
    next_action = live_context.get("business_judgment", {}).get("next_action")
    expected_next = live_context.get("business_judgment", {}).get("expected_next")
    if live_context.get("intent") == "group_access" or next_action == "verify_group_access" or expected_next == "agent_group_onboarding_no_fake_action":
        return business_judgment_reply(text, live_context)
    if live_context.get("conversation_objective") in {"casual_greeting", "friend_chat", "joke", "correction"}:
        return business_judgment_reply(text, live_context) or social_context_reply(text, live_context)
    if intent == "property" and (
        next_action in {"recommend", "continue_buyer_requirement"}
        or expected_next in {"shortlist_or_check_options", "developer_shortlist_or_options", "continue_buyer_search"}
    ):
        return business_judgment_reply(text, live_context)
    if social in {"identity_intro", "correction", "emoji_reaction", "banter", "frustration", "urgency"}:
        return social_context_reply(text, live_context)
    if intent == "greeting":
        return greeting_reply(text, live_context)
    if next_action in {"recommend", "calm_action_first", "urgent_action_first", "acknowledge_correction", "safe_answer_or_escalate"}:
        return business_judgment_reply(text, live_context)
    if next_action == "ask_one_missing_detail" and live_context.get("conversation_objective") in {"property_inquiry", "active_deal"}:
        return business_judgment_reply(text, live_context)
    if next_action in {"continue_buyer_requirement"} or live_context.get("business_judgment", {}).get("expected_next") == "developer_shortlist_or_options":
        return business_judgment_reply(text, live_context)
    return ""


def enforce_interaction_policy(text, reply, live_context):
    knowledge_reply = knowledge_first_reply(text, live_context)
    if knowledge_reply and ("?" in (reply or "") or "؟" in (reply or "")):
        return knowledge_reply
    probe = live_context.get("knowledge_probe", {})
    if probe.get("known_answer") and ("?" in (reply or "") or "؟" in (reply or "")):
        if probe.get("document_hits"):
            language = live_context.get("latest_message_language") or detect_language(text)
            names = [hit.get("name", "") for hit in probe.get("document_hits", [])[:3] if hit.get("name")]
            if language == "arabic":
                return "لقيت عندي ملفات مرتبطة:\n- " + "\n- ".join(names) + "\nهذه المطابقات المحلية المؤكدة."
            return "Found related files:\n- " + "\n- ".join(names) + "\nThese are the verified local matches."
        if probe.get("history_hit") or probe.get("memory_hit"):
            judgment_reply = business_judgment_reply(text, live_context)
            if judgment_reply:
                return judgment_reply
        if has_enough_property_info(text):
            return action_first_property_reply(text)
    judgment_reply = business_judgment_reply(text, live_context)
    if live_context.get("intent") == "group_access" or live_context.get("business_judgment", {}).get("next_action") == "verify_group_access":
        return judgment_reply or reply
    social_reply = social_context_reply(text, live_context)
    if social_reply:
        return social_reply
    if judgment_reply and ("?" in reply or "؟" in reply or live_context.get("business_judgment", {}).get("ask_allowed") is False):
        return judgment_reply
    if live_context.get("intent") == "property" and has_enough_property_info(text):
        if "?" in reply or "؟" in reply:
            return action_first_property_reply(text)
    if "would you like me to" in (reply or "").lower():
        return re.sub(r"(?i)would you like me to", "I’ll", reply).strip()
    return reply


def openai_reply(text, sender, state_session=None, context_seed=None):
    # Merge the live WhatsApp context with injected system_context before any OpenAI call.
    merged_data = build_live_response_context(
        text,
        sender,
        state_session=state_session,
        seeded_relationship_tag=(context_seed or {}).get("relationship_tag"),
        seeded_relationship_source=(context_seed or {}).get("relationship_tag_source"),
        system_context=(context_seed or {}).get("system_context"),
    )
    live_context = merged_data
    print("--- LIVE PAYLOAD DEBUG ---")
    print(f"System Context keys: {merged_data.get('system_context', {}).keys()}")
    if "identity_dna" in merged_data.get("system_context", {}):
        print("Identity DNA detected in live payload.")
    else:
        print("Identity DNA MISSING in live payload.")
    history = live_context["conversation_history"]
    if _is_bridge_feedback(text):
        reply = human_bridge_reply(text)
        log_event(
            "humanity_bridge_triggered",
            sender=sender,
            text=text[:180],
            relationship=live_context.get("relationship"),
            relationship_tag=live_context.get("relationship_tag"),
            reply=reply,
        )
        return reply, 200, False, history, live_context

    permission = live_context["permission"]
    retrieval_proof = live_context.get("retrieval_proof", {})
    sentiment_handoff = live_context.get("personality", {}).get("sentiment_handoff", {})
    psych_profile = live_context.get("psych_profile", {})

    retrieval_reply = data_retrieval_reply(text, live_context)
    if retrieval_reply:
        return retrieval_reply, 200, False, history, live_context

    if permission["decision"] in {"refuse_safe", "hold_for_omar"} and permission.get("safe_reply"):
        return permission["safe_reply"], 200, False, history, live_context

    if retrieval_proof.get("required") and (
        not retrieval_proof.get("executed") or not retrieval_proof.get("match_found")
    ):
        log_event(
            "retrieval_gate_no_match",
            sender=sender,
            text=text[:180],
            retrieval_intent=retrieval_proof.get("retrieval_intent"),
            source_used=retrieval_proof.get("source_used"),
            query_used=retrieval_proof.get("query_used"),
            match_found=retrieval_proof.get("match_found"),
            result_count=retrieval_proof.get("result_count"),
        )
        if state_session is not None:
            state_session["payload"] = {
                "context_gathering_state": "awaiting clarification after no-match retrieval",
                "last_query": text,
                "retrieval_intent": retrieval_proof.get("retrieval_intent"),
            }
            _transition_session_state(state_session, "CONTEXT_GATHERING")
        return bridge_no_match_reply(text), 200, False, history, live_context

    quick_reply = fast_path_reply(text, live_context)
    if quick_reply:
        return quick_reply, 200, False, history, live_context

    augmented_message = format_live_prompt(text, live_context)
    status, parsed, raw = post_json(
        OPENAI_ENDPOINT,
        {
            "message": augmented_message,
            "latest_message": text,
            "from": sender,
            "history": history,
            "psych_profile": psych_profile,
            "contact_context": live_context["contact_context"],
            "relationship_tag": live_context.get("relationship_tag"),
            "relationship": live_context["relationship"],
            "intent": live_context["intent"],
            "permission": live_context["permission"],
            "personality": live_context["personality"],
            "system_context": merged_data.get("system_context", {}),
            "merged_context": merged_data,
        },
        timeout=60,
    )
    reply = ""
    fallback = False
    if isinstance(parsed, dict):
        reply = parsed.get("reply") or parsed.get("text") or parsed.get("output") or ""
        fallback = bool(parsed.get("fallback"))
    reply = str(reply or "").strip()
    if status < 200 or status >= 300 or not reply:
        raise RuntimeError(f"OpenAI endpoint failed status={status} body={raw[:500]}")
    if fallback or is_generic_or_fallback_reply(reply):
        raise RuntimeError(f"Fallback/generic reply blocked by live personality mode: {reply[:160]}")
    reply = enforce_interaction_policy(text, reply, live_context)
    expected_language = live_context.get("latest_message_language") or "english"
    if reply_violates_language_lock(reply, expected_language):
        locked_reply = language_lock_fallback(text, live_context)
        log_event(
            "language_lock_rewrite",
            sender=sender,
            expected_language=expected_language,
            original_reply=reply[:240],
            rewritten_reply=locked_reply[:240],
        )
        reply = locked_reply
    return reply, status, fallback, history, live_context


def emergency_non_silent_reply(text):
    language = detect_language(text)
    if language == "arabic":
        return "وصلني."
    if language == "german":
        return "Erhalten."
    if language == "russian":
        return "Получил."
    return "Received."


def send_whatsapp(to, text):
    token = keychain_secret("AIOS Wasender API Key")
    last_error = None
    candidates = normalize_outbound_target_candidates(to)
    for target in candidates:
        log_event("whatsapp_send_attempt", original_target=str(to or ""), provider_target=target)
        status, parsed, raw = post_json(
            WASENDER_SEND_URL,
            {"to": target, "text": text},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "AIOS-Simple-WhatsApp-Gateway/1.0",
            },
            timeout=60,
        )
        ok = bool(isinstance(parsed, dict) and (parsed.get("success") is True or parsed.get("status") in ("sent", "success")))
        if status >= 200 and status < 300 and ok:
            if target != (candidates[0] if candidates else target):
                log_event("whatsapp_send_target_fallback", original=normalize_outbound_whatsapp_target(to), fallback_target=target)
            return parsed, status
        last_error = f"status={status} body={raw[:500]}"

    raise RuntimeError(f"Wasender send failed after trying {candidates}: {last_error}")


def send_whatsapp_with_pacing(to, text, psych_profile=None):
    text = sanitize_human_output(text)
    safe_reply, blocked, reason = apply_data_shield(text)
    urgency = (psych_profile or {}).get("urgency", "Medium") if isinstance(psych_profile, dict) else "Medium"
    delay = estimate_human_delay(safe_reply, urgency)
    if delay > 0:
        time.sleep(delay)

    segments = split_reply_message(safe_reply)
    if not segments:
        return None, 0, "", False

    if len(segments) == 1:
        send_result, send_status = send_whatsapp(to, segments[0])
        return send_result, send_status, segments[0], blocked

    first_part, second_part = segments[0], segments[1]
    send_result, send_status = send_whatsapp(to, first_part)
    send_typing_state(to)
    time.sleep(3)
    send_result2, send_status2 = send_whatsapp(to, second_part)
    send_status = send_status2
    if isinstance(send_result, dict):
        combined = dict(send_result)
        combined["followup_message"] = second_part
        combined["followup_send_status"] = send_status2
        combined["data_shield_blocked"] = blocked
        combined["data_shield_reason"] = reason if blocked else ""
        return combined, send_status, safe_reply, blocked
    return send_result2, send_status, safe_reply, blocked


class Handler(BaseHTTPRequestHandler):
    server_version = "AIOSSimpleWhatsAppGateway/1.0"

    def send_json(self, code, body):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _auth_failed(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("WWW-Authenticate", 'Basic realm="AIOS Admin"')
        raw = json.dumps({"ok": False, "error": "unauthorized"}).encode("utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return None, 400, {"ok": False, "error": "invalid_content_length"}, 0
        if length < 0 or length > MAX_BODY_BYTES:
            return None, 413, {"ok": False, "error": "payload_too_large"}, length
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        return payload, None, None, length

    def _basic_auth_ok(self):
        if not ADMIN_AUTH_USER or not ADMIN_AUTH_PASSWORD:
            return False
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        user, sep, password = decoded.partition(":")
        return bool(sep) and hmac.compare_digest(user, ADMIN_AUTH_USER) and hmac.compare_digest(password, ADMIN_AUTH_PASSWORD)

    def _shared_secret_ok(self, payload, required_secret):
        if not required_secret:
            return False
        payload = payload if isinstance(payload, dict) else {}
        supplied = (
            self.headers.get("X-AIOS-Webhook-Secret", "")
            or self.headers.get("X-Webhook-Secret", "")
            or self.headers.get("X-AIOS-Admin-Secret", "")
            or str((payload or {}).get("webhook_secret") or "")
            or str((payload or {}).get("admin_secret") or "")
        )
        return bool(supplied) and hmac.compare_digest(str(supplied), required_secret)

    def _webhook_authorized(self, payload):
        return self._shared_secret_ok(payload, WEBHOOK_SECRET)

    def _admin_authorized(self, payload):
        return self._basic_auth_ok() or self._shared_secret_ok(payload, ADMIN_SECRET)

    def do_GET(self):
        if self.path == "/health":
            try:
                queue_stats = airtable_queue_stats()
            except Exception as exc:
                queue_stats = {"error": str(exc)}
            self.send_json(
                200,
                {
                    "ok": True,
                    "service": "simple-whatsapp-openai-gateway",
                    "airtable_configured": airtable_is_configured(),
                    "airtable_queue": queue_stats,
                    "airtable_replay_worker_alive": bool(AIRTABLE_REPLAY_THREAD and AIRTABLE_REPLAY_THREAD.is_alive()),
                    "airtable_replay_interval_seconds": AIRTABLE_REPLAY_INTERVAL_SECONDS,
                },
            )
        else:
            self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path == "/admin/airtable/replay":
            payload, error_code, error_body, _payload_size = self._read_json_body()
            if error_code:
                self.send_json(error_code, error_body)
                return
            if not self._admin_authorized(payload):
                self._auth_failed()
                return
            limit = int(payload.get("limit") or 25)
            result = airtable_replay_writeback_queue(limit=limit)
            try:
                result["airtable_queue"] = airtable_queue_stats()
            except Exception as exc:
                result["airtable_queue"] = {"error": str(exc)}
            self.send_json(200 if result.get("ok") else 409, result)
            return

        if self.path != "/webhook/whatsapp/simple":
            self.send_json(404, {"ok": False, "error": "not_found"})
            return

        payload, error_code, error_body, payload_size = self._read_json_body()
        if error_code:
            self.send_json(error_code, error_body)
            return
        if not self._webhook_authorized(payload):
            self._auth_failed()
            return

        parsed = extract_payload(payload)
        log_event(
            "inbound_received",
            event_type="webhook_inbound",
            message_id=parsed.get("message_id"),
            sender=parsed.get("sender"),
            payload_size=payload_size,
            ignored=parsed.get("ignored"),
            ignored_reason=parsed.get("ignored_reason"),
        )
        if parsed.get("from_me"):
            record_human_reply_time(parsed.get("sender"))
        forced_relationship_tag = resolve_relationship_override(parsed.get("sender"))
        if forced_relationship_tag:
            parsed["relationship_tag"] = forced_relationship_tag
            parsed["relationship_tag_source"] = "stress_test_override"
            parsed["relationship_override"] = True
            log_event(
                "relationship_override_applied",
                sender=parsed.get("sender"),
                override_tag=forced_relationship_tag,
                strategy=RELATIONSHIP_ASSIGNMENT_STRATEGY,
            )
        else:
            parsed["relationship_tag"] = None
            parsed["relationship_tag_source"] = None
            parsed["relationship_override"] = False
        pre_contact_context = get_contact_context(parsed.get("sender"))
        pre_relationship_tag, pre_relationship_source = (parsed["relationship_tag"], parsed["relationship_tag_source"]) if parsed.get("relationship_tag") else relationship_classifier_node(
            parsed.get("sender"),
            parsed.get("text", ""),
            pre_contact_context,
        )
        parsed["relationship_tag"] = pre_relationship_tag
        parsed["relationship_tag_source"] = pre_relationship_source

        state_session = _state_machine_session(parsed.get("sender"))

        if parsed["ignored"]:
            airtable_writeback_inbound(parsed, gate_reason=parsed.get("ignored_reason", "inbound_blocked"), decision="ignored")
            log_event("inbound_ignored", reason=parsed.get("ignored_reason", "inbound_blocked"), parsed=parsed)
            self.send_json(200, {"ok": True, "ignored": True})
            return

        should_respond, gate_reason = should_i_respond(
            parsed.get("text", ""),
            parsed.get("sender", ""),
            parsed.get("relationship_tag"),
            is_user_typing=bool(parsed.get("is_user_typing")),
            state_session=state_session,
        )
        if not should_respond:
            log_event(
                "inbound_business_gate_ignored",
                reason=gate_reason,
                sender=parsed.get("sender"),
                relationship_tag=parsed.get("relationship_tag"),
                text=parsed.get("text", "")[:180],
            )
            airtable_writeback_inbound(parsed, gate_reason=gate_reason, decision="ignored_by_gate")
            self.send_json(200, {"ok": True, "ignored": True, "reason": gate_reason})
            return

        duplicate, duplicate_key = is_duplicate(parsed)
        if duplicate:
            log_event("duplicate_suppressed", key=duplicate_key, parsed=parsed)
            airtable_writeback_inbound(parsed, gate_reason="duplicate_suppressed", decision="duplicate_suppressed")
            self.send_json(200, {"ok": True, "duplicate": True, "suppressed": True})
            return

        airtable_writeback_inbound(parsed, gate_reason="accepted_for_processing", decision="accepted_for_processing")

        try:
            _transition_session_state(
                state_session,
                "DISCOVERY_RAPPORT" if not state_session.get("contact_record_exists") else "ACTIVE_CONTEXT",
            )

            remember(parsed["sender"], "user", parsed["text"])
            if parsed.get("sender"):
                _append_to_state_history(state_session, "user", parsed.get("text", ""))

            if parsed.get("is_user_typing"):
                log_event("reflected_typing_freeze", sender=parsed.get("sender"))
                self.send_json(200, {"ok": True, "ignored": True, "reason": "user_typing"})
                return

            if REFLECTIVE_GATEWAY_DELAY_SECONDS > 0:
                time.sleep(REFLECTIVE_GATEWAY_DELAY_SECONDS)

            reply, openai_status, fallback, history, live_context = openai_reply(
                parsed["text"],
                parsed["sender"],
                state_session=state_session,
                context_seed={
                    "relationship_tag": parsed.get("relationship_tag"),
                    "relationship_tag_source": parsed.get("relationship_tag_source"),
                    "system_context": payload.get("system_context") or payload.get("context_object") or {},
                },
            )
            stress_tone_check = None
            if parsed.get("relationship_override"):
                stress_tone_check = evaluate_relationship_tone_match(parsed.get("relationship_tag"), reply)
                log_event(
                    "stress_relationship_tone_check",
                    sender=parsed["sender"],
                    override_tag=parsed.get("relationship_tag"),
                    relationship=live_context.get("relationship"),
                    tone_match=stress_tone_check,
                    text=parsed.get("text"),
                    reply=reply[:120],
                )
            log_retrieval_audit(parsed["sender"], parsed["text"], live_context, reply)
            log_event(
                "personality_context_built",
                sender=parsed["sender"],
                intent=live_context["intent"],
                relationship=live_context["relationship"],
                relationship_source=live_context.get("relationship_source"),
                sender_type=live_context["permission"]["sender_type"],
                policy_decision=live_context["permission"]["decision"],
                contact_known=live_context["contact_context"].get("known_chat", False),
                personality_profile=live_context["personality"].get("profile"),
                social_context=live_context.get("social_context", {}).get("category"),
                business_next_action=live_context.get("business_judgment", {}).get("next_action"),
                expected_next=live_context.get("business_judgment", {}).get("expected_next"),
                retrieval_intent=live_context.get("retrieval_proof", {}).get("retrieval_intent"),
                retrieval_source=live_context.get("retrieval_proof", {}).get("source_used"),
                retrieval_query=live_context.get("retrieval_proof", {}).get("query_used"),
                retrieval_match_found=live_context.get("retrieval_proof", {}).get("match_found"),
                retrieval_result_count=live_context.get("retrieval_proof", {}).get("result_count"),
            )
            log_event(
                "openai_reply",
                status=openai_status,
                sender=parsed["sender"],
                reply=reply,
                fallback=fallback,
                history_loaded=history != "No prior history",
                history=history,
                personality_profile=live_context["personality"].get("profile"),
                policy_decision=live_context["permission"]["decision"],
                relationship=live_context["relationship"],
                retrieval_proof=live_context.get("retrieval_proof", {}),
                psych_profile=live_context.get("psych_profile", {}),
            )
            if parsed.get("relationship_override"):
                log_event(
                    "stress_relationship_final_state",
                    sender=parsed["sender"],
                    override_tag=parsed.get("relationship_tag"),
                    session_state=state_session.get("state") if state_session else None,
                    tone_match=stress_tone_check,
                )
            outbound_state = load_outbound_state(parsed["sender"])
            rewritten_reply = rewrite_to_omar_style(
                reply,
                {
                    "relationship": live_context.get("relationship"),
                    "relationship_tag": parsed.get("relationship_tag"),
                    "intent": live_context.get("intent"),
                    "retrieval_used": bool(live_context.get("retrieval_proof", {}).get("executed")),
                    "language": live_context.get("latest_message_language"),
                },
            )
            controller_input = {
                "sender": parsed["sender"],
                "relationship": live_context.get("relationship"),
                "relationship_tag": parsed.get("relationship_tag") or live_context.get("relationship_tag"),
                "message_id": parsed.get("message_id"),
                "inbound_text": parsed.get("text", ""),
                "original_reply": reply,
                "proposed_reply": rewritten_reply,
                "retrieval_used": bool(live_context.get("retrieval_proof", {}).get("executed")),
                "retrieval_match_found": bool(live_context.get("retrieval_proof", {}).get("match_found")),
                "openai_used": True,
                "confidence": live_context.get("retrieval_proof", {}).get("confidence", 0),
                "is_test_message": False,
                "last_bot_reply": outbound_state.get("last_bot_reply_text", ""),
                "last_human_reply_time": outbound_state.get("last_human_reply_time", 0),
                "last_inbound_message_id": outbound_state.get("last_inbound_message_id", ""),
                "recent_replies": [outbound_state.get("last_bot_reply_text", "")],
                "intent": live_context.get("intent"),
                "language": live_context.get("latest_message_language"),
                "private_or_sensitive_flags": [] if live_context.get("permission", {}).get("decision") == "allow" else [live_context.get("permission", {}).get("decision")],
                "state": outbound_state,
            }
            controller_result = outbound_safety_controller(controller_input)
            final_reply = controller_result.get("final_reply") or rewritten_reply
            send_result = {}
            send_status = 0
            blocked = False
            sent = False
            outcome_label = "drafted_for_omar"
            if controller_result["decision"] == "SEND_NOW":
                send_result, send_status, safe_reply, blocked = send_whatsapp_with_pacing(
                    parsed.get("reply_target") or parsed["sender"],
                    final_reply,
                    live_context.get("psych_profile", {}),
                )
                final_reply = safe_reply
                sent = True
                outcome_label = "sent_success" if 200 <= int(send_status or 0) < 300 else "provider_failed"
                remember(parsed["sender"], "assistant", final_reply)
                if parsed.get("sender"):
                    _append_to_state_history(state_session, "assistant", final_reply)
                store_ai_promise(parsed["sender"], final_reply)
                log_event(
                    "whatsapp_outbound",
                    status=send_status,
                    sender=parsed["sender"],
                    result=send_result,
                    shielded=blocked,
                    relationship_override=parsed.get("relationship_override"),
                    expected_relationship=parsed.get("relationship_tag"),
                    relationship_source=parsed.get("relationship_tag_source"),
                    tone_match=evaluate_relationship_tone_match(
                        parsed.get("relationship_tag") if parsed.get("relationship_override") else live_context.get("relationship"),
                        final_reply,
                    ),
                    controller_decision=controller_result["decision"],
                    reason_codes=controller_result.get("reason_codes", []),
                )
            else:
                reason_codes = controller_result.get("reason_codes", [])
                if "blocked_duplicate_inbound" in reason_codes or "blocked_duplicate_semantic_reply" in reason_codes:
                    outcome_label = "blocked_duplicate"
                elif "blocked_test_text" in reason_codes:
                    outcome_label = "blocked_test_text"
                elif "blocked_human_recent" in reason_codes:
                    outcome_label = "blocked_human_recent"
                elif "blocked_unsafe_private" in reason_codes:
                    outcome_label = "blocked_unsafe_private"
                elif "blocked_low_quality_fallback" in reason_codes:
                    outcome_label = "blocked_low_quality"
                elif controller_result["decision"] == "DRAFT_FOR_OMAR":
                    outcome_label = "drafted_for_omar"
                log_event(
                    "whatsapp_outbound_blocked",
                    sender=parsed["sender"],
                    message_id=parsed.get("message_id"),
                    decision=controller_result["decision"],
                    reason_codes=reason_codes,
                    original_reply=reply,
                    rewritten_reply=rewritten_reply,
                    final_reply=final_reply,
                )
            update_relationship_memory(parsed["sender"], parsed["text"], live_context)
            update_outbound_state_after_decision(parsed["sender"], parsed.get("message_id"), final_reply, live_context, controller_result, sent=sent)
            log_outbound_decision(
                controller_input,
                controller_result,
                original_reply=reply,
                rewritten_reply=rewritten_reply,
                final_reply=final_reply,
                sent=sent,
                send_result=send_result,
                outcome_label=outcome_label,
                live_context=live_context,
            )
            if parsed.get("sender"):
                _persist_state_session(state_session)
            outcome = _derive_post_response_outcome(
                sender_text=parsed.get("text", ""),
                reply_text=final_reply,
                live_context=live_context,
                send_status=send_status if sent else 200,
                send_result=send_result,
            )
            build_human_identity_feedback(
                sender=parsed["sender"],
                event_id=parsed.get("message_id"),
                outcome_label=outcome_label if not sent else outcome["outcome_label"],
                outcome_confidence=outcome["outcome_confidence"],
                impact_level=outcome["impact_level"],
                notes=outcome["notes"],
                data_root=str(DATA_DIR),
            )
            self.send_json(
                200,
                {
                    "ok": True,
                    "reply": final_reply,
                    "send": send_result,
                    "sent": sent,
                    "controller_decision": controller_result["decision"],
                    "reason_codes": controller_result.get("reason_codes", []),
                    "relationship": live_context["relationship"],
                    "intent": live_context["intent"],
                    "policy_decision": live_context["permission"]["decision"],
                    "personality_profile": live_context["personality"].get("profile"),
                    "data_shield": "blocked" if blocked else "ok",
                },
            )
        except Exception as exc:
            log_event(
                "gateway_error",
                sender=parsed.get("sender"),
                text=parsed.get("text"),
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            emergency_reply = emergency_non_silent_reply(parsed.get("text", ""))
            controller_input = {
                "sender": parsed.get("sender"),
                "relationship": parsed.get("relationship_tag") or "UNKNOWN",
                "relationship_tag": parsed.get("relationship_tag") or "UNKNOWN",
                "message_id": parsed.get("message_id"),
                "inbound_text": parsed.get("text", ""),
                "original_reply": emergency_reply,
                "proposed_reply": emergency_reply,
                "retrieval_used": False,
                "retrieval_match_found": False,
                "openai_used": False,
                "confidence": 0,
                "is_test_message": False,
                "last_bot_reply": "",
                "last_human_reply_time": 0,
                "last_inbound_message_id": "",
                "recent_replies": [],
                "intent": "emergency",
                "language": detect_language(parsed.get("text", "")),
                "private_or_sensitive_flags": ["gateway_error"],
            }
            controller_result = outbound_safety_controller(controller_input)
            controller_result["decision"] = "DRAFT_FOR_OMAR"
            controller_result["reason_codes"] = list(dict.fromkeys(controller_result.get("reason_codes", []) + ["gateway_error_draft"]))
            log_outbound_decision(
                controller_input,
                controller_result,
                original_reply=emergency_reply,
                rewritten_reply=emergency_reply,
                final_reply=emergency_reply,
                sent=False,
                send_result={},
                outcome_label="drafted_for_omar",
                live_context={},
            )
            self.send_json(200, {"ok": True, "emergency_reply": True, "sent": False, "controller_decision": "DRAFT_FOR_OMAR", "reply": emergency_reply})
        finally:
            if state_session:
                _persist_state_session(state_session)

    def log_message(self, fmt, *args):
        return


def main():
    load_relationship_store()
    init_runtime_state_db()
    start_airtable_replay_worker()
    log_event(
        "gateway_start",
        host=HOST,
        port=PORT,
        openai_endpoint=OPENAI_ENDPOINT,
        relationship_assignment_strategy=RELATIONSHIP_ASSIGNMENT_STRATEGY,
        stress_relationship_overrides=len(AIOS_STRESS_RELATIONSHIP_TAG_MAP),
        airtable_configured=airtable_is_configured(),
        airtable_replay_worker=True,
    )
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
