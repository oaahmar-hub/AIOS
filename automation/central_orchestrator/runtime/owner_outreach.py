#!/usr/bin/env python3
"""Owner Outreach desk: unit -> owner contact -> drafted direct offer.

Closes the last gap in Omar's pipeline (search agents -> portal matcher ->
owner details -> direct offer): given a target (area/building/project/unit
text), find inventory units whose owner contact is on file in the RESTRICTED
store, and produce a ready-to-approve outreach queue with a personal draft
message per owner.

Privacy + control contract:
- Owner mobiles come from ``restricted_owner_contact`` and are MASKED in
  every queue response (last 3 digits only). The full number is resolved
  only at send time, server-side, from the ``restricted_ref``.
- NOTHING is ever sent automatically. ``send()`` fires one message to one
  owner and must be called explicitly (the API endpoint additionally
  requires the admin secret). Every send is rate-limited via chat_governor
  and journaled to the volume.
- Drafts are honest: Omar introducing himself about that specific unit.
  No fake buyer claims, no pressure lines.

Pure stdlib; read paths never raise (errors come back inside the payload).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

_RUNTIME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _RUNTIME_DIR.parents[2]
DB_PATH = _REPO_ROOT / "KnowledgeBase" / "resolver" / "unit_resolver_database.resolver"

SEND_JOURNAL = Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "outreach_journal.jsonl"

MAX_QUEUE = 50


def _mask(mobile: str) -> str:
    digits = "".join(ch for ch in str(mobile or "") if ch.isdigit())
    return f"***{digits[-3:]}" if len(digits) >= 3 else "***"


def _normalize_mobile(mobile: str) -> str:
    """UAE-normalize: '0501234567'/'501234567' -> '971501234567'."""
    d = "".join(ch for ch in str(mobile or "") if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("971"):
        return d
    if d.startswith("05") and len(d) == 10:
        return "971" + d[1:]
    if d.startswith("5") and len(d) == 9:
        return "971" + d
    return d


def draft_message(owner_name: str, area: str, building: str, unit: str, lang: str = "en") -> str:
    """Honest personal opener from Omar about this specific unit."""
    where = " ".join(x for x in (building, area) if x).strip() or "your property"
    unit_part = f" unit {unit}" if unit else ""
    name_part = f" {owner_name.split()[0].title()}" if owner_name else ""
    if lang == "ar":
        return (
            f"مرحباً{name_part}، معك عمر من HSH العقارية في دبي. "
            f"عندنا اهتمام حقيقي بالوحدات في {where}{unit_part}. "
            "إذا تفكر بالبيع أو التأجير يسعدني أتواصل معك بالتفاصيل. "
            "وإذا ما تحب رسائل من هذا النوع قلي وما أزعجك مرة ثانية."
        )
    return (
        f"Hello{name_part}, this is Omar from HSH Real Estate in Dubai. "
        f"We're seeing genuine interest in units at {where}{unit_part}. "
        "If you'd ever consider selling or renting it out, I'd be glad to share what "
        "it could achieve. If you'd rather not receive messages like this, just say so "
        "and I won't contact you again."
    )


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def queue(query: str, limit: int = 20, lang: str = "en") -> dict:
    """Owner-outreach queue for units matching ``query`` with contact on file."""
    try:
        q = str(query or "").strip().lower()
        if not q:
            return {"ok": False, "error": "empty query"}
        limit = max(1, min(int(limit or 20), MAX_QUEUE))
        tokens = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 2]
        if not tokens:
            return {"ok": False, "error": "query too short"}
        con = _connect()
        try:
            like = " AND ".join(
                "(lower(coalesce(area,'')||' '||coalesce(project,'')||' '||"
                "coalesce(building,'')||' '||coalesce(unit,'')) LIKE ?)"
                for _ in tokens
            )
            rows = con.execute(
                f"""
                SELECT r.resolver_record_id, r.area, r.project, r.building, r.unit,
                       r.bedrooms, c.restricted_ref, c.owner_name, c.mobile
                FROM resolver_records r
                JOIN restricted_owner_contact c
                  ON c.resolver_record_id = r.resolver_record_id
                WHERE r.owner_contact_available = 'YES' AND {like}
                LIMIT ?
                """,
                [f"%{t}%" for t in tokens] + [limit * 3],
            ).fetchall()
        finally:
            con.close()
        seen: set = set()
        out = []
        for r in rows:
            mob = _normalize_mobile(r["mobile"])
            if not mob or mob in seen:
                continue
            seen.add(mob)
            out.append({
                "restricted_ref": r["restricted_ref"],
                "owner_name": (r["owner_name"] or "").title(),
                "mobile_masked": _mask(mob),
                "area": r["area"] or "",
                "building": r["building"] or "",
                "unit": r["unit"] or "",
                "bedrooms": r["bedrooms"] or "",
                "draft": draft_message(r["owner_name"] or "", r["area"] or "",
                                       r["building"] or "", r["unit"] or "", lang),
            })
            if len(out) >= limit:
                break
        return {
            "ok": True,
            "department": "owner_outreach",
            "query": query,
            "matches": len(out),
            "queue": out,
            "note": "Mobiles are masked. Nothing is sent automatically - approve an "
                    "entry by calling POST /api/outreach/send with its restricted_ref.",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def resolve_mobile(restricted_ref: str) -> Optional[str]:
    """Full mobile for a restricted_ref - server-side use only."""
    try:
        con = _connect()
        try:
            row = con.execute(
                "SELECT mobile FROM restricted_owner_contact WHERE restricted_ref = ?",
                [str(restricted_ref or "").strip()],
            ).fetchone()
        finally:
            con.close()
        return _normalize_mobile(row["mobile"]) if row and row["mobile"] else None
    except Exception:
        return None


def journal_send(restricted_ref: str, mobile: str, message: str, sent: bool, detail: str) -> None:
    try:
        SEND_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with SEND_JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": time.time(), "restricted_ref": restricted_ref,
                "mobile_masked": _mask(mobile), "sent": sent, "detail": detail,
                "chars": len(message or ""),
            }) + "\n")
    except Exception:
        pass


def health() -> dict:
    try:
        con = _connect()
        try:
            n = con.execute("SELECT count(*) FROM restricted_owner_contact").fetchone()[0]
        finally:
            con.close()
        return {"component": "owner_outreach", "restricted_contacts": int(n),
                "status": "ok" if n else "no_contacts"}
    except Exception as exc:
        return {"component": "owner_outreach", "status": f"error:{exc}"}
