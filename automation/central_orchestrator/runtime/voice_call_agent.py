#!/usr/bin/env python3
"""Outbound voice-calling agent — the AIOS caller, in Omar's cloned voice.

A fully independent calling channel that dials a number through **Twilio** and
speaks a message using the SAME ElevenLabs clone as the WhatsApp voice notes
(see :mod:`voice_notes`). Never tied to Omar's personal number: it dials FROM a
dedicated Twilio caller number configured in the environment.

stdlib only (urllib) so it runs on the pip-free Railway image, exactly like the
rest of the server. Fully gated — if any credential is missing, every call is a
no-op that reports why through :func:`health`, and nothing else breaks.

Environment:
  TWILIO_ACCOUNT_SID     Twilio account SID  (starts "AC…")
  TWILIO_AUTH_TOKEN      Twilio auth token   (kept only in Railway env — never
                         in git, never in chat)
  TWILIO_CALLER_NUMBER   The dedicated Twilio number to dial FROM (E.164, e.g.
                         "+9714…" or a US number). NOT Omar's personal line.
  AIOS_PUBLIC_BASE_URL   Public https base of this server (e.g.
                         "https://aios-runtime-production.up.railway.app") so
                         Twilio can fetch the spoken audio via <Play>.
  AIOS_VOICE_CALL_ENABLED  "true" to arm the channel.

The clone reuses ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID from voice_notes.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CALL_ENABLED = os.getenv("AIOS_VOICE_CALL_ENABLED", "").strip().lower() in {"1", "true", "yes"}
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM = os.getenv("TWILIO_CALLER_NUMBER", "").strip()
PUBLIC_BASE = os.getenv("AIOS_PUBLIC_BASE_URL", "").strip().rstrip("/")

_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"

# Twilio Polly fallback voices (used only when the ElevenLabs clone is off) so a
# call still speaks rather than failing silently. Zeina = Arabic, Joanna = EN.
_POLLY_AR = "Polly.Zeina"
_POLLY_EN = "Polly.Joanna"

# In-memory audio cache: token -> (mp3_bytes, created_at). Twilio fetches each
# clip once, unauthenticated, via an unguessable token, then it ages out.
_AUDIO: dict[str, tuple[bytes, float]] = {}
_AUDIO_LOCK = threading.Lock()
_AUDIO_TTL = 900          # 15 min is ample for Twilio to fetch + play
_AUDIO_MAX = 200


def twilio_configured() -> bool:
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)


def is_configured() -> bool:
    return bool(CALL_ENABLED and twilio_configured())


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _is_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in (text or ""))


def _prune_audio() -> None:
    now = time.time()
    dead = [k for k, (_, ts) in _AUDIO.items() if now - ts > _AUDIO_TTL]
    for k in dead:
        _AUDIO.pop(k, None)
    if len(_AUDIO) > _AUDIO_MAX:
        for k in sorted(_AUDIO, key=lambda k: _AUDIO[k][1])[: len(_AUDIO) - _AUDIO_MAX]:
            _AUDIO.pop(k, None)


def _store_audio(mp3: bytes) -> str:
    token = secrets.token_urlsafe(18)
    with _AUDIO_LOCK:
        _prune_audio()
        _AUDIO[token] = (mp3, time.time())
    return token


def get_audio(token: str) -> Optional[bytes]:
    """Return cached MP3 bytes for a clip token (Twilio <Play> fetches this)."""
    with _AUDIO_LOCK:
        item = _AUDIO.get(token)
    return item[0] if item else None


def build_twiml(text: str, audio_token: Optional[str]) -> str:
    """TwiML the call plays on answer: the cloned-voice clip when available,
    else a Polly spoken fallback so the call is never silent."""
    if audio_token and PUBLIC_BASE:
        play = "{base}/api/voice/audio/{tok}".format(base=PUBLIC_BASE, tok=audio_token)
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                "<Response><Play>{url}</Play></Response>".format(url=_xml_escape(play)))
    voice = _POLLY_AR if _is_arabic(text) else _POLLY_EN
    lang = "arb" if _is_arabic(text) else "en-US"
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Response><Say voice="{v}" language="{l}">{t}</Say></Response>'.format(
                v=voice, l=lang, t=_xml_escape(text or "Hello from HSH Real Estate.")))


def place_call(to_number: str, message_text: str) -> dict:
    """Dial ``to_number`` and speak ``message_text`` in Omar's cloned voice.

    Returns {ok, sid|error, spoke_with}. Never raises.
    """
    to_number = (to_number or "").strip()
    message_text = (message_text or "").strip()
    if not is_configured():
        return {"ok": False, "error": "voice-calling not configured", "health": health()}
    if not to_number:
        return {"ok": False, "error": "missing destination number"}
    if not to_number.startswith("+"):
        return {"ok": False, "error": "destination must be E.164, e.g. +9715XXXXXXXX"}

    # Try the ElevenLabs clone first; fall back to Twilio Polly if unavailable.
    audio_token = None
    spoke_with = "polly_fallback"
    try:
        import voice_notes as _vn
        mp3 = _vn.synthesize(message_text)
        if mp3:
            audio_token = _store_audio(mp3)
            spoke_with = "omar_clone"
    except Exception:
        audio_token = None

    twiml = build_twiml(message_text, audio_token)
    body = urlencode({"To": to_number, "From": TWILIO_FROM, "Twiml": twiml}).encode("utf-8")
    auth = _basic_auth(TWILIO_SID, TWILIO_TOKEN)
    req = Request(_API.format(sid=TWILIO_SID), data=body,
                  headers={"Authorization": auth,
                           "Content-Type": "application/x-www-form-urlencoded"},
                  method="POST")
    try:
        with urlopen(req, timeout=25) as resp:
            import json as _json
            data = _json.loads(resp.read().decode("utf-8"))
        return {"ok": True, "sid": data.get("sid"), "status": data.get("status"),
                "to": to_number, "spoke_with": spoke_with}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400] if hasattr(exc, "read") else ""
        return {"ok": False, "error": "twilio {}".format(exc.code), "detail": detail}
    except URLError as exc:
        return {"ok": False, "error": "network: {}".format(exc.reason)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def _basic_auth(user: str, pw: str) -> str:
    import base64
    return "Basic " + base64.b64encode("{}:{}".format(user, pw).encode("utf-8")).decode("ascii")


def health() -> dict:
    try:
        import voice_notes as _vn
        clone_ready = _vn.is_configured()
    except Exception:
        clone_ready = False
    return {
        "component": "voice_call_agent",
        "enabled_flag": CALL_ENABLED,
        "twilio_sid_present": bool(TWILIO_SID),
        "twilio_token_present": bool(TWILIO_TOKEN),
        "twilio_from_present": bool(TWILIO_FROM),
        "public_base_present": bool(PUBLIC_BASE),
        "clone_voice_ready": clone_ready,
        "status": "ok" if is_configured() else "not_configured",
        "voice": "omar_clone" if clone_ready else "polly_fallback",
        "note": "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_CALLER_NUMBER, "
                "AIOS_PUBLIC_BASE_URL and AIOS_VOICE_CALL_ENABLED=true to arm the "
                "caller. Add ELEVENLABS_* to speak in Omar's cloned voice.",
    }
