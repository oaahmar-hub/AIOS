"""Truth Bridge audit tests — the score must be earned from real data."""
import datetime, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import truth_bridge_audit as tb

def test_audit_scores_real_inventory():
    a = tb.audit()
    assert a["ok"] and a["units"] > 1000
    assert a["factors"]["identifiers_%"] == 100.0   # every quoted unit has real building+unit
    assert a["factors"]["price_or_size_%"] >= 95
    assert 0 <= a["score"] <= 100

def test_freshness_is_actually_penalised():
    # A far-future "today" makes everything stale -> score must drop.
    now = tb.audit()["score"]
    stale = tb.audit(today=datetime.date(2030, 1, 1))["score"]
    assert stale < now

def test_guarantees_present_and_gap_disclosed():
    a = tb.audit()
    assert a["guarantees"]["no_fabrication"] and a["guarantees"]["honest_disclosure"]
    assert "DLD" in a["remaining_gap"]           # the real remaining gap is named, not hidden

def test_health_shape():
    h = tb.health()
    assert "truth score" in h["detail"]
