#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

import simple_whatsapp_openai_gateway as gateway


gateway.load_relationship_store()

ctx = gateway.build_live_response_context("عمر همام انا", "971506794299")
reply = gateway.fast_path_reply("عمر همام انا", ctx)

tests = [
    (
        "old_chat_detected_before_reply",
        ctx["contact_context"].get("known_chat") is True
        and ctx["relationship"] in {"Existing Client", "CLIENT"}
        and ctx["contact_context"].get("known_contact_name") == "H M Hasaan Noc Palm",
    ),
    (
        "old_subject_loaded",
        "Nakheel/Palm" in ctx["contact_context"].get("old_chat_subject_summary", "")
        and "portal/account access" in ctx["contact_context"].get("old_chat_subject_summary", ""),
    ),
    (
        "old_history_loaded",
        "Nakheel Account Access" in ctx["conversation_history"]
        and "ضروري" in ctx["conversation_history"],
    ),
    (
        "identity_not_business_qualification",
        ctx["intent"] == "identity_intro"
        and "عمر همام" in reply
        and all(x not in reply for x in ["شراء", "إيجار", "استشارة", "عقاري"]),
    ),
]

results = [
    {"test": name, "pass": bool(ok)}
    for name, ok in tests
]
print(
    json.dumps(
        {
            "passed": sum(r["pass"] for r in results),
            "total": len(results),
            "results": results,
            "context": {
                "known_chat": ctx["contact_context"].get("known_chat"),
                "known_contact_name": ctx["contact_context"].get("known_contact_name"),
                "old_chat_subject_summary": ctx["contact_context"].get("old_chat_subject_summary"),
                "relationship": ctx["relationship"],
                "intent": ctx["intent"],
                "reply": reply,
            },
        },
        ensure_ascii=False,
        indent=2,
    )
)
