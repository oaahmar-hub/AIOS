#!/usr/bin/env python3
"""AIOS local approval-state manager.

Tracks approval status for local action packets. This does not execute any
external action. Even approved local records keep external execution disabled
until a future n8n/Airtable/Gmail/WhatsApp connector receives explicit approval.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
ACTION_QUEUE_PATH = REPORTS_DIR / "ACTION_QUEUE.json"
APPROVAL_STATE_PATH = REPORTS_DIR / "APPROVAL_STATE.json"
APPROVAL_RESULT_PATH = REPORTS_DIR / "APPROVAL_MANAGER_RESULT.json"

DECISIONS = {"approved", "rejected", "hold", "pending_omar_review"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_actions() -> list[dict[str, Any]]:
    data = _load_json(ACTION_QUEUE_PATH)
    return data.get("actions", []) if isinstance(data, dict) else []


def _load_state() -> dict[str, dict[str, Any]]:
    data = _load_json(APPROVAL_STATE_PATH)
    records = data.get("approvals", []) if isinstance(data, dict) else []
    return {record.get("action_id"): record for record in records if record.get("action_id")}


def sync() -> dict[str, Any]:
    existing = _load_state()
    actions = _load_actions()
    approvals = []
    for action in actions:
        action_id = action.get("action_id")
        if not action_id:
            continue
        record = existing.get(action_id) or {
            "action_id": action_id,
            "created_at": _now(),
            "status": "pending_omar_review",
            "decision": None,
            "decided_at": None,
            "decided_by": None,
            "note": "",
        }
        record.update(
            {
                "title": action.get("title", ""),
                "type": action.get("type", ""),
                "artifact_path": action.get("artifact_path", ""),
                "safety_gate": action.get("safety_gate", ""),
                "external_execution_enabled": False,
                "external_execution_policy": "disabled_until_explicit_approved_connector_run",
                "external_side_effects": {
                    "messages_sent": False,
                    "crm_rows_written": False,
                    "calendar_events_created": False,
                    "drive_files_modified": False,
                    "content_published": False,
                },
            }
        )
        approvals.append(record)

    payload = {
        "updated_at": _now(),
        "approval_count": len(approvals),
        "pending_count": sum(1 for item in approvals if item.get("status") == "pending_omar_review"),
        "approved_count": sum(1 for item in approvals if item.get("status") == "approved"),
        "rejected_count": sum(1 for item in approvals if item.get("status") == "rejected"),
        "hold_count": sum(1 for item in approvals if item.get("status") == "hold"),
        "approvals": approvals,
    }
    APPROVAL_STATE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def decide(action_id: str, decision: str, actor: str = "local_operator", note: str = "") -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    state = sync()
    approvals = state.get("approvals", [])
    found = False
    for record in approvals:
        if record.get("action_id") == action_id:
            record["status"] = decision
            record["decision"] = decision
            record["decided_at"] = _now()
            record["decided_by"] = actor
            record["note"] = note
            record["external_execution_enabled"] = False
            found = True
            break
    if not found:
        raise ValueError(f"unknown action_id {action_id}")
    payload = {
        "updated_at": _now(),
        "approval_count": len(approvals),
        "pending_count": sum(1 for item in approvals if item.get("status") == "pending_omar_review"),
        "approved_count": sum(1 for item in approvals if item.get("status") == "approved"),
        "rejected_count": sum(1 for item in approvals if item.get("status") == "rejected"),
        "hold_count": sum(1 for item in approvals if item.get("status") == "hold"),
        "approvals": approvals,
    }
    APPROVAL_STATE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def run(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {"action": "sync"}
    if command.get("action") == "decide":
        state = decide(
            str(command.get("action_id", "")),
            str(command.get("decision", "")),
            str(command.get("actor", "local_operator")),
            str(command.get("note", "")),
        )
        action = "decide"
    else:
        state = sync()
        action = "sync"
    result = {
        "ran_at": _now(),
        "passed": True,
        "action": action,
        "approval_count": state.get("approval_count", 0),
        "pending_count": state.get("pending_count", 0),
        "approved_count": state.get("approved_count", 0),
        "rejected_count": state.get("rejected_count", 0),
        "hold_count": state.get("hold_count", 0),
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
        },
    }
    APPROVAL_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"action": raw}


if __name__ == "__main__":
    print(json.dumps(run(_parse()), indent=2, ensure_ascii=False))
