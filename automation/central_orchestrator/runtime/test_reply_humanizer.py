"""Tests for the WhatsApp reply humanizer, media honesty, and ack gating."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reply_humanizer as rh


def test_strips_assistant_openers_and_closers():
    raw = (
        "Certainly! The unit in Bloom Towers is 33 sqm at AED 418k.\n"
        "I hope this helps!\n"
        "Feel free to reach out if you have any questions."
    )
    out = rh.humanize(raw)
    assert "Certainly" not in out
    assert "hope this helps" not in out.lower()
    assert "feel free" not in out.lower()
    assert "418k" in out  # facts survive


def test_strips_ai_self_reference():
    out = rh.humanize("As an AI, I cannot visit the site.\nThe villa is on Frond P.")
    assert "as an ai" not in out.lower()
    assert "Frond P" in out


def test_markdown_becomes_whatsapp_style():
    raw = "## Options\n- **Bloom Towers** 1BR\n- **Cello** 2BR\nFurthermore, both are in JVC."
    out = rh.humanize(raw)
    assert "##" not in out and "- " not in out and "**" not in out
    assert "*Bloom Towers*" in out
    assert "furthermore" not in out.lower()
    assert "JVC" in out


def test_arabic_ai_lines_removed():
    raw = "بصفتي ذكاء اصطناعي لا أستطيع.\nالشقة متوفرة في فيردانا."
    out = rh.humanize(raw)
    assert "ذكاء اصطناعي" not in out
    assert "فيردانا" in out


def test_humanize_never_returns_empty_for_nonempty_input():
    assert rh.humanize("I hope this helps!").strip()


def test_plain_ack_detection():
    assert rh.is_plain_ack("ok")
    assert rh.is_plain_ack("Thanks!")
    assert rh.is_plain_ack("تمام")
    assert rh.is_plain_ack("👍")
    assert not rh.is_plain_ack("ok what is the price of the 2BR?")
    assert not rh.is_plain_ack("")


def test_media_intent_en_ar():
    assert rh.media_intent("can you send me photos of the unit?")
    assert rh.media_intent("ابغى صور الشقة والمخطط")
    assert rh.media_intent("share the floor plan please")
    assert not rh.media_intent("what is the price?")


def test_enforce_media_honesty_rewrites_false_attach():
    reply = "Here are the photos of the unit. It has a great view."
    out = rh.enforce_media_honesty(reply, media_sent=False, inbound_text="send photos")
    assert "here are the photos" not in out.lower()
    assert "send" in out.lower() and "shortly" in out.lower()


def test_enforce_media_honesty_arabic():
    reply = "مرفق الصور، الشقة رائعة."
    out = rh.enforce_media_honesty(reply, media_sent=False, inbound_text="ابغى صور")
    assert "مرفق" not in out
    assert "الصور" in out  # honest Arabic promise present


def test_enforce_media_honesty_noop_when_media_sent():
    reply = "Here are the photos of the unit."
    assert rh.enforce_media_honesty(reply, media_sent=True) == reply


def test_prompt_rules_mention_key_constraints():
    rules = rh.prompt_rules()
    assert "AI" in rules and "WhatsApp" in rules
    assert "check and confirm" in rules


def test_media_vault_missing_index_is_safe():
    import media_vault
    assert media_vault.find_media("photos of verdana") is None or isinstance(
        media_vault.find_media("photos of verdana"), dict
    )
    h = media_vault.health()
    assert h["component"] == "media_vault"


def test_voice_notes_gated_off_by_default():
    import voice_notes
    assert voice_notes.synthesize("hello") is None or voice_notes.is_configured()
    h = voice_notes.health()
    assert h["component"] == "voice_notes"
