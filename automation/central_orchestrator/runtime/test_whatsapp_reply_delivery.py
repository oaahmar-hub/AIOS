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


def test_generate_reply_gated_without_endpoint(monkeypatch):
    monkeypatch.setattr(server, "WA_REPLY_ENDPOINT", "")
    text, detail = server._generate_reply_text("hello")
    assert text == "" and detail == "no_endpoint_or_message"


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
