#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/PersonalityEngine")
sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

from omar_personality_engine import build_personality_context
import simple_whatsapp_openai_gateway as gateway


def ctx(message, history, relationship="New Client"):
    personality = build_personality_context(
        message,
        history=history,
        sender_type="Customer",
        relationship=relationship,
        contact_context={"known_chat": bool(history and history != "No prior history")},
    )
    return {
        "conversation_history": history,
        "contact_context": {"known_chat": bool(history and history != "No prior history")},
        "relationship": personality["relationship"],
        "intent": personality["intent"],
        "latest_message_language": personality["language"],
        "social_context": personality["social_context"],
        "business_judgment": personality["business_judgment"],
        "relationship_memory": personality["relationship_memory"],
        "permission": {"decision": "allow"},
        "personality": personality,
    }


def bad_business_push(reply):
    bad_terms = ["شراء", "إيجار", "استشارة", "عقاري", "استفسار", "buy", "rent", "property"]
    return any(term in (reply or "") for term in bad_terms)


cases = []

c1 = ctx("كيفك شو اخبارك", "user: هلا\nassistant: هلا والله 🌹")
r1 = gateway.fast_path_reply("كيفك شو اخبارك", c1)
cases.append(
    (
        "arabic_how_are_you_stays_social",
        c1["intent"] == "greeting" and "الحمدلله" in r1 and not bad_business_push(r1),
        {"intent": c1["intent"], "reply": r1},
    )
)

history = "user: هلا\nassistant: هلا والله 🌹\nuser: كيفك شو اخبارك\nassistant: الحمدلله بخير يا غالي، إنت كيفك؟"
c2 = ctx("عمر همام انا", history)
r2 = gateway.fast_path_reply("عمر همام انا", c2)
cases.append(
    (
        "arabic_identity_intro_no_qualification",
        c2["intent"] == "identity_intro"
        and c2["social_context"]["category"] == "identity_intro"
        and "عمر همام" in r2
        and not bad_business_push(r2),
        {"intent": c2["intent"], "social": c2["social_context"], "judgment": c2["business_judgment"], "reply": r2},
    )
)

c3 = ctx("Downtown\nDubai Hills Specialist", "user: Sohaib Ahsan\nassistant: Thanks.")
r3 = gateway.fast_path_reply("Downtown\nDubai Hills Specialist", c3)
cases.append(
    (
        "dubai_hills_not_greeting_hi_substring",
        c3["intent"] != "greeting" and r3 != "Hi.",
        {"intent": c3["intent"], "reply": r3},
    )
)

results = [{"test": name, "pass": bool(ok), "detail": detail} for name, ok, detail in cases]
print(json.dumps({"passed": sum(r["pass"] for r in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2))
