#!/usr/bin/env python3
"""Build AIOS team workspace and access map.

This local runtime defines how Omar, HSH team members, future clients, and
future AIOS customers should see AIOS. It produces role views, allowed modules,
blocked actions, command surfaces, and approval gates without creating users,
changing permissions, sending invites, or provisioning external accounts.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "TEAM_WORKSPACE_ACCESS_REPORT.json"

SOURCE_REPORTS = {
    "daily_command_session": "DAILY_COMMAND_SESSION.json",
    "usage_adoption_ledger": "USAGE_ADOPTION_LEDGER.json",
    "connector_readiness": "CONNECTOR_READINESS_REPORT.json",
    "command_center_data": "COMMAND_CENTER_DATA.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "users_created": False,
    "invites_sent": False,
    "permissions_changed": False,
    "oauth_started": False,
    "credentials_read": False,
    "network_calls_made": False,
    "client_portal_published": False,
    "team_workspace_published": False,
    "analytics_events_sent": False,
}

ROLE_DEFINITIONS = [
    {
        "role": "omar_owner",
        "label": "Omar Owner Command",
        "audience": "Omar",
        "view": "full_command_center",
        "modules": [
            "one_brain",
            "ceo_dashboard",
            "daily_command_session",
            "usage_ledger",
            "crm_followup",
            "operations",
            "property_intelligence",
            "content_factory",
            "connectors",
            "mobile_command",
        ],
        "allowed_commands": ["@brain", "@ceo", "@daily-command", "@autopilot", "@usage-ledger", "@decision-local"],
        "blocked_actions": ["external_send_without_approval", "payment_without_approval", "connector_activation_without_final_approval"],
    },
    {
        "role": "hsh_team_operator",
        "label": "HSH Team Operator",
        "audience": "HSH Team",
        "view": "operations_and_crm_workspace",
        "modules": [
            "daily_command_session",
            "crm_followup",
            "operations",
            "knowledge_vault",
            "property_intelligence",
            "content_factory",
        ],
        "allowed_commands": ["@crm-followup", "@operations", "@knowledge-vault", "@property-intel", "@content-factory"],
        "blocked_actions": ["view_owner_only_finance", "approve_high_risk_decision", "activate_connector"],
    },
    {
        "role": "future_client",
        "label": "Future Client Portal",
        "audience": "Future Clients",
        "view": "client_read_only_workspace",
        "modules": ["property_intelligence", "document_status", "approved_content_preview", "appointment_handoff"],
        "allowed_commands": ["@property-intel", "@documents", "@calendar-handoff"],
        "blocked_actions": ["see_internal_notes", "see_team_tasks", "trigger_live_send", "see_other_clients"],
    },
    {
        "role": "future_aios_customer",
        "label": "Future AIOS Customer Workspace",
        "audience": "Future AIOS Customers",
        "view": "product_demo_workspace",
        "modules": ["website", "mobile_app", "command_center_preview", "usage_ledger_preview", "connector_readiness_preview"],
        "allowed_commands": ["@website", "@mobile", "@readiness"],
        "blocked_actions": ["access_hsh_private_data", "activate_hsh_connectors", "see_whatsapp_conversations"],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_role_views(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    usage_summary = reports["usage_adoption_ledger"].get("summary", {})
    connector_summary = reports["connector_readiness"].get("summary", {})
    session_summary = reports["daily_command_session"].get("summary", {})
    workflow_count = len(reports["command_center_data"].get("workflows", []))
    views = []
    for role in ROLE_DEFINITIONS:
        views.append(
            {
                **role,
                "module_count": len(role["modules"]),
                "command_count": len(role["allowed_commands"]),
                "access_status": "local_view_ready_not_published",
                "requires_login": role["role"] != "omar_owner",
                "requires_omar_approval": True,
                "live_access_enabled": False,
                "external_invite_enabled": False,
                "source_metrics": {
                    "session_entries": usage_summary.get("session_entry_count", 0),
                    "daily_session_items": session_summary.get("session_item_count", 0),
                    "connector_count": connector_summary.get("connector_count", 0),
                    "workflow_count": workflow_count,
                },
            }
        )
    return views


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    role_views = build_role_views(reports)
    unique_modules = sorted({module for role in role_views for module in role["modules"]})
    blocked_actions = sorted({action for role in role_views for action in role["blocked_actions"]})
    result = {
        "generated_at": _now(),
        "mode": "safe_local_team_workspace_access_no_external_side_effects",
        "summary": {
            "role_count": len(role_views),
            "workspace_view_count": len(role_views),
            "unique_module_count": len(unique_modules),
            "blocked_action_count": len(blocked_actions),
            "published_workspace_count": 0,
            "live_access_enabled_count": 0,
            "external_invites_sent_count": 0,
            "all_live_access_disabled": all(view["live_access_enabled"] is False for view in role_views),
            "all_invites_disabled": all(view["external_invite_enabled"] is False for view in role_views),
        },
        "role_views": role_views,
        "unique_modules": unique_modules,
        "blocked_actions": blocked_actions,
        "access_policy": {
            "owner_of_record": "Omar",
            "default_mode": "local_preview_only",
            "publish_rule": "No team workspace, client portal, or customer workspace is published without Omar approval and connector/login setup.",
            "sensitive_data_rule": "Client data, WhatsApp history, legal/payment context, and owner-only financial controls stay hidden from non-owner roles.",
        },
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
