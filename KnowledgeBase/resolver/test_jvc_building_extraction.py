"""Tests for JVC packed-building recovery and building canonicalization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from repair_resolver_fields import extract_packed_jvc_building, repair_record
from listing_similarity_matcher import canonical_building


def test_packed_jvc_name_with_area_phrase():
    raw = "00 350000 jumeirah village circle may residence jvc10rmra800 1 may residence tower"
    assert extract_packed_jvc_building(raw) == "may residence"


def test_packed_jvc_name_plural_drift():
    raw = "00 363375 jumeirah village circle hyati residence jvc14lmrp200 1 hyati residences apartment building"
    assert extract_packed_jvc_building(raw) == "hyati residence"


def test_packed_jvc_name_truncated_head_recovers_full_name():
    raw = "towers jvc10rhra200 1 bloom towers b 35 b 3206 681"
    assert extract_packed_jvc_building(raw) == "bloom towers"


def test_packed_jvc_name_multi_part_code():
    raw = "00 734506 jumeirah village circle the orchard place jvc12xhrg001b 001c 1 the orchard place tower"
    assert extract_packed_jvc_building(raw) == "the orchard place"


def test_packed_jvc_no_name_returns_none():
    assert extract_packed_jvc_building("56 a402 681") is None
    assert extract_packed_jvc_building("46 null 681 6238 building") is None
    assert extract_packed_jvc_building("00 525000 jumeirah village circle tower") is None
    assert extract_packed_jvc_building("") is None


def test_repair_record_writes_recovered_building_and_is_idempotent():
    record = {
        "building": "00 300000 jumeirah village circle may residence jvc10rmra800 1 may residence tower",
        "project": "",
        "unit": "1203",
        "area": "JVC",
    }
    changes = repair_record(record)
    assert changes["building"] == "May Residence"
    assert changes["project"] == "May Residence"
    record.update(changes)
    assert repair_record(record) == {}


def test_canonical_building_junk_is_empty():
    assert canonical_building("56 a402 681") == ""
    assert canonical_building("46 null 681 6238 building") == ""
    assert canonical_building("65 1009 681") == ""


def test_canonical_building_real_names_survive():
    assert canonical_building("binghatti crescent") == "binghatti crescent"
    assert canonical_building("g24") == "g24"
    assert canonical_building("10 oxford") == "10 oxford"


def test_canonical_building_aliases_align_inventory_and_portal():
    assert canonical_building("cello residences tower b") == canonical_building("cello residences")
    assert canonical_building("hyati residences") == canonical_building("hyati residence")
    assert canonical_building("bloom towers b") == canonical_building("bloom towers")
    assert canonical_building("May Residence") == canonical_building("may residence tower")
    assert canonical_building("luma22 west") == canonical_building("luma22")
    assert canonical_building("oakley square residences") == canonical_building("oakley square")
    # names must remain non-empty after suffix alignment
    for name in ("may residence", "cello residences", "hyati residences", "bloom towers"):
        assert canonical_building(name)
