#!/usr/bin/env python3
"""Build integrated AIOS brain answer packets.

This runtime is the local one-brain answer layer. It consumes unified memory,
command-center reports, and domain runtimes to answer representative HSH
questions with evidence, next actions, safety gates, and disabled execution
contracts. It does not call LLM APIs or external services.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "AIOS_BRAIN_REPORT.json"

SOURCE_REPORTS = {
    "unified_memory": "UNIFIED_MEMORY_REPORT.json",
    "property_intelligence": "PROPERTY_INTELLIGENCE_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "ceo_operating": "CEO_OPERATING_REPORT.json",
    "impact_metrics": "IMPACT_METRICS_REPORT.json",
    "mobile_command": "MOBILE_COMMAND_REPORT.json",
    "knowledge_vault": "KNOWLEDGE_VAULT_REPORT.json",
    "approval_state": "APPROVAL_STATE.json",
}

DEFAULT_QUERIES = [
    "What should Omar do first today?",
    "Find JVC property options and prepare the safest client reply",
    "Show DLD transfer and NOC checklist risks before any submission",
    "Which leads need follow-up and what should we draft?",
    "Create campaign content but keep publishing disabled",
    "Load WhatsApp context before replying to a returning contact",
]

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
    "external_llm_called": False,
    "external_search_called": False,
    "workflow_executed": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9@]+", text.lower()) if len(token) >= 2}


def _find_memory_packets(query: str, memory: dict[str, Any]) -> list[dict[str, Any]]:
    terms = _tokens(query)
    scored = []
    for packet in memory.get("context_packets", []):
        haystack = " ".join(
            [
                packet.get("packet_id", ""),
                packet.get("subject", ""),
                packet.get("memory_type", ""),
                packet.get("summary", ""),
                " ".join(packet.get("retrieval_commands", []) or []),
            ]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if any(command in query.lower() for command in packet.get("retrieval_commands", []) or []):
            score += 5
        if score:
            scored.append((score, packet))
    scored.sort(key=lambda item: (-item[0], item[1].get("packet_id", "")))
    return [packet for _, packet in scored[:4]]


def _intent(query: str) -> str:
    lowered = query.lower()
    if any(term in lowered for term in ["today", "first", "priority", "briefing", "ceo"]):
        return "ceo_operating"
    if any(term in lowered for term in ["property", "jvc", "option", "recommend", "shortlist"]):
        return "property_intelligence"
    if any(term in lowered for term in ["dld", "noc", "rera", "transfer", "submission", "mortgage", "ejari"]):
        return "operations"
    if any(term in lowered for term in ["lead", "follow", "client", "draft reply"]):
        return "crm_followup"
    if any(term in lowered for term in ["campaign", "content", "caption", "reel", "publish"]):
        return "content_factory"
    if any(term in lowered for term in ["whatsapp", "returning", "contact", "conversation"]):
        return "conversation_memory"
    return "general_memory"


def _safety_gate(intent: str, query: str) -> str:
    risky = ["payment", "passport", "title deed", "legal", "contract", "transfer", "publish", "send", "reply"]
    if any(term in query.lower() for term in risky):
        return "HOLD_FOR_OMAR_APPROVAL"
    if intent == "content_factory":
        return "DRAFT_ONLY_NO_PUBLISH"
    return "DRAFT_ONLY_NO_EXTERNAL_ACTION"


def _domain_answer(intent: str, reports: dict[str, dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    if intent == "ceo_operating":
        ceo = reports["ceo_operating"]
        priorities = ceo.get("priority_stack", [])
        first = priorities[0] if priorities else {}
        return (
            f"Start with {first.get('title', 'the P1 operating queue')}. The daily plan currently has {len(priorities)} priorities, {len(ceo.get('time_blocks', []))} time blocks, and {len(ceo.get('risk_controls', []))} risk controls.",
            ["CEO_OPERATING_REPORT.json", "APPROVAL_STATE.json", "IMPACT_METRICS_REPORT.json"],
            [first.get("next_action", "Review the CEO operating report.")],
        )
    if intent == "property_intelligence":
        prop = reports["property_intelligence"]
        matches = prop.get("top_matches", [])
        names = [item.get("title", "property option") for item in matches[:3]]
        return (
            f"AIOS found {prop.get('matched_count', 0)} matching property options. Shortlist: {', '.join(names)}. Verify live availability, price, and permit status before sending.",
            ["PROPERTY_INTELLIGENCE_REPORT.json", "UNIFIED_MEMORY_REPORT.json"],
            ["Prepare shortlist draft only.", "Route selected option through Omar approval before WhatsApp or CRM writeback."],
        )
    if intent == "operations":
        ops = reports["operations_assistant"]
        fee = ops.get("fee_calculator", {})
        return (
            f"Operations brain has {ops.get('case_count', 0)} case checklists ready. Validation model shows AED {float(fee.get('total_estimated_cash_to_close', 0)):,.0f} estimated cash-to-close and approval-gated portal/payment/legal steps.",
            ["OPERATIONS_ASSISTANT_REPORT.json", "KNOWLEDGE_VAULT_REPORT.json"],
            ["Use the DLD/NOC checklist before submission.", "Hold portal submissions, payments, and legal decisions for Omar approval."],
        )
    if intent == "crm_followup":
        crm = reports["crm_followup"]
        dash = crm.get("dashboard", {})
        return (
            f"Follow-up engine shows {dash.get('hot_leads', 0)} hot lead, {dash.get('open_tasks', 0)} open tasks, and {dash.get('stale_risk_count', 0)} stale-risk cases. Drafts remain local until approval.",
            ["CRM_FOLLOWUP_REPORT.json", "MOBILE_COMMAND_REPORT.json"],
            ["Review hot lead draft first.", "Confirm missing CRM fields before sending or writing to Airtable."],
        )
    if intent == "content_factory":
        content = reports["content_factory"]
        return (
            f"Content Factory has {content.get('artifact_count', 0)} draft artifacts and {len(content.get('compliance_checks', []))} compliance checks. Publishing, generation, ads, and broadcasts remain disabled.",
            ["CONTENT_FACTORY_REPORT.json", "IMPACT_METRICS_REPORT.json"],
            ["Verify RERA permit, availability, property facts, and media rights.", "Use social/content dry review before any live publish path."],
        )
    if intent == "conversation_memory":
        memory = reports["unified_memory"]
        conv = memory.get("conversation_state", {})
        return (
            f"Unified Memory has read-only WhatsApp state: {conv.get('conversation_count', 0)} conversations, {conv.get('message_count', 0)} messages, and {conv.get('reply_decision_count', 0)} reply decisions. Load this before replying to returning contacts.",
            ["UNIFIED_MEMORY_REPORT.json", "conversation_state.sqlite"],
            ["Use conversation context plus CRM follow-up packet.", "Keep actual WhatsApp replies disabled until approval."],
        )
    memory = reports["unified_memory"]
    return (
        f"Unified Memory has {memory.get('memory_packet_count', 0)} one-brain context packets across {', '.join(memory.get('memory_types', []))}.",
        ["UNIFIED_MEMORY_REPORT.json", "COMMAND_CENTER_DATA.json"],
        ["Select the relevant memory packet, then route through the matching domain runtime."],
    )


def answer_query(query: str, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    intent = _intent(query)
    matched_memory = _find_memory_packets(query, reports["unified_memory"])
    answer, evidence, next_actions = _domain_answer(intent, reports)
    commands = []
    for packet in matched_memory:
        commands.extend(packet.get("retrieval_commands", []) or [])
    return {
        "query": query,
        "intent": intent,
        "answer": answer,
        "matched_memory_packets": [
            {
                "packet_id": packet.get("packet_id"),
                "subject": packet.get("subject"),
                "memory_type": packet.get("memory_type"),
                "summary": packet.get("summary"),
            }
            for packet in matched_memory
        ],
        "evidence": evidence,
        "recommended_next_actions": next_actions,
        "retrieval_commands": sorted(set(commands))[:8],
        "safety_gate": _safety_gate(intent, query),
        "execution_enabled": False,
        "approval_required": True,
    }


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    queries = payload.get("queries") or DEFAULT_QUERIES
    answer_packets = [answer_query(str(query), reports) for query in queries]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_integrated_aios_brain_no_external_side_effects",
        "query_count": len(answer_packets),
        "answer_packets": answer_packets,
        "capabilities_covered": sorted({packet["intent"] for packet in answer_packets}),
        "memory_packets_available": reports["unified_memory"].get("memory_packet_count", 0),
        "approval_policy": "Every answer is draft-only until Omar approval; live connector execution remains disabled.",
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
