from __future__ import annotations

"""AIOS Memory Layer v1.

Practical memory retrieval using existing sources only:
- Airtable export payloads passed in by connector/workflow
- Notion/Knowledge Vault local markdown
- Leads, Tasks, Contact notes, and Comms history

This module does not create a new database. It composes a response-ready memory
packet that can be called before WhatsApp/email/manual replies.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import argparse
import json
import os
import re


ROOT = Path(os.getenv("AIOS_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))).expanduser().resolve()
KNOWLEDGE_VAULT = ROOT / "KnowledgeBase" / "AIOS_Knowledge_Vault"
OPERATIONS_CORPUS = ROOT / "KnowledgeBase" / "Operations_Corpus" / "text"


@dataclass
class MemoryPacket:
    contact_query: str
    contact_history: list[dict[str, Any]]
    preferences: list[str]
    open_tasks: list[dict[str, Any]]
    lead_context: list[dict[str, Any]]
    knowledge_matches: list[str]
    operations_matches: list[str]
    response_rules: list[str]


def _canon(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = _canon(text)
    return any(_canon(term) in lowered for term in terms if term)


def _search_files(root: Path, terms: list[str], limit: int = 8) -> list[str]:
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".csv"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        haystack = f"{path.name}\n{text}"
        if _contains_any(haystack, terms):
            hits.append(str(path))
        if len(hits) >= limit:
            break
    return hits


def _filter_records(records: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for record in records:
        if _contains_any(json.dumps(record, ensure_ascii=False), terms):
            matched.append(record)
    return matched


def build_memory_packet(
    *,
    contact_query: str,
    contacts: list[dict[str, Any]] | None = None,
    leads: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    comms: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
) -> MemoryPacket:
    terms = [contact_query]
    if "@" in contact_query:
        terms.append(contact_query.split("@", 1)[0])
    digits = re.sub(r"\D+", "", contact_query)
    if digits:
        terms.append(digits[-7:])

    contacts = contacts or []
    leads = leads or []
    tasks = tasks or []
    comms = comms or []
    notes = notes or []

    matched_contacts = _filter_records(contacts, terms)
    matched_leads = _filter_records(leads, terms)
    matched_tasks = _filter_records(tasks, terms)
    matched_comms = _filter_records(comms, terms)

    preference_terms = ["prefers", "budget", "language", "area", "bed", "bedroom", "villa", "apartment", "cash", "mortgage"]
    preferences = [
        note for note in notes
        if _contains_any(note, preference_terms) and _contains_any(note, terms)
    ][:10]

    knowledge_terms = terms + ["contact", "lead", "follow", "preference", "case", "playbook"]
    operations_terms = terms + ["noc", "transfer", "dld", "rera", "mortgage", "visa"]

    return MemoryPacket(
        contact_query=contact_query,
        contact_history=matched_contacts + matched_comms[:10],
        preferences=preferences,
        open_tasks=matched_tasks[:10],
        lead_context=matched_leads[:10],
        knowledge_matches=_search_files(KNOWLEDGE_VAULT, knowledge_terms, limit=8),
        operations_matches=_search_files(OPERATIONS_CORPUS, operations_terms, limit=5),
        response_rules=[
            "Do not ask again for information already present in contact_history, lead_context, preferences, or open_tasks.",
            "Use short premium executive style.",
            "Escalate legal, financial, payment, government, or uncertain topics to Omar review.",
            "If the contact has an open task, acknowledge the pending action instead of restarting the conversation.",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AIOS memory packet v1")
    parser.add_argument("contact_query")
    args = parser.parse_args()
    packet = build_memory_packet(contact_query=args.contact_query)
    print(json.dumps(asdict(packet), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
