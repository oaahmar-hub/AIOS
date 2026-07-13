#!/usr/bin/env python3
"""Dubai Pulse (DLD open data) connector — all-Dubai units + REAL prices.

Pulls the official DLD open datasets (sale transactions, rent-price index,
lookups) via Dubai Pulse's OAuth + CKAN datastore API, and ingests them into a
local prices/units index. This is the legitimate, all-of-Dubai source: every
registered sale — building, area, unit, price, size, rooms, date — in one feed,
so the unit finder and comparable-price valuations cover the whole city instead
of one private xlsx at a time.

NOTE ON PII: the OPEN transactions dataset has NO owner names/phones (those stay
in Omar's private DLD xlsx -> owner_lookup). This feeds the UNIT + PRICE side.

Gated on DUBAI_PULSE_API_KEY / DUBAI_PULSE_API_SECRET — inert until set, so
importing/deploying this never changes behaviour. Pure stdlib.

Access (free): register at dubaipulse.gov.ae -> grant the DLD 'dld_transactions'
dataset -> you receive API Key + API Secret in two emails -> set them as Railway
env vars. Token endpoint + CKAN paths are overridable via env for portability.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_KEY = os.getenv("DUBAI_PULSE_API_KEY", "").strip()
API_SECRET = os.getenv("DUBAI_PULSE_API_SECRET", "").strip()
TOKEN_URL = os.getenv(
    "DUBAI_PULSE_TOKEN_URL",
    "https://api.dubaipulse.gov.ae/oauth/client_credential/accesstoken?grant_type=client_credentials",
)
# CKAN datastore_search action endpoint (override if the gateway path differs).
CKAN_SEARCH_URL = os.getenv(
    "DUBAI_PULSE_CKAN_URL",
    "https://api.dubaipulse.gov.ae/open/dld/dld_transactions-open/datastore_search",
)
# The transactions resource id (from the dataset's API page). Overridable.
TX_RESOURCE = os.getenv("DUBAI_PULSE_TX_RESOURCE", "dld_transactions-open")

_DB = Path(os.getenv("AIOS_PULSE_DB_PATH",
                     str(Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "dld_prices.sqlite")))

_token_cache: dict = {}


def configured() -> bool:
    return bool(API_KEY and API_SECRET)


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------
def get_token() -> str:
    """Return a valid bearer token, refreshing when near expiry (~30 min TTL)."""
    now = time.time()
    tok = _token_cache.get("t")
    if tok and now < _token_cache.get("exp", 0) - 60:
        return tok
    if not configured():
        return ""
    body = urlencode({"client_id": API_KEY, "client_secret": API_SECRET}).encode()
    req = Request(TOKEN_URL, data=body,
                  headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    tok = str(data.get("access_token") or "")
    ttl = float(data.get("expires_in") or data.get("expiresIn") or 1800)
    _token_cache["t"], _token_cache["exp"] = tok, now + ttl
    return tok


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
def _search(resource: str, limit: int, offset: int) -> dict:
    tok = get_token()
    if not tok:
        return {"success": False, "error": "no_token"}
    url = CKAN_SEARCH_URL + "?" + urlencode({"resource_id": resource, "limit": limit, "offset": offset})
    req = Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", "replace") or "{}")


def pull(resource: str = "", max_rows: int = 50000, page: int = 5000):
    """Yield transaction records, paginating through datastore_search."""
    resource = resource or TX_RESOURCE
    offset, got = 0, 0
    while got < max_rows:
        try:
            data = _search(resource, min(page, max_rows - got), offset)
        except (HTTPError, URLError, Exception):
            break
        recs = ((data.get("result") or {}).get("records")) or data.get("records") or []
        if not recs:
            break
        for r in recs:
            yield r
        n = len(recs)
        got += n
        offset += n
        if n < page:
            break


# ---------------------------------------------------------------------------
# ingest -> local prices/units index
# ---------------------------------------------------------------------------
_F = {  # tolerant field aliases across dataset versions
    "area": ("area_name_en", "area_en", "area", "master_project_en"),
    "building": ("building_name_en", "project_en", "building_name", "project_name_en"),
    "unit": ("procedure_area", "unit_number", "rooms_en"),
    "rooms": ("rooms_en", "rooms", "beds"),
    "size": ("procedure_area", "actual_area", "size", "property_size"),
    "price": ("actual_worth", "trans_value", "amount", "meter_sale_price", "procedure_value"),
    "date": ("instance_date", "transaction_date", "date"),
    "ptype": ("property_type_en", "property_sub_type_en", "property_type"),
}


def _pick(rec: dict, key: str) -> str:
    for a in _F[key]:
        v = rec.get(a)
        if v not in (None, ""):
            return str(v)
    return ""


def _con() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS sales(
        area TEXT, building TEXT, rooms TEXT, size TEXT, price REAL,
        date TEXT, ptype TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_sales_area ON sales(area)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_sales_bld ON sales(building)")
    return con


def sync(max_rows: int = 100000) -> dict:
    """Pull transactions into the local prices index. Returns a summary."""
    if not configured():
        return {"ok": False, "error": "dubai_pulse_not_configured"}
    con = _con()
    n = 0
    try:
        buf = []
        for rec in pull(max_rows=max_rows):
            price = _pick(rec, "price")
            try:
                price = float(str(price).replace(",", "")) if price else 0.0
            except Exception:
                price = 0.0
            buf.append((_pick(rec, "area"), _pick(rec, "building"), _pick(rec, "rooms"),
                        _pick(rec, "size"), price, _pick(rec, "date"), _pick(rec, "ptype")))
            if len(buf) >= 2000:
                con.executemany("INSERT INTO sales VALUES(?,?,?,?,?,?,?)", buf)
                con.commit(); n += len(buf); buf = []
        if buf:
            con.executemany("INSERT INTO sales VALUES(?,?,?,?,?,?,?)", buf)
            con.commit(); n += len(buf)
    finally:
        con.close()
    return {"ok": True, "ingested": n}


def comps(area: str = "", building: str = "", limit: int = 200) -> dict:
    """Comparable-price summary (count / avg / median / recent) for a building
    or area — instant valuation from real registered sales."""
    try:
        con = _con()
        try:
            clauses, params = [], []
            if area.strip():
                clauses.append("lower(area) LIKE ?"); params.append(f"%{area.strip().lower()}%")
            if building.strip():
                clauses.append("lower(building) LIKE ?"); params.append(f"%{building.strip().lower()}%")
            where = " AND ".join(clauses) if clauses else "1=1"
            rows = con.execute(
                f"SELECT price,size,rooms,date FROM sales WHERE {where} AND price>0 "
                f"ORDER BY date DESC LIMIT ?", params + [max(1, min(limit, 1000))]).fetchall()
        finally:
            con.close()
        prices = sorted(r["price"] for r in rows)
        if not prices:
            return {"ok": True, "count": 0, "note": "no comparable sales on file"}
        med = prices[len(prices) // 2]
        return {
            "ok": True, "count": len(prices),
            "avg": round(sum(prices) / len(prices)),
            "median": round(med),
            "min": round(prices[0]), "max": round(prices[-1]),
            "recent": [{"price": round(r["price"]), "size": r["size"],
                        "rooms": r["rooms"], "date": r["date"]} for r in rows[:5]],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def health() -> dict:
    try:
        if not configured():
            return {"component": "dubai_pulse", "status": "not_configured",
                    "hint": "set DUBAI_PULSE_API_KEY / DUBAI_PULSE_API_SECRET"}
        con = _con()
        try:
            n = con.execute("SELECT count(*) FROM sales").fetchone()[0]
            areas = con.execute("SELECT count(DISTINCT area) FROM sales").fetchone()[0]
        finally:
            con.close()
        return {"component": "dubai_pulse", "status": "ok", "sales": int(n), "areas": int(areas)}
    except Exception as exc:
        return {"component": "dubai_pulse", "status": f"error:{exc}"}
