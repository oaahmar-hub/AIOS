#!/usr/bin/env python3
"""AIOS live-run request builder.

Packages approved connector dry-run-ready items into a local request for Omar's
final review. It does not enable or call live connectors. The output is a
human-readable approval packet plus a JSON report that can later feed a real
connector runner after explicit final approval.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import build as build_command_center_data
from connector_dry_run_executor import DRY_RUN_PLAN_PATH, build as build_connector_dry_run


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REQUESTS_DIR = REPORTS_DIR / "live_run_requests"
LIVE_RUN_REQUEST_PATH = REPORTS_DIR / "LIVE_RUN_REQUEST.json"
LIVE_RUN_REQUEST_RESULT_PATH = REPORTS_DIR / "LIVE_RUN_REQUEST_RESULT.json"


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


def _safe_slug(value: str) -> str:
    allowed = [char if char.isalnum() else "-" for char in value.upper()]
    return "-".join("".join(allowed).split("-"))[:80] or "AIOS-LIVE-RUN"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _packet_markdown(request: dict[str, Any]) -> str:
    lines = [
        f"# AIOS Live-Run Request {request['request_id']}",
        "",
        f"Generated: {request['generated_at']}",
        f"Mode: {request['mode']}",
        f"Live execution enabled: {str(request['execution_enabled']).lower()}",
        f"Requires Omar final approval: {str(request['requires_omar_final_approval']).lower()}",
        "",
        "## Summary",
        "",
        f"- Ready items: {request['ready_items_count']}",
        f"- Blocked items: {request['blocked_items_count']}",
        f"- Proposed connector steps: {request['proposed_steps_count']}",
        "- External side effects: none",
        "",
        "## Ready Items",
        "",
    ]
    if not request["ready_items"]:
        lines.append("No approved connector dry-run items are ready for live-run review.")
    for item in request["ready_items"]:
        lines.extend(
            [
                f"### {item.get('title') or item.get('action_id')}",
                "",
                f"- Action ID: `{item.get('action_id')}`",
                f"- Type: `{item.get('type')}`",
                f"- Source artifact: `{item.get('source_artifact')}`",
                f"- Approval status: `{item.get('approval_status')}`",
                f"- Proposed steps: {len(item.get('steps', []))}",
                "",
            ]
        )
        for step in item.get("steps", []):
            lines.append(
                f"- `{step.get('connector')}` / `{step.get('operation')}` -> `{step.get('target')}`; would_execute=`false`"
            )
        lines.append("")
    lines.extend(
        [
            "## Blocked Items",
            "",
            f"{request['blocked_items_count']} item(s) remain blocked because they are not locally approved.",
            "",
            "## Final Approval Gate",
            "",
            "This packet is not authorization to run live connectors. A separate explicit final approval is required before any external connector operation can be enabled.",
            "",
        ]
    )
    return "\n".join(lines)


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    request_label = str(command.get("label", "local-review"))
    action_id_filter = str(command.get("action_id", "")).strip()
    dry_run = build_connector_dry_run()
    ready_items = [
        item
        for item in dry_run.get("items", [])
        if item.get("eligible_for_connector_execution") and item.get("would_execute_external_connectors") is False
    ]
    if action_id_filter:
        ready_items = [item for item in ready_items if str(item.get("action_id", "")) == action_id_filter]
    blocked_items = [item for item in dry_run.get("items", []) if not item.get("eligible_for_connector_execution")]
    proposed_steps_count = sum(len(item.get("steps", [])) for item in ready_items)
    request_id = f"LRR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{_safe_slug(request_label)}"
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = REQUESTS_DIR / f"{request_id}.md"
    rel_packet_path = packet_path.relative_to(AIOS_ROOT).as_posix()
    request = {
        "generated_at": _now(),
        "request_id": request_id,
        "label": request_label,
        "mode": "local_live_run_request_only",
        "execution_enabled": False,
        "requires_omar_final_approval": True,
        "dry_run_plan_path": DRY_RUN_PLAN_PATH.name,
        "action_id_filter": action_id_filter or None,
        "packet_path": rel_packet_path,
        "ready_items_count": len(ready_items),
        "blocked_items_count": len(blocked_items),
        "proposed_steps_count": proposed_steps_count,
        "ready_items": ready_items,
        "blocked_action_ids": [item.get("action_id") for item in blocked_items],
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    packet_path.write_text(_packet_markdown(request), encoding="utf-8")
    LIVE_RUN_REQUEST_PATH.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": True,
        "request_id": request_id,
        "request_path": LIVE_RUN_REQUEST_PATH.name,
        "packet_path": rel_packet_path,
        "ready_items_count": request["ready_items_count"],
        "blocked_items_count": request["blocked_items_count"],
        "proposed_steps_count": request["proposed_steps_count"],
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "execution_enabled": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    LIVE_RUN_REQUEST_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return request


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"label": raw}


if __name__ == "__main__":
    print(json.dumps(build(_parse()), indent=2, ensure_ascii=False))
