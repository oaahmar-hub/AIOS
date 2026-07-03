#!/usr/bin/env python3
"""Build the AIOS weekly operating review.

This local runtime converts AIOS usage, impact, CEO priorities, CRM follow-up,
operations, content, connector readiness, and sync-queue signals into a weekly
management cadence for HSH. It does not send reports, create tasks, schedule
meetings, write CRM rows, publish content, or call external services.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "WEEKLY_OPERATING_REVIEW_REPORT.json"

SOURCE_REPORTS = {
    "usage_adoption_ledger": "USAGE_ADOPTION_LEDGER.json",
    "impact_metrics": "IMPACT_METRICS_REPORT.json",
    "ceo_operating": "CEO_OPERATING_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "connector_readiness": "CONNECTOR_READINESS_REPORT.json",
    "business_sync_queue": "BUSINESS_SYNC_QUEUE_REPORT.json",
    "daily_command_session": "DAILY_COMMAND_SESSION.json",
    "command_center_data": "COMMAND_CENTER_DATA.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "weekly_report_sent": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "crm_rows_written": False,
    "tasks_created_externally": False,
    "notion_pages_created": False,
    "drive_files_created": False,
    "analytics_events_sent": False,
    "content_published": False,
    "messages_sent": False,
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_scorecard(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    usage = reports["usage_adoption_ledger"].get("summary", {})
    impact = reports["impact_metrics"].get("quality_metrics", {})
    crm = reports["crm_followup"].get("dashboard", {})
    connector = reports["connector_readiness"].get("summary", {})
    sync = reports["business_sync_queue"].get("summary", {})
    command = reports["command_center_data"]
    return {
        "adoption_score": usage.get("adoption_score", 0),
        "weekly_hours_saved_projection": usage.get("weekly_hours_saved_projection", impact.get("estimated_weekly_hours_saved", 0)),
        "manual_work_reduction_units": impact.get("manual_work_reduction_units", 0),
        "search_records": len(command.get("search_index", [])),
        "workflow_records": len(command.get("workflows", [])),
        "health_keys": len(command.get("health", {})),
        "hot_leads": crm.get("hot_leads", 0),
        "open_follow_up_tasks": crm.get("open_tasks", 0),
        "stale_risk_count": crm.get("stale_risk_count", 0),
        "connector_count": connector.get("connector_count", 0),
        "connector_activation_allowed": connector.get("activation_allowed_count", 0),
        "sync_packets": sync.get("sync_packet_count", 0),
        "sync_ready": sync.get("ready_for_live_sync_count", 0),
        "sync_blocked": sync.get("blocked_packet_count", 0),
    }


def build_review_sections(reports: dict[str, dict[str, Any]], scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    impact = reports["impact_metrics"].get("quality_metrics", {})
    daily = reports["daily_command_session"].get("summary", {})
    crm = reports["crm_followup"]
    operations = reports["operations_assistant"]
    content = reports["content_factory"]
    connector = reports["connector_readiness"].get("summary", {})
    sync = reports["business_sync_queue"].get("summary", {})
    ceo = reports["ceo_operating"]
    return [
        {
            "section": "executive_scorecard",
            "label": "Executive Scorecard",
            "status": "ready_for_omar_review",
            "evidence": [
                f"{scorecard['weekly_hours_saved_projection']} projected hours saved/week",
                f"{scorecard['manual_work_reduction_units']} manual-work units reduced",
                f"{scorecard['search_records']} searchable records",
                f"{scorecard['workflow_records']} workflow records",
            ],
            "next_action": "Review whether AIOS is replacing manual operating routines this week.",
            "automation_mode": "local_review_only",
        },
        {
            "section": "crm_followup_quality",
            "label": "Client Pipeline Quality",
            "status": "needs_omar_review" if scorecard["stale_risk_count"] else "controlled",
            "evidence": [
                f"{crm.get('lead_count', 0)} leads tracked",
                f"{scorecard['hot_leads']} hot leads",
                f"{scorecard['open_follow_up_tasks']} open follow-ups",
                f"{scorecard['stale_risk_count']} stale-risk items",
            ],
            "next_action": "Clear stale follow-up risks before adding new automation.",
            "automation_mode": "draft_tasks_only",
        },
        {
            "section": "operations_pipeline",
            "label": "Operations Pipeline",
            "status": "ready_for_case_review",
            "evidence": [
                f"{operations.get('case_count', 0)} operations cases",
                "DLD/RERA/NOC/Ejari/mortgage/off-plan/visa coverage",
                f"AED {operations.get('fee_calculator', {}).get('total_estimated_cash_to_close', 0)} validation cash-to-close model",
            ],
            "next_action": "Pick the highest-risk authority case and run strict pre-submission review.",
            "automation_mode": "checklist_only",
        },
        {
            "section": "content_output",
            "label": "Content Factory Output",
            "status": "draft_ready_no_publish",
            "evidence": [
                f"{content.get('artifact_count', 0)} draft artifacts",
                f"{len(content.get('compliance_checks', []))} compliance checks",
                f"{impact.get('content_quality_signals', {}).get('passed_compliance_checks', 0)} passed content checks",
            ],
            "next_action": "Select one approved campaign candidate for Omar review; keep publishing disabled.",
            "automation_mode": "draft_only",
        },
        {
            "section": "connector_activation",
            "label": "Connector Activation",
            "status": "blocked_until_credentials_and_approval",
            "evidence": [
                f"{connector.get('connector_count', 0)} connectors tracked",
                f"{connector.get('local_ready_count', 0)} local-ready connectors",
                f"{connector.get('activation_allowed_count', 0)} activation-allowed connectors",
            ],
            "next_action": "Prioritize one connector for credential/OAuth approval when Omar is ready.",
            "automation_mode": "no_oauth_no_network",
        },
        {
            "section": "sync_readiness",
            "label": "Business Sync Readiness",
            "status": "all_packets_blocked",
            "evidence": [
                f"{sync.get('sync_packet_count', 0)} sync packets",
                f"{sync.get('blocked_packet_count', 0)} blocked packets",
                f"{sync.get('ready_for_live_sync_count', 0)} live-ready packets",
            ],
            "next_action": "Keep sync packets blocked until mapping, credentials, and final approval are complete.",
            "automation_mode": "local_rehearsal_only",
        },
        {
            "section": "daily_operating_cadence",
            "label": "Daily Operating Cadence",
            "status": "cadence_defined",
            "evidence": [
                f"{daily.get('session_block_count', 0)} daily session blocks",
                f"{daily.get('session_item_count', 0)} session items",
                f"{daily.get('auto_local_count', 0)} auto-local items",
                f"{daily.get('stopped_for_human_count', 0)} human-stop items",
            ],
            "next_action": "Use Morning Command, Midday Execution, and End-of-Day Closeout as the default work rhythm.",
            "automation_mode": "local_operating_loop",
        },
        {
            "section": "ceo_decisions",
            "label": "CEO Decisions",
            "status": "decision_queue_ready",
            "evidence": [
                f"{len(ceo.get('priority_stack', []))} CEO priorities",
                f"{len(ceo.get('risk_controls', []))} risk controls",
                f"{ceo.get('scorecard', {}).get('pending_approvals', 0)} pending approvals",
            ],
            "next_action": "Choose the top three decisions for the next week and keep the rest in local hold.",
            "automation_mode": "decision_packet_only",
        },
    ]


def build_decision_queue(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    connector_names = reports["connector_readiness"].get("summary", {}).get("connector_count", 0)
    return [
        {
            "decision": "approve_next_connector_focus",
            "label": "Choose next connector focus",
            "gate": "LOGIN_OR_OAUTH_APPROVAL_REQUIRED",
            "recommended_owner": "Omar",
            "detail": f"{connector_names} connectors tracked; activation remains disabled.",
            "execution_enabled": False,
        },
        {
            "decision": "clear_stale_followups",
            "label": "Clear stale follow-up risk",
            "gate": "OMAR_REVIEW_REQUIRED",
            "recommended_owner": "Omar",
            "detail": "Review hot/stale leads before increasing automation volume.",
            "execution_enabled": False,
        },
        {
            "decision": "select_content_candidate",
            "label": "Select one content candidate",
            "gate": "PUBLISH_APPROVAL_REQUIRED",
            "recommended_owner": "Omar",
            "detail": "Move one draft campaign into approval review; no publishing enabled.",
            "execution_enabled": False,
        },
        {
            "decision": "validate_authority_case",
            "label": "Validate highest-risk authority case",
            "gate": "HIGH_RISK_DECISION",
            "recommended_owner": "Omar",
            "detail": "Run strict pre-submission review before any DLD/RERA/NOC action.",
            "execution_enabled": False,
        },
    ]


def build_next_week_priorities(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "priority": "P1",
            "title": "Run AIOS as the daily operating platform",
            "source_section": "daily_operating_cadence",
            "success_check": "Morning, midday, and closeout sessions used on working days.",
        },
        {
            "priority": "P2",
            "title": "Reduce follow-up risk",
            "source_section": "crm_followup_quality",
            "success_check": "No qualified lead remains stale without a reviewed next action.",
        },
        {
            "priority": "P3",
            "title": "Prepare one connector for approval",
            "source_section": "connector_activation",
            "success_check": "One connector has confirmed scope, required credentials, and approval packet.",
        },
        {
            "priority": "P4",
            "title": "Promote one content draft to review",
            "source_section": "content_output",
            "success_check": "One campaign candidate is selected, checked, and still unpublished.",
        },
        {
            "priority": "P5",
            "title": "Validate canonical sync mappings",
            "source_section": "sync_readiness",
            "success_check": "Business sync queue remains blocked but packet mapping is reviewed.",
        },
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    scorecard = build_scorecard(reports)
    review_sections = build_review_sections(reports, scorecard)
    decisions = build_decision_queue(reports)
    priorities = build_next_week_priorities(review_sections)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_weekly_operating_review_no_external_side_effects",
        "summary": {
            "review_section_count": len(review_sections),
            "decision_count": len(decisions),
            "next_week_priority_count": len(priorities),
            "weekly_hours_saved_projection": scorecard.get("weekly_hours_saved_projection", 0),
            "manual_work_reduction_units": scorecard.get("manual_work_reduction_units", 0),
            "adoption_score": scorecard.get("adoption_score", 0),
            "connector_activation_allowed": scorecard.get("connector_activation_allowed", 0),
            "sync_ready_count": scorecard.get("sync_ready", 0),
            "all_decisions_execution_disabled": all(item["execution_enabled"] is False for item in decisions),
            "all_external_actions_disabled": all(value is False for value in EXTERNAL_SIDE_EFFECTS.values()),
        },
        "scorecard": scorecard,
        "review_sections": review_sections,
        "decision_queue": decisions,
        "next_week_priorities": priorities,
        "review_policy": {
            "cadence": "weekly_hsh_operating_review",
            "default_mode": "local_review_only",
            "send_rule": "No weekly report is emailed, posted, scheduled, or written externally without Omar approval.",
            "success_rule": "Use this review to prove AIOS saves time, reduces manual work, improves response/follow-up quality, and becomes the primary HSH platform.",
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
