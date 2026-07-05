#!/usr/bin/env python3
"""Tests for bridge identifier / URL hygiene in bridge_data_layer.

Run directly: `python test_bridge_data_layer.py`. No network or DB access.
"""
from __future__ import annotations

import bridge_data_layer as b


def test_clean_identifier_rejects_slug_and_url_junk() -> None:
    assert b.clean_identifier("listed") == ""
    assert b.clean_identifier("details") == ""
    assert b.clean_identifier("/details 14924691") == ""
    assert b.clean_identifier("for sale dubai dubai land majan 1583088") == ""
    assert b.clean_identifier("https://www.bayut.com/x") == ""
    assert b.clean_identifier("scaped") == ""


def test_clean_identifier_keeps_real_identifiers() -> None:
    assert b.clean_identifier("000920402") == "000920402"
    assert b.clean_identifier("10306-TIuehO") == "10306-TIuehO"


def test_is_strong_identifier() -> None:
    assert b.is_strong_identifier("000920402", "permit_number") is True
    assert b.is_strong_identifier("AVENUE C VP 02", "property_number") is False  # no digit run
    assert b.is_strong_identifier("PLOT 12345", "plot_number") is False  # space -> plot regex
    assert b.is_strong_identifier("12345", "plot_number") is True
    # Junk must never count as a hard identifier.
    assert b.is_strong_identifier("listed", "property_number") is False
    assert b.is_strong_identifier("/details 14924691", "property_number") is False
    assert b.is_strong_identifier("for sale dubai dubai land majan 1583088", "plot_number") is False


def test_is_listing_url() -> None:
    assert b.is_listing_url("https://www.bayut.com/en/property/details-13818665.html") is True
    assert b.is_listing_url("https://www.propertyfinder.ae/en/plp/rent/apartment-123.html") is True
    # Auth / redirect / login links are not listings.
    assert b.is_listing_url("https://bayut.com/auth/realms/bayut/passwordless-login/actions/action-token?key=x") is False
    assert b.is_listing_url("https://www.propertyfinder.ae/go/CS99856AQC8XFEGMY9P7V0BP0G/ar") is False
    assert b.is_listing_url("https://www.bayut.com/en/signin") is False
    assert b.is_listing_url("https://example.com/property/1") is False


def test_is_placeholder_building() -> None:
    assert b.is_placeholder_building("Canal Bay") is True
    assert b.is_placeholder_building("canal bay") is True
    assert b.is_placeholder_building("Marina Gate") is False


def test_classify_bridge_row_demotes_junk() -> None:
    junk = b.classify_bridge_row(
        {
            "listing_url": "https://www.propertyfinder.ae/go/CS99856AQC8XFEGMY9P7V0BP0G/ar",
            "listing_id": "",
            "broker_reference": "",
            "property_number": "listed",
            "permit_number": "",
            "plot_number": "for sale dubai dubai land majan 1583088",
            "unit_number": "",
            "building_name": "Canal Bay",
            "community": "",
            "project_name": "",
        }
    )
    assert junk["bridge_classification"] == "invalid_bridge"

    real = b.classify_bridge_row(
        {
            "listing_url": "https://www.bayut.com/en/property/details-13818665.html",
            "listing_id": "13818665",
            "broker_reference": "10306-TIuehO",
            "property_number": "",
            "permit_number": "000920402",
            "plot_number": "",
            "unit_number": "",
            "building_name": "Indigo Beach Residence",
            "community": "",
            "project_name": "",
        }
    )
    assert real["bridge_classification"] == "exact_bridge"


def run_all() -> None:
    tests = [
        test_clean_identifier_rejects_slug_and_url_junk,
        test_clean_identifier_keeps_real_identifiers,
        test_is_strong_identifier,
        test_is_listing_url,
        test_is_placeholder_building,
        test_classify_bridge_row_demotes_junk,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: {test.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_all()
