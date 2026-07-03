#!/usr/bin/env python3
"""Unit tests for the unit-intelligence ingestion framework.

No external network calls are made.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import url_parser
from bridge_enrichment import BridgeEnrichment
from feed_adapters import ingest_feed_file, load_feed_file
from ingestion_queue import IngestionQueue
from crm_writeback import CRMWritebackAdapter, CRMWritebackRecord, build_record_from_resolution
from marketing_trigger import MarketingStaging, build_plan, trigger_from_resolution
from staging_db import StagingDatabase
from whatsapp_extractor import extract_from_message


def test_parse_propertyfinder_url() -> None:
    url = "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html"
    parsed = url_parser.parse_url(url)
    assert parsed.portal == "propertyfinder"
    assert parsed.listing_id == "78188849"
    assert parsed.transaction == "rent"
    assert parsed.property_type == "townhouse"
    assert parsed.area == "Jumeirah Village Circle District 12 Nakheel Townhouses"
    assert parsed.confidence == "exact"


def test_parse_unsupported_url() -> None:
    parsed = url_parser.parse_url("https://example.com/listing/123")
    assert parsed.portal == "unknown"
    assert parsed.confidence == "unknown"


def test_whatsapp_extractor() -> None:
    text = (
        "Hi Omar, check this 2 bed in JVC AED 1.2M "
        "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html "
        "call me 0551234567"
    )
    result = extract_from_message(text)
    assert result.source == "whatsapp"
    assert len(result.urls) == 1
    assert result.urls[0].listing_id == "78188849"
    assert 2 in result.bedroom_counts
    assert "0551234567" in result.phone_numbers
    assert "jvc" in [a.lower() for a in result.areas_mentioned]


def test_staging_database_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite"
        db = StagingDatabase(db_path)
        job_id = db.create_job(source="test", raw_input="hello")
        assert job_id is not None
        stats = db.get_stats()
        assert stats["jobs"]["pending"] == 1


def test_ingestion_queue() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite"
        q = IngestionQueue(db_path)
        result = q.ingest_url(
            "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html"
        )
        assert result["job_id"] == 1
        assert result["source"] == "manual"
        stats = q.stats()
        assert stats["jobs"]["parsed"] == 1
        assert stats["candidates"]["pending"] == 1


def test_csv_feed_adapter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "propertyfinder.csv"
        csv_path.write_text(
            "listing_url,listing_id,bedrooms,area,price\n"
            "https://www.propertyfinder.ae/en/plp/rent/apartment-for-rent-dubai-marina-12345678.html,12345678,2,Dubai Marina,150000\n"
        )
        rows = load_feed_file(csv_path)
        assert len(rows) == 1
        assert rows[0]["portal"] == "propertyfinder"
        assert rows[0]["bedrooms"] == 2


def test_feed_adapter_ingest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite"
        csv_path = Path(tmp) / "propertyfinder.csv"
        csv_path.write_text(
            "listing_url,listing_id,bedrooms,area,price\n"
            "https://www.propertyfinder.ae/en/plp/rent/apartment-for-rent-dubai-marina-12345678.html,12345678,2,Dubai Marina,150000\n"
        )
        q = IngestionQueue(db_path)
        result = ingest_feed_file(csv_path, queue=q)
        assert result["rows_loaded"] == 1
        assert result["ingested"] == 1


def test_marketing_plan_for_exact_match() -> None:
    plan = build_plan(source_job_id=1, unit_id="unit-123", confidence="exact", unit_facts={"area": "JVC"})
    assert plan.confidence == "exact"
    assert len(plan.assets) == 5
    assert all(asset.get("approval_required") for asset in plan.assets)


def test_marketing_plan_not_triggered_for_low_confidence() -> None:
    plan = build_plan(source_job_id=1, unit_id="unit-123", confidence="unknown")
    assert len(plan.assets) == 0


def test_marketing_trigger_stages_assets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "marketing.sqlite"
        staging = MarketingStaging(db_path)
        result = trigger_from_resolution(job_id=1, unit_id="unit-123", confidence="exact", staging=staging)
        assert result["staged"] is True
        assert result["assets_count"] == 5
        jobs = staging.get_staged_jobs()
        assert len(jobs) == 1


def test_crm_writeback_dry_run() -> None:
    adapter = CRMWritebackAdapter(dry_run=True)
    record = CRMWritebackRecord(
        contact_name="Test Lead",
        contact_phone="0551234567",
        unit_id="unit-123",
        listing_url="https://example.com/listing/123",
        confidence="exact",
        area="JVC",
    )
    result = adapter.write_lead(record)
    assert result["status"] == "dry_run"
    assert "payload" in result
    assert len(adapter.get_audit()) == 1


def test_crm_writeback_live_mode_requires_confirmation() -> None:
    adapter = CRMWritebackAdapter(dry_run=True)
    try:
        adapter.enable_live_mode(confirmed=False)
        raise AssertionError("Expected RuntimeError")
    except RuntimeError:
        pass


def test_build_record_from_resolution() -> None:
    record = build_record_from_resolution(
        ingestion_job_id=1,
        candidate={
            "url": "https://example.com/listing/123",
            "listing_id": "123",
            "confidence": "exact",
            "matched_unit_id": "unit-abc",
            "portal": "propertyfinder",
        },
        matched_unit={"area": "Marina", "bedrooms": "2"},
        whatsapp_text="Hi Omar, see this link",
    )
    assert record.unit_id == "unit-abc"
    assert record.area == "Marina"
    assert record.bedrooms == "2"
    assert record.channel == "whatsapp"
    assert record.requires_human_review is False


def run_all() -> None:
    tests = [
        test_parse_propertyfinder_url,
        test_parse_unsupported_url,
        test_whatsapp_extractor,
        test_staging_database_schema,
        test_ingestion_queue,
        test_csv_feed_adapter,
        test_feed_adapter_ingest,
        test_marketing_plan_for_exact_match,
        test_marketing_plan_not_triggered_for_low_confidence,
        test_marketing_trigger_stages_assets,
        test_crm_writeback_dry_run,
        test_crm_writeback_live_mode_requires_confirmation,
        test_build_record_from_resolution,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL: {test.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_all()
