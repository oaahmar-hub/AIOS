#!/usr/bin/env python3
"""Owner Lookup — unit / building / property-number -> real owner + phone.

Built on the DLD ownership exports (JVC.xlsx and the per-area files). This is
the keystone the Deal Agent uses at stage OWNERS: given a candidate unit it
returns the real owner name(s) + phone(s), or nothing (never a fabricated
number).

Handles the two DLD sheet schemas seen in the data:
  * "transaction" schema:  BuildingNameEn / UnitNumber / NameEn / Mobile /
    ProcedurePartyTypeNameEn (Seller|Buyer) / Plot Pre Reg No
  * "owner" schema:        BuildingName 2 / UnitNumber / property_number /
    Owner Name / Phone 1..2 / Mobile 1..2

Ingest writes a local SQLite index (``AIOS_OWNER_DB_PATH``, default under the
runtime data dir). The data is PII (names, mobiles, IDs) — it lives only in
that local/volume DB, is never committed, and is served ONLY behind admin auth
(the customer channel's NEVER_DISCLOSE guard stays intact).

Pure stdlib for query/health. Ingest uses openpyxl when available.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "owner_lookup.sqlite"
OWNER_DB_PATH = Path(os.getenv("AIOS_OWNER_DB_PATH", str(_DEFAULT_DB)))

# Encrypted seed DB shipped in the repo (ciphertext only — never plaintext PII).
# On boot, if the live DB is empty and AIOS_OWNER_SEED_KEY is set, the server
# restores the real owner index from this seed. The key lives ONLY in the
# Railway env, so the git blob is useless without it.
_SEED_PATH = Path(__file__).resolve().parent / "data" / "owner_seed.db.gz.enc"
_SEED_RESTORED = False


def _seed_crypt(data: bytes, key: str, nonce: bytes) -> bytes:
    """Symmetric stream cipher (HMAC-SHA256 keystream, CTR mode) — stdlib only.
    XOR is its own inverse, so this both encrypts and decrypts."""
    import hashlib
    import hmac
    kb = hashlib.sha256(key.encode("utf-8")).digest()
    out = bytearray()
    i = 0
    while len(out) < len(data):
        out.extend(hmac.new(kb, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest())
        i += 1
    return bytes(a ^ b for a, b in zip(data, out))


def _db_count_safe() -> int:
    try:
        con = sqlite3.connect(str(OWNER_DB_PATH))
        try:
            return con.execute("SELECT count(*) FROM owners").fetchone()[0]
        finally:
            con.close()
    except Exception:
        return 0


def _maybe_restore_seed() -> None:
    """Restore the real owner DB from the encrypted seed when the live DB is
    empty. Idempotent, best-effort, never raises into callers."""
    global _SEED_RESTORED
    if _SEED_RESTORED:
        return
    _SEED_RESTORED = True
    key = os.getenv("AIOS_OWNER_SEED_KEY", "")
    if not key or not _SEED_PATH.exists():
        return
    try:
        if OWNER_DB_PATH.exists() and _db_count_safe() > 0:
            return  # already populated (e.g. mounted volume)
        import gzip
        blob = _SEED_PATH.read_bytes()
        nonce, ct = blob[:16], blob[16:]
        raw = gzip.decompress(_seed_crypt(ct, key, nonce))
        OWNER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        OWNER_DB_PATH.write_bytes(raw)
    except Exception:
        pass

_OWNER_COLS = ["NameEn", "Owner Name", "OwnerName"]
_PHONE_COLS = ["Mobile 1", "Mobile 2", "Phone 1", "Phone 2", "Mobile", "Phone"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _norm(x) -> str:
    return str(x).strip() if x is not None else ""


def _clean_phone(s: str) -> str:
    """Keep a phone only if it has a plausible number of digits."""
    s = _norm(s)
    d = "".join(c for c in s if c.isdigit())
    if len(d) < 7 or d.strip("0") == "":
        return ""
    return s


def _first_phone(*vals) -> str:
    for v in vals:
        p = _clean_phone(v)
        if p:
            return p
    return ""


def mask(phone: str) -> str:
    d = "".join(c for c in _norm(phone) if c.isdigit())
    return f"***{d[-3:]}" if len(d) >= 3 else "***"


def _connect() -> sqlite3.Connection:
    _maybe_restore_seed()
    OWNER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(OWNER_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS owners(
            area TEXT, building TEXT, unit TEXT, project TEXT,
            property_number TEXT, role TEXT, name TEXT, phone TEXT,
            country TEXT, source TEXT)"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS ix_bu ON owners(building, unit)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_pn ON owners(property_number)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_unit ON owners(unit)")


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------
def index_rows(rows: list, source: str = "manual", reset: bool = False) -> int:
    """Insert normalized owner rows. Each row is a dict with any of:
    area, building, unit, project, property_number, role, name, phone, country.
    Returns the number inserted."""
    con = _connect()
    try:
        _ensure_schema(con)
        if reset:
            con.execute("DELETE FROM owners WHERE source = ?", (source,))
        buf = []
        for r in rows:
            name = _norm(r.get("name"))
            if not name:
                continue
            buf.append((
                _norm(r.get("area")), _norm(r.get("building")), _norm(r.get("unit")),
                _norm(r.get("project")), _norm(r.get("property_number")),
                _norm(r.get("role")) or "Owner", name, _clean_phone(r.get("phone")),
                _norm(r.get("country")), source,
            ))
        con.executemany(
            "INSERT INTO owners(area,building,unit,project,property_number,role,name,phone,country,source)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)", buf,
        )
        con.commit()
        return len(buf)
    finally:
        con.close()


def ingest_dld_xlsx(path: str, area: str = "") -> dict:
    """Parse a DLD ownership xlsx (either schema, all sheets) into the index."""
    try:
        import openpyxl
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"openpyxl unavailable: {exc}"}
    p = Path(path)
    area = area or re.sub(r"[^A-Za-z0-9 ]", "", p.stem).strip()
    try:
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    total = 0
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        it = ws.iter_rows(values_only=True)
        try:
            header = [_norm(h) for h in next(it)]
        except StopIteration:
            continue
        I = {h: i for i, h in enumerate(header)}

        def g(row, name):
            i = I.get(name)
            return _norm(row[i]) if i is not None and i < len(row) else ""

        owner_col = next((c for c in _OWNER_COLS if c in I), None)
        if not owner_col:
            continue
        building_col = next((c for c in ("BuildingName 2", "BuildingNameEn", "Building 1", "Building No") if c in I), None)
        unit_col = next((c for c in ("UnitNumber", "Unit Number", "Unit") if c in I), None)
        pn_col = next((c for c in ("property_number", "Plot Pre Reg No") if c in I), None)
        rows = []
        for r in it:
            name = g(r, owner_col)
            if not name:
                continue
            phone = _first_phone(*[g(r, c) for c in _PHONE_COLS if c in I])
            rows.append({
                "area": area,
                "building": g(r, building_col) if building_col else "",
                "unit": g(r, unit_col) if unit_col else "",
                "project": g(r, "Project"),
                "property_number": g(r, pn_col) if pn_col else "",
                "role": g(r, "ProcedurePartyTypeNameEn") or "Owner",
                "name": name,
                "phone": phone,
                "country": g(r, "CountryNameEn"),
            })
        total += index_rows(rows, source=f"dld:{p.name}")
    return {"ok": True, "file": p.name, "area": area, "indexed": total}


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------
def lookup(building: str = "", unit: str = "", property_number: str = "",
           area: str = "", limit: int = 10, reveal: bool = False) -> dict:
    """Return owners matching the given keys. Phones masked unless reveal=True
    (reveal is only ever passed after admin auth at the API layer)."""
    try:
        if not any([building.strip(), unit.strip(), property_number.strip()]):
            return {"ok": False, "error": "need building, unit, or property_number"}
        con = _connect()
        try:
            _ensure_schema(con)
            clauses, params = [], []
            if property_number.strip():
                clauses.append("lower(property_number) = ?"); params.append(property_number.strip().lower())
            if building.strip():
                # token-AND match: every significant word must appear in the
                # building, in any order — so "Bloom Towers" (or a URL-derived
                # "bloom towers") matches "BLOOM TOWERS C". Generic filler words
                # are dropped so they don't over-constrain.
                _filler = {"the", "of", "at", "by", "and", "dubai"}
                toks = [t for t in re.split(r"[^a-z0-9]+", building.strip().lower())
                        if len(t) > 1]
                core = [t for t in toks if t not in _filler] or toks
                for t in core:
                    clauses.append("lower(building) LIKE ?"); params.append(f"%{t}%")
            if unit.strip():
                clauses.append("lower(unit) = ?"); params.append(unit.strip().lower())
            if area.strip():
                clauses.append("lower(area) LIKE ?"); params.append(f"%{area.strip().lower()}%")
            where = " AND ".join(clauses)
            rows = con.execute(
                f"SELECT area,building,unit,property_number,role,name,phone,country "
                f"FROM owners WHERE {where} AND phone != '' LIMIT ?",
                params + [max(1, min(limit, 50))],
            ).fetchall()
        finally:
            con.close()
        out = []
        for r in rows:
            out.append({
                "area": r["area"], "building": r["building"], "unit": r["unit"],
                "property_number": r["property_number"], "role": r["role"],
                "name": r["name"], "country": r["country"],
                "phone": r["phone"] if reveal else mask(r["phone"]),
            })
        return {"ok": True, "matches": len(out), "owners": out}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


def owners_for_unit(unit: dict) -> list:
    """Deal Agent adapter: candidate unit dict -> [{name, phone(real)}]. Server
    side only (reveal=True) — the outbound guardrails live in the Deal Agent."""
    res = lookup(
        building=str(unit.get("building", "")),
        unit=str(unit.get("unit", "")),
        property_number=str(unit.get("property_number", "")),
        reveal=True, limit=5,
    )
    return res.get("owners", []) if res.get("ok") else []


def health() -> dict:
    try:
        con = _connect()
        try:
            _ensure_schema(con)
            n = con.execute("SELECT count(*) FROM owners").fetchone()[0]
            withph = con.execute("SELECT count(*) FROM owners WHERE phone != ''").fetchone()[0]
            areas = con.execute("SELECT count(DISTINCT area) FROM owners").fetchone()[0]
        finally:
            con.close()
        return {"component": "owner_lookup", "records": int(n), "with_phone": int(withph),
                "areas": int(areas), "db": str(OWNER_DB_PATH),
                "status": "ok" if n else "empty_awaiting_ingest"}
    except Exception as exc:
        return {"component": "owner_lookup", "status": f"error:{exc}"}
