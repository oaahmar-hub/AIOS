#!/usr/bin/env python3
"""Local reply brain — generates a real, honest WhatsApp reply with NO external
LLM and NO n8n. Intent + the real verified inventory only.

This is the always-available tier: when neither the direct LLM (Groq/OpenAI)
nor the n8n brain is reachable (no key, quota exhausted, outage), the system
still answers naturally instead of going silent — and never fabricates a fact
(unknown -> "I'll check"). Quotes ONLY real inventory rows.

Pure stdlib. Never raises into the caller.
"""

from __future__ import annotations

import re

_AR = re.compile(r"[؀-ۿ]")


def _is_ar(t: str) -> bool:
    return bool(_AR.search(t or ""))


def _hz(text: str) -> str:
    try:
        import reply_humanizer as rh
        return rh.humanize(text)
    except Exception:
        return text


def reply(message: str, history: str = "") -> tuple[str, str]:
    """Return (reply_text, detail). Empty text only for an empty message."""
    m = (message or "").strip()
    if not m:
        return "", "empty"
    low = m.lower()
    ar = _is_ar(m)

    greet = (
        any(w in low for w in ("hello", "hi ", "hey", "good morning", "good evening", "good afternoon"))
        or low in ("hi", "hey", "hello")
        or any(w in m for w in ("مرحبا", "السلام", "اهلا", "أهلا", "هلا", "صباح", "مساء"))
    )
    thanks = any(w in low for w in ("thanks", "thank you", "thx", "appreciate")) or "شكرا" in m or "شكراً" in m
    photo = (
        any(w in low for w in ("photo", "picture", "pics", "images", "image", "brochure", "video"))
        or any(w in m for w in ("صور", "صورة", "بروشور", "فيديو"))
    )

    # Inventory intent — search real verified units only.
    q: dict = {}
    rows: list = []
    try:
        import inventory_retrieval as inv
        q = inv.parse_query(m) or {}
        wants_inv = bool(q.get("area") or q.get("bedrooms") or q.get("budget") or q.get("project")) or any(
            w in low for w in ("available", "availability", "for rent", "for sale", "price", "unit", "apartment", "villa")
        ) or any(w in m for w in ("متاح", "متوفر", "للايجار", "للبيع", "سعر", "شقة", "فيلا", "وحدة"))
        if wants_inv:
            rows = inv.search(m, max_results=3) or []
    except Exception:
        q, rows = {}, []

    # Price / valuation intent -> real DLD comparable sales (if synced).
    price_q = any(w in low for w in ("price", "worth", "value", "how much", "market")) or any(
        w in m for w in ("سعر", "قيمة", "كم سعر", "بكم"))
    if price_q:
        try:
            import dubai_pulse as _dp
            area = q.get("area") or ""
            bld = q.get("project") or ""
            c = _dp.comps(area=str(area), building=str(bld)) if (area or bld) else {"count": 0}
            if c.get("count"):
                head = ("حسب آخر تعاملات مسجلة" if ar else "Based on recent registered sales")
                body = (f"~AED {c['median']:,} median ({c['count']} deals, "
                        f"range {c['min']:,}–{c['max']:,})")
                return _hz(f"{head}: {body}." + ("\nتحب تحليل أدق؟" if ar else "\nWant a full breakdown?")), "local:comps"
        except Exception:
            pass

    if rows:
        try:
            import inventory_retrieval as inv
            lines = [inv._fmt_row(r) for r in rows[:3]]
        except Exception:
            lines = []
        if lines:
            head = "عندي هدول المطابقين لطلبك:" if ar else "Here's what I have matching:"
            tail = "\n\nتحب أرسلك تفاصيل أكثر أو أرتبلك معاينة؟" if ar else "\n\nWant more details or a viewing?"
            return _hz(head + "\n" + "\n".join(lines) + tail), "local:inventory"

    if thanks:
        return _hz("العفو، تحت أمرك 🙏" if ar else "You're welcome — anytime 🙏"), "local:thanks"
    if photo:
        return _hz("بشوف الصور المتوفرة عندي وبرسلها لك 👍" if ar else "Let me check the photos I have and send them over 👍"), "local:photo"
    if greet:
        return _hz("هلا 🌟 كيف بقدر أساعدك اليوم؟" if ar else "Hey! 🌟 How can I help you today?"), "local:greet"
    if q.get("area") or q.get("bedrooms") or q.get("budget"):
        return _hz("خليني أتأكد من التوفر وأرجعلك بأسرع وقت." if ar else "Let me check availability and get right back to you."), "local:no_match"

    return _hz("وصلني — بشيّك وبرجعلك 👍" if ar else "Got it — I'll check and get back to you shortly 👍"), "local:ack"
