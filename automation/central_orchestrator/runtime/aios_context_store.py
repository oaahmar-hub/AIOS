#!/usr/bin/env python3
"""Persistent runtime context store for unified relationship + memory state.

This module keeps one canonical context object per contact. It is intentionally
local, file-backed, and small so it can be safely shared by interaction,
unified memory, and validation paths.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
STATE_DIR = RUNTIME_DIR / "state"
STATE_DB = STATE_DIR / "aios_context_store.sqlite"
DECAY_HOURS = 12 * 7 * 24  # 7 days


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_db(path: Path = STATE_DB) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            create table if not exists contact_contexts (
                contact_phone text primary key,
                relationship_tag text not null default 'UNKNOWN',
                dna json,
                weather text,
                profile_summary text,
                relationship_history_summary text,
                history_summary text,
                confidence real default 0.0,
                confidence_source text default 'uninitialized',
                source text default 'runtime',
                decay_until text,
                last_seen_at text,
                created_at text,
                updated_at text,
                interactions integer default 0,
                retrieval_last_count integer default 0
            )
            """
        )
        conn.execute(
            """
            create table if not exists context_events (
                id integer primary key autoincrement,
                contact_phone text,
                event_at text,
                source text,
                payload json,
                relationship_tag text,
                intent text,
                confidence real
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit() or ch == "+")


def _decay_timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc) + timedelta(hours=DECAY_HOURS)).isoformat()


def load_context(phone: str) -> dict[str, Any]:
    _ensure_db()
    normalized = _normalize_phone(phone)
    if not normalized:
        return {}
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select * from contact_contexts where contact_phone = ?",
            (normalized,),
        ).fetchone()
        if not row:
            return {
                "contact_phone": normalized,
                "exists": False,
                "relationship_tag": "UNKNOWN",
                "dna": None,
                "weather": None,
                "profile_summary": None,
                "relationship_history_summary": None,
                "history_summary": None,
                "confidence": 0.0,
                "confidence_source": "uninitialized",
                "source": "runtime",
                "decay_metadata": {
                    "mode": "new",
                    "expires_at": _decay_timestamp(),
                },
                "interactions": 0,
                "retrieval_last_count": 0,
            }

        decay_raw = row["decay_until"]
        return {
            "contact_phone": row["contact_phone"],
            "exists": True,
            "relationship_tag": row["relationship_tag"],
            "dna": json.loads(row["dna"]) if row["dna"] else None,
            "weather": row["weather"],
            "profile_summary": row["profile_summary"],
            "relationship_history_summary": row["relationship_history_summary"],
            "history_summary": row["history_summary"],
            "confidence": float(row["confidence"] or 0.0),
            "confidence_source": row["confidence_source"],
            "source": row["source"],
            "decay_metadata": {
                "mode": "fresh" if decay_raw and datetime.fromisoformat(decay_raw) >= datetime.now(timezone.utc) else "stale",
                "expires_at": decay_raw,
            },
            "interactions": int(row["interactions"] or 0),
            "retrieval_last_count": int(row["retrieval_last_count"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_seen_at": row["last_seen_at"],
        }
    finally:
        conn.close()


def upsert_context(phone: str, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_db()
    normalized = _normalize_phone(phone)
    now = datetime.now(timezone.utc)
    row = load_context(normalized)
    confidence = float(payload.get("confidence", row.get("confidence", 0.0) or 0.0))
    interactions = int((row.get("interactions") or 0) + 1)
    retrieval_last_count = int((payload.get("retrieval_last_count", row.get("retrieval_last_count") or 0) or 0))
    dna = payload.get("dna")
    weather = payload.get("weather")
    profile_summary = payload.get("profile_summary")
    relationship_history_summary = payload.get("relationship_history_summary")
    history_summary = payload.get("history_summary")
    relationship_tag = payload.get("relationship_tag", row.get("relationship_tag", "UNKNOWN"))
    confidence_source = payload.get("confidence_source", row.get("confidence_source", "runtime"))
    source = payload.get("source", row.get("source", "runtime"))
    decay_until = _decay_timestamp(now)

    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            insert into contact_contexts(
                contact_phone, relationship_tag, dna, weather, profile_summary,
                relationship_history_summary, history_summary, confidence,
                confidence_source, source, decay_until, last_seen_at,
                created_at, updated_at, interactions, retrieval_last_count
            ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(contact_phone) do update set
                relationship_tag=excluded.relationship_tag,
                dna=excluded.dna,
                weather=excluded.weather,
                profile_summary=excluded.profile_summary,
                relationship_history_summary=excluded.relationship_history_summary,
                history_summary=excluded.history_summary,
                confidence=excluded.confidence,
                confidence_source=excluded.confidence_source,
                source=excluded.source,
                decay_until=excluded.decay_until,
                last_seen_at=excluded.last_seen_at,
                updated_at=excluded.updated_at,
                interactions=excluded.interactions,
                retrieval_last_count=excluded.retrieval_last_count
            """,
            (
                normalized,
                relationship_tag,
                json.dumps(dna, ensure_ascii=False) if dna is not None else None,
                weather,
                profile_summary,
                relationship_history_summary,
                history_summary,
                confidence,
                confidence_source,
                source,
                decay_until,
                _now(),
                row.get("created_at") or _now(),
                _now(),
                interactions,
                retrieval_last_count,
            ),
        )
        conn.execute(
            """
            insert into context_events(
                contact_phone, event_at, source, payload, relationship_tag, intent, confidence
            ) values(?,?,?,?,?,?,?)
            """,
            (
                normalized,
                _now(),
                source,
                json.dumps(payload, ensure_ascii=False),
                relationship_tag,
                payload.get("intent"),
                confidence,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return load_context(normalized)


def build_context_object(phone: str, payload: dict[str, Any]) -> dict[str, Any]:
    return upsert_context(phone, payload)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect AIOS context store")
    parser.add_argument("phone", help="phone")
    args = parser.parse_args()
    print(json.dumps(load_context(args.phone), ensure_ascii=False, indent=2))
