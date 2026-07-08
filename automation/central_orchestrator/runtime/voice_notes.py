#!/usr/bin/env python3
"""Voice replies for WhatsApp — same Omar tone, spoken.

Turns a reply into a voice note via ElevenLabs TTS and returns a URL that
Wasender can attach as an audio message. Fully gated:

- ``AIOS_VOICE_REPLY_ENABLED=true`` AND ``ELEVENLABS_API_KEY`` set -> active.
- Anything missing or any error -> ``synthesize`` returns None and text-only
  replies flow exactly as before. This module must never break the text path.

Voice identity: set ``ELEVENLABS_VOICE_ID`` to a voice cloned from Omar's own
voice notes (ElevenLabs instant voice clone) so the spoken tone matches the
chat persona. Until a key is configured this is a scaffold that reports its
own status through ``health()``.
"""

from __future__ import annotations

import json
import os
from typing import Optional
from urllib.request import Request, urlopen

VOICE_ENABLED = os.getenv("AIOS_VOICE_REPLY_ENABLED", "").strip().lower() in {"1", "true", "yes"}
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# eleven_multilingual_v2 handles Arabic + English in one voice.
_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()

# Voice notes should stay short and human; long content belongs in text.
MAX_VOICE_CHARS = 400


def is_configured() -> bool:
    return bool(VOICE_ENABLED and ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)


def synthesize(text: str) -> Optional[bytes]:
    """Return MP3 bytes for the reply, or None (disabled/too long/error)."""
    try:
        if not is_configured():
            return None
        clean = (text or "").strip()
        if not clean or len(clean) > MAX_VOICE_CHARS:
            return None
        body = json.dumps(
            {
                "text": clean,
                "model_id": _MODEL_ID,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35},
            }
        ).encode("utf-8")
        req = Request(
            _TTS_URL.format(voice_id=ELEVENLABS_VOICE_ID),
            data=body,
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            audio = resp.read()
        return audio if audio else None
    except Exception:  # pragma: no cover - defensive
        return None


def health() -> dict:
    return {
        "component": "voice_notes",
        "enabled_flag": VOICE_ENABLED,
        "api_key_present": bool(ELEVENLABS_API_KEY),
        "voice_id_present": bool(ELEVENLABS_VOICE_ID),
        "status": "ok" if is_configured() else "not_configured",
        "note": "Set AIOS_VOICE_REPLY_ENABLED, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID "
                "(voice cloned from Omar's voice notes) to activate.",
    }
