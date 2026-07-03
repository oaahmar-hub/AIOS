#!/usr/bin/env python3
"""AIOS disabled live connector runner.

Consumes LIVE_RUN_REQUEST.json and validates the proposed connector steps. This
is a scaffold for the future live connector runner, but it deliberately refuses
execution unless final approval is explicit. Even with approval, this version
does not call external services; it only produces a validated execution plan.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import build as build_command_center_data
from live_run_request_builder import LIVE_RUN_REQUEST_PATH, build as build_live_run_request


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
LIVE_CONNECTOR_RUNNER_PLAN_PATH = REPORTS_DIR / "LIVE_CONNECTOR_RUNNER_PLAN.json"
LIVE_CONNECTOR_RUNNER_RESULT_PATH = REPORTS_DIR / "LIVE_CONNECTOR_RUNNER_RESULT.json"

ALLOWED_CONNECTORS = {
    "n8n",
    "airtable",
    "notion",
    "dashboard",
    "gmail_draft",
    "calendar_read",
    "drive_draft",
    "instagram_draft",
    "content_factory",
}

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


def _validate_step(step: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    connector = step.get("connector")
    operation = step.get("operation")
    target = step.get("target")
    if connector not in ALLOWED_CONNECTORS:
        errors.append(f"unsupported_connector:{connector}")
    if not operation:
        errors.append("missing_operation")
    if not target:
        errors.append("missing_target")
    if step.get("would_execute") is not False:
        errors.append("dry_run_step_not_locked")
    if step.get("external_side_effect") is not False:
        errors.append("step_external_side_effect_not_false")
    return errors


def _build_execution_plan(request: dict[str, Any], final_approval: bool) -> tuple[list[dict[str, Any]], list[str]]:
    planned_steps = []
    validation_errors = []
    for item in request.get("ready_items", []):
        action_id = item.get("action_id")
        if item.get("approval_status") != "approved":
            validation_errors.append(f"{action_id}:approval_status_not_approved")
        if item.get("eligible_for_connector_execution") is not True:
            validation_errors.append(f"{action_id}:not_connector_eligible")
        if item.get("would_execute_external_connectors") is not False:
            validation_errors.append(f"{action_id}:item_would_execute_not_false")
        for step in item.get("steps", []):
            step_errors = _validate_step(step)
            validation_errors.extend(f"{action_id}:{error}" for error in step_errors)
            planned_steps.append(
                {
                    "action_id": action_id,
                    "connector": step.get("connector"),
                    "operation": step.get("operation"),
                    "target": step.get("target"),
                    "validated": not step_errors,
                    "execution_mode": "refused_no_final_approval" if not final_approval else "validated_plan_only",
                    "would_call_external_service": False,
                    "external_side_effect": False,
                }
            )
    return planned_steps, validation_errors


def run(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    final_approval = bool(command.get("final_approval", False))
    approval_reference = str(command.get("approval_reference", "")).strip()
    refresh_request = bool(command.get("refresh_request", False))
    if refresh_request or not LIVE_RUN_REQUEST_PATH.exists():
        build_live_run_request({"label": str(command.get("label", "runner-refresh"))})

    request = _load_json(LIVE_RUN_REQUEST_PATH)
    planned_steps, validation_errors = _build_execution_plan(request, final_approval)
    final_approval_valid = final_approval and bool(approval_reference)
    refusal_reasons = []
    if not final_approval:
        refusal_reasons.append("missing_final_approval")
    if final_approval and not approval_reference:
        refusal_reasons.append("missing_approval_reference")
    if not request.get("ready_items_count"):
        refusal_reasons.append("no_ready_live_run_items")
    if validation_errors:
        refusal_reasons.append("request_validation_errors")

    runner_status = "refused"
    if final_approval_valid and request.get("ready_items_count", 0) > 0 and not validation_errors:
        runner_status = "validated_plan_only_no_external_calls"

    plan = {
        "generated_at": _now(),
        "mode": "disabled_live_connector_runner",
        "runner_status": runner_status,
        "execution_enabled": False,
        "final_approval": final_approval,
        "approval_reference": approval_reference,
        "request_id": request.get("request_id"),
        "request_path": LIVE_RUN_REQUEST_PATH.name,
        "ready_items_count": request.get("ready_items_count", 0),
        "blocked_items_count": request.get("blocked_items_count", 0),
        "proposed_steps_count": request.get("proposed_steps_count", 0),
        "planned_steps_count": len(planned_steps),
        "planned_steps": planned_steps,
        "validation_errors": validation_errors,
        "refusal_reasons": refusal_reasons,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    LIVE_CONNECTOR_RUNNER_PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": runner_status in {"refused", "validated_plan_only_no_external_calls"} and not any(SIDE_EFFECTS_FALSE.values()),
        "runner_status": runner_status,
        "execution_enabled": False,
        "final_approval": final_approval,
        "request_id": request.get("request_id"),
        "ready_items_count": plan["ready_items_count"],
        "planned_steps_count": len(planned_steps),
        "validation_error_count": len(validation_errors),
        "refusal_reasons": refusal_reasons,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    LIVE_CONNECTOR_RUNNER_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return plan


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"approval_reference": raw}


if __name__ == "__main__":
    print(json.dumps(run(_parse()), indent=2, ensure_ascii=False))
