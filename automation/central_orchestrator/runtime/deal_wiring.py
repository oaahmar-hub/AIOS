#!/usr/bin/env python3
"""Wire the Deal Agent's provider interfaces to the real runtime modules.

Keeps :mod:`deal_agent` pure/testable while this file connects it to the
live pieces:
  - parse   -> deal_parser.parse_request
  - search  -> inventory_retrieval.search (real verified inventory today;
               portal scrapers can replace/augment this behind the same iface)
  - owners  -> owner_lookup.owners_for_unit (real DLD owner + phone)
  - send/reply/call -> injected by the caller (Wasender now, Twilio voice later)

Everything degrades to a safe empty result if a module is missing, so importing
this never breaks the server.
"""

from __future__ import annotations

from typing import Callable, Optional


def _criteria_to_query(criteria: dict) -> str:
    parts = []
    for k in ("beds", "type", "area"):
        v = criteria.get(k)
        if v:
            parts.append(str(v))
    return " ".join(parts) or str(criteria.get("raw", ""))


def _units_from_url(raw: str) -> list:
    """If the request contains a portal listing link, resolve it to a precise
    unit (building/area) so the owner lookup can hit it directly."""
    import re
    m = re.search(r"https?://\S+", raw or "")
    if not m:
        return []
    try:
        import portal_extract as pe
        info = pe.extract(m.group(0))
        if info.get("ok") and (info.get("building") or info.get("area")):
            return [{
                "building": info.get("building", ""),
                "unit": "",
                "area": info.get("area", ""),
                "property_number": "",
                "source": f"{info.get('portal')} listing {info.get('listing_id', '')}",
            }]
    except Exception:
        pass
    return []


def _search(criteria: dict) -> list:
    try:
        # 1) a pasted portal link -> the exact building first
        out = _units_from_url(str(criteria.get("raw", "")))
        # 2) plus matching verified inventory
        import inventory_retrieval as inv
        rows = inv.search(_criteria_to_query(criteria), max_results=10) or []
        for r in rows:
            out.append({
                "building": r.get("building", "") or r.get("project", ""),
                "unit": r.get("unit", ""),
                "project": r.get("project", ""),
                "property_number": r.get("permit_number", "") or r.get("property_number", ""),
                "price": r.get("price", ""),
                "area": r.get("area", ""),
            })
        return out
    except Exception:
        return []


def _owners(unit: dict) -> list:
    try:
        import owner_lookup as ol
        return ol.owners_for_unit(unit)
    except Exception:
        return []


def build_agent(
    send_whatsapp: Callable[[str, str], tuple],
    reply_group: Callable[[str, str], tuple],
    place_call: Optional[Callable[[str, str], dict]] = None,
):
    """Return a live DealAgent wired to the real search + owner modules."""
    import deal_agent as da
    from deal_parser import parse_request
    return da.DealAgent(
        parse=parse_request,
        search=_search,
        lookup_owners=_owners,
        send_whatsapp=send_whatsapp,
        reply_group=reply_group,
        place_call=place_call,
    )


def health() -> dict:
    checks = {}
    try:
        import inventory_retrieval as inv
        checks["search_source"] = f"inventory:{inv.quotable_count()} units"
    except Exception as exc:
        checks["search_source"] = f"error:{exc}"
    try:
        import owner_lookup as ol
        h = ol.health()
        checks["owner_source"] = f"{h.get('with_phone', 0)} phones / {h.get('areas', 0)} areas"
    except Exception as exc:
        checks["owner_source"] = f"error:{exc}"
    return {"component": "deal_wiring", "providers": checks, "status": "ok"}
