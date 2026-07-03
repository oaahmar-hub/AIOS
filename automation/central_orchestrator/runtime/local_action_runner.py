#!/usr/bin/env python3
"""AIOS local action runner.

Turns an Ask AIOS response into safe local action artifacts. This is the bridge
between "think/search/recommend" and "execute" without external side effects.
It writes local queue packets and draft files only; live sends, CRM writes,
calendar changes, Drive changes, and publishing remain disabled.
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ask_aios import LAST_RESPONSE_PATH, ask


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
ACTION_DIR = REPORTS_DIR / "actions"
ACTION_QUEUE_PATH = REPORTS_DIR / "ACTION_QUEUE.json"
ACTION_RESULT_PATH = REPORTS_DIR / "LOCAL_ACTION_RUNNER_RESULT.json"

RISK_HOLD_GATES = {"HOLD_FOR_OMAR_APPROVAL"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "aios-action"


def _load_last_response() -> dict[str, Any]:
    try:
        return json.loads(LAST_RESPONSE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ask("Prepare today's AIOS daily briefing")


def _action_type(response: dict[str, Any]) -> str:
    intent = response.get("intent", "")
    query = response.get("query", "").lower()
    if intent == "daily_briefing" or "briefing" in query:
        return "daily_briefing_packet"
    if intent == "content_factory" or any(term in query for term in ("caption", "reel", "flyer", "brochure", "campaign")):
        return "content_draft_packet"
    if intent == "workflow_stage" or response.get("matches"):
        return "workflow_packet"
    return "task_packet"


def _markdown_for(action: dict[str, Any], response: dict[str, Any]) -> str:
    lines = [
        f"# {action['title']}",
        "",
        f"Action ID: `{action['action_id']}`",
        f"Created: `{action['created_at']}`",
        f"Safety gate: `{action['safety_gate']}`",
        f"Action type: `{action['type']}`",
        "",
        "## Request",
        response.get("query", ""),
        "",
        "## Local Answer",
        response.get("answer", ""),
        "",
        "## Evidence Matches",
    ]
    for match in response.get("matches", [])[:6]:
        lines.append(f"- `{match.get('path', '')}` — {match.get('title', '')}")
    lines.extend(
        [
            "",
            "## Execution Policy",
            "- Local packet only.",
            "- No messages sent.",
            "- No CRM rows written.",
            "- No calendar events created.",
            "- No Drive files modified.",
            "- No content published.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_action(response: dict[str, Any]) -> dict[str, Any]:
    ACTION_DIR.mkdir(parents=True, exist_ok=True)
    action_id = "ACT-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + str(uuid.uuid4())[:6].upper()
    action_type = _action_type(response)
    title = {
        "daily_briefing_packet": "AIOS Daily Briefing Packet",
        "content_draft_packet": "AIOS Content Draft Packet",
        "workflow_packet": "AIOS Workflow Packet",
        "task_packet": "AIOS Task Packet",
    }.get(action_type, "AIOS Action Packet")
    safety_gate = response.get("safety_gate") or "DRAFT_ONLY_NO_EXTERNAL_ACTION"
    status = "blocked_for_omar_approval" if safety_gate in RISK_HOLD_GATES else "local_packet_created"
    md_name = f"{action_id}-{_slug(title)}.md"
    md_path = ACTION_DIR / md_name
    action = {
        "action_id": action_id,
        "created_at": _now(),
        "type": action_type,
        "title": title,
        "status": status,
        "safety_gate": safety_gate,
        "source_query": response.get("query", ""),
        "answer": response.get("answer", ""),
        "match_count": len(response.get("matches", [])),
        "top_match": (response.get("matches") or [{}])[0],
        "artifact_path": md_path.relative_to(AIOS_ROOT).as_posix(),
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
        },
    }
    md_path.write_text(_markdown_for(action, response), encoding="utf-8")
    return action


def _load_queue() -> list[dict[str, Any]]:
    try:
        data = json.loads(ACTION_QUEUE_PATH.read_text(encoding="utf-8"))
        return data.get("actions", []) if isinstance(data, dict) else []
    except Exception:
        return []


def run(query: str | None = None) -> dict[str, Any]:
    response = ask(query) if query else _load_last_response()
    action = build_action(response)
    queue = [action] + _load_queue()
    queue = queue[:50]
    result = {
        "ran_at": _now(),
        "passed": True,
        "action": action,
        "queue_count": len(queue),
        "actions": queue,
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
        },
    }
    ACTION_QUEUE_PATH.write_text(json.dumps({"updated_at": result["ran_at"], "actions": queue}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ACTION_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _parse_query() -> str | None:
    if len(sys.argv) > 1:
        arg = " ".join(sys.argv[1:]).strip()
        try:
            payload = json.loads(arg)
            return str(payload.get("query") or payload.get("command") or "").strip() or None
        except Exception:
            return arg
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return str(payload.get("query") or payload.get("command") or "").strip() or None
    except Exception:
        return raw


if __name__ == "__main__":
    print(json.dumps(run(_parse_query()), indent=2, ensure_ascii=False))
