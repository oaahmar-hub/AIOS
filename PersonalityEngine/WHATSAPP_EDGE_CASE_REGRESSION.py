#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hassanka/Downloads/AIOS/PersonalityEngine")
TRANSPORT_ROOT = Path("/Users/hassanka/Downloads/AIOS/transport")
sys.path.insert(0, str(TRANSPORT_ROOT))


def run_json(script: str) -> dict:
    output = subprocess.check_output([sys.executable, str(ROOT / script)], text=True)
    return json.loads(output)


def main() -> None:
    results = []

    import simple_whatsapp_openai_gateway as gateway

    greeting_ctx = gateway.build_live_response_context("هاي", "wa-edge-001-zaki")
    greeting_reply = gateway.fast_path_reply("هاي", greeting_ctx)
    results.append(
        {
            "edge_case": "WA-EDGE-001",
            "regression": "WHATSAPP_EDGE_CASE_REGRESSION.py",
            "pass": greeting_ctx.get("social_context", {}).get("category") != "correction"
            and greeting_ctx.get("intent") == "greeting"
            and "صححت" not in (greeting_reply or "")
            and "corrected" not in (greeting_reply or "").lower(),
            "detail": {
                "objective": greeting_ctx.get("conversation_objective"),
                "intent": greeting_ctx.get("intent"),
                "social": greeting_ctx.get("social_context"),
                "reply": greeting_reply,
            },
        }
    )

    rental_message = "Any one bedroom available for rent in downtown up to 100k ?"
    rental_ctx = gateway.build_live_response_context(rental_message, "wa-edge-002-rental")
    rental_reply = gateway.fast_path_reply(rental_message, rental_ctx)
    results.append(
        {
            "edge_case": "WA-EDGE-002",
            "regression": "WHATSAPP_EDGE_CASE_REGRESSION.py",
            "pass": "verified rental" in (rental_reply or "").lower()
            and "source is connected" in (rental_reply or "").lower()
            and "I’ll check" not in (rental_reply or "")
            and "Got it — I’ll check the best options" not in (rental_reply or ""),
            "detail": {
                "objective": rental_ctx.get("conversation_objective"),
                "intent": rental_ctx.get("intent"),
                "reply": rental_reply,
            },
        }
    )

    knowledge = run_json("KNOWLEDGE_FIRST_REGRESSION.py")
    results.append(
        {
            "edge_case": "WA-EDGE-003",
            "regression": "KNOWLEDGE_FIRST_REGRESSION.py",
            "pass": knowledge.get("passed") == knowledge.get("total"),
            "detail": "Unit-specific request checks inventory and does not invent details.",
        }
    )

    old_chat = run_json("OLD_CHAT_CONTEXT_REGRESSION.py")
    results.append(
        {
            "edge_case": "WA-EDGE-004",
            "regression": "OLD_CHAT_CONTEXT_REGRESSION.py",
            "pass": old_chat.get("passed") == old_chat.get("total"),
            "detail": "Old contact loads existing chat context before reply.",
        }
    )

    markus = run_json("MARKUS_CONVERSATION_REGRESSION.py")
    results.append(
        {
            "edge_case": "WA-EDGE-005",
            "regression": "MARKUS_CONVERSATION_REGRESSION.py",
            "pass": markus.get("passed") == markus.get("total"),
            "detail": "Casual friend chat does not become lead qualification.",
        }
    )

    passed = sum(1 for item in results if item["pass"])
    report = {"passed": passed, "total": len(results), "results": results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
