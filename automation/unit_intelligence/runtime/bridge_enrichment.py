#!/usr/bin/env python3
"""Bridge enrichment: match ingested candidates against the resolver database.

This module performs read-only matching against the local resolver SQLite
database. It does not scrape portals or call external APIs.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from marketing_trigger import trigger_from_resolution
from staging_db import StagingDatabase

logger = logging.getLogger("bridge_enrichment")


_RESOLVER_DIR = Path(__file__).resolve().parents[3] / "KnowledgeBase" / "resolver"
_AIOS_RESOLVER_DB_PATH = os.getenv("AIOS_RESOLVER_DB_PATH", "").strip()
RESOLVER_DB_PATH = (
    Path(_AIOS_RESOLVER_DB_PATH)
    if _AIOS_RESOLVER_DB_PATH
    else (
        _RESOLVER_DIR / "unit_resolver_database.resolver"
        if (_RESOLVER_DIR / "unit_resolver_database.resolver").is_file()
        else _RESOLVER_DIR / "unit_resolver_database.sqlite"
    )
)


class BridgeEnrichment:
    def __init__(
        self,
        staging_db_path: str | Path | None = None,
        resolver_db_path: str | Path = RESOLVER_DB_PATH,
    ) -> None:
        self.staging = StagingDatabase(staging_db_path) if staging_db_path else StagingDatabase()
        self.resolver_db_path = Path(resolver_db_path)

    def _resolver_conn(self) -> sqlite3.Connection:
        logger.info(
            "resolver_conn: path=%s exists=%s cwd=%s",
            self.resolver_db_path,
            self.resolver_db_path.is_file(),
            Path.cwd(),
        )
        return sqlite3.connect(self.resolver_db_path)

    def match_by_url(self, url: str) -> dict[str, Any] | None:
        """Exact match by listing URL."""
        with self._resolver_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT resolver_record_id, area, project, building, unit, bedrooms, price, size, developer,
                       owner_contact_available, permit_number, property_number, plot_number
                FROM resolver_records
                WHERE listing_url = ? OR property_finder_url = ? OR bayut_url = ? OR dubizzle_url = ?
                LIMIT 1
                """,
                (url, url, url, url),
            ).fetchone()
            if row:
                return dict(row)
        return None

    def match_by_listing_id(self, portal: str, listing_id: str) -> dict[str, Any] | None:
        """Match by listing_id and platform."""
        with self._resolver_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT resolver_record_id, area, project, building, unit, bedrooms, price, size, developer,
                       owner_contact_available, permit_number, property_number, plot_number
                FROM resolver_records
                WHERE listing_id = ? AND listing_platform = ?
                LIMIT 1
                """,
                (listing_id, portal),
            ).fetchone()
            if row:
                return dict(row)
        return None

    def match_by_signals(
        self,
        area: str | None,
        bedrooms: int | None,
        property_type: str | None,
        price: int | None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Likely candidate matching by area, bedrooms, and optionally price."""
        conditions = []
        params: list[Any] = []
        if area:
            conditions.append("area LIKE ?")
            params.append(f"%{area}%")
        if bedrooms is not None:
            conditions.append("bedrooms = ?")
            params.append(str(bedrooms))
        if price is not None:
            conditions.append("ABS(CAST(REPLACE(price, ',', '') AS REAL) - ?) < ?")
            params.append(price)
            params.append(max(price * 0.15, 50_000))

        if not conditions:
            return []

        query = f"""
            SELECT resolver_record_id, area, project, building, unit, bedrooms, price, size, developer,
                   owner_contact_available
            FROM resolver_records
            WHERE {' AND '.join(conditions)}
            LIMIT ?
        """
        params.append(limit)

        with self._resolver_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def enrich_candidate(self, candidate_id: int) -> dict[str, Any]:
        """Try to enrich a single candidate and update its bridge status."""
        with sqlite3.connect(self.staging.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM bridge_candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
            if not row:
                return {"candidate_id": candidate_id, "status": "not_found"}
            candidate = dict(row)

        url = candidate.get("url")
        listing_id = candidate.get("listing_id")
        portal = candidate.get("portal")
        area = candidate.get("area")
        bedrooms = candidate.get("bedrooms")
        property_type = candidate.get("property_type")
        transaction_type = candidate.get("transaction_type") or candidate.get("transaction")
        price = None

        matched = None
        match_basis = None
        confidence = candidate.get("confidence")

        if url:
            matched = self.match_by_url(url)
            if matched:
                match_basis = "exact_url"
                confidence = "exact"

        if not matched and listing_id and portal:
            matched = self.match_by_listing_id(portal, listing_id)
            if matched:
                match_basis = "listing_id"
                confidence = "exact"

        if not matched:
            candidates = self.match_by_signals(area, bedrooms, property_type, price)
            if candidates:
                matched = candidates[0]
                match_basis = "signal_similarity"
                confidence = "likely"

        if matched:
            unit_id = matched.get("resolver_record_id")
            self.staging.update_candidate_bridge(
                candidate_id,
                bridge_status="matched",
                matched_unit_id=str(unit_id),
            )
            # Update parent job with resolved unit if exact
            if confidence == "exact" and candidate.get("job_id"):
                self.staging.update_job_status(
                    candidate["job_id"],
                    "resolved",
                    resolved_unit_id=str(unit_id),
                    resolver_confidence=confidence,
                    resolver_notes=f"Matched via {match_basis}",
                )
                # Stage marketing assets for exact matches
                marketing_result = trigger_from_resolution(
                    job_id=candidate["job_id"],
                    unit_id=str(unit_id),
                    confidence=confidence,
                    unit_facts={
                        "area": matched.get("area"),
                        "project": matched.get("project"),
                        "building": matched.get("building"),
                        "unit": matched.get("unit"),
                        "bedrooms": matched.get("bedrooms"),
                        "price": matched.get("price"),
                        "size": matched.get("size"),
                        "developer": matched.get("developer"),
                    },
                )
                return {
                    "candidate_id": candidate_id,
                    "status": "matched",
                    "match_basis": match_basis,
                    "confidence": confidence,
                    "candidate": candidate,
                    "matched_unit": matched,
                    "marketing_staged": marketing_result.get("staged"),
                    "marketing_job_id": marketing_result.get("marketing_job_id"),
                    "marketing_assets_count": marketing_result.get("assets_count"),
                }
            return {
                "candidate_id": candidate_id,
                "status": "matched",
                "match_basis": match_basis,
                "confidence": confidence,
                "candidate": candidate,
                "matched_unit": matched,
            }

        self.staging.update_candidate_bridge(candidate_id, bridge_status="unresolved")
        return {
            "candidate_id": candidate_id,
            "status": "unresolved",
            "confidence": confidence,
        }

    def enrich_all_pending(self, limit: int = 100) -> dict[str, Any]:
        """Enrich all pending bridge candidates."""
        pending = self.staging.get_candidates_by_status("pending", limit=limit)
        results = []
        for candidate in pending:
            results.append(self.enrich_candidate(candidate["candidate_id"]))
        return {
            "processed": len(results),
            "matched": sum(1 for r in results if r["status"] == "matched"),
            "unresolved": sum(1 for r in results if r["status"] == "unresolved"),
            "results": results,
        }


if __name__ == "__main__":
    import sys

    enricher = BridgeEnrichment()
    # Run a quick demo if no args
    if len(sys.argv) == 1:
        url = "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html"
        match = enricher.match_by_url(url)
        print(json.dumps({"url": url, "match": match}, indent=2, default=str))
    else:
        print(json.dumps(enricher.enrich_all_pending(), indent=2, default=str))
