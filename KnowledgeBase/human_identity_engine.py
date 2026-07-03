from __future__ import annotations

"""Human Identity Engine (first-generation profile layer).

This module provides a lightweight, dependency-light identity packet for each
WhatsApp interaction:

* Relationship profile
* Communication profile
* Episodic event memory summary
* Omar DNA profile
* Best-version weighting metadata
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import json
import re
from typing import Any


IDENTITY_EVENT_FILE = "human_identity_events.jsonl"
RELATIONSHIP_TYPES = {
    "CLIENT",
    "AGENT",
    "STAFF",
    "FRIEND",
    "FAMILY",
    "INVESTOR",
    "BUYER",
    "SELLER",
    "TENANT",
    "OWNER",
    "DEVELOPER",
    "PARTNER",
    "VIP CLIENT",
    "UNKNOWN",
}


@dataclass
class RelationshipProfile:
    relationship_type: str = "UNKNOWN"
    trust_level: str = "medium"
    communication_style: str = "professional"
    response_style: str = "concise"
    preferred_language: str = ""
    preferred_time: str = "business_hours"
    preferred_detail_level: str = "medium"
    important_events: list[str] | None = None
    previous_conflicts: list[str] | None = None
    previous_wins: list[str] | None = None


@dataclass
class IdentityProfile:
    contact_name: str = ""
    role_summary: str = ""
    communication_pattern: str = "direct"
    negotiation_style: str = "pragmatic"
    decision_style: str = "structured"
    follow_up_style: str = "short"
    closure_style: str = "option-led"
    humor_style: str = "light"
    risk_style: str = "balanced"
    confidence_style: str = "measured"
    preferred_closing_actions: list[str] | None = None


@dataclass
class EpisodicEvent:
    ts: str
    event_type: str
    emotion: str
    outcome: str
    impact: str
    future_relevance: str
    quality_score: float = 0.5
    source: str = "inferred"
    raw: str | None = None


@dataclass
class HumanIdentityContext:
    sender: str
    relationship_profile: RelationshipProfile
    identity_profile: IdentityProfile
    episodes: list[EpisodicEvent]
    best_version_score: float
    last_action_recommendation: str


def _hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:16]


def _normalize_sender(sender: str) -> str:
    return re.sub(r"\D+", "", sender or "")


def _safe_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _infer_relationship_from_text(text: str) -> str:
    blob = (text or "").lower()
    if not blob:
        return "UNKNOWN"
    if any(token in blob for token in ("bro", "buddy", "ياخوي", "احب", "my friend", "صديق")):
        return "FRIEND"
    if any(token in blob for token in ("family", "brother", "أخت", "ابني", "ابن", "ماما", "ابو")):
        return "FAMILY"
    if any(token in blob for token in ("agent", "broker", "coordinator", "مستشار", "وكيل")):
        return "AGENT"
    if any(token in blob for token in ("staff", "team", "assistant", "assistant", "ops", "operations")):
        return "STAFF"
    return "CLIENT"


def _classify_event_type(text: str) -> str:
    blob = (text or "").lower()
    if any(token in blob for token in ("thank", "شكرا", "thanks", "ممتن", "مشكور")):
        return "support"
    if any(token in blob for token in ("sorry", "اعتذار", "غلط", "خطأ", "mistake")):
        return "objection"
    if any(token in blob for token in ("how much", "price", "budget", "رسوم", "تكلفة", "payment")):
        return "negotiation"
    if any(token in blob for token in ("next", "today", "follow", "update", "later", "بكرة")):
        return "follow-up"
    if any(token in blob for token in ("closing", "book", "visit", "viewing", "نلتقي")):
        return "closing"
    if any(token in blob for token in ("angry", "zgh", "frustrat", "غضب", "مشاكل", "issue")):
        return "objection"
    if any(token in blob for token in ("hello", "hi", "hey", "yo", "مساء")):
        return "social"
    return "business"


def _normalize_quality(value: float) -> float:
    try:
        value_f = float(value)
    except Exception:
        return 0.5
    if value_f != value_f:
        return 0.5
    return max(0.0, min(1.0, value_f))


def _infer_quality_from_context(text: str, outcome: str, impact: str, event_type: str) -> float:
    """Estimate episode quality to favor high-performing Omar behavior.

    The engine learns from what worked. Good signals are:
    - Successful operational outcomes (confirmed, agreed, booked, sent options)
    - Clear follow-up progress signals
    - Minimal conflict or confusion
    """
    blob = (text or "").lower()
    score = 0.55

    high_value_terms = (
        "closed",
        "agreed",
        "confirmed",
        "sent options",
        "booking",
        "booked",
        "scheduled",
        "sent shortlist",
        "sent options",
        "approved",
        "accepted",
    )
    friction_terms = ("angry", "bad", "wrong", "confused", "dispute", "complaint", "cancel", "frustrated", "issue", "bug")
    high_detail_terms = ("rationale", "calc", "analysis", "exact", "ready", "specific")

    if any(t in blob for t in high_value_terms):
        score += 0.26
    if any(t in blob for t in high_detail_terms):
        score += 0.08
    if any(t in blob for t in friction_terms):
        score -= 0.25

    if event_type == "closing":
        score += 0.08
    if event_type == "social":
        score += 0.0

    if outcome:
        outcome_blob = outcome.lower()
        if any(t in outcome_blob for t in ("success", "won", "book", "closed", "resolved")):
            score += 0.15
        if any(t in outcome_blob for t in ("fail", "lost", "cancel", "dispute", "escalate")):
            score -= 0.18

    if impact:
        impact_blob = impact.lower()
        if "property" in impact_blob:
            score += 0.02

    return _normalize_quality(score)


def _event_emotion(text: str) -> str:
    blob = (text or "").lower()
    if any(token in blob for token in ("angry", "frustrate", "غاضب", "مشاكل")):
        return "frustrated"
    if any(token in blob for token in ("thank", "nice", "great", "تمام", "ممتاز", "شكرا")):
        return "positive"
    if any(token in blob for token in ("sorry", "sorry", "عذر")):
        return "reflective"
    return "neutral"


def _load_events(event_path: Path, sender: str) -> list[dict[str, Any]]:
    if not event_path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with event_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if str(item.get("sender", "")) == sender:
                    events.append(item)
    except Exception:
        return []
    return events


def _load_all_events(event_path: Path) -> list[dict[str, Any]]:
    if not event_path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with event_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return events


def _append_event(event_path: Path, sender: str, event: EpisodicEvent) -> None:
    event_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(event)
    payload["sender"] = sender
    with event_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_identity_profile(history: str, sender_context: dict[str, Any]) -> IdentityProfile:
    return IdentityProfile(
        contact_name=str(sender_context.get("known_contact_name", "")),
        role_summary=str(sender_context.get("role_summary", "")),
        communication_pattern=sender_context.get("communication_pattern", "direct"),
        negotiation_style=sender_context.get("negotiation_style", "pragmatic"),
        decision_style=sender_context.get("decision_style", "structured"),
        follow_up_style=sender_context.get("follow_up_style", "short"),
        closure_style=sender_context.get("closure_style", "option-led"),
        humor_style=sender_context.get("humor_style", "light"),
        risk_style=sender_context.get("risk_style", "balanced"),
        confidence_style=sender_context.get("confidence_style", "measured"),
        preferred_closing_actions=_safe_list(sender_context.get("preferred_closing_actions")),
    )


def _select_best_version(events: list[dict[str, Any]]) -> float:
    if not events:
        return 0.5
    success_terms = ("closed", "agreed", "book", "confirmed", "viewing", "sent options", "paid")
    fail_terms = ("angry", "cancel", "failed", "bad", "dispute", "wrong", "confused", "hesitate", "frustrat")
    success_outcomes = {"won", "success", "resolved", "booked", "agreed", "confirmed", "delivered", "sent"}
    fail_outcomes = {"failed", "lost", "cancelled", "canceled", "bad", "wrong", "complaint", "blocked", "rejected"}

    if not events:
        return 0.5

    score = 0.5
    total_weight = 0.0
    for event in events[-30:]:
        text = (str(event.get("raw", "")).lower() or "")
        outcome_label = str(event.get("outcome_label") or event.get("outcome") or "").lower()
        quality = _normalize_quality(float(event.get("quality_score", 0.5)))
        weight = max(0.35, quality)

        if any(t in text for t in success_terms):
            score = score + (0.04 * weight)
        if any(t in text for t in fail_terms):
            score = score - (0.05 * weight)
        if outcome_label in success_outcomes:
            score = score + (0.06 * weight)
        if outcome_label in fail_outcomes:
            score = score - (0.07 * max(0.35, 1.0 - quality))
        if event.get("source") == "feedback":
            score = score + (0.025 * (quality - 0.5))
        if event.get("future_relevance"):
            score = score + (0.015 * weight)
        total_weight += weight

    if total_weight > 0:
        score = score / max(1.0, 1.0 + (len(events[-30:]) / 30.0))

    return round(_normalize_quality(score), 3)


def _top_learning_events(events: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
    if not events:
        return []
    enriched = []
    for event in events:
        quality = _normalize_quality(event.get("quality_score", 0.5))
        enriched.append((quality, event))
    enriched.sort(key=lambda item: item[0], reverse=True)
    return [event for _quality, event in enriched[: max(0, top_n)]]


def _build_best_rules(events: list[dict[str, Any]]) -> dict[str, Any]:
    top_events = _top_learning_events(events, top_n=3)
    if not top_events:
        return {
            "learning_rules": [],
            "best_version_signal": "no_learning_events",
            "quality_average": 0.5,
        }
    quality_scores = [_normalize_quality(e.get("quality_score", 0.5)) for e in top_events]
    average_quality = sum(quality_scores) / len(quality_scores)
    return {
        "learning_rules": [str(e.get("event_type", "business")) for e in top_events],
        "best_version_signal": "best_effort_mode" if average_quality >= 0.6 else "fallback_mode",
        "quality_average": round(average_quality, 3),
    }


def _coerce_episode(record: dict[str, Any]) -> EpisodicEvent:
    fields = {f.name for f in EpisodicEvent.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    payload = {k: v for k, v in record.items() if k in fields}
    return EpisodicEvent(**payload)


def build_human_identity_context(
    *,
    sender: str,
    text: str,
    relationship: str,
    profile_summary: dict[str, Any] | None,
    conversation_objective: str,
    intent: str,
    history_text: str,
    data_root: str,
    stored_memory: dict[str, Any] | None = None,
) -> HumanIdentityContext:
    sender = _normalize_sender(sender)
    normalized_relationship = str(relationship or "").upper().strip()
    if normalized_relationship not in RELATIONSHIP_TYPES:
        normalized_relationship = _infer_relationship_from_text(text)

    rel_profile = RelationshipProfile(
        relationship_type=normalized_relationship,
        trust_level=str(stored_memory.get("trust_level", "")) if stored_memory else "medium",
        communication_style=str(stored_memory.get("preferred_tone", "")) if stored_memory else "professional",
        response_style="concise",
        preferred_language=str(stored_memory.get("preferred_language", "")) if stored_memory else "",
        preferred_time=str(stored_memory.get("preferred_time", "business_hours")) if stored_memory else "business_hours",
        preferred_detail_level=str(stored_memory.get("preferred_detail_level", "medium")) if stored_memory else "medium",
        important_events=_safe_list(stored_memory.get("important_events", [])),
        previous_conflicts=_safe_list(stored_memory.get("previous_conflicts", [])),
        previous_wins=_safe_list(stored_memory.get("previous_wins", [])),
    )

    identity_profile = _build_identity_profile(history_text, stored_memory or {})

    event_path = Path(data_root) / "transport" / IDENTITY_EVENT_FILE
    prev_events = _load_events(event_path, sender)
    event = EpisodicEvent(
        ts=_now_iso(),
        event_type=_classify_event_type(text),
        emotion=_event_emotion(text),
        outcome=conversation_objective,
        impact=intent,
        future_relevance="continue",
        quality_score=_infer_quality_from_context(
            text=str(text),
            outcome=conversation_objective,
            impact=intent,
            event_type=_classify_event_type(text),
        ),
        source="inferred_message",
        raw=(text or "")[:250],
    )
    _append_event(event_path, sender, event)

    rec_action = "send options"
    if intent == "complaint":
        rec_action = "investigate and reassure"
    elif conversation_objective == "casual_chat":
        rec_action = "reply naturally and keep context"
    elif conversation_objective == "property_inquiry":
        rec_action = "search and shortlist"
    elif intent in {"closing", "followup"}:
        rec_action = "align timeline and next action"

    return HumanIdentityContext(
        sender=sender or _hash(sender),
        relationship_profile=rel_profile,
        identity_profile=identity_profile,
        episodes=[_coerce_episode(e) for e in _top_learning_events(prev_events, top_n=6)] if prev_events else [],
        best_version_score=_select_best_version(prev_events),
        last_action_recommendation=rec_action,
    )


def build_human_identity_feedback(
    sender: str,
    event_id: str | None = None,
    outcome_label: str | None = None,
    outcome_confidence: float = 0.6,
    impact_level: str = "neutral",
    notes: str | None = None,
    data_root: str | None = None,
) -> dict[str, Any]:
    """Store explicit post-interaction outcomes that can be used for best-version learning.

    This is the hook for real learning: each conversation can contribute a
    concrete outcome and confidence that updates future Omar DNA ranking.
    """
    sender = _normalize_sender(sender)
    if not sender:
        return {"status": "missing_sender", "quality": 0.5}

    root = Path(data_root) if data_root else Path(".")
    event_path = root / "transport" / IDENTITY_EVENT_FILE
    all_records = _load_all_events(event_path)
    event_records = [item for item in all_records if str(item.get("sender", "")) == sender]
    if not event_records:
        return {"status": "no_events", "sender": sender, "quality": 0.5}

    positive_outcomes = {"won", "success", "resolved", "booked", "agreed", "confirmed", "delivered", "sent"}
    negative_outcomes = {"failed", "lost", "cancelled", "canceled", "bad", "wrong", "complaint", "blocked", "rejected"}
    progress_outcomes = {"in_progress", "progress", "satisfaction"}
    normalized_label = (outcome_label or "").lower()
    if normalized_label in positive_outcomes:
        base_quality = 0.75
    elif normalized_label in negative_outcomes:
        base_quality = 0.25
    elif normalized_label in progress_outcomes:
        base_quality = 0.58
    else:
        base_quality = 0.5
    quality = _normalize_quality(base_quality)
    quality = _normalize_quality((quality * 0.85) + _normalize_quality(outcome_confidence) * 0.15)
    best = event_records[-1]
    best["quality_score"] = quality
    best["outcome_label"] = outcome_label or best.get("outcome", "")
    best["outcome_confidence"] = _normalize_quality(outcome_confidence)
    best["impact_level"] = impact_level
    best["feedback_notes"] = notes or ""
    best["source"] = "feedback"

    # Replace only the last event for this sender, preserving all other contacts.
    replaced = False
    updated_events: list[dict[str, Any]] = []
    target_ts = best.get("ts")
    for item in reversed(all_records):
        if not replaced and str(item.get("sender", "")) == sender and item.get("ts") == target_ts:
            updated_events.append(best)
            replaced = True
        else:
            updated_events.append(item)
    updated_events.reverse()
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("w", encoding="utf-8") as f:
        for item in updated_events:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return {
        "status": "stored",
        "sender": sender,
        "quality": quality,
        "event_id": _hash(event_id or str(best.get("ts", ""))),
    }


def identity_context_to_contract(context: HumanIdentityContext) -> dict[str, Any]:
    return {
        "sender": context.sender,
        "relationship_profile": asdict(context.relationship_profile),
        "identity_profile": asdict(context.identity_profile),
        "episodes": [asdict(event) for event in context.episodes],
        "best_version_score": context.best_version_score,
        "last_action_recommendation": context.last_action_recommendation,
        "best_learning_rules": _build_best_rules([asdict(event) for event in context.episodes]),
    }
