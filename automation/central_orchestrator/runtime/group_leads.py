#!/usr/bin/env python3
"""Group-Lead Agent — turn WhatsApp-group chatter into ranked leads for Omar.

The safe half of the lead vision: it never auto-messages strangers. It watches
inbound messages (including group messages, which the reply path ignores),
detects genuine buyer/seller/rent requests, extracts the requirement, matches
it against real inventory, and records a ranked lead card Omar can act on.

Detection is intent + signal based (EN + AR). Matching reuses the same honest
inventory_retrieval used by the brain — so a lead card only cites real units.
Stored on the Railway volume; exposed via /api/leads/recent.

Pure stdlib. Never raises into the reply path.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

_VOL = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
if _VOL and Path(_VOL).is_dir():
    _DB = Path(_VOL) / "group_leads.sqlite3"
else:
    _DB = Path(os.getenv("AIOS_LEADS_DB", "/tmp/aios_group_leads.sqlite3"))

_lock = threading.Lock()
_ready = False

# A real request needs BOTH an ask verb and a property signal — this keeps
# small talk, jokes, and status posts out of the lead list.
_ASK = re.compile(
    r"\b(looking for|want|need|require|searching|any(one)?\s+(have|has)|who\s+has|available|"
    r"required|wanted|hunting|seeking|show me|send me|budget|ready buyer|serious buyer|client)\b|"
    r"مطلوب|ابحث|أبحث|بدور|بدي|محتاج|عندكم|في أحد|متوفر|زبون|عميل|جاهز",
    re.I,
)
_PROP = re.compile(
    r"\b(\d\s?br|\dbhk|studio|apartment|apt|villa|townhouse|penthouse|plot|office|flat|"
    r"bed(room)?s?|jvc|jvt|marina|downtown|business bay|dubai hills|palm|jbr|creek|"
    r"beachfront|arjan|damac|emaar|nakheel)\b|"
    r"شقة|فيلا|تاون|استوديو|غرفة|غرفتين|بنتهاوس|مكتب|أرض|عقار",
    re.I,
)
_INTENT = [
    (re.compile(r"\b(rent|rental|lease|to let|إيجار|للايجار|للإيجار)\b", re.I), "rent"),
    (re.compile(r"\b(sell|selling|for sale|بيع|للبيع)\b", re.I), "sell"),
    (re.compile(r"\b(buy|buyer|purchase|شراء|مشتري|للشراء)\b", re.I), "buy"),
]


def _conn() -> sqlite3.Connection:
    global _ready
    con = sqlite3.connect(_DB, timeout=5)
    if not _ready:
        con.execute(
            "CREATE TABLE IF NOT EXISTS leads ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  ts REAL, sender TEXT, source TEXT, intent TEXT,"
            "  text TEXT, matches INTEGER, cards TEXT)"
        )
        con.commit()
        _ready = True
    return con


def is_request(text: str) -> bool:
    t = str(text or "")
    return bool(_ASK.search(t) and _PROP.search(t))


def classify_intent(text: str) -> str:
    for rx, label in _INTENT:
        if rx.search(text or ""):
            return label
    return "inquiry"


def detect(sender: str, text: str, source: str = "group") -> dict:
    """If the message is a real request, match inventory and record a lead.

    Returns {is_lead, intent?, matches?, lead_id?}. Best-effort, never raises.
    """
    try:
        if not is_request(text):
            return {"is_lead": False}
        intent = classify_intent(text)
        cards = []
        try:
            import inventory_retrieval as _inv
            for r in _inv.search(text, max_results=3):
                cards.append(_inv._fmt_row(r))
        except Exception:
            cards = []
        rec = {
            "ts": time.time(), "sender": re.sub(r"\D", "", str(sender or "")) or "unknown",
            "source": source, "intent": intent, "text": str(text or "")[:600],
            "matches": len(cards), "cards": json.dumps(cards, ensure_ascii=False),
        }
        with _lock:
            con = _conn()
            cur = con.execute(
                "INSERT INTO leads (ts,sender,source,intent,text,matches,cards) VALUES (?,?,?,?,?,?,?)",
                (rec["ts"], rec["sender"], rec["source"], rec["intent"], rec["text"], rec["matches"], rec["cards"]),
            )
            con.commit(); lead_id = cur.lastrowid; con.close()
        return {"is_lead": True, "intent": intent, "matches": len(cards), "lead_id": lead_id, "cards": cards}
    except Exception:  # pragma: no cover
        return {"is_lead": False}


def recent(limit: int = 25) -> list[dict]:
    try:
        with _lock:
            con = _conn()
            rows = con.execute(
                "SELECT id,ts,sender,source,intent,text,matches,cards FROM leads ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            con.close()
    except Exception:
        return []
    out = []
    for r in rows:
        out.append({
            "id": r[0], "ts": r[1], "sender": r[2], "source": r[3], "intent": r[4],
            "text": r[5], "matches": r[6], "cards": json.loads(r[7] or "[]"),
        })
    return out


def stats() -> dict:
    try:
        with _lock:
            con = _conn()
            total = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            matched = con.execute("SELECT COUNT(*) FROM leads WHERE matches>0").fetchone()[0]
            con.close()
        return {"ok": True, "leads": int(total), "with_matches": int(matched)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    print(detect("971500", "Looking for a 2BR in JVC under 1.2m, serious buyer"))
    print(detect("971500", "good morning everyone"))
    print("STATS", stats())
