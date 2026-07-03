#!/usr/bin/env python3
"""AIOS n8n dry-import builder.

Creates an inactive, credential-free n8n workflow draft from the local n8n
payload contract. This is an import review artifact only. It does not call n8n,
does not activate a workflow, and does not include credentials.
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
DRY_IMPORTS_DIR = REPORTS_DIR / "n8n_dry_imports"
N8N_DRY_IMPORT_MANIFEST_PATH = REPORTS_DIR / "N8N_DRY_IMPORT_MANIFEST.json"
N8N_DRY_IMPORT_RESULT_PATH = REPORTS_DIR / "N8N_DRY_IMPORT_RESULT.json"

SIDE_EFFECTS_FALSE = {
    "n8n_workflows_called": False,
    "n8n_workflows_imported": False,
    "n8n_workflows_activated": False,
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


def _safe_slug(value: str) -> str:
    allowed = [char if char.isalnum() else "-" for char in value.upper()]
    return "-".join("".join(allowed).split("-"))[:80] or "AIOS-N8N-DRY-IMPORT"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _code_node_js(payload: dict[str, Any]) -> str:
    body = payload.get("body", {})
    return (
        "const payload = "
        + json.dumps(body, indent=2, ensure_ascii=False)
        + ";\n"
        + "return [{ json: {\n"
        + "  dry_import_only: true,\n"
        + "  network_call_enabled: false,\n"
        + "  execution_enabled: false,\n"
        + "  source: payload.source,\n"
        + "  request_id: payload.request_id,\n"
        + "  action_id: payload.action_id,\n"
        + "  connector: payload.connector,\n"
        + "  operation: payload.operation,\n"
        + "  target: payload.target,\n"
        + "  approval_reference: payload.approval_reference\n"
        + "} }];\n"
    )


def _workflow_for_payload(payload: dict[str, Any], label: str) -> dict[str, Any]:
    request_id = payload.get("body", {}).get("request_id") or "NO_REQUEST"
    action_id = payload.get("body", {}).get("action_id") or "NO_ACTION"
    return {
        "name": f"AIOS Dry Import - {request_id}",
        "active": False,
        "nodes": [
            {
                "parameters": {},
                "id": "manual-review-trigger",
                "name": "Manual Review Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [280, 300],
            },
            {
                "parameters": {"jsCode": _code_node_js(payload)},
                "id": "build-local-payload",
                "name": "Build Local Payload Contract",
                "type": "n8n-nodes-base.code",
                "typeVersion": 1,
                "position": [520, 300],
            },
            {
                "parameters": {
                    "jsCode": (
                        "return items.map(item => ({ json: {\n"
                        "  ...item.json,\n"
                        "  status: 'STOPPED_BEFORE_EXTERNAL_CALL',\n"
                        "  import_review_only: true,\n"
                        "  credentials_required_before_activation: true,\n"
                        "  live_activation_allowed: false\n"
                        "} }));\n"
                    )
                },
                "id": "stop-before-external-call",
                "name": "Stop Before External Call",
                "type": "n8n-nodes-base.code",
                "typeVersion": 1,
                "position": [760, 300],
            },
        ],
        "connections": {
            "Manual Review Trigger": {
                "main": [[{"node": "Build Local Payload Contract", "type": "main", "index": 0}]]
            },
            "Build Local Payload Contract": {
                "main": [[{"node": "Stop Before External Call", "type": "main", "index": 0}]]
            },
        },
        "settings": {"executionOrder": "v1"},
        "versionId": f"dry-import-{_safe_slug(action_id)}",
        "meta": {
            "instanceId": "AIOS_LOCAL_DRY_IMPORT_ONLY",
            "templateCredsSetupCompleted": False,
            "dryImportOnly": True,
            "label": label,
            "requestId": request_id,
            "actionId": action_id,
            "networkCallEnabled": False,
            "credentialsIncluded": False,
        },
    }


def _validate_workflow(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if workflow.get("active") is not False:
        errors.append("workflow_active_not_false")
    if not workflow.get("nodes"):
        errors.append("workflow_missing_nodes")
    for node in workflow.get("nodes", []):
        if "credentials" in node:
            errors.append(f"{node.get('name')}:credentials_present")
        if node.get("type") not in {"n8n-nodes-base.manualTrigger", "n8n-nodes-base.code"}:
            errors.append(f"{node.get('name')}:unsupported_node_type:{node.get('type')}")
    if workflow.get("meta", {}).get("networkCallEnabled") is not False:
        errors.append("meta_network_call_enabled")
    if workflow.get("meta", {}).get("credentialsIncluded") is not False:
        errors.append("meta_credentials_included")
    return errors


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    label = str(command.get("label", "local-n8n-dry-import"))
    payload_report = _load_json(CONNECTOR_PAYLOADS_PATH)
    n8n_payloads = [
        payload
        for payload in payload_report.get("payloads", [])
        if payload.get("connector") == "n8n"
        and payload.get("network_call_enabled") is False
        and payload.get("execution_enabled") is False
    ]
    DRY_IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    workflows = []
    validation_errors = []

    for payload in n8n_payloads:
        workflow = _workflow_for_payload(payload, label)
        workflow_errors = _validate_workflow(workflow)
        validation_errors.extend(workflow_errors)
        request_id = payload.get("body", {}).get("request_id") or "NO_REQUEST"
        file_name = f"{_safe_slug(request_id)}-N8N-DRY-IMPORT.json"
        path = DRY_IMPORTS_DIR / file_name
        path.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        workflows.append(
            {
                "file": file_name,
                "path": path.relative_to(REPORTS_DIR).as_posix(),
                "name": workflow.get("name"),
                "active": workflow.get("active"),
                "node_count": len(workflow.get("nodes", [])),
                "credentials_included": False,
                "network_call_enabled": False,
                "sha256": sha256,
            }
        )

    manifest = {
        "generated_at": _now(),
        "mode": "n8n_dry_import_only",
        "payload_report_status": payload_report.get("runner_plan_status"),
        "payloads_ready": payload_report.get("payloads_ready") is True,
        "workflow_ready": bool(workflows) and not validation_errors,
        "workflow_count": len(workflows),
        "workflows": workflows,
        "validation_errors": validation_errors if workflows else ["n8n_payload_not_ready"],
        "import_enabled": False,
        "activation_enabled": False,
        "credentials_included": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    N8N_DRY_IMPORT_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": not validation_errors,
        "workflow_ready": manifest["workflow_ready"],
        "workflow_count": manifest["workflow_count"],
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
    N8N_DRY_IMPORT_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
