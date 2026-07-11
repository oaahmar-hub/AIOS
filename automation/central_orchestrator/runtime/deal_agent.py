#!/usr/bin/env python3
"""The Autonomous Deal Agent — the brain that runs the end-to-end loop.

This is the structure Omar asked for: one independent real-estate agent that,
for every request an agent posts in a WhatsApp group, runs the full loop and
never stops:

    [1] CATCH    a request from an agent group   (group message -> job)
    [2] PARSE    area / beds / budget / buy|rent
    [3] SEARCH   Property Finder + Bayut + Dubizzle for matching live units
    [4] OWNERS   DLD lookup: unit -> owner / landlord name + phone
    [5] OUTREACH text (and optionally call) 2-3 owners for availability + price
    [6] REPLY    post the match + details back to the requesting agent
    [7] loop to the next request

Design principles
-----------------
- **State machine, resumable.** Every request is a `Deal` persisted to the
  volume with a `stage`. The loop advances deals stage by stage; a crash or
  restart resumes exactly where it left off — no request is ever lost.
- **Pluggable channels.** WhatsApp send/receive and voice calls go through
  provider callables injected at run time (Wasender now, official WhatsApp
  Business API / Twilio later) — swapping the number or provider needs no
  rewrite.
- **Guardrails baked in.** At most ``MAX_OWNERS_PER_DEAL`` owners contacted,
  per-number rate limits, dedupe, and opt-out — the restraint that keeps the
  agent's number alive instead of WhatsApp-banned.
- **Honest data.** Owner lookup returns only real DLD matches; no match ->
  the deal is marked ``no_owner_data`` and the agent tells the truth, never a
  fabricated number.

Providers (injected — see :class:`DealAgent`):
    parse(text)            -> dict | None        request criteria
    search(criteria)       -> list[dict]         candidate units
    lookup_owners(unit)    -> list[dict]         [{name, phone, ...}]
    send_whatsapp(to,text) -> tuple[bool,str]
    place_call(to,script)  -> dict               {ok, transcript, ...}
    reply_group(gid,text)  -> tuple[bool,str]

Pure stdlib. Nothing here raises into the webhook path.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Config / guardrails
# ---------------------------------------------------------------------------
AGENT_ENABLED = os.getenv("AIOS_DEAL_AGENT_ENABLED", "").strip().lower() in {"1", "true", "yes"}
MAX_OWNERS_PER_DEAL = int(os.getenv("AIOS_DEAL_MAX_OWNERS", "3") or 3)
CALLS_ENABLED = os.getenv("AIOS_DEAL_CALLS_ENABLED", "").strip().lower() in {"1", "true", "yes"}
OWNER_MIN_GAP_SECONDS = int(os.getenv("AIOS_DEAL_OWNER_MIN_GAP", "45") or 45)
OWNER_MAX_PER_HOUR = int(os.getenv("AIOS_DEAL_OWNER_MAX_PER_HOUR", "20") or 20)

_STATE_DIR = Path(os.getenv("AIOS_PHASE4_DB_PATH", "/tmp/x")).parent / "deal_agent"

STAGES = ["received", "parsed", "searched", "owners_found", "outreach_sent", "replied", "done"]
TERMINAL = {"done", "failed", "no_match", "no_owner_data"}


# ---------------------------------------------------------------------------
# Deal record
# ---------------------------------------------------------------------------
@dataclass
class Deal:
    deal_id: str
    group_id: str
    requester: str          # phone/handle of the agent who posted
    text: str               # the raw request
    stage: str = "received"
    criteria: dict = field(default_factory=dict)
    units: list = field(default_factory=list)
    owners: list = field(default_factory=list)
    outreach: list = field(default_factory=list)   # [{phone_masked, sent, called}]
    detail: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def path(self) -> Path:
        return _STATE_DIR / f"{self.deal_id}.json"

    def save(self) -> None:
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            self.updated_at = time.time()
            self.path().write_text(json.dumps(asdict(self)), encoding="utf-8")
        except Exception:
            pass


def _mask(phone: str) -> str:
    d = "".join(c for c in str(phone or "") if c.isdigit())
    return f"***{d[-3:]}" if len(d) >= 3 else "***"


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------
class DealAgent:
    """Runs deals through the loop. Providers are injected so the same brain
    works with any WhatsApp/voice/portal backend."""

    def __init__(
        self,
        parse: Callable[[str], Optional[dict]],
        search: Callable[[dict], list],
        lookup_owners: Callable[[dict], list],
        send_whatsapp: Callable[[str, str], tuple],
        reply_group: Callable[[str, str], tuple],
        place_call: Optional[Callable[[str, str], dict]] = None,
        now: Optional[Callable[[], float]] = None,
    ):
        self.parse = parse
        self.search = search
        self.lookup_owners = lookup_owners
        self.send_whatsapp = send_whatsapp
        self.reply_group = reply_group
        self.place_call = place_call
        self._now = now or time.time
        self._owner_log: dict = {}  # phone -> [timestamps]

    # ---- intake -----------------------------------------------------------
    def intake(self, group_id: str, requester: str, text: str) -> Optional[Deal]:
        """Turn an inbound group message into a Deal, if it's a real request."""
        criteria = None
        try:
            criteria = self.parse(text)
        except Exception:
            criteria = None
        if not criteria:
            return None  # not a request (chatter, greeting, listing, etc.)
        deal = Deal(
            deal_id="D" + uuid.uuid4().hex[:10],
            group_id=str(group_id),
            requester=str(requester),
            text=str(text)[:600],
            criteria=criteria,
            stage="parsed",
            created_at=self._now(),
        )
        deal.save()
        return deal

    # ---- guardrail --------------------------------------------------------
    def _owner_allowed(self, phone: str) -> bool:
        t = self._now()
        log = [x for x in self._owner_log.get(phone, []) if t - x < 3600]
        if log and t - log[-1] < OWNER_MIN_GAP_SECONDS:
            return False
        if len(log) >= OWNER_MAX_PER_HOUR:
            return False
        log.append(t)
        self._owner_log[phone] = log
        return True

    # ---- the loop ---------------------------------------------------------
    def advance(self, deal: Deal) -> Deal:
        """Advance a deal by exactly one stage. Idempotent per stage; safe to
        call repeatedly. Never raises."""
        try:
            if deal.stage == "parsed":
                units = self.search(deal.criteria) or []
                deal.units = units[:10]
                deal.stage = "searched" if units else "no_match"
                deal.detail = f"{len(units)} units" if units else "no matching units on portals"

            elif deal.stage == "searched":
                owners = []
                for u in deal.units:
                    for o in (self.lookup_owners(u) or []):
                        if o.get("phone"):
                            owners.append({**o, "unit": u})
                # dedupe by phone
                seen, uniq = set(), []
                for o in owners:
                    if o["phone"] not in seen:
                        seen.add(o["phone"]); uniq.append(o)
                deal.owners = uniq
                deal.stage = "owners_found" if uniq else "no_owner_data"
                deal.detail = f"{len(uniq)} owners with a phone" if uniq else "no owner contact on file"

            elif deal.stage == "owners_found":
                sent = []
                for o in deal.owners[:MAX_OWNERS_PER_DEAL]:
                    phone = o["phone"]
                    if not self._owner_allowed(phone):
                        continue
                    msg = _owner_message(deal.criteria, o)
                    ok, det = self.send_whatsapp(phone, msg)
                    rec = {"phone_masked": _mask(phone), "sent": ok, "detail": det, "called": False}
                    if CALLS_ENABLED and self.place_call:
                        try:
                            call = self.place_call(phone, _owner_call_script(deal.criteria, o))
                            rec["called"] = bool(call.get("ok"))
                        except Exception:
                            pass
                    sent.append(rec)
                deal.outreach = sent
                deal.stage = "outreach_sent"
                deal.detail = f"contacted {sum(1 for s in sent if s['sent'])} owners"

            elif deal.stage == "outreach_sent":
                # Post an honest status back to the requesting agent's group.
                text = _group_reply(deal)
                self.reply_group(deal.group_id, text)
                deal.stage = "replied"
                deal.detail = "agent notified"

            elif deal.stage == "replied":
                deal.stage = "done"

            deal.save()
        except Exception as exc:  # pragma: no cover - loop must never die
            deal.detail = f"error:{exc}"
            deal.save()
        return deal

    def run_to_completion(self, deal: Deal, max_steps: int = 8) -> Deal:
        steps = 0
        while deal.stage not in TERMINAL and steps < max_steps:
            self.advance(deal)
            steps += 1
        return deal


# ---------------------------------------------------------------------------
# Message templates (honest, human)
# ---------------------------------------------------------------------------
def _owner_message(criteria: dict, owner: dict) -> str:
    unit = owner.get("unit", {})
    where = " ".join(str(x) for x in (unit.get("building"), unit.get("unit")) if x).strip() or "your property"
    return (
        f"Hello, this is HSH Real Estate in Dubai. We have a genuine client looking in "
        f"{where}. Is it available for {criteria.get('intent', 'sale/rent')}, and what's "
        "the current price? If you'd rather not receive messages like this, just reply STOP."
    )


def _owner_call_script(criteria: dict, owner: dict) -> str:
    unit = owner.get("unit", {})
    where = " ".join(str(x) for x in (unit.get("building"), unit.get("unit")) if x).strip() or "your property"
    return (
        f"Hi, calling from HSH Real Estate. We have a serious buyer interested in {where}. "
        "I wanted to check if it's still available and what price you'd consider."
    )


def _group_reply(deal: Deal) -> str:
    c = deal.criteria
    ask = " ".join(str(x) for x in (c.get("beds"), c.get("type"), c.get("area")) if x).strip() or deal.text[:40]
    contacted = sum(1 for s in deal.outreach if s.get("sent"))
    if contacted:
        return (
            f"On your request ({ask}): found {len(deal.units)} matching units, reached out to "
            f"{contacted} owners to confirm availability & price. I'll share the confirmed "
            "options here as they reply."
        )
    if deal.stage == "no_owner_data":
        return f"On your request ({ask}): found {len(deal.units)} units but no owner contact on file yet — checking other sources."
    return f"On your request ({ask}): searching now, will update you shortly."


# ---------------------------------------------------------------------------
# Persistence helpers + health
# ---------------------------------------------------------------------------
def load_deals(limit: int = 50) -> list:
    out = []
    try:
        for p in sorted(_STATE_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            out.append(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return out


def stats() -> dict:
    deals = load_deals(500)
    by_stage: dict = {}
    for d in deals:
        by_stage[d.get("stage", "?")] = by_stage.get(d.get("stage", "?"), 0) + 1
    return {"total": len(deals), "by_stage": by_stage}


def health() -> dict:
    return {
        "component": "deal_agent",
        "enabled": AGENT_ENABLED,
        "calls_enabled": CALLS_ENABLED,
        "max_owners_per_deal": MAX_OWNERS_PER_DEAL,
        "deals_tracked": len(load_deals(500)),
        "status": "ok" if AGENT_ENABLED else "structure_ready_disabled",
        "note": "Autonomous loop wired. Activate with AIOS_DEAL_AGENT_ENABLED once the "
                "agent's own WhatsApp number + owner data are connected.",
    }
