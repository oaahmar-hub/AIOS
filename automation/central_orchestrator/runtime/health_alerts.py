#!/usr/bin/env python3
"""Health alerting: WhatsApp Omar the moment a department goes red.

A daemon thread checks deep health every ``AIOS_ALERT_INTERVAL_MINUTES``
(default 10). When overall status leaves ``healthy`` it sends ONE WhatsApp
alert to ``AIOS_ALERT_PHONE`` naming the failing components, then stays
silent about the same failure set (re-alerts only if the failure set
changes, or after ``AIOS_ALERT_REPEAT_HOURS``, default 6). When the system
recovers it sends one "back to green" message.

Gating: requires AIOS_HEALTH_ALERTS_ENABLED=true AND AIOS_ALERT_PHONE set.
The monitor thread must never take down the server - every cycle is fully
wrapped. State lives on the volume so restarts don't re-spam.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable

ALERTS_ENABLED = os.getenv("AIOS_HEALTH_ALERTS_ENABLED", "").strip().lower() in {"1", "true", "yes"}
ALERT_PHONE = "".join(ch for ch in os.getenv("AIOS_ALERT_PHONE", "") if ch.isdigit())
INTERVAL_MIN = max(2, int(os.getenv("AIOS_ALERT_INTERVAL_MINUTES", "10") or 10))
REPEAT_HOURS = max(1, int(os.getenv("AIOS_ALERT_REPEAT_HOURS", "6") or 6))

_STATE = Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "health_alert_state.json"
_started = False


def is_configured() -> bool:
    return bool(ALERTS_ENABLED and ALERT_PHONE)


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


def _failing(components: dict) -> list:
    return sorted(k for k, v in (components or {}).items() if v.get("ok") is False)


def check_once(get_health: Callable[[], dict], send: Callable[[str, str], tuple],
               now: float | None = None) -> str:
    """One monitoring cycle. Returns the action taken (for tests/logs)."""
    try:
        t = now if now is not None else time.time()
        health = get_health() or {}
        status = str(health.get("status") or "unknown")
        fails = _failing(health.get("components") or {})
        key = ",".join(fails) or status
        state = _load()
        was_red = bool(state.get("red"))
        last_key = state.get("key") or ""
        last_sent = float(state.get("sent_at") or 0)

        if status == "healthy" and not fails:
            if was_red:
                send(ALERT_PHONE, "AIOS: back to green. All departments healthy again.")
                _save({"red": False, "key": "", "sent_at": t})
                return "recovered_alert"
            return "green_quiet"

        # red / degraded
        fresh_failure = key != last_key
        repeat_due = (t - last_sent) > REPEAT_HOURS * 3600
        if fresh_failure or repeat_due or not was_red:
            names = ", ".join(fails) if fails else status
            send(ALERT_PHONE,
                 f"AIOS ALERT: system is {status}. Failing: {names}. "
                 f"Check {os.getenv('AIOS_PUBLIC_BASE_URL', '')}/api/health/deep")
            _save({"red": True, "key": key, "sent_at": t})
            return "alert_sent"
        return "red_quiet"
    except Exception:  # pragma: no cover - monitor must never raise
        return "error"


def start_monitor(get_health: Callable[[], dict], send: Callable[[str, str], tuple]) -> bool:
    """Start the daemon thread once. Returns True if started."""
    global _started
    if _started or not is_configured():
        return False
    _started = True

    def _loop() -> None:
        # first check shortly after boot, then on the interval
        time.sleep(60)
        while True:
            check_once(get_health, send)
            time.sleep(INTERVAL_MIN * 60)

    threading.Thread(target=_loop, name="aios-health-alerts", daemon=True).start()
    return True


def health() -> dict:
    return {
        "component": "health_alerts",
        "enabled": ALERTS_ENABLED,
        "phone_set": bool(ALERT_PHONE),
        "interval_minutes": INTERVAL_MIN,
        "status": "ok" if is_configured() else "not_configured",
    }
