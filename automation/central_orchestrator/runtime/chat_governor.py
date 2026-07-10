#!/usr/bin/env python3
"""Chat discipline for the WhatsApp auto-reply — when NOT to talk.

Four guards, all deterministic, pure stdlib, SQLite on the Railway volume.
Every function fails OPEN for reads and CLOSED for replies where noted, and
none may ever raise into the webhook path.

1. **Human takeover** — the moment Omar himself messages a contact (a
   ``from_me`` event), the bot goes SILENT for that contact for
   ``AIOS_TAKEOVER_COOLDOWN_MIN`` minutes (default 120). Two people must never
   type from the same number. Omar's own turn is also recorded into
   conversation memory as context.
2. **Freshness** — events older than ``AIOS_MAX_EVENT_AGE_MIN`` minutes
   (default 10) are backlog/history-sync replays, not live customers. They are
   never answered, never captured as leads.
3. **Throttle** — per contact, at most one auto-reply every
   ``AIOS_REPLY_MIN_GAP_SEC`` seconds (default 25) and at most
   ``AIOS_REPLY_HOURLY_CAP`` auto-replies per rolling hour (default 6).
   A human doesn't machine-gun answers; neither do we.
4. **Substance** — if the message needs knowledge we don't have (no inventory
   match, no clear intent), and ``AIOS_REPLY_WHEN_CLUELESS`` is not "true",
   the bot stays quiet instead of sending a confident-sounding nothing.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

_VOL = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
_PHASE4 = os.getenv("AIOS_PHASE4_DB_PATH", "").strip()
if _VOL:
    _DB_PATH = Path(_VOL) / "chat_governor.sqlite3"
elif _PHASE4:
    _DB_PATH = Path(_PHASE4).parent / "chat_governor.sqlite3"
else:
    _DB_PATH = Path(os.getenv("AIOS_GOVERNOR_DB", "/tmp/aios_chat_governor.sqlite3"))

TAKEOVER_COOLDOWN_MIN = int(os.getenv("AIOS_TAKEOVER_COOLDOWN_MIN", "120") or 120)
MAX_EVENT_AGE_MIN = int(os.getenv("AIOS_MAX_EVENT_AGE_MIN", "10") or 10)
REPLY_MIN_GAP_SEC = int(os.getenv("AIOS_REPLY_MIN_GAP_SEC", "25") or 25)
REPLY_HOURLY_CAP = int(os.getenv("AIOS_REPLY_HOURLY_CAP", "6") or 6)
REPLY_WHEN_CLUELESS = os.getenv("AIOS_REPLY_WHEN_CLUELESS", "").strip().lower() in {"1", "true", "yes"}


def _digits(phone: str) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH, timeout=5)
    con.execute(
        "create table if not exists takeover (contact text primary key, omar_until real not null)"
    )
    con.execute(
        "create table if not exists replies (contact text not null, sent_at real not null)"
    )
    con.execute("create index if not exists idx_replies on replies(contact, sent_at)")
    return con


# ---------------------------------------------------------------------------
# 1. Human takeover
# ---------------------------------------------------------------------------

def record_omar_message(contact: str) -> None:
    """Omar messaged this contact himself -> bot silent for the cooldown."""
    try:
        c = _digits(contact)
        if not c:
            return
        until = time.time() + TAKEOVER_COOLDOWN_MIN * 60
        con = _conn()
        try:
            con.execute(
                "insert into takeover(contact, omar_until) values(?, ?) "
                "on conflict(contact) do update set omar_until = excluded.omar_until",
                (c, until),
            )
            con.commit()
        finally:
            con.close()
    except Exception:  # pragma: no cover - defensive
        pass


def omar_in_control(contact: str) -> bool:
    """True while Omar's manual-takeover window for this contact is open."""
    try:
        c = _digits(contact)
        if not c:
            return False
        con = _conn()
        try:
            row = con.execute("select omar_until from takeover where contact = ?", (c,)).fetchone()
        finally:
            con.close()
        return bool(row and float(row[0]) > time.time())
    except Exception:  # pragma: no cover - defensive
        return False


def release_control(contact: str) -> None:
    """Manually hand the contact back to the bot (used by ops endpoints)."""
    try:
        c = _digits(contact)
        con = _conn()
        try:
            con.execute("delete from takeover where contact = ?", (c,))
            con.commit()
        finally:
            con.close()
    except Exception:  # pragma: no cover - defensive
        pass


# ---------------------------------------------------------------------------
# 2. Freshness — backlog/history replays are not live customers
# ---------------------------------------------------------------------------

def event_age_seconds(timestamp: object) -> float | None:
    """Age of the event in seconds, or None when unparseable."""
    try:
        raw = str(timestamp or "").strip()
        if not raw:
            return None
        if re.fullmatch(r"\d{9,13}", raw):
            ts = float(raw)
            if ts > 1e12:  # milliseconds
                ts /= 1000.0
            return max(0.0, time.time() - ts)
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - dt.timestamp())
    except Exception:
        return None


def is_stale(timestamp: object, max_age_min: int | None = None) -> bool:
    """True when the event is older than the freshness window.

    Unparseable/missing timestamps are treated as FRESH (the gateway stamps
    now() when the provider omits one), so a provider quirk can't mute the bot.
    """
    age = event_age_seconds(timestamp)
    if age is None:
        return False
    limit = (max_age_min if max_age_min is not None else MAX_EVENT_AGE_MIN) * 60
    return age > limit


# ---------------------------------------------------------------------------
# 3. Per-contact reply throttle
# ---------------------------------------------------------------------------

def allow_reply(contact: str) -> tuple[bool, str]:
    """Check the per-contact gap + hourly cap. Returns (ok, reason)."""
    try:
        c = _digits(contact)
        if not c:
            return True, "no_contact"
        now = time.time()
        con = _conn()
        try:
            con.execute("delete from replies where sent_at < ?", (now - 3600,))
            last = con.execute(
                "select max(sent_at) from replies where contact = ?", (c,)
            ).fetchone()[0]
            count = con.execute(
                "select count(*) from replies where contact = ?", (c,)
            ).fetchone()[0]
            con.commit()
        finally:
            con.close()
        if last is not None and now - float(last) < REPLY_MIN_GAP_SEC:
            return False, f"gap<{REPLY_MIN_GAP_SEC}s"
        if int(count) >= REPLY_HOURLY_CAP:
            return False, f"hourly_cap:{REPLY_HOURLY_CAP}"
        return True, "ok"
    except Exception:  # pragma: no cover - defensive
        return True, "governor_error_open"


def note_reply(contact: str) -> None:
    """Record that an auto-reply was just sent to this contact."""
    try:
        c = _digits(contact)
        if not c:
            return
        con = _conn()
        try:
            con.execute("insert into replies(contact, sent_at) values(?, ?)", (c, time.time()))
            con.commit()
        finally:
            con.close()
    except Exception:  # pragma: no cover - defensive
        pass


# ---------------------------------------------------------------------------
# 4. Substance — greetings/real questions get answered; clueless gets silence
# ---------------------------------------------------------------------------

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|salam|salaam|slm|hala|ahlan|good (morning|afternoon|evening)|"
    r"مرحبا|أهلا|اهلا|هلا|السلام عليكم|سلام|صباح الخير|مساء الخير)\b[\s!,.؟?]*$",
    re.IGNORECASE,
)


def should_stay_silent(text: str, inventory_count: int) -> tuple[bool, str]:
    """Decide whether the honest move is to say nothing.

    Silent only when ALL hold: no inventory matched, the message is not a
    greeting, not a question, and has no substance we can act on — i.e. the
    reply would be a confident-sounding nothing. Configurable escape hatch:
    AIOS_REPLY_WHEN_CLUELESS=true restores always-reply.
    """
    try:
        if REPLY_WHEN_CLUELESS:
            return False, "clueless_reply_enabled"
        t = (text or "").strip()
        if not t:
            return True, "empty"
        if inventory_count > 0:
            return False, "has_knowledge"
        if _GREETING_RE.match(t):
            return False, "greeting"
        if "?" in t or "؟" in t:
            return False, "question"
        # Real-estate substance words -> the brain can at least take the brief.
        if re.search(
            r"\b(buy|sell|rent|lease|villa|apartment|studio|unit|plot|price|budget|"
            r"bedroom|bhk|br|sqft|sqm|payment|handover|offer|viewing|listing)\b"
            r"|شقة|فيلا|ارض|أرض|ايجار|إيجار|بيع|شراء|سعر|ميزانية|غرفة|معاينة|عرض",
            t, re.IGNORECASE,
        ):
            return False, "re_intent"
        if len(t) >= 80:
            return False, "long_message"
        return True, "no_knowledge_no_intent"
    except Exception:  # pragma: no cover - defensive
        return False, "governor_error_open"


def health() -> dict:
    try:
        con = _conn()
        try:
            active = con.execute(
                "select count(*) from takeover where omar_until > ?", (time.time(),)
            ).fetchone()[0]
        finally:
            con.close()
        return {
            "component": "chat_governor",
            "ok": True,
            "takeover_active_contacts": int(active),
            "cooldown_min": TAKEOVER_COOLDOWN_MIN,
            "max_event_age_min": MAX_EVENT_AGE_MIN,
            "reply_min_gap_sec": REPLY_MIN_GAP_SEC,
            "reply_hourly_cap": REPLY_HOURLY_CAP,
            "db": str(_DB_PATH),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"component": "chat_governor", "ok": False, "error": str(exc)}
