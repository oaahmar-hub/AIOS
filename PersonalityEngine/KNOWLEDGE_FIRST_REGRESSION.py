#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

from simple_whatsapp_openai_gateway import build_live_response_context, fast_path_reply


def assert_case(name, passed, detail):
    return {"test": name, "pass": bool(passed), "detail": detail}


def main():
    results = []

    unit_ctx = build_live_response_context("Tell me details of Unit 801 Anwa.", "knowledge-first-test-unit")
    unit_reply = fast_path_reply("Tell me details of Unit 801 Anwa.", unit_ctx)
    results.append(
        assert_case(
            "unit_details_answer_first",
            bool(unit_reply)
            and ("Found this in inventory" in unit_reply or "verified details" in unit_reply)
            and "?" not in unit_reply,
            {
                "objective": unit_ctx["conversation_objective"],
                "intent": unit_ctx["intent"],
                "knowledge_probe": unit_ctx["knowledge_probe"],
                "reply": unit_reply,
            },
        )
    )

    roi_history_sender = "knowledge-first-test-roi"
    # Seed the in-memory history to simulate a real active property search.
    from simple_whatsapp_openai_gateway import remember

    remember(roi_history_sender, "user", "I want a 1 bedroom in Creek Harbour for sale at a good price.")
    remember(roi_history_sender, "assistant", "Perfect, what budget?")
    remember(roi_history_sender, "user", "1.6M")
    remember(roi_history_sender, "assistant", "Ready/resale or off-plan?")
    roi_ctx = build_live_response_context("No preference. High ROI.", roi_history_sender)
    roi_reply = fast_path_reply("No preference. High ROI.", roi_ctx)
    results.append(
        assert_case(
            "roi_preference_action_first",
            bool(roi_reply)
            and "corrected" not in roi_reply.lower()
            and "?" not in roi_reply,
            {
                "objective": roi_ctx["conversation_objective"],
                "intent": roi_ctx["intent"],
                "knowledge_probe": roi_ctx["knowledge_probe"],
                "reply": roi_reply,
            },
        )
    )

    doc_ctx = build_live_response_context("Find Nakheel modification documents", "knowledge-first-test-doc")
    results.append(
        assert_case(
            "document_request_searches_knowledge_before_asking",
            doc_ctx["conversation_objective"] == "document_request"
            and doc_ctx["knowledge_probe"]["searched"]["documents"] is True
            and bool(doc_ctx["knowledge_probe"]["document_hits"]),
            {
                "objective": doc_ctx["conversation_objective"],
                "knowledge_probe": doc_ctx["knowledge_probe"],
            },
        )
    )

    passed = sum(1 for r in results if r["pass"])
    print(json.dumps({"passed": passed, "total": len(results), "results": results}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
