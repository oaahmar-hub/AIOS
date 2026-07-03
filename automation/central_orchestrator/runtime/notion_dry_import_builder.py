#!/usr/bin/env python3
"""AIOS Notion dry-import page mapper.

Creates local Notion page drafts from Notion payload contracts. This is a
review artifact only: it never calls Notion, never creates pages, and never
includes credentials.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import build as build_command_center_data
from connector_payload_builder import CONNECTOR_PAYLOADS_PATH


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
DRY_IMPORTS_DIR = REPORTS_DIR / "notion_dry_imports"
NOTION_DRY_IMPORT_MANIFEST_PATH = REPORTS_DIR / "NOTION_DRY_IMPORT_MANIFEST.json"
NOTION_DRY_IMPORT_RESULT_PATH = REPORTS_DIR / "NOTION_DRY_IMPORT_RESULT.json"

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
    return "-".join("".join(allowed).split("-"))[:90] or "AIOS-NOTION-DRY-IMPORT"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _page_for_payload(payload: dict[str, Any], label: str) -> dict[str, Any]:
    properties = payload.get("properties", {})
    action_id = str(properties.get("Action ID") or "NO_ACTION")
    request_id = str(properties.get("Request ID") or "NO_REQUEST")
    return {
        "page_id": f"NDP-{_safe_slug(action_id)}",
        "label": label,
        "connector": "notion",
        "payload_type": payload.get("payload_type"),
        "workspace_contract": payload.get("workspace_contract"),
        "database_contract": payload.get("database_contract"),
        "operation": payload.get("operation"),
        "match_field": payload.get("match_field"),
        "request_id": request_id,
        "action_id": action_id,
        "property_count": len(properties),
        "properties": properties,
        "children": payload.get("children", []),
        "network_call_enabled": False,
        "page_create_enabled": False,
        "credentials_included": False,
        "activation_allowed": False,
    }


def _markdown_page(page: dict[str, Any]) -> str:
    lines = [
        "# AIOS Notion Dry Import Page Draft",
        "",
        f"Page ID: `{page['page_id']}`",
        f"Request ID: `{page['request_id']}`",
        f"Action ID: `{page['action_id']}`",
        "",
        "## Target",
        "",
        f"- Workspace contract: `{page.get('workspace_contract')}`",
        f"- Database contract: `{page.get('database_contract')}`",
        f"- Operation: `{page.get('operation')}`",
        f"- Match field: `{page.get('match_field')}`",
        "",
        "## Properties",
        "",
        "| Property | Value |",
        "|---|---|",
    ]
    for name, value in page.get("properties", {}).items():
        lines.append(f"| `{name}` | `{value}` |")
    lines.extend(["", "## Content Blocks", ""])
    for child in page.get("children", []):
        lines.append(f"- `{child.get('type', 'paragraph')}`: {child.get('text', '')}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Network call enabled: `false`",
            "- Page create enabled: `false`",
            "- Credentials included: `false`",
            "- Activation allowed: `false`",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_page(page: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if page.get("connector") != "notion":
        errors.append("connector_not_notion")
    if not page.get("workspace_contract"):
        errors.append("missing_workspace_contract")
    if not page.get("database_contract"):
        errors.append("missing_database_contract")
    if page.get("match_field") != "Action ID":
        errors.append("match_field_not_action_id")
    properties = page.get("properties", {})
    for required in ["Title", "Action ID", "Request ID", "Status", "External Execution Enabled"]:
        if required not in properties:
            errors.append(f"missing_property:{required}")
    if page.get("network_call_enabled") is not False:
        errors.append("network_call_enabled")
    if page.get("page_create_enabled") is not False:
        errors.append("page_create_enabled")
    if page.get("credentials_included") is not False:
        errors.append("credentials_included")
    if page.get("activation_allowed") is not False:
        errors.append("activation_allowed")
    return errors


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    label = str(command.get("label", "local-notion-dry-import"))
    payload_report = _load_json(CONNECTOR_PAYLOADS_PATH)
    notion_payloads = [
        payload
        for payload in payload_report.get("payloads", [])
        if payload.get("connector") == "notion"
        and payload.get("network_call_enabled") is False
        and payload.get("execution_enabled") is False
    ]
    DRY_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pages = []
    validation_errors = []

    for payload in notion_payloads:
        page = _page_for_payload(payload, label)
        page_errors = _validate_page(page)
        validation_errors.extend(page_errors)
        file_name = f"{_safe_slug(page['request_id'])}-NOTION-DRY-IMPORT.md"
        path = DRY_IMPORTS_DIR / file_name
        path.write_text(_markdown_page(page), encoding="utf-8")
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        pages.append(
            {
                **page,
                "packet_file": file_name,
                "packet_path": path.relative_to(REPORTS_DIR).as_posix(),
                "packet_sha256": sha256,
            }
        )

    manifest = {
        "generated_at": _now(),
        "mode": "notion_dry_import_page_draft_only",
        "payload_report_status": payload_report.get("runner_plan_status"),
        "payloads_ready": payload_report.get("payloads_ready") is True,
        "page_ready": bool(pages) and not validation_errors,
        "page_count": len(pages),
        "pages": pages,
        "validation_errors": validation_errors if pages else ["notion_payload_not_ready"],
        "network_call_enabled": False,
        "page_create_enabled": False,
        "activation_enabled": False,
        "credentials_included": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    NOTION_DRY_IMPORT_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": not validation_errors,
        "page_ready": manifest["page_ready"],
        "page_count": manifest["page_count"],
        "network_call_enabled": False,
        "page_create_enabled": False,
        "activation_enabled": False,
        "credentials_included": False,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    NOTION_DRY_IMPORT_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


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
