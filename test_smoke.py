#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "transport"))

import simple_whatsapp_openai_gateway as gateway


def main():
    gateway.load_relationship_store()
    sender = next(iter(gateway.RELATIONSHIP_STORE.keys()), "971506794299")
    ctx = gateway.build_live_response_context("Good evening yooo", sender)
    result = {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(gateway.DATA_DIR),
        "relationship_store_path": gateway.RELATIONSHIP_STORE_PATH,
        "log_path": gateway.LOG_PATH,
        "known_contact_name": ctx.get("contact_context", {}).get("known_contact_name"),
        "relationship": ctx.get("relationship"),
        "intent": ctx.get("intent"),
        "history_loaded": ctx.get("conversation_history") != "No prior history",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
