#!/usr/bin/env python3
"""AIOS Google Workspace dry-review builder.

Creates local review artifacts from Gmail, Calendar, and Drive payload
contracts. It never calls Google APIs, never sends email, never creates calendar
events, and never creates or modifies Drive files.
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
DRY_IMPORTS_DIR = REPORTS_DIR / "google_workspace_dry_imports"
GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST_PATH = REPORTS_DIR / "GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json"
GOOGLE_WORKSPACE_DRY_IMPORT_RESULT_PATH = REPORTS_DIR / "GOOGLE_WORKSPACE_DRY_IMPORT_RESULT.json"

GOOGLE_CONNECTORS = {"gmail_draft", "calendar_read", "drive_draft"}

SIDE_EFFECTS_FALSE = {
    "n8n_workflows_called": False,
    "airtable_rows_written": False,
    "notion_pages_created": False,
    "gmail_drafts_created": False,
    "gmail_messages_sent": False,
    "calendar_events_created": False,
    "calendar_events_updated": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "whatsapp_messages_sent": False,
    "instagram_posts_published": False,
    "content_published": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    allowed = [char if char.isalnum() else "-" for char in value.upper()]
    return "-".join("".join(allowed).split("-"))[:90] or "AIOS-GOOGLE-WORKSPACE-DRY-IMPORT"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _artifact_for_payload(payload: dict[str, Any], label: str) -> dict[str, Any]:
    connector = payload.get("connector")
    action_id = ""
    request_id = ""
    if connector == "gmail_draft":
        draft = payload.get("draft", {})
        action_id = str(draft.get("action_id") or "NO_ACTION")
        request_id = str(draft.get("request_id") or "NO_REQUEST")
        title = "Gmail Draft Review"
        disabled_flags = {"send_enabled": payload.get("send_enabled") is False}
    elif connector == "calendar_read":
        query = payload.get("query", {})
        action_id = str(query.get("action_id") or "NO_ACTION")
        request_id = str(query.get("request_id") or "NO_REQUEST")
        title = "Calendar Availability Read Review"
        disabled_flags = {"calendar_write_enabled": payload.get("calendar_write_enabled") is False}
    else:
        file_payload = payload.get("file", {})
        action_id = str(file_payload.get("action_id") or "NO_ACTION")
        request_id = str(file_payload.get("request_id") or "NO_REQUEST")
        title = "Drive File Draft Review"
        disabled_flags = {"file_create_enabled": payload.get("file_create_enabled") is False}
    return {
        "artifact_id": f"GWS-{_safe_slug(connector or 'google')}-{_safe_slug(action_id)}",
        "label": label,
        "title": title,
        "connector": connector,
        "payload_type": payload.get("payload_type"),
        "account_contract": payload.get("account_contract"),
        "operation": payload.get("operation"),
        "target": payload.get("target"),
        "request_id": request_id,
        "action_id": action_id,
        "payload": payload,
        "disabled_flags": disabled_flags,
        "network_call_enabled": False,
        "execution_enabled": False,
        "credentials_included": False,
        "activation_allowed": False,
    }


def _markdown_artifact(artifact: dict[str, Any]) -> str:
    payload = artifact.get("payload", {})
    lines = [
        f"# AIOS Google Workspace Dry Review - {artifact['title']}",
        "",
        f"Artifact ID: `{artifact['artifact_id']}`",
        f"Request ID: `{artifact['request_id']}`",
        f"Action ID: `{artifact['action_id']}`",
        "",
        "## Target",
        "",
        f"- Connector: `{artifact.get('connector')}`",
        f"- Account contract: `{artifact.get('account_contract')}`",
        f"- Operation: `{artifact.get('operation')}`",
        f"- Target: `{artifact.get('target')}`",
        "",
        "## Payload Preview",
        "",
        "```json",
        json.dumps(payload, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Safety",
        "",
        "- Network call enabled: `false`",
        "- Execution enabled: `false`",
        "- Credentials included: `false`",
        "- Activation allowed: `false`",
    ]
    for key, value in artifact.get("disabled_flags", {}).items():
        lines.append(f"- {key}: `{str(not value).lower() if False else 'false'}`")
    lines.append("")
    return "\n".join(lines)


def _validate_artifact(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    connector = artifact.get("connector")
    if connector not in GOOGLE_CONNECTORS:
        errors.append(f"unsupported_google_connector:{connector}")
    if not artifact.get("account_contract"):
        errors.append("missing_account_contract")
    if not artifact.get("operation"):
        errors.append("missing_operation")
    if artifact.get("network_call_enabled") is not False:
        errors.append("network_call_enabled")
    if artifact.get("execution_enabled") is not False:
        errors.append("execution_enabled")
    if artifact.get("credentials_included") is not False:
        errors.append("credentials_included")
    if artifact.get("activation_allowed") is not False:
        errors.append("activation_allowed")
    for flag, disabled in artifact.get("disabled_flags", {}).items():
        if disabled is not True:
            errors.append(f"{flag}_not_disabled")
    return errors


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    label = str(command.get("label", "local-google-workspace-dry-review"))
    payload_report = _load_json(CONNECTOR_PAYLOADS_PATH)
    google_payloads = [
        payload
        for payload in payload_report.get("payloads", [])
        if payload.get("connector") in GOOGLE_CONNECTORS
        and payload.get("network_call_enabled") is False
        and payload.get("execution_enabled") is False
    ]
    DRY_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = []
    validation_errors = []

    for payload in google_payloads:
        artifact = _artifact_for_payload(payload, label)
        artifact_errors = _validate_artifact(artifact)
        validation_errors.extend(artifact_errors)
        file_name = f"{_safe_slug(artifact['request_id'])}-{_safe_slug(artifact['connector'])}-DRY-REVIEW.md"
        path = DRY_IMPORTS_DIR / file_name
        path.write_text(_markdown_artifact(artifact), encoding="utf-8")
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append(
            {
                **artifact,
                "packet_file": file_name,
                "packet_path": path.relative_to(REPORTS_DIR).as_posix(),
                "packet_sha256": sha256,
            }
        )

    manifest = {
        "generated_at": _now(),
        "mode": "google_workspace_dry_review_only",
        "payload_report_status": payload_report.get("runner_plan_status"),
        "payloads_ready": payload_report.get("payloads_ready") is True,
        "artifact_ready": bool(artifacts) and not validation_errors,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "validation_errors": validation_errors if artifacts else ["google_workspace_payload_not_ready"],
        "network_call_enabled": False,
        "execution_enabled": False,
        "credentials_included": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": not validation_errors,
        "artifact_ready": manifest["artifact_ready"],
        "artifact_count": manifest["artifact_count"],
        "network_call_enabled": False,
        "execution_enabled": False,
        "credentials_included": False,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    GOOGLE_WORKSPACE_DRY_IMPORT_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
