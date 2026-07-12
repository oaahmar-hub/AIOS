#!/usr/bin/env python3
"""Listing asking-price reader — pairs portal ASKING prices with DLD SOLD data.

Given a pasted Bayut/PropertyFinder/Dubizzle link, pulls the asking price the
page exposes (JSON-LD Offer / embedded price), resolves area+building via
portal_extract, and compares against the official market read (market_index)
so an agent instantly sees whether a listing is priced above/below the market.

Best-effort: portals redirect + bot-protect, so extraction can fail — in which
case it says so honestly rather than guessing. User-initiated (agent pastes the
link). Pure stdlib.
"""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126 Safari/537.36")


def _fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": _UA, "Accept-Language": "en-US,en",
                                "Accept": "text/html"})
    with urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _extract_price(html: str) -> tuple:
    """Return (price:int|None, currency). Tries JSON-LD, then embedded JSON."""
    # 1) JSON-LD blocks
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict):
                continue
            offer = node.get("offers") or {}
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            price = offer.get("price") or node.get("price")
            if price:
                try:
                    return int(float(str(price).replace(",", ""))), str(
                        offer.get("priceCurrency") or node.get("priceCurrency") or "AED")
                except Exception:
                    pass
    # 2) embedded "price":N (take the first plausible property price)
    for mm in re.finditer(r'"price"\s*:\s*"?([0-9]{5,12})', html):
        try:
            v = int(mm.group(1))
            if 50_000 <= v <= 500_000_000:
                return v, "AED"
        except Exception:
            continue
    return None, "AED"


def assess(url: str) -> dict:
    """{asking_price, area, building, market, verdict} for a pasted listing."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "missing url"}
    info = {}
    try:
        import portal_extract as pe
        info = pe.extract(url)
    except Exception:
        info = {}
    price, cur = None, "AED"
    detail = "ok"
    try:
        price, cur = _extract_price(_fetch(url))
    except Exception as exc:
        detail = f"fetch_failed:{type(exc).__name__}"
    out = {
        "ok": True,
        "portal": info.get("portal", ""),
        "area": info.get("area", ""),
        "building": info.get("building", ""),
        "listing_id": info.get("listing_id", ""),
        "asking_price": price,
        "currency": cur,
        "detail": detail,
    }
    # Compare to the official market read.
    try:
        import market_index as mi
        s = mi.summary()
        if s.get("ok"):
            out["market"] = {
                "avg_flat": s.get("flat_avg_price"),
                "avg_villa": s.get("villa_avg_price"),
                "yoy_pct": s.get("market_yoy_pct"),
                "direction": s.get("direction"),
            }
            ref = s.get("flat_avg_price")
            if price and ref:
                gap = round((price - ref) / ref * 100, 1)
                out["vs_market_flat_pct"] = gap
                out["verdict"] = ("above market" if gap > 8 else
                                  "below market" if gap < -8 else "around market")
    except Exception:
        pass
    if not price:
        out["note"] = "Couldn't read the asking price (portal blocked it) — paste the price and I'll assess."
    return out
