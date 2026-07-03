#!/usr/bin/env python3
"""AIOS connector payload builder.

Builds local-only connector parameter payloads from the disabled live runner
plan. This prepares exact n8n and Airtable payload shapes for review without
making network calls or enabling connector execution.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import build as build_command_center_data
from disabled_live_connector_runner import LIVE_CONNECTOR_RUNNER_PLAN_PATH


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
CONNECTOR_PAYLOADS_PATH = REPORTS_DIR / "CONNECTOR_PARAMETER_PAYLOADS.json"
CONNECTOR_PAYLOADS_RESULT_PATH = REPORTS_DIR / "CONNECTOR_PARAMETER_PAYLOADS_RESULT.json"

SUPPORTED_PAYLOAD_CONNECTORS = {
    "n8n",
    "airtable",
    "notion",
    "gmail_draft",
    "calendar_read",
    "drive_draft",
    "content_factory",
    "instagram_draft",
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


def _payload_for_n8n(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "n8n",
        "payload_type": "workflow_call_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "method": "POST",
        "endpoint_contract": "n8n_workflow_or_webhook_endpoint_disabled_until_final_activation",
        "workflow_key": "AIOS_MASTER_ROUTER",
        "operation": step.get("operation"),
        "target": step.get("target"),
        "body": {
            "source": "AIOS_CENTRAL_ORCHESTRATOR",
            "request_id": runner_plan.get("request_id"),
            "action_id": step.get("action_id"),
            "connector": step.get("connector"),
            "operation": step.get("operation"),
            "target": step.get("target"),
            "mode": "validated_plan_only_no_external_calls",
            "approval_reference": runner_plan.get("approval_reference"),
        },
    }


def _payload_for_airtable(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "airtable",
        "payload_type": "record_upsert_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "base_contract": "Omar RE OS CRM tables",
        "table_contract": "AIOS Action Queue",
        "operation": "upsert",
        "match_field": "Action ID",
        "fields": {
            "Action ID": step.get("action_id"),
            "Request ID": runner_plan.get("request_id"),
            "Connector": step.get("connector"),
            "Operation": step.get("operation"),
            "Target": step.get("target"),
            "Status": "validated_plan_only",
            "Approval Reference": runner_plan.get("approval_reference"),
            "External Execution Enabled": False,
        },
    }


def _payload_for_notion(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "notion",
        "payload_type": "page_create_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "workspace_contract": "AIOS Notion workspace",
        "database_contract": "AIOS Operations Knowledge Base",
        "operation": "create_page",
        "match_field": "Action ID",
        "properties": {
            "Title": "AIOS Workflow Packet",
            "Action ID": step.get("action_id"),
            "Request ID": runner_plan.get("request_id"),
            "Connector": step.get("connector"),
            "Operation": step.get("operation"),
            "Target": step.get("target"),
            "Status": "validated_plan_only",
            "Approval Reference": runner_plan.get("approval_reference"),
            "External Execution Enabled": False,
        },
        "children": [
            {
                "type": "paragraph",
                "text": "AIOS generated this local Notion page contract for review only. No Notion API call is enabled.",
            }
        ],
    }


def _payload_for_gmail_draft(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "gmail_draft",
        "payload_type": "gmail_draft_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "send_enabled": False,
        "account_contract": "Gmail account",
        "operation": "create_draft_review_only",
        "target": step.get("target"),
        "draft": {
            "to": "omar_review_only@example.invalid",
            "subject": "AIOS Daily Briefing - Review Draft",
            "body": "AIOS prepared this Gmail draft contract locally. No Gmail API call is enabled.",
            "request_id": runner_plan.get("request_id"),
            "action_id": step.get("action_id"),
            "approval_reference": runner_plan.get("approval_reference"),
        },
    }


def _payload_for_calendar_read(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "calendar_read",
        "payload_type": "calendar_availability_read_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "calendar_write_enabled": False,
        "account_contract": "Google Calendar account",
        "operation": "read_availability_review_only",
        "target": step.get("target"),
        "query": {
            "calendar": "primary",
            "window": "next_7_days",
            "request_id": runner_plan.get("request_id"),
            "action_id": step.get("action_id"),
            "approval_reference": runner_plan.get("approval_reference"),
        },
    }


def _payload_for_drive_draft(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "drive_draft",
        "payload_type": "drive_file_draft_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "file_create_enabled": False,
        "account_contract": "Google Drive account",
        "operation": "prepare_file_draft_review_only",
        "target": step.get("target"),
        "file": {
            "name": "AIOS Content Draft - Review Only.md",
            "mime_type": "text/markdown",
            "folder_contract": "AIOS Google Drive knowledge base",
            "body": "AIOS prepared this Google Drive file contract locally. No Drive API call is enabled.",
            "request_id": runner_plan.get("request_id"),
            "action_id": step.get("action_id"),
            "approval_reference": runner_plan.get("approval_reference"),
        },
    }


def _payload_for_content_factory(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "content_factory",
        "payload_type": "content_asset_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "asset_generation_enabled": False,
        "publish_enabled": False,
        "operation": "prepare_content_asset_review_only",
        "target": step.get("target"),
        "asset": {
            "title": "AIOS Content Draft - Review Only",
            "format": "caption_campaign_brief",
            "channel": "internal_content_factory",
            "brief": "Prepare a premium real-estate content draft for Omar review. No asset generation or publishing is enabled.",
            "request_id": runner_plan.get("request_id"),
            "action_id": step.get("action_id"),
            "approval_reference": runner_plan.get("approval_reference"),
        },
    }


def _payload_for_instagram_draft(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector": "instagram_draft",
        "payload_type": "instagram_post_draft_contract",
        "network_call_enabled": False,
        "execution_enabled": False,
        "publish_enabled": False,
        "account_contract": "Instagram / future social connector",
        "operation": "prepare_post_draft_review_only",
        "target": step.get("target"),
        "post": {
            "caption": "AIOS prepared this Instagram post draft locally. No Instagram API call or publish action is enabled.",
            "media_required": True,
            "status": "draft_review_only",
            "request_id": runner_plan.get("request_id"),
            "action_id": step.get("action_id"),
            "approval_reference": runner_plan.get("approval_reference"),
        },
    }


def _payload_for_step(step: dict[str, Any], runner_plan: dict[str, Any]) -> dict[str, Any] | None:
    connector = step.get("connector")
    if connector == "n8n":
        return _payload_for_n8n(step, runner_plan)
    if connector == "airtable":
        return _payload_for_airtable(step, runner_plan)
    if connector == "notion":
        return _payload_for_notion(step, runner_plan)
    if connector == "gmail_draft":
        return _payload_for_gmail_draft(step, runner_plan)
    if connector == "calendar_read":
        return _payload_for_calendar_read(step, runner_plan)
    if connector == "drive_draft":
        return _payload_for_drive_draft(step, runner_plan)
    if connector == "content_factory":
        return _payload_for_content_factory(step, runner_plan)
    if connector == "instagram_draft":
        return _payload_for_instagram_draft(step, runner_plan)
    return None


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    runner_plan = _load_json(LIVE_CONNECTOR_RUNNER_PLAN_PATH)
    planned_steps = runner_plan.get("planned_steps", [])
    payloads = []
    skipped_steps = []
    validation_errors = []

    if runner_plan.get("runner_status") != "validated_plan_only_no_external_calls":
        validation_errors.append("runner_plan_not_validated")

    for step in planned_steps:
        connector = step.get("connector")
        if connector not in SUPPORTED_PAYLOAD_CONNECTORS:
            skipped_steps.append(
                {
                    "action_id": step.get("action_id"),
                    "connector": connector,
                    "reason": "payload_builder_not_required_for_connector",
                }
            )
            continue
        if step.get("validated") is not True:
            validation_errors.append(f"{step.get('action_id')}:{connector}:step_not_validated")
            continue
        if step.get("would_call_external_service") is not False:
            validation_errors.append(f"{step.get('action_id')}:{connector}:would_call_external_service")
            continue
        payload = _payload_for_step(step, runner_plan)
        if payload:
            payloads.append(payload)

    payload_errors = []
    for payload in payloads:
        if payload.get("network_call_enabled") is not False:
            payload_errors.append(f"{payload.get('connector')}:network_call_enabled")
        if payload.get("execution_enabled") is not False:
            payload_errors.append(f"{payload.get('connector')}:execution_enabled")

    report = {
        "generated_at": _now(),
        "mode": "connector_payload_contracts_only",
        "runner_plan_status": runner_plan.get("runner_status", "missing"),
        "request_id": runner_plan.get("request_id"),
        "payloads_ready": bool(payloads) and not validation_errors and not payload_errors,
        "payload_count": len(payloads),
        "skipped_step_count": len(skipped_steps),
        "validation_errors": validation_errors + payload_errors,
        "payloads": payloads,
        "skipped_steps": skipped_steps,
        "execution_enabled": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    CONNECTOR_PAYLOADS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": not payload_errors,
        "payloads_ready": report["payloads_ready"],
        "payload_count": report["payload_count"],
        "skipped_step_count": report["skipped_step_count"],
        "validation_error_count": len(report["validation_errors"]),
        "execution_enabled": False,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    CONNECTOR_PAYLOADS_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
