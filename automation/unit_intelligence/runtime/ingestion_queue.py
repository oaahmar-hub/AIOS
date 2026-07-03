#!/usr/bin/env python3
"""Ingestion queue orchestrator for unit intelligence.

Safely ingests property clues from WhatsApp messages, manual inputs, and future
portal feeds. All processing is local. No live scraping or external messages.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from staging_db import StagingDatabase
from url_parser import parse_url
from whatsapp_extractor import extract_from_message


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "unit_intelligence_staging.sqlite"


class IngestionQueue:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db = StagingDatabase(db_path or DEFAULT_DB_PATH)

    def ingest_whatsapp_message(self, text: str, message_id: str | None = None) -> dict[str, Any]:
        clues = extract_from_message(text)
        job_id = self.db.create_job(
            source="whatsapp",
            source_id=message_id,
            raw_input=text,
            parsed_urls=[u.to_dict() for u in clues.urls],
            extracted_clues=clues.to_dict(),
        )
        for url in clues.urls:
            self.db.create_candidate(job_id, url.to_dict())
        self.db.update_job_status(job_id, "parsed")
        return {
            "job_id": job_id,
            "source": "whatsapp",
            "urls_found": len(clues.urls),
            "confidence": clues.confidence,
        }

    def ingest_url(self, url: str, source: str = "manual") -> dict[str, Any]:
        parsed = parse_url(url)
        job_id = self.db.create_job(
            source=source,
            raw_input=url,
            parsed_urls=[parsed.to_dict()],
        )
        self.db.create_candidate(job_id, parsed.to_dict())
        self.db.update_job_status(job_id, "parsed")
        return {
            "job_id": job_id,
            "source": source,
            "parsed": parsed.to_dict(),
        }

    def ingest_portal_feed(self, feed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ingest a structured portal feed (e.g., from an approved export or API)."""
        results = []
        for item in feed_items:
            url = item.get("url") or item.get("listing_url")
            if not url:
                continue
            parsed = parse_url(url)
            job_id = self.db.create_job(
                source="portal_feed",
                source_id=item.get("feed_id"),
                raw_input=json.dumps(item, ensure_ascii=False),
                parsed_urls=[parsed.to_dict()],
            )
            candidate = parsed.to_dict()
            # Enrich with feed data if available
            candidate.update({
                "project": item.get("project"),
                "building": item.get("building"),
                "bedrooms": item.get("bedrooms") or candidate.get("bedrooms"),
                "property_type": item.get("property_type") or candidate.get("property_type"),
            })
            self.db.create_candidate(job_id, candidate)
            self.db.update_job_status(job_id, "parsed")
            results.append({"job_id": job_id, "url": url})
        return results

    def process_pending(self, limit: int = 100) -> dict[str, Any]:
        """Process pending jobs by marking them for enrichment/resolution."""
        jobs = self.db.get_pending_jobs(limit)
        for job in jobs:
            job_id = job["job_id"]
            self.db.update_job_status(job_id, "enriched")
        return {"processed": len(jobs)}

    def stats(self) -> dict[str, Any]:
        return self.db.get_stats()


if __name__ == "__main__":
    import sys

    q = IngestionQueue("/tmp/aios_unit_intelligence_staging.sqlite")
    sample = (
        "Hi Omar, check this 2 bed in JVC AED 1.2M "
        "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html"
    )
    if len(sys.argv) > 1:
        sample = " ".join(sys.argv[1:])
    result = q.ingest_whatsapp_message(sample, message_id="MSG-TEST-001")
    print(json.dumps(result, indent=2))
    print(json.dumps(q.stats(), indent=2))
