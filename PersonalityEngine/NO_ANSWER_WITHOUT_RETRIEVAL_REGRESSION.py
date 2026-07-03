#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

import simple_whatsapp_openai_gateway as gateway


def main() -> None:
    sender = "971500000000"
    cases = []

    missing_reply, _, _, _, missing_ctx = gateway.openai_reply("Who owns DEC Tower Unit 2701?", sender)
    cases.append(
        {
            "test": "missing_inventory_blocks_conversation",
            "pass": missing_reply == gateway.NO_MATCH_REPLY
            and missing_ctx["retrieval_proof"]["retrieval_intent"] == "ownership_lookup"
            and missing_ctx["retrieval_proof"]["match_found"] is False,
            "reply": missing_reply,
            "retrieval_proof": missing_ctx["retrieval_proof"],
        }
    )

    known_ctx = gateway.build_live_response_context("Who owns Binghatti House Unit 2201?", sender)
    cases.append(
        {
            "test": "known_inventory_retrieves_before_reply",
            "pass": known_ctx["retrieval_proof"]["retrieval_intent"] == "ownership_lookup"
            and known_ctx["retrieval_proof"]["executed"] is True
            and known_ctx["retrieval_proof"]["match_found"] is True
            and known_ctx["retrieval_proof"]["result_count"] > 0,
            "retrieval_proof": known_ctx["retrieval_proof"],
        }
    )

    yas_ctx = gateway.build_live_response_context("Find Yas Acres units", sender)
    cases.append(
        {
            "test": "project_inventory_retrieves_before_reply",
            "pass": yas_ctx["retrieval_proof"]["retrieval_intent"] == "inventory_lookup"
            and yas_ctx["retrieval_proof"]["executed"] is True
            and yas_ctx["retrieval_proof"]["match_found"] is True,
            "retrieval_proof": yas_ctx["retrieval_proof"],
        }
    )

    print(json.dumps({"pass": all(case["pass"] for case in cases), "cases": cases}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
