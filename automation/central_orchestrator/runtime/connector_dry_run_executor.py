#!/usr/bin/env python3
"""AIOS connector dry-run executor.

Builds a local-only execution simulation from the connector manifest. This is
the rehearsal layer before any approved n8n, Airtable, Gmail, Calendar, Drive,
WhatsApp, Instagram, Notion, or content connector call. It never calls external
services and never mutates business systems.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from connector_execution_manifest import CONNECTOR_MANIFEST_PATH, build as build_connector_manifest


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
DRY_RUN_PLAN_PATH = REPORTS_DIR / "CONNECTOR_DRY_RUN_PLAN.json"
DRY_RUN_RESULT_PATH = REPORTS_DIR / "CONNECTOR_DRY_RUN_RESULT.json"


SIDE_EFFECTS_FALSE = {
    "n8n_workflows_called": False,
    "airtable_rows_written": False,
    "notion_pages_created": False,
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


def _dry_run_step(operation: dict[str, Any], eligible: bool) -> dict[str, Any]:
    status = "ready_for_review" if eligible else "blocked_pending_omar_approval"
    return {
        "connector": operation.get("connector", "dashboard"),
        "operation": operation.get("operation", "prepare_operation"),
        "target": operation.get("target", ""),
        "status": status,
        "would_execute": False,
        "dry_run_only": True,
        "external_side_effect": False,
        "blocked_reason": "" if eligible else "approval_status_not_approved",
    }


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a connector execution dry-run plan.

    `simulate_approved=true` rehearses the approved branch without changing
    approval state or enabling external operations.
    """
    command = command or {}
    simulate_approved = bool(command.get("simulate_approved", False))
    manifest = build_connector_manifest()
    items = []
    for item in manifest.get("items", []):
        eligible = item.get("approval_status") == "approved" or simulate_approved
        steps = [_dry_run_step(operation, eligible) for operation in item.get("operations", [])]
        items.append(
            {
                "action_id": item.get("action_id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "approval_status": item.get("approval_status"),
                "simulated_as_approved": simulate_approved and item.get("approval_status") != "approved",
                "source_artifact": item.get("source_artifact"),
                "eligible_for_connector_execution": eligible,
                "would_execute_external_connectors": False,
                "steps": steps,
            }
        )

    ready_items = [item for item in items if item.get("eligible_for_connector_execution")]
    blocked_items = [item for item in items if not item.get("eligible_for_connector_execution")]
    plan = {
        "generated_at": _now(),
        "mode": "connector_execution_dry_run_only",
        "simulate_approved": simulate_approved,
        "execution_enabled": False,
        "requires_explicit_omar_approval_for_live_run": True,
        "manifest_path": CONNECTOR_MANIFEST_PATH.name,
        "items_count": len(items),
        "ready_items_count": len(ready_items),
        "blocked_items_count": len(blocked_items),
        "steps_count": sum(len(item.get("steps", [])) for item in items),
        "items": items,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    DRY_RUN_PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = {
        "ran_at": _now(),
        "passed": True,
        "mode": plan["mode"],
        "simulate_approved": simulate_approved,
        "plan_path": DRY_RUN_PLAN_PATH.name,
        "items_count": plan["items_count"],
        "ready_items_count": plan["ready_items_count"],
        "blocked_items_count": plan["blocked_items_count"],
        "steps_count": plan["steps_count"],
        "execution_enabled": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    DRY_RUN_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return plan


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"action": raw}


if __name__ == "__main__":
    print(json.dumps(build(_parse()), indent=2, ensure_ascii=False))
