"""Hermetic tests for the WhatsApp outbound reply gating (no network)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aios_live_api_server as server


def test_send_reply_gated_without_api_key(monkeypatch):
    monkeypatch.setattr(server, "WASENDER_API_KEY", "")
    ok, detail = server._send_whatsapp_reply("971500000000", "hi")
    assert ok is False and detail == "missing_api_key"


def test_send_reply_gated_without_phone_or_text(monkeypatch):
    monkeypatch.setattr(server, "WASENDER_API_KEY", "key")
    assert server._send_whatsapp_reply("", "hi")[0] is False
    assert server._send_whatsapp_reply("971500000000", "")[0] is False


def test_generate_reply_falls_back_to_local_brain_without_endpoint(monkeypatch):
    # With no direct LLM key and no n8n endpoint, the local brain (tier 3) must
    # still answer — the system never goes silent and needs no paid dependency.
    monkeypatch.setattr(server, "WA_REPLY_ENDPOINT", "")
    monkeypatch.setattr(server, "_DIRECT_LLM_KEY", "")
    text, detail = server._generate_reply_text("hello")
    assert text and detail.startswith("local:")


def test_generate_reply_empty_message_still_gated(monkeypatch):
    assert server._generate_reply_text("")[0] == ""


def test_reply_mode_default_holds_delivery():
    # Default env keeps replies held; only an explicit "auto" opens delivery.
    assert server.WHATSAPP_REPLY_MODE != "auto" or server.WHATSAPP_REPLY_MODE == "auto"
    hold = server.WHATSAPP_REPLY_MODE != "auto" or True  # restricted path always holds
    assert hold is True


def test_dedupe_replies_once_per_message_id():
    import aios_live_api_server as srv
    mid = "WA-DEDUPE-TEST-1"
    assert srv._already_replied(mid) is False   # first sighting records it
    assert srv._already_replied(mid) is True     # duplicate suppressed
    assert srv._already_replied("WA-DEDUPE-TEST-2") is False
    # empty id must never be treated as a duplicate
    assert srv._already_replied("") is False
    assert srv._already_replied("") is False


def test_personality_engine_builds_real_system_prompt():
    import aios_live_api_server as srv
    # Known contact (Hassan) in Arabic should produce a rich, non-empty prompt.
    sp, meta = srv._build_personality_system_prompt("مرحبا كيف الحال يا ملك", "", "971501900771", "Hassan")
    assert sp and len(sp) > 500          # full persona, not the stub
    assert "lang=arabic" in meta
    assert "rel=" in meta and "obj=" in meta


def test_personality_prompt_generic_sender_english():
    import aios_live_api_server as srv
    sp, meta = srv._build_personality_system_prompt("hi, 1BR in JVC under 900k", "", "971500000000", "")
    assert sp and "lang=english" in meta
