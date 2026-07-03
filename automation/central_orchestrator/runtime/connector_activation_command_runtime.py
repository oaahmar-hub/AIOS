#!/usr/bin/env python3
"""Build the AIOS connector activation command plan.

This runtime turns the local connector readiness matrix into an operational
setup plan. It does not perform OAuth, read credentials, call external APIs, or
activate any connector. It only produces the next safe command and blocker
state for Omar to review before a future live activation path.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "CONNECTOR_ACTIVATION_COMMAND_PLAN.json"
READINESS_PATH = REPORTS_DIR / "CONNECTOR_READINESS_REPORT.json"

CONNECTOR_ORDER = [
    "whatsapp",
    "airtable",
    "gmail",
    "google_calendar",
    "google_drive",
    "notion",
    "n8n",
    "instagram",
    "future_channels",
]

CONNECTOR_COMMANDS = {
    "whatsapp": {
        "setup_command": "@activate-whatsapp",
        "validation_command": "@validate-whatsapp-gateway",
        "handoff": "Confirm provider credential path and production number without Facebook login.",
        "risk_gate": "Omar approves any send/reply behavior before outbound activation.",
        "credential_scope": ["provider_api_key", "business_number", "webhook_secret"],
    },
    "airtable": {
        "setup_command": "@activate-airtable",
        "validation_command": "@airtable-dry-import",
        "handoff": "Confirm base, tables, field mapping, and API/OAuth path.",
        "risk_gate": "Omar approves CRM writeback table mapping before row creation.",
        "credential_scope": ["airtable_token_or_oauth", "base_id"],
    },
    "gmail": {
        "setup_command": "@activate-gmail",
        "validation_command": "@google-workspace-dry-review",
        "handoff": "Connect Google OAuth and keep draft/send permissions separated.",
        "risk_gate": "Omar approves sending; draft creation remains separate from send.",
        "credential_scope": ["google_oauth", "gmail_account"],
    },
    "google_calendar": {
        "setup_command": "@activate-calendar",
        "validation_command": "@google-workspace-dry-review",
        "handoff": "Connect calendar read/write scope and confirm calendar ID.",
        "risk_gate": "Omar approves event creation and invite sends.",
        "credential_scope": ["google_oauth", "calendar_id"],
    },
    "google_drive": {
        "setup_command": "@activate-drive",
        "validation_command": "@google-workspace-dry-review",
        "handoff": "Connect Drive scope and confirm folder structure.",
        "risk_gate": "Omar approves file create/update permissions and destination folders.",
        "credential_scope": ["google_oauth", "drive_folder_ids"],
    },
    "notion": {
        "setup_command": "@activate-notion",
        "validation_command": "@notion-dry-import",
        "handoff": "Connect Notion integration and confirm workspace/database targets.",
        "risk_gate": "Omar approves page/database creation targets.",
        "credential_scope": ["notion_token_or_oauth", "workspace_id", "database_ids"],
    },
    "n8n": {
        "setup_command": "@activate-n8n",
        "validation_command": "@n8n-dry-import",
        "handoff": "Confirm n8n credentials, import target, and workflow activation status.",
        "risk_gate": "Omar approves workflow import first, activation second.",
        "credential_scope": ["n8n_api_key_or_oauth", "n8n_project_id"],
    },
    "instagram": {
        "setup_command": "@activate-instagram",
        "validation_command": "@social-content-dry-review",
        "handoff": "Connect social publishing auth only after RERA and content approval controls are confirmed.",
        "risk_gate": "Omar approves every publish action and required permit checks.",
        "credential_scope": ["social_auth", "instagram_business_account"],
    },
    "future_channels": {
        "setup_command": "@activate-future-channel",
        "validation_command": "@readiness",
        "handoff": "Create a channel-specific contract before adding any new live connector.",
        "risk_gate": "Business/legal review and explicit activation approval required.",
        "credential_scope": ["channel_specific_credentials"],
    },
}

EXTERNAL_SIDE_EFFECTS = {
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
    "messages_sent": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_created": False,
    "airtable_rows_written": False,
    "notion_pages_created": False,
    "instagram_posts_published": False,
    "n8n_workflows_imported": False,
    "n8n_workflows_activated": False,
    "future_channel_activated": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _phase_for(connector: dict[str, Any]) -> str:
    status = connector.get("status", "")
    if status.startswith("local_ready"):
        return "credential_authorization"
    if status.startswith("planned"):
        return "contract_design"
    return "local_artifact_repair"


def _blockers_for(connector: dict[str, Any]) -> list[str]:
    status = connector.get("status", "")
    required = connector.get("required_approval", [])
    blockers = []
    if not status.startswith("local_ready"):
        blockers.append("local readiness artifact incomplete")
    blockers.extend(str(item) for item in required)
    if connector.get("execution_enabled") is not False:
        blockers.append("execution flag must remain false until final approval")
    if connector.get("credentials_included") is not False:
        blockers.append("credentials must not be embedded in local plan")
    return blockers


def build_activation_steps(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    connectors = {row.get("connector"): row for row in readiness.get("connectors", [])}
    steps = []
    for index, name in enumerate(CONNECTOR_ORDER, start=1):
        connector = connectors.get(name, {"connector": name, "status": "missing_from_readiness"})
        command = CONNECTOR_COMMANDS[name]
        blockers = _blockers_for(connector)
        ready_for_login = connector.get("status", "").startswith("local_ready")
        steps.append(
            {
                "sequence": index,
                "connector": name,
                "phase": _phase_for(connector),
                "status": "ready_for_user_login_or_credential" if ready_for_login else "blocked_before_login",
                "setup_command": command["setup_command"],
                "validation_command": command["validation_command"],
                "handoff": command["handoff"],
                "risk_gate": command["risk_gate"],
                "credential_scope": command["credential_scope"],
                "credential_value_included": False,
                "oauth_started": False,
                "network_call_enabled": False,
                "activation_allowed": False,
                "blockers": blockers,
                "local_artifacts": connector.get("local_artifacts", []),
            }
        )
    return steps


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    readiness = _load_json(READINESS_PATH)
    steps = build_activation_steps(readiness)
    ready_steps = [step for step in steps if step["status"] == "ready_for_user_login_or_credential"]
    blocked_steps = [step for step in steps if step["status"] == "blocked_before_login"]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_connector_activation_command_plan_no_external_side_effects",
        "source_report": "CONNECTOR_READINESS_REPORT.json",
        "summary": {
            "connector_count": len(steps),
            "ready_for_user_login_count": len(ready_steps),
            "blocked_before_login_count": len(blocked_steps),
            "activation_allowed_count": len([step for step in steps if step.get("activation_allowed")]),
            "oauth_started_count": len([step for step in steps if step.get("oauth_started")]),
            "all_network_calls_disabled": all(step.get("network_call_enabled") is False for step in steps),
            "all_credentials_excluded": all(step.get("credential_value_included") is False for step in steps),
        },
        "activation_steps": steps,
        "global_sequence": [
            "Run local readiness validation.",
            "Select one connector from the activation command plan.",
            "Obtain Omar approval for the connector setup attempt.",
            "Complete OAuth/login/credential entry outside this local report.",
            "Run connector-specific dry validation.",
            "Obtain separate approval for first live write/send/import.",
        ],
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
