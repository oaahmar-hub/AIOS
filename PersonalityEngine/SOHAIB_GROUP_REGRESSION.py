#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/PersonalityEngine")
sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

from omar_personality_engine import build_personality_context
import simple_whatsapp_openai_gateway as gateway


def ctx(message, history, relationship="Agent", contact_name="Sohaib"):
    personality = build_personality_context(
        message,
        history=history,
        sender_type="Customer",
        relationship=relationship,
        contact_context={
            "known_chat": bool(history and history != "No prior history"),
            "known_contact_name": contact_name,
            "runtime_history_turns": 4 if history and history != "No prior history" else 0,
        },
    )
    return {
        "conversation_history": history,
        "contact_context": {"known_contact_name": contact_name, "known_chat": bool(history and history != "No prior history")},
        "relationship": personality["relationship"],
        "intent": personality["intent"],
        "latest_message_language": personality["language"],
        "social_context": personality["social_context"],
        "business_judgment": personality["business_judgment"],
        "relationship_memory": personality["relationship_memory"],
        "permission": {"decision": "allow"},
        "personality": personality,
    }


def clean(reply):
    return (reply or "").lower()


cases = []
history0 = "user: Hello Omar\nMy name is Sohaib from Aron and trisl real estate\nassistant: Hello."

c1 = ctx("Can you please add me in your dxb group", history0)
r1 = gateway.fast_path_reply("Can you please add me in your dxb group", c1)
cases.append(
    (
        "dxb_group_detected_as_group_access",
        c1["intent"] == "group_access"
        and "secondary" in clean(r1)
        and "review" in clean(r1)
        and "which dxb group" not in clean(r1),
        {"intent": c1["intent"], "judgment": c1["business_judgment"], "reply": r1},
    )
)

history1 = history0 + "\nuser: Can you please add me in your dxb group\nassistant: " + r1
c2 = ctx("In both group please", history1)
r2 = gateway.fast_path_reply("In both group please", c2)
cases.append(
    (
        "both_groups_no_display_name_loop",
        "both" in clean(r2)
        and "display name" not in clean(r2)
        and "i’ll add you to both" not in clean(r2)
        and "all set" not in clean(r2),
        {"intent": c2["intent"], "judgment": c2["business_judgment"], "reply": r2},
    )
)

history2 = history1 + "\nuser: In both group please\nassistant: " + r2
c3 = ctx("I always have some inquiries and some good properties so i can share in the group", history2)
r3 = gateway.fast_path_reply("I always have some inquiries and some good properties so i can share in the group", c3)
cases.append(
    (
        "share_context_agent_group_quality",
        "secondary group" in clean(r3)
        and "clean" in clean(r3)
        and "display name" not in clean(r3),
        {"intent": c3["intent"], "judgment": c3["business_judgment"], "reply": r3},
    )
)

history3 = history2 + "\nuser: I always have some inquiries and some good properties so i can share in the group\nassistant: " + r3
c4 = ctx("Actually i don’t know about display name", history3)
r4 = gateway.fast_path_reply("Actually i don’t know about display name", c4)
cases.append(
    (
        "display_name_correction_contextual",
        "whatsapp name is enough" in clean(r4)
        and "got it, corrected" not in clean(r4),
        {"intent": c4["intent"], "judgment": c4["business_judgment"], "reply": r4},
    )
)

history4 = history3 + "\nuser: Actually i don’t know about display name\nassistant: " + r4
c5 = ctx("0552110133 \nYoh can also add this person", history4)
r5 = gateway.fast_path_reply("0552110133 \nYoh can also add this person", c5)
cases.append(
    (
        "phone_add_person_not_greeting",
        "which company" in clean(r5)
        and "review before adding" in clean(r5)
        and clean(r5) != "hi.",
        {"intent": c5["intent"], "judgment": c5["business_judgment"], "reply": r5},
    )
)

forbidden = ["all set with the groups", "i’ll add you to both", "which display name should"]
cases.append(
    (
        "no_fake_group_completion_claims",
        all(not any(term in clean(reply) for term in forbidden) for reply in [r1, r2, r3, r4, r5]),
        {"replies": [r1, r2, r3, r4, r5]},
    )
)

results = [{"test": name, "pass": bool(ok), "detail": detail} for name, ok, detail in cases]
print(json.dumps({"passed": sum(r["pass"] for r in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2))
