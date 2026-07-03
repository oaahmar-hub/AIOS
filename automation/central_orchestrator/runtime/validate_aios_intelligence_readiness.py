#!/usr/bin/env python3
"""Mission: AIOS Intelligence Ready validation.

Checks:
1) Relationship continuity across sessions.
2) CRM write-back evidence.
3) Context object completion and persistence.
4) Confidence gate behavior.
5) Good-Evening human response.
6) State memory skip-question behavior.
7) Unit finder URL / PDF extraction.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aios_context_store import load_context
from aios_interaction_architecture_runtime import (
    CRM_WRITEBACK_LEDGER_PATH,
    _calculate_confidence,
    _confidence_gate,
    _format_unit_finder_payload,
    _load_configured_relationship_map,
    _load_contact_context_store,
    _state_memory_skip_question,
    process_interaction,
    load_relationship_memory,
)
from aios_context_store import STATE_DB


VALIDATION_REPORT = ROOT / "reports" / "INTELLIGENCE_READY_VALIDATION.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(phone: str, message: str, channel: str = "whatsapp", **extra: Any) -> Dict[str, Any]:
    payload = {
        "from": phone,
        "channel": channel,
        "profile_name": extra.pop("profile_name", "Validation Contact"),
        "message": message,
        "property_interests": extra.pop("property_interests", ["Dubai Marina"]),
    }
    payload.update(extra)
    return payload


def _reset_contact(phone: str) -> None:
    if not phone:
        return
    try:
        conn = sqlite3.connect(str(STATE_DB))
        try:
            conn.execute("delete from contact_contexts where contact_phone = ?", (phone,))
            conn.execute("delete from context_events where contact_phone = ?", (phone,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _ledger_entries_for(phone: str) -> List[Dict[str, Any]]:
    if not CRM_WRITEBACK_LEDGER_PATH.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with CRM_WRITEBACK_LEDGER_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("contact_phone") == phone:
                rows.append(item)
    return rows


def _check(condition: bool, message: str) -> Dict[str, Any]:
    return {
        "passed": bool(condition),
        "message": message,
    }


def _build_identity(event: Dict[str, Any]) -> Dict[str, Any]:
    from aios_interaction_architecture_runtime import detect_identity, load_relationship_memory

    identity = detect_identity(event)
    relationship = load_relationship_memory(event, identity)
    return {"identity": identity, "relationship": relationship}


def _run_relationship_and_context() -> Dict[str, Any]:
    phone = "+971555111222"
    _reset_contact(phone)
    first = process_interaction(_event(phone, "Good evening and quick update on JVC 2 bed budget 2.5m"))
    second = process_interaction(_event(phone, "Can you share Marina options with the same budget and area?"))
    context = load_context(phone)
    rel_first = first["relationship_memory"]["context_object"]
    rel_second = second["relationship_memory"]["context_object"]
    return {
        "phone": phone,
        "first_interaction": {
            "identity_tag": first["identity"]["relationship_tag"],
            "relationship_loaded": first["relationship_memory"]["loaded"],
            "relationship_source": first["relationship_memory"]["context_source"],
            "confidence": rel_first.get("confidence"),
        },
        "second_interaction": {
            "identity_tag": second["identity"]["relationship_tag"],
            "relationship_loaded": second["relationship_memory"]["loaded"],
            "relationship_source": second["relationship_memory"]["context_source"],
            "confidence": rel_second.get("confidence"),
            "decay": second["relationship_memory"]["context_object"].get("decay_metadata"),
        },
        "context_store": context,
        "checks": [
            _check(first["identity"]["type"] != "Unknown", "Identity classified."),
            _check(first["identity"]["relationship_tag"] in {"CLIENT", "AGENT", "STAFF", "FRIEND", "FAMILY", "UNKNOWN"}, "Relationship tag normalized."),
            _check(first["identity"]["relationship_tag"] == second["identity"]["relationship_tag"], "Relationship tag stable across sessions."),
            _check(bool(context.get("exists")), "Persistent context created in store."),
            _check((context.get("interactions") or 0) >= 2, "Interactions incrementing in persistent context."),
            _check(
                "No prior interaction history found." not in str(context.get("history_summary", "")),
                "History summary updated from interaction.",
            ),
        ],
    }


def _run_crm_writeback() -> Dict[str, Any]:
    phone = "+971555101102"
    _reset_contact(phone)
    before = load_context(phone)
    before_ledger_count = len(_ledger_entries_for(phone))
    interaction = process_interaction(
        _event(
            phone,
            "Need a 3-bed villa in Palm Jumeirah, budget 5m. Can we schedule a follow-up?",
            property_interests=["Palm Jumeirah", "3 bed"],
            intent="property_inquiry",
        )
    )
    after = load_context(phone)
    after_ledger = _ledger_entries_for(phone)
    added = after_ledger[before_ledger_count:]
    memory_write = interaction.get("memory_update", {}).get("persisted_context", {})
    return {
        "phone": phone,
        "before_context": before,
        "after_context": after,
        "memory_written": bool(memory_write),
        "ledger_delta_count": len(added),
        "ledger_delta": added,
        "after_fields": {
            "relationship_tag": (memory_write or {}).get("relationship_tag"),
            "lead_state": interaction.get("memory_update", {}).get("pending_update", {}).get("lead_state"),
            "intent": interaction.get("intent", {}).get("intent"),
            "confidence": interaction.get("memory_update", {}).get("pending_update", {}).get("confidence"),
            "timestamp": interaction.get("memory_update", {}).get("write_time"),
        },
        "checks": [
            _check(before.get("exists") is False, "Before state has no prior interactions."),
            _check(after.get("exists") is True, "After state persisted in context store."),
            _check(memory_write is not None and bool(memory_write), "Runtime attempted context persistence."),
            _check(
                interaction.get("memory_update", {}).get("write_enabled"),
                "Memory writeback enabled.",
            ),
            _check(len(added) >= 1, "Ledger records writeback."),
            _check(
                interaction.get("memory_update", {}).get("pending_update", {}).get("lead_state") == "attention_required",
                "Lead state persisted as expected for high-friction interaction.",
            ),
        ],
    }


def _run_context_object_completion() -> Dict[str, Any]:
    phone = "+971555101103"
    _reset_contact(phone)
    interaction = process_interaction(_event(phone, "Show me available 2 bed in Marina, budget 1.5m, furnished"))
    payload = interaction["relationship_memory"]
    context = payload.get("context_object", {})
    required = ["relationship", "dna", "weather", "history_summary", "confidence", "source", "decay_metadata"]
    missing = [key for key in required if key not in context]
    decayed = context.get("decay_metadata", {})
    return {
        "phone": phone,
        "context_object": context,
        "required_fields_present": missing == [],
        "required_fields_missing": missing,
        "decay_mode": decayed.get("mode"),
        "checks": [
            _check(not missing, f"Required context fields present: {', '.join(required)}"),
            _check(context.get("relationship") in {"CLIENT", "AGENT", "STAFF", "FRIEND", "FAMILY", "UNKNOWN"}, "Relationship tag normalized."),
            _check(isinstance(decayed, dict) and bool(decayed.get("expires_at")), "Decay metadata present."),
            _check(context.get("source") in {"aios_context_store", "unified_context_load", "unified_context_fallback", "runtime"}, "Context source tagged."),
            _check(bool(context.get("history_summary")), "History summary available after interaction."),
        ],
    }


def _run_confidence_gate() -> Dict[str, Any]:
    low = _calculate_confidence(
        {"confidence": 0.2, "remember_classification": False, "type": "Unknown", "relationship_tag": "UNKNOWN"},
        {"confidence": 0.2, "intent": "casual_chat"},
        {"context_object": {"confidence": 0.0, "history_summary": ""}},
        {"merged_match_count": 0},
    )
    med = _calculate_confidence(
        {"confidence": 0.84, "remember_classification": True, "type": "Existing Client", "relationship_tag": "CLIENT"},
        {"confidence": 0.56, "intent": "property_inquiry"},
        {"context_object": {"confidence": 0.55, "history_summary": "Prior conversation mentions Marina and budget"}},
        {"merged_match_count": 1},
    )
    high = _calculate_confidence(
        {"confidence": 0.95, "remember_classification": True, "type": "Existing Client", "relationship_tag": "CLIENT"},
        {"confidence": 0.96, "intent": "property_inquiry"},
        {"context_object": {"confidence": 0.95, "history_summary": "Returning client with multiple Marina transactions"}},
        {"merged_match_count": 6},
    )
    return {
        "low": {"score": low, "mode": _confidence_gate(low)},
        "medium": {"score": med, "mode": _confidence_gate(med)},
        "high": {"score": high, "mode": _confidence_gate(high)},
        "checks": [
            _check(_confidence_gate(low) == "retrieve_more", "Low score maps to retrieve_more."),
            _check(_confidence_gate(med) == "clarify", "Medium score maps to clarify."),
            _check(_confidence_gate(high) == "answer", "High score maps to answer."),
        ],
    }


def _run_good_evening() -> Dict[str, Any]:
    r = process_interaction(_event("+971555101104", "Good evening yooo"))
    reply = r.get("response_generation", {}).get("draft_reply", "")
    forbidden = ("no match found", "error", "escalation", "verification in progress")
    return {
        "reply": reply,
        "checks": [
            _check("good evening" in reply.lower(), "Contains a human greeting."),
            _check(not any(term in reply.lower() for term in forbidden), "No technical/bot refusal language."),
        ],
    }


def _run_state_memory() -> Dict[str, Any]:
    phone = "+971555101105"
    _reset_contact(phone)
    first = process_interaction(_event(phone, "Need Marina 2 bed budget 2.5m to check availability"))
    context = first["relationship_memory"]["context_object"]
    follow = process_interaction(_event(phone, "Can you book viewings this weekend?"))
    state = follow.get("state_memory", {})
    return {
        "first_context_loaded": first["relationship_memory"]["loaded"],
        "state_memory_skip_question": state.get("skip_question"),
        "state_memory_reason": state.get("reason"),
        "follow_reply": follow.get("response_generation", {}).get("draft_reply", ""),
        "checks": [
            _check(context.get("history_summary") != "No prior interaction history found.", "History persists before follow-up."),
            _check(bool(state), "State memory decision computed."),
            _check(bool(state.get("skip_question")), "Context-aware skip_question is active."),
            _check(
                not re.search(r"which area|where|tell me|furnished", (follow.get("response_generation", {}).get("draft_reply", "").lower() or ""),
                re.IGNORECASE,
                ) is not None,
                "No repeated qualification wording detected.",
            ),
        ],
    }


def _run_unit_finder() -> Dict[str, Any]:
    cases = [
        ("property_finder", "Check https://www.propertyfinder.ae/property-details/DFR-1234"),
        ("bayut", "https://www.bayut.com/property/details/678901"),
        ("dubizzle", "https://dubizzle.com/property/details/12345678"),
        ("pdf", "Please check ref_2048.pdf from attachment"),
    ]
    results: List[Dict[str, Any]] = []
    for tag, message in cases:
        found = _format_unit_finder_payload(message)
        results.append({"label": tag, "input": message, "unit_finder": found, "found": bool(found.get("found"))})
    return {
        "results": results,
        "checks": [
            _check(all(item["found"] for item in results), "Unit finder resolves all test inputs."),
            _check(all(
                item["unit_finder"].get("source") in {"property_finder", "bayut", "dubizzle", "pdf"}
                for item in results
            ), "Unit finder identifies source for each input."),
        ],
    }


def main() -> int:
    _ = _load_contact_context_store
    _ = _load_configured_relationship_map
    checks: Dict[str, Any] = {
        "metadata": {
            "generated_at": _now(),
            "script": "validate_aios_intelligence_readiness.py",
        },
        "phase_1_relationship_memory": _run_relationship_and_context(),
        "phase_2_crm_writeback": _run_crm_writeback(),
        "phase_3_context_completion": _run_context_object_completion(),
        "phase_4_confidence_gate": _run_confidence_gate(),
        "phase_5_good_evening": _run_good_evening(),
        "phase_6_state_memory": _run_state_memory(),
        "phase_7_unit_finder": _run_unit_finder(),
    }

    all_checks: List[bool] = []
    for phase in checks.values():
        if isinstance(phase, dict) and "checks" in phase:
            all_checks.extend(item["passed"] for item in phase["checks"])
    runtime_ready = all(all_checks)

    checks["readiness"] = {
        "runtime_ready": runtime_ready,
        "intelligence_ready": runtime_ready,
        "production_ready": False,
        "production_readiness_blockers": ["Pending separate hosting/auth/domain/deployment prerequisites for full production readiness."],
    }
    checks["artifacts"] = {
        "crm_writeback_ledger": str(CRM_WRITEBACK_LEDGER_PATH),
        "validation_report": str(VALIDATION_REPORT),
        "screen_capture_note": "No automated UI screenshot capture in this backend-only validation pass.",
    }
    VALIDATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_REPORT.write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(checks, indent=2, ensure_ascii=False))
    return 0 if runtime_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
