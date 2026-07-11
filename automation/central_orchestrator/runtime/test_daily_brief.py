"""Tests for the daily CEO brief."""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import daily_brief as db

db._STATE = Path(tempfile.mkdtemp()) / "daily_brief_state.json"
db.ALERT_PHONE = "971500000000"


class Sender:
    def __init__(self):
        self.sent = []

    def __call__(self, phone, text):
        self.sent.append((phone, text))
        return True, "test"


def _health():
    return {"status": "healthy", "components": {}}


def setup_function(_):
    try:
        db._STATE.unlink()
    except FileNotFoundError:
        pass


def test_brief_sent_after_hour_once_per_day():
    s = Sender()
    at_nine = datetime(2026, 7, 12, 9, 0, tzinfo=db.DUBAI)
    assert db.check_once(_health, s, now_dt=at_nine) == "brief_sent"
    assert db.check_once(_health, s, now_dt=at_nine) == "already_sent"
    assert len(s.sent) == 1


def test_too_early_waits():
    s = Sender()
    at_six = datetime(2026, 7, 12, 6, 0, tzinfo=db.DUBAI)
    assert db.check_once(_health, s, now_dt=at_six) == "too_early"
    assert s.sent == []


def test_next_day_sends_again():
    s = Sender()
    db.check_once(_health, s, now_dt=datetime(2026, 7, 12, 9, 0, tzinfo=db.DUBAI))
    assert db.check_once(_health, s, now_dt=datetime(2026, 7, 13, 9, 0, tzinfo=db.DUBAI)) == "brief_sent"
    assert len(s.sent) == 2


def test_compose_contains_real_sections():
    text = db.compose(_health, since_epoch=0)
    assert "AIOS daily brief" in text
    assert "System: all green" in text
    assert "Inventory:" in text
    assert "Owner outreach:" in text


def test_compose_survives_broken_health():
    def boom():
        raise RuntimeError("x")
    text = db.compose(boom, since_epoch=0)
    assert "System: n/a" in text  # honest fallback, no crash


def test_check_once_never_raises():
    def boom():
        raise RuntimeError("x")
    # even with broken health, the brief goes out with n/a sections
    s = Sender()
    r = db.check_once(boom, s, now_dt=datetime(2026, 7, 14, 9, 0, tzinfo=db.DUBAI))
    assert r in ("brief_sent", "error")


def test_health_component():
    h = db.health()
    assert h["component"] == "daily_brief"
    assert 0 <= h["hour_dubai"] <= 23
