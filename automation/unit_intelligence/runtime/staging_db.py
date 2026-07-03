#!/usr/bin/env python3
"""SQLite staging database for unit-intelligence ingestion.

Stores incoming listing URLs, parsed metadata, enrichment status, and audit logs.
No external network calls are made here.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,          -- whatsapp, portal_feed, manual, api
    source_id TEXT,                -- message_id, feed_id, etc.
    raw_input TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, parsed, enriched, resolved, failed
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    parsed_urls TEXT,              -- JSON list of ParsedListingUrl dicts
    extracted_clues TEXT,          -- JSON dict from whatsapp_extractor
    resolved_unit_id TEXT,
    resolver_confidence TEXT,
    resolver_notes TEXT,
    requires_human_review INTEGER DEFAULT 0,
    review_reason TEXT
);

CREATE TABLE IF NOT EXISTS bridge_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    portal TEXT NOT NULL,
    listing_id TEXT,
    url TEXT NOT NULL,
    transaction_type TEXT,
    property_type TEXT,
    area TEXT,
    project TEXT,
    building TEXT,
    bedrooms INTEGER,
    slug TEXT,
    confidence TEXT NOT NULL,
    parse_notes TEXT,
    bridge_status TEXT DEFAULT 'pending', -- pending, matched, enriched, unresolved
    matched_unit_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES ingestion_jobs(job_id)
);

CREATE TABLE IF NOT EXISTS ingestion_audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    candidate_id INTEGER,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,           -- system, user, agent
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_candidates_url ON bridge_candidates(url);
CREATE INDEX IF NOT EXISTS idx_candidates_listing_id ON bridge_candidates(listing_id);
CREATE INDEX IF NOT EXISTS idx_candidates_bridge_status ON bridge_candidates(bridge_status);
"""


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "unit_intelligence_staging.sqlite"


class StagingDatabase:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_job(
        self,
        *,
        source: str,
        source_id: str | None = None,
        raw_input: str,
        parsed_urls: list[dict[str, Any]] | None = None,
        extracted_clues: dict[str, Any] | None = None,
    ) -> int:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO ingestion_jobs
                (source, source_id, raw_input, status, created_at, updated_at, parsed_urls, extracted_clues)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    source_id,
                    raw_input,
                    "pending",
                    now,
                    now,
                    json.dumps(parsed_urls or [], ensure_ascii=False),
                    json.dumps(extracted_clues or {}, ensure_ascii=False),
                ),
            )
            job_id = cursor.lastrowid
            self._log(conn, job_id, None, "job_created", "system", {"source": source})
            conn.commit()
        return job_id

    def update_job_status(
        self,
        job_id: int,
        status: str,
        *,
        resolved_unit_id: str | None = None,
        resolver_confidence: str | None = None,
        resolver_notes: str | None = None,
        requires_human_review: bool = False,
        review_reason: str | None = None,
    ) -> None:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, updated_at = ?, resolved_unit_id = ?, resolver_confidence = ?,
                    resolver_notes = ?, requires_human_review = ?, review_reason = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    now,
                    resolved_unit_id,
                    resolver_confidence,
                    resolver_notes,
                    int(requires_human_review),
                    review_reason,
                    job_id,
                ),
            )
            self._log(conn, job_id, None, "job_status_updated", "system", {"status": status})
            conn.commit()

    def create_candidate(self, job_id: int, candidate: dict[str, Any]) -> int:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO bridge_candidates
                (job_id, portal, listing_id, url, transaction_type, property_type, area, project, building,
                 bedrooms, slug, confidence, parse_notes, bridge_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    candidate.get("portal"),
                    candidate.get("listing_id"),
                    candidate.get("url"),
                    candidate.get("transaction_type") or candidate.get("transaction"),
                    candidate.get("property_type"),
                    candidate.get("area"),
                    candidate.get("project"),
                    candidate.get("building"),
                    candidate.get("bedrooms"),
                    candidate.get("slug"),
                    candidate.get("confidence"),
                    json.dumps(candidate.get("parse_notes", []), ensure_ascii=False),
                    "pending",
                    now,
                    now,
                ),
            )
            candidate_id = cursor.lastrowid
            self._log(conn, job_id, candidate_id, "candidate_created", "system", candidate)
            conn.commit()
        return candidate_id

    def update_candidate_bridge(
        self,
        candidate_id: int,
        bridge_status: str,
        matched_unit_id: str | None = None,
    ) -> None:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE bridge_candidates
                SET bridge_status = ?, matched_unit_id = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (bridge_status, matched_unit_id, now, candidate_id),
            )
            self._log(
                conn,
                None,
                candidate_id,
                "candidate_bridge_updated",
                "system",
                {"bridge_status": bridge_status, "matched_unit_id": matched_unit_id},
            )
            conn.commit()

    def _log(
        self,
        conn: sqlite3.Connection,
        job_id: int | None,
        candidate_id: int | None,
        action: str,
        actor: str,
        details: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO ingestion_audit_log (job_id, candidate_id, action, actor, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                candidate_id,
                action,
                actor,
                json.dumps(details, ensure_ascii=False),
                self._now(),
            ),
        )

    def get_pending_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ingestion_jobs WHERE status = 'pending' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_candidates_by_status(self, status: str, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM bridge_candidates WHERE bridge_status = ? ORDER BY created_at LIMIT ?",
                (status, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_stats(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            job_counts = conn.execute(
                "SELECT status, COUNT(*) FROM ingestion_jobs GROUP BY status"
            ).fetchall()
            candidate_counts = conn.execute(
                "SELECT bridge_status, COUNT(*) FROM bridge_candidates GROUP BY bridge_status"
            ).fetchall()
            audit_count = conn.execute("SELECT COUNT(*) FROM ingestion_audit_log").fetchone()[0]
            return {
                "jobs": dict(job_counts),
                "candidates": dict(candidate_counts),
                "audit_log_entries": audit_count,
            }


if __name__ == "__main__":
    db = StagingDatabase("/tmp/aios_unit_intelligence_staging.sqlite")
    print(json.dumps(db.get_stats(), indent=2))
