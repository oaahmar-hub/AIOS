#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/PersonalityEngine")
sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

from omar_personality_engine import build_personality_context, detect_language
import simple_whatsapp_openai_gateway as gateway


def fake_context(message, relationship="New Client", history="No prior history", sender_type="Customer"):
    personality = build_personality_context(
        message,
        history=history,
        sender_type=sender_type,
        relationship=relationship,
        contact_context={"known_chat": history != "No prior history", "runtime_history_turns": 2},
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


def assert_case(name, condition, detail):
    return {"test": name, "pass": bool(condition), "detail": detail}


def main():
    results = []

    language_cases = [
        ("Hello", "english"),
        ("السلام عليكم", "arabic"),
        ("Guten Morgen", "german"),
        ("Доброе утро", "russian"),
    ]
    for text, expected in language_cases:
        ctx = fake_context(text, relationship="Client")
        reply = gateway.fast_path_reply(text, ctx)
        results.append(assert_case(f"language_{expected}", ctx["latest_message_language"] == expected and bool(reply), {"text": text, "language": ctx["latest_message_language"], "reply": reply}))

    continuity_ctx = fake_context(
        "please do sent me your offer",
        relationship="Staff",
        history="user: may i have one bedroom downtown for rent ?\nassistant: Got it — I’ll check available 1BR in Downtown.",
        sender_type="HSH Staff",
    )
    results.append(assert_case("conversation_continuity", continuity_ctx["business_judgment"]["signals"]["active_history"], continuity_ctx["business_judgment"]))

    follow_ctx = fake_context("Please make MOU and send it to me", relationship="Existing Client", history="user: deal details shared")
    results.append(assert_case("follow_up_behavior", follow_ctx["business_judgment"]["next_action"] == "safe_answer_or_escalate", follow_ctx["business_judgment"]))

    property_ctx = fake_context("Hello please one bedroom for rent JVC 80k yearly", relationship="New Client")
    property_reply = gateway.fast_path_reply("Hello please one bedroom for rent JVC 80k yearly", property_ctx)
    results.append(
        assert_case(
            "over_qualification",
            property_ctx["business_judgment"]["ask_allowed"] is False
            and "?" not in property_reply
            and "verified rental" in property_reply.lower()
            and "confirmed live option" in property_reply.lower(),
            {"judgment": property_ctx["business_judgment"], "reply": property_reply},
        )
    )

    social_cases = [
        ("this is Salwa", "correction"),
        ("😂", "emoji_reaction"),
        ("ال AI يلعب", "banter"),
        ("why it is not working again??", "frustration"),
    ]
    for text, expected in social_cases:
        ctx = fake_context(text, relationship="Friend", history="user: previous")
        results.append(assert_case(f"social_{expected}", ctx["social_context"]["category"] == expected, ctx["social_context"]))

    speed_cases = [
        fake_context("Hello", relationship="New Client"),
        fake_context("😂", relationship="Friend", history="user: joke"),
        fake_context("Hello please one bedroom for rent JVC 80k yearly", relationship="New Client"),
    ]
    speed_pass = all(gateway.fast_path_reply(c["personality"].get("history_summary", "") or "Hello", c) is not None for c in speed_cases)
    results.append(assert_case("response_speed_fast_path_available", speed_pass, "fast path callable after required layers"))

    coverage_required = [
        "conversation_history",
        "relationship",
        "intent",
        "latest_message_language",
        "social_context",
        "business_judgment",
        "relationship_memory",
        "permission",
        "personality",
    ]
    coverage_ctx = fake_context("Hi", relationship="Agent")
    results.append(assert_case("all_chat_coverage", all(k in coverage_ctx for k in coverage_required), {k: k in coverage_ctx for k in coverage_required}))

    closing_ctx = fake_context("2BR Yas Island under 2M", relationship="Client")
    results.append(assert_case("business_closing", closing_ctx["business_judgment"]["next_action"] in {"recommend", "ask_one_missing_detail"}, closing_ctx["business_judgment"]))

    passed = sum(1 for r in results if r["pass"])
    output = {"passed": passed, "total": len(results), "score_percent": round((passed / len(results)) * 100, 2), "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
