#!/usr/bin/env python3
"""Dubai market intelligence — official DLD residential sale/price index.

Turns the DLD open 'Residential Sale Index' (bundled at data/market/) into a
plain-English market read: current price level, year-on-year change, and trend
for flats and villas. Feeds the WhatsApp brain so a client asking "how's the
market / good time to buy?" gets a real, data-backed answer instead of opinion.

Public open data (no PII). Pure stdlib. Never raises into callers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DATA = Path(os.getenv("AIOS_MARKET_INDEX_PATH",
                       str(Path(__file__).resolve().parent / "data" / "market" / "dld_sale_index.json")))

_cache: dict = {}


def _rows() -> list:
    if "rows" in _cache:
        return _cache["rows"]
    rows = []
    try:
        data = json.loads(_DATA.read_text())
        rows = data if isinstance(data, list) else (data.get("records") or data.get("data") or [])
        rows = [r for r in rows if isinstance(r, dict) and r.get("first_date_of_month")]
        rows.sort(key=lambda r: r.get("first_date_of_month", ""))
    except Exception:
        rows = []
    _cache["rows"] = rows
    return rows


def _num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "", "None") else None
    except Exception:
        return None


def _latest(rows: list, key: str):
    """Most recent row (date, value) where key is populated."""
    for r in reversed(rows):
        v = _num(r.get(key))
        if v is not None:
            return r.get("first_date_of_month"), v
    return None, None


def _yoy(rows: list, key: str):
    """Year-on-year % change of the price index for `key`."""
    dated = [(r.get("first_date_of_month"), _num(r.get(key))) for r in rows]
    dated = [(d, v) for d, v in dated if v is not None]
    if len(dated) < 13:
        return None
    d_now, v_now = dated[-1]
    # find the value ~12 months earlier
    target_year = str(int(d_now[:4]) - 1) + d_now[4:7]
    prev = next((v for d, v in dated if d and d[:7] == target_year), None)
    if prev is None:
        prev = dated[-13][1]
    if not prev:
        return None
    return round((v_now - prev) / prev * 100, 1)


def summary() -> dict:
    rows = _rows()
    if not rows:
        return {"ok": False, "error": "market_index_unavailable"}
    d_flat, flat_price = _latest(rows, "flat_monthly_price_index")
    d_villa, villa_price = _latest(rows, "villa_monthly_price_index")
    flat_yoy = _yoy(rows, "flat_monthly_price_index")
    villa_yoy = _yoy(rows, "villa_monthly_price_index")
    all_yoy = _yoy(rows, "all_monthly_price_index")
    direction = "flat"
    if all_yoy is not None:
        direction = "rising" if all_yoy > 1 else ("cooling" if all_yoy < -1 else "stable")
    return {
        "ok": True,
        "as_of": d_flat or d_villa,
        "flat_avg_price": round(flat_price) if flat_price else None,
        "villa_avg_price": round(villa_price) if villa_price else None,
        "flat_yoy_pct": flat_yoy,
        "villa_yoy_pct": villa_yoy,
        "market_yoy_pct": all_yoy,
        "direction": direction,
        "source": "DLD Residential Sale Index (official)",
    }


def brief(lang: str = "en") -> str:
    """One-line plain-English market read for the reply brain."""
    s = summary()
    if not s.get("ok"):
        return ""
    yoy = s.get("market_yoy_pct")
    if lang == "ar":
        arrow = "صاعد" if s["direction"] == "rising" else ("يهدأ" if s["direction"] == "cooling" else "مستقر")
        parts = [f"السوق {arrow}"]
        if yoy is not None:
            parts.append(f"{yoy:+.1f}% سنوياً")
        if s.get("flat_avg_price"):
            parts.append(f"متوسط الشقق ~AED {s['flat_avg_price']:,}")
        return " · ".join(parts) + f" (مؤشر DLD، {s.get('as_of','')})"
    arrow = {"rising": "up", "cooling": "cooling", "stable": "stable"}.get(s["direction"], "")
    parts = [f"Market is {arrow}"]
    if yoy is not None:
        parts.append(f"{yoy:+.1f}% YoY")
    if s.get("flat_avg_price"):
        parts.append(f"avg flat ~AED {s['flat_avg_price']:,}")
    if s.get("villa_avg_price"):
        parts.append(f"avg villa ~AED {s['villa_avg_price']:,}")
    return " · ".join(parts) + f" (DLD index, {s.get('as_of','')})"


def health() -> dict:
    rows = _rows()
    return {"component": "market_index", "status": "ok" if rows else "no_data",
            "months": len(rows)}
