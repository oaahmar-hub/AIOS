"""Tests for the owner WhatsApp command center."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import whatsapp_commands as wc


def test_is_owner_matches_last9(monkeypatch):
    monkeypatch.setattr(wc, "OWNER_PHONE", "971555593714")
    assert wc.is_owner("971555593714")
    assert wc.is_owner("+971 55 559 3714")
    assert wc.is_owner("00971555593714@s.whatsapp.net".replace("@s.whatsapp.net", ""))
    assert not wc.is_owner("971500000000")
    assert not wc.is_owner("")


def test_non_command_passes_through():
    reply, detail = wc.handle("hey how are you")
    assert reply is None and detail == "not_command"


def test_help():
    reply, detail = wc.handle("help")
    assert reply and detail == "cmd:help" and "owner" in reply.lower()


def test_market_command():
    reply, detail = wc.handle("market")
    assert detail == "cmd:market" and reply


def test_find_command_returns_units():
    reply, detail = wc.handle("find Business Bay")
    assert detail == "cmd:find" and reply


def test_owner_command_shape():
    reply, detail = wc.handle("owner Marina Gate")
    assert detail == "cmd:owner" and reply


def test_empty():
    assert wc.handle("")[0] is None
