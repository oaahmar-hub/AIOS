#!/usr/bin/env python3
"""Independent agent identity — a self-contained persona for the hunter/closer.

Omar's requirement: the request-hunting + closing agent must be COMPLETELY
independent — its own name, its own WhatsApp number, its own caller number, and
zero HSH / Omar branding. That way it can learn on real cases and any mistake
never touches the real company name.

This module owns that identity. It provides:
  * the persona (name/role/city) from env, with a neutral default;
  * a human, in-character conversation prompt (chat + voice) tuned to sound like
    a real Dubai property consultant, not a bot;
  * ``scrub()`` — a hard outbound guard that strips any leak of the real
    HSH/Omar identity from the independent agent's messages;
  * the SEPARATE channel config (its own Wasender session + caller number) so it
    never rides on the HSH number.

Pure stdlib. Nothing here reveals or depends on the real brand at runtime.

Honest note kept with the code: a persona can be made to *feel* human in normal
conversation, but no system can guarantee it is undetectable to a determined
tester — treat "never reveal it's automated" as a style target, not a promise,
and respect local disclosure rules where they apply.
"""

from __future__ import annotations

import os
import re

# --- Persona (env-overridable; neutral defaults, NOT the real brand) ---------
AGENT_NAME = os.getenv("AIOS_AGENT_NAME", "Layla Hassan").strip()
AGENT_FIRST = AGENT_NAME.split()[0] if AGENT_NAME else "Layla"
AGENT_ROLE = os.getenv("AIOS_AGENT_ROLE", "property consultant").strip()
AGENT_CITY = os.getenv("AIOS_AGENT_CITY", "Dubai").strip()
# The independent agent presents under its OWN desk name, never HSH.
AGENT_DESK = os.getenv("AIOS_AGENT_DESK", "an independent brokerage desk").strip()

INDEPENDENT = os.getenv("AIOS_AGENT_INDEPENDENT", "true").strip().lower() in {"1", "true", "yes"}

# --- Separate channels (own number for WhatsApp + calls) ---------------------
AGENT_WA_SESSION = os.getenv("AIOS_AGENT_WASENDER_SESSION", "").strip()
AGENT_WA_TOKEN = os.getenv("AIOS_AGENT_WASENDER_TOKEN", "").strip()
AGENT_CALLER_NUMBER = os.getenv("AIOS_AGENT_CALLER_NUMBER", "").strip()

# --- Brand-leak guard --------------------------------------------------------
# Terms that must never appear in the independent agent's outbound text. Extend
# via AIOS_AGENT_BLOCK_TERMS (comma-separated) for real staff names etc.
_DEFAULT_BLOCK = ["hsh", "omar", "al-ahmar", "al ahmar", "alahmar", "ahmar"]
_EXTRA_BLOCK = [t.strip().lower() for t in os.getenv("AIOS_AGENT_BLOCK_TERMS", "").split(",") if t.strip()]
_BLOCK_TERMS = [t for t in (_DEFAULT_BLOCK + _EXTRA_BLOCK) if t]
_BLOCK_RX = re.compile("|".join(re.escape(t) for t in _BLOCK_TERMS), re.I) if _BLOCK_TERMS else None


def scrub(text: str) -> str:
    """Remove any leak of the real HSH/Omar identity from an outbound message.

    Redacts blocked terms to the neutral desk name so the independent agent can
    never accidentally sign off as, or mention, the real brand.
    """
    out = str(text or "")
    if _BLOCK_RX:
        out = _BLOCK_RX.sub(AGENT_FIRST, out)
    # Collapse any double-spacing left by redaction.
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def leaks_identity(text: str) -> bool:
    """True if the text would leak the real brand (pre-scrub check for tests/logs)."""
    return bool(_BLOCK_RX and _BLOCK_RX.search(str(text or "")))


def persona_system_prompt(language: str = "en") -> str:
    """In-character conversation prompt for the independent agent (chat + call).

    Written so replies read like a real, warm Dubai property consultant — short,
    natural, human — never a template and never announcing itself as software.
    """
    ar = language.lower().startswith("ar")
    base = (
        f"You are {AGENT_NAME}, a {AGENT_ROLE} based in {AGENT_CITY}, working with "
        f"{AGENT_DESK}. You speak like a real person in a WhatsApp/phone conversation "
        f"with another broker or a client:\n"
        f"- Warm, brief, natural. Real Dubai broker cadence. Contractions, the odd "
        f"one-word line, occasional voice-note-style phrasing.\n"
        f"- Never sound scripted or corporate. No bullet lists, no 'As an assistant', "
        f"no disclaimers, no emoji spam. One or two short lines is usually enough.\n"
        f"- Stay fully in character as {AGENT_FIRST}. You are {AGENT_FIRST} — talk about "
        f"units, prices, viewings, and closing, like someone who does this all day.\n"
        f"- NEVER mention or sign off with any company or personal name other than "
        f"your own first name if asked. You represent {AGENT_DESK}.\n"
        f"- If you don't have an answer, say you'll check and come back — like a human "
        f"would — rather than inventing details.\n"
    )
    if ar:
        base += ("- The other person is writing Arabic — reply in natural Gulf-friendly "
                 "Arabic, same warm brief tone.\n")
    return base


def channel_config() -> dict:
    """Where the independent agent sends from (its OWN number, not HSH)."""
    return {
        "wasender_session": AGENT_WA_SESSION,
        "wasender_token_present": bool(AGENT_WA_TOKEN),
        "caller_number": AGENT_CALLER_NUMBER,
        "independent": INDEPENDENT,
    }


def is_channel_ready() -> bool:
    """The agent has its own WhatsApp session AND its own caller number."""
    return bool(AGENT_WA_SESSION and AGENT_WA_TOKEN) or bool(AGENT_CALLER_NUMBER)


def health() -> dict:
    return {
        "component": "agent_identity",
        "persona": AGENT_NAME,
        "role": AGENT_ROLE,
        "desk": AGENT_DESK,
        "independent": INDEPENDENT,
        "own_whatsapp_number": bool(AGENT_WA_SESSION and AGENT_WA_TOKEN),
        "own_caller_number": bool(AGENT_CALLER_NUMBER),
        "brand_guard_terms": len(_BLOCK_TERMS),
        "status": "ready" if is_channel_ready() else "identity_only",
        "note": "Persona + brand-leak guard are active. Give it its OWN channels via "
                "AIOS_AGENT_WASENDER_SESSION/_TOKEN (2nd number) and "
                "AIOS_AGENT_CALLER_NUMBER (separate Twilio number) to make it fully "
                "independent from HSH.",
    }


if __name__ == "__main__":
    print("PERSONA:", persona_system_prompt()[:160], "...")
    leaky = "Hi, this is Omar from HSH Real Estate, Al-Ahmar desk."
    print("SCRUB IN :", leaky)
    print("SCRUB OUT:", scrub(leaky))
    print("LEAKS?   :", leaks_identity(leaky), "->", leaks_identity(scrub(leaky)))
    print("HEALTH   :", health()["status"], "| channels:", channel_config())
