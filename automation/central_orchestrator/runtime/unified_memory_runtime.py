#!/usr/bin/env python3
"""Build AIOS unified memory context packets.

This runtime joins local AIOS reports, approval state, action packets, and
WhatsApp conversation state into reusable context packets for the one-brain
operating layer. It is read-only: no CRM, Airtable, Notion, Drive, vector,
message, or file-sync writes are performed.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios_context_store import build_context_object as build_contact_context_object


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "UNIFIED_MEMORY_REPORT.json"
CONVERSATION_DB = AIOS_ROOT / "automation" / "whatsapp_provider_gateway" / "state" / "conversation_state.sqlite"

SOURCE_REPORTS = {
    "command_center": "COMMAND_CENTER_DATA.json",
    "property_intelligence": "PROPERTY_INTELLIGENCE_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "knowledge_vault": "KNOWLEDGE_VAULT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "mobile_command": "MOBILE_COMMAND_REPORT.json",
    "ceo_operating": "CEO_OPERATING_REPORT.json",
    "impact_metrics": "IMPACT_METRICS_REPORT.json",
    "approval_state": "APPROVAL_STATE.json",
    "action_queue": "ACTION_QUEUE.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "messages_sent": False,
    "whatsapp_messages_sent": False,
    "gmail_drafts_created": False,
    "gmail_messages_sent": False,
    "calendar_events_created": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "notion_pages_created": False,
    "vector_db_written": False,
    "documents_uploaded": False,
    "external_search_called": False,
    "conversation_state_written": False,
}


REQUIRED_CONTEXT_FIELDS = [
    "relationship",
    "dna",
    "weather",
    "history_summary",
    "confidence",
    "source",
    "decay_metadata",
]


def _compose_contact_context(phone: str, conversation: dict[str, Any]) -> dict[str, Any]:
    stored = build_contact_context_object(phone, {
        "relationship_tag": conversation.get("relationship_tag", "UNKNOWN"),
        "relationship_history_summary": conversation.get("relationship_history_summary", "new contact"),
        "history_summary": conversation.get("recent_summary", "No prior interaction history available."),
        "dna": conversation.get("dna"),
        "weather": conversation.get("weather", "not_available"),
        "confidence": float(conversation.get("confidence", 0.4) or 0.4),
        "confidence_source": "unified_memory_load",
        "source": "relationship_memory_runtime",
        "retrieval_last_count": int(conversation.get("retrieval_last_count", 0) or 0),
        "intent": conversation.get("intent", "unknown"),
        "profile_summary": conversation.get("history_summary", "No profile summary persisted for this contact yet."),
    })

    return {
        k: stored.get(k) for k in REQUIRED_CONTEXT_FIELDS
        if k in stored
    } | {
        "contact_phone": stored.get("contact_phone"),
        "stored_at": stored.get("updated_at") or stored.get("created_at"),
        "relationship": stored.get("relationship_tag"),
        "exists": bool(stored.get("exists", False)),
        "decay_metadata": stored.get("decay_metadata", {}),
    }


def _build_relationship_context(conversations: dict[str, Any], focus_phone: str | None) -> dict[str, Any]:
    if not focus_phone:
        return {"status": "not_available", "history_summary": "No contact selected for context object."}

    normalized = re.sub(r"\D", "", str(focus_phone))
    if not normalized:
        return {"status": "not_available", "history_summary": "Invalid contact phone for lookup."}

    relationship_summary = []
    for message in conversations.get("recent_messages", [])[:3]:
        relationship_summary.append(message.get("excerpt", ""))
    recent_summary = " | ".join([part for part in relationship_summary if part]) or "No recent conversation snippets found."

    return _compose_contact_context(normalized, {
        "relationship_tag": conversations.get("focus_relationship_tag", "UNKNOWN"),
        "relationship_history_summary": f"Messages: {len(conversations.get('recent_messages', []) )}",
        "history_summary": recent_summary,
        "confidence": 0.76 if conversations.get("recent_messages") else 0.42,
        "dna": conversations.get("dna", {"behavioral": "repeat_user", "channel": conversations.get("source", "unknown")}),
        "weather": conversations.get("weather", "not_available"),
        "intent": conversations.get("intent", "unknown"),
        "retrieval_last_count": len(conversations.get("recent_messages", [])),
    })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _excerpt(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _conversation_state() -> dict[str, Any]:
    summary = {
        "db_path": CONVERSATION_DB.relative_to(AIOS_ROOT).as_posix(),
        "db_exists": CONVERSATION_DB.exists(),
        "conversation_count": 0,
        "message_count": 0,
        "reply_decision_count": 0,
        "recent_conversations": [],
        "recent_messages": [],
        "recent_reply_decisions": [],
        "read_only": True,
    }
    if not CONVERSATION_DB.exists():
        return summary
    con = sqlite3.connect(CONVERSATION_DB)
    con.row_factory = sqlite3.Row
    try:
        summary["conversation_count"] = con.execute("select count(*) from conversations").fetchone()[0]
        summary["message_count"] = con.execute("select count(*) from messages").fetchone()[0]
        summary["reply_decision_count"] = con.execute("select count(*) from reply_decisions").fetchone()[0]
        summary["recent_conversations"] = [
            {
                "contact_phone": row["contact_phone"],
                "provider": row["provider"],
                "profile_name": row["profile_name"],
                "last_lead_id": row["last_lead_id"],
                "ai_enabled": bool(row["ai_enabled"]),
                "updated_at": row["updated_at"],
            }
            for row in con.execute(
                "select contact_phone, provider, profile_name, last_lead_id, ai_enabled, updated_at from conversations order by updated_at desc limit 5"
            )
        ]
        summary["recent_messages"] = [
            {
                "message_id": row["message_id"],
                "contact_phone": row["contact_phone"],
                "direction": row["direction"],
                "lead_id": row["lead_id"],
                "excerpt": _excerpt(row["message_text"], 120),
                "received_at": row["received_at"],
            }
            for row in con.execute(
                "select message_id, contact_phone, direction, lead_id, message_text, received_at from messages order by coalesce(received_at, processed_at) desc limit 6"
            )
        ]
        summary["recent_reply_decisions"] = [
            {
                "decision_id": row["decision_id"],
                "contact_phone": row["contact_phone"],
                "lead_id": row["lead_id"],
                "final_mode": row["final_mode"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in con.execute(
                "select decision_id, contact_phone, lead_id, final_mode, reason, created_at from reply_decisions order by created_at desc limit 6"
            )
        ]
    finally:
        con.close()
    return summary


def _build_contact_slice(context_packets: list[dict[str, Any]], conversations: dict[str, Any], focus_phone: str | None) -> dict[str, Any]:
    if not focus_phone:
        return {
            "contact_phone": None,
            "matched_packets": [packet["packet_id"] for packet in context_packets],
            "conversation_state": conversations,
        }
    normalized_phone = re.sub(r"\D", "", str(focus_phone))
    contact_messages = [
        message
        for message in conversations.get("recent_messages", [])
        if normalized_phone and normalized_phone in str(message.get("contact_phone") or "")
    ]
    return {
        "contact_phone": focus_phone,
        "matched_packets": [packet["packet_id"] for packet in context_packets],
        "conversation_state": {
            **conversations,
            "matched_recent_messages": contact_messages,
            "matched_reply_decisions": [
                row
                for row in conversations.get("recent_reply_decisions", [])
                if normalized_phone and normalized_phone in str(row.get("contact_phone") or "")
            ],
        },
    }


def build_context_packets(reports: dict[str, dict[str, Any]], conversations: dict[str, Any]) -> list[dict[str, Any]]:
    crm = reports["crm_followup"]
    operations = reports["operations_assistant"]
    property_report = reports["property_intelligence"]
    knowledge = reports["knowledge_vault"]
    content = reports["content_factory"]
    ceo = reports["ceo_operating"]
    impact = reports["impact_metrics"]
    approvals = reports["approval_state"]
    packets: list[dict[str, Any]] = [
        {
            "packet_id": "MEM-EXEC-OMAR",
            "subject": "Omar Executive Operating Context",
            "memory_type": "executive",
            "priority": "P1",
            "summary": f"{len(ceo.get('priority_stack', []))} CEO priorities, {approvals.get('pending_count', 0)} pending approvals, {impact.get('quality_metrics', {}).get('estimated_weekly_hours_saved', 0)} projected weekly hours saved.",
            "evidence": [
                "CEO_OPERATING_REPORT.json",
                "IMPACT_METRICS_REPORT.json",
                "APPROVAL_STATE.json",
            ],
            "retrieval_commands": ["@ceo", "@impact", "@approve-local"],
            "writeback_contracts": ["airtable_task", "notion_page", "dashboard_log"],
            "writeback_enabled": False,
        },
        {
            "packet_id": "MEM-CRM-HOT-LEADS",
            "subject": "CRM Follow-Up Context",
            "memory_type": "crm",
            "priority": "P1",
            "summary": f"{crm.get('dashboard', {}).get('hot_leads', 0)} hot leads, {crm.get('dashboard', {}).get('open_tasks', 0)} open tasks, {crm.get('dashboard', {}).get('stale_risk_count', 0)} stale-risk cases.",
            "evidence": ["CRM_FOLLOWUP_REPORT.json", "MOBILE_COMMAND_REPORT.json"],
            "retrieval_commands": ["@crm-followup", "@mobile-command"],
            "writeback_contracts": ["airtable_lead_update", "gmail_draft", "whatsapp_draft"],
            "writeback_enabled": False,
        },
        {
            "packet_id": "MEM-PROPERTY-RECOMMENDATION",
            "subject": "Property Recommendation Context",
            "memory_type": "property",
            "priority": "P2",
            "summary": f"{property_report.get('matched_count', 0)} matched options and {len(property_report.get('community_context', {}))} market contexts loaded.",
            "evidence": ["PROPERTY_INTELLIGENCE_REPORT.json", "KNOWLEDGE_VAULT_REPORT.json"],
            "retrieval_commands": ["@property-intel", "@knowledge-vault"],
            "writeback_contracts": ["airtable_opportunity", "whatsapp_draft", "drive_draft"],
            "writeback_enabled": False,
        },
        {
            "packet_id": "MEM-OPERATIONS-COMPLIANCE",
            "subject": "Operations and Compliance Context",
            "memory_type": "operations",
            "priority": "P1",
            "summary": f"{operations.get('case_count', 0)} operations cases, AED {float(operations.get('fee_calculator', {}).get('total_estimated_cash_to_close', 0)):,.0f} validation cash-to-close model.",
            "evidence": ["OPERATIONS_ASSISTANT_REPORT.json", "KNOWLEDGE_VAULT_REPORT.json"],
            "retrieval_commands": ["@operations", "@dld", "@noc", "@knowledge-vault"],
            "writeback_contracts": ["notion_case_note", "drive_draft", "airtable_task"],
            "writeback_enabled": False,
        },
        {
            "packet_id": "MEM-CONTENT-CAMPAIGN",
            "subject": "Content Factory Context",
            "memory_type": "content",
            "priority": "P2",
            "summary": f"{content.get('artifact_count', 0)} draft artifacts and {len(content.get('compliance_checks', []))} compliance checks staged.",
            "evidence": ["CONTENT_FACTORY_REPORT.json", "IMPACT_METRICS_REPORT.json"],
            "retrieval_commands": ["@content-factory", "@impact"],
            "writeback_contracts": ["drive_draft", "instagram_draft", "airtable_content_task"],
            "writeback_enabled": False,
        },
        {
            "packet_id": "MEM-KNOWLEDGE-VAULT",
            "subject": "Knowledge Retrieval Context",
            "memory_type": "knowledge",
            "priority": "P2",
            "summary": f"{knowledge.get('asset_count', 0)} assets across {len(knowledge.get('categories', {}))} categories with {len(knowledge.get('retrieval_results', []))} validation queries.",
            "evidence": ["KNOWLEDGE_VAULT_REPORT.json", "COMMAND_CENTER_DATA.json"],
            "retrieval_commands": ["@knowledge-vault", "@ask"],
            "writeback_contracts": ["notion_page", "vector_index_future", "drive_sync_future"],
            "writeback_enabled": False,
        },
        {
            "packet_id": "MEM-WHATSAPP-CONTEXT",
            "subject": "WhatsApp Conversation Context",
            "memory_type": "conversation",
            "priority": "P1",
            "summary": f"{conversations.get('conversation_count', 0)} conversations, {conversations.get('message_count', 0)} messages, {conversations.get('reply_decision_count', 0)} reply decisions available read-only.",
            "evidence": ["conversation_state.sqlite", "MOBILE_COMMAND_REPORT.json"],
            "retrieval_commands": ["@whatsapp", "@mobile-command", "@crm-followup"],
            "writeback_contracts": ["whatsapp_draft", "airtable_contact_update", "conversation_state_future"],
            "writeback_enabled": False,
        },
    ]
    return packets


def build_retrieval_map(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routes = []
    for packet in packets:
        for command in packet["retrieval_commands"]:
            routes.append(
                {
                    "command": command,
                    "packet_id": packet["packet_id"],
                    "subject": packet["subject"],
                    "memory_type": packet["memory_type"],
                    "writeback_enabled": False,
                }
            )
    return routes


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    conversations = _conversation_state()
    packets = build_context_packets(reports, conversations)
    focus_phone = payload.get("phone") or payload.get("contact_phone")
    focus_layer = _build_contact_slice(packets, conversations, str(focus_phone) if focus_phone else None)
    contact_context = _build_relationship_context(conversations, str(focus_phone) if focus_phone else None)

    focus_layer["context_object"] = {
        **contact_context,
        "required_fields": REQUIRED_CONTEXT_FIELDS,
    }

    result = {
        "generated_at": _now(),
        "context_version": "2.0",
        "mode": "safe_local_unified_memory_no_external_side_effects",
        "memory_packet_count": len(packets),
        "memory_types": sorted({packet["memory_type"] for packet in packets}),
        "context_packets": packets,
        "retrieval_map": build_retrieval_map(packets),
        "conversation_state": focus_layer["conversation_state"] if payload.get("focus_mode") == "contact" else conversations,
        "focus_view": focus_layer,
        "context_object": focus_layer.get("context_object", {}),
        "source_reports": SOURCE_REPORTS,
        "recommended_next_actions": [
            "Use memory packets before drafting client replies, property recommendations, NOC answers, or campaign copy.",
            "Promote writeback contracts to live Airtable/Notion/Drive/vector sync only after connector credentials and explicit approval.",
            "Keep WhatsApp conversation state read-only until the live provider path is approved.",
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
