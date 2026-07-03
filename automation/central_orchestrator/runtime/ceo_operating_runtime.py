#!/usr/bin/env python3
"""Build the AIOS CEO operating report.

This runtime turns the local AIOS reports into a daily operating plan: ranked
priorities, time blocks, approval bottlenecks, follow-up quality checks, and
next actions. It is local-only and does not send messages, write CRM rows,
create calendar events, modify Drive, or publish content.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "CEO_OPERATING_REPORT.json"

SOURCE_REPORTS = {
    "command_center": "COMMAND_CENTER_DATA.json",
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
    "calendar_events_updated": False,
    "drive_files_created": False,
    "drive_files_modified": False,
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "notion_pages_created": False,
    "content_published": False,
    "instagram_posts_published": False,
    "tasks_created_externally": False,
    "notifications_pushed_to_device": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    path = REPORTS_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _priority(priority: str) -> int:
    return {"P1": 1, "Hot": 1, "P2": 2, "Warm": 2, "P3": 3, "Normal": 3}.get(priority, 4)


def build_priority_stack(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    crm = reports["crm_followup"]
    for lead in crm.get("scored_leads", [])[:5]:
        rows.append(
            {
                "priority": "P1" if lead.get("priority") == "Hot" else "P2",
                "domain": "CRM Follow-Up",
                "title": f"{lead.get('priority', 'Lead')} lead: {lead.get('name', 'Unknown')}",
                "reason": ", ".join(lead.get("reasons", [])[:2]) or "lead follow-up due",
                "next_action": "Review draft message, confirm KYC/missing fields, then approve follow-up.",
                "handoff": "@crm-followup",
                "approval_required": True,
            }
        )
    operations = reports["operations_assistant"]
    fee = operations.get("fee_calculator", {})
    if operations.get("case_count"):
        rows.append(
            {
                "priority": "P1",
                "domain": "Operations",
                "title": f"DLD/NOC operating checklist ready: {operations.get('case_count')} cases",
                "reason": f"Cash-to-close model AED {float(fee.get('total_estimated_cash_to_close', 0)):,.0f}",
                "next_action": "Use the relevant checklist before any portal submission, payment, or legal step.",
                "handoff": "@operations",
                "approval_required": True,
            }
        )
    property_report = reports["property_intelligence"]
    if property_report.get("top_matches"):
        top = property_report["top_matches"][0]
        rows.append(
            {
                "priority": "P2",
                "domain": "Property Intelligence",
                "title": f"Property recommendation ready: {top.get('title', 'top match')}",
                "reason": f"Score {top.get('score', 0)} with {property_report.get('matched_count', 0)} matched options",
                "next_action": "Verify live availability and facts before sending shortlist.",
                "handoff": "@property-intel",
                "approval_required": True,
            }
        )
    content = reports["content_factory"]
    if content.get("artifact_count"):
        rows.append(
            {
                "priority": "P2",
                "domain": "Content Factory",
                "title": f"{content.get('artifact_count', 0)} content drafts ready",
                "reason": "flyer, brochure, presentation, reel, video, caption, and campaign plan staged",
                "next_action": "Verify RERA permit, availability, and media rights before publishing.",
                "handoff": "@content-factory",
                "approval_required": True,
            }
        )
    mobile = reports["mobile_command"]
    for action in mobile.get("actions", [])[:3]:
        rows.append(
            {
                "priority": action.get("priority", "P3"),
                "domain": "Mobile Command",
                "title": action.get("raw_text", "Mobile command"),
                "reason": f"Routed to {action.get('handoff_command')} as {action.get('intent')}",
                "next_action": action.get("suggested_reply", "Review staged mobile action."),
                "handoff": action.get("handoff_command", "@mobile-command"),
                "approval_required": action.get("approval_required", True),
            }
        )
    approvals = reports["approval_state"]
    pending = int(approvals.get("pending_count") or 0)
    if pending:
        rows.append(
            {
                "priority": "P1",
                "domain": "Approval Gate",
                "title": f"{pending} packets pending Omar review",
                "reason": "external execution remains blocked until approval",
                "next_action": "Clear high-value or time-sensitive packets first; leave risky items on hold.",
                "handoff": "@approve-local",
                "approval_required": True,
            }
        )
    rows.sort(key=lambda row: (_priority(str(row.get("priority"))), row.get("domain", ""), row.get("title", "")))
    return rows[:12]


def build_time_blocks(priorities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "block": "Morning Command Review",
            "time": "08:00-09:00",
            "focus": "Health, approvals, hot leads, and urgent operations",
            "items": [row["title"] for row in priorities if row["priority"] == "P1"][:4],
        },
        {
            "block": "Revenue and Client Execution",
            "time": "11:00-13:00",
            "focus": "Property shortlists, lead follow-up, viewings, and owner/client replies",
            "items": [row["title"] for row in priorities if row["domain"] in {"CRM Follow-Up", "Property Intelligence", "Mobile Command"}][:4],
        },
        {
            "block": "Operations and Knowledge",
            "time": "14:00-15:30",
            "focus": "DLD, RERA, NOC, document retrieval, and compliance checks",
            "items": [row["title"] for row in priorities if row["domain"] in {"Operations", "Approval Gate"}][:4],
        },
        {
            "block": "Content and Review",
            "time": "16:00-17:00",
            "focus": "Content drafts, campaign checks, and tomorrow's queued work",
            "items": [row["title"] for row in priorities if row["domain"] == "Content Factory"][:4],
        },
    ]


def build_scorecard(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    command_center = reports["command_center"]
    crm = reports["crm_followup"]
    approvals = reports["approval_state"]
    mobile = reports["mobile_command"]
    return {
        "brain_health_keys": len(command_center.get("health", {})),
        "search_records": len(command_center.get("search_index", [])),
        "workflow_records": len(command_center.get("workflows", [])),
        "pending_approvals": approvals.get("pending_count", 0),
        "hot_leads": crm.get("dashboard", {}).get("hot_leads", 0),
        "open_follow_up_tasks": crm.get("dashboard", {}).get("open_tasks", 0),
        "stale_risk_count": crm.get("dashboard", {}).get("stale_risk_count", 0),
        "mobile_commands": mobile.get("command_count", 0),
        "content_drafts": reports["content_factory"].get("artifact_count", 0),
        "operations_cases": reports["operations_assistant"].get("case_count", 0),
        "knowledge_assets": reports["knowledge_vault"].get("asset_count", 0),
    }


def build_risks(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    risks = []
    approvals = reports["approval_state"]
    if approvals.get("pending_count", 0):
        risks.append(
            {
                "risk": "approval_queue_bottleneck",
                "severity": "high",
                "detail": f"{approvals.get('pending_count')} packets pending Omar review",
                "control": "external execution disabled until explicit approval",
            }
        )
    crm = reports["crm_followup"]
    stale = crm.get("dashboard", {}).get("stale_risk_count", 0)
    if stale:
        risks.append(
            {
                "risk": "follow_up_quality",
                "severity": "high",
                "detail": f"{stale} lead(s) flagged as stale-risk",
                "control": "prioritize hot/warm lead follow-up before content work",
            }
        )
    content = reports["content_factory"]
    failed = [check.get("check") for check in content.get("compliance_checks", []) if check.get("passed") is not True]
    risks.append(
        {
            "risk": "content_compliance",
            "severity": "controlled" if not failed else "high",
            "detail": "all content remains draft-only" if not failed else ", ".join(failed),
            "control": "RERA permit, availability, and media rights must be verified before publish",
        }
    )
    risks.append(
        {
            "risk": "connector_execution",
            "severity": "controlled",
            "detail": "live connector writes and sends remain disabled",
            "control": "approval checklist and final-run packet required before activation",
        }
    )
    return risks


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    priorities = build_priority_stack(reports)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_ceo_operating_runtime_no_external_side_effects",
        "operator": payload.get("operator", "Omar"),
        "operating_day": payload.get("operating_day", "today"),
        "scorecard": build_scorecard(reports),
        "priority_stack": priorities,
        "time_blocks": build_time_blocks(priorities),
        "risk_controls": build_risks(reports),
        "decision_rules": [
            "P1 client, approval, and compliance work beats content work.",
            "No owner/client-specific message, public content, portal action, payment, or legal step executes without approval.",
            "A lead with stale risk must receive reviewed follow-up before new nurture campaigns are launched.",
            "Property recommendations must verify live availability, price, and permit status before being sent.",
        ],
        "workflow_handoffs": [
            {"command": "@approve-local", "scope": "approval queue review"},
            {"command": "@crm-followup", "scope": "lead quality and follow-up"},
            {"command": "@property-intel", "scope": "shortlists and recommendations"},
            {"command": "@operations", "scope": "DLD/RERA/NOC checklists"},
            {"command": "@content-factory", "scope": "draft content review"},
            {"command": "@mobile-command", "scope": "phone-side staged actions"},
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
