#!/usr/bin/env python3
"""Renewal-Lead Agent — turn expiring Ejari tenancies into warm leads.

Dubai registers every tenancy (Ejari) with a contract END date. A tenancy
ending soon = a live opportunity: the owner may want to re-let (at today's
higher market), or the tenant may be moving. This agent:

  1. indexes rent contracts (area / building / unit / annual rent / end date),
  2. finds the ones expiring within N days,
  3. joins each to the REAL owner phone (owner_lookup) so it's actionable,
  4. drafts an outreach message with live market context (market_index).

No competitor's WhatsApp bot does timed renewal outreach. Rent-contract data
comes from DLD/Ejari open data via the same access as transactions; until then
this runs on any ingested contracts and its logic is fully tested.

Pure stdlib. PII (owner phone) only attached when reveal=True (admin path).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_DB = Path(os.getenv("AIOS_RENEWALS_DB_PATH",
                     str(Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "ejari_contracts.sqlite")))


def _con() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS contracts(
        area TEXT, building TEXT, unit TEXT, rooms TEXT,
        annual_rent REAL, start_date TEXT, end_date TEXT, source TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_end ON contracts(end_date)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_c_bld ON contracts(building)")
    return con


def _norm_date(s: str) -> str:
    """Normalise common DLD date formats to YYYY-MM-DD; '' if unparseable."""
    s = str(s or "").strip()
    if not s:
        return ""
    s = s.split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return s if len(s) == 10 and s[4] == "-" else ""


def ingest_contracts(rows: list, source: str = "ejari") -> int:
    """rows: dicts with any of area/building/unit/rooms/annual_rent/start_date/end_date."""
    con = _con()
    try:
        buf = []
        for r in rows:
            end = _norm_date(r.get("end_date"))
            if not end:
                continue
            try:
                rent = float(str(r.get("annual_rent") or 0).replace(",", "")) or 0.0
            except Exception:
                rent = 0.0
            buf.append((
                str(r.get("area", "")).strip(), str(r.get("building", "")).strip(),
                str(r.get("unit", "")).strip(), str(r.get("rooms", "")).strip(),
                rent, _norm_date(r.get("start_date")), end, source,
            ))
        con.executemany(
            "INSERT INTO contracts(area,building,unit,rooms,annual_rent,start_date,end_date,source)"
            " VALUES(?,?,?,?,?,?,?,?)", buf)
        con.commit()
        return len(buf)
    finally:
        con.close()


def expiring(within_days: int = 60, ref_date: str = "", limit: int = 200) -> list:
    """Contracts ending between today and today+within_days (soonest first)."""
    try:
        today = datetime.strptime(ref_date, "%Y-%m-%d") if ref_date else datetime.utcnow()
    except Exception:
        today = datetime.utcnow()
    lo = today.strftime("%Y-%m-%d")
    hi = (today + timedelta(days=within_days)).strftime("%Y-%m-%d")
    con = _con()
    try:
        rows = con.execute(
            "SELECT area,building,unit,rooms,annual_rent,end_date FROM contracts "
            "WHERE end_date >= ? AND end_date <= ? ORDER BY end_date ASC LIMIT ?",
            (lo, hi, max(1, min(limit, 1000)))).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def _draft(c: dict, lang: str = "en") -> str:
    bld = c.get("building", "") or c.get("area", "")
    unit = c.get("unit", "")
    end = c.get("end_date", "")
    try:
        import market_index as _mi
        mkt = _mi.brief(lang)
    except Exception:
        mkt = ""
    if lang == "ar":
        base = (f"مرحباً، عقد إيجار وحدتك {('('+unit+') ' ) if unit else ''}في {bld} ينتهي بتاريخ {end}. "
                f"نقدر نعيد تأجيرها بسعر السوق الحالي.")
        return base + (f" {mkt}" if mkt else "")
    base = (f"Hi — the tenancy on your unit {('('+unit+') ') if unit else ''}in {bld} ends {end}. "
            f"We can re-let it at today's market rate.")
    return base + (f" {mkt}" if mkt else "")


def build_leads(within_days: int = 60, reveal: bool = False, lang: str = "en",
                ref_date: str = "", limit: int = 100) -> dict:
    """Expiring tenancies joined to the real owner (phone if reveal) + a draft."""
    items = expiring(within_days=within_days, ref_date=ref_date, limit=limit)
    leads = []
    try:
        import owner_lookup as _ol
    except Exception:
        _ol = None
    for c in items:
        owner = {}
        if _ol:
            found = _ol.lookup(building=c.get("building", ""), unit=c.get("unit", ""),
                               reveal=reveal, limit=1)
            if found.get("ok") and found.get("owners"):
                o = found["owners"][0]
                owner = {"name": o.get("name", ""), "phone": o.get("phone", "")}
        leads.append({
            "area": c.get("area", ""), "building": c.get("building", ""),
            "unit": c.get("unit", ""), "end_date": c.get("end_date", ""),
            "annual_rent": c.get("annual_rent", 0), "owner": owner,
            "draft": _draft(c, lang),
        })
    return {"ok": True, "within_days": within_days, "count": len(leads), "leads": leads}


def health() -> dict:
    try:
        con = _con()
        try:
            n = con.execute("SELECT count(*) FROM contracts").fetchone()[0]
        finally:
            con.close()
        return {"component": "renewal_agent", "status": "ok" if n else "awaiting_ejari_data",
                "contracts": int(n)}
    except Exception as exc:
        return {"component": "renewal_agent", "status": f"error:{exc}"}
