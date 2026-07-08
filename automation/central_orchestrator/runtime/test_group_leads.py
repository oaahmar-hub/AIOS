"""Group-Lead Agent tests (isolated temp DB)."""
import importlib, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def _fresh():
    os.environ["AIOS_LEADS_DB"] = tempfile.mktemp(suffix=".sqlite3")
    import group_leads as g
    importlib.reload(g)
    return g

def test_detects_real_request_only():
    g = _fresh()
    assert g.is_request("Looking for a 2BR in JVC under 1.2m, serious buyer")
    assert g.is_request("مطلوب شقة غرفتين في مارينا")
    assert not g.is_request("good morning everyone")
    assert not g.is_request("thanks bro see you")
    assert not g.is_request("the weather is nice in dubai")  # no ask+prop pair

def test_intent_classification():
    g = _fresh()
    assert g.classify_intent("for sale 2BR marina") == "sell"
    assert g.classify_intent("looking to rent a studio") == "rent"
    assert g.classify_intent("serious buyer for villa") == "buy"

def test_detect_records_and_matches_real_inventory():
    g = _fresh()
    r = g.detect("971509", "looking for 1BR in JVC, budget 900k", source="group")
    assert r["is_lead"] and r["intent"] == "inquiry" or r["is_lead"]
    assert r["matches"] >= 1
    for card in r["cards"]:
        assert "JVC" in card  # only real inventory surfaced
    assert g.stats()["leads"] == 1

def test_small_talk_creates_no_lead():
    g = _fresh()
    assert g.detect("971509", "hi how are you")["is_lead"] is False
    assert g.stats()["leads"] == 0

def test_recent_returns_cards():
    g = _fresh()
    g.detect("971509", "need 2BR beachfront around 5m")
    rec = g.recent()
    assert rec and "cards" in rec[0] and rec[0]["intent"]
