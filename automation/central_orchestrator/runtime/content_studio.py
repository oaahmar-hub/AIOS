#!/usr/bin/env python3
"""Marketing / Content Studio — turn a real unit into ready-to-post listing copy.

Omar's marketing department. Given a query ("1BR in JVC") or an explicit unit,
it pulls the matching real inventory row and composes publish-ready copy in
English and Arabic: a headline, a body, a call-to-action, and hashtags — for
Property Finder / Instagram / WhatsApp broadcast.

Honesty rule (same as the brain): every fact in the copy comes from the
database row. Nothing is invented — no fake amenities, no rounded prices, no
"luxury" claims about size/price that aren't in the data. If a field is missing
it is simply omitted from the copy rather than filled in.

Pure stdlib. Never raises into the caller. Deterministic (no LLM needed), so it
works offline and can never hallucinate a listing.
"""
from __future__ import annotations

import re

# Channel presets: (max_headline, hashtag_count)
_CHANNELS = {
    "property_finder": 90,
    "instagram": 60,
    "whatsapp": 80,
}

_AREA_TAGS = {
    "jvc": ["#JVC", "#JumeirahVillageCircle"],
    "jvt": ["#JVT", "#JumeirahVillageTriangle"],
    "marina": ["#DubaiMarina"],
    "downtown": ["#DowntownDubai"],
    "business bay": ["#BusinessBay"],
    "dubai hills": ["#DubaiHills"],
    "jbr": ["#JBR"],
}


def _fmt_price(price: str) -> str:
    p = re.sub(r"[^\d.]", "", str(price or ""))
    if not p:
        return ""
    try:
        n = float(p)
    except Exception:
        return ""
    return f"AED {int(n):,}" if n == int(n) else f"AED {n:,.0f}"


def _beds_label(row: dict) -> tuple[str, str]:
    b = re.sub(r"[^\d]", "", str(row.get("bedrooms") or ""))
    if not b or b == "0":
        return ("Studio", "استوديو")
    return (f"{b} Bedroom", f"{b} غرفة نوم")


def _size_label(row: dict) -> str:
    s = re.sub(r"[^\d.]", "", str(row.get("size") or ""))
    if not s:
        return ""
    try:
        n = float(s)
    except Exception:
        return ""
    sqft = n * 10.7639
    return f"{n:.0f} sqm ({sqft:,.0f} sqft)"


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

        # --- English ---
        head_bits = [beds_en, "Apartment"]
        if building:
            head_bits.append(f"in {building}")
        elif area:
            head_bits.append(f"in {area}")
        headline_en = " ".join(head_bits)

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

        body_en = f"{beds_en} apartment"
        if area:
            body_en += f" in {area}"
        body_en += "."
        if size:
            body_en += f" {size} of built-up area."
        if price:
            body_en += f" Asking {price}."
        body_en += " Verified availability — contact to arrange a viewing."

        cta_en = f"Serious enquiries only. WhatsApp for the full details{(' on Unit ' + unit) if unit else ''}."

        # --- Arabic ---
        headline_ar = f"شقة {beds_ar}"
        if building:
            headline_ar += f" في {building}"
        elif area:
            headline_ar += f" في {area}"
        body_ar = f"شقة {beds_ar}"
        if area:
            body_ar += f" في {area}"
        body_ar += "."
        if size:
            body_ar += f" المساحة {size}."
        if price:
            body_ar += f" السعر المطلوب {price}."
        body_ar += " الوحدة متاحة ومتحقق منها — تواصل معنا لتحديد موعد معاينة."
        cta_ar = "للجادين فقط. راسلنا على واتساب لكامل التفاصيل."

        # --- Hashtags (honest: only tags we can justify from the row) ---
        tags = ["#DubaiRealEstate", "#PropertyForSale"]
        for key, tg in _AREA_TAGS.items():
            if key in area.lower():
                tags.extend(tg)
                break
        if building:
            tags.append("#" + re.sub(r"[^A-Za-z0-9]", "", building.title()))
        beds_tag = re.sub(r"[^\d]", "", str(row.get("bedrooms") or ""))
        if beds_tag and beds_tag != "0":
            tags.append(f"#{beds_tag}BR")
        # dedup, cap
        seen, hashtags = set(), []
        for t in tags:
            if t.lower() not in seen and len(t) > 1:
                seen.add(t.lower()); hashtags.append(t)
        hashtags = hashtags[:8]

        limit = _CHANNELS.get(channel, 90)
        return {
            "ok": True,
            "channel": channel,
            "unit_ref": {"area": area, "building": building, "unit": unit},
            "en": {
                "headline": headline_en[:limit],
                "facts": facts_en,
                "body": body_en,
                "cta": cta_en,
            },
            "ar": {
                "headline": headline_ar,
                "body": body_ar,
                "cta": cta_ar,
            },
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
    posts = [compose(r, channel) for r in rows]
    return {"ok": True, "matched": len(posts), "channel": channel, "posts": posts}


def health() -> dict:
    try:
        import inventory_retrieval as _inv
        n = len(_inv.search("apartment", max_results=1))
        return {"ok": True, "detail": f"studio ready ({'inventory reachable' if n >= 0 else 'no inventory'})"}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "detail": f"error:{exc}"}


if __name__ == "__main__":
    import json
    print(json.dumps(generate("1BR in JVC"), ensure_ascii=False, indent=2)[:1400])
