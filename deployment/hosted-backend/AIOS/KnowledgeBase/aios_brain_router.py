from __future__ import annotations

"""AIOS Brain Router

A lightweight dispatch layer for the first production AIOS path.
The router decides the target knowledge system, then delegates the lookup.

Canonical production source: AIOS/KnowledgeBase/aios_brain_router.py.
Deployment copies must be synced from this file before packaging hosted builds.

This local version uses the Property Master Database directly and keeps the
other branches as integration stubs for Drive/Gmail/Calendar/Airtable/Operations
Brain/Knowledge Vault lookups handled by the Codex-connected production stack.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
import re
import sqlite3

DB_PATH = Path(__file__).resolve().parent / "Property_Master_Database.sqlite"

Route = Literal[
    "property_search",
    "document_search",
    "meeting_task",
    "email_lookup",
    "process_question",
    "company_knowledge",
]

RetrievalIntent = Literal[
    "ownership_lookup",
    "property_lookup",
    "inventory_lookup",
    "document_lookup",
    "operations_lookup",
    "followup_lookup",
    "contact_lookup",
    "project_lookup",
    "developer_lookup",
]


@dataclass
class RouteDecision:
    route: Route
    reason: str
    target: str
    retrieval_intent: RetrievalIntent = "property_lookup"
    confidence: float = 0.5


def canon(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _has_unit_reference(q: str) -> bool:
    return bool(
        re.search(r"\b(?:unit|apt|apartment|villa|plot|office)\s*[a-z0-9/-]*\s*\d{2,}\b", q)
        or re.search(r"\b\d{3,5}\b", q)
    )


def classify_retrieval_intent(query: str) -> RouteDecision:
    """Classify what kind of retrieval should happen before choosing a tool.

    The key production rule is: decide the retrieval intent first, then select
    the source. This prevents ownership/contact/document questions from falling
    into the generic property-search path.
    """
    q = canon(query)

    if any(k in q for k in ["owner", "owns", "ownership", "مالك", "صاحب الوحدة", "who owns"]):
        return RouteDecision(
            "property_search",
            "ownership language detected; owner fields require permission-layer handling",
            "Property_Master_Database ownership/inventory rows",
            "ownership_lookup",
            0.95,
        )

    if any(k in q for k in ["passport", "phone", "mobile", "email", "contact", "number", "رقم", "ايميل"]):
        return RouteDecision(
            "company_knowledge",
            "contact/person lookup language detected",
            "CRM + Contact History + Knowledge Vault",
            "contact_lookup",
            0.88,
        )

    if any(k in q for k in ["document", "docs", "file", "pdf", "contract", "title deed", "noc file", "nakheel", "modification", "drive", "ملف", "عقد"]):
        return RouteDecision(
            "document_search",
            "document retrieval language detected",
            "Google Drive + local document vault",
            "document_lookup",
            0.92,
        )

    if any(k in q for k in ["noc", "transfer process", "dld", "rera", "mortgage", "visa", "company setup", "procedure", "fees", "timeline", "requirements", "خطوات", "رسوم"]):
        return RouteDecision(
            "process_question",
            "operations/process language detected",
            "Operations Brain",
            "operations_lookup",
            0.9,
        )

    if any(k in q for k in ["follow up", "follow-up", "remind", "task", "meeting", "calendar", "schedule", "book", "appointment", "متابعة", "موعد"]):
        return RouteDecision(
            "meeting_task",
            "follow-up/task/calendar language detected",
            "Google Calendar + Airtable",
            "followup_lookup",
            0.9,
        )

    if any(k in q for k in ["developer", "emaar", "nakheel", "aldar", "damac", "binghatti", "reportage", "tiger", "eleven", "developer of"]):
        return RouteDecision(
            "property_search",
            "developer lookup language detected",
            "Property_Master_Database developers/projects",
            "developer_lookup",
            0.82,
        )

    if any(k in q for k in ["project", "community", "building", "tower", "phase", "launch", "payment plan", "brochure", "مشروع", "برج"]):
        return RouteDecision(
            "property_search",
            "project/building lookup language detected",
            "Property_Master_Database projects/inventory",
            "project_lookup",
            0.84,
        )

    if _has_unit_reference(q) or any(k in q for k in ["availability", "available", "inventory", "unit", "price list", "stock", "وحدة", "متوفر"]):
        return RouteDecision(
            "property_search",
            "unit/inventory language detected",
            "Property_Master_Database inventory rows",
            "inventory_lookup",
            0.86,
        )

    if any(k in q for k in ["email", "mail", "inbox", "message from"]):
        return RouteDecision(
            "email_lookup",
            "email lookup language detected",
            "Gmail",
            "contact_lookup",
            0.78,
        )

    if any(k in q for k in ["case", "historical", "lessons", "playbook", "knowledge", "omar"]):
        return RouteDecision(
            "company_knowledge",
            "company knowledge language detected",
            "Knowledge Vault",
            "operations_lookup",
            0.72,
        )

    return RouteDecision(
        "property_search",
        "generic property/inquiry default",
        "Property_Master_Database",
        "property_lookup",
        0.62,
    )


def classify(query: str) -> RouteDecision:
    return classify_retrieval_intent(query)


def property_search(query: str, limit: int = 5) -> list[dict]:
    # Import the already-proven local search engine.
    from property_recommendation_agent import PropertyRecommendationAgent

    agent = PropertyRecommendationAgent(DB_PATH)
    matches = agent.search(query_text=query, limit=limit)
    if matches:
        return [m.__dict__ for m in matches]

    # Fallback: if the exact bedroom-filtered search is too strict, broaden the
    # search to the routed area/budget so the brain still returns usable matches.
    q = canon(query)
    area = ""
    for term in ("yas island", "saadiyat island", "al reem island", "al raha gardens", "al raha", "al reeman", "jvc", "jumeirah village circle", "dubai", "abu dhabi"):
        if term in q:
            area = term.title() if term != "jvc" else "Jumeirah Village Circle"
            break
    budget = None
    m = re.search(r"(?:under|below|max(?:imum)?|up to)\s*(?:aed\s*)?(\d+(?:\.\d+)?)\s*(m|million)?", q)
    if m:
        amount = float(m.group(1))
        budget = int(amount * 1_000_000 if m.group(2) else amount)
    bedrooms = None
    m = re.search(r"\b(\d+)\s*(?:br|bed|bedroom)\b", q)
    if m:
        bedrooms = int(m.group(1))

    if area or budget is not None or bedrooms is not None:
        matches = agent.search(
            query_text=" ".join(part for part in [area, f"under {budget}" if budget else ""] if part).strip(),
            area=area,
            bedrooms=bedrooms,
            max_price=budget,
            limit=limit,
        )
    if not matches and area:
        matches = agent.search(query_text=area, area=area, limit=limit)
    return [m.__dict__ for m in matches]


def db_stats() -> dict:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    stats = {}
    for table in ["developers", "areas", "projects", "property_types", "inventory_files", "inventory_rows", "source_row_map"]:
        stats[table] = cur.execute(f"select count(*) from {table}").fetchone()[0]
    con.close()
    return stats


if __name__ == "__main__":
    import argparse, json

    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    args = ap.parse_args()
    decision = classify(args.query)
    result = {
        "route": decision.route,
        "retrieval_intent": decision.retrieval_intent,
        "reason": decision.reason,
        "target": decision.target,
        "confidence": decision.confidence,
    }
    if decision.route == "property_search":
        result["matches"] = property_search(args.query)
    else:
        result["status"] = "integrated via live connector in Codex session"
    print(json.dumps(result, indent=2, ensure_ascii=False))
