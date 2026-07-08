#!/usr/bin/env python3
"""Humanize outbound WhatsApp replies and keep media promises honest.

Three deterministic jobs, all pure-stdlib, none may ever raise into the
reply path:

1. ``humanize(text)`` — strip the AI fingerprint from an LLM reply so it
   reads like a busy human typing on WhatsApp: no assistant-isms, no
   corporate transition words, no markdown bullets/headers, WhatsApp-style
   bold, no sign-off boilerplate. Works for English and Arabic.
2. ``prompt_rules()`` — the system-prompt block that prevents most of the
   fingerprint at the source (cheaper than fixing it after).
3. ``media_intent(text)`` / ``enforce_media_honesty(reply, media_sent)`` —
   detect photo/plan/video/location requests (EN+AR) and, when we did NOT
   actually send media, rewrite any "attached/here is the photo" claim into
   an honest "I'll check and send it" in the reply's own language.

Nothing here invents content: it only removes, rewrites, or constrains.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 1. AI-fingerprint removal
# ---------------------------------------------------------------------------

# Whole-line openers/closers an assistant writes but a human never does.
_LINE_KILLERS = [
    r"^\s*(sure|certainly|of course|absolutely|great question|good question)[!,.:]\s*",
    r"^\s*as an ai\b.*$",
    r"^\s*i'?m an ai\b.*$",
    r"^\s*i am an ai\b.*$",
    r"^\s*(i )?hope (this|that) helps[!. ]*$",
    r"^\s*feel free to (reach out|ask|contact me).*$",
    r"^\s*(please )?(don'?t hesitate|do not hesitate) to.*$",
    r"^\s*let me know if (you have any|there'?s anything).*$",
    r"^\s*is there anything else (i can|you'?d like).*$",
    r"^\s*i apologi[sz]e for any (confusion|inconvenience).*$",
    r"^\s*بصفتي ذكاء(?:ً)? اصطناعي.*$",
    r"^\s*أنا ذكاء اصطناعي.*$",
    r"^\s*لا تتردد في التواصل.*$",
    r"^\s*أتمنى أن يكون هذا مفيد(?:ًا)?.*$",
]
_LINE_KILLER_RES = [re.compile(p, re.IGNORECASE) for p in _LINE_KILLERS]

# In-sentence assistant vocabulary swapped for plain speech.
_PHRASE_SWAPS = [
    (re.compile(r"\bas of my (last )?knowledge( update)?[^,.]*[,.]?\s*", re.I), ""),
    (re.compile(r"\bit(?:'s| is) (important|worth) (to note|noting) that\b\s*", re.I), ""),
    (re.compile(r"\bplease note that\b\s*", re.I), ""),
    (re.compile(r"\bkindly note that\b\s*", re.I), ""),
    (re.compile(r"\bfurthermore,?\s*", re.I), "also "),
    (re.compile(r"\bmoreover,?\s*", re.I), "also "),
    (re.compile(r"\badditionally,?\s*", re.I), "also "),
    (re.compile(r"\bin conclusion,?\s*", re.I), ""),
    (re.compile(r"\bdelve into\b", re.I), "look at"),
    (re.compile(r"\bnavigate the landscape of\b", re.I), "handle"),
    (re.compile(r"\bcutting[- ]edge\b", re.I), "latest"),
    (re.compile(r"\bgame[- ]changer\b", re.I), "big deal"),
    (re.compile(r"\bseamlessly\b", re.I), "smoothly"),
    (re.compile(r"\bleverage\b", re.I), "use"),
    (re.compile(r"\butilize\b", re.I), "use"),
    (re.compile(r"\bI would be (more than )?happy to\b", re.I), "I can"),
]

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
_HEADER_RE = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_BOLD_MD_RE = re.compile(r"\*\*(.+?)\*\*")
_EMDASH_RE = re.compile(r"\s*—\s*")


def humanize(text: str) -> str:
    """Return the reply with the AI fingerprint removed. Never raises."""
    try:
        if not text:
            return text
        out = str(text)
        # markdown -> WhatsApp: **bold** becomes *bold*, headers/bullets flatten
        out = _BOLD_MD_RE.sub(r"*\1*", out)
        out = _HEADER_RE.sub("", out)
        out = _BULLET_RE.sub("", out)
        out = _EMDASH_RE.sub(" - ", out)
        # kill assistant boilerplate lines
        lines = []
        for line in out.splitlines():
            killed = False
            for rx in _LINE_KILLER_RES:
                if rx.sub("", line).strip() != line.strip():
                    line = rx.sub("", line)
                    killed = not line.strip()
                    if killed:
                        break
            if not killed:
                lines.append(line)
        out = "\n".join(lines)
        for rx, repl in _PHRASE_SWAPS:
            out = rx.sub(repl, out)
        # collapse the whitespace the removals leave behind
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        # a human doesn't start a WhatsApp message with a comma or lowercase glue
        out = re.sub(r"^[,;:\s]+", "", out)
        return out or str(text).strip()
    except Exception:  # pragma: no cover - defensive
        return text


def prompt_rules() -> str:
    """System-prompt block that stops the AI fingerprint at the source."""
    return (
        "WHATSAPP HUMAN STYLE - non-negotiable:\n"
        "- You are Omar texting on WhatsApp, not an assistant writing an essay.\n"
        "- Short messages. 1-3 sentences unless real data needs more.\n"
        "- No bullet lists, no headers, no numbered points, no sign-offs.\n"
        "- Never say or imply you are an AI, bot, assistant, or system.\n"
        "- No filler: never 'hope this helps', 'feel free', 'don't hesitate', "
        "'it's important to note', 'furthermore', 'as of my knowledge'.\n"
        "- Mirror the customer's language (Arabic in -> Arabic out, same dialect "
        "register). Mirror their energy; vary sentence rhythm like a person.\n"
        "- At most one question per message.\n"
        "- Facts only from the context you were given. Missing info -> say you'll "
        "check and confirm, like a busy broker would, then stop."
    )


# ---------------------------------------------------------------------------
# 2. Acknowledgement gating - don't answer an essay to "ok"
# ---------------------------------------------------------------------------

_ACK_TOKENS = {
    "ok", "okay", "okey", "kk", "k", "tmam", "tamam", "done", "thanks", "thank you",
    "thx", "ty", "great", "perfect", "nice", "cool", "good", "noted", "sure",
    "تمام", "اوك", "أوك", "اوكي", "طيب", "ماشي", "شكرا", "شكراً", "مشكور", "تسلم",
    "ممتاز", "جميل", "حلو", "ينعم", "يعطيك العافية",
}
_EMOJI_ONLY_RE = re.compile(
    r"^[\s\U0001F300-\U0001FAFF☀-➿⬀-⯿️‍👍🙏❤️]+$"
)


def is_plain_ack(text: str) -> bool:
    """True when the inbound message is a bare acknowledgement/emoji."""
    try:
        t = (text or "").strip().lower().strip("!.,~ ")
        if not t:
            return False
        if _EMOJI_ONLY_RE.match(t):
            return True
        return t in _ACK_TOKENS
    except Exception:  # pragma: no cover - defensive
        return False


ACK_REPLY_EN = "👍"
ACK_REPLY_AR = "👍"


# ---------------------------------------------------------------------------
# 3. Media honesty
# ---------------------------------------------------------------------------

_MEDIA_WORDS_RE = re.compile(
    r"\b(photo|photos|pic|pics|picture|pictures|image|images|video|videos|"
    r"brochure|floor ?plan|floorplan|layout|master ?plan|location pin|"
    r"send (me )?the (location|link))\b"
    r"|صور|صورة|الصور|فيديو|بروشور|مخطط|المخطط|اللوكيشن|لوكيشن|الموقع على الخريطة",
    re.IGNORECASE,
)

# Reply-side claims that media is attached/being sent right now.
_FALSE_ATTACH_RE = re.compile(
    r"(attached|here (is|are) the (photo|photos|picture|pictures|plan|brochure|video)s?|"
    r"sending (you )?the (photo|photos|picture|pictures|plan|brochure|video)s? now|"
    r"i(?:'ve| have) (sent|attached)|"
    r"مرفق|أرفقت|ها هي الصور|أرسلت لك الصور)",
    re.IGNORECASE,
)

_AR_RE = re.compile(r"[؀-ۿ]")

HONEST_MEDIA_EN = "I'll pull the photos and plans and send them to you shortly."
HONEST_MEDIA_AR = "بجيب لك الصور والمخططات وأرسلها لك قريباً إن شاء الله."


def media_intent(text: str) -> bool:
    """True when the customer is asking for photos/plans/video/location media."""
    try:
        return bool(_MEDIA_WORDS_RE.search(text or ""))
    except Exception:  # pragma: no cover - defensive
        return False


def media_prompt_rule() -> str:
    """Extra system-prompt rule when the customer asked for media."""
    return (
        "MEDIA REQUEST: the customer asked for photos/plans/video/location. "
        "You CANNOT attach media in this reply and no media exists in your "
        "context. Do NOT claim anything is attached or being sent now, and do "
        "NOT describe imaginary photos. Say naturally that you'll get the "
        "photos/plans and send them shortly, then move the conversation forward."
    )


def enforce_media_honesty(reply: str, media_sent: bool, inbound_text: str = "") -> str:
    """If we did not actually send media, remove any 'attached' claim.

    Deterministic guard of last resort behind the prompt rule: a reply that
    claims media was sent when ``media_sent`` is False gets that claim replaced
    with the honest line, in the reply's own language. Never raises.
    """
    try:
        if media_sent or not reply:
            return reply
        if not _FALSE_ATTACH_RE.search(reply):
            return reply
        honest = HONEST_MEDIA_AR if _AR_RE.search(reply) or _AR_RE.search(inbound_text or "") else HONEST_MEDIA_EN
        cleaned = _FALSE_ATTACH_RE.sub("", reply)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip(" .,\n")
        if cleaned:
            return f"{cleaned}. {honest}" if not cleaned.endswith((".", "!", "؟", "?")) else f"{cleaned} {honest}"
        return honest
    except Exception:  # pragma: no cover - defensive
        return reply
