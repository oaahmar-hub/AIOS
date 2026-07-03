#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

import simple_whatsapp_openai_gateway as gateway


def has_property_qualification(reply: str) -> bool:
    text = (reply or "").lower()
    return any(
        phrase in text
        for phrase in [
            "buying or renting",
            "buy or rent",
            "area?",
            "budget?",
            "bedrooms?",
            "شراء أو إيجار",
            "ميزانية",
        ]
    )


def has_ai_workflow_language(reply: str) -> bool:
    text = (reply or "").lower()
    return any(
        phrase in text
        for phrase in [
            "i will check",
            "i’ll check",
            "i will verify",
            "i’ll verify",
            "i will escalate",
            "i’ll escalate",
            "i will update you",
            "i’ll update you",
            "let me check",
            "let me verify",
        ]
    )


def main() -> None:
    sender = "971500009999"
    gateway.CONVERSATION_HISTORY[sender].clear()
    gateway.remember(sender, "user", "Need 1BR Downtown under 1M")
    gateway.remember(sender, "assistant", "NO MATCH FOUND")

    memory_ctx = gateway.build_live_response_context("هلا", sender)
    memory_reply = gateway.fast_path_reply("هلا", memory_ctx)

    unit_ctx = gateway.build_live_response_context("Who owns Binghatti House Unit 2201?", sender)
    unit_reply, _, _, _, unit_reply_ctx = gateway.openai_reply("Who owns Binghatti House Unit 2201?", sender)

    ownership_ctx = unit_reply_ctx

    casual_ctx = gateway.build_live_response_context("Everything good What about you", sender)
    casual_reply = gateway.fast_path_reply("Everything good What about you", casual_ctx)

    greeting_ctx = gateway.build_live_response_context("Hi", sender)
    greeting_reply = gateway.fast_path_reply("Hi", greeting_ctx)

    dec_reply, _, _, _, dec_ctx = gateway.openai_reply("Who owns DEC Tower Unit 2701?", sender)

    emergency_reply = gateway.emergency_non_silent_reply("Hello")

    tests = [
        {
            "id": "A",
            "name": "Previous conversation is read before reply",
            "pass": memory_ctx["conversation_history"] != "No prior history"
            and "Need 1BR Downtown" in memory_ctx["conversation_history"],
            "proof": {
                "history_loaded": memory_ctx["conversation_history"] != "No prior history",
                "history_excerpt": memory_ctx["conversation_history"][-180:],
                "reply": memory_reply,
            },
        },
        {
            "id": "B",
            "name": "Building + Unit retrieves correct record",
            "pass": unit_ctx["retrieval_proof"]["required"] is True
            and unit_ctx["retrieval_proof"]["executed"] is True
            and unit_ctx["retrieval_proof"]["match_found"] is True
            and any("Binghatti House" in json.dumps(m, ensure_ascii=False) for m in unit_ctx["retrieval_proof"]["matches"]),
            "proof": {
                "source_used": unit_ctx["retrieval_proof"]["source_used"],
                "query_used": unit_ctx["retrieval_proof"]["query_used"],
                "match_found": unit_ctx["retrieval_proof"]["match_found"],
                "result_count": unit_ctx["retrieval_proof"]["result_count"],
                "first_match": unit_ctx["retrieval_proof"]["matches"][0] if unit_ctx["retrieval_proof"]["matches"] else None,
            },
        },
        {
            "id": "C",
            "name": "Ownership questions route correctly",
            "pass": ownership_ctx["retrieval_proof"]["retrieval_intent"] == "ownership_lookup"
            and ownership_ctx["retrieval_proof"]["match_found"] is True
            and "restricted" in unit_reply.lower(),
            "proof": {
                "retrieval_intent": ownership_ctx["retrieval_proof"]["retrieval_intent"],
                "permission_decision": ownership_ctx["permission"]["decision"],
                "reply": unit_reply,
            },
        },
        {
            "id": "D",
            "name": "Casual chat still works",
            "pass": casual_ctx["conversation_objective"] in {"casual_greeting", "friend_chat"}
            and not has_property_qualification(casual_reply),
            "proof": {
                "objective": casual_ctx["conversation_objective"],
                "intent": casual_ctx["intent"],
                "reply": casual_reply,
            },
        },
        {
            "id": "E",
            "name": "No repeated greetings / no restart",
            "pass": greeting_ctx["conversation_history"] != "No prior history"
            and not has_property_qualification(greeting_reply),
            "proof": {
                "history_loaded": greeting_ctx["conversation_history"] != "No prior history",
                "reply": greeting_reply,
            },
        },
        {
            "id": "F",
            "name": "No AI-style workflow language",
            "pass": not has_ai_workflow_language(unit_reply) and not has_ai_workflow_language(dec_reply),
            "proof": {
                "ownership_reply": unit_reply,
                "missing_reply": dec_reply,
            },
        },
        {
            "id": "G",
            "name": "No dead silence",
            "pass": bool(emergency_reply.strip()),
            "proof": {
                "emergency_reply": emergency_reply,
            },
        },
        {
            "id": "H",
            "name": "No answer without retrieval for data questions",
            "pass": dec_reply == gateway.NO_MATCH_REPLY
            and dec_ctx["retrieval_proof"]["required"] is True
            and dec_ctx["retrieval_proof"]["executed"] is True
            and dec_ctx["retrieval_proof"]["match_found"] is False,
            "proof": {
                "reply": dec_reply,
                "source_used": dec_ctx["retrieval_proof"]["source_used"],
                "query_used": dec_ctx["retrieval_proof"]["query_used"],
                "match_found": dec_ctx["retrieval_proof"]["match_found"],
            },
        },
    ]

    print(json.dumps({"pass": all(t["pass"] for t in tests), "tests": tests}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
