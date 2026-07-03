#!/usr/bin/env python3
"""AIOS connector execution manifest.

Maps local approval-gated action packets to future connector operations.
This file deliberately does not execute n8n, Airtable, Gmail, Calendar, Drive,
WhatsApp, Notion, Instagram, or any other connector. It produces an explicit
disabled manifest so approved connector runs can later be reviewed and enabled
with Omar approval.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from approval_state_manager import APPROVAL_STATE_PATH, run as sync_approvals


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
CONNECTOR_MANIFEST_PATH = REPORTS_DIR / "CONNECTOR_EXECUTION_MANIFEST.json"
CONNECTOR_RESULT_PATH = REPORTS_DIR / "CONNECTOR_EXECUTION_RESULT.json"


CONNECTOR_MAP = {
    "workflow_packet": ["n8n", "airtable", "notion", "dashboard"],
    "task_packet": ["airtable", "dashboard"],
    "daily_briefing_packet": ["dashboard", "gmail_draft", "calendar_read"],
    "content_draft_packet": ["content_factory", "drive_draft", "instagram_draft", "dashboard"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _operation_for(connector: str, approval: dict[str, Any]) -> dict[str, Any]:
    action_type = approval.get("type", "task_packet")
    base = {
        "connector": connector,
        "action_id": approval.get("action_id"),
        "source_artifact": approval.get("artifact_path"),
        "approval_status": approval.get("status"),
        "enabled": False,
        "blocked_reason": "connector_execution_disabled_until_explicit_omar_approval",
    }
    if connector == "n8n":
        base.update({"operation": "stage_workflow_call", "target": "AIOS master router workflow"})
    elif connector == "airtable":
        base.update({"operation": "prepare_record_upsert", "target": "Omar RE OS CRM tables"})
    elif connector == "notion":
        base.update({"operation": "prepare_knowledge_page", "target": "AIOS Notion operations knowledge base"})
    elif connector == "dashboard":
        base.update({"operation": "append_activity_and_status", "target": "AIOS command center"})
    elif connector == "gmail_draft":
        base.update({"operation": "prepare_draft_only", "target": "Gmail account"})
    elif connector == "calendar_read":
        base.update({"operation": "prepare_availability_read", "target": "Google Calendar account"})
    elif connector == "drive_draft":
        base.update({"operation": "prepare_file_draft", "target": "Google Drive knowledge base"})
    elif connector == "instagram_draft":
        base.update({"operation": "prepare_post_draft_only", "target": "Instagram / future social connector"})
    elif connector == "content_factory":
        base.update({"operation": "prepare_content_asset", "target": "AIOS content factory"})
    else:
        base.update({"operation": f"prepare_{action_type}", "target": connector})
    return base


def build() -> dict[str, Any]:
    sync_approvals({"action": "sync"})
    approval_state = _load_json(APPROVAL_STATE_PATH)
    approvals = approval_state.get("approvals", [])
    execution_items = []
    for approval in approvals:
        connectors = CONNECTOR_MAP.get(approval.get("type"), ["dashboard"])
        execution_items.append(
            {
                "action_id": approval.get("action_id"),
                "title": approval.get("title"),
                "type": approval.get("type"),
                "approval_status": approval.get("status"),
                "source_artifact": approval.get("artifact_path"),
                "external_execution_enabled": False,
                "eligible_for_connector_execution": approval.get("status") == "approved",
                "operations": [_operation_for(connector, approval) for connector in connectors],
            }
        )
    manifest = {
        "generated_at": _now(),
        "mode": "manifest_only_no_connector_execution",
        "execution_enabled": False,
        "requires_explicit_omar_approval": True,
        "items_count": len(execution_items),
        "approved_items_count": sum(1 for item in execution_items if item.get("approval_status") == "approved"),
        "pending_items_count": sum(1 for item in execution_items if item.get("approval_status") == "pending_omar_review"),
        "items": execution_items,
        "external_side_effects": {
            "n8n_workflows_called": False,
            "airtable_rows_written": False,
            "notion_pages_created": False,
            "gmail_drafts_created": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "whatsapp_messages_sent": False,
            "instagram_posts_published": False,
            "content_published": False,
        },
    }
    CONNECTOR_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {
        "ran_at": _now(),
        "passed": True,
        "manifest_path": CONNECTOR_MANIFEST_PATH.name,
        "items_count": manifest["items_count"],
        "execution_enabled": False,
        "external_side_effects": manifest["external_side_effects"],
    }
    CONNECTOR_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"action": raw}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False))
