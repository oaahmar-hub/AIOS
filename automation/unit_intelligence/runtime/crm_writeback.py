#!/usr/bin/env python3
"""CRM write-back adapter for resolved unit-intelligence leads.

This module prepares Airtable CRM write-back records. It defaults to dry-run mode
and requires explicit approval for live mutations. No records are written to
Airtable unless approval is explicitly granted.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CRMWritebackRecord:
    lead_source: str = "aios_unit_intelligence"
    channel: str = "whatsapp"
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_name: str | None = None
    unit_id: str | None = None
    listing_url: str | None = None
    listing_id: str | None = None
    confidence: str | None = None
    match_basis: str | None = None
    area: str | None = None
    project: str | None = None
    building: str | None = None
    bedrooms: int | None = None
    price: str | None = None
    notes: str = ""
    requires_human_review: bool = True
    tags: list[str] = field(default_factory=list)

    def to_airtable_lead(self) -> dict[str, Any]:
        return {
            "Source": self.lead_source,
            "Channel": self.channel,
            "Listing URL": self.listing_url,
            "Listing ID": self.listing_id,
            "Unit ID": self.unit_id,
            "Confidence": self.confidence,
            "Match Basis": self.match_basis,
            "Area": self.area,
            "Project": self.project,
            "Building": self.building,
            "Bedrooms": self.bedrooms,
            "Price": self.price,
            "Notes": self.notes,
            "Requires Human Review": self.requires_human_review,
            "Tags": ", ".join(self.tags),
            "Created At": datetime.now(timezone.utc).isoformat(),
        }

    def to_airtable_contact(self) -> dict[str, Any]:
        return {
            "Name": self.contact_name or "Unknown",
            "Phone": self.contact_phone or "",
            "Email": self.contact_email or "",
            "Source": self.lead_source,
            "Tags": ", ".join(self.tags),
        }


class CRMWritebackAdapter:
    """Approval-gated CRM write-back adapter.

    By default this adapter is in dry-run mode. Call `enable_live_mode()` with
    explicit confirmation before any live Airtable mutations.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self._live_mode_enabled = False
        self._audit: list[dict[str, Any]] = []

    def enable_live_mode(self, *, confirmed: bool = False) -> None:
        if not confirmed:
            raise RuntimeError("Live mode must be explicitly confirmed by setting confirmed=True")
        self._live_mode_enabled = True
        self.dry_run = False

    def _log(self, action: str, record: dict[str, Any], result: dict[str, Any]) -> None:
        self._audit.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "dry_run": self.dry_run,
                "record": record,
                "result": result,
            }
        )

    def write_lead(self, record: CRMWritebackRecord) -> dict[str, Any]:
        lead_payload = record.to_airtable_lead()
        if self.dry_run:
            result = {"status": "dry_run", "records_prepared": 1, "payload": lead_payload}
            self._log("write_lead", lead_payload, result)
            return result

        if not self._live_mode_enabled:
            raise RuntimeError("Cannot write to live CRM without explicit approval")

        # Live Airtable write-back would go here. Intentionally not implemented
        # until explicit approval and environment validation.
        result = {
            "status": "not_implemented",
            "reason": "Live Airtable write-back requires environment validation and explicit approval.",
            "payload": lead_payload,
        }
        self._log("write_lead", lead_payload, result)
        return result

    def write_contact(self, record: CRMWritebackRecord) -> dict[str, Any]:
        contact_payload = record.to_airtable_contact()
        if self.dry_run:
            result = {"status": "dry_run", "records_prepared": 1, "payload": contact_payload}
            self._log("write_contact", contact_payload, result)
            return result

        if not self._live_mode_enabled:
            raise RuntimeError("Cannot write to live CRM without explicit approval")

        result = {
            "status": "not_implemented",
            "reason": "Live Airtable write-back requires environment validation and explicit approval.",
            "payload": contact_payload,
        }
        self._log("write_contact", contact_payload, result)
        return result

    def get_audit(self) -> list[dict[str, Any]]:
        return list(self._audit)


def build_record_from_resolution(
    *,
    ingestion_job_id: int,
    candidate: dict[str, Any],
    matched_unit: dict[str, Any],
    whatsapp_text: str | None = None,
) -> CRMWritebackRecord:
    """Build a CRM write-back record from an enriched candidate."""
    notes = f"Resolved by AIOS unit intelligence. Job ID: {ingestion_job_id}."
    if whatsapp_text:
        notes += f" Original message: {whatsapp_text[:200]}"
    return CRMWritebackRecord(
        lead_source="aios_unit_intelligence",
        channel="whatsapp" if whatsapp_text else "api",
        unit_id=str(candidate.get("matched_unit_id") or matched_unit.get("resolver_record_id")),
        listing_url=candidate.get("url"),
        listing_id=candidate.get("listing_id"),
        confidence=candidate.get("confidence"),
        match_basis=candidate.get("match_basis") or "unknown",
        area=matched_unit.get("area") or candidate.get("area"),
        project=matched_unit.get("project") or candidate.get("project"),
        building=matched_unit.get("building") or candidate.get("building"),
        bedrooms=matched_unit.get("bedrooms") or candidate.get("bedrooms"),
        price=matched_unit.get("price"),
        notes=notes,
        requires_human_review=candidate.get("confidence") != "exact",
        tags=["unit_intelligence", candidate.get("portal", "unknown"), candidate.get("confidence", "unknown")],
    )


if __name__ == "__main__":
    adapter = CRMWritebackAdapter(dry_run=True)
    record = CRMWritebackRecord(
        contact_name="Test Lead",
        contact_phone="0551234567",
        unit_id="unit-123",
        listing_url="https://example.com/listing/123",
        confidence="exact",
        area="JVC",
    )
    print(json.dumps(adapter.write_lead(record), indent=2, ensure_ascii=False))
    print("Audit count:", len(adapter.get_audit()))
