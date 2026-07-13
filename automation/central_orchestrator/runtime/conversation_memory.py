#!/usr/bin/env python3
"""Conversation memory for the WhatsApp brain.

The runtime previously passed an empty history to the brain on every message,
so it forgot the conversation between turns. This gives each contact a durable
rolling memory of their last N turns, stored on the Railway persistent volume
(survives deploys) with a local fallback for dev.

Pure stdlib (sqlite3). Thread-safe. Never raises into the reply path — on any
failure it degrades to "no history" so replies still flow.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path

# Persist on the Railway volume when present, else the phase4 db dir, else /tmp.
_VOL = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
_PHASE4 = os.getenv("AIOS_PHASE4_DB_PATH", "").strip()
if _VOL and Path(_VOL).is_dir():
    _DB_PATH = Path(_VOL) / "conversation_memory.sqlite3"
elif _PHASE4:
    _DB_PATH = Path(_PHASE4).parent / "conversation_memory.sqlite3"
else:
    _DB_PATH = Path(os.getenv("AIOS_MEMORY_DB", "/tmp/aios_conversation_memory.sqlite3"))

MAX_TURNS = int(os.getenv("AIOS_MEMORY_TURNS", "12"))   # turns kept per contact in the prompt
_RETAIN = int(os.getenv("AIOS_MEMORY_RETAIN", "60"))    # rows retained per contact on disk

_lock = threading.Lock()
_ready = False


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def _conn() -> sqlite3.Connection:
    global _ready
    con = sqlite3.connect(_DB_PATH, timeout=5)
    if not _ready:
        con.execute(
            "CREATE TABLE IF NOT EXISTS turns ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  contact TEXT NOT NULL,"
            "  role TEXT NOT NULL,"
            "  text TEXT NOT NULL,"
            "  ts REAL NOT NULL)"
        )
        con.execute("CREATE INDEX IF NOT EXISTS ix_contact ON turns(contact, id)")
        con.commit()
        _ready = True
    return con


def record(contact: str, role: str, text: str) -> None:
    """Append one turn (role = 'user' | 'assistant'). Best-effort, never raises."""
    c = _digits(contact)
    t = str(text or "").strip()
    if not c or not t or role not in {"user", "assistant"}:
        return
    try:
        with _lock:
            con = _conn()
            con.execute(
                "INSERT INTO turns (contact, role, text, ts) VALUES (?,?,?,?)",
                (c, role, t[:2000], time.time()),
            )
            # Trim to the last _RETAIN rows for this contact.
            con.execute(
                "DELETE FROM turns WHERE contact=? AND id NOT IN "
                "(SELECT id FROM turns WHERE contact=? ORDER BY id DESC LIMIT ?)",
                (c, c, _RETAIN),
            )
            con.commit()
            con.close()
    except Exception:
        return


def history(contact: str, max_turns: int = MAX_TURNS) -> str:
    """Return the last max_turns turns as a plain transcript for the LLM prompt."""
    c = _digits(contact)
    if not c:
        return ""
    try:
        with _lock:
            con = _conn()
            rows = con.execute(
                "SELECT role, text FROM turns WHERE contact=? ORDER BY id DESC LIMIT ?",
                (c, max_turns),
            ).fetchall()
            con.close()
    except Exception:
        return ""
    if not rows:
        return ""
    rows = list(reversed(rows))
    lines = []
    for role, text in rows:
        who = "Customer" if role == "user" else "You (Omar)"
        lines.append(f"{who}: {text}")
    return "\n".join(lines)


def stats() -> dict:
    """Health snapshot: distinct contacts + total turns remembered."""
    try:
        with _lock:
            con = _conn()
            contacts = con.execute("SELECT COUNT(DISTINCT contact) FROM turns").fetchone()[0]
            total = con.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
            con.close()
        return {"ok": True, "contacts": int(contacts), "turns": int(total), "db": str(_DB_PATH)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "db": str(_DB_PATH)}


if __name__ == "__main__":
    record("971500000001", "user", "hi, 1BR in JVC?")
    record("971500000001", "assistant", "Luma22 unit 609 — want details?")
    record("971500000001", "user", "yes please")
    print("HISTORY:\n" + history("971500000001"))
    print("STATS:", stats())
