#!/usr/bin/env python3
"""AIOS connector activation checklist generator.

Turns local connector payload contracts into a human approval checklist. This is
the final review layer before any real connector integration work. It does not
use credentials, call APIs, or enable live activation.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import build as build_command_center_data
from connector_payload_builder import CONNECTOR_PAYLOADS_PATH


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
CHECKLISTS_DIR = REPORTS_DIR / "connector_activation_checklists"
ACTIVATION_CHECKLIST_PATH = REPORTS_DIR / "CONNECTOR_ACTIVATION_CHECKLIST.json"
ACTIVATION_CHECKLIST_RESULT_PATH = REPORTS_DIR / "CONNECTOR_ACTIVATION_CHECKLIST_RESULT.json"

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
    return "-".join("".join(allowed).split("-"))[:80] or "AIOS-CONNECTOR-ACTIVATION"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _checklist_item(payload: dict[str, Any]) -> dict[str, Any]:
    connector = payload.get("connector", "connector")
    if connector == "n8n":
        title = "Review n8n workflow-call contract"
        required_checks = [
            "Confirm target n8n workflow or webhook endpoint.",
            "Confirm AIOS_MASTER_ROUTER workflow is the intended receiver.",
            "Confirm payload body contains action_id, request_id, operation, target, and approval_reference.",
            "Confirm execution remains disabled until Omar final activation.",
        ]
    elif connector == "airtable":
        title = "Review Airtable record-upsert contract"
        required_checks = [
            "Confirm Airtable base and table names.",
            "Confirm Action ID is the match field.",
            "Confirm External Execution Enabled is false.",
            "Confirm field mapping before any live Airtable write.",
        ]
    elif connector == "notion":
        title = "Review Notion page-create contract"
        required_checks = [
            "Confirm Notion workspace and database destination.",
            "Confirm Action ID is included for traceability.",
            "Confirm page properties map to the AIOS knowledge-base structure.",
            "Confirm External Execution Enabled is false before any live Notion write.",
        ]
    elif connector == "gmail_draft":
        title = "Review Gmail draft contract"
        required_checks = [
            "Confirm Gmail account destination.",
            "Confirm draft recipient, subject, and body.",
            "Confirm send_enabled remains false.",
            "Confirm Omar approval is required before any Gmail API write.",
        ]
    elif connector == "calendar_read":
        title = "Review Google Calendar read contract"
        required_checks = [
            "Confirm calendar account and read window.",
            "Confirm the operation is read-only availability lookup.",
            "Confirm calendar_write_enabled remains false.",
            "Confirm no event creation or update is included.",
        ]
    elif connector == "drive_draft":
        title = "Review Google Drive file-draft contract"
        required_checks = [
            "Confirm Drive destination folder contract.",
            "Confirm draft file name, MIME type, and body.",
            "Confirm file_create_enabled remains false.",
            "Confirm no Drive file create or modify call is enabled.",
        ]
    elif connector == "content_factory":
        title = "Review Content Factory asset contract"
        required_checks = [
            "Confirm content brief, format, and target channel.",
            "Confirm asset_generation_enabled remains false.",
            "Confirm publish_enabled remains false.",
            "Confirm Omar approval is required before final media generation or campaign publishing.",
        ]
    elif connector == "instagram_draft":
        title = "Review Instagram post-draft contract"
        required_checks = [
            "Confirm Instagram account or future social connector destination.",
            "Confirm caption draft and media requirement.",
            "Confirm publish_enabled remains false.",
            "Confirm no Instagram API call or publishing step is enabled.",
        ]
    else:
        title = f"Review {connector} payload contract"
        required_checks = ["Confirm connector payload is reviewed before activation."]
    return {
        "connector": connector,
        "title": title,
        "payload_type": payload.get("payload_type"),
        "network_call_enabled": False,
        "execution_enabled": False,
        "required_checks": required_checks,
        "activation_allowed": False,
    }


def _markdown(checklist: dict[str, Any]) -> str:
    lines = [
        f"# AIOS Connector Activation Checklist {checklist['checklist_id']}",
        "",
        f"Generated: {checklist['generated_at']}",
        f"Request ID: {checklist.get('request_id') or 'none'}",
        f"Activation enabled: {str(checklist['activation_enabled']).lower()}",
        f"Requires Omar approval: {str(checklist['requires_omar_approval']).lower()}",
        "",
        "## Summary",
        "",
        f"- Payloads ready: {str(checklist['payloads_ready']).lower()}",
        f"- Checklist items: {checklist['checklist_item_count']}",
        "- Network calls: disabled",
        "- Live activation: disabled",
        "",
        "## Checklist",
        "",
    ]
    if not checklist["items"]:
        lines.append("No connector payloads are ready for activation review.")
    for item in checklist["items"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"- Connector: `{item['connector']}`",
                f"- Payload type: `{item.get('payload_type')}`",
                "- Network call enabled: `false`",
                "- Execution enabled: `false`",
                "",
            ]
        )
        for check in item["required_checks"]:
            lines.append(f"- [ ] {check}")
        lines.append("")
    lines.extend(
        [
            "## Stop Condition",
            "",
            "Do not activate any connector until Omar gives explicit final approval and credentials/OAuth are handled in the correct connector flow.",
            "",
        ]
    )
    return "\n".join(lines)


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    label = str(command.get("label", "local-activation-review"))
    payload_report = _load_json(CONNECTOR_PAYLOADS_PATH)
    payloads = payload_report.get("payloads", [])
    payloads_ready = bool(payloads) and payload_report.get("payloads_ready") is True
    items = [_checklist_item(payload) for payload in payloads] if payloads_ready else []
    checklist_id = f"CAC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{_safe_slug(label)}"
    CHECKLISTS_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = CHECKLISTS_DIR / f"{checklist_id}.md"
    rel_packet_path = packet_path.relative_to(AIOS_ROOT).as_posix()
    checklist = {
        "generated_at": _now(),
        "checklist_id": checklist_id,
        "label": label,
        "mode": "connector_activation_checklist_only",
        "request_id": payload_report.get("request_id"),
        "payloads_ready": payloads_ready,
        "payload_count": len(payloads),
        "checklist_item_count": len(items),
        "activation_enabled": False,
        "requires_omar_approval": True,
        "packet_path": rel_packet_path,
        "items": items,
        "blocked_reason": "" if payloads_ready else "connector_payloads_not_ready",
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    packet_path.write_text(_markdown(checklist), encoding="utf-8")
    ACTIVATION_CHECKLIST_PATH.write_text(json.dumps(checklist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": True,
        "checklist_id": checklist_id,
        "payloads_ready": payloads_ready,
        "checklist_item_count": len(items),
        "activation_enabled": False,
        "packet_path": rel_packet_path,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    ACTIVATION_CHECKLIST_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return checklist


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
