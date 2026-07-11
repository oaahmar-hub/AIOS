#!/usr/bin/env python3
"""Engineering department: design-compliance audit against verified DCR rules.

Give it a proposed design (plot area, GFA, coverage, floors, setbacks,
parking, pool setback) and it audits every parameter against the ruleset in
``KnowledgeBase/EngineeringRules/dcr_rules.json`` — the same checks a Nakheel
NCPM reviewer runs on the Villa-Townhouse evaluation form.

Honesty contract (same as the whole system):
- Only rulesets verified from real authority documents are on file; an
  unknown community returns ``ruleset_not_on_file`` — never a guess.
- A parameter the caller didn't supply is ``not_checked``, never assumed.
- Every verdict carries the citation of the rule it came from.
- Rules whose numeric limits are not yet verified are surfaced by name in
  ``needs_verification`` so nobody mistakes silence for compliance.

Pure stdlib. ``evaluate`` never raises; errors come back as a JSON verdict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_RUNTIME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _RUNTIME_DIR.parents[2]
RULES_FILE = _REPO_ROOT / "KnowledgeBase" / "EngineeringRules" / "dcr_rules.json"

COMMUNITY_ALIASES = {
    "palm jumeirah": "palm_jumeirah_villa",
    "palm_jumeirah": "palm_jumeirah_villa",
    "palm": "palm_jumeirah_villa",
    "palm_jumeirah_villa": "palm_jumeirah_villa",
}


def _load_rules() -> dict:
    try:
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _floors_above_ground(value: Any) -> Optional[int]:
    """Parse 'G+2', 'B+G+2', '3', 'ground + 2' -> floors above ground."""
    try:
        text = str(value or "").strip().lower()
        if not text:
            return None
        m = re.search(r"g\s*\+\s*(\d+)", text)
        if m:
            return int(m.group(1))
        if text.isdigit():
            return int(text)
        return None
    except Exception:
        return None


def _check(name: str, proposed: Optional[float], limit: float, citation: str,
           mode: str) -> dict:
    if proposed is None:
        return {"rule": name, "status": "not_checked", "reason": "value not provided",
                "limit": limit, "citation": citation}
    ok = proposed <= limit if mode == "max" else proposed >= limit
    return {
        "rule": name,
        "status": "complies" if ok else "breach",
        "proposed": proposed,
        "limit": limit,
        "margin": round((limit - proposed) if mode == "max" else (proposed - limit), 3),
        "citation": citation,
    }


def evaluate(community: str, proposal: dict) -> dict:
    """Audit a proposed design. ``proposal`` keys (all optional, all numeric
    unless noted): plot_area_sqm, gfa_sqm, coverage_sqm, coverage_pct,
    floors (e.g. "B+G+2"), setback_front_m, setback_side_m, setback_rear_m,
    parking_spaces, pool_boundary_setback_m.
    """
    try:
        rules_db = _load_rules()
        key = COMMUNITY_ALIASES.get(str(community or "").strip().lower())
        ruleset = rules_db.get(key or "")
        if not ruleset:
            return {
                "ok": False,
                "verdict": "ruleset_not_on_file",
                "community_requested": community,
                "rulesets_on_file": sorted(rules_db.keys()),
                "note": "No verified DCR ruleset for this community yet. Rules are "
                        "added only from real authority documents - nothing is guessed.",
            }
        rules = ruleset.get("rules", {})
        checks: list = []

        plot_area = _num(proposal.get("plot_area_sqm"))
        gfa = _num(proposal.get("gfa_sqm"))

        # FAR: needs plot area + GFA
        far_rule = rules.get("max_far", {})
        if far_rule:
            far = round(gfa / plot_area, 4) if (gfa and plot_area) else None
            check = _check("max_far", far, float(far_rule["limit"]), far_rule["citation"], "max")
            if far is None:
                check["reason"] = "needs plot_area_sqm and gfa_sqm"
            else:
                check["derived_from"] = {"gfa_sqm": gfa, "plot_area_sqm": plot_area}
            checks.append(check)

        # Coverage: accept % directly or derive from sqm
        cov_rule = rules.get("max_coverage_pct", {})
        if cov_rule:
            cov_pct = _num(proposal.get("coverage_pct"))
            cov_sqm = _num(proposal.get("coverage_sqm"))
            if cov_pct is None and cov_sqm and plot_area:
                cov_pct = round(cov_sqm / plot_area * 100, 2)
            checks.append(_check("max_coverage_pct", cov_pct, float(cov_rule["limit"]),
                                 cov_rule["citation"], "max"))

        # Floors above ground (basement excluded from the count)
        fl_rule = rules.get("max_floors_above_ground", {})
        if fl_rule:
            proposed_fl = _floors_above_ground(proposal.get("floors"))
            limit_fl = _floors_above_ground(fl_rule["limit"])
            check = _check("max_floors_above_ground",
                           float(proposed_fl) if proposed_fl is not None else None,
                           float(limit_fl), fl_rule["citation"], "max")
            check["limit_label"] = fl_rule["limit"]
            if proposed_fl is not None:
                check["proposed_label"] = str(proposal.get("floors"))
            checks.append(check)

        for name, field, mode in (
            ("min_setback_front_m", "setback_front_m", "min"),
            ("min_setback_side_m", "setback_side_m", "min"),
            ("min_setback_rear_m", "setback_rear_m", "min"),
            ("min_parking_spaces", "parking_spaces", "min"),
            ("min_pool_boundary_setback_m", "pool_boundary_setback_m", "min"),
        ):
            rule = rules.get(name, {})
            if rule:
                checks.append(_check(name, _num(proposal.get(field)),
                                     float(rule["limit"]), rule["citation"], mode))

        breaches = [c for c in checks if c["status"] == "breach"]
        unchecked = [c["rule"] for c in checks if c["status"] == "not_checked"]
        verdict = "breach" if breaches else ("complies" if not unchecked else "complies_partially_checked")
        return {
            "ok": True,
            "department": "engineering_design_compliance",
            "ruleset": ruleset.get("ruleset_name"),
            "verified_from": ruleset.get("verified_from", []),
            "verdict": verdict,
            "breaches": len(breaches),
            "checks": checks,
            "not_checked": unchecked,
            "needs_verification": ruleset.get("rules_named_but_value_not_on_file", {}),
            "height_datum": rules.get("height_datum", {}).get("limit"),
            "disclaimer": "Automated pre-check against verified DCR values. Formal "
                          "approval authority remains Nakheel NCPM / Trakhees.",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "verdict": "error", "error": str(exc)}


def health() -> dict:
    db = _load_rules()
    return {
        "component": "design_compliance",
        "rules_file": RULES_FILE.is_file(),
        "rulesets": sorted(db.keys()),
        "status": "ok" if db else "no_rules_on_file",
    }
