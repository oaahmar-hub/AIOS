#!/usr/bin/env python3
"""Twilio WhatsApp channel — one Twilio number for the independent agent.

Lets the independent agent send/receive WhatsApp through Twilio's official
WhatsApp Business API, so a SINGLE Twilio number runs both the agent's WhatsApp
(this module) and its voice calls (:mod:`voice_call_agent`). Official + Meta-
sanctioned, so it won't get banned like an unofficial link.

stdlib only (urllib + basic auth), matching the rest of the pip-free server.
Fully gated: if the number/creds aren't set it's a no-op that reports why via
:func:`health`, and the existing Wasender path is untouched.

Environment:
  TWILIO_ACCOUNT_SID    (shared with voice_call_agent)
  TWILIO_AUTH_TOKEN     (shared; kept only in Railway env)
  TWILIO_WHATSAPP_FROM  the WhatsApp-enabled Twilio number in E.164 (defaults to
                        TWILIO_CALLER_NUMBER so ONE number does WhatsApp + calls)

Outbound text is brand-scrubbed via agent_identity so the real HSH/Omar name
never rides out on the independent agent's messages.
"""

from __future__ import annotations

import base64
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
# One number for both: WhatsApp sender defaults to the voice caller number.
_FROM = (os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
         or os.getenv("TWILIO_CALLER_NUMBER", "").strip())

_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def is_configured() -> bool:
    return bool(_SID and _TOKEN and _FROM)


def _basic_auth() -> str:
    return "Basic " + base64.b64encode(f"{_SID}:{_TOKEN}".encode("utf-8")).decode("ascii")


def _wa(num: str) -> str:
    num = (num or "").strip()
    if num.startswith("whatsapp:"):
        return num
    if not num.startswith("+"):
        num = "+" + "".join(ch for ch in num if ch.isdigit())
    return "whatsapp:" + num


def send(to: str, text: str) -> tuple[bool, str]:
    """Send a WhatsApp message from the agent's Twilio number. Never raises."""
    if not is_configured():
        return False, "twilio_whatsapp_not_configured"
    # Brand-leak guard: never let the real HSH/Omar identity ride out.
    try:
        import agent_identity as _ai
        text = _ai.scrub(text)
    except Exception:
        pass
    if not to or not text:
        return False, "missing_to_or_text"
    body = urlencode({"From": _wa(_FROM), "To": _wa(to), "Body": text}).encode("utf-8")
    req = Request(_API.format(sid=_SID), data=body,
                  headers={"Authorization": _basic_auth(),
                           "Content-Type": "application/x-www-form-urlencoded"},
                  method="POST")
    try:
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return True, f"{resp.status}:{data.get('sid', 'sent')}"
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200] if hasattr(exc, "read") else ""
        return False, f"http_error:{exc.code}:{detail}"
    except URLError as exc:
        return False, f"url_error:{exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"error:{exc}"


def parse_inbound(form: dict) -> dict:
    """Normalize a Twilio inbound WhatsApp webhook (form-encoded) to {from,text}."""
    frm = str(form.get("From") or "").replace("whatsapp:", "").strip()
    text = str(form.get("Body") or "").strip()
    return {"from": frm, "text": text, "wa_id": "".join(ch for ch in frm if ch.isdigit())}


def health() -> dict:
    return {
        "component": "twilio_whatsapp",
        "sid_present": bool(_SID),
        "token_present": bool(_TOKEN),
        "from_present": bool(_FROM),
        "one_number_both": bool(_FROM and _FROM == os.getenv("TWILIO_CALLER_NUMBER", "").strip()),
        "status": "ok" if is_configured() else "not_configured",
        "note": "Set TWILIO_AUTH_TOKEN and a WhatsApp-enabled Twilio number as "
                "TWILIO_CALLER_NUMBER (used for BOTH WhatsApp + calls). Register the "
                "number as a WhatsApp sender in the Twilio console (Meta verify).",
    }


if __name__ == "__main__":
    print("HEALTH:", health())
    print("wa fmt:", _wa("971500000000"), _wa("+15551234567"), _wa("whatsapp:+1"))
    print("inbound:", parse_inbound({"From": "whatsapp:+971501234567", "Body": "looking for 2br marina"}))
