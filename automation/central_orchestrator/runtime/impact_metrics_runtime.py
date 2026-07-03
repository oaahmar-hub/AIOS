#!/usr/bin/env python3
"""Build AIOS impact metrics.

This runtime measures whether AIOS is moving toward the operating-system goal:
time saved, manual work reduced, response quality improved, follow-up quality
improved, and primary-platform readiness. It reads local reports only and never
executes external actions.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "IMPACT_METRICS_REPORT.json"

SOURCE_REPORTS = {
    "command_center": "COMMAND_CENTER_DATA.json",
    "ceo_operating": "CEO_OPERATING_REPORT.json",
    "property_intelligence": "PROPERTY_INTELLIGENCE_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "knowledge_vault": "KNOWLEDGE_VAULT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "mobile_command": "MOBILE_COMMAND_REPORT.json",
    "approval_state": "APPROVAL_STATE.json",
    "action_queue": "ACTION_QUEUE.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "messages_sent": False,
    "whatsapp_messages_sent": False,
    "gmail_drafts_created": False,
    "gmail_messages_sent": False,
    "calendar_events_created": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "notion_pages_created": False,
    "content_published": False,
    "instagram_posts_published": False,
    "external_analytics_called": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_time_savings(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    property_matches = len(reports["property_intelligence"].get("top_matches", []))
    operations_cases = int(reports["operations_assistant"].get("case_count") or 0)
    knowledge_queries = len(reports["knowledge_vault"].get("retrieval_results", []))
    content_drafts = int(reports["content_factory"].get("artifact_count") or 0)
    mobile_commands = int(reports["mobile_command"].get("command_count") or 0)
    ceo_priorities = len(reports["ceo_operating"].get("priority_stack", []))
    followup_tasks = int(reports["crm_followup"].get("dashboard", {}).get("open_tasks") or 0)
    action_packets = len(reports["action_queue"].get("actions", []))
    rows = [
        {
            "area": "Property Intelligence",
            "unit_count": property_matches,
            "manual_minutes_per_unit": 12,
            "saved_minutes": property_matches * 12,
            "evidence": "ranked property matches and comparisons generated locally",
        },
        {
            "area": "Operations Assistant",
            "unit_count": operations_cases,
            "manual_minutes_per_unit": 20,
            "saved_minutes": operations_cases * 20,
            "evidence": "DLD/RERA/NOC/Ejari/mortgage/off-plan/visa checklists prepared",
        },
        {
            "area": "Knowledge Vault",
            "unit_count": knowledge_queries,
            "manual_minutes_per_unit": 10,
            "saved_minutes": knowledge_queries * 10,
            "evidence": "retrieval routes avoid manual SOP/document lookup",
        },
        {
            "area": "CRM Follow-Up",
            "unit_count": followup_tasks,
            "manual_minutes_per_unit": 8,
            "saved_minutes": followup_tasks * 8,
            "evidence": "lead scores, stale-risk flags, tasks, and draft messages generated",
        },
        {
            "area": "Content Factory",
            "unit_count": content_drafts,
            "manual_minutes_per_unit": 18,
            "saved_minutes": content_drafts * 18,
            "evidence": "draft flyers, brochures, presentation, scripts, captions, campaign plan",
        },
        {
            "area": "Mobile Command",
            "unit_count": mobile_commands,
            "manual_minutes_per_unit": 6,
            "saved_minutes": mobile_commands * 6,
            "evidence": "phone commands routed into staged actions and notifications",
        },
        {
            "area": "CEO Operating Plan",
            "unit_count": ceo_priorities,
            "manual_minutes_per_unit": 5,
            "saved_minutes": ceo_priorities * 5,
            "evidence": "daily priorities, time blocks, and risk controls assembled",
        },
        {
            "area": "Action Queue",
            "unit_count": action_packets,
            "manual_minutes_per_unit": 4,
            "saved_minutes": action_packets * 4,
            "evidence": "approval-safe local packets staged for review",
        },
    ]
    return rows


def build_quality_metrics(reports: dict[str, dict[str, Any]], time_savings: list[dict[str, Any]]) -> dict[str, Any]:
    crm = reports["crm_followup"]
    content = reports["content_factory"]
    command_center = reports["command_center"]
    approval_state = reports["approval_state"]
    total_saved = sum(row["saved_minutes"] for row in time_savings)
    content_checks = content.get("compliance_checks", [])
    passed_content_checks = len([check for check in content_checks if check.get("passed") is True])
    return {
        "estimated_weekly_minutes_saved": total_saved,
        "estimated_weekly_hours_saved": round(total_saved / 60, 2),
        "manual_work_reduction_units": sum(row["unit_count"] for row in time_savings),
        "response_quality_signals": {
            "local_search_records": len(command_center.get("search_index", [])),
            "workflow_contracts": len(command_center.get("workflows", [])),
            "knowledge_assets": reports["knowledge_vault"].get("asset_count", 0),
            "operations_cases": reports["operations_assistant"].get("case_count", 0),
        },
        "follow_up_quality_signals": {
            "lead_count": crm.get("lead_count", 0),
            "hot_leads": crm.get("dashboard", {}).get("hot_leads", 0),
            "open_tasks": crm.get("dashboard", {}).get("open_tasks", 0),
            "stale_risk_count": crm.get("dashboard", {}).get("stale_risk_count", 0),
            "draft_messages": len(crm.get("draft_messages", [])),
        },
        "content_quality_signals": {
            "draft_artifacts": content.get("artifact_count", 0),
            "compliance_checks": len(content_checks),
            "passed_compliance_checks": passed_content_checks,
            "draft_only": all(item.get("approval_required") for item in content.get("draft_artifacts", [])),
        },
        "platform_adoption_signals": {
            "health_keys": len(command_center.get("health", {})),
            "activity_records": len(command_center.get("activity", [])),
            "pending_approval_packets": approval_state.get("pending_count", 0),
            "mobile_commands": reports["mobile_command"].get("command_count", 0),
            "ceo_operating_priorities": len(reports["ceo_operating"].get("priority_stack", [])),
        },
    }


def build_goals_status(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    hours = float(metrics.get("estimated_weekly_hours_saved") or 0)
    follow = metrics["follow_up_quality_signals"]
    platform = metrics["platform_adoption_signals"]
    response = metrics["response_quality_signals"]
    content = metrics["content_quality_signals"]
    return [
        {
            "goal": "save_significant_time_every_week",
            "status": "measuring_ready" if hours >= 8 else "needs_more_live_usage",
            "evidence": f"{hours} estimated weekly hours saved from local operating outputs",
        },
        {
            "goal": "reduce_manual_work",
            "status": "measuring_ready" if metrics.get("manual_work_reduction_units", 0) >= 50 else "building",
            "evidence": f"{metrics.get('manual_work_reduction_units', 0)} manual-work units converted into AIOS outputs",
        },
        {
            "goal": "improve_response_quality",
            "status": "measuring_ready" if response.get("local_search_records", 0) >= 100 and response.get("workflow_contracts", 0) >= 10 else "building",
            "evidence": f"{response.get('local_search_records', 0)} searchable records and {response.get('workflow_contracts', 0)} workflow contracts",
        },
        {
            "goal": "improve_follow_up_quality",
            "status": "measuring_ready" if follow.get("open_tasks", 0) and follow.get("draft_messages", 0) else "building",
            "evidence": f"{follow.get('open_tasks', 0)} tasks, {follow.get('draft_messages', 0)} drafts, {follow.get('stale_risk_count', 0)} stale-risk flags",
        },
        {
            "goal": "become_primary_operating_platform",
            "status": "measuring_ready" if platform.get("health_keys", 0) >= 30 and platform.get("ceo_operating_priorities", 0) >= 6 else "building",
            "evidence": f"{platform.get('health_keys', 0)} health keys, {platform.get('ceo_operating_priorities', 0)} CEO priorities, {platform.get('mobile_commands', 0)} mobile commands",
        },
        {
            "goal": "keep_approval_safety",
            "status": "controlled",
            "evidence": f"{content.get('passed_compliance_checks', 0)} content checks passed; external execution remains disabled",
        },
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    savings = build_time_savings(reports)
    metrics = build_quality_metrics(reports, savings)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_impact_metrics_no_external_side_effects",
        "period": payload.get("period", "weekly_projection_from_current_local_outputs"),
        "time_savings": savings,
        "quality_metrics": metrics,
        "success_metric_status": build_goals_status(metrics),
        "recommended_next_measurements": [
            "Replace estimates with real before/after timestamps once live HSH daily usage begins.",
            "Track actual approved replies, viewings booked, content published after approval, and closed-loop lead outcomes.",
            "Record weekly manual tasks avoided, stale leads resolved, and approval queue clearance time.",
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
