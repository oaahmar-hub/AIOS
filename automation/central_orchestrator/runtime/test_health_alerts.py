"""Tests for the health-alert monitor."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import health_alerts as ha

ha._STATE = Path(tempfile.mkdtemp()) / "health_alert_state.json"
ha.ALERT_PHONE = "971500000000"


class Sender:
    def __init__(self):
        self.sent = []

    def __call__(self, phone, text):
        self.sent.append((phone, text))
        return True, "test"


def _health(status, fails=()):
    return {"status": status,
            "components": {name: {"ok": False} for name in fails}}


def setup_function(_):
    try:
        ha._STATE.unlink()
    except FileNotFoundError:
        pass


def test_green_is_quiet():
    s = Sender()
    assert ha.check_once(lambda: _health("healthy"), s, now=1000) == "green_quiet"
    assert s.sent == []


def test_red_alerts_once_then_stays_quiet():
    s = Sender()
    assert ha.check_once(lambda: _health("degraded", ["crm_leads"]), s, now=1000) == "alert_sent"
    assert "crm_leads" in s.sent[0][1]
    assert ha.check_once(lambda: _health("degraded", ["crm_leads"]), s, now=2000) == "red_quiet"
    assert len(s.sent) == 1


def test_new_failure_realerts():
    s = Sender()
    ha.check_once(lambda: _health("degraded", ["crm_leads"]), s, now=1000)
    assert ha.check_once(lambda: _health("degraded", ["crm_leads", "media_vault"]), s, now=2000) == "alert_sent"
    assert len(s.sent) == 2


def test_repeat_after_window():
    s = Sender()
    ha.check_once(lambda: _health("down", ["runtime"]), s, now=1000)
    later = 1000 + ha.REPEAT_HOURS * 3600 + 10
    assert ha.check_once(lambda: _health("down", ["runtime"]), s, now=later) == "alert_sent"


def test_recovery_message_once():
    s = Sender()
    ha.check_once(lambda: _health("degraded", ["crm_leads"]), s, now=1000)
    assert ha.check_once(lambda: _health("healthy"), s, now=2000) == "recovered_alert"
    assert "green" in s.sent[-1][1]
    assert ha.check_once(lambda: _health("healthy"), s, now=3000) == "green_quiet"


def test_monitor_never_raises():
    def boom():
        raise RuntimeError("x")
    assert ha.check_once(boom, Sender(), now=1000) == "error"


def test_health_reports_not_configured_by_default():
    h = ha.health()
    assert h["component"] == "health_alerts"
