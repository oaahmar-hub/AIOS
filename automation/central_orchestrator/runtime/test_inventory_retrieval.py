"""Knowledge-connection tests: retrieval is real-data-only, never invents."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inventory_retrieval as inv


def _raw_index():
    path = Path(__file__).resolve().parents[3] / "KnowledgeBase" / "resolver" / "unit_resolver_index.csv"
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def test_quotable_rows_exist_and_are_clean():
    rows = inv._load_rows()
    assert len(rows) > 100
    for r in rows:
        assert r["area"] and r["building"] and r["unit"]
        assert r["price"] or r["size"]
        assert not inv._is_junk_building(r["building"])
        assert not inv._is_junk_area(r["area"])


def test_every_search_result_exists_in_database():
    raw = {( (r.get("area") or "").strip(), (r.get("unit") or "").strip() ) for r in _raw_index()}
    for msg in ["1BR in JVC under 900k", "2BR beachfront 5m", "unit 1081 cello residences"]:
        for hit in inv.search(msg):
            assert (hit["area"], hit["unit"]) in raw, f"invented row: {hit}"


def test_query_parsing():
    q = inv.parse_query("hi, looking for 1BR in JVC under 900k")
    assert q["area"] == "JVC" and q["bedrooms"] == 1 and q["budget"] == 900000
    q2 = inv.parse_query("بدور شقة غرفة وصالة في jvc بحدود ٩٠٠ الف")
    assert q2["area"] == "JVC" and q2["bedrooms"] == 1 and q2["budget"] == 900000


def test_no_anchor_returns_nothing():
    assert inv.search("hello how are you") == []
    block, n = inv.build_inventory_context("good morning")
    assert block == "" and n == 0


def test_budget_filter_respected():
    for hit in inv.search("2BR in beachfront under 5m"):
        if hit["price"]:
            assert float(hit["price"].replace(",", "")) <= 5_000_000 * 1.1


def test_context_block_marks_only_quotable_source():
    block, n = inv.build_inventory_context("1BR in JVC")
    assert n > 0 and "ONLY listings you may quote" in block
