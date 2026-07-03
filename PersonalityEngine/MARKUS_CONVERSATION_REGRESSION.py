#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/PersonalityEngine")
sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

from omar_personality_engine import build_personality_context
import simple_whatsapp_openai_gateway as gateway


def ctx(message, history, relationship="Friend"):
    personality = build_personality_context(
        message,
        history=history,
        sender_type="Customer",
        relationship=relationship,
        contact_context={"known_chat": bool(history and history != "No prior history")},
    )
    return {
        "conversation_history": history,
        "relationship": personality["relationship"],
        "intent": personality["intent"],
        "latest_message_language": personality["language"],
        "social_context": personality["social_context"],
        "business_judgment": personality["business_judgment"],
        "relationship_memory": personality["relationship_memory"],
        "permission": {"decision": "allow"},
        "personality": personality,
    }


cases = []

c1 = ctx("Hello Brother", "No prior history")
r1 = gateway.fast_path_reply("Hello Brother", c1)
cases.append(("hello_brother_not_property", c1["intent"] == "greeting" and "buy" not in r1.lower() and "rent" not in r1.lower(), {"intent": c1["intent"], "reply": r1}))

c2 = ctx("Everything good\nWhat about you", "user: Hello Brother\nassistant: Hello.")
r2 = gateway.fast_path_reply("Everything good\nWhat about you", c2)
cases.append(("what_about_you_social", "All good" in r2, {"intent": c2["intent"], "reply": r2}))

c3 = ctx("Wrong chat ?", "user: Brother\nassistant: Brother — looking to buy or rent?")
r3 = gateway.fast_path_reply("Wrong chat ?", c3)
cases.append(("wrong_chat_correction", c3["intent"] == "correction" and "corrected" in r3.lower(), {"intent": c3["intent"], "reply": r3}))

c4 = ctx("We buy now the propertys", "user: Wrong chat ?\nassistant: Got it, corrected.")
r4 = gateway.fast_path_reply("We buy now the propertys", c4)
cases.append(("buy_now_buyer_context", c4["intent"] == "property" and "buying" in r4.lower(), {"intent": c4["intent"], "judgment": c4["business_judgment"], "reply": r4}))

c5 = ctx("From Tiger and Eleven", "user: We buy now the propertys\nassistant: Perfect, buying. Send me the preferred area or developer and I’ll shortlist the best options.")
r5 = gateway.fast_path_reply("From Tiger and Eleven", c5)
cases.append(("developer_continuation", c5["intent"] == "property" and "tiger" in r5.lower() and "eleven" in r5.lower() and "budget" not in r5.lower(), {"intent": c5["intent"], "judgment": c5["business_judgment"], "reply": r5}))

results = [{"test": name, "pass": bool(ok), "detail": detail} for name, ok, detail in cases]
print(json.dumps({"passed": sum(r["pass"] for r in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2))

