#!/usr/bin/env python3
"""AIOS learning runtime for human feedback and outcome updates.

This module keeps learning local and explicit. It records human-reviewed
identity corrections and outcome confirmations into the canonical context store
plus append-only ledgers for validation proof.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios_context_store import load_context, upsert_context


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
IDENTITY_LEDGER_PATH = REPORTS_DIR / "IDENTITY_FEEDBACK_LEDGER.jsonl"
OUTCOME_LEDGER_PATH = REPORTS_DIR / "OUTCOME_LEARNING_LEDGER.jsonl"
IDENTITY_REPORT_PATH = REPORTS_DIR / "IDENTITY_FEEDBACK_REPORT.json"
OUTCOME_REPORT_PATH = REPORTS_DIR / "OUTCOME_LEARNING_REPORT.json"

VALID_RELATIONSHIPS = {"CLIENT", "AGENT", "STAFF", "FRIEND", "FAMILY", "UNKNOWN"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_recent(path: Path, limit: int = 100) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_summary(path: Path, ledger_path: Path, payload: dict[str, Any]) -> None:
    summary = {
        "generated_at": _now(),
        "ledger": str(ledger_path.relative_to(AIOS_ROOT)),
        **payload,
    }
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_identity_feedback(
    phone: str,
    relationship_tag: str,
    corrected_identity_type: str,
    profile_summary: str,
    reason: str,
) -> dict[str, Any]:
    relationship_tag = str(relationship_tag or "").upper().strip()
    if relationship_tag not in VALID_RELATIONSHIPS:
        raise ValueError(f"Invalid relationship_tag: {relationship_tag}")

    before = load_context(phone)
    existing_dna = dict(before.get("dna") or {})
    existing_feedback = list(existing_dna.get("human_feedback_history") or [])
    feedback_entry = {
        "feedback_id": "FDBK-" + uuid.uuid4().hex[:12].upper(),
        "at": _now(),
        "relationship_tag": relationship_tag,
        "identity_type": corrected_identity_type,
        "reason": reason,
    }
    existing_feedback.append(feedback_entry)
    dna = {
        **existing_dna,
        "identity_type": corrected_identity_type,
        "human_feedback_validated": True,
        "human_feedback_history": existing_feedback[-12:],
    }
    payload = {
        "relationship_tag": relationship_tag,
        "dna": dna,
        "weather": before.get("weather") or "not_available",
        "profile_summary": profile_summary,
        "relationship_history_summary": "human_feedback_validated",
        "history_summary": (
            f"Human feedback validated identity as {corrected_identity_type} ({relationship_tag}). "
            f"Reason: {reason}"
        )[:420],
        "confidence": max(float(before.get("confidence") or 0.0), 0.99),
        "confidence_source": "human_feedback",
        "source": "aios_learning_runtime",
        "intent": "identity_feedback",
        "retrieval_last_count": int(before.get("retrieval_last_count") or 0),
    }
    after = upsert_context(phone, payload)
    ledger_entry = {
        "event": "identity_feedback",
        "phone": phone,
        "before_relationship_tag": before.get("relationship_tag"),
        "after_relationship_tag": after.get("relationship_tag"),
        "corrected_identity_type": corrected_identity_type,
        "profile_summary": profile_summary,
        "reason": reason,
        "at": _now(),
        "context_source": after.get("source"),
    }
    _append_jsonl(IDENTITY_LEDGER_PATH, ledger_entry)
    _write_summary(
        IDENTITY_REPORT_PATH,
        IDENTITY_LEDGER_PATH,
        {
            "entry_count": len(_read_recent(IDENTITY_LEDGER_PATH, limit=1000)),
            "latest_entry": ledger_entry,
            "latest_context": after,
        },
    )
    return {
        "before": before,
        "after": after,
        "ledger_entry": ledger_entry,
        "ledger_path": str(IDENTITY_LEDGER_PATH.relative_to(AIOS_ROOT)),
        "report_path": str(IDENTITY_REPORT_PATH.relative_to(AIOS_ROOT)),
    }


def record_outcome_learning(
    phone: str,
    outcome_type: str,
    outcome_status: str,
    notes: str,
    impact_score: float = 0.8,
) -> dict[str, Any]:
    before = load_context(phone)
    existing_dna = dict(before.get("dna") or {})
    history = list(existing_dna.get("outcome_history") or [])
    outcome_entry = {
        "outcome_id": "OUT-" + uuid.uuid4().hex[:12].upper(),
        "at": _now(),
        "type": outcome_type,
        "status": outcome_status,
        "notes": notes,
        "impact_score": impact_score,
    }
    history.append(outcome_entry)
    dna = {
        **existing_dna,
        "last_outcome_type": outcome_type,
        "last_outcome_status": outcome_status,
        "outcome_history": history[-20:],
    }
    previous_history = str(before.get("history_summary") or "").strip()
    history_summary = (
        f"{previous_history} | Outcome: {outcome_type} [{outcome_status}] {notes}".strip(" |")
        if previous_history
        else f"Outcome: {outcome_type} [{outcome_status}] {notes}"
    )[:420]
    payload = {
        "relationship_tag": before.get("relationship_tag") or "UNKNOWN",
        "dna": dna,
        "weather": before.get("weather") or "not_available",
        "profile_summary": before.get("profile_summary") or f"Outcome-tracked contact {phone}",
        "relationship_history_summary": before.get("relationship_history_summary") or "outcome_learning",
        "history_summary": history_summary,
        "confidence": max(float(before.get("confidence") or 0.0), min(0.97, impact_score)),
        "confidence_source": "outcome_learning",
        "source": "aios_learning_runtime",
        "intent": "outcome_learning",
        "retrieval_last_count": int(before.get("retrieval_last_count") or 0),
    }
    after = upsert_context(phone, payload)
    ledger_entry = {
        "event": "outcome_learning",
        "phone": phone,
        "outcome_type": outcome_type,
        "outcome_status": outcome_status,
        "notes": notes,
        "impact_score": impact_score,
        "at": _now(),
        "context_source": after.get("source"),
    }
    _append_jsonl(OUTCOME_LEDGER_PATH, ledger_entry)
    _write_summary(
        OUTCOME_REPORT_PATH,
        OUTCOME_LEDGER_PATH,
        {
            "entry_count": len(_read_recent(OUTCOME_LEDGER_PATH, limit=1000)),
            "latest_entry": ledger_entry,
            "latest_context": after,
        },
    )
    return {
        "before": before,
        "after": after,
        "ledger_entry": ledger_entry,
        "ledger_path": str(OUTCOME_LEDGER_PATH.relative_to(AIOS_ROOT)),
        "report_path": str(OUTCOME_REPORT_PATH.relative_to(AIOS_ROOT)),
    }

