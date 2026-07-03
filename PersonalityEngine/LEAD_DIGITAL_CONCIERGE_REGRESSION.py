#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")
sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/PersonalityEngine")

import simple_whatsapp_openai_gateway as gateway
from omar_personality_engine import build_personality_context, sentiment_handoff_decision


def main() -> None:
    sender = "971500008888"
    angry_text = "This is so slow and useless, fix it now!"

    direct = sentiment_handoff_decision(angry_text, "")
    reply, status, fallback, history, ctx = gateway.openai_reply(angry_text, sender)
    normal_ctx = build_personality_context("Hello", "", "Customer", "")

    tests = [
        {
            "name": "Angry/frustrated text triggers deterministic handoff",
            "pass": direct["action"] == "ESCALATE"
            and direct["priority"] == "HIGH"
            and direct["sentiment_score"] >= 5
            and {"slow", "useless", "fix"}.issubset(set(direct["triggers"])),
            "proof": direct,
        },
        {
            "name": "Gateway returns handoff before normal AI generation",
            "pass": status == 200
            and fallback is False
            and ctx["personality"]["sentiment_handoff"]["action"] == "ESCALATE"
            and "human specialist" in reply.lower(),
            "proof": {
                "status": status,
                "fallback": fallback,
                "reply": reply,
                "handoff": ctx["personality"]["sentiment_handoff"],
            },
        },
        {
            "name": "Normal text remains in AI response path",
            "pass": normal_ctx["sentiment_handoff"]["action"] == "RESPOND_VIA_AI"
            and normal_ctx["sentiment_handoff"]["priority"] == "NORMAL",
            "proof": normal_ctx["sentiment_handoff"],
        },
        {
            "name": "Lead Digital Operations Concierge persona is loaded",
            "pass": normal_ctx["operations_persona"] == "LEAD_DIGITAL_OPERATIONS_CONCIERGE"
            and "Zero-Latency Accuracy" in normal_ctx["operations_persona_text"]
            and "Human-Equivalence" in normal_ctx["operations_persona_text"],
            "proof": {
                "persona": normal_ctx["operations_persona"],
                "persona_file": normal_ctx["operations_persona_file"],
            },
        },
    ]

    failed = [test for test in tests if not test["pass"]]
    print(json.dumps({"tests": tests, "failed": failed}, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
