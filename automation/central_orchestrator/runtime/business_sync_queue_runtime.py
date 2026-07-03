#!/usr/bin/env python3
"""Build the AIOS business sync queue.

This runtime converts the canonical business data model into local connector
sync packets. It is a rehearsal queue only: no Airtable rows, Drive files,
Gmail drafts, Calendar events, Notion pages, WhatsApp messages, Instagram
posts, n8n imports, or future-channel writes are executed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "BUSINESS_SYNC_QUEUE_REPORT.json"

SOURCE_REPORTS = {
    "business_data_model": "BUSINESS_DATA_MODEL_REPORT.json",
    "connector_readiness": "CONNECTOR_READINESS_REPORT.json",
    "connector_activation": "CONNECTOR_ACTIVATION_COMMAND_PLAN.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "property_intelligence": "PROPERTY_INTELLIGENCE_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "knowledge_vault": "KNOWLEDGE_VAULT_REPORT.json",
    "approval_state": "APPROVAL_STATE.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "drive_files_created": False,
    "drive_files_shared": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "notion_pages_created": False,
    "whatsapp_messages_sent": False,
    "instagram_posts_published": False,
    "n8n_workflows_imported": False,
    "future_channel_messages_sent": False,
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _entity_source_count(entity: str, reports: dict[str, dict[str, Any]]) -> int:
    if entity in {"lead", "contact"}:
        return int(reports["crm_followup"].get("lead_count", 0))
    if entity == "property":
        return int(reports["property_intelligence"].get("matched_count", 0))
    if entity in {"deal", "calendar_event"}:
        return int(reports["operations_assistant"].get("case_count", 0))
    if entity == "task":
        return len(reports["crm_followup"].get("follow_up_tasks", [])) or reports["approval_state"].get("pending_count", 0)
    if entity == "communication":
        return len(reports["crm_followup"].get("draft_messages", []))
    if entity == "document":
        return len(reports["knowledge_vault"].get("document_cases", []))
    if entity == "content_asset":
        return int(reports["content_factory"].get("artifact_count", 0))
    if entity == "approval":
        return len(reports["approval_state"].get("approvals", []))
    if entity == "workflow":
        return 1
    if entity == "knowledge_asset":
        return int(reports["knowledge_vault"].get("asset_count", 0))
    return 0


def build_sync_packets(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    data_model = reports["business_data_model"]
    connector_status = {
        item.get("connector"): item.get("status", "unknown")
        for item in reports["connector_readiness"].get("connectors", [])
    }
    packets: list[dict[str, Any]] = []
    for mapping in data_model.get("connector_mappings", []):
        connector = mapping.get("connector", "unknown")
        for entity in mapping.get("entities", []):
            source_count = _entity_source_count(entity, reports)
            packets.append(
                {
                    "packet_id": f"SYNC-{connector.upper()}-{entity.upper()}",
                    "connector": connector,
                    "entity": entity,
                    "target": mapping.get("target", ""),
                    "source_record_count": source_count,
                    "connector_status": connector_status.get(connector, "planned_contract_only"),
                    "operation_contract": _operation_for(connector, entity),
                    "approval_gate": _gate_for(connector, entity),
                    "write_enabled": False,
                    "execution_enabled": False,
                    "network_call_enabled": False,
                    "credentials_included": False,
                    "ready_for_live_sync": False,
                }
            )
    return packets


def _operation_for(connector: str, entity: str) -> str:
    if connector == "airtable":
        return f"upsert_{entity}_record"
    if connector == "google_drive":
        return f"stage_{entity}_file_contract"
    if connector == "gmail":
        return f"stage_{entity}_draft_contract"
    if connector == "google_calendar":
        return f"stage_{entity}_event_contract"
    if connector == "notion":
        return f"stage_{entity}_page_contract"
    if connector == "whatsapp":
        return f"stage_{entity}_reply_contract"
    if connector == "instagram":
        return f"stage_{entity}_publish_contract"
    if connector == "n8n":
        return f"stage_{entity}_workflow_contract"
    return f"stage_{entity}_future_channel_contract"


def _gate_for(connector: str, entity: str) -> str:
    if connector in {"gmail", "whatsapp", "instagram", "future_channels"}:
        return "OMAR_MESSAGE_OR_PUBLISH_APPROVAL_REQUIRED"
    if connector in {"airtable", "notion", "google_drive"}:
        return "DATA_MAPPING_AND_PERMISSION_APPROVAL_REQUIRED"
    if connector == "google_calendar":
        return "CALENDAR_BOOKING_APPROVAL_REQUIRED"
    if connector == "n8n":
        return "FINAL_LIVE_RUN_APPROVAL_REQUIRED"
    return "CONNECTOR_APPROVAL_REQUIRED"


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    packets = build_sync_packets(reports)
    connectors = sorted({packet["connector"] for packet in packets})
    entities = sorted({packet["entity"] for packet in packets})
    blocked_packets = [packet for packet in packets if packet["ready_for_live_sync"] is False]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_business_sync_queue_no_external_side_effects",
        "summary": {
            "sync_packet_count": len(packets),
            "connector_count": len(connectors),
            "entity_count": len(entities),
            "blocked_packet_count": len(blocked_packets),
            "ready_for_live_sync_count": 0,
            "write_enabled_count": 0,
            "execution_enabled_count": 0,
            "network_call_enabled_count": 0,
            "credentials_included_count": 0,
            "all_packets_blocked": len(blocked_packets) == len(packets),
            "all_writes_disabled": all(packet["write_enabled"] is False for packet in packets),
            "all_external_actions_disabled": all(value is False for value in EXTERNAL_SIDE_EFFECTS.values()),
        },
        "sync_packets": packets,
        "connectors": connectors,
        "entities": entities,
        "sync_policy": {
            "default_mode": "local_sync_rehearsal_only",
            "source_of_truth": "BUSINESS_DATA_MODEL_REPORT.json",
            "approval_rule": "No connector sync packet becomes live until connector credentials, mapping review, and Omar approval gates are complete.",
            "execution_rule": "Every packet remains non-executable and write-disabled in the local queue.",
        },
        "source_reports": SOURCE_REPORTS,
        "external_side_effects": EXTERNAL_SIDE_EFFECTS,
        "requested_payload": payload,
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
