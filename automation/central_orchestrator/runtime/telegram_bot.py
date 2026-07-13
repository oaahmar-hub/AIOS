#!/usr/bin/env python3
"""AIOS Telegram bot — permit / link / building → owner details.

Mirrors the workflow Omar already knows (paste a permit number or a Property
Finder / Bayut link, get the property + owner back), but powered by the AIOS
owner index. Pure stdlib (urllib long-poll of the Telegram Bot API) so it runs
on the same pip-free Railway image, as a daemon thread in the server or stand-
alone. Gated entirely on TELEGRAM_BOT_TOKEN — inert until a token is set.

It reveals phone numbers (this is the operator's own bot). It is honest when a
property isn't in the data — exactly like the real DLD bots, which also return
"could not find this property" on units DLD doesn't hold.
"""

from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_API = "https://api.telegram.org/bot{token}/{method}"
_PERMIT_RE = re.compile(r"^\s*\d[\d\s-]{4,}\s*$")
_URL_RE = re.compile(r"https?://\S+", re.I)


def is_configured() -> bool:
    return bool(BOT_TOKEN)


def _call(method: str, params: dict, timeout: int = 30) -> dict:
    body = urlencode(params).encode("utf-8")
    req = Request(_API.format(token=BOT_TOKEN, method=method), data=body,
                  headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, Exception):  # pragma: no cover - network
        return {"ok": False}


def _fmt_owner(o: dict) -> str:
    bits = []
    if o.get("name"):
        bits.append("👤 " + str(o["name"]))
    line2 = []
    if o.get("building"):
        line2.append(str(o["building"]))
    if o.get("unit"):
        line2.append("unit " + str(o["unit"]))
    if o.get("area"):
        line2.append(str(o["area"]))
    if line2:
        bits.append("🏢 " + " · ".join(line2))
    if o.get("phone"):
        bits.append("📱 " + str(o["phone"]))
    if o.get("country"):
        bits.append("🌍 " + str(o["country"]))
    if o.get("property_number"):
        bits.append("🔑 permit " + str(o["property_number"]))
    return "\n".join(bits)


def lookup_reply(text: str) -> str:
    """Turn an inbound message into an owner reply. Never raises."""
    t = (text or "").strip()
    if not t:
        return "Send me a permit number, a building/area name, or a Property Finder / Bayut link."
    if t.lower() in ("/start", "start", "hi", "hello"):
        return ("👋 Send me one of:\n"
                "• a *permit number* (e.g. 7118957400)\n"
                "• a *Property Finder / Bayut link*\n"
                "• a *building or area* name\n\n"
                "I'll return the registered owner and phone.")
    try:
        import owner_lookup as _ol
    except Exception:
        return "System not ready — owner index unavailable."
    owners = []
    try:
        m = _URL_RE.search(t)
        if m:
            import portal_extract as _pe
            info = _pe.extract(m.group(0))
            if not info.get("ok"):
                return ("That link isn't a Property Finder / Bayut / Dubizzle listing. "
                        "Paste a listing link, or send the permit number or building name.")
            res = _ol.lookup(building=info.get("building", ""), area=info.get("area", ""),
                             reveal=True, limit=10)
            owners = res.get("owners", [])
            head = f"📍 {info.get('building','')} · {info.get('area','')}".strip(" ·")
        elif _PERMIT_RE.match(t):
            permit = re.sub(r"\D", "", t)
            res = _ol.lookup(property_number=permit, reveal=True, limit=10)
            owners = res.get("owners", [])
            head = f"🔑 Permit {permit}"
        else:
            res = _ol.lookup(q=t, reveal=True, limit=10)
            owners = res.get("owners", [])
            head = f"🔎 {t}"
    except Exception as exc:  # pragma: no cover - defensive
        return "Lookup error — try again, or send the building name."

    if not owners:
        return ("❌ Not found in the DLD data I have.\n"
                "Try the exact building name, or paste a Property Finder / Bayut link. "
                "(Newer/off-plan units aren't in the registry yet.)")
    parts = [head, ""]
    for i, o in enumerate(owners[:5], 1):
        parts.append(f"— Owner {i} —")
        parts.append(_fmt_owner(o))
        parts.append("")
    if len(owners) > 5:
        parts.append(f"…and {len(owners)-5} more on record.")
    return "\n".join(parts).strip()


def run_forever() -> None:
    """Long-poll the Telegram Bot API and answer messages. Runs until killed."""
    if not is_configured():
        return
    offset = 0
    while True:
        try:
            r = _call("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            for upd in r.get("result", []) or []:
                offset = max(offset, upd.get("update_id", 0) + 1)
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = (msg.get("chat") or {}).get("id")
                text = msg.get("text") or msg.get("caption") or ""
                if chat_id is None:
                    continue
                reply = lookup_reply(text)
                _call("sendMessage", {"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"})
        except Exception:  # pragma: no cover - never die
            time.sleep(3)


def health() -> dict:
    return {
        "component": "telegram_bot",
        "configured": is_configured(),
        "status": "ready" if is_configured() else "no_token",
        "note": "Set TELEGRAM_BOT_TOKEN (from @BotFather) to switch the bot on. "
                "Answers permit / link / building with the real owner + phone.",
    }


if __name__ == "__main__":
    if is_configured():
        print("AIOS Telegram bot polling…")
        run_forever()
    else:
        print("HEALTH:", health())
        print("SAMPLE reply (permit):\n", lookup_reply("Princess Tower"))
