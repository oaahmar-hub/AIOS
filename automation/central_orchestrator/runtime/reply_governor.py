#!/usr/bin/env python3
"""Reply discipline: WHEN the WhatsApp brain may speak at all.

Born from a real incident: the bot replied to backlog messages as if fresh,
kept talking while Omar was personally handling the chat, and machine-gunned
"ok ok" replies. These are hard gates, checked BEFORE any LLM call:

1. **Staleness** — a message older than ``AIOS_REPLY_MAX_AGE_SECONDS``
   (default 180s) is history, not a conversation. Never answer it, never
   CRM-capture it. Kills webhook backlog replays and old-chat resyncs.
2. **Human override** — the moment Omar himself sends anything in a chat
   (a ``from_me`` event), the bot goes silent with that contact for
   ``AIOS_HUMAN_OVERRIDE_MINUTES`` (default 60). Omar typing = Omar's chat.
3. **Kill-switch** — Omar sends ``#off`` in any chat -> bot muted for that
   contact until he sends ``#on``. Works from his own phone, instantly.
4. **Rate limit** — per contact: minimum ``AIOS_REPLY_MIN_GAP_SECONDS``
   (default 25s) between replies and at most ``AIOS_REPLY_MAX_PER_HOUR``
   (default 6). A human doesn't answer 15 times a minute.

State is one JSON file on the persistent volume; every function is pure
stdlib and never raises into the reply path (fail-open on errors EXCEPT the
mute list, which fails-closed to respect an explicit #off).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_AGE_SECONDS = int(os.getenv("AIOS_REPLY_MAX_AGE_SECONDS", "180") or 180)
OVERRIDE_MINUTES = int(os.getenv("AIOS_HUMAN_OVERRIDE_MINUTES", "60") or 60)
MIN_GAP_SECONDS = int(os.getenv("AIOS_REPLY_MIN_GAP_SECONDS", "25") or 25)
MAX_PER_HOUR = int(os.getenv("AIOS_REPLY_MAX_PER_HOUR", "6") or 6)

MUTE_CMD = "#off"
UNMUTE_CMD = "#on"


def _state_path() -> Path:
    db = os.getenv("AIOS_PHASE4_DB_PATH", "").strip()
    base = Path(db).parent if db else Path("/tmp")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path("/tmp")
    return base / "reply_governor_state.json"


def _load() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(state: dict) -> None:
    try:
        tmp = _state_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(_state_path())
    except Exception:
        pass


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


# ---------------------------------------------------------------------------
# 1. Staleness
# ---------------------------------------------------------------------------

def is_stale(event_timestamp: str, now: float | None = None) -> bool:
    """True when the message is too old to be a live conversation turn."""
    try:
        ts = str(event_timestamp or "").strip()
        if not ts:
            return False  # no timestamp -> assume live (fail-open)
        if ts.isdigit():
            event_epoch = float(ts)
        else:
            event_epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        age = (now if now is not None else time.time()) - event_epoch
        return age > MAX_AGE_SECONDS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 2 + 3. Human override and kill-switch (fed by from_me events)
# ---------------------------------------------------------------------------

def note_human_message(contact: str, text: str = "", now: float | None = None) -> str:
    """Record that Omar himself messaged this contact. Returns the action taken.

    ``#off`` mutes the contact, ``#on`` unmutes; anything else refreshes the
    human-override window.
    """
    try:
        c = _digits(contact)
        if not c:
            return "no_contact"
        t = (text or "").strip().lower()
        state = _load()
        if t == MUTE_CMD:
            state.setdefault("muted", {})[c] = True
            _save(state)
            return "muted"
        if t == UNMUTE_CMD:
            state.setdefault("muted", {}).pop(c, None)
            state.setdefault("human_seen", {}).pop(c, None)
            _save(state)
            return "unmuted"
        state.setdefault("human_seen", {})[c] = now if now is not None else time.time()
        _save(state)
        return "override_started"
    except Exception:
        return "error"


def human_active(contact: str, now: float | None = None) -> bool:
    """True while Omar's own last message to this contact is inside the window."""
    try:
        c = _digits(contact)
        state = _load()
        if state.get("muted", {}).get(c):
            return True  # muted counts as permanently human-controlled
        seen = state.get("human_seen", {}).get(c)
        if not seen:
            return False
        return ((now if now is not None else time.time()) - float(seen)) < OVERRIDE_MINUTES * 60
    except Exception:
        return True  # fail-closed: when unsure, stay silent


def is_muted(contact: str) -> bool:
    try:
        return bool(_load().get("muted", {}).get(_digits(contact)))
    except Exception:
        return True


# ---------------------------------------------------------------------------
# 4. Per-contact rate limit
# ---------------------------------------------------------------------------

def allow_reply(contact: str, now: float | None = None) -> tuple[bool, str]:
    """Check-and-record one outbound reply for this contact."""
    try:
        c = _digits(contact)
        if not c:
            return True, "no_contact"
        t = now if now is not None else time.time()
        state = _load()
        log = [x for x in state.get("reply_log", {}).get(c, []) if t - float(x) < 3600]
        if log and t - float(log[-1]) < MIN_GAP_SECONDS:
            return False, f"min_gap_{MIN_GAP_SECONDS}s"
        if len(log) >= MAX_PER_HOUR:
            return False, f"max_{MAX_PER_HOUR}_per_hour"
        log.append(t)
        state.setdefault("reply_log", {})[c] = log
        _save(state)
        return True, "ok"
    except Exception:
        return True, "error_fail_open"


def health() -> dict:
    state = _load()
    return {
        "component": "reply_governor",
        "state_file": str(_state_path()),
        "muted_contacts": len(state.get("muted", {})),
        "override_active": len(state.get("human_seen", {})),
        "limits": {
            "max_age_seconds": MAX_AGE_SECONDS,
            "override_minutes": OVERRIDE_MINUTES,
            "min_gap_seconds": MIN_GAP_SECONDS,
            "max_per_hour": MAX_PER_HOUR,
        },
        "status": "ok",
    }
