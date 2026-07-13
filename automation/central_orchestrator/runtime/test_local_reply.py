"""Tests for the local (no-LLM, no-n8n) reply brain."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_reply as lr


def test_empty_message():
    assert lr.reply("")[0] == ""


def test_greeting_en():
    txt, detail = lr.reply("Hi there")
    assert txt and detail == "local:greet"


def test_greeting_ar():
    txt, detail = lr.reply("مرحبا")
    assert txt and detail == "local:greet"


def test_thanks():
    txt, detail = lr.reply("thank you")
    assert txt and detail == "local:thanks"


def test_photo_request():
    txt, detail = lr.reply("can you send photos?")
    assert txt and detail == "local:photo"


def test_default_ack_never_empty():
    txt, detail = lr.reply("random unrelated sentence about weather")
    assert txt and detail.startswith("local:")


def test_never_raises_and_always_answers():
    for msg in ["1BR JVC under 900k", "متاح شقة غرفتين الخليج التجاري", "hello", "أهلا", "price?"]:
        txt, detail = lr.reply(msg)
        assert txt, f"empty reply for {msg!r}"
        assert detail.startswith("local:")
