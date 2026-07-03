from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aios_brain_router import RouteDecision, classify, property_search


ROOT = Path(os.getenv("AIOS_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))).expanduser().resolve()
OPERATIONS_CORPUS = ROOT / "KnowledgeBase" / "Operations_Corpus" / "text"
KNOWLEDGE_VAULT = ROOT / "KnowledgeBase" / "AIOS_Knowledge_Vault"


@dataclass
class EntryPointResult:
    request: str
    route: str
    source: str
    action: str
    result: Any


def _search_local_text(folder: Path, terms: list[str], limit: int = 5) -> list[str]:
    hits: list[str] = []
    if not folder.exists():
        return hits
    term_set = [t.lower() for t in terms if t]
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lowered = text.lower()
        if any(t in lowered for t in term_set):
            hits.append(str(path))
        if len(hits) >= limit:
            break
    return hits


def _drive_action(query: str) -> dict[str, str]:
    return {
        "source": "Google Drive",
        "action": f"Search Drive for: {query}",
    }


def _calendar_airtable_action(query: str) -> dict[str, str]:
    return {
        "source": "Google Calendar + Airtable",
        "action": f"Create or schedule operational task: {query}",
    }


def _gmail_action(query: str) -> dict[str, str]:
    return {
        "source": "Gmail",
        "action": f"Search inbox for: {query}",
    }


def _operations_action(query: str) -> dict[str, Any]:
    hits = _search_local_text(
        OPERATIONS_CORPUS,
        ["transfer", "noc", "mortgage", "dld", "rera", "tarakheesi", "icp", "gdrfa", "ejari"],
        limit=5,
    )
    return {
        "source": "Operations Brain",
        "action": f"Search local operations corpus for: {query}",
        "matches": hits,
    }


def _knowledge_action(query: str) -> dict[str, Any]:
    hits = _search_local_text(
        KNOWLEDGE_VAULT,
        ["case", "playbook", "hsh", "provider blocker", "contract", "knowledge"],
        limit=5,
    )
    return {
        "source": "Knowledge Vault",
        "action": f"Search knowledge vault for: {query}",
        "matches": hits,
    }


def route_request(query: str) -> EntryPointResult:
    decision: RouteDecision = classify(query)
    if decision.route == "property_search":
        result = property_search(query, limit=5)
        action = "Query Property_Master_Database"
        source = "Property_Master_Database"
    elif decision.route == "document_search":
        result = _drive_action(query)
        action = "Query Google Drive"
        source = "Google Drive"
    elif decision.route == "meeting_task":
        result = _calendar_airtable_action(query)
        action = "Query Google Calendar + Airtable"
        source = "Google Calendar + Airtable"
    elif decision.route == "email_lookup":
        result = _gmail_action(query)
        action = "Query Gmail"
        source = "Gmail"
    elif decision.route == "process_question":
        result = _operations_action(query)
        action = "Query Operations Brain"
        source = "Operations Brain"
    else:
        result = _knowledge_action(query)
        action = "Query Knowledge Vault"
        source = "Knowledge Vault"

    return EntryPointResult(
        request=query,
        route=decision.route,
        source=source,
        action=action,
        result=result,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AIOS entry point")
    parser.add_argument("request", help="User request to dispatch")
    args = parser.parse_args()
    print(json.dumps(asdict(route_request(args.request)), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
