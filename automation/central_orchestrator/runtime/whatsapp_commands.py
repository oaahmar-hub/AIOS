#!/usr/bin/env python3
"""WhatsApp command center — text AIOS, get instant answers.

When the OWNER (AIOS_ALERT_PHONE) messages the AIOS number, these commands run
the real tools and reply in WhatsApp — so the phone he already has open all day
IS the command center. No app, no browser.

Commands (case-insensitive, EN + a few AR triggers):
  owner <building|permit>   -> real owner(s) + phone   (owner sees full numbers)
  find  <query>             -> units across all Dubai areas
  market                    -> today's DLD market read
  comps <building|area>     -> comparable sale prices (needs DLD tx access)
  renewals [days]           -> expiring tenancies -> leads
  <paste a Bayut/PF link>   -> owner + asking-vs-market
  help                      -> this list

Owner-only (never exposes owner phones to customers). Pure stdlib; never raises.
"""

from __future__ import annotations

import os
import re

OWNER_PHONE = re.sub(r"\D", "", os.getenv("AIOS_ALERT_PHONE", ""))


def is_owner(sender_digits: str) -> bool:
    s = re.sub(r"\D", "", str(sender_digits or ""))
    if not s or not OWNER_PHONE:
        return False
    return s[-9:] == OWNER_PHONE[-9:]


def _fmt_owners(owners: list, limit: int = 5) -> str:
    lines = []
    for o in owners[:limit]:
        bits = [o.get("name", "Owner"), o.get("phone", "")]
        tail = " · ".join(x for x in [o.get("area", ""), o.get("building", ""),
                                      o.get("unit", "") and ("unit " + o["unit"])] if x)
        lines.append("• " + " — ".join(x for x in bits if x) + (f"\n  {tail}" if tail else ""))
    return "\n".join(lines)


HELP = (
    "AIOS commands:\n"
    "• owner <building or permit>\n"
    "• find <query>  (e.g. find 2BR Business Bay)\n"
    "• market\n"
    "• comps <building/area>\n"
    "• renewals [days]\n"
    "• paste a Bayut/PF link\n"
    "• help"
)


def handle(text: str) -> tuple:
    """Return (reply_text | None, detail). None = not a command (let the brain reply)."""
    t = (text or "").strip()
    if not t:
        return None, "empty"
    low = t.lower()

    # A pasted portal link -> owner + asking-vs-market.
    m = re.search(r"https?://\S+", t)
    if m:
        url = m.group(0)
        try:
            import owner_lookup as ol, portal_extract as pe
            info = pe.extract(url)
            owners = ol.lookup(building=info.get("building", ""), area=info.get("area", ""),
                               reveal=True, limit=5).get("owners", []) if info.get("ok") else []
        except Exception:
            info, owners = {}, []
        ask = ""
        try:
            import listing_price as lp
            a = lp.assess(url)
            if a.get("asking_price"):
                ask = f"\nAsking: AED {a['asking_price']:,} ({a.get('verdict','')})"
        except Exception:
            pass
        head = f"{info.get('building') or info.get('area') or 'Listing'} ({info.get('portal','')})"
        body = _fmt_owners(owners) if owners else "No owner on file for that."
        return f"{head}{ask}\n\n{body}", "cmd:link"

    def arg(*prefixes):
        for p in prefixes:
            if low.startswith(p):
                return t[len(p):].strip(" :")
        return None

    if low in ("help", "menu", "commands", "?"):
        return HELP, "cmd:help"

    if low in ("market", "market?", "السوق", "market update"):
        try:
            import market_index as mi
            return "📈 " + (mi.brief("en") or "market data unavailable"), "cmd:market"
        except Exception:
            return "market data unavailable", "cmd:market"

    q = arg("owner ", "owners ", "مالك ", "اونر ")
    if q is not None:
        try:
            import owner_lookup as ol
            permit = bool(re.fullmatch(r"[A-Za-z0-9\-/]{6,}", q) and re.search(r"\d", q))
            r = ol.lookup(property_number=q, reveal=True, limit=6) if permit else ol.lookup(building=q, reveal=True, limit=6)
            owners = r.get("owners", [])
            return (f"Owners for '{q}':\n{_fmt_owners(owners)}" if owners
                    else f"No owner on file for '{q}'."), "cmd:owner"
        except Exception as e:
            return f"owner lookup error: {e}", "cmd:owner"

    q = arg("find ", "unit ", "units ", "search ", "وحدة ")
    if q is not None:
        try:
            import owner_lookup as ol
            units = ol.search_units(query=q, limit=8)
            if not units:
                return f"No units found for '{q}'.", "cmd:find"
            lines = [f"• {u.get('building','')} — {u.get('area','')}"
                     + (f" · unit {u['unit']}" if u.get("unit") else "") for u in units]
            return f"Units for '{q}':\n" + "\n".join(lines), "cmd:find"
        except Exception as e:
            return f"find error: {e}", "cmd:find"

    q = arg("comps ", "comp ", "price ", "سعر ")
    if q is not None:
        try:
            import dubai_pulse as dp
            c = dp.comps(building=q, area=q)
            if not c.get("count"):
                return (f"No comparable sales for '{q}' yet (needs DLD transactions access)."), "cmd:comps"
            return (f"Comps '{q}': ~AED {c['median']:,} median · {c['count']} deals · "
                    f"range {c['min']:,}–{c['max']:,}"), "cmd:comps"
        except Exception as e:
            return f"comps error: {e}", "cmd:comps"

    if low.startswith("renewal"):
        days = 60
        mm = re.search(r"(\d{1,3})", low)
        if mm:
            days = int(mm.group(1))
        try:
            import renewal_agent as ra
            r = ra.build_leads(within_days=days, reveal=True, limit=8)
            if not r.get("count"):
                return f"No tenancies expiring in {days} days on file (needs Ejari data).", "cmd:renew"
            lines = [f"• {l.get('building','')} {l.get('unit','')} — ends {l.get('end_date','')}"
                     + (f" · {l['owner']['phone']}" if l.get("owner", {}).get("phone") else "")
                     for l in r["leads"]]
            return f"Expiring ≤{days}d:\n" + "\n".join(lines), "cmd:renew"
        except Exception as e:
            return f"renewals error: {e}", "cmd:renew"

    # Not a recognised command -> let the normal brain handle it.
    return None, "not_command"
