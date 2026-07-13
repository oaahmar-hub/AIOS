#!/usr/bin/env python3
"""Omar Personality Engine v1.

Small deterministic layer that prepares style instructions before a WhatsApp
reply is generated. It does not replace the permission layer or AIOS router; it
adds Omar-style guidance after intent/context are known and before OpenAI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROFILE_PATH = ROOT / "OMAR_PERSONALITY_PROFILE_V1.json"
POLICY_PATH = ROOT / "OMAR_REPLY_POLICY.md"
RELATIONSHIP_BEHAVIOR_PATH = ROOT / "RELATIONSHIP_BEHAVIOR_ENGINE.json"
CONCIERGE_PERSONA_PATH = ROOT / "LEAD_DIGITAL_OPERATIONS_CONCIERGE_PERSONA.md"
SPECIAL_CONTACT_PROFILES = {
    "hassan_kazzabel": {
        "display_name": "Hassan Kazzabel",
        "match_names": ["hassan kazzabel", "hassan kazabr", "hasan hsh brother", "hassan kazabr brother"],
        "match_phones": ["971501900771"],
        "role": "Executive / Inner Circle",
        "relationship": "Friend",
        "tone": "personalized, friendly, humorous, direct, high-trust, Omar-style",
        "data_access_note": "Interaction style only. Does not bypass permission, security, or privacy layers.",
        "first_greeting_ar": "أهلاً وسهلاً أستاذ حسن 😄\nأخيراً تشرفت بالحكي معك.\nأنا AIOS، الموظف الوحيد بالشركة اللي ما بطلب إجازة ولا راتب 😂\nشو الأخبار؟",
        "short_greeting_ar": "هلا أستاذ حسن 😄 شو الأخبار؟",
        "short_greeting_en": "My brother Hassan 😄 tell me.",
    },
    "vetn": {
        "display_name": "Vetn",
        "match_names": ["vetn", "vetn stuff"],
        "match_phones": ["33644655014"],
        "role": "Trusted Internal Contact",
        "relationship": "Staff",
        "tone": "friendly, direct, professional, internal-style",
        "data_access_note": "Interaction style only. Internal knowledge can be handled through existing role/permission rules; privacy restrictions still apply.",
        "short_greeting_ar": "هلا Vetn، تفضل.",
        "short_greeting_en": "Hey Vetn — tell me.",
    },
}

AR = re.compile(r"[\u0600-\u06FF]")
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)
ANGRY_HANDOFF_KEYWORDS = [
    "hate",
    "useless",
    "slow",
    "stupid",
    "fix",
    "angry",
    "terrible",
    "worst",
    "broken",
    "not working",
    "waste",
    "غبي",
    "بطيء",
    "بطي",
    "ما يشتغل",
    "مش شغال",
    "خربان",
    "زفت",
]


def _load_profile() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {}
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _load_concierge_persona() -> str:
    if CONCIERGE_PERSONA_PATH.exists():
        return CONCIERGE_PERSONA_PATH.read_text(encoding="utf-8").strip()
    return (
        "Lead Digital Operations Concierge: retrieve first, confirm with data, "
        "never guess, no robotic filler, and hand off immediately when a data-bearing "
        "request cannot be solved in one turn."
    )


def _load_relationship_behavior() -> dict[str, Any]:
    if not RELATIONSHIP_BEHAVIOR_PATH.exists():
        return {}
    return json.loads(RELATIONSHIP_BEHAVIOR_PATH.read_text(encoding="utf-8"))


def special_contact_profile(contact_context: dict[str, Any] | None = None, sender: str = "") -> dict[str, Any]:
    """Return a contact-specific interaction profile without changing permissions."""
    contact_context = contact_context or {}
    sender_digits = re.sub(r"\D+", "", str(sender or contact_context.get("phone") or ""))
    name_blob = " ".join(
        str(value or "")
        for value in [
            contact_context.get("known_contact_name"),
            contact_context.get("desktop_chat_name"),
            contact_context.get("profile_name"),
        ]
    ).lower()
    for profile_id, profile in SPECIAL_CONTACT_PROFILES.items():
        if sender_digits and sender_digits in set(profile.get("match_phones", [])):
            return {"id": profile_id, **profile}
        if any(alias in name_blob for alias in profile.get("match_names", [])):
            return {"id": profile_id, **profile}
    return {}


def detect_language(text: str) -> str:
    raw = text or ""
    lower = raw.lower()
    has_ar = bool(AR.search(raw))
    has_cyrillic = bool(CYRILLIC.search(raw))
    has_latin = bool(re.search(r"[A-Za-z]", raw))
    german_markers = [
        "guten morgen",
        "guten tag",
        "guten abend",
        "danke",
        "bitte",
        "wie geht",
        "wohnung",
        "miete",
        "kaufen",
    ]
    if has_cyrillic:
        return "russian"
    if any(marker in lower for marker in german_markers):
        return "german"
    if has_ar and has_latin:
        return "mixed"
    if has_ar:
        return "arabic"
    if has_latin:
        return "english"
    return "neutral"


def sentiment_handoff_decision(user_input: str, history: str = "") -> dict[str, Any]:
    """Deterministic frustration gate before normal AI response generation."""
    text = (user_input or "").lower()
    triggers = [keyword for keyword in ANGRY_HANDOFF_KEYWORDS if keyword in text]
    sentiment_score = 10 if triggers else 0
    language = detect_language(user_input)
    if sentiment_score >= 5:
        if language == "arabic":
            message = "وصلت. خليني أرتّبها بشكل واضح."
        else:
            message = "Got it. Let me keep it straightforward."
        return {
            "action": "RESPOND_VIA_AI",
            "message": message,
            "priority": "NORMAL",
            "sentiment_score": sentiment_score,
            "triggers": triggers,
            "history_considered": bool(history),
        }
    return {
        "action": "RESPOND_VIA_AI",
        "message": "Proceed with retrieval-first AIOS response.",
        "priority": "NORMAL",
        "sentiment_score": sentiment_score,
        "triggers": triggers,
        "history_considered": bool(history),
    }


def detect_social_context(text: str, history: str = "") -> dict[str, Any]:
    raw = text or ""
    lower = raw.lower().strip()
    history_lower = (history or "").lower()

    emoji_hits = EMOJI_RE.findall(raw)
    emoji_meaning = "none"
    if any(e in raw for e in ["😅", "😂", "🤣"]):
        emoji_meaning = "laughing_or_light_embarrassment"
    elif any(e in raw for e in ["👍", "✅", "👌"]):
        emoji_meaning = "acknowledgement_or_approval"
    elif any(e in raw for e in ["🔥", "💯"]):
        emoji_meaning = "approval_or_excitement"
    elif emoji_hits and not re.search(r"[\w\u0600-\u06FF]", raw):
        emoji_meaning = "emoji_only_reaction"

    correction_patterns = [
        r"\bthis is\b",
        r"\bnot\b.+\bthis\b",
        r"\bi mean\b",
        r"\bactually\b",
        r"\bcorrection\b",
        r"\bwrong\b",
        r"\bno[, ]",
        r"\bلا\b",
        r"\bمش\b",
        r"\bقصدي\b",
        r"\bيعني\b",
        r"\bهذا\b",
    ]
    is_correction = any(re.search(p, lower) for p in correction_patterns) and len(lower.split()) <= 8

    joke_patterns = [
        r"\bhaha\b",
        r"\blol\b",
        r"\bjust kidding\b",
        r"\bjoke\b",
        r"\bمزح\b",
        r"\bامزح\b",
        r"\bضحك\b",
    ]
    is_joke = any(re.search(p, lower) for p in joke_patterns) or any(e in raw for e in ["😂", "🤣"])

    sarcasm_patterns = [
        r"\byeah right\b",
        r"\bsure\b.*\b😂",
        r"\bاكيد\b.*\b😂",
        r"\bوالله\b.*\b؟",
        r"\bbravo\b",
    ]
    is_sarcasm = any(re.search(p, lower) for p in sarcasm_patterns)

    teasing_patterns = [
        r"\bking\b",
        r"\bboss\b",
        r"\blegend\b",
        r"\bيا ملك\b",
        r"\bحبيبي\b",
        r"\bعمور\b",
        r"\bالغالي\b",
        r"\bيلعب\b",
        r"\bيلعبها\b",
        r"\bwhere have you been\b",
        r"\bmissed in action\b",
        r"\bhow is everything\b",
        r"\bhow'?s everything\b",
        r"\bwhat'?s going on with you\b",
        r"\bوين مختفي\b",
        r"\bوينك\b",
        r"\bمختفي\b",
        r"\bوين هالغيبة\b",
        r"\bوين هالقطعة\b",
    ]
    is_teasing_or_banter = any(re.search(p, lower) for p in teasing_patterns)

    misunderstanding_patterns = [
        r"\bwhat do you mean\b",
        r"\bnot what i meant\b",
        r"\byou misunderstood\b",
        r"\bمش هيك\b",
        r"\bما قصدي\b",
        r"\bفهمتني غلط\b",
    ]
    is_misunderstanding = any(re.search(p, lower) for p in misunderstanding_patterns)

    identity_intro_patterns = [
        r"\bthis is\b",
        r"\bit'?s\b.+\b(me|omar|hasan|zaki)\b",
        r"\bmy name is\b",
        r"\bانا\b",
        r"\bأنا\b",
        r"\bمعك\b",
        r"\bاسمي\b",
    ]
    is_identity_intro = any(re.search(p, lower) for p in identity_intro_patterns) and len(lower.split()) <= 8

    frustration_patterns = [
        r"\bwhy\b.*\bnot\b",
        r"\bnot working\b",
        r"\bagain\b",
        r"\bslow\b",
        r"\bwaste\b",
        r"\bproblem\b",
        r"\bمش شغال\b",
        r"\bليش\b",
        r"\bتأخير\b",
        r"\bخلص\b",
        r"\bمشكلة\b",
        r"\bغلط\b",
    ]
    is_frustration = any(re.search(p, lower) for p in frustration_patterns)

    urgency_patterns = [
        r"\basap\b",
        r"\burgent\b",
        r"\bnow\b",
        r"\bquick\b",
        r"\btoday\b",
        r"\bimmediately\b",
        r"\bالحين\b",
        r"\bضروري\b",
        r"\bمستعجل\b",
        r"\bاليوم\b",
        r"\bبسرعة\b",
    ]
    is_urgency = any(re.search(p, lower) for p in urgency_patterns) or "??" in raw

    has_only_emoji_or_symbols = bool(emoji_hits) and not re.search(r"[\w\u0600-\u06FF]", raw)

    if is_identity_intro and not is_correction:
        category = "identity_intro"
        response_hint = "Acknowledge who they are warmly and continue naturally. Do not qualify or ask business questions yet."
    elif is_correction:
        category = "correction"
        response_hint = "Acknowledge correction and continue from corrected context. Do not treat as property inquiry."
    elif has_only_emoji_or_symbols or emoji_meaning in {
        "laughing_or_light_embarrassment",
        "acknowledgement_or_approval",
        "approval_or_excitement",
    }:
        category = "emoji_reaction"
        response_hint = "Treat as emotional signal/acknowledgement. Reply lightly or continue only if needed."
    elif is_misunderstanding:
        category = "misunderstanding"
        response_hint = "Acknowledge and ask for the corrected meaning briefly."
    elif is_sarcasm:
        category = "sarcasm"
        response_hint = "Do not answer literally; respond lightly and reset to action."
    elif is_frustration:
        category = "frustration"
        response_hint = "Acknowledge calmly, avoid defensiveness, give the next concrete action."
    elif is_urgency:
        category = "urgency"
        response_hint = "Be brief, action-first, and state what happens next."
    elif is_joke or is_teasing_or_banter:
        category = "banter"
        response_hint = "Respond naturally and briefly; playful if relationship allows."
    else:
        category = "business_or_general"
        response_hint = "Use normal intent and relationship behavior."

    return {
        "category": category,
        "emoji": emoji_hits,
        "emoji_meaning": emoji_meaning,
        "is_correction": is_correction,
        "is_joke": is_joke,
        "is_sarcasm": is_sarcasm,
        "is_teasing_or_banter": is_teasing_or_banter,
        "is_misunderstanding": is_misunderstanding,
        "is_identity_intro": is_identity_intro,
        "is_frustration": is_frustration,
        "is_urgency": is_urgency,
        "response_hint": response_hint,
        "history_relevant": bool(history_lower),
    }


def detect_conversation_objective(text: str, history: str = "", relationship: str = "") -> str:
    """Decide what conversation is happening before property intent is considered."""
    raw = text or ""
    lower = raw.lower().strip()
    history_lower = (history or "").lower()
    social = detect_social_context(raw, history)
    greeting_patterns = [
        r"\bhello\b",
        r"\bhelo\b",
        r"\bhi\b",
        r"\bbrother\b",
        r"\bhow are you\b",
        r"\bhow is everything\b",
        r"\bhow'?s everything\b",
        r"\bhow everything\b",
        r"\bwhat about you\b",
        r"\bwhat'?s up\b",
        r"\bgood morning\b",
        r"هلا",
        r"هاي",
        r"مرحبا",
        r"السلام",
        r"سلام",
        r"كيفك",
        r"شلونك",
        r"شو اخبارك",
        r"وينك",
        r"وين مختفي",
        r"مختفي",
        r"صباح",
    ]
    current_is_greeting = any(re.search(pattern, lower) for pattern in greeting_patterns)
    explicit_property_words = any(
        x in lower
        for x in [
            "need",
            "looking",
            "search",
            "find",
            "want",
            "interested",
            "requirement",
            "budget",
            "buy",
            "rent",
            "sale",
            "lease",
            "studio",
            "1br",
            "2br",
            "3br",
            "bedroom",
            "villa",
            "apartment",
            "plot",
            "unit",
            "downtown",
            "jvc",
            "yas",
            "saadiyat",
            "شراء",
            "ايجار",
            "إيجار",
            "شقة",
            "فيلا",
        ]
    )

    if ("ai" in lower or "الـ ai" in lower or "ال ai" in lower) and any(x in lower for x in ["omar", "عمر", "دخل", "مدخل"]):
        return "joke"

    # Latest message wins. Old property history must not turn a fresh greeting,
    # correction, joke, or emoji into lead qualification.
    if social["category"] == "emoji_reaction":
        return "joke" if social.get("emoji_meaning") == "laughing_or_light_embarrassment" else "casual_greeting"
    if social["category"] in {"banter", "sarcasm"}:
        return "joke"
    if social["category"] in {"correction", "identity_intro", "misunderstanding"}:
        return "correction"
    if current_is_greeting and not explicit_property_words:
        normalized = normalize_relationship(relationship)
        return "friend_chat" if normalized == "Friend" else "casual_greeting"

    prior_group_context = any(
        x in history_lower
        for x in [
            "dxb group",
            "both group",
            "both groups",
            "share in the group",
            "display name",
            "agent group",
            "broker group",
            "xp property",
        ]
    )
    prior_property_context = any(
        x in history_lower
        for x in [
            "buy",
            "rent",
            "property",
            "properties",
            "propertys",
            "unit",
            "villa",
            "apartment",
            "bedroom",
            "downtown",
            "jvc",
            "shortlist",
            "developer",
            "budget",
        ]
    )
    developer_signal = any(x in lower for x in ["tiger", "eleven", "emaar", "damac", "nakheel", "aldar", "sobha", "azizi", "danube"])

    if prior_group_context and not any(x in lower for x in ["buy", "rent", "شراء", "ايجار", "إيجار"]):
        return "agent_discussion"
    if developer_signal and prior_property_context:
        return "property_inquiry"

    if social["category"] == "frustration":
        return "complaint"

    group_signal = (
        any(x in lower for x in ["dxb group", "whatsapp group", "agent group", "broker group", "add me", "add this person", "share in the group"])
        or ("group" in lower and any(x in lower for x in ["add", "share", "inquiries", "properties", "listings", "agents", "brokers"]))
    )
    if group_signal:
        return "agent_discussion"

    document_signal = any(
        x in lower
        for x in [
            "document",
            "docs",
            "contract",
            "mou",
            "title deed",
            "passport",
            "emirates id",
            "noc",
            "pdf",
            "ملف",
            "عقد",
            "مستند",
        ]
    )
    if document_signal:
        return "document_request"

    active_deal_signal = any(x in lower for x in ["update", "where are we", "status", "follow up", "done?", "خلص", "وين وصلنا", "شو صار"])
    if active_deal_signal or any(x in history_lower for x in ["nakheel", "noc", "mou", "dld", "transfer", "active deal", "portal/account access"]):
        return "active_deal" if active_deal_signal else "follow_up"

    negotiation_signal = any(x in lower for x in ["offer", "price", "discount", "commission", "سعر", "عرض", "عمولة", "تفاوض"])
    if negotiation_signal:
        return "negotiation"

    property_requirement = (
        any(x in lower for x in ["need", "looking", "search", "find", "want", "interested", "requirement", "budget"])
        and any(x in lower for x in ["studio", "1br", "2br", "3br", "bedroom", "villa", "apartment", "plot", "unit", "property", "downtown", "jvc", "dubai hills", "yas", "saadiyat"])
    )
    buy_rent_requirement = (
        any(x in lower for x in ["buy", "rent", "sale", "lease", "شراء", "ايجار", "إيجار", "بيع"])
        and any(x in lower for x in ["studio", "bedroom", "br", "villa", "apartment", "plot", "unit", "property", "شقة", "فيلا", "ارض", "أرض"])
    )
    concise_property_requirement = bool(
        re.search(r"\b(?:need|find|looking for|want)\s+(?:a\s+)?(?:studio|[1-9]\s*br|[1-9]br|[1-9]\s*bedroom|villa|apartment|plot)\b", lower)
    )
    shorthand_property_requirement = bool(
        re.search(r"\b(?:studio|[1-9]\s*br|[1-9]br|[1-9]\s*bedroom|villa|apartment|plot)\b", lower)
        and any(area in lower for area in ["jvc", "yas", "saadiyat", "reem", "marina", "downtown", "business bay", "jumeirah", "al raha", "reeman"])
        and (
            any(x in lower for x in ["under", "below", "budget", "up to", "max", "تحت", "ميزانية"])
            or bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:k|m|million|مليون|الف|ألف)\b", lower))
        )
    )
    property_continuation = prior_property_context and (
        developer_signal
        or property_requirement
        or buy_rent_requirement
        or concise_property_requirement
        or shorthand_property_requirement
        or any(x in lower for x in ["ready", "off plan", "secondary", "viewing", "options", "send", "check", "roi", "growth", "no preference"])
    )
    if property_requirement or buy_rent_requirement or concise_property_requirement or shorthand_property_requirement or property_continuation:
        return "property_inquiry"

    if any(re.search(pattern, lower) for pattern in greeting_patterns):
        normalized = normalize_relationship(relationship)
        return "friend_chat" if normalized == "Friend" else "casual_greeting"

    if normalize_relationship(relationship) == "Staff":
        return "internal_staff_discussion"
    if normalize_relationship(relationship) == "Agent":
        return "agent_discussion"
    return "casual_greeting" if len(lower.split()) <= 3 else "follow_up"


def detect_intent(text: str, history: str = "", conversation_objective: str | None = None) -> str:
    lower = (text or "").lower()
    social = detect_social_context(text, history)
    objective = conversation_objective or detect_conversation_objective(text, history)
    group_access_signal = (
        any(
            x in lower
            for x in [
                "dxb group",
                "whatsapp group",
                "wa group",
                "your group",
                "the group",
                "both group",
                "both groups",
                "add me",
                "add this person",
                "add him",
                "add her",
                "share in the group",
                "secondary group",
                "agent group",
                "broker group",
                "xp property",
            ]
        )
        or (
            "group" in lower
            and any(x in lower for x in ["add", "share", "inquiries", "properties", "listings", "agents", "brokers"])
        )
        or bool(re.search(r"\b0?5\d{8}\b", lower))
    )
    property_signal = (
        any(x in lower for x in ["rent", "buy", "villa", "apartment", "studio", "bedroom", "plot", "unit", "property", "properties", "propertys", "ايجار", "شراء", "شقة", "فيلا"])
        or bool(re.search(r"\b[1-9]\s*br\b|\b[1-9]br\b|\bbr\b", lower))
    )
    developer_signal = any(x in lower for x in ["tiger", "eleven", "emaar", "damac", "nakheel", "aldar", "sobha", "azizi", "danube"])
    if group_access_signal:
        return "group_access"
    if social["category"] in {"identity_intro", "correction", "emoji_reaction", "banter", "sarcasm", "misunderstanding", "frustration"}:
        return social["category"]
    if any(x in lower for x in ["تعرفهم", "who are they", "do you know them", "من هم", "مين هم"]):
        return "unclear_reference"
    if any(x in lower for x in [
        "noc", "dld", "contract", "mou", "payment", "bank", "legal", "owner", "landlord",
        "private", "internal", "crm", "commission", "title deed", "passport",
        "emirates id", "عقد", "مذكرة", "دفع", "بنك", "مالك", "خاص", "داخلي", "عمولة",
    ]):
        return "sensitive"
    if objective in {"property_inquiry", "active_deal"} and (property_signal or developer_signal):
        return "property"
    if social["category"] == "urgency":
        return "urgency"
    if any(x in lower for x in ["price", "offer", "commission", "سعر", "عرض", "عمولة"]):
        return "negotiation"
    greeting_patterns = [
        r"\bhello\b",
        r"\bhi\b",
        r"\bgood morning\b",
        r"\bhow are you\b",
        r"\bhow is everything\b",
        r"\bhow'?s everything\b",
        r"\bwhat about you\b",
        r"\bwhat'?s up\b",
        r"\bassalam\b",
        r"\bsalam\b",
        r"\bguten morgen\b",
        r"\bguten tag\b",
        r"\bguten abend\b",
        r"\bhallo\b",
        r"\bдоброе утро\b",
        r"\bздравствуйте\b",
        r"\bпривет\b",
        r"صباح",
        r"مساء",
        r"هلا",
        r"هاي",
        r"مرحبا",
        r"السلام",
        r"سلام",
        r"يسعد",
        r"كيفك",
        r"وينك",
        r"وين مختفي",
        r"مختفي",
        r"شلونك",
        r"شو اخبارك",
    ]
    if any(re.search(pattern, lower) for pattern in greeting_patterns):
        return "greeting"
    return "general"


def relationship_memory_profile(
    relationship: str,
    sender_type: str = "",
    contact_context: dict[str, Any] | None = None,
    history: str = "",
) -> dict[str, Any]:
    """Build a small preference profile for this contact from known signals.

    This is intentionally deterministic: it does not store raw chats as memory.
    It extracts only interaction preferences that help the next reply feel right.
    """
    contact_context = contact_context or {}
    special_profile = special_contact_profile(contact_context)
    normalized = normalize_relationship(relationship, sender_type)
    if special_profile.get("relationship"):
        normalized = normalize_relationship(special_profile["relationship"], sender_type)
    sample = " ".join(
        str(x or "")
        for x in [
            contact_context.get("known_contact_name", ""),
            contact_context.get("last_message_excerpt", ""),
            history[-900:],
        ]
    )
    language = detect_language(sample)
    if language == "neutral":
        language = "mixed" if normalized in {"Friend", "Staff", "Omar"} else "english"

    detail_by_relationship = {
        "Friend": "very_short",
        "Client": "short_with_next_step",
        "Existing Client": "short_continue_context",
        "New Client": "short_one_question_max",
        "Agent": "very_short_market_direct",
        "Staff": "brief_execution_or_checklist",
        "Omar": "command_mode",
        "Trusted Partner": "full_access_direct",
        "Unknown": "short_safe",
    }
    tone_by_relationship = {
        "Friend": "warm_familiar",
        "Client": "premium_reassuring",
        "Existing Client": "personal_premium",
        "New Client": "welcoming_confident",
        "Agent": "fast_direct",
        "Staff": "internal_execution",
        "Omar": "direct_command",
        "Trusted Partner": "trusted_partner_direct",
        "Unknown": "polite_cautious",
    }
    return {
        "relationship": normalized,
        "preferred_language": language,
        "latest_message_language": None,
        "preferred_tone": tone_by_relationship.get(normalized, "polite_cautious"),
        "preferred_detail_level": detail_by_relationship.get(normalized, "short_safe"),
        "known_contact_name": contact_context.get("known_contact_name", ""),
        "special_contact_profile": special_profile,
        "known_chat": bool(contact_context.get("known_chat")),
        "history_turns": contact_context.get("runtime_history_turns", 0),
        "expect_repeat_greeting": False if history and history != "No prior history" else None,
    }


def business_judgment(
    text: str,
    intent: str,
    social_context: dict[str, Any],
    relationship: str,
    history: str = "",
    conversation_objective: str = "",
) -> dict[str, Any]:
    """Decide what the person likely expects next."""
    lower = (text or "").lower()
    normalized = normalize_relationship(relationship)
    objective = conversation_objective or detect_conversation_objective(text, history, relationship)

    history_lower = (history or "").lower()
    has_area = any(area in lower for area in ["jvc", "yas", "saadiyat", "reem", "marina", "downtown", "business bay", "jumeirah", "al raha", "reeman"])
    has_type = (
        any(kind in lower for kind in ["studio", "bedroom", "villa", "apartment", "plot", "unit", "property", "properties", "propertys", "شقة", "فيلا", "غرفة", "ارض", "أرض"])
        or bool(re.search(r"\b[1-9]\s*br\b|\b[1-9]br\b|\bbr\b", lower))
    )
    has_budget = bool(re.search(r"\b\d+\s*(k|m|million|مليون|الف|ألف)?\b", lower))
    has_process_word = any(x in lower for x in ["noc", "dld", "transfer", "rera", "mortgage", "visa", "تسجيل", "نقل", "رهن"])
    has_developer = any(x in lower for x in ["tiger", "eleven", "emaar", "damac", "nakheel", "aldar", "sobha", "azizi", "danube"])
    prior_property_context = any(x in history_lower for x in ["buy", "rent", "property", "properties", "unit", "villa", "apartment", "bedroom", "downtown", "jvc", "shortlist"])
    group_access_signal = (
        intent == "group_access"
        or any(x in lower for x in ["dxb group", "both group", "both groups", "add me", "add this person", "share in the group", "agent group", "broker group", "xp property"])
        or ("group" in lower and any(x in lower for x in ["add", "share", "inquiries", "properties", "listings", "agents", "brokers"]))
        or bool(re.search(r"\b0?5\d{8}\b", lower))
        or any(x in history_lower for x in ["dxb group", "both group", "both groups", "share in the group", "display name"])
    )

    next_action = "answer"
    ask_allowed = True
    escalation = "none"
    stop_qualifying = False
    expectation = "direct_answer"

    category = social_context.get("category")
    if category == "correction":
        next_action = "acknowledge_correction"
        ask_allowed = False
        expectation = "update_context_and_continue"
        stop_qualifying = True
    elif category == "emoji_reaction":
        next_action = "light_acknowledgement"
        ask_allowed = False
        expectation = "emotional_ack_or_continue"
        stop_qualifying = True
    elif category in {"banter", "sarcasm"}:
        next_action = "respond_socially_then_reset"
        ask_allowed = False
        expectation = "human_social_reply"
    elif category == "identity_intro":
        next_action = "acknowledge_identity"
        ask_allowed = False
        expectation = "friendly_identity_ack_no_business_qualification"
        stop_qualifying = True
    elif category == "misunderstanding":
        next_action = "repair_misunderstanding"
        ask_allowed = True
        expectation = "brief_clarification"
    elif category == "frustration":
        next_action = "calm_action_first"
        ask_allowed = False
        expectation = "fix_or_exact_next_step"
        stop_qualifying = True
    elif category == "urgency":
        next_action = "urgent_action_first"
        expectation = "fast_next_action"

    if objective in {"casual_greeting", "friend_chat"}:
        next_action = "casual_reply"
        ask_allowed = False
        stop_qualifying = True
        expectation = "natural_social_reply_no_property_qualification"
    elif objective == "joke":
        next_action = "humor_reply"
        ask_allowed = False
        stop_qualifying = True
        expectation = "playful_human_reply_no_property_route"
    elif objective == "correction" and category != "identity_intro":
        next_action = "acknowledge_correction"
        ask_allowed = False
        stop_qualifying = True
        expectation = "update_context_and_continue"
    elif intent == "group_access" or group_access_signal or objective == "agent_discussion":
        next_action = "verify_group_access"
        ask_allowed = False
        stop_qualifying = True
        expectation = "agent_group_onboarding_no_fake_action"
    elif intent == "property" and objective in {"property_inquiry", "active_deal"}:
        if has_developer and prior_property_context:
            next_action = "recommend"
            ask_allowed = False
            stop_qualifying = True
            expectation = "developer_shortlist_or_options"
        elif has_area and has_type and (has_budget or normalized in {"Agent", "Staff", "Omar", "Existing Client"}):
            next_action = "recommend"
            ask_allowed = False
            stop_qualifying = True
            expectation = "shortlist_or_check_options"
        elif "buy" in lower and (has_type or prior_property_context):
            next_action = "continue_buyer_requirement"
            ask_allowed = False
            stop_qualifying = True
            expectation = "continue_buyer_search"
        else:
            next_action = "ask_one_missing_detail"
            ask_allowed = True
            expectation = "one_sharp_question"
    elif objective in {"property_inquiry", "active_deal"} and (has_area or has_type or has_budget or has_developer or prior_property_context):
        next_action = "recommend" if (has_area and has_type and has_budget) or has_developer else "continue_buyer_requirement"
        ask_allowed = False
        stop_qualifying = True
        expectation = "shortlist_or_check_options"
    elif intent == "greeting" and history and history != "No prior history":
        next_action = "continue_greeting"
        ask_allowed = False
        expectation = "natural_short_greeting_no_restart"
    elif objective == "document_request" or intent == "sensitive":
        next_action = "safe_answer_or_escalate"
        escalation = "omar_review_if_private_or_commitment"
        expectation = "safe_boundary_plus_next_step"
    elif intent == "negotiation":
        next_action = "collect_offer_or_answer"
        escalation = "none"
        expectation = "do_not_commit_price"
    elif has_process_word and intent == "general":
        next_action = "answer_process"
        expectation = "steps_documents_timeline"

    return {
        "engine": "BUSINESS_JUDGMENT_ENGINE_V1",
        "next_action": next_action,
        "expected_next": expectation,
        "ask_allowed": ask_allowed,
        "stop_qualifying": stop_qualifying,
        "escalation": escalation,
        "signals": {
            "conversation_objective": objective,
            "has_area": has_area,
            "has_property_type": has_type,
            "has_budget": has_budget,
            "has_process_word": has_process_word,
            "has_developer": has_developer,
            "prior_property_context": prior_property_context,
            "active_history": bool(history and history != "No prior history"),
        },
        "rule": (
            "Answer/recommend/act when enough signal exists. Ask only one sharp question "
            "when required. Escalate commitments/private/sensitive matters."
        ),
    }


def normalize_relationship(relationship: str = "", sender_type: str = "") -> str:
    value = (relationship or sender_type or "Unknown").strip().lower()
    mapping = {
        "friend / personal contact": "Friend",
        "personal": "Friend",
        "friend": "Friend",
        "customer": "Client",
        "client": "Client",
        "existing client": "Existing Client",
        "known contact": "Existing Client",
        "new client": "New Client",
        "agent / broker": "Agent",
        "agent": "Agent",
        "broker": "Agent",
        "hsh internal staff": "Staff",
        "hsh staff": "Staff",
        "staff": "Staff",
        "internal": "Staff",
        "omar": "Omar",
        "trusted partner": "Trusted Partner",
        "trusted": "Trusted Partner",
        "full access": "Trusted Partner",
        "unknown": "Unknown",
    }
    return mapping.get(value, "Unknown")


def relationship_behavior(relationship: str, sender_type: str = "") -> dict[str, Any]:
    normalized = normalize_relationship(relationship, sender_type)
    data = _load_relationship_behavior()
    profiles = data.get("relationship_types", {}) if isinstance(data, dict) else {}
    behavior = profiles.get(normalized) or profiles.get("Unknown") or {}
    return {"relationship": normalized, **behavior}


def build_personality_context(
    message: str,
    history: str = "",
    sender_type: str = "Customer",
    relationship: str = "",
    contact_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contact_context = contact_context or {}
    profile = _load_profile()
    concierge_persona = _load_concierge_persona()
    stats = (profile.get("stats") or {}) if isinstance(profile, dict) else {}
    language = detect_language(message)
    social_context = detect_social_context(message, history)
    special_profile = special_contact_profile(contact_context)
    sentiment_handoff = sentiment_handoff_decision(message, history)
    if special_profile.get("relationship"):
        relationship = special_profile["relationship"]
    behavior = relationship_behavior(relationship, sender_type)
    conversation_objective = detect_conversation_objective(message, history, behavior.get("relationship", relationship))
    intent = detect_intent(message, history, conversation_objective)
    relationship_memory = relationship_memory_profile(relationship, sender_type, contact_context, history)
    relationship_memory["latest_message_language"] = language
    judgment = business_judgment(message, intent, social_context, behavior.get("relationship", "Unknown"), history, conversation_objective)
    friendly = intent == "greeting" or any(token in (message or "") for token in ["ملك", "حبيبي", "brother", "boss"])

    if language == "arabic":
        tone = "Arabic warm, Gulf/Levant natural, concise."
    elif language == "mixed":
        tone = "Mixed Arabic/English naturally, mirror user language."
    else:
        tone = "English concise, direct, premium business tone."

    return {
        "profile": "OMAR_PERSONALITY_PROFILE_V1",
        "operations_persona": "LEAD_DIGITAL_OPERATIONS_CONCIERGE",
        "operations_persona_file": str(CONCIERGE_PERSONA_PATH),
        "operations_persona_text": concierge_persona,
        "response_engine": [
            "Identity Classification",
            "Conversation Objective Detection",
            "Intent Detection",
            "Permission Layer",
            "Knowledge Retrieval",
            "Omar Personality Layer",
            "Safe Reply Generation",
        ],
        "confidence_percent": stats.get("confidence_percent"),
        "sender_type": sender_type,
        "relationship_behavior_engine": "RELATIONSHIP_BEHAVIOR_ENGINE_V1",
        "relationship": behavior.get("relationship", "Unknown"),
        "relationship_behavior": behavior,
        "special_contact_profile": special_profile,
        "sentiment_handoff": sentiment_handoff,
        "conversation_objective": conversation_objective,
        "intent": intent,
        "social_context": social_context,
        "business_judgment": judgment,
        "relationship_memory": relationship_memory,
        "language": language,
        "tone": tone,
        "length_rule": "Default one short sentence; detailed only for operational/process clarity.",
        "warmth_rule": "Use light familiar warmth only when context is friendly." if friendly else "Stay professional and direct.",
        "action_rule": (
            "Answer/action first. Ask one sharp clarifying question only when a required "
            "detail is truly missing; never ask again for details already provided."
        ),
        "language_rule": (
            "Reply in the same language as the latest inbound user message. If the user changes "
            "language, switch immediately without explaining."
        ),
        "safety_rule": (
            "For Omar and Trusted Partner full-access senders, use full approved retrieval. "
            "For everyone else, do not expose owner/private/internal data; hold sensitive commitments for Omar."
        ),
        "allowed_knowledge": [
            "property details",
            "availability",
            "areas",
            "communities",
            "developers",
            "payment plans",
            "project information",
            "community information",
            "market information",
            "property comparisons",
            "DLD procedures",
            "RERA procedures",
            "NOC procedures",
            "transfer procedures",
            "mortgage procedures",
            "residency and visa information",
            "company setup information",
            "operations knowledge",
            "public inventory",
            "public brochures",
            "public project documents",
        ],
        "restricted_knowledge": [] if behavior.get("relationship") == "Trusted Partner" or sender_type == "Trusted Partner" else [
            "owner names",
            "owner emails",
            "owner phone numbers",
            "passport details",
            "Emirates ID details",
            "unit-specific ownership data",
            "private ownership records",
            "internal CRM notes",
            "internal negotiations",
            "internal commissions",
            "private documents",
            "internal conversations",
            "staff personal information",
            "confidential deal information",
        ],
        "response_goal": (
            "The personality should feel like Omar; the knowledge should feel like AIOS: "
            "more informed, more organized, and more consistent."
        ),
        "history_summary": history[-1200:] if history else "No prior history",
        "last_10_message_summary": "\n".join((history or "No prior history").splitlines()[-10:]) if history else "No prior history",
        "system_instruction": (
            "Lead Digital Operations Concierge is active: optimize for Zero-Latency Accuracy "
            "and Human-Equivalence. You are not a chatbot; you are an extension of the human team. "
            "Execute precision queries; do not search blindly. Confirm; do not guess. "
            "No robotic filler or lengthy explanations. Reply like Omar, not ChatGPT. Match language. Keep it short, human, premium, "
            "and action-oriented. Do not repeat greetings in active conversations. If the "
            "user already gave area, type, budget, or timeline, move directly to the next "
            "action: search, recommend, compare, or act. Share maximum useful allowed "
            "knowledge and never expose restricted knowledge. Adapt tone, length, humor, "
            "directness, professionalism, and follow-up based on relationship_behavior. "
            "Use social_context to detect corrections, jokes, teasing, sarcasm, misunderstandings, "
            "frustration, urgency, and emoji reactions before deciding the reply. Use business_judgment "
            "to decide whether to ask, answer, recommend, or stop qualifying. Use "
            "relationship_memory to match this person's expected language, tone, and detail level. "
            "The reply language must follow latest_message_language, not older history. "
            "There is no automatic human handoff for normal conversation."
        ),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build Omar personality context")
    parser.add_argument("message")
    parser.add_argument("--history", default="")
    parser.add_argument("--sender-type", default="Customer")
    parser.add_argument("--relationship", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            build_personality_context(args.message, args.history, args.sender_type, args.relationship),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
