#!/usr/bin/env python3
"""API handlers for unit-intelligence endpoints.

These handlers are safe: they do not scrape portals, send messages, or mutate
external systems. They parse provided input and return structured results with
confidence labels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bridge_enrichment import BridgeEnrichment
from ingestion_queue import IngestionQueue
from staging_db import StagingDatabase


# Reuse the same staging DB path that the queue uses.
STAGING_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "unit_intelligence_staging.sqlite"


def _queue() -> IngestionQueue:
    return IngestionQueue(STAGING_DB_PATH)


def _enricher() -> BridgeEnrichment:
    return BridgeEnrichment(STAGING_DB_PATH)


def _db() -> StagingDatabase:
    return StagingDatabase(STAGING_DB_PATH)


def get_stats() -> dict[str, Any]:
    return {
        "ok": True,
        "route": "/api/unit/stats",
        "staging_db": str(STAGING_DB_PATH.relative_to(STAGING_DB_PATH.parents[2])),
        "stats": _db().get_stats(),
    }


def ingest_url(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "missing_url"}
    source = str(payload.get("source") or "api").strip()
    result = _queue().ingest_url(url, source=source)
    return {"ok": True, "route": "/api/unit/ingest", "source": source, "result": result}


def ingest_message(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or payload.get("message") or "").strip()
    if not text:
        return {"ok": False, "error": "missing_text"}
    message_id = str(payload.get("message_id") or "").strip() or None
    result = _queue().ingest_whatsapp_message(text, message_id=message_id)
    return {"ok": True, "route": "/api/unit/ingest", "source": "whatsapp", "result": result}


def ingest(payload: dict[str, Any]) -> dict[str, Any]:
    if "url" in payload:
        return ingest_url(payload)
    if "text" in payload or "message" in payload:
        return ingest_message(payload)
    return {"ok": False, "error": "missing_url_or_text"}


def resolve_property(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a property clue: URL or free text. Returns candidates with confidence."""
    url = str(payload.get("url") or "").strip()
    text = str(payload.get("text") or payload.get("message") or "").strip()
    if not url and not text:
        return {"ok": False, "error": "missing_url_or_text"}

    enricher = _enricher()
    queue = _queue()
    results: list[dict[str, Any]] = []

    if url:
        ingest_result = queue.ingest_url(url, source="api-resolve")
        # Enrich the candidate(s) created by the ingestion
        db = _db()
        candidates = db.get_candidates_by_status("pending", limit=10)
        for candidate in candidates:
            if candidate["job_id"] == ingest_result["job_id"]:
                results.append(enricher.enrich_candidate(candidate["candidate_id"]))

    if text:
        ingest_result = queue.ingest_whatsapp_message(text, message_id="api-resolve")
        db = _db()
        candidates = db.get_candidates_by_status("pending", limit=10)
        for candidate in candidates:
            if candidate["job_id"] == ingest_result["job_id"]:
                results.append(enricher.enrich_candidate(candidate["candidate_id"]))

    return {
        "ok": True,
        "route": "/api/property/resolve",
        "input": {"url": url, "text": text},
        "candidates_processed": len(results),
        "results": results,
        "notes": "Matched resolver unit fields may be sparse; enrich resolver data via external feeds or manual input.",
    }


def enrich_pending(payload: dict[str, Any]) -> dict[str, Any]:
    limit = int(payload.get("limit", 100))
    result = _enricher().enrich_all_pending(limit=limit)
    return {"ok": True, "route": "/api/unit/enrich", "result": result}
