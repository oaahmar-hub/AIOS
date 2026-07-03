#!/usr/bin/env python3
"""Build AIOS connector readiness matrix.

This runtime gives one activation view for the AIOS end-state connections:
Airtable, Google Drive, Gmail, Calendar, Notion, WhatsApp, Instagram, n8n, and
future channels. It reads local dry-run/review artifacts only and never calls
external services or enables credentials.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "CONNECTOR_READINESS_REPORT.json"

SOURCE_REPORTS = {
    "connector_manifest": "CONNECTOR_EXECUTION_MANIFEST.json",
    "connector_dry_run": "CONNECTOR_DRY_RUN_PLAN.json",
    "live_run_request": "LIVE_RUN_REQUEST.json",
    "live_connector_runner": "LIVE_CONNECTOR_RUNNER_PLAN.json",
    "connector_payloads": "CONNECTOR_PARAMETER_PAYLOADS.json",
    "activation_checklist": "CONNECTOR_ACTIVATION_CHECKLIST.json",
    "n8n_dry_import": "N8N_DRY_IMPORT_MANIFEST.json",
    "airtable_dry_import": "AIRTABLE_DRY_IMPORT_SCHEMA.json",
    "notion_dry_import": "NOTION_DRY_IMPORT_MANIFEST.json",
    "google_workspace_dry_import": "GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json",
    "social_content_dry_review": "SOCIAL_CONTENT_DRY_REVIEW_MANIFEST.json",
    "mobile_command": "MOBILE_COMMAND_REPORT.json",
    "unified_memory": "UNIFIED_MEMORY_REPORT.json",
    "aios_brain": "AIOS_BRAIN_REPORT.json",
}

WHATSAPP_PROOF_FILES = [
    "automation/whatsapp_provider_gateway/reports/GATEWAY_TO_PIPELINE_VALIDATION.json",
    "automation/whatsapp_provider_gateway/reports/CONVERSATION_STATE_VALIDATION.json",
    "automation/whatsapp_provider_gateway/reports/wasender_live_relay.log.jsonl",
    "automation/whatsapp_provider_gateway/runtime/whatsapp_provider_gateway.py",
]

EXTERNAL_SIDE_EFFECTS = {
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
    "messages_sent": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "airtable_rows_written": False,
    "notion_pages_created": False,
    "instagram_posts_published": False,
    "n8n_workflows_imported": False,
    "n8n_workflows_activated": False,
    "future_channel_activated": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _exists(rel: str) -> bool:
    return (AIOS_ROOT / rel).exists()


def _readiness_status(local_ready: bool, credentials_required: bool = True) -> str:
    if local_ready and credentials_required:
        return "local_ready_credentials_required"
    if local_ready:
        return "local_ready_no_credentials_needed"
    return "blocked_until_payload_or_validation_ready"


def build_connectors(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    payloads = reports["connector_payloads"].get("payloads", [])
    payload_connectors = {payload.get("connector") for payload in payloads}
    google_artifacts = reports["google_workspace_dry_import"].get("artifacts", [])
    social_artifacts = reports["social_content_dry_review"].get("artifacts", [])
    mobile_contracts = {
        contract.get("connector")
        for action in reports["mobile_command"].get("actions", [])
        for contract in action.get("connector_contracts", [])
    }
    whatsapp_ready = any(_exists(path) for path in WHATSAPP_PROOF_FILES[:2]) and _exists(WHATSAPP_PROOF_FILES[-1])
    connectors = [
        {
            "connector": "n8n",
            "purpose": "workflow automation and orchestration",
            "status": _readiness_status(reports["n8n_dry_import"].get("workflow_ready") is True or "n8n" in payload_connectors),
            "local_artifacts": ["N8N_DRY_IMPORT_MANIFEST.json", "CONNECTOR_PARAMETER_PAYLOADS.json"],
            "required_approval": ["Omar final approval", "n8n credentials", "workflow import approval", "activation approval"],
        },
        {
            "connector": "airtable",
            "purpose": "CRM source of truth for leads, contacts, tasks, approvals, and action queue",
            "status": _readiness_status(reports["airtable_dry_import"].get("schema_ready") is True or "airtable" in payload_connectors or "airtable_task" in mobile_contracts),
            "local_artifacts": ["AIRTABLE_DRY_IMPORT_SCHEMA.json", "UNIFIED_MEMORY_REPORT.json"],
            "required_approval": ["Airtable OAuth/API key", "base/table confirmation", "field mapping approval"],
        },
        {
            "connector": "gmail",
            "purpose": "draft-only client and follow-up email preparation",
            "status": _readiness_status(any(item.get("connector") == "gmail_draft" for item in google_artifacts) or "gmail_draft" in mobile_contracts),
            "local_artifacts": ["GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json", "CRM_FOLLOWUP_REPORT.json"],
            "required_approval": ["Google OAuth", "Gmail account confirmation", "send approval"],
        },
        {
            "connector": "google_calendar",
            "purpose": "calendar availability review and future viewing handoff",
            "status": _readiness_status(any(item.get("connector") == "calendar_read" for item in google_artifacts) or "calendar_read" in mobile_contracts),
            "local_artifacts": ["GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json", "MOBILE_COMMAND_REPORT.json"],
            "required_approval": ["Google OAuth", "calendar account confirmation", "write approval for future events"],
        },
        {
            "connector": "google_drive",
            "purpose": "document drafts, knowledge base, campaign assets, and future file sync",
            "status": _readiness_status(any(item.get("connector") == "drive_draft" for item in google_artifacts) or "drive_draft" in mobile_contracts),
            "local_artifacts": ["GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json", "KNOWLEDGE_VAULT_REPORT.json"],
            "required_approval": ["Google OAuth", "Drive folder confirmation", "file create/write approval"],
        },
        {
            "connector": "notion",
            "purpose": "knowledge pages, case notes, operating documentation, and future team workspace",
            "status": _readiness_status(reports["notion_dry_import"].get("page_ready") is True or "notion" in payload_connectors or "notion" in mobile_contracts),
            "local_artifacts": ["NOTION_DRY_IMPORT_MANIFEST.json", "UNIFIED_MEMORY_REPORT.json"],
            "required_approval": ["Notion OAuth/API key", "workspace/database confirmation", "page creation approval"],
        },
        {
            "connector": "whatsapp",
            "purpose": "inbound/outbound client conversation channel with safety and approval gates",
            "status": _readiness_status(whatsapp_ready),
            "local_artifacts": WHATSAPP_PROOF_FILES,
            "required_approval": ["provider credentials", "production number confirmation", "reply/send approval", "no Facebook-login path unless explicitly approved"],
        },
        {
            "connector": "instagram",
            "purpose": "future social publishing from approved content drafts",
            "status": _readiness_status(any(item.get("connector") == "instagram_draft" for item in social_artifacts) or "instagram_draft" in mobile_contracts),
            "local_artifacts": ["SOCIAL_CONTENT_DRY_REVIEW_MANIFEST.json", "CONTENT_FACTORY_REPORT.json"],
            "required_approval": ["Instagram/Meta or social connector auth", "RERA permit check", "publish approval"],
        },
        {
            "connector": "future_channels",
            "purpose": "future portals, video, voice, creative production, and additional messaging channels",
            "status": "planned_contract_only",
            "local_artifacts": ["AIOS_BRAIN_REPORT.json", "CONNECTOR_ACTIVATION_CHECKLIST.json"],
            "required_approval": ["channel-specific credentials", "business/legal review", "explicit activation approval"],
        },
    ]
    for connector in connectors:
        connector["execution_enabled"] = False
        connector["network_call_enabled"] = False
        connector["credentials_included"] = False
        connector["activation_allowed"] = False
    return connectors


def build_summary(connectors: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [item for item in connectors if item["status"].startswith("local_ready")]
    blocked = [item for item in connectors if item["status"].startswith("blocked")]
    planned = [item for item in connectors if item["status"].startswith("planned")]
    return {
        "connector_count": len(connectors),
        "local_ready_count": len(ready),
        "blocked_count": len(blocked),
        "planned_count": len(planned),
        "activation_allowed_count": len([item for item in connectors if item.get("activation_allowed")]),
        "all_execution_disabled": all(item.get("execution_enabled") is False and item.get("network_call_enabled") is False for item in connectors),
        "all_credentials_excluded": all(item.get("credentials_included") is False for item in connectors),
    }


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    connectors = build_connectors(reports)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_connector_readiness_no_external_side_effects",
        "summary": build_summary(connectors),
        "connectors": connectors,
        "activation_sequence": [
            "Review local readiness matrix.",
            "Resolve connector-specific OAuth/API credential blockers.",
            "Confirm destination account/base/folder/workspace/channel.",
            "Run dry import or dry review artifact.",
            "Get Omar final approval.",
            "Only then run a separate live connector activation path.",
        ],
        "source_reports": SOURCE_REPORTS,
        "external_side_effects": EXTERNAL_SIDE_EFFECTS,
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
