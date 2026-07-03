#!/usr/bin/env python3
"""Build the AIOS Autopilot queue.

Autopilot is the local operating layer that decides what AIOS can prepare
without interruption and what must stop for Omar because it needs login, OAuth,
payment approval, legal judgment, or another high-risk decision. It never sends,
writes to external systems, starts OAuth, pays, publishes, or activates live
connectors.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "AIOS_AUTOPILOT_REPORT.json"

SOURCE_REPORTS = {
    "aios_brain": "AIOS_BRAIN_REPORT.json",
    "ceo_operating": "CEO_OPERATING_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "mobile_command": "MOBILE_COMMAND_REPORT.json",
    "connector_activation_command": "CONNECTOR_ACTIVATION_COMMAND_PLAN.json",
    "impact_metrics": "IMPACT_METRICS_REPORT.json",
}

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
    "crm_rows_written": False,
    "notion_pages_created": False,
    "instagram_posts_published": False,
    "content_published": False,
    "payments_made": False,
    "portal_submissions": False,
    "legal_claims_finalized": False,
    "n8n_workflows_imported": False,
    "n8n_workflows_activated": False,
    "future_channel_activated": False,
}

STOP_GATES = {"LOGIN_APPROVAL", "OAUTH_APPROVAL", "PAYMENT_APPROVAL", "HIGH_RISK_DECISION", "OTP_CODE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _action(
    *,
    action_id: str,
    domain: str,
    title: str,
    priority: str,
    mode: str,
    gate: str,
    command: str,
    source: str,
    expected_minutes_saved: int,
    evidence: list[str],
    next_step: str,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "domain": domain,
        "title": title,
        "priority": priority,
        "mode": mode,
        "human_intervention_gate": gate,
        "command": command,
        "source_report": source,
        "expected_minutes_saved": expected_minutes_saved,
        "evidence": evidence,
        "next_step": next_step,
        "execution_enabled": False,
        "external_write_enabled": False,
        "approval_required": gate in STOP_GATES,
    }


def _priority_rank(priority: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(priority, 9)


def build_actions(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    ceo = reports["ceo_operating"]
    for index, item in enumerate(ceo.get("priority_stack", [])[:4], start=1):
        actions.append(
            _action(
                action_id=f"AUTO-CEO-{index:02d}",
                domain="ceo_operating",
                title=item.get("title") or item.get("action") or "CEO priority",
                priority="P1" if index <= 2 else "P2",
                mode="prepare_local_brief",
                gate="NO_INTERVENTION_LOCAL_ONLY",
                command=item.get("handoff_command") or "@ceo",
                source=SOURCE_REPORTS["ceo_operating"],
                expected_minutes_saved=18,
                evidence=[SOURCE_REPORTS["ceo_operating"]],
                next_step=item.get("next_action") or "Prepare local operating brief and keep execution disabled.",
            )
        )

    crm = reports["crm_followup"]
    for index, task in enumerate(crm.get("follow_up_tasks", [])[:4], start=1):
        priority = "P1" if "hot" in str(task).lower() or index == 1 else "P2"
        actions.append(
            _action(
                action_id=f"AUTO-CRM-{index:02d}",
                domain="crm_followup",
                title=task.get("task") or task.get("title") or task.get("lead_name") or "CRM follow-up",
                priority=priority,
                mode="draft_follow_up_only",
                gate="HIGH_RISK_DECISION" if priority == "P1" else "NO_INTERVENTION_LOCAL_ONLY",
                command="@crm-followup",
                source=SOURCE_REPORTS["crm_followup"],
                expected_minutes_saved=12,
                evidence=[SOURCE_REPORTS["crm_followup"]],
                next_step="Prepare draft reply/task packet; do not send or write CRM externally.",
            )
        )

    ops = reports["operations_assistant"]
    for index, case in enumerate(ops.get("cases", [])[:4], start=1):
        case_text = f"{case.get('case_type', '')} {case.get('title', '')} {case.get('risk_level', '')}".lower()
        high_risk = any(word in case_text for word in ["noc", "transfer", "mortgage", "visa", "payment", "legal"])
        actions.append(
            _action(
                action_id=f"AUTO-OPS-{index:02d}",
                domain="operations",
                title=case.get("title") or case.get("case_type") or "Operations checklist",
                priority="P1" if high_risk else "P2",
                mode="prepare_checklist_only",
                gate="HIGH_RISK_DECISION" if high_risk else "NO_INTERVENTION_LOCAL_ONLY",
                command="@operations",
                source=SOURCE_REPORTS["operations_assistant"],
                expected_minutes_saved=20,
                evidence=[SOURCE_REPORTS["operations_assistant"]],
                next_step="Prepare checklist and risk notes; stop before portal submission, legal conclusion, or payment.",
            )
        )

    content = reports["content_factory"]
    for index, artifact in enumerate(content.get("draft_artifacts", [])[:4], start=1):
        actions.append(
            _action(
                action_id=f"AUTO-CONTENT-{index:02d}",
                domain="content_factory",
                title=artifact.get("title") or artifact.get("type") or "Content draft",
                priority="P2",
                mode="generate_local_draft",
                gate="NO_INTERVENTION_LOCAL_ONLY",
                command="@content-factory",
                source=SOURCE_REPORTS["content_factory"],
                expected_minutes_saved=15,
                evidence=[SOURCE_REPORTS["content_factory"]],
                next_step="Prepare draft content locally; publishing and asset generation stay disabled.",
            )
        )

    brain = reports["aios_brain"]
    for index, packet in enumerate(brain.get("answer_packets", [])[:3], start=1):
        actions.append(
            _action(
                action_id=f"AUTO-BRAIN-{index:02d}",
                domain="one_brain",
                title=packet.get("query") or packet.get("intent") or "AIOS brain answer",
                priority="P2",
                mode="answer_and_route",
                gate="NO_INTERVENTION_LOCAL_ONLY",
                command="@brain",
                source=SOURCE_REPORTS["aios_brain"],
                expected_minutes_saved=10,
                evidence=packet.get("evidence", [SOURCE_REPORTS["aios_brain"]]),
                next_step="Surface grounded answer, memory packets, and next local action.",
            )
        )

    mobile = reports["mobile_command"]
    for index, action in enumerate(mobile.get("actions", [])[:3], start=1):
        actions.append(
            _action(
                action_id=f"AUTO-MOBILE-{index:02d}",
                domain="mobile_command",
                title=action.get("title") or action.get("intent") or "Mobile command",
                priority="P2",
                mode="prepare_mobile_packet",
                gate="NO_INTERVENTION_LOCAL_ONLY",
                command="@mobile-command",
                source=SOURCE_REPORTS["mobile_command"],
                expected_minutes_saved=8,
                evidence=[SOURCE_REPORTS["mobile_command"]],
                next_step="Prepare mobile command packet; no push notification or device action.",
            )
        )

    activation = reports["connector_activation_command"]
    for index, step in enumerate(activation.get("activation_steps", [])[:5], start=1):
        gate = "LOGIN_APPROVAL" if step.get("status") == "ready_for_user_login_or_credential" else "OAUTH_APPROVAL"
        actions.append(
            _action(
                action_id=f"AUTO-CONNECT-{index:02d}",
                domain="connector_activation",
                title=f"{step.get('connector', 'connector')} setup gate",
                priority="P1" if index <= 3 else "P2",
                mode="prepare_login_or_oauth_handoff",
                gate=gate,
                command=step.get("setup_command") or "@activation-command",
                source=SOURCE_REPORTS["connector_activation_command"],
                expected_minutes_saved=10,
                evidence=[SOURCE_REPORTS["connector_activation_command"]],
                next_step=step.get("handoff") or "Prepare connector setup handoff; do not start OAuth.",
            )
        )

    return sorted(actions, key=lambda item: (_priority_rank(item["priority"]), item["action_id"]))


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    actions = build_actions(reports)
    auto_local = [item for item in actions if item["human_intervention_gate"] == "NO_INTERVENTION_LOCAL_ONLY"]
    stopped = [item for item in actions if item["human_intervention_gate"] in STOP_GATES]
    domains = sorted({item["domain"] for item in actions})
    minutes_saved = sum(item["expected_minutes_saved"] for item in actions)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_autopilot_queue_no_external_side_effects",
        "summary": {
            "action_count": len(actions),
            "auto_local_count": len(auto_local),
            "stopped_for_human_count": len(stopped),
            "high_risk_hold_count": len([item for item in stopped if item["human_intervention_gate"] == "HIGH_RISK_DECISION"]),
            "login_or_oauth_hold_count": len([item for item in stopped if item["human_intervention_gate"] in {"LOGIN_APPROVAL", "OAUTH_APPROVAL", "OTP_CODE"}]),
            "domains_covered_count": len(domains),
            "estimated_minutes_saved": minutes_saved,
            "all_execution_disabled": all(item["execution_enabled"] is False and item["external_write_enabled"] is False for item in actions),
        },
        "domains_covered": domains,
        "autopilot_actions": actions,
        "intervention_policy": {
            "continue_without_asking": ["local brief", "local checklist", "draft copy", "grounded answer", "local command packet"],
            "stop_for": sorted(STOP_GATES),
            "live_execution_rule": "A separate explicit approval is required before sends, writes, OAuth, payments, portal submissions, publishing, or connector activation.",
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
