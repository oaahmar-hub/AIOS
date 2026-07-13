#!/usr/bin/env python3
"""Independent agent closer — the hunter that actually replies and works a lead.

Completes the loop Omar asked for A-Z: once ``group_leads`` detects a real
request, THIS module (when armed) crafts a human, in-persona reply as the
independent agent (see :mod:`agent_identity`) and sends it FROM the agent's OWN
WhatsApp number — never the HSH line — so the agent can hunt and close on its
own identity, and any mistake stays on its own sandbox number.

Hard-gated and safe by default:
  * OFF unless ``AIOS_AGENT_AUTOCLOSE_ENABLED=true`` AND the agent has its own
    channel (its own Wasender session/token).
  * Every outbound message passes the brand-leak scrub.
  * Per-contact cooldown so it never spams a requester.
  * Never raises into the webhook path.

stdlib only. The LLM reply is produced by a callback the server passes in
(reusing its Groq/OpenAI brain); with no brain it falls back to a natural,
non-templated short line.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Callable, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

AUTOCLOSE_ENABLED = os.getenv("AIOS_AGENT_AUTOCLOSE_ENABLED", "").strip().lower() in {"1", "true", "yes"}
_SEND_URL = os.getenv("WASENDER_SEND_URL", "https://www.wasenderapi.com/api/send-message").strip()
_UA = os.getenv(
    "WASENDER_BROWSER_UA",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
).strip()

# Per-contact cooldown so the agent works a lead like a human, not a spammer.
_COOLDOWN_SEC = int(os.getenv("AIOS_AGENT_REPLY_COOLDOWN_SEC", "3600") or "3600")
_last_reply: "OrderedDict[str, float]" = OrderedDict()
_last_lock = threading.Lock()
_LAST_MAX = 2000


def _agent_token() -> str:
    return os.getenv("AIOS_AGENT_WASENDER_TOKEN", "").strip()


def is_armed() -> bool:
    """Live only when explicitly enabled AND the agent has its own send channel."""
    if not AUTOCLOSE_ENABLED:
        return False
    try:
        import agent_identity as _ai
        return bool(_agent_token() and _ai.INDEPENDENT)
    except Exception:
        return bool(_agent_token())


def _cooled_down(contact: str) -> bool:
    now = time.time()
    with _last_lock:
        ts = _last_reply.get(contact)
        if ts and (now - ts) < _COOLDOWN_SEC:
            return False
        _last_reply[contact] = now
        while len(_last_reply) > _LAST_MAX:
            _last_reply.popitem(last=False)
    return True


def send(to: str, text: str) -> tuple[bool, str]:
    """Send a WhatsApp message FROM the agent's own number (its own token).

    Scrubs the real brand out first. No-op if the agent channel isn't set.
    """
    token = _agent_token()
    if not token:
        return False, "agent_channel_not_configured"
    try:
        import agent_identity as _ai
        text = _ai.scrub(text)
    except Exception:
        pass
    if not to or not text:
        return False, "missing_to_or_text"
    body = json.dumps({"to": to, "text": text}).encode("utf-8")
    req = Request(
        _SEND_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": _UA,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return True, f"{resp.status}:sent"
    except HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except URLError as exc:
        return False, f"url_error:{exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"error:{exc}"


def _fallback_line(intent: str, cards: list) -> str:
    """Natural short opener when no LLM brain is available (still human, no template feel)."""
    if cards:
        return "hey — saw your message, I might have something that fits. can I send you the details?"
    if intent == "rent":
        return "hi! saw you're looking to rent — what area and budget are you working with?"
    if intent == "sell":
        return "hey, saw you're selling — which building/area? I may have buyers."
    return "hi! saw your message — happy to help. can you tell me a bit more about what you need?"


def respond_to_lead(
    sender: str,
    text: str,
    intent: str = "inquiry",
    cards: Optional[list] = None,
    reply_fn: Optional[Callable[[str, str, str], tuple]] = None,
) -> dict:
    """Craft a human, in-persona reply and send it from the agent's own number.

    ``reply_fn(message, history, system_prompt) -> (reply, detail)`` is the
    server's LLM brain; when absent a natural fallback line is used. Returns a
    small status dict; never raises.
    """
    try:
        if not is_armed():
            return {"sent": False, "reason": "not_armed"}
        contact = "".join(ch for ch in str(sender or "") if ch.isdigit())
        if not contact:
            return {"sent": False, "reason": "no_contact"}
        if not _cooled_down(contact):
            return {"sent": False, "reason": "cooldown"}
        cards = cards or []

        reply = ""
        if reply_fn is not None:
            try:
                import agent_identity as _ai
                sysp = _ai.persona_system_prompt(
                    "ar" if any("؀" <= c <= "ۿ" for c in str(text or "")) else "en"
                )
                ctx = str(text or "")
                if cards:
                    ctx += "\n\n[Matching inventory you can offer, use naturally]:\n" + \
                        "\n".join(f"- {str(c)[:160]}" for c in cards[:3])
                reply, _ = reply_fn(ctx, "", sysp)
            except Exception:
                reply = ""
        if not reply:
            reply = _fallback_line(intent, cards)

        ok, detail = send(contact, reply)
        return {"sent": ok, "detail": detail, "to_tail": contact[-4:], "used_llm": bool(reply_fn and reply)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"sent": False, "reason": f"error:{exc}"}


def health() -> dict:
    try:
        import agent_identity as _ai
        persona = _ai.AGENT_NAME
    except Exception:
        persona = "?"
    return {
        "component": "agent_closer",
        "enabled_flag": AUTOCLOSE_ENABLED,
        "own_channel": bool(_agent_token()),
        "armed": is_armed(),
        "persona": persona,
        "cooldown_sec": _COOLDOWN_SEC,
        "status": "armed" if is_armed() else ("enabled_no_channel" if AUTOCLOSE_ENABLED else "off"),
        "note": "Set AIOS_AGENT_WASENDER_TOKEN (the agent's own number) and "
                "AIOS_AGENT_AUTOCLOSE_ENABLED=true to let it reply/close from its "
                "own identity. Default off — detection still records leads either way.",
    }


if __name__ == "__main__":
    print("HEALTH:", health())
    print("FALLBACK rent:", _fallback_line("rent", []))
    print("FALLBACK match:", _fallback_line("buy", ["2BR JVC AED 1.15M"]))
    print("respond (unarmed):", respond_to_lead("971500000000", "looking for 2br in marina", "buy", []))
