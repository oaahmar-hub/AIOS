#!/usr/bin/env python3
"""AIOS Airtable dry-import schema mapper.

Creates a local review-only Airtable schema map and import checklist from the
Airtable payload contract. This never calls Airtable, never writes records, and
never includes credentials.
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
DRY_IMPORTS_DIR = REPORTS_DIR / "airtable_dry_imports"
AIRTABLE_DRY_IMPORT_SCHEMA_PATH = REPORTS_DIR / "AIRTABLE_DRY_IMPORT_SCHEMA.json"
AIRTABLE_DRY_IMPORT_RESULT_PATH = REPORTS_DIR / "AIRTABLE_DRY_IMPORT_RESULT.json"

SIDE_EFFECTS_FALSE = {
    "n8n_workflows_called": False,
    "airtable_bases_created": False,
    "airtable_tables_created": False,
    "airtable_fields_created": False,
    "airtable_rows_written": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_modified": False,
    "whatsapp_messages_sent": False,
    "instagram_posts_published": False,
    "content_published": False,
}

FIELD_TYPE_HINTS = {
    "Action ID": "single_line_text",
    "Request ID": "single_line_text",
    "Connector": "single_select",
    "Operation": "single_line_text",
    "Target": "single_line_text",
    "Status": "single_select",
    "Approval Reference": "single_line_text",
    "External Execution Enabled": "checkbox",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    allowed = [char if char.isalnum() else "-" for char in value.upper()]
    return "-".join("".join(allowed).split("-"))[:90] or "AIOS-AIRTABLE-DRY-IMPORT"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _field_type(name: str, value: Any) -> str:
    if name in FIELD_TYPE_HINTS:
        return FIELD_TYPE_HINTS[name]
    if isinstance(value, bool):
        return "checkbox"
    if isinstance(value, (int, float)):
        return "number"
    return "single_line_text"


def _schema_for_payload(payload: dict[str, Any], label: str) -> dict[str, Any]:
    fields = payload.get("fields", {})
    action_id = str(fields.get("Action ID") or "NO_ACTION")
    request_id = str(fields.get("Request ID") or "NO_REQUEST")
    field_maps = [
        {
            "field_name": name,
            "airtable_type": _field_type(name, value),
            "required": name in {"Action ID", "Request ID", "Status"},
            "source_value_preview": value,
            "write_enabled": False,
        }
        for name, value in fields.items()
    ]
    return {
        "schema_id": f"ATS-{_safe_slug(action_id)}",
        "label": label,
        "connector": "airtable",
        "payload_type": payload.get("payload_type"),
        "base_contract": payload.get("base_contract"),
        "table_contract": payload.get("table_contract"),
        "operation": payload.get("operation"),
        "match_field": payload.get("match_field"),
        "request_id": request_id,
        "action_id": action_id,
        "field_count": len(field_maps),
        "fields": field_maps,
        "import_checklist": [
            "Confirm Airtable base is the production Omar RE OS CRM base.",
            "Confirm table name or ID for AIOS Action Queue.",
            "Confirm match field Action ID exists and is unique.",
            "Confirm required fields exist with compatible Airtable field types.",
            "Confirm External Execution Enabled remains false before any first write.",
            "Run one manual test record only after Omar approves live Airtable writeback.",
        ],
        "network_call_enabled": False,
        "write_enabled": False,
        "credentials_included": False,
        "activation_allowed": False,
    }


def _markdown_packet(schema: dict[str, Any]) -> str:
    lines = [
        "# AIOS Airtable Dry Import Schema Map",
        "",
        f"Schema ID: `{schema['schema_id']}`",
        f"Request ID: `{schema['request_id']}`",
        f"Action ID: `{schema['action_id']}`",
        "",
        "## Target",
        "",
        f"- Base contract: `{schema.get('base_contract')}`",
        f"- Table contract: `{schema.get('table_contract')}`",
        f"- Operation: `{schema.get('operation')}`",
        f"- Match field: `{schema.get('match_field')}`",
        "",
        "## Field Map",
        "",
        "| Field | Type | Required | Write Enabled |",
        "|---|---|---:|---:|",
    ]
    for field in schema.get("fields", []):
        lines.append(
            f"| `{field['field_name']}` | `{field['airtable_type']}` | {str(field['required']).lower()} | false |"
        )
    lines.extend(
        [
            "",
            "## Activation Checklist",
            "",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in schema.get("import_checklist", []))
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Network call enabled: `false`",
            "- Write enabled: `false`",
            "- Credentials included: `false`",
            "- Activation allowed: `false`",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_schema(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if schema.get("connector") != "airtable":
        errors.append("connector_not_airtable")
    if not schema.get("base_contract"):
        errors.append("missing_base_contract")
    if not schema.get("table_contract"):
        errors.append("missing_table_contract")
    if schema.get("match_field") != "Action ID":
        errors.append("match_field_not_action_id")
    field_names = {field.get("field_name") for field in schema.get("fields", [])}
    required = {"Action ID", "Request ID", "Status", "External Execution Enabled"}
    missing = sorted(required - field_names)
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")
    if schema.get("network_call_enabled") is not False:
        errors.append("network_call_enabled")
    if schema.get("write_enabled") is not False:
        errors.append("write_enabled")
    if schema.get("credentials_included") is not False:
        errors.append("credentials_included")
    if schema.get("activation_allowed") is not False:
        errors.append("activation_allowed")
    return errors


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    label = str(command.get("label", "local-airtable-dry-import"))
    payload_report = _load_json(CONNECTOR_PAYLOADS_PATH)
    airtable_payloads = [
        payload
        for payload in payload_report.get("payloads", [])
        if payload.get("connector") == "airtable"
        and payload.get("network_call_enabled") is False
        and payload.get("execution_enabled") is False
    ]
    DRY_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    schemas = []
    validation_errors = []

    for payload in airtable_payloads:
        schema = _schema_for_payload(payload, label)
        schema_errors = _validate_schema(schema)
        validation_errors.extend(schema_errors)
        packet_name = f"{_safe_slug(schema['request_id'])}-AIRTABLE-DRY-IMPORT.md"
        packet_path = DRY_IMPORTS_DIR / packet_name
        packet_path.write_text(_markdown_packet(schema), encoding="utf-8")
        sha256 = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        schemas.append(
            {
                **schema,
                "packet_file": packet_name,
                "packet_path": packet_path.relative_to(REPORTS_DIR).as_posix(),
                "packet_sha256": sha256,
            }
        )

    report = {
        "generated_at": _now(),
        "mode": "airtable_dry_import_schema_map_only",
        "payload_report_status": payload_report.get("runner_plan_status"),
        "payloads_ready": payload_report.get("payloads_ready") is True,
        "schema_ready": bool(schemas) and not validation_errors,
        "schema_count": len(schemas),
        "schemas": schemas,
        "validation_errors": validation_errors if schemas else ["airtable_payload_not_ready"],
        "network_call_enabled": False,
        "write_enabled": False,
        "import_enabled": False,
        "activation_enabled": False,
        "credentials_included": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    AIRTABLE_DRY_IMPORT_SCHEMA_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": not validation_errors,
        "schema_ready": report["schema_ready"],
        "schema_count": report["schema_count"],
        "network_call_enabled": False,
        "write_enabled": False,
        "import_enabled": False,
        "activation_enabled": False,
        "credentials_included": False,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    AIRTABLE_DRY_IMPORT_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


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
