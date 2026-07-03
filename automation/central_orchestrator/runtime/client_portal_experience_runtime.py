#!/usr/bin/env python3
"""Build AIOS client portal experience contract.

This runtime creates a local-only future-client portal preview. It maps what a
client can see, what they can request, and which internal AIOS modules receive
the request. It does not publish a portal, create accounts, share files, send
messages, write CRM records, or call external services.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "CLIENT_PORTAL_EXPERIENCE_REPORT.json"

SOURCE_REPORTS = {
    "team_workspace_access": "TEAM_WORKSPACE_ACCESS_REPORT.json",
    "property_intelligence": "PROPERTY_INTELLIGENCE_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "daily_command_session": "DAILY_COMMAND_SESSION.json",
    "usage_adoption_ledger": "USAGE_ADOPTION_LEDGER.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "client_portal_published": False,
    "client_accounts_created": False,
    "invites_sent": False,
    "messages_sent": False,
    "calendar_events_created": False,
    "drive_files_shared": False,
    "crm_rows_written": False,
    "payments_made": False,
    "portal_submissions": False,
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
}

HIDDEN_DATA_RULES = [
    {
        "data_class": "internal_crm_notes",
        "rule": "Hide owner/team scoring notes, objections, private follow-up logic, and negotiation strategy.",
        "risk_if_exposed": "Client trust loss and negotiation leakage.",
    },
    {
        "data_class": "whatsapp_history",
        "rule": "Hide raw WhatsApp threads and conversation memory unless Omar explicitly shares a client-ready extract.",
        "risk_if_exposed": "Privacy breach and accidental disclosure of unrelated context.",
    },
    {
        "data_class": "other_clients",
        "rule": "Never expose another lead, buyer, seller, tenant, owner, phone number, or request.",
        "risk_if_exposed": "Confidentiality breach.",
    },
    {
        "data_class": "owner_finance",
        "rule": "Hide commissions, margin assumptions, cash-flow, bank, payment, and owner-only finance controls.",
        "risk_if_exposed": "Commercial and financial exposure.",
    },
    {
        "data_class": "legal_payment_context",
        "rule": "Show only status labels; keep legal analysis, payment decisions, and high-risk authority advice behind Omar approval.",
        "risk_if_exposed": "Unauthorized legal or financial reliance.",
    },
    {
        "data_class": "connector_credentials",
        "rule": "Never expose tokens, account status, OAuth state, webhook URLs, provider IDs, or configuration secrets.",
        "risk_if_exposed": "System compromise.",
    },
    {
        "data_class": "team_tasks",
        "rule": "Hide internal task owners, queues, blockers, staff notes, and workload status from clients.",
        "risk_if_exposed": "Operational leakage and client confusion.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _team_future_client_role(team_workspace: dict[str, Any]) -> dict[str, Any]:
    return next((role for role in team_workspace.get("role_views", []) if role.get("role") == "future_client"), {})


def build_portal_sections(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    property_report = reports["property_intelligence"]
    operations_report = reports["operations_assistant"]
    content_report = reports["content_factory"]
    crm_report = reports["crm_followup"]
    usage_summary = reports["usage_adoption_ledger"].get("summary", {})
    daily_summary = reports["daily_command_session"].get("summary", {})

    return [
        {
            "section": "property_recommendations",
            "label": "Property Recommendations",
            "client_visible": True,
            "display_mode": "curated_read_only_cards",
            "source_module": "@property-intel",
            "source_metric": property_report.get("matched_count", 0),
            "allowed_content": [
                "curated matches",
                "public property facts",
                "availability subject to confirmation",
                "client-ready comparison notes",
            ],
            "hidden_content": ["internal ranking notes", "other client demand", "owner negotiation context"],
            "actions": ["request_viewing", "ask_property_question"],
        },
        {
            "section": "document_status",
            "label": "Document Status",
            "client_visible": True,
            "display_mode": "status_timeline_only",
            "source_module": "@knowledge-vault",
            "source_metric": operations_report.get("case_count", 0),
            "allowed_content": [
                "document received/missing/under review status",
                "client upload request labels",
                "authority step names",
            ],
            "hidden_content": ["internal document comments", "legal analysis", "payment decisions"],
            "actions": ["request_documents"],
        },
        {
            "section": "appointment_request",
            "label": "Appointment Request",
            "client_visible": True,
            "display_mode": "request_only_no_live_booking",
            "source_module": "@calendar-handoff",
            "source_metric": daily_summary.get("stopped_for_human_count", 0),
            "allowed_content": ["preferred date", "preferred time window", "viewing or call type", "contact preference"],
            "hidden_content": ["Omar calendar internals", "team availability conflicts", "private client meetings"],
            "actions": ["request_viewing"],
        },
        {
            "section": "approved_content_preview",
            "label": "Approved Content Preview",
            "client_visible": True,
            "display_mode": "approved_assets_only",
            "source_module": "@content-factory",
            "source_metric": content_report.get("artifact_count", 0),
            "allowed_content": ["approved property copy", "approved brochure preview", "approved campaign visuals"],
            "hidden_content": ["draft variants", "compliance comments", "publish controls"],
            "actions": ["request_marketing_preview"],
        },
        {
            "section": "operations_status",
            "label": "Operations Status",
            "client_visible": True,
            "display_mode": "plain_language_progress",
            "source_module": "@operations",
            "source_metric": operations_report.get("case_count", 0),
            "allowed_content": ["case stage", "next client action", "missing document labels", "estimated next checkpoint"],
            "hidden_content": ["authority strategy", "internal escalation notes", "fee/payment decisions"],
            "actions": ["request_offer_support", "request_documents"],
        },
        {
            "section": "client_request_intake",
            "label": "Client Request Intake",
            "client_visible": True,
            "display_mode": "draft_intake_no_submission",
            "source_module": "@brain",
            "source_metric": crm_report.get("lead_count", 0),
            "allowed_content": ["question", "request category", "urgency", "preferred contact channel"],
            "hidden_content": ["lead score", "CRM routing notes", "team assignment logic"],
            "actions": ["ask_property_question", "request_offer_support"],
        },
        {
            "section": "client_success_snapshot",
            "label": "Client Success Snapshot",
            "client_visible": True,
            "display_mode": "summary_metrics_without_internal_detail",
            "source_module": "@usage-ledger",
            "source_metric": usage_summary.get("adoption_score", 0),
            "allowed_content": ["service readiness", "request status", "safe next step"],
            "hidden_content": ["usage ledger internals", "automation diagnostics", "validation traces"],
            "actions": ["ask_property_question"],
        },
    ]


def build_request_routes() -> list[dict[str, Any]]:
    return [
        {
            "request": "request_viewing",
            "label": "Request Viewing",
            "route_to": ["@property-intel", "@calendar-handoff"],
            "gate": "OMAR_APPROVAL_REQUIRED",
            "client_response_mode": "acknowledge_request_no_live_booking",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_documents",
            "label": "Request Documents",
            "route_to": ["@knowledge-vault", "@operations"],
            "gate": "INTERNAL_REVIEW_REQUIRED",
            "client_response_mode": "show_status_not_files_until_approved",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "ask_property_question",
            "label": "Ask Property Question",
            "route_to": ["@brain", "@property-intel"],
            "gate": "DRAFT_ONLY",
            "client_response_mode": "draft_answer_for_review",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_offer_support",
            "label": "Request Offer Support",
            "route_to": ["@operations", "@crm-followup"],
            "gate": "HIGH_RISK_DECISION",
            "client_response_mode": "hold_for_omar_on_price_legal_payment_terms",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
        {
            "request": "request_marketing_preview",
            "label": "Request Marketing Preview",
            "route_to": ["@content-factory"],
            "gate": "APPROVED_CONTENT_ONLY",
            "client_response_mode": "approved_preview_only",
            "execution_enabled": False,
            "external_write_enabled": False,
        },
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    portal_sections = build_portal_sections(reports)
    request_routes = build_request_routes()
    future_client_role = _team_future_client_role(reports["team_workspace_access"])
    hidden_data_classes = [rule["data_class"] for rule in HIDDEN_DATA_RULES]
    unsafe_sections = [section["section"] for section in portal_sections if section.get("client_visible") is not True]
    unsafe_routes = [
        route["request"]
        for route in request_routes
        if route.get("execution_enabled") is not False or route.get("external_write_enabled") is not False
    ]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_client_portal_preview_no_external_side_effects",
        "summary": {
            "portal_section_count": len(portal_sections),
            "request_route_count": len(request_routes),
            "hidden_data_rule_count": len(HIDDEN_DATA_RULES),
            "published_portal_count": 0,
            "external_share_enabled_count": 0,
            "client_account_count": 0,
            "all_external_actions_disabled": not unsafe_routes and all(value is False for value in EXTERNAL_SIDE_EFFECTS.values()),
            "all_sensitive_data_hidden": len(hidden_data_classes) >= 7 and not unsafe_sections,
            "future_client_role_loaded": bool(future_client_role),
        },
        "portal_sections": portal_sections,
        "request_routes": request_routes,
        "hidden_data_rules": HIDDEN_DATA_RULES,
        "access_policy": {
            "audience": "Future Clients",
            "default_mode": "local_preview_only",
            "publish_rule": "No client portal is published, invited, or shared without Omar approval and login/permission setup.",
            "request_rule": "Client requests are captured as draft local contracts only; every live message, booking, file share, CRM write, payment, or legal/offer response stays gated.",
            "sensitive_data_rule": "Internal CRM notes, WhatsApp history, other clients, finance, legal/payment context, connector credentials, and team tasks are always hidden.",
        },
        "future_client_role": future_client_role,
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
