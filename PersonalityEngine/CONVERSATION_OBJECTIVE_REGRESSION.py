#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/PersonalityEngine")
sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

from omar_personality_engine import build_personality_context
import simple_whatsapp_openai_gateway as gateway


def ctx(message, history="No prior history", relationship="New Client"):
    personality = build_personality_context(
        message,
        history=history,
        sender_type="Customer",
        relationship=relationship,
        contact_context={"known_chat": history != "No prior history"},
    )
    return {
        "conversation_history": history,
        "contact_context": {"known_chat": history != "No prior history"},
        "relationship": personality["relationship"],
        "conversation_objective": personality["conversation_objective"],
        "intent": personality["intent"],
        "latest_message_language": personality["language"],
        "social_context": personality["social_context"],
        "business_judgment": personality["business_judgment"],
        "relationship_memory": personality["relationship_memory"],
        "permission": {"decision": "allow"},
        "personality": personality,
    }


def has_property_question(reply):
    return any(x in (reply or "") for x in ["buy", "rent", "area", "budget", "bedroom", "شراء", "إيجار", "منطقة", "ميزانية", "غرف"])


cases = []

c1 = ctx("هلا", relationship="Friend")
r1 = gateway.fast_path_reply("هلا", c1)
cases.append(("friend_hala_is_friend_chat", c1["conversation_objective"] == "friend_chat" and not has_property_question(r1), {"objective": c1["conversation_objective"], "reply": r1}))

c2 = ctx("كيفك", history="user: هلا\nassistant: هلا والله 🌹")
r2 = gateway.fast_path_reply("كيفك", c2)
cases.append(("arabic_how_are_you_is_casual", c2["conversation_objective"] == "casual_greeting" and not has_property_question(r2), {"objective": c2["conversation_objective"], "reply": r2}))

c3 = ctx("😂", relationship="Friend")
r3 = gateway.fast_path_reply("😂", c3)
cases.append(("emoji_is_social_not_property", c3["conversation_objective"] == "joke" and not has_property_question(r3), {"objective": c3["conversation_objective"], "reply": r3}))

c4 = ctx("لا عمر مدخل الـ AI", history="user: هلا\nassistant: هلا والله 🌹", relationship="Friend")
r4 = gateway.fast_path_reply("لا عمر مدخل الـ AI", c4)
cases.append(("ai_joke_not_property", c4["conversation_objective"] == "joke" and "AI" in r4 and not has_property_question(r4), {"objective": c4["conversation_objective"], "reply": r4}))

c5 = ctx("This is Salwa", history="user: Hello\nassistant: Hello.", relationship="Staff")
r5 = gateway.fast_path_reply("This is Salwa", c5)
cases.append(("this_is_salwa_is_correction", c5["conversation_objective"] == "correction" and not has_property_question(r5), {"objective": c5["conversation_objective"], "intent": c5["intent"], "reply": r5}))

c6 = ctx("Need 1BR Downtown", relationship="New Client")
r6 = gateway.fast_path_reply("Need 1BR Downtown", c6)
cases.append(("need_1br_downtown_is_property", c6["conversation_objective"] == "property_inquiry" and c6["intent"] == "property", {"objective": c6["conversation_objective"], "intent": c6["intent"], "reply": r6}))

c7 = ctx("Looking to buy in JVC", relationship="New Client")
r7 = gateway.fast_path_reply("Looking to buy in JVC", c7)
cases.append(("looking_buy_jvc_is_property", c7["conversation_objective"] == "property_inquiry" and c7["intent"] == "property", {"objective": c7["conversation_objective"], "intent": c7["intent"], "reply": r7}))

results = [{"test": name, "pass": bool(ok), "detail": detail} for name, ok, detail in cases]
print(json.dumps({"passed": sum(r["pass"] for r in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2))
