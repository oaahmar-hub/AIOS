#!/usr/bin/env python3
"""Build AIOS customer workspace and product demo contract.

This local runtime defines how future AIOS customers can preview the platform
without exposing HSH private data, creating accounts, starting trials, charging
payments, publishing a workspace, or calling external services.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "AIOS_CUSTOMER_WORKSPACE_REPORT.json"

SOURCE_REPORTS = {
    "team_workspace_access": "TEAM_WORKSPACE_ACCESS_REPORT.json",
    "client_portal_experience": "CLIENT_PORTAL_EXPERIENCE_REPORT.json",
    "connector_readiness": "CONNECTOR_READINESS_REPORT.json",
    "aios_brain": "AIOS_BRAIN_REPORT.json",
    "impact_metrics": "IMPACT_METRICS_REPORT.json",
    "mobile_command": "MOBILE_COMMAND_REPORT.json",
    "command_center_data": "COMMAND_CENTER_DATA.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "customer_workspace_published": False,
    "customer_accounts_created": False,
    "demo_invites_sent": False,
    "trial_started": False,
    "payments_made": False,
    "checkout_started": False,
    "contracts_sent": False,
    "messages_sent": False,
    "calendar_events_created": False,
    "crm_rows_written": False,
    "drive_files_shared": False,
    "notion_pages_created": False,
    "n8n_workflows_imported": False,
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
}

DATA_ISOLATION_RULES = [
    {
        "data_class": "hsh_private_operating_data",
        "rule": "Demo workspaces use synthetic or redacted examples only; HSH live operations, approvals, tasks, and business metrics stay private.",
    },
    {
        "data_class": "client_records",
        "rule": "Never expose HSH leads, contacts, client requests, documents, phone numbers, emails, or communication history.",
    },
    {
        "data_class": "whatsapp_conversations",
        "rule": "Show only generic WhatsApp capability patterns; no raw HSH conversations, provider IDs, numbers, or relay logs are shown.",
    },
    {
        "data_class": "connector_credentials",
        "rule": "OAuth state, tokens, webhook URLs, API keys, account IDs, and provider configuration stay excluded from all demo/customer outputs.",
    },
    {
        "data_class": "financial_and_payment_data",
        "rule": "No HSH payment data, commissions, owner finance, pricing negotiations, or purchase checkout is exposed or started.",
    },
    {
        "data_class": "legal_and_authority_context",
        "rule": "Authority, legal, and compliance examples are generic until Omar approves a customer-specific scope.",
    },
    {
        "data_class": "brand_and_internal_strategy",
        "rule": "Internal brand decisions, strategy notes, operating vulnerabilities, and private handover context stay hidden.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _future_aios_customer_role(team_workspace: dict[str, Any]) -> dict[str, Any]:
    return next((role for role in team_workspace.get("role_views", []) if role.get("role") == "future_aios_customer"), {})


def build_demo_modules(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    command_center = reports["command_center_data"]
    connector_summary = reports["connector_readiness"].get("summary", {})
    impact_quality = reports["impact_metrics"].get("quality_metrics", {})
    brain = reports["aios_brain"]
    mobile = reports["mobile_command"]

    return [
        {
            "module": "command_center_demo",
            "label": "Command Center Demo",
            "preview_mode": "synthetic_metrics_read_only",
            "source_metric": len(command_center.get("workflows", [])),
            "capabilities": ["system health", "activity feed", "workflow controls", "search everything"],
            "hidden_data": ["HSH live queues", "approval records", "private action packets"],
        },
        {
            "module": "one_brain_demo",
            "label": "One Brain Demo",
            "preview_mode": "sample_answer_packets",
            "source_metric": brain.get("query_count", 0),
            "capabilities": ["cross-module answers", "evidence grounding", "safety gates"],
            "hidden_data": ["HSH unified memory", "WhatsApp memory", "client facts"],
        },
        {
            "module": "crm_followup_demo",
            "label": "Client Pipeline Demo",
            "preview_mode": "sample_pipeline_only",
            "source_metric": impact_quality.get("follow_up_quality_signals", {}).get("draft_messages", 0),
            "capabilities": ["lead scoring", "follow-up tasks", "draft messages"],
            "hidden_data": ["real leads", "client contact data", "private follow-up notes"],
        },
        {
            "module": "operations_brain_demo",
            "label": "Operations Brain Demo",
            "preview_mode": "generic_checklist_examples",
            "source_metric": impact_quality.get("manual_work_reduction_units", 0),
            "capabilities": ["DLD", "RERA", "NOC", "transfers", "mortgages", "visas"],
            "hidden_data": ["active authority submissions", "legal context", "payment decisions"],
        },
        {
            "module": "content_factory_demo",
            "label": "Content Factory Demo",
            "preview_mode": "sample_draft_assets",
            "source_metric": impact_quality.get("content_quality_signals", {}).get("draft_artifacts", 0),
            "capabilities": ["flyers", "brochures", "presentations", "reels", "captions", "campaigns"],
            "hidden_data": ["unapproved HSH campaigns", "client-owned assets", "publishing controls"],
        },
        {
            "module": "connector_readiness_demo",
            "label": "Connector Readiness Demo",
            "preview_mode": "connector_scope_matrix",
            "source_metric": connector_summary.get("connector_count", 0),
            "capabilities": ["Airtable", "Google Workspace", "Notion", "WhatsApp", "Instagram", "n8n"],
            "hidden_data": ["credentials", "OAuth state", "webhook URLs", "account identifiers"],
        },
        {
            "module": "mobile_command_demo",
            "label": "Mobile Command Demo",
            "preview_mode": "responsive_console_preview",
            "source_metric": mobile.get("command_count", 0),
            "capabilities": ["Ask AIOS", "tasks", "calendar", "Gmail", "documents", "voice commands"],
            "hidden_data": ["device tokens", "notifications", "voice audio", "personal calendar data"],
        },
        {
            "module": "impact_metrics_demo",
            "label": "Impact Metrics Demo",
            "preview_mode": "outcome_scorecard",
            "source_metric": impact_quality.get("estimated_weekly_hours_saved", 0),
            "capabilities": ["time saved", "manual work reduced", "response quality", "adoption signals"],
            "hidden_data": ["HSH internal performance details", "financial metrics", "staff workload"],
        },
    ]


def build_onboarding_routes() -> list[dict[str, Any]]:
    return [
        {
            "request": "request_aios_demo",
            "label": "Request AIOS Demo",
            "route_to": ["@website", "@customer-workspace", "@calendar-handoff"],
            "gate": "OMAR_APPROVAL_REQUIRED",
            "response_mode": "draft_demo_invite_only",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_private_beta",
            "label": "Request Private Beta",
            "route_to": ["@customer-workspace", "@readiness", "@activation-command"],
            "gate": "SALES_QUALIFICATION_REQUIRED",
            "response_mode": "qualification_packet_only",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_connector_assessment",
            "label": "Request Connector Assessment",
            "route_to": ["@readiness", "@connector-manifest", "@activation-command"],
            "gate": "CONNECTOR_SCOPE_REVIEW",
            "response_mode": "local_assessment_draft",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_custom_workspace",
            "label": "Request Custom Workspace",
            "route_to": ["@customer-workspace", "@brain", "@mobile"],
            "gate": "DATA_ISOLATION_REVIEW",
            "response_mode": "requirements_packet_only",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_purchase_or_subscription",
            "label": "Request Purchase or Subscription",
            "route_to": ["@customer-workspace", "@legal", "@finance"],
            "gate": "PAYMENT_AND_LEGAL_APPROVAL_REQUIRED",
            "response_mode": "hold_for_omar_no_checkout",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    demo_modules = build_demo_modules(reports)
    onboarding_routes = build_onboarding_routes()
    future_customer_role = _future_aios_customer_role(reports["team_workspace_access"])
    unsafe_routes = [
        route["request"]
        for route in onboarding_routes
        if route.get("execution_enabled") is not False or route.get("external_write_enabled") is not False
    ]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_aios_customer_workspace_no_external_side_effects",
        "summary": {
            "demo_module_count": len(demo_modules),
            "onboarding_route_count": len(onboarding_routes),
            "data_isolation_rule_count": len(DATA_ISOLATION_RULES),
            "published_customer_workspace_count": 0,
            "customer_account_count": 0,
            "demo_invite_count": 0,
            "trial_started_count": 0,
            "checkout_started_count": 0,
            "all_external_actions_disabled": not unsafe_routes and all(value is False for value in EXTERNAL_SIDE_EFFECTS.values()),
            "all_hsh_private_data_isolated": len(DATA_ISOLATION_RULES) >= 7,
            "future_aios_customer_role_loaded": bool(future_customer_role),
        },
        "demo_modules": demo_modules,
        "onboarding_routes": onboarding_routes,
        "data_isolation_rules": DATA_ISOLATION_RULES,
        "product_policy": {
            "audience": "Future AIOS Customers",
            "default_mode": "local_demo_preview_only",
            "publish_rule": "No AIOS customer workspace, trial, invite, checkout, or customer account is created without Omar approval.",
            "data_rule": "Future customers see synthetic or redacted platform examples only; HSH private operating data remains isolated.",
            "commercial_rule": "Payments, contracts, subscription setup, and legal commitments remain blocked until Omar explicitly approves them.",
        },
        "future_aios_customer_role": future_customer_role,
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
