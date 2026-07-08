"""Candidate inventory tests — the honesty guarantee is the point of these."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate_inventory as ci
import inventory_retrieval as inv

def test_candidates_are_never_marked_quotable():
    for c in ci.worklist(200):
        assert c["quotable"] is False
        assert "verify" in c["disclosure"].lower()

def test_candidates_do_not_leak_into_quotable_inventory():
    # The brain's quotable set must never contain a candidate key.
    live = {(r["area"].lower(), r["building"].lower(), str(r["unit"]).lower()) for r in inv._load_rows()}
    for c in ci.worklist(200):
        assert (c["area"].lower(), c["building"].lower(), c["unit"].lower()) not in live

def test_only_candidate_states_present():
    for c in ci.worklist(200):
        assert c["confidence"] in {"POSSIBLE", "LIKELY"}

def test_every_candidate_has_real_building_unit_price():
    for c in ci.worklist(200):
        assert c["building"] and c["unit"] and c["asking_price"]
        assert not inv._is_junk_building(c["building"])

def test_stats_shape():
    s = ci.stats()
    assert s["ok"] and s["candidates"] == len(ci.worklist(10000))
    assert isinstance(s["by_confidence"], dict)
