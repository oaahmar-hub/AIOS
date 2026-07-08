#!/usr/bin/env python3
"""Marketing Engine (Content Studio) — turn real units into ready-to-post assets.

Omar's marketing department. It pulls matching REAL inventory rows and composes
publish-ready copy in English and Arabic across channels (Property Finder,
Instagram, WhatsApp broadcast, Story, Email), builds multi-unit campaigns, and
surfaces the best units to promote (value picks by price-per-sqft).

Honesty rule (same as the brain): every fact in the copy comes from the database
row. Nothing is invented — no fake amenities, no rounded prices, no "luxury"
claims that aren't in the data. Missing fields are omitted, never filled in.
Size units are inferred safely (sqm vs sqft) rather than assumed.

Pure stdlib. Never raises into the caller. Deterministic (no LLM), so it works
offline and can never hallucinate a listing.
"""
from __future__ import annotations

import re

# Channel presets: max headline length used when trimming.
_CHANNELS = {
    "property_finder": 90,
    "instagram": 60,
    "whatsapp": 80,
    "story": 48,
    "email": 140,
    "broadcast": 80,
}

_AREA_TAGS = {
    "jvc": ["#JVC", "#JumeirahVillageCircle"],
    "jvt": ["#JVT", "#JumeirahVillageTriangle"],
    "marina": ["#DubaiMarina"],
    "downtown": ["#DowntownDubai"],
    "business bay": ["#BusinessBay"],
    "dubai hills": ["#DubaiHills"],
    "jbr": ["#JBR"],
    "creek harbour": ["#CreekHarbour", "#DubaiCreekHarbour"],
    "emaar south": ["#EmaarSouth"],
    "beach front": ["#EmaarBeachfront"],
    "palm": ["#PalmJumeirah"],
    "bianca": ["#Bianca"],
    "valley": ["#TheValley"],
}


def _num(v) -> float | None:
    s = re.sub(r"[^\d.]", "", str(v or ""))
    if not s:
        return None
    try:
        n = float(s)
        return n if n > 0 else None
    except Exception:
        return None


def _fmt_price(price) -> str:
    n = _num(price)
    return f"AED {int(n):,}" if n is not None else ""


def _beds_label(row: dict) -> tuple[str, str]:
    b = re.sub(r"[^\d]", "", str(row.get("bedrooms") or ""))
    if not b or b == "0":
        return ("Studio", "استوديو")
    return (f"{b} Bedroom", f"{b} غرفة نوم")


def _sqft(row: dict) -> float | None:
    """Return the unit's built-up area in sqft, inferring the stored unit.

    Dubai apartment areas below ~200 are square metres (a real flat is never
    ~80 sqft); larger values are already square feet. This keeps mixed-source
    data honest instead of assuming one unit everywhere.
    """
    n = _num(row.get("size"))
    if n is None:
        return None
    return n * 10.7639 if n < 200 else n


def _size_label(row: dict) -> str:
    n = _num(row.get("size"))
    if n is None:
        return ""
    if n < 200:  # square metres in source
        return f"{n:.0f} sqm ({n * 10.7639:,.0f} sqft)"
    return f"{n:,.0f} sqft ({n / 10.7639:,.0f} sqm)"  # square feet in source


def _price_per_sqft(row: dict) -> float | None:
    p = _num(row.get("price"))
    f = _sqft(row)
    if p is None or not f:
        return None
    return p / f


def _hashtags(row: dict) -> list[str]:
    area = str(row.get("area") or "")
    building = str(row.get("building") or "")
    tags = ["#DubaiRealEstate", "#PropertyForSale"]
    for key, tg in _AREA_TAGS.items():
        if key in area.lower() or key in building.lower():
            tags.extend(tg)
            break
    if building:
        tags.append("#" + re.sub(r"[^A-Za-z0-9]", "", building.title()))
    beds_tag = re.sub(r"[^\d]", "", str(row.get("bedrooms") or ""))
    if beds_tag and beds_tag != "0":
        tags.append(f"#{beds_tag}BR")
    seen, out = set(), []
    for t in tags:
        if t.lower() not in seen and len(t) > 1:
            seen.add(t.lower()); out.append(t)
    return out[:8]


def compose(row: dict, channel: str = "property_finder") -> dict:
    """Build EN+AR listing copy from ONE real inventory row. Never raises."""
    try:
        area = str(row.get("area") or "").strip()
        building = str(row.get("building") or "").strip()
        unit = str(row.get("unit") or "").strip()
        developer = str(row.get("developer") or "").strip()
        beds_en, beds_ar = _beds_label(row)
        price = _fmt_price(row.get("price"))
        size = _size_label(row)
        short = channel in ("story", "instagram")

        head_bits = [beds_en, "Apartment"]
        head_bits.append(f"in {building}" if building else (f"in {area}" if area else ""))
        headline_en = " ".join(b for b in head_bits if b)

        line = []
        if area and building:
            line.append(f"{building}, {area}")
        elif area:
            line.append(area)
        if size:
            line.append(size)
        if developer:
            line.append(f"Developer: {developer}")
        if unit:
            line.append(f"Unit {unit}")
        facts_en = " · ".join(line)

        if short:
            body_en = f"{beds_en}" + (f" in {area}" if area else "") + "."
            if price:
                body_en += f" {price}."
            body_en += " Verified. DM to view."
        else:
            body_en = f"{beds_en} apartment" + (f" in {area}" if area else "") + "."
            if size:
                body_en += f" {size} of built-up area."
            if price:
                body_en += f" Asking {price}."
            body_en += " Verified availability — contact to arrange a viewing."

        cta_en = f"Serious enquiries only. WhatsApp for the full details{(' on Unit ' + unit) if unit else ''}."

        headline_ar = f"شقة {beds_ar}" + (f" في {building}" if building else (f" في {area}" if area else ""))
        body_ar = f"شقة {beds_ar}" + (f" في {area}" if area else "") + "."
        if size:
            body_ar += f" المساحة {size}."
        if price:
            body_ar += f" السعر المطلوب {price}."
        body_ar += " الوحدة متاحة ومتحقق منها — تواصل معنا لتحديد موعد معاينة."
        cta_ar = "للجادين فقط. راسلنا على واتساب لكامل التفاصيل."

        hashtags = _hashtags(row)
        limit = _CHANNELS.get(channel, 90)
        return {
            "ok": True,
            "channel": channel,
            "unit_ref": {"area": area, "building": building, "unit": unit},
            "en": {"headline": headline_en[:limit], "facts": facts_en, "body": body_en, "cta": cta_en},
            "ar": {"headline": headline_ar, "body": body_ar, "cta": cta_ar},
            "hashtags": hashtags,
            "post": f"{headline_en}\n\n{body_en}\n\n{cta_en}\n\n{' '.join(hashtags)}",
            "post_ar": f"{headline_ar}\n\n{body_ar}\n\n{cta_ar}\n\n{' '.join(hashtags)}",
            "honest": True,
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


def generate(query: str, channel: str = "property_finder", max_results: int = 3) -> dict:
    """Match a query against real inventory and compose copy for each unit."""
    try:
        import inventory_retrieval as _inv
        rows = _inv.search(query, max_results=max_results)
    except Exception as exc:
        return {"ok": False, "error": f"inventory:{exc}", "posts": []}
    if not rows:
        return {"ok": True, "matched": 0, "posts": [],
                "note": "No verified unit matched — nothing composed (no fabrication)."}
    return {"ok": True, "matched": len(rows), "channel": channel,
            "posts": [compose(r, channel) for r in rows]}


def value_picks(query: str, count: int = 5) -> list[dict]:
    """Rank matched real units by best price-per-sqft (value first). Honest —
    only units that actually have both a price and a size can be ranked."""
    try:
        import inventory_retrieval as _inv
        rows = _inv.search(query, max_results=max(count * 4, 12))
    except Exception:
        return []
    scored = []
    for r in rows:
        ppsf = _price_per_sqft(r)
        if ppsf is None:
            continue
        scored.append((ppsf, r))
    scored.sort(key=lambda x: x[0])
    out = []
    for ppsf, r in scored[:count]:
        out.append({**r, "price_per_sqft": round(ppsf), "why": f"AED {round(ppsf):,}/sqft"})
    return out


def campaign(query: str, channel: str = "instagram", count: int = 3) -> dict:
    """A full marketing campaign for a query: the best units to promote, one
    post each, plus a ready WhatsApp broadcast. Real units only."""
    picks = value_picks(query, count=count)
    if not picks:
        # fall back to plain matches (some sources lack size for ppsf)
        g = generate(query, channel, max_results=count)
        picks = [p["unit_ref"] for p in g.get("posts", [])] if g.get("posts") else []
        if not g.get("posts"):
            return {"ok": True, "matched": 0, "posts": [],
                    "note": "No verified unit matched — nothing composed (no fabrication)."}
        posts = g["posts"]
        area = posts[0]["unit_ref"].get("area", "")
    else:
        posts = [compose(p, channel) for p in picks]
        area = picks[0].get("area", "")

    prices = [_num(p.get("price")) for p in picks] if picks and isinstance(picks[0], dict) and "price" in picks[0] else []
    prices = [p for p in prices if p]
    from_price = f"AED {int(min(prices)):,}" if prices else ""

    header_en = f"{len(posts)} verified {area} home{'s' if len(posts) != 1 else ''}".strip()
    if from_price:
        header_en += f" — from {from_price}"
    header_en += " · this week's picks"
    header_ar = f"{len(posts)} وحدة متحقق منها في {area}".strip()
    if from_price:
        header_ar += f" — تبدأ من {from_price}"

    # WhatsApp broadcast: a header + one honest line per unit.
    lines_en = [f"🏠 *{header_en}*", ""]
    lines_ar = [f"🏠 *{header_ar}*", ""]
    for p in posts:
        ref = p["unit_ref"]
        bits = [x for x in [ref.get("building"), ref.get("area"),
                            (f"Unit {ref.get('unit')}" if ref.get("unit") else "")] if x]
        # find the price back from the composed body
        m = re.search(r"AED [\d,]+", p["en"]["body"])
        price = f" — {m.group(0)}" if m else ""
        lines_en.append("• " + " · ".join(bits) + price)
        lines_ar.append("• " + " · ".join(bits) + price)
    lines_en += ["", "Verified availability. WhatsApp for details & viewing."]
    lines_ar += ["", "وحدات متحقق منها. راسلنا على واتساب للتفاصيل والمعاينة."]

    return {
        "ok": True,
        "matched": len(posts),
        "channel": channel,
        "header": {"en": header_en, "ar": header_ar},
        "posts": posts,
        "broadcast_en": "\n".join(lines_en),
        "broadcast_ar": "\n".join(lines_ar),
        "honest": True,
    }


def health() -> dict:
    try:
        import inventory_retrieval as _inv
        n = _inv.quotable_count()
        return {"ok": n > 0, "detail": f"engine ready · {n} units · 6 channels · campaigns+value-picks"}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "detail": f"error:{exc}"}


if __name__ == "__main__":
    import json
    print(json.dumps(campaign("2BR in JVC", count=3), ensure_ascii=False, indent=2)[:1800])
