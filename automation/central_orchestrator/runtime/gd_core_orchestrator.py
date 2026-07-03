#!/usr/bin/env python3
"""GD Core Orchestrator.

One safe local entry point for AIOS events. It does not send messages, mutate
CRM rows, create calendar events, or call external APIs. It classifies the
event, reuses existing AIOS modules when available, and returns the single
writeback/health contract that n8n or another approved runner can execute.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
AUTOMATION_ROOT = AIOS_ROOT / "automation"

CHANNEL_ALIASES = {
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "twilio": "whatsapp",
    "wasenderapi": "whatsapp",
    "meta_cloud_api": "whatsapp",
    "gmail": "gmail",
    "email": "gmail",
    "calendar": "calendar",
    "google_calendar": "calendar",
    "drive": "document",
    "google_drive": "document",
    "document": "document",
    "file": "document",
    "content": "content_factory",
    "marketing": "content_factory",
    "social": "content_factory",
    "dashboard": "command_center",
    "health": "command_center",
    "command": "command_center",
}

RISK_TERMS = {
    "aml",
    "bank",
    "banking",
    "cheque",
    "commission dispute",
    "contract",
    "court",
    "deposit",
    "dld",
    "ejari",
    "emirates id",
    "final offer",
    "government",
    "legal",
    "mortgage approval",
    "passport",
    "payment",
    "poa",
    "power of attorney",
    "refund",
    "rera",
    "title deed",
    "transfer",
    "visa",
}

CONTENT_TERMS = {
    "caption",
    "campaign",
    "flyer",
    "brochure",
    "presentation",
    "reel",
    "video",
    "post",
    "script",
    "thumbnail",
}

PROPERTY_TERMS = {
    "apartment",
    "budget",
    "buy",
    "buyer",
    "investment",
    "listing",
    "property",
    "rent",
    "roi",
    "sell",
    "tenant",
    "valuation",
    "villa",
    "yield",
}

OPERATIONS_TERMS = {
    "approval",
    "dld",
    "ejari",
    "handover",
    "mortgage",
    "nakheel",
    "noc",
    "off-plan",
    "rera",
    "transfer",
}


def _load_module(name: str, path: Path, extra_path: Path | None = None) -> Any:
    if extra_path:
        sys.path.insert(0, str(extra_path))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_from_event(event: dict[str, Any]) -> str:
    fields = [
        "text",
        "body",
        "message_text",
        "Body",
        "subject",
        "summary",
        "title",
        "description",
        "document_text",
        "prompt",
        "request",
        "command",
    ]
    return " ".join(str(event.get(field, "")) for field in fields if event.get(field)).strip()


def _detect_channel(event: dict[str, Any]) -> str:
    explicit = str(event.get("channel") or event.get("source") or event.get("provider") or "").lower().strip()
    if explicit in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[explicit]
    if "SmsMessageSid" in event or str(event.get("From", "")).startswith("whatsapp:"):
        return "whatsapp"
    if "entry" in event or event.get("object") == "whatsapp_business_account":
        return "whatsapp"
    if event.get("email") or event.get("from_email") or event.get("subject"):
        return "gmail"
    if event.get("start") or event.get("end") or event.get("event_time"):
        return "calendar"
    if event.get("document_text") or event.get("file_path") or event.get("mime_type"):
        return "document"
    text = _text_from_event(event).lower()
    if any(term in text for term in CONTENT_TERMS):
        return "content_factory"
    if any(term in text for term in ("status", "health", "dashboard", "briefing")):
        return "command_center"
    return "manual"


def _risk_flags(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(term for term in RISK_TERMS if term in lowered)


def _business_domain(text: str, channel: str) -> str:
    lowered = text.lower()
    if channel == "document":
        return "knowledge_vault"
    if channel == "content_factory":
        return "content_factory"
    if channel == "command_center":
        return "command_center"
    if any(term in lowered for term in CONTENT_TERMS):
        return "content_factory"
    if any(term in lowered for term in OPERATIONS_TERMS):
        return "operations"
    if any(term in lowered for term in PROPERTY_TERMS):
        return "property_intelligence"
    if channel in {"gmail", "calendar"}:
        return "operations"
    return "crm"


def _priority(text: str, risk_flags: list[str]) -> str:
    lowered = text.lower()
    if risk_flags or any(term in lowered for term in ("urgent", "today", "asap", "now", "cash buyer")):
        return "Hot"
    if any(term in lowered for term in ("buy", "sell", "rent", "budget", "offer", "viewing", "campaign")):
        return "Warm"
    return "Normal"


def _load_whatsapp(payload: dict[str, Any]) -> dict[str, Any]:
    gateway_dir = AUTOMATION_ROOT / "whatsapp_provider_gateway" / "runtime"
    gateway = _load_module(
        "whatsapp_provider_gateway",
        gateway_dir / "whatsapp_provider_gateway.py",
        gateway_dir,
    )
    return gateway.process(payload)


def _load_lead_pipeline(lead: dict[str, Any]) -> dict[str, Any]:
    lead_dir = AUTOMATION_ROOT / "lead_pipeline_os" / "runtime"
    engine = _load_module("lead_pipeline_engine", lead_dir / "lead_pipeline_engine.py", lead_dir)
    return engine.build(lead)


def _load_crm_score(lead: dict[str, Any]) -> dict[str, Any]:
    crm_dir = AUTOMATION_ROOT / "crm_business_os" / "runtime"
    scorer = _load_module("crm_lead_scorer", crm_dir / "crm_lead_scorer.py", crm_dir)
    return scorer.score_lead(lead)


def _load_interaction_contract(event: dict[str, Any]) -> dict[str, Any]:
    interaction = _load_module(
        "aios_interaction_architecture_runtime",
        RUNTIME_DIR / "aios_interaction_architecture_runtime.py",
        RUNTIME_DIR,
    )
    return interaction.process_interaction(event)


def _base_record(event: dict[str, Any], channel: str, text: str, risk: list[str]) -> dict[str, Any]:
    domain = _business_domain(text, channel)
    priority = _priority(text, risk)
    event_id = event.get("event_id") or event.get("id") or "EVT-" + str(uuid.uuid4())[:8].upper()
    due = datetime.now(timezone.utc) + timedelta(hours=1 if priority == "Hot" else 4 if priority == "Warm" else 24)
    return {
        "event_id": event_id,
        "received_at": _now(),
        "channel": channel,
        "domain": domain,
        "priority": priority,
        "risk_flags": risk,
        "text": text,
        "sla_due_at": due.isoformat(),
    }


def _gmail_plan(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    risky = bool(record["risk_flags"])
    return {
        "classification": {
            "intent": "email_follow_up",
            "domain": record["domain"],
            "priority": record["priority"],
            "human_review_required": risky,
        },
        "actions": {
            "search_contact_history": True,
            "draft_email_reply": True,
            "send_email": False,
            "create_follow_up_task": True,
            "append_comm_log": True,
            "calendar_hand_off": any(term in record["text"].lower() for term in ("meeting", "viewing", "appointment")),
        },
        "writeback": {
            "contact": {
                "Email": event.get("from_email") or event.get("email") or "",
                "Full Name": event.get("from_name") or event.get("name") or "",
                "Source": "Gmail",
                "Updated At": _now(),
            },
            "task": {
                "Task ID": "TASK-" + str(uuid.uuid4())[:8].upper(),
                "Title": f"{record['priority']}: Gmail follow-up",
                "Owner": "Omar",
                "Status": "Open",
                "Due At": record["sla_due_at"],
            },
        },
        "safety_gate": "HOLD_FOR_OMAR_APPROVAL" if risky else "DRAFT_ONLY_NO_SEND",
    }


def _calendar_plan(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return {
        "classification": {
            "intent": "calendar_coordination",
            "domain": "operations",
            "priority": record["priority"],
            "human_review_required": bool(record["risk_flags"]),
        },
        "actions": {
            "load_contact_history": True,
            "check_calendar_availability": True,
            "create_calendar_event": False,
            "create_follow_up_task": True,
            "append_comm_log": True,
        },
        "writeback": {
            "task": {
                "Task ID": "TASK-" + str(uuid.uuid4())[:8].upper(),
                "Title": f"{record['priority']}: Calendar coordination",
                "Owner": "Omar",
                "Status": "Open",
                "Due At": record["sla_due_at"],
            },
            "calendar_request": {
                "Title": event.get("title") or "AIOS calendar request",
                "Start": event.get("start") or event.get("event_time") or "",
                "End": event.get("end") or "",
                "Create Automatically": False,
            },
        },
        "safety_gate": "DRAFT_ONLY_NO_EVENT_CREATE",
    }


def _document_plan(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    doc_type = "unknown"
    lowered = record["text"].lower()
    if "title deed" in lowered:
        doc_type = "title_deed"
    elif "tenancy" in lowered or "ejari" in lowered:
        doc_type = "tenancy_or_ejari"
    elif "noc" in lowered or "approval" in lowered:
        doc_type = "noc_approval"
    elif "passport" in lowered or "emirates id" in lowered:
        doc_type = "identity_document"
    return {
        "classification": {
            "intent": "document_intake",
            "domain": "knowledge_vault",
            "document_type": doc_type,
            "priority": record["priority"],
            "human_review_required": bool(record["risk_flags"]),
        },
        "actions": {
            "classify_document": True,
            "extract_key_facts": True,
            "store_reference_in_drive": False,
            "link_to_contact_or_case": True,
            "append_knowledge_index": True,
            "create_follow_up_task": bool(record["risk_flags"]),
        },
        "writeback": {
            "knowledge_item": {
                "Knowledge ID": "KN-" + str(uuid.uuid4())[:8].upper(),
                "Source": event.get("file_path") or event.get("file_name") or "inline_document_text",
                "Type": doc_type,
                "Summary": record["text"][:280],
                "Indexed At": _now(),
            }
        },
        "safety_gate": "HOLD_FOR_OMAR_APPROVAL" if record["risk_flags"] else "KNOWLEDGE_INDEX_ONLY",
    }


def _content_plan(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    lowered = record["text"].lower()
    asset = "campaign_brief"
    if "reel" in lowered or "video" in lowered:
        asset = "video_brief"
    elif "flyer" in lowered:
        asset = "flyer_brief"
    elif "brochure" in lowered or "presentation" in lowered:
        asset = "presentation_brief"
    elif "caption" in lowered or "post" in lowered:
        asset = "caption_draft"
    return {
        "classification": {
            "intent": "content_factory_request",
            "domain": "content_factory",
            "asset_type": asset,
            "priority": record["priority"],
            "human_review_required": True,
        },
        "actions": {
            "load_brand_guidelines": True,
            "create_draft": True,
            "create_variants": True,
            "publish_content": False,
            "create_marketing_task": True,
            "append_campaign_log": True,
        },
        "writeback": {
            "content_task": {
                "Task ID": "TASK-" + str(uuid.uuid4())[:8].upper(),
                "Title": f"Create {asset.replace('_', ' ')}",
                "Owner": "Omar",
                "Status": "Draft Required",
                "Due At": record["sla_due_at"],
                "Brief": event.get("brief") or record["text"][:500],
            }
        },
        "safety_gate": "DRAFT_ONLY_NO_PUBLISH",
    }


def _command_center_plan(record: dict[str, Any]) -> dict[str, Any]:
    health = {
        "brain": "online_local_router",
        "router": "ready",
        "crm": "writeback_contract_ready",
        "database": "local_state_ready",
        "whatsapp": "provider_gateway_contract_ready",
        "calendar": "handoff_contract_ready",
        "gmail": "draft_contract_ready",
        "drive": "knowledge_contract_ready",
        "follow_up": "task_contract_ready",
    }
    return {
        "classification": {
            "intent": "command_center_health",
            "domain": "command_center",
            "priority": record["priority"],
            "human_review_required": False,
        },
        "actions": {
            "publish_health_view": True,
            "search_everything": "search" in record["text"].lower(),
            "run_workflow": False,
            "append_system_log": True,
        },
        "writeback": {"health": health},
        "safety_gate": "READ_ONLY_HEALTH",
    }


def process(event: dict[str, Any]) -> dict[str, Any]:
    channel = _detect_channel(event)
    text = _text_from_event(event)
    risk = _risk_flags(text)
    record = _base_record(event, channel, text, risk)
    interaction_contract = _load_interaction_contract(
        {**event, "channel": channel, "message": text, "validation_read_only": True}
    )

    module_output: dict[str, Any] = {}
    if channel == "whatsapp":
        module_output["whatsapp_provider_gateway"] = _load_whatsapp(event)
        lead = module_output["whatsapp_provider_gateway"].get("crm", {}).get("lead", {})
        module_output["lead_pipeline"] = _load_lead_pipeline(lead)
        module_output["crm_score"] = _load_crm_score(
            {
                "Lead ID": lead.get("Lead ID"),
                "Message Text": text or module_output["whatsapp_provider_gateway"].get("crm", {}).get("message", {}).get("Message Text", ""),
                "Client Intent": lead.get("Client Intent", ""),
                "Summary": lead.get("Summary", ""),
            }
        )
        plan = {
            "classification": module_output["whatsapp_provider_gateway"].get("classification", {}),
            "actions": module_output["whatsapp_provider_gateway"].get("tool_plan", {}),
            "writeback": module_output["whatsapp_provider_gateway"].get("crm", {}),
            "reply": module_output["whatsapp_provider_gateway"].get("reply", {}),
            "safety_gate": module_output["whatsapp_provider_gateway"].get("safety_gate", "HOLD_FOR_OMAR_APPROVAL"),
        }
        if risk and plan["safety_gate"] == "NO_REPLY_NON_ACTIONABLE":
            plan["safety_gate"] = "HOLD_FOR_OMAR_APPROVAL"
            plan["classification"]["human_takeover_required"] = True
            plan["classification"]["risk_flags"] = sorted(set(plan["classification"].get("risk_flags", []) + risk))
    elif channel == "gmail":
        plan = _gmail_plan(record, event)
    elif channel == "calendar":
        plan = _calendar_plan(record, event)
    elif channel == "document":
        plan = _document_plan(record, event)
    elif channel == "content_factory":
        plan = _content_plan(record, event)
    elif channel == "command_center":
        plan = _command_center_plan(record)
    else:
        plan = _gmail_plan(record, event)
        plan["classification"]["intent"] = "manual_aios_request"
        plan["safety_gate"] = "DRAFT_ONLY_NO_EXTERNAL_ACTION"

    return {
        "aios_event": record,
        "brain": {
            "name": "GD Core Intelligence",
            "version": "2026-06-21-local-router",
            "mode": "safe_local_no_external_side_effects",
            "one_brain_contract": True,
        },
        "interaction_contract": interaction_contract,
        "route": plan,
        "module_output": module_output,
        "command_center_health": _command_center_plan(record)["writeback"]["health"],
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
        },
    }


def _parse_stdin() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


if __name__ == "__main__":
    print(json.dumps(process(_parse_stdin()), indent=2, ensure_ascii=False))
