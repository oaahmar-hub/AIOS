#!/usr/bin/env python3
"""Ask AIOS local runtime.

Answers operational questions from the AIOS command-center index and stages
actions through the GD Core Orchestrator contract. This is safe local execution:
no external API calls, no live sends, no CRM writes, and no publishing.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import OUTPUT_PATH, build as build_command_center_data
from gd_core_orchestrator import process as route_event


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
LAST_RESPONSE_PATH = REPORTS_DIR / "ASK_AIOS_LAST_RESPONSE.json"
DAILY_BRIEFING_PATH = REPORTS_DIR / "AIOS_DAILY_BRIEFING.json"

RISK_TERMS = {
    "legal",
    "contract",
    "payment",
    "bank",
    "dld",
    "rera",
    "ejari",
    "visa",
    "passport",
    "emirates id",
    "title deed",
    "transfer",
    "refund",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_data() -> dict[str, Any]:
    if not OUTPUT_PATH.exists():
        return build_command_center_data()
    try:
        return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return build_command_center_data()


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9@]+", text.lower()) if len(token) >= 2]


def _search(query: str, rows: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    terms = _tokens(query)
    scored = []
    for row in rows:
        title = str(row.get("title", "")).lower()
        path = str(row.get("path", "")).lower()
        category = str(row.get("category", "")).lower()
        haystack = " ".join(
            [
                title,
                path,
                category,
                str(row.get("excerpt", "")),
                " ".join(row.get("tags", []) or []),
            ]
        ).lower()
        score = 0
        for term in terms:
            if term in title:
                score += 6
            elif term in path:
                score += 4
            elif term in category:
                score += 3
            elif term in haystack:
                score += 1
        if "workflow" in terms and "workflows/" in path:
            score += 8
        if "noc" in terms and ("noc" in title or "noc" in path):
            score += 8
        if "checklist" in terms and ("checklist" in title or "checklist" in path):
            score += 4
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], item[1].get("path", "")))
    return [row for _, row in scored[:limit]]


def _intent(query: str) -> str:
    lowered = query.lower()
    if any(term in lowered for term in ("brief", "briefing", "morning", "today", "status")):
        return "daily_briefing"
    if any(term in lowered for term in ("run", "start", "stage", "workflow", "@")):
        return "workflow_stage"
    if any(term in lowered for term in ("find", "search", "where", "show", "retrieve")):
        return "search"
    if any(term in lowered for term in ("create", "draft", "caption", "reel", "flyer", "brochure", "campaign")):
        return "content_factory"
    return "answer"


def _risk_flags(query: str) -> list[str]:
    lowered = query.lower()
    return sorted(term for term in RISK_TERMS if term in lowered)


def _briefing(data: dict[str, Any]) -> dict[str, Any]:
    health = data.get("health", {})
    activity = data.get("activity", [])[:5]
    workflows = data.get("workflows", [])[:5]
    briefing = {
        "generated_at": _now(),
        "title": "AIOS Daily Briefing",
        "system_health": health,
        "priority_focus": [
            "Review Omar approval queue before any sensitive outbound action.",
            "Use Search Everything for SOPs, documents, workflows, and content assets.",
            "Stage workflows through AIOS contracts before external execution.",
        ],
        "recent_activity": activity,
        "ready_workflows": workflows,
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
        },
    }
    DAILY_BRIEFING_PATH.write_text(json.dumps(briefing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return briefing


def ask(query: str) -> dict[str, Any]:
    data = _load_data()
    intent = _intent(query)
    risk = _risk_flags(query)
    matches = _search(query, data.get("search_index", []), limit=6)
    route = route_event({"command": query})
    briefing = _briefing(data) if intent == "daily_briefing" else None

    if briefing:
        answer = "Daily briefing generated from command-center health, recent activity, and ready workflow contracts."
    elif matches:
        top = matches[0]
        answer = f"Best match: {top.get('title')} at {top.get('path')}. I found {len(matches)} relevant AIOS records and staged a safe local route."
    else:
        answer = "No strong local match found. I staged the request through the GD Core Orchestrator so it can become a task or workflow draft."

    response = {
        "answered_at": _now(),
        "query": query,
        "intent": intent,
        "answer": answer,
        "risk_flags": risk,
        "safety_gate": "HOLD_FOR_OMAR_APPROVAL" if risk else route.get("route", {}).get("safety_gate", "DRAFT_ONLY_NO_EXTERNAL_ACTION"),
        "matches": matches,
        "route": route,
        "briefing": briefing,
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
        },
    }
    LAST_RESPONSE_PATH.write_text(json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return response


def _parse_input() -> str:
    if len(sys.argv) > 1:
        arg = " ".join(sys.argv[1:]).strip()
        try:
            payload = json.loads(arg)
            return str(payload.get("query") or payload.get("command") or arg).strip()
        except Exception:
            return arg
    raw = sys.stdin.read().strip()
    if not raw:
        return "AIOS daily briefing"
    try:
        payload = json.loads(raw)
        return str(payload.get("query") or payload.get("command") or raw).strip()
    except Exception:
        return raw


if __name__ == "__main__":
    print(json.dumps(ask(_parse_input()), indent=2, ensure_ascii=False))
