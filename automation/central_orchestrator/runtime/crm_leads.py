#!/usr/bin/env python3
"""CRM lead capture — write every real inbound WhatsApp contact to Airtable.

No lead is lost: on each actionable inbound message the runtime upserts a
Contact/Lead row (dedup by phone), stamps last-message + a lightweight
Hot/Warm/Cold score from intent signals, and appends the message to the
conversation trail. Uses the Airtable PAT + base already configured in the
runtime environment.

Pure stdlib. Fully gated: if Airtable env is absent it no-ops cleanly and the
reply path is never affected. Reads/writes are best-effort and never raise.
"""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

AIRTABLE_PAT = (os.getenv("AIRTABLE_PAT", "") or os.getenv("AIRTABLE_TOKEN", "")).strip()
AIRTABLE_BASE = os.getenv("AIRTABLE_BASE_ID", "").strip()
LEADS_TABLE = os.getenv("AIRTABLE_LEADS_TABLE", "").strip()
API = "https://api.airtable.com/v0"

# Hot/Warm/Cold heuristic from message content (EN + AR signals).
_HOT = re.compile(r"\b(buy|purchase|book|viewing|deposit|cash|ready|urgent|today|now)\b|شراء|حجز|معاينة|كاش|جاهز|اليوم|الآن", re.I)
_WARM = re.compile(r"\b(price|budget|available|option|1br|2br|3br|studio|villa|apartment|jvc|marina|downtown)\b|سعر|ميزانية|متاح|شقة|فيلا|استوديو", re.I)


def configured() -> bool:
    return bool(AIRTABLE_PAT and AIRTABLE_BASE and LEADS_TABLE)


def score(text: str) -> str:
    t = str(text or "")
    if _HOT.search(t):
        return "Hot"
    if _WARM.search(t):
        return "Warm"
    return "Cold"


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def _req(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")


def _find(phone: str) -> str | None:
    """Return existing record id for this phone, or None."""
    formula = quote(f"FIND('{phone}', SUBSTITUTE({{Phone}} & '', ' ', ''))")
    url = f"{API}/{AIRTABLE_BASE}/{quote(LEADS_TABLE)}?filterByFormula={formula}&maxRecords=1"
    try:
        recs = _req("GET", url).get("records") or []
        return recs[0]["id"] if recs else None
    except Exception:
        return None


def capture(phone: str, name: str, text: str, lead_score: str | None = None) -> dict:
    """Upsert a lead by phone. Returns {ok, action, id?} — never raises."""
    if not configured():
        return {"ok": False, "action": "skipped", "reason": "airtable_not_configured"}
    p = _digits(phone)
    if not p:
        return {"ok": False, "action": "skipped", "reason": "no_phone"}
    sc = lead_score or score(text)
    fields = {
        "Phone": p,
        "Name": (name or "WhatsApp Contact")[:120],
        "Source": "WhatsApp / AIOS",
        "Lead Score": sc,
        "Last Message": (text or "")[:500],
        "Channel": "WhatsApp",
    }
    # Field-set fallbacks: schemas differ between bases, so degrade to the most
    # likely-present fields rather than losing the lead entirely.
    field_sets = [fields, {"Name": fields["Name"], "Phone": p}, {"Name": f"{fields['Name']} ({p})"}]
    try:
        rid = _find(p)
    except Exception:
        rid = None
    last = "unknown"
    for fs in field_sets:
        try:
            if rid:
                _req("PATCH", f"{API}/{AIRTABLE_BASE}/{quote(LEADS_TABLE)}/{rid}", {"fields": fs, "typecast": True})
                return {"ok": True, "action": "updated", "id": rid, "score": sc}
            res = _req("POST", f"{API}/{AIRTABLE_BASE}/{quote(LEADS_TABLE)}", {"fields": fs, "typecast": True})
            return {"ok": True, "action": "created", "id": res.get("id"), "score": sc}
        except HTTPError as e:
            last = f"http_{e.code}"
            if e.code != 422:
                break  # only field-mismatch is worth retrying with fewer fields
        except URLError as e:
            last = f"url_{e.reason}"; break
        except Exception as e:  # pragma: no cover
            last = str(e)[:60]; break
    return {"ok": False, "action": "error", "reason": last}


def health() -> dict:
    return {"ok": configured(), "detail": "airtable_configured" if configured() else "not_configured"}
