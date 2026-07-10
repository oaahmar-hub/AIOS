"""Tests for the reply-discipline governor (staleness, override, mute, rate)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reply_governor as gov

# isolate governor state without leaking env changes into other test modules
_STATE = Path(tempfile.mkdtemp()) / "reply_governor_state.json"
gov._state_path = lambda: _STATE


def setup_function(_):
    # fresh state file per test
    try:
        gov._state_path().unlink()
    except FileNotFoundError:
        pass


def test_stale_messages_are_never_answered():
    from datetime import datetime, timezone, timedelta
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    assert gov.is_stale(old_ts) is True
    assert gov.is_stale(fresh_ts) is False
    assert gov.is_stale("") is False  # no timestamp -> assume live


def test_epoch_timestamps_supported():
    import time
    assert gov.is_stale(str(int(time.time()) - 7200)) is True
    assert gov.is_stale(str(int(time.time()))) is False


def test_human_message_silences_bot_for_contact():
    assert gov.human_active("971501111111") is False
    gov.note_human_message("971501111111", "let me handle this one")
    assert gov.human_active("971501111111") is True
    # a different contact is unaffected
    assert gov.human_active("971502222222") is False


def test_override_expires_after_window():
    import time
    t0 = time.time()
    gov.note_human_message("97150333", "hello", now=t0)
    assert gov.human_active("97150333", now=t0 + 10) is True
    assert gov.human_active("97150333", now=t0 + gov.OVERRIDE_MINUTES * 60 + 5) is False


def test_kill_switch_mute_and_unmute():
    gov.note_human_message("97150444", "#off")
    assert gov.is_muted("97150444") is True
    assert gov.human_active("97150444") is True  # muted = silent
    gov.note_human_message("97150444", "#on")
    assert gov.is_muted("97150444") is False
    assert gov.human_active("97150444") is False


def test_rate_limit_min_gap_and_hourly_cap():
    import time
    t0 = time.time()
    ok, _ = gov.allow_reply("97150555", now=t0)
    assert ok
    ok, detail = gov.allow_reply("97150555", now=t0 + 5)
    assert not ok and "min_gap" in detail
    # space replies out past the gap until the hourly cap trips
    t = t0
    blocked = None
    for i in range(gov.MAX_PER_HOUR + 2):
        t += gov.MIN_GAP_SECONDS + 1
        ok, detail = gov.allow_reply("97150555", now=t)
        if not ok:
            blocked = detail
            break
    assert blocked and "per_hour" in blocked


def test_health_reports():
    h = gov.health()
    assert h["component"] == "reply_governor"
    assert h["limits"]["max_per_hour"] == gov.MAX_PER_HOUR
