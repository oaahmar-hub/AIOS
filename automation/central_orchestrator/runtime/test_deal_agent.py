"""Tests for the autonomous Deal Agent loop + request parser."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deal_agent as da
from deal_parser import parse_request

da._STATE_DIR = Path(tempfile.mkdtemp()) / "deal_agent"


# ---- parser ---------------------------------------------------------------
def test_parses_real_requests():
    c = parse_request("Need 2BR JVC for rent under 90k")
    assert c["area"] == "JVC" and c["intent"] == "rent" and c["beds"] == "2BR" and c["budget"] == 90000

    c = parse_request("client wants 3 bed villa Palm for sale 12M")
    assert c["area"] == "Palm Jumeirah" and c["intent"] == "sale" and c["type"] == "villa" and c["budget"] == 12_000_000

    c = parse_request("Looking for studio Marina rental budget 55k")
    assert c["area"] == "Dubai Marina" and c["beds"] == "studio" and c["budget"] == 55000


def test_parses_arabic_request():
    c = parse_request("مطلوب 1 غرفة الخليج التجاري للايجار 70 الف")
    assert c and c["area"] == "Business Bay" and c["intent"] == "rent" and c["budget"] == 70000


def test_ignores_chatter_and_listings():
    assert parse_request("good morning everyone") is None
    assert parse_request("thanks bro") is None
    # a listing (offering, not requesting) with no request hint
    assert parse_request("Beautiful apartment available call me") is None


# ---- loop -----------------------------------------------------------------
class Spy:
    def __init__(self):
        self.wa = []
        self.group = []
        self.calls = []

    def search(self, criteria):
        return [{"building": "Bloom Towers", "unit": "C-2308", "price": "88000"}]

    def owners(self, unit):
        return [{"name": "Owner One", "phone": "971500000001"},
                {"name": "Owner Two", "phone": "971500000002"}]

    def send_wa(self, to, text):
        self.wa.append((to, text)); return True, "sent"

    def reply_group(self, gid, text):
        self.group.append((gid, text)); return True, "posted"

    def place_call(self, to, script):
        self.calls.append((to, script)); return {"ok": True, "transcript": "available, 90k"}


def _agent(spy):
    return da.DealAgent(
        parse=parse_request, search=spy.search, lookup_owners=spy.owners,
        send_whatsapp=spy.send_wa, reply_group=spy.reply_group, place_call=spy.place_call,
    )


def test_full_loop_end_to_end():
    spy = Spy()
    agent = _agent(spy)
    deal = agent.intake("group-123", "971509999999", "Need 2BR JVC for rent under 90k")
    assert deal and deal.stage == "parsed"
    agent.run_to_completion(deal)
    assert deal.stage == "done"
    # contacted owners (capped) and replied to the group
    assert len(spy.wa) == 2  # two owners (MAX_OWNERS_PER_DEAL default 3)
    assert len(spy.group) == 1
    assert "owners" in spy.group[0][1].lower() or "matching" in spy.group[0][1].lower()


def test_no_owner_data_is_honest():
    spy = Spy()
    spy.owners = lambda unit: []  # no owners on file
    agent = _agent(spy)
    deal = agent.intake("g", "r", "Need 2BR JVC rent 90k")
    agent.run_to_completion(deal)
    assert deal.stage == "no_owner_data"
    # never texted an owner it doesn't have
    assert spy.wa == []


def test_no_matching_units_stops_clean():
    spy = Spy()
    spy.search = lambda c: []
    agent = _agent(spy)
    deal = agent.intake("g", "r", "Need 2BR JVC rent 90k")
    agent.run_to_completion(deal)
    assert deal.stage == "no_match"
    assert spy.wa == []


def test_intake_ignores_nonrequest():
    agent = _agent(Spy())
    assert agent.intake("g", "r", "good morning") is None


def test_owner_rate_limit_guard():
    spy = Spy()
    agent = _agent(spy)
    # same owner phone across two deals in the same second -> second is gapped
    d1 = agent.intake("g", "r", "Need 2BR JVC rent 90k")
    agent.run_to_completion(d1)
    first = len(spy.wa)
    d2 = agent.intake("g", "r", "Need 2BR JVC rent 90k")
    agent.run_to_completion(d2)
    # the min-gap guard prevents immediately re-texting the same two owners
    assert len(spy.wa) == first


def test_health_and_stats():
    h = da.health()
    assert h["component"] == "deal_agent"
    s = da.stats()
    assert "by_stage" in s


def test_owner_lookup_endpoint_masks_without_admin(monkeypatch=None):
    # owner_lookup.lookup already tested; here assert the reveal contract holds
    import owner_lookup as ol
    import tempfile
    from pathlib import Path
    ol.OWNER_DB_PATH = Path(tempfile.mkdtemp()) / "ol.sqlite"
    ol.index_rows([{"building": "Test Tower", "unit": "1", "name": "X", "phone": "971500000009"}], reset=True)
    masked = ol.lookup(building="Test Tower")
    assert masked["owners"][0]["phone"].startswith("***")
    real = ol.lookup(building="Test Tower", reveal=True)
    assert real["owners"][0]["phone"] == "971500000009"
