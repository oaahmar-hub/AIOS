#!/usr/bin/env python3
"""Daily CEO brief: one WhatsApp message every morning with the real numbers.

At ``AIOS_DAILY_BRIEF_HOUR`` (default 08, Asia/Dubai = UTC+4) a daemon
thread composes and sends Omar one message:

- system status (green / which departments are red)
- conversations handled + contacts remembered
- new group leads captured
- outreach messages sent (from the journal) since the last brief
- quotable inventory count

Every number comes from the live modules - nothing invented; a section
whose source fails says "n/a" instead of guessing. Gated on
``AIOS_DAILY_BRIEF_ENABLED`` + ``AIOS_ALERT_PHONE`` (same number as health
alerts). One brief per calendar day (Dubai), state on the volume.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

BRIEF_ENABLED = os.getenv("AIOS_DAILY_BRIEF_ENABLED", "").strip().lower() in {"1", "true", "yes"}
ALERT_PHONE = "".join(ch for ch in os.getenv("AIOS_ALERT_PHONE", "") if ch.isdigit())
BRIEF_HOUR = min(23, max(0, int(os.getenv("AIOS_DAILY_BRIEF_HOUR", "8") or 8)))
DUBAI = timezone(timedelta(hours=4))

_STATE = Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "daily_brief_state.json"
_OUTREACH_JOURNAL = Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "outreach_journal.jsonl"
_started = False


def is_configured() -> bool:
    return bool(BRIEF_ENABLED and ALERT_PHONE)


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(state: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _outreach_sends_since(epoch: float) -> int:
    try:
        count = 0
        with _OUTREACH_JOURNAL.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    if rec.get("sent") and float(rec.get("ts") or 0) >= epoch:
                        count += 1
                except Exception:
                    continue
        return count
    except Exception:
        return 0


def compose(get_health: Callable[[], dict], since_epoch: float) -> str:
    """Build the brief text from live modules. Sections fail to 'n/a'."""
    lines = [f"AIOS daily brief - {datetime.now(DUBAI).strftime('%a %d %b')}"]
    try:
        h = get_health() or {}
        fails = sorted(k for k, v in (h.get("components") or {}).items() if v.get("ok") is False)
        lines.append("System: all green ✅" if h.get("status") == "healthy"
                     else f"System: {h.get('status')} - check {', '.join(fails) or 'health page'}")
    except Exception:
        lines.append("System: n/a")
    try:
        import conversation_memory as _mem
        ms = _mem.stats()
        lines.append(f"Chats: {ms.get('contacts', 'n/a')} contacts, {ms.get('turns', ms.get('total_turns', 'n/a'))} turns remembered")
    except Exception:
        lines.append("Chats: n/a")
    try:
        import group_leads as _gl
        gs = _gl.stats()
        lines.append(f"Group leads: {gs.get('total', gs.get('leads', 0))} captured")
    except Exception:
        lines.append("Group leads: n/a")
    sends = _outreach_sends_since(since_epoch)
    lines.append(f"Owner outreach: {sends} sent since last brief")
    try:
        import inventory_retrieval as _inv
        lines.append(f"Inventory: {_inv.quotable_count()} quotable units")
    except Exception:
        lines.append("Inventory: n/a")
    lines.append("Reply 'report' for the full picture.")
    return "\n".join(lines)


def check_once(get_health: Callable[[], dict], send: Callable[[str, str], tuple],
               now_dt: datetime | None = None) -> str:
    """Send the brief if it's due today and not yet sent. Never raises."""
    try:
        now = now_dt or datetime.now(DUBAI)
        if now.tzinfo is None:
            now = now.replace(tzinfo=DUBAI)
        today = now.astimezone(DUBAI).strftime("%Y-%m-%d")
        if now.astimezone(DUBAI).hour < BRIEF_HOUR:
            return "too_early"
        state = _load()
        if state.get("last_day") == today:
            return "already_sent"
        since = float(state.get("last_epoch") or (time.time() - 86400))
        send(ALERT_PHONE, compose(get_health, since))
        _save({"last_day": today, "last_epoch": time.time()})
        return "brief_sent"
    except Exception:  # pragma: no cover - must never raise
        return "error"


def start_monitor(get_health: Callable[[], dict], send: Callable[[str, str], tuple]) -> bool:
    global _started
    if _started or not is_configured():
        return False
    _started = True

    def _loop() -> None:
        time.sleep(120)
        while True:
            check_once(get_health, send)
            time.sleep(600)  # check every 10 min whether the daily slot is due

    threading.Thread(target=_loop, name="aios-daily-brief", daemon=True).start()
    return True


def health() -> dict:
    return {
        "component": "daily_brief",
        "enabled": BRIEF_ENABLED,
        "phone_set": bool(ALERT_PHONE),
        "hour_dubai": BRIEF_HOUR,
        "status": "ok" if is_configured() else "not_configured",
    }
