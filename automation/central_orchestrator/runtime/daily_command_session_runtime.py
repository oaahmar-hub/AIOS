#!/usr/bin/env python3
"""Build the AIOS Daily Command Session.

This runtime turns AIOS into a daily operating loop for HSH. It joins the
briefing, CEO plan, Autopilot queue, CRM follow-ups, operations cases, content
drafts, connector activation gates, and impact metrics into morning, midday,
and end-of-day sessions. It is local-only and never sends, writes, publishes,
starts OAuth, or executes live workflows.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "DAILY_COMMAND_SESSION.json"

SOURCE_REPORTS = {
    "daily_briefing": "AIOS_DAILY_BRIEFING.json",
    "ceo_operating": "CEO_OPERATING_REPORT.json",
    "aios_autopilot": "AIOS_AUTOPILOT_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "connector_activation_command": "CONNECTOR_ACTIVATION_COMMAND_PLAN.json",
    "impact_metrics": "IMPACT_METRICS_REPORT.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
    "workflow_executed": False,
    "messages_sent": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "notion_pages_created": False,
    "instagram_posts_published": False,
    "content_published": False,
    "payments_made": False,
    "portal_submissions": False,
    "legal_claims_finalized": False,
    "n8n_workflows_imported": False,
    "n8n_workflows_activated": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _item(title: str, command: str, gate: str, source: str, minutes: int, detail: str) -> dict[str, Any]:
    return {
        "title": title,
        "command": command,
        "gate": gate,
        "source_report": source,
        "estimated_minutes": minutes,
        "detail": detail,
        "execution_enabled": False,
        "external_write_enabled": False,
    }


def _safe_title(row: dict[str, Any], *keys: str, fallback: str) -> str:
    for key in keys:
        if row.get(key):
            return str(row[key])
    return fallback


def build_session_blocks(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ceo = reports["ceo_operating"]
    autopilot = reports["aios_autopilot"]
    crm = reports["crm_followup"]
    operations = reports["operations_assistant"]
    content = reports["content_factory"]
    connectors = reports["connector_activation_command"]

    priorities = ceo.get("priority_stack", [])
    autopilot_actions = autopilot.get("autopilot_actions", [])
    crm_tasks = crm.get("follow_up_tasks", [])
    operation_cases = operations.get("cases", [])
    content_drafts = content.get("draft_artifacts", [])
    connector_steps = connectors.get("activation_steps", [])

    morning_items = [
        _item(
            _safe_title(row, "title", "action", fallback="CEO priority"),
            row.get("handoff_command") or "@ceo",
            "NO_INTERVENTION_LOCAL_ONLY",
            SOURCE_REPORTS["ceo_operating"],
            15,
            row.get("next_action") or "Prepare today's executive operating brief.",
        )
        for row in priorities[:3]
    ]
    morning_items.extend(
        _item(
            _safe_title(row, "title", fallback="Autopilot action"),
            row.get("command") or "@autopilot",
            row.get("human_intervention_gate") or "NO_INTERVENTION_LOCAL_ONLY",
            SOURCE_REPORTS["aios_autopilot"],
            int(row.get("expected_minutes_saved") or 10),
            row.get("next_step") or "Prepare local action packet.",
        )
        for row in autopilot_actions[:4]
    )

    midday_items = [
        _item(
            _safe_title(row, "task", "title", "lead_name", fallback="CRM follow-up"),
            "@crm-followup",
            "HIGH_RISK_DECISION" if index == 0 else "NO_INTERVENTION_LOCAL_ONLY",
            SOURCE_REPORTS["crm_followup"],
            12,
            "Prepare follow-up task and draft-only client response.",
        )
        for index, row in enumerate(crm_tasks[:3])
    ]
    midday_items.extend(
        _item(
            _safe_title(row, "title", "case_type", fallback="Operations case"),
            "@operations",
            "HIGH_RISK_DECISION",
            SOURCE_REPORTS["operations_assistant"],
            20,
            "Prepare checklist; stop before portal submission, legal conclusion, or payment.",
        )
        for row in operation_cases[:3]
    )

    end_day_items = [
        _item(
            _safe_title(row, "title", "type", fallback="Content draft"),
            "@content-factory",
            "NO_INTERVENTION_LOCAL_ONLY",
            SOURCE_REPORTS["content_factory"],
            15,
            "Prepare draft content locally; publishing remains disabled.",
        )
        for row in content_drafts[:3]
    ]
    end_day_items.extend(
        _item(
            f"{row.get('connector', 'connector')} connector handoff",
            row.get("setup_command") or "@activation-command",
            "LOGIN_APPROVAL" if row.get("status") == "ready_for_user_login_or_credential" else "OAUTH_APPROVAL",
            SOURCE_REPORTS["connector_activation_command"],
            10,
            row.get("handoff") or "Prepare connector handoff; do not start OAuth.",
        )
        for row in connector_steps[:3]
    )

    return [
        {
            "block": "Morning Command",
            "objective": "Set the day, choose the highest-leverage work, and prepare local action packets.",
            "items": morning_items,
        },
        {
            "block": "Midday Execution",
            "objective": "Handle follow-ups and operations work while stopping before high-risk decisions.",
            "items": midday_items,
        },
        {
            "block": "End-of-Day Closeout",
            "objective": "Prepare content, connector handoffs, and tomorrow's setup without live external execution.",
            "items": end_day_items,
        },
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    blocks = build_session_blocks(reports)
    items = [item for block in blocks for item in block["items"]]
    stop_items = [item for item in items if item["gate"] != "NO_INTERVENTION_LOCAL_ONLY"]
    auto_items = [item for item in items if item["gate"] == "NO_INTERVENTION_LOCAL_ONLY"]
    impact = reports["impact_metrics"].get("quality_metrics", {})
    result = {
        "generated_at": _now(),
        "mode": "safe_local_daily_command_session_no_external_side_effects",
        "operator": payload.get("operator", "Omar"),
        "session_date": payload.get("session_date", datetime.now(timezone.utc).date().isoformat()),
        "summary": {
            "session_block_count": len(blocks),
            "session_item_count": len(items),
            "auto_local_count": len(auto_items),
            "stopped_for_human_count": len(stop_items),
            "estimated_minutes_in_session": sum(item["estimated_minutes"] for item in items),
            "weekly_hours_saved_projection": impact.get("estimated_weekly_hours_saved", 0),
            "all_execution_disabled": all(item["execution_enabled"] is False and item["external_write_enabled"] is False for item in items),
        },
        "session_blocks": blocks,
        "stop_policy": {
            "allowed_without_interrupting": ["local briefs", "checklists", "drafts", "search/routing", "internal queue updates"],
            "stop_for": ["LOGIN_APPROVAL", "OAUTH_APPROVAL", "OTP_CODE", "PAYMENT_APPROVAL", "HIGH_RISK_DECISION"],
            "rule": "Daily Command can prepare work, but cannot send, write, publish, submit, pay, start OAuth, or activate connectors.",
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
