#!/usr/bin/env python3
"""Build a local Mobile Command report for AIOS.

The runtime turns phone commands and voice-note transcripts into safe AIOS
mobile actions. It prepares local notifications, search routes, task drafts,
and connector handoff contracts without sending messages, creating calendar
events, writing CRM rows, or modifying external apps.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "MOBILE_COMMAND_REPORT.json"

SOURCE_PATHS = {
    "mobile_app": "AIOS-MOBILE-APP.html",
    "dashboard": "AIOS-DASHBOARD.html",
    "ask_aios": "automation/central_orchestrator/runtime/ask_aios.py",
    "core_orchestrator": "automation/central_orchestrator/runtime/gd_core_orchestrator.py",
    "property_intelligence": "automation/central_orchestrator/runtime/property_intelligence_runtime.py",
    "operations_assistant": "automation/central_orchestrator/runtime/operations_assistant_runtime.py",
    "crm_followup": "automation/central_orchestrator/runtime/crm_followup_runtime.py",
    "knowledge_vault": "automation/central_orchestrator/runtime/knowledge_vault_runtime.py",
    "content_factory": "automation/central_orchestrator/runtime/content_factory_runtime.py",
}

DEFAULT_COMMANDS = [
    {
        "command_id": "MOB-001",
        "input_type": "typed",
        "text": "Find JVC 2 bed options under AED 1m and prepare WhatsApp reply",
    },
    {
        "command_id": "MOB-002",
        "input_type": "voice",
        "transcript": "Remind me to follow up with the Palm seller tomorrow and draft a valuation email",
    },
    {
        "command_id": "MOB-003",
        "input_type": "typed",
        "text": "Show DLD transfer checklist with mortgage cash to close",
    },
    {
        "command_id": "MOB-004",
        "input_type": "voice",
        "transcript": "Find title deed and NOC documents for Nakheel approval package",
    },
    {
        "command_id": "MOB-005",
        "input_type": "typed",
        "text": "Create Instagram caption and reel script for Dubai Hills listing",
    },
]

INTENT_RULES = [
    {
        "intent": "property_search",
        "panel": "search",
        "command": "@property-intel",
        "keywords": ["property", "jvc", "bed", "buy", "budget", "shortlist", "options", "listing"],
        "connector_contracts": ["whatsapp_draft", "airtable_task"],
    },
    {
        "intent": "lead_follow_up",
        "panel": "work",
        "command": "@crm-followup",
        "keywords": ["follow up", "seller", "buyer", "lead", "client", "valuation", "reply"],
        "connector_contracts": ["gmail_draft", "calendar_read", "airtable_task"],
    },
    {
        "intent": "operations_assistant",
        "panel": "ops",
        "command": "@operations",
        "keywords": ["dld", "rera", "noc", "ejari", "transfer", "mortgage", "visa", "checklist"],
        "connector_contracts": ["drive_draft", "notion"],
    },
    {
        "intent": "document_search",
        "panel": "comms",
        "command": "@knowledge-vault",
        "keywords": ["document", "contract", "title deed", "drive", "noc", "approval package", "file"],
        "connector_contracts": ["drive_draft", "notion"],
    },
    {
        "intent": "content_factory",
        "panel": "ops",
        "command": "@content-factory",
        "keywords": ["caption", "reel", "instagram", "campaign", "flyer", "brochure", "video", "content"],
        "connector_contracts": ["instagram_draft", "drive_draft"],
    },
]

EXTERNAL_SIDE_EFFECTS = {
    "messages_sent": False,
    "whatsapp_messages_sent": False,
    "whatsapp_broadcasts_sent": False,
    "gmail_drafts_created": False,
    "gmail_messages_sent": False,
    "calendar_events_created": False,
    "calendar_events_updated": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "notion_pages_created": False,
    "instagram_posts_published": False,
    "content_assets_generated": False,
    "notifications_pushed_to_device": False,
    "voice_audio_recorded": False,
    "external_transcription_called": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _command_text(command: dict[str, Any]) -> str:
    return _text(command.get("text") or command.get("transcript") or command.get("voice_note") or command.get("command"))


def _voice_summary(text: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return {
        "transcript": normalized,
        "normalized_command": normalized[:1].upper() + normalized[1:] if normalized else "",
        "capture_mode": "local_transcript_only",
        "audio_recorded": False,
        "external_transcription_called": False,
        "device_permission_required_for_live_voice": True,
    }


def _match_intent(text: str) -> dict[str, Any]:
    lowered = text.lower()
    scored = []
    for rule in INTENT_RULES:
        score = sum(1 for keyword in rule["keywords"] if keyword in lowered)
        scored.append((score, rule))
    score, best = max(scored, key=lambda item: item[0])
    if score <= 0:
        best = {
            "intent": "ask_aios",
            "panel": "home",
            "command": "@ask",
            "connector_contracts": [],
        }
    return {**best, "match_score": score}


def _priority_for(intent: str, text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["today", "tomorrow", "urgent", "now", "transfer", "mortgage"]):
        return "P1"
    if intent in {"lead_follow_up", "property_search", "operations_assistant"}:
        return "P2"
    return "P3"


def _build_action(command: dict[str, Any]) -> dict[str, Any]:
    text = _command_text(command)
    intent = _match_intent(text)
    command_id = _text(command.get("command_id") or f"MOB-{abs(hash(text)) % 100000:05d}")
    input_type = _text(command.get("input_type") or ("voice" if command.get("transcript") else "typed"))
    priority = _priority_for(intent["intent"], text)
    approval_required = intent["intent"] in {"lead_follow_up", "property_search", "content_factory"}
    connector_contracts = [
        {
            "connector": connector,
            "execution_enabled": False,
            "network_call_enabled": False,
            "approval_required": True,
        }
        for connector in intent.get("connector_contracts", [])
    ]
    action = {
        "command_id": command_id,
        "input_type": input_type,
        "source": "AIOS Mobile Command Console",
        "raw_text": text,
        "intent": intent["intent"],
        "match_score": intent["match_score"],
        "panel": intent["panel"],
        "handoff_command": intent["command"],
        "priority": priority,
        "status": "staged_local_only",
        "approval_required": approval_required,
        "external_execution_enabled": False,
        "suggested_reply": suggested_reply(intent["intent"], text),
        "connector_contracts": connector_contracts,
    }
    if input_type == "voice":
        action["voice_command"] = _voice_summary(text)
    return action


def suggested_reply(intent: str, text: str) -> str:
    if intent == "property_search":
        return "I will shortlist local property matches, check availability, and prepare a draft WhatsApp reply for Omar approval."
    if intent == "lead_follow_up":
        return "I will stage the follow-up task and prepare draft communication. No email or calendar write will happen automatically."
    if intent == "operations_assistant":
        return "I will open the relevant DLD/RERA/NOC checklist and calculate the local case requirements."
    if intent == "document_search":
        return "I will search the local knowledge vault and prepare a Drive/Notion reference contract only."
    if intent == "content_factory":
        return "I will prepare draft content assets and social copy for review. Nothing will be generated or published externally."
    return "I will route this through Ask AIOS and keep the result local."


def build_notifications(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notifications = []
    for action in actions:
        title = {
            "property_search": "Property search staged",
            "lead_follow_up": "Follow-up task ready",
            "operations_assistant": "Operations checklist ready",
            "document_search": "Document search staged",
            "content_factory": "Content draft staged",
        }.get(action["intent"], "AIOS command staged")
        notifications.append(
            {
                "notification_id": "NOTIF-" + action["command_id"],
                "title": title,
                "summary": action["suggested_reply"],
                "priority": action["priority"],
                "panel": action["panel"],
                "push_sent": False,
                "approval_required": action["approval_required"],
            }
        )
    return sorted(notifications, key=lambda item: item["priority"])


def build_mobile_panels(actions: list[dict[str, Any]], notifications: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "home": {
            "notifications": notifications,
            "health_keys": ["brain", "router", "crm", "database", "whatsapp", "calendar", "gmail", "drive", "follow_up", "content_factory"],
        },
        "search": {
            "property_actions": [action for action in actions if action["intent"] == "property_search"],
            "lead_actions": [action for action in actions if action["intent"] == "lead_follow_up"],
            "search_everything_enabled": True,
        },
        "work": {
            "tasks": [
                {
                    "task_id": "TASK-" + action["command_id"],
                    "title": action["suggested_reply"],
                    "priority": action["priority"],
                    "status": "local_staged",
                    "approval_required": action["approval_required"],
                }
                for action in actions
                if action["intent"] in {"lead_follow_up", "property_search", "operations_assistant"}
            ],
            "calendar_contracts": [
                contract
                for action in actions
                for contract in action["connector_contracts"]
                if contract["connector"] == "calendar_read"
            ],
        },
        "comms": {
            "gmail_contracts": [
                contract
                for action in actions
                for contract in action["connector_contracts"]
                if contract["connector"] == "gmail_draft"
            ],
            "document_contracts": [
                contract
                for action in actions
                for contract in action["connector_contracts"]
                if contract["connector"] in {"drive_draft", "notion"}
            ],
            "whatsapp_contracts": [
                contract
                for action in actions
                for contract in action["connector_contracts"]
                if contract["connector"] == "whatsapp_draft"
            ],
        },
        "ops": {
            "operations_actions": [action for action in actions if action["intent"] == "operations_assistant"],
            "voice_commands": [action["voice_command"] for action in actions if action.get("voice_command")],
            "content_actions": [action for action in actions if action["intent"] == "content_factory"],
        },
    }


def build_capabilities() -> list[dict[str, Any]]:
    return [
        {"capability": "Ask AIOS", "status": "local_query_ready", "live_write_enabled": False},
        {"capability": "Property Search", "status": "routes_to_property_intelligence", "live_write_enabled": False},
        {"capability": "Lead Search", "status": "routes_to_crm_followup", "live_write_enabled": False},
        {"capability": "Tasks", "status": "local_task_staging_ready", "live_write_enabled": False},
        {"capability": "Calendar", "status": "read_contract_only", "live_write_enabled": False},
        {"capability": "Gmail", "status": "draft_contract_only", "live_write_enabled": False},
        {"capability": "Documents", "status": "drive_knowledge_contract_only", "live_write_enabled": False},
        {"capability": "Operations Assistant", "status": "local_checklist_runtime_ready", "live_write_enabled": False},
        {"capability": "Notifications", "status": "local_feed_ready_push_disabled", "live_write_enabled": False},
        {"capability": "Voice Commands", "status": "transcript_contract_ready_device_permission_required", "live_write_enabled": False},
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    commands = payload.get("commands") or DEFAULT_COMMANDS
    actions = [_build_action(command) for command in commands]
    notifications = build_notifications(actions)
    panels = build_mobile_panels(actions, notifications)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_mobile_command_runtime_no_external_side_effects",
        "mobile_app_path": "AIOS-MOBILE-APP.html",
        "command_count": len(actions),
        "voice_command_count": len([action for action in actions if action.get("voice_command")]),
        "notification_count": len(notifications),
        "capabilities": build_capabilities(),
        "actions": actions,
        "notifications": notifications,
        "mobile_panels": panels,
        "workflow_handoffs": [
            {"command": "@ask", "scope": "Ask AIOS local answer"},
            {"command": "@property-intel", "scope": "mobile property search and recommendation"},
            {"command": "@crm-followup", "scope": "mobile lead follow-up and task staging"},
            {"command": "@operations", "scope": "mobile DLD/RERA/NOC checklist support"},
            {"command": "@knowledge-vault", "scope": "mobile document and SOP retrieval"},
            {"command": "@content-factory", "scope": "mobile content draft requests"},
        ],
        "source_paths": list(SOURCE_PATHS.values()),
        "recommended_next_actions": [
            "Use the mobile report as the phone UI data source for notifications and staged actions.",
            "Keep live voice capture behind device permission and explicit transcription approval.",
            "Keep Gmail, Calendar, WhatsApp, Drive, Airtable, Notion, and Instagram execution disabled until final connector activation.",
        ],
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
