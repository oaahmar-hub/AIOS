"""Tests for the chat governor: takeover, freshness, throttle, substance."""

import importlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _fresh_governor(tmp_path, **env):
    os.environ["AIOS_GOVERNOR_DB"] = str(tmp_path / "gov.sqlite3")
    for k, v in env.items():
        os.environ[k] = v
    import chat_governor
    importlib.reload(chat_governor)
    return chat_governor


def test_takeover_silences_then_expires(tmp_path):
    gov = _fresh_governor(tmp_path)
    assert not gov.omar_in_control("971501234567")
    gov.record_omar_message("+971 50 123 4567")
    assert gov.omar_in_control("971501234567")
    gov.release_control("971501234567")
    assert not gov.omar_in_control("971501234567")


def test_stale_epoch_and_iso_detection(tmp_path):
    gov = _fresh_governor(tmp_path)
    old_epoch = str(int(time.time()) - 3600)
    fresh_epoch = str(int(time.time()) - 30)
    assert gov.is_stale(old_epoch)
    assert not gov.is_stale(fresh_epoch)
    assert gov.is_stale("2026-07-01T10:00:00+00:00")
    # unparseable/missing -> treated as fresh (fail open for replies)
    assert not gov.is_stale("")
    assert not gov.is_stale("not-a-date")


def test_throttle_gap_and_hourly_cap(tmp_path):
    gov = _fresh_governor(tmp_path, AIOS_REPLY_MIN_GAP_SEC="9999", AIOS_REPLY_HOURLY_CAP="6")
    ok, _ = gov.allow_reply("97150000001")
    assert ok
    gov.note_reply("97150000001")
    ok, reason = gov.allow_reply("97150000001")
    assert not ok and "gap" in reason


def test_hourly_cap(tmp_path):
    gov = _fresh_governor(tmp_path, AIOS_REPLY_MIN_GAP_SEC="0", AIOS_REPLY_HOURLY_CAP="3")
    for _ in range(3):
        gov.note_reply("97150000002")
    ok, reason = gov.allow_reply("97150000002")
    assert not ok and "hourly_cap" in reason


def test_substance_gate(tmp_path):
    gov = _fresh_governor(tmp_path)
    # greeting, question, RE intent, or knowledge -> reply
    assert gov.should_stay_silent("hi", 0) == (False, "greeting")
    assert gov.should_stay_silent("السلام عليكم", 0)[0] is False
    assert gov.should_stay_silent("how much?", 0) == (False, "question")
    assert gov.should_stay_silent("looking to buy a villa", 0) == (False, "re_intent")
    assert gov.should_stay_silent("random words", 3) == (False, "has_knowledge")
    # no knowledge, no intent -> silence
    silent, reason = gov.should_stay_silent("asdf jkl", 0)
    assert silent and reason == "no_knowledge_no_intent"


def test_governor_health(tmp_path):
    gov = _fresh_governor(tmp_path)
    h = gov.health()
    assert h["component"] == "chat_governor" and h["ok"]
