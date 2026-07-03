from __future__ import annotations

"""AIOS Follow-Up Engine v1.

Daily run composer over existing CRM/task/calendar/email inputs. No new DB.
It accepts Airtable/Calendar/Gmail payloads from connectors or workflow nodes and
returns due actions, draft follow-ups, and a CEO brief.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
import argparse
import json

from aios_memory_layer_v1 import build_memory_packet


@dataclass
class DueAction:
    source: str
    title: str
    priority: str
    due: str
    reason: str
    draft_follow_up: str
    send_decision: str
    send_channel: str
    send_reason: str


@dataclass
class FollowUpRun:
    run_date: str
    due_actions: list[DueAction]
    auto_send_queue: list[DueAction]
    approval_queue: list[DueAction]
    ceo_brief: str
    system_notes: list[str]


AUTO_SEND_TERMS = {
    "viewing",
    "appointment",
    "document",
    "documents",
    "status update",
    "status",
    "reminder",
    "follow-up",
    "follow up",
    "brochure",
    "shortlist",
}

HOLD_TERMS = {
    "negotiation",
    "negotiate",
    "price",
    "offer",
    "discount",
    "legal",
    "contract",
    "complaint",
    "dispute",
    "sensitive",
    "payment",
    "commission",
    "government",
    "rera",
    "dld",
    "mortgage",
    "visa",
    "bank",
    "tax",
}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raw = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _field(record: dict[str, Any], *names: str) -> Any:
    fields = record.get("fields", record)
    for name in names:
        if name in fields:
            return fields[name]
    return None


def _draft(title: str, reason: str) -> str:
    return (
        f"Hi, quick follow-up on {title}. "
        f"I have this pending: {reason}. "
        "Send me any update and I will take it from there."
    )


def _send_policy(title: str, reason: str, source: str) -> tuple[str, str, str]:
    text = f"{title} {reason}".lower()
    if any(term in text for term in HOLD_TERMS):
        return ("hold_for_omar", "none", "Sensitive/price/legal/complaint topic requires human approval.")
    if any(term in text for term in AUTO_SEND_TERMS):
        return ("auto_send_approved", "existing_crm_channel", "Approved safe reminder/status/document/viewing follow-up.")
    if source in {"Google Calendar", "Airtable Tasks"}:
        return ("auto_send_approved", "existing_crm_channel", "Operational reminder with no sensitive terms.")
    return ("hold_for_omar", "none", "Unclassified follow-up held by default.")


def run_follow_up_engine(
    *,
    leads: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    calendar_events: list[dict[str, Any]] | None = None,
    important_emails: list[dict[str, Any]] | None = None,
    run_date: date | None = None,
) -> FollowUpRun:
    today = run_date or date.today()
    leads = leads or []
    tasks = tasks or []
    calendar_events = calendar_events or []
    important_emails = important_emails or []
    due_actions: list[DueAction] = []

    def add_action(source: str, title: str, priority: str, due: str, reason: str) -> None:
        decision, channel, send_reason = _send_policy(title, reason, source)
        due_actions.append(
            DueAction(
                source,
                title,
                priority,
                due,
                reason,
                _draft(title, reason),
                decision,
                channel,
                send_reason,
            )
        )

    for lead in leads:
        title = str(_field(lead, "Lead", "lead", "title") or "Lead follow-up")
        due = _parse_date(_field(lead, "Next action date", "next_action_date", "First-response due"))
        status = str(_field(lead, "Status", "status") or "").lower()
        if (due and due <= today) or status in {"new", "open", "active"}:
            reason = str(_field(lead, "Next action", "next_action", "Draft reply", "Notes") or "lead requires follow-up")
            memory = build_memory_packet(contact_query=title, leads=[lead], tasks=tasks)
            if memory.open_tasks:
                reason += " | existing task context loaded"
            add_action("Airtable Leads", title, "High", str(due or today), reason)

    for task in tasks:
        title = str(_field(task, "Task", "task", "title") or "Task follow-up")
        due = _parse_date(_field(task, "Due", "due"))
        status = str(_field(task, "Status", "status") or "").lower()
        if due and due <= today and status not in {"done", "complete", "completed"}:
            reason = f"task due {due}"
            add_action("Airtable Tasks", title, "High", str(due), reason)

    for event in calendar_events:
        title = str(_field(event, "summary", "title", "name") or "Calendar item")
        start = _parse_date(_field(event, "start", "date"))
        if start == today:
            reason = "calendar item scheduled today"
            add_action("Google Calendar", title, "Medium", str(today), reason)

    for email in important_emails:
        title = str(_field(email, "subject", "Subject") or "Important email")
        reason = str(_field(email, "from", "From", "sender") or "email requires attention")
        add_action("Gmail", title, "Medium", str(today), reason)

    auto_send_queue = [action for action in due_actions if action.send_decision == "auto_send_approved"]
    approval_queue = [action for action in due_actions if action.send_decision == "hold_for_omar"]

    brief_lines = [
        f"Daily AIOS Follow-Up Brief - {today.isoformat()}",
        f"Due actions: {len(due_actions)}",
        f"Auto-send approved: {len(auto_send_queue)}",
        f"Held for Omar: {len(approval_queue)}",
    ]
    for idx, action in enumerate(due_actions[:12], start=1):
        brief_lines.append(f"{idx}. [{action.priority}] {action.title} - {action.reason} - {action.send_decision}")

    return FollowUpRun(
        run_date=today.isoformat(),
        due_actions=due_actions,
        auto_send_queue=auto_send_queue,
        approval_queue=approval_queue,
        ceo_brief="\n".join(brief_lines),
        system_notes=[
            "Uses existing Airtable Leads, Airtable Tasks, Google Calendar, Gmail, and Memory Layer v1 inputs.",
            "Auto-send queue is limited to approved safe reminders/status/document/viewing follow-ups.",
            "Negotiation, price, legal, complaint, sensitive, payment, government, mortgage, visa, banking, and tax items are held for Omar.",
            "Transport send is delegated to the existing CRM/WhatsApp/email channel; this engine produces the approved send queue and log payload.",
        ],
    )


def demo() -> FollowUpRun:
    return run_follow_up_engine(
        leads=[
            {
                "Lead": "AIOS Live Lead - 2BR Yas Island under 2M",
                "Status": "New",
                "Next action": "Send property shortlist follow-up reminder",
                "Next action date": date.today().isoformat(),
            }
        ],
        tasks=[
            {
                "Task": "Follow up buyer requirement for Yas Island",
                "Status": "Active",
                "Due": date.today().isoformat(),
            }
        ],
        calendar_events=[
            {"summary": "Review AIOS production blockers", "start": date.today().isoformat()}
        ],
        important_emails=[
            {"subject": "WhatsApp provider support follow-up", "from": "Provider support"}
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AIOS follow-up engine v1")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    run = demo() if args.demo else run_follow_up_engine()
    print(json.dumps(asdict(run), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
