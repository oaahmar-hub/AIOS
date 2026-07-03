#!/usr/bin/env python3
"""AIOS local approval command.

Applies a local Omar-style approval decision to one action packet, then rebuilds
the disabled connector manifest, connector dry-run plan, and command-center data.
This is a local state command only. It never enables or calls live connectors.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from approval_state_manager import APPROVAL_STATE_PATH, DECISIONS, run as run_approval_state
from build_command_center_data import build as build_command_center_data
from connector_dry_run_executor import build as build_connector_dry_run
from connector_execution_manifest import build as build_connector_manifest


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
APPROVAL_COMMAND_RESULT_PATH = REPORTS_DIR / "LOCAL_APPROVAL_COMMAND_RESULT.json"


SIDE_EFFECTS_FALSE = {
    "n8n_workflows_called": False,
    "airtable_rows_written": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_modified": False,
    "whatsapp_messages_sent": False,
    "instagram_posts_published": False,
    "content_published": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _latest_pending_action_id() -> str:
    run_approval_state({"action": "sync"})
    state = _load_json(APPROVAL_STATE_PATH)
    approvals = state.get("approvals", [])
    for approval in approvals:
        if approval.get("status") == "pending_omar_review":
            return str(approval.get("action_id", ""))
    return str(approvals[0].get("action_id", "")) if approvals else ""


def run(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    decision = str(command.get("decision", "approved"))
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")

    action_id = str(command.get("action_id") or _latest_pending_action_id())
    if not action_id:
        raise ValueError("no action_id supplied and no approval records are available")

    actor = str(command.get("actor", "omar_local_approval_command"))
    note = str(command.get("note", "local approval command rehearsal"))

    approval_result = run_approval_state(
        {
            "action": "decide",
            "action_id": action_id,
            "decision": decision,
            "actor": actor,
            "note": note,
        }
    )
    approval_state = _load_json(APPROVAL_STATE_PATH)
    decided_record = next(
        (item for item in approval_state.get("approvals", []) if item.get("action_id") == action_id),
        {},
    )
    connector_manifest = build_connector_manifest()
    connector_dry_run = build_connector_dry_run()
    command_center_data = build_command_center_data()

    matching_manifest_item = next(
        (item for item in connector_manifest.get("items", []) if item.get("action_id") == action_id),
        {},
    )
    matching_dry_run_item = next(
        (item for item in connector_dry_run.get("items", []) if item.get("action_id") == action_id),
        {},
    )
    enabled_ops = [
        operation
        for item in connector_manifest.get("items", [])
        for operation in item.get("operations", [])
        if operation.get("enabled")
    ]
    would_execute_steps = [
        step
        for item in connector_dry_run.get("items", [])
        for step in item.get("steps", [])
        if step.get("would_execute")
    ]

    result = {
        "ran_at": _now(),
        "passed": not enabled_ops and not would_execute_steps,
        "action": "decide_and_rebuild_local_execution_state",
        "action_id": action_id,
        "decision": decision,
        "actor": actor,
        "note": note,
        "approval_result": approval_result,
        "decided_record": decided_record,
        "matching_manifest_item": {
            "action_id": matching_manifest_item.get("action_id"),
            "approval_status": matching_manifest_item.get("approval_status"),
            "eligible_for_connector_execution": matching_manifest_item.get("eligible_for_connector_execution"),
            "external_execution_enabled": matching_manifest_item.get("external_execution_enabled"),
            "operation_count": len(matching_manifest_item.get("operations", [])),
        },
        "matching_dry_run_item": {
            "action_id": matching_dry_run_item.get("action_id"),
            "approval_status": matching_dry_run_item.get("approval_status"),
            "eligible_for_connector_execution": matching_dry_run_item.get("eligible_for_connector_execution"),
            "would_execute_external_connectors": matching_dry_run_item.get("would_execute_external_connectors"),
            "step_count": len(matching_dry_run_item.get("steps", [])),
        },
        "approval_counts": {
            "approval_count": approval_state.get("approval_count", 0),
            "pending_count": approval_state.get("pending_count", 0),
            "approved_count": approval_state.get("approved_count", 0),
            "rejected_count": approval_state.get("rejected_count", 0),
            "hold_count": approval_state.get("hold_count", 0),
        },
        "connector_counts": {
            "manifest_items": connector_manifest.get("items_count", 0),
            "approved_manifest_items": connector_manifest.get("approved_items_count", 0),
            "dry_run_items": connector_dry_run.get("items_count", 0),
            "dry_run_ready_items": connector_dry_run.get("ready_items_count", 0),
            "dry_run_blocked_items": connector_dry_run.get("blocked_items_count", 0),
            "dry_run_steps": connector_dry_run.get("steps_count", 0),
        },
        "dashboard_counts": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "execution_enabled": False,
        "enabled_connector_operations": enabled_ops,
        "would_execute_dry_run_steps": would_execute_steps,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    APPROVAL_COMMAND_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"decision": raw}


if __name__ == "__main__":
    print(json.dumps(run(_parse()), indent=2, ensure_ascii=False))
