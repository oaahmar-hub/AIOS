"""Tests for the Owner Outreach desk."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import owner_outreach as oo


def test_queue_finds_owners_with_masked_mobiles():
    res = oo.queue("beach tower", limit=5)
    assert res["ok"], res
    assert res["matches"] > 0
    for entry in res["queue"]:
        assert entry["mobile_masked"].startswith("***")
        assert len(entry["mobile_masked"]) <= 6  # never a full number
        assert entry["restricted_ref"]
        assert "Omar" in entry["draft"]


def test_queue_never_leaks_full_mobile_anywhere():
    res = oo.queue("beach tower", limit=5)
    blob = str(res)
    for entry in res["queue"]:
        real = oo.resolve_mobile(entry["restricted_ref"])
        assert real  # ref resolves server-side
        assert real not in blob and real[3:] not in blob, "full mobile leaked"


def test_empty_and_junk_queries_are_safe():
    assert oo.queue("")["ok"] is False
    assert oo.queue("x")["ok"] is False


def test_resolve_mobile_roundtrip():
    res = oo.queue("beach tower", limit=1)
    if not res["queue"]:
        return  # environment without data — nothing to roundtrip
    ref = res["queue"][0]["restricted_ref"]
    mobile = oo.resolve_mobile(ref)
    assert mobile and mobile.startswith("971") and len(mobile) == 12


def test_resolve_unknown_ref_is_none():
    assert oo.resolve_mobile("no-such-ref") is None


def test_mobile_normalization():
    assert oo._normalize_mobile("0501234567") == "971501234567"
    assert oo._normalize_mobile("501234567") == "971501234567"
    assert oo._normalize_mobile("971501234567") == "971501234567"
    assert oo._normalize_mobile("00971501234567") == "971501234567"


def test_draft_is_honest_and_has_opt_out():
    d = oo.draft_message("MARIA GAMARRA", "Dubai Marina", "Beach Tower", "2205")
    assert "Omar" in d and "Beach Tower" in d and "2205" in d
    assert "won't contact you again" in d
    ar = oo.draft_message("", "دبي", "برج", "12", lang="ar")
    assert "عمر" in ar


def test_health():
    h = oo.health()
    assert h["component"] == "owner_outreach"
    assert h["restricted_contacts"] > 20000
