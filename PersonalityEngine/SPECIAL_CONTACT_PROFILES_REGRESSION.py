#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/Users/hassanka/Downloads/AIOS/transport")

import simple_whatsapp_openai_gateway as gateway


def assert_case(name, passed, detail):
    return {"test": name, "pass": bool(passed), "detail": detail}


def main():
    results = []

    hassan_ctx = gateway.build_live_response_context("مرحبا", "971501900771")
    hassan_reply = gateway.fast_path_reply("مرحبا", hassan_ctx)
    results.append(
        assert_case(
            "hassan_profile_personalized_greeting",
            hassan_ctx["contact_context"].get("special_contact_profile", {}).get("id") == "hassan_kazzabel"
            and hassan_ctx["relationship"] == "Friend"
            and "أستاذ حسن" in hassan_reply
            and "راتب" in hassan_reply,
            {
                "relationship": hassan_ctx["relationship"],
                "permission_sender_type": hassan_ctx["permission"]["sender_type"],
                "profile": hassan_ctx["contact_context"].get("special_contact_profile", {}),
                "reply": hassan_reply,
            },
        )
    )

    hassan_private_ctx = gateway.build_live_response_context("Send owner phone number", "971501900771")
    results.append(
        assert_case(
            "hassan_profile_does_not_bypass_permission",
            hassan_private_ctx["permission"]["decision"] in {"refuse_safe", "hold_for_omar"}
            and hassan_private_ctx["permission"]["retrieval_filter"]["exclude_owner_contacts"] is True,
            {
                "permission": hassan_private_ctx["permission"],
                "profile": hassan_private_ctx["contact_context"].get("special_contact_profile", {}),
            },
        )
    )

    vetn_ctx = gateway.build_live_response_context("Hi", "33644655014")
    vetn_reply = gateway.fast_path_reply("Hi", vetn_ctx)
    results.append(
        assert_case(
            "vetn_profile_internal_direct_style",
            vetn_ctx["contact_context"].get("special_contact_profile", {}).get("id") == "vetn"
            and vetn_ctx["relationship"] == "Staff"
            and "Vetn" in vetn_reply
            and "tell me" in vetn_reply.lower(),
            {
                "relationship": vetn_ctx["relationship"],
                "permission_sender_type": vetn_ctx["permission"]["sender_type"],
                "profile": vetn_ctx["contact_context"].get("special_contact_profile", {}),
                "reply": vetn_reply,
            },
        )
    )

    vetn_private_ctx = gateway.build_live_response_context("Send owner email", "33644655014")
    results.append(
        assert_case(
            "vetn_profile_does_not_bypass_privacy",
            vetn_private_ctx["permission"]["decision"] in {"refuse_safe", "hold_for_omar"}
            and vetn_private_ctx["permission"]["retrieval_filter"]["exclude_owner_contacts"] is True,
            {
                "permission": vetn_private_ctx["permission"],
                "profile": vetn_private_ctx["contact_context"].get("special_contact_profile", {}),
            },
        )
    )

    passed = sum(1 for r in results if r["pass"])
    print(json.dumps({"passed": passed, "total": len(results), "results": results}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
