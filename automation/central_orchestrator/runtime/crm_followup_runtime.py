#!/usr/bin/env python3
"""Build a local CRM and follow-up intelligence report for AIOS.

The runtime scores leads, stages follow-up tasks, and prepares draft-only
communication guidance from local AIOS CRM rules. It does not write Airtable,
send WhatsApp/Gmail messages, create calendar events, or mutate trackers.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "CRM_FOLLOWUP_REPORT.json"

SOURCE_PATHS = {
    "crm_guide": "crm/CRM-GUIDE.md",
    "buyer_tracker": "crm/BUYER-TRACKER.md",
    "seller_tracker": "crm/SELLER-TRACKER.md",
    "tenant_tracker": "crm/TENANT-TRACKER.md",
    "landlord_tracker": "crm/LANDLORD-TRACKER.md",
    "client_manager_agent": "agents/04-CLIENT-MANAGER-AGENT.md",
    "lead_qualification_sop": "sops/SOP-09-LEAD-QUALIFICATION.md",
    "client_onboarding_workflow": "workflows/WF-05-CLIENT-ONBOARDING.md",
    "crm_lead_scorer": "automation/crm_business_os/runtime/crm_lead_scorer.py",
    "lead_pipeline_engine": "automation/lead_pipeline_os/runtime/lead_pipeline_engine.py",
}

DEFAULT_LEADS = [
    {
        "lead_id": "LEAD-JVC-READY-001",
        "name": "Validation Buyer",
        "channel": "WhatsApp",
        "client_type": "buyer",
        "message": "Cash buyer. Need 2 bed in JVC, budget AED 1m, viewing today if possible.",
        "budget": "AED 1,000,000",
        "areas": ["JVC"],
        "timeline": "today",
        "last_contact_hours_ago": 2,
        "stage": "Inquiry",
        "kyc_status": "PENDING",
    },
    {
        "lead_id": "LEAD-PALM-SELLER-002",
        "name": "Palm Owner",
        "channel": "Referral call",
        "client_type": "seller",
        "message": "Owner wants valuation for Palm villa and may sell this month.",
        "budget": "",
        "areas": ["Palm Jumeirah"],
        "timeline": "this month",
        "last_contact_hours_ago": 18,
        "stage": "Qualified",
        "kyc_status": "PENDING",
    },
    {
        "lead_id": "LEAD-DH-TENANT-003",
        "name": "Dubai Hills Tenant",
        "channel": "Portal message",
        "client_type": "tenant",
        "message": "Looking for 1 bedroom in Dubai Hills, move in around 3 months, budget flexible.",
        "budget": "flexible",
        "areas": ["Dubai Hills"],
        "timeline": "3 months",
        "last_contact_hours_ago": 30,
        "stage": "New",
        "kyc_status": "PENDING",
    },
]

HOT_TERMS = {"today", "urgent", "cash", "ready", "viewing", "asap", "now", "immediate", "serious"}
HIGH_VALUE_TERMS = {"buy", "purchase", "invest", "sell", "valuation", "owner", "mortgage", "cash buyer"}
AREA_TERMS = {"palm", "jvc", "dubai marina", "downtown", "business bay", "arabian ranches", "dubai hills", "jlt", "meydan", "emirates living"}

RESPONSE_TARGET_HOURS = {
    "property finder": 5 / 60,
    "bayut call": 5 / 60,
    "portal call": 5 / 60,
    "portal message": 2,
    "portal email": 2,
    "whatsapp": 1,
    "referral call": 0.25,
    "social media dm": 4,
    "instagram": 4,
}

FOLLOWUP_RULES = {
    "Hot": {"sla_hours": 1, "cadence": "daily until decision", "stage": "Immediate follow-up"},
    "Warm": {"sla_hours": 4, "cadence": "every 3 days", "stage": "Same-day follow-up"},
    "Normal": {"sla_hours": 24, "cadence": "weekly for 1 month, then monthly", "stage": "Standard nurture"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower_blob(lead: dict[str, Any]) -> str:
    parts = [
        lead.get("message"),
        lead.get("summary"),
        lead.get("client_type"),
        lead.get("channel"),
        lead.get("budget"),
        lead.get("timeline"),
        " ".join(str(area) for area in lead.get("areas", []) or []),
    ]
    return " ".join(_text(part) for part in parts).lower()


def response_target_hours(channel: str) -> float:
    lowered = channel.lower().strip()
    for key, hours in RESPONSE_TARGET_HOURS.items():
        if key in lowered:
            return hours
    return 24


def score_lead(lead: dict[str, Any], now: datetime) -> dict[str, Any]:
    text = _lower_blob(lead)
    score = 30
    reasons: list[str] = []
    if any(term in text for term in HOT_TERMS):
        score += 25
        reasons.append("urgent timing or readiness signal")
    if any(term in text for term in HIGH_VALUE_TERMS):
        score += 20
        reasons.append("transaction intent")
    if any(area in text for area in AREA_TERMS):
        score += 10
        reasons.append("Dubai area specified")
    if re.search(r"\b\d+(\.\d+)?\s?m\b|million|aed|budget", text):
        score += 10
        reasons.append("budget signal")
    if re.search(r"\b[1-7]\s?(br|bed|bedroom)\b", text):
        score += 5
        reasons.append("unit requirement")
    score = min(score, 100)
    if score >= 80:
        priority = "Hot"
        grade = "A"
    elif score >= 60:
        priority = "Warm"
        grade = "B"
    else:
        priority = "Normal"
        grade = "C"
    rule = FOLLOWUP_RULES[priority]
    lead_id = _text(lead.get("lead_id") or lead.get("Lead ID") or "LEAD-UNASSIGNED")
    due_at = now + timedelta(hours=rule["sla_hours"])
    target_hours = response_target_hours(_text(lead.get("channel")))
    last_contact_hours = float(lead.get("last_contact_hours_ago") or 0)
    stale_risk = last_contact_hours > max(target_hours, rule["sla_hours"])
    return {
        "lead_id": lead_id,
        "name": _text(lead.get("name") or lead.get("Name") or "Unknown lead"),
        "channel": _text(lead.get("channel") or "unknown"),
        "client_type": _text(lead.get("client_type") or "client"),
        "stage": _text(lead.get("stage") or rule["stage"]),
        "lead_score": score,
        "grade": grade,
        "priority": priority,
        "reasons": reasons or ["basic lead captured"],
        "sla_hours": rule["sla_hours"],
        "response_target_hours": target_hours,
        "last_contact_hours_ago": last_contact_hours,
        "stale_risk": stale_risk,
        "next_follow_up": due_at.isoformat(),
        "recommended_stage": rule["stage"],
        "follow_up_cadence": rule["cadence"],
        "kyc_status": _text(lead.get("kyc_status") or "PENDING"),
        "missing_fields": missing_fields(lead),
        "source": "local_crm_followup_runtime",
    }


def missing_fields(lead: dict[str, Any]) -> list[str]:
    checks = {
        "name": lead.get("name") or lead.get("Name"),
        "phone": lead.get("phone") or lead.get("Phone"),
        "email": lead.get("email") or lead.get("Email"),
        "budget_or_requirement": lead.get("budget") or lead.get("message"),
        "source_channel": lead.get("channel"),
        "next_action": lead.get("next_action") or lead.get("Next Action"),
    }
    return [field for field, value in checks.items() if not _text(value)]


def build_tasks(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks = []
    for lead in sorted(scored, key=lambda item: (-item["lead_score"], item["next_follow_up"])):
        tasks.append(
            {
                "task_id": "TASK-" + lead["lead_id"].replace("LEAD-", "").replace("_", "-"),
                "lead_id": lead["lead_id"],
                "title": f"{lead['priority']} follow-up: {lead['name']}",
                "owner": "Omar",
                "due_at": lead["next_follow_up"],
                "status": "Open",
                "approval_required_before_send": True,
                "recommended_action": action_for_lead(lead),
            }
        )
    return tasks


def action_for_lead(lead: dict[str, Any]) -> str:
    if lead["priority"] == "Hot":
        return "Call now, qualify, then send shortlist or viewing options after Omar approval."
    if lead["priority"] == "Warm":
        return "Send options and schedule a same-day or next-day follow-up."
    return "Add to nurture and send a concise market/update message after review."


def build_draft_messages(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drafts = []
    for lead in scored:
        if lead["client_type"].lower() == "seller":
            body = (
                f"Hi {lead['name']}, I can prepare a quick market view and valuation route. "
                "Before I advise pricing, I need the property details, title status, occupancy, and your target timeline."
            )
        elif lead["client_type"].lower() == "tenant":
            body = (
                f"Hi {lead['name']}, I noted your requirement. I will shortlist suitable options and confirm move-in timing, "
                "budget range, furnishing preference, and cheque plan first."
            )
        else:
            body = (
                f"Hi {lead['name']}, I saw your inquiry. I will narrow this to the best matching options and confirm budget, "
                "timeline, finance status, and preferred areas before arranging viewings."
            )
        drafts.append(
            {
                "lead_id": lead["lead_id"],
                "channel": lead["channel"],
                "draft_type": "follow_up_message",
                "body": body,
                "send_enabled": False,
                "approval_required": True,
            }
        )
    return drafts


def build_dashboard(scored: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    hot = [lead for lead in scored if lead["priority"] == "Hot"]
    warm = [lead for lead in scored if lead["priority"] == "Warm"]
    stale = [lead for lead in scored if lead["stale_risk"]]
    return {
        "lead_count": len(scored),
        "hot_leads": len(hot),
        "warm_leads": len(warm),
        "normal_leads": len(scored) - len(hot) - len(warm),
        "open_tasks": len(tasks),
        "stale_risk_count": len(stale),
        "next_due_lead": tasks[0]["lead_id"] if tasks else "",
        "follow_up_quality_rule": "Never let a qualified lead go more than 7 days without contact.",
    }


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    now = _now()
    leads = [dict(item) for item in (payload.get("leads") or DEFAULT_LEADS)]
    scored = [score_lead(lead, now) for lead in leads]
    tasks = build_tasks(scored)
    drafts = build_draft_messages(scored)
    result = {
        "generated_at": now.isoformat(),
        "mode": "safe_local_crm_followup_no_external_side_effects",
        "lead_count": len(scored),
        "scored_leads": scored,
        "follow_up_tasks": tasks,
        "draft_messages": drafts,
        "dashboard": build_dashboard(scored, tasks),
        "crm_rules": {
            "response_targets": RESPONSE_TARGET_HOURS,
            "qualification_questions": [
                "Purpose: investment or own use?",
                "Timeline: when do you need to move or invest?",
                "Budget range?",
                "Finance: cash or mortgage, pre-approved?",
                "Requirement: size, bedrooms, and preferred areas?",
            ],
            "mandatory_crm_fields": [
                "name",
                "phone",
                "email",
                "source",
                "budget_or_requirement",
                "score",
                "next_action",
                "next_action_date",
            ],
            "source_paths": list(SOURCE_PATHS.values()),
        },
        "workflow_handoffs": [
            {"command": "@client", "scope": "client lifecycle, pipeline report, follow-up schedule"},
            {"command": "@lead", "scope": "lead intake, scoring, assignment, approval center"},
            {"command": "@crm", "scope": "CRM scoring, tasks, stale lead digest"},
            {"command": "@property-intel", "scope": "buyer matching and shortlist preparation"},
            {"command": "@calendar", "scope": "viewing or follow-up scheduling after approval"},
            {"command": "@gmail", "scope": "draft-only email follow-up after approval"},
            {"command": "@whatsapp", "scope": "draft-only WhatsApp reply after approval"},
        ],
        "recommended_next_actions": [
            "Call or message Hot leads first, but keep outbound sends behind approval gates.",
            "Complete missing phone, email, source, budget, and next-action fields before marking leads Active.",
            "Push approved lead packets to Airtable only after connector credentials and Omar approval are in place.",
        ],
        "external_side_effects": {
            "airtable_rows_written": False,
            "crm_rows_written": False,
            "messages_sent": False,
            "gmail_drafts_created": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "whatsapp_messages_sent": False,
            "tasks_created_externally": False,
        },
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
