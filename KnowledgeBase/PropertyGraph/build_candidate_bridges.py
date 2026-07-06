#!/usr/bin/env python3
"""Wire the clean area+building / area+project anchors into the graph as
explicit, clearly-labeled *candidate* bridges.

Portal listing URLs do not carry a unit number, so they can never close to a
single physical unit on their own. But after the resolver corpus was repaired
(:mod:`repair_resolver_fields`), the inventory now exposes trustworthy
``area + building`` and ``area + project`` groups. This pass matches each
public listing URL (using the community / project / building parsed from the
portal) against those inventory groups and, when it lands inside exactly one
group, surfaces the **most likely building/unit set** for human review.

The result is written two ways:

1. ``candidate_bridges.csv`` / ``.json`` / ``CANDIDATE_BRIDGES_REPORT.md`` — a
   dedicated review surface listing every candidate: the listing URL, the
   matched area + entity, the match type, and the candidate unit set.
2. The matched rows in ``listing_bridge_master.csv`` are relabeled
   ``bridge_status = candidate_bridge`` with their ``building`` filled to the
   matched entity, so the graph reflects the anchor.

Candidate bridges are **never** counted as exact matches — the audit maps
``candidate_bridge`` into the "Weak" bucket. This is a review aid, not a
closure. It is deterministic and invents no values: every unit surfaced is a
real inventory unit from the matched group.

Run order: ``build_property_graph`` -> ``sanitize_bridge_master`` ->
``build_candidate_bridges`` -> ``truth_bridge_quality_audit``.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

OUT_DIR = Path(__file__).resolve().parent
KB = OUT_DIR.parent
RESOLVER_DIR = KB / "resolver"
sys.path.append(str(RESOLVER_DIR))

import bridge_data_layer as bridge  # noqa: E402
import listing_similarity_matcher as matcher  # noqa: E402


def normalize_url(url: str) -> str:
    return bridge.normalize_public_url(url).get("normalized_url", "") or bridge.low(url)

INDEX_CSV = RESOLVER_DIR / "unit_resolver_index.csv"
MASTER_CSV = OUT_DIR / "listing_bridge_master.csv"
MASTER_JSON = OUT_DIR / "listing_bridge_master.json"

CANDIDATE_CSV = OUT_DIR / "candidate_bridges.csv"
CANDIDATE_JSON = OUT_DIR / "candidate_bridges.json"
CANDIDATE_REPORT = OUT_DIR / "CANDIDATE_BRIDGES_REPORT.md"

# A group with too many units is not a useful "most likely set" to review.
MAX_UNITS_FOR_CANDIDATE = 60
# Cap the units listed per candidate row so the review file stays readable.
MAX_UNITS_LISTED = 40

CANDIDATE_FIELDS = [
    "listing_url",
    "listing_id",
    "source_platform",
    "match_type",
    "matched_area",
    "matched_entity",
    "candidate_unit_count",
    "candidate_units",
]


def _norm(value: object) -> str:
    return str(value or "").strip()


def build_inventory_groups() -> Tuple[Dict[Tuple[str, str], Set[str]], Dict[Tuple[str, str], Set[str]]]:
    """Return (area_building -> units, area_project -> units) from the repaired inventory."""
    area_building: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    area_project: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    with INDEX_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            area = matcher.canonical_area(row.get("area", ""))
            building = matcher.canonical_building(row.get("building", ""))
            project = matcher.canonical_project(row.get("project", ""))
            unit = matcher.normalize_unit(row.get("unit", ""))
            if not (area and unit):
                continue
            if building:
                area_building[(area, building)].add(unit)
            if project:
                area_project[(area, project)].add(unit)
    return area_building, area_project


def load_url_context() -> Dict[str, Dict[str, str]]:
    """Map normalized listing_url -> parsed {community, project_name, building_name} from bridge_records."""
    context: Dict[str, Dict[str, str]] = {}
    for row in bridge.load_bridge_rows():
        url = bridge.norm(row.get("listing_url", ""))
        if not url:
            continue
        context[normalize_url(url)] = {
            "community": _norm(row.get("community")),
            "project_name": _norm(row.get("project_name")),
            "building_name": _norm(row.get("building_name")),
            "listing_id": _norm(row.get("listing_id")),
            "source_platform": _norm(row.get("source_platform")),
        }
    return context


def match_candidate(
    ctx: Dict[str, str],
    area_building: Dict[Tuple[str, str], Set[str]],
    area_project: Dict[Tuple[str, str], Set[str]],
) -> Optional[Dict[str, object]]:
    area = matcher.canonical_area(ctx.get("community", ""))
    if not area:
        return None
    building = matcher.canonical_building(ctx.get("building_name", ""))
    project = matcher.canonical_project(ctx.get("project_name", ""))
    # Prefer the more specific building anchor, then fall back to project.
    for match_type, entity, groups in (
        ("area_building", building, area_building),
        ("area_project", project, area_project),
    ):
        if entity and (area, entity) in groups:
            units = sorted(groups[(area, entity)])
            if 0 < len(units) <= MAX_UNITS_FOR_CANDIDATE:
                return {
                    "match_type": match_type,
                    "matched_area": area,
                    "matched_entity": entity,
                    "units": units,
                }
    return None


def build() -> Dict[str, object]:
    area_building, area_project = build_inventory_groups()
    url_context = load_url_context()

    with MASTER_CSV.open(newline="", encoding="utf-8") as handle:
        master_rows = list(csv.DictReader(handle))
    fieldnames = list(master_rows[0].keys()) if master_rows else []

    candidates: List[Dict[str, object]] = []
    relabelled = 0
    seen_urls: Set[str] = set()

    for row in master_rows:
        url = bridge.norm(row.get("listing_url", ""))
        # Only rows that still lack a trusted closure are eligible; never touch
        # exact bridges or invent hard identifiers.
        if not url or row.get("bridge_status") == "exact_bridge":
            continue
        if any(_norm(row.get(field)) for field in ("permit_number", "property_number", "plot_number")):
            continue
        ctx = url_context.get(normalize_url(url))
        if not ctx:
            continue
        match = match_candidate(ctx, area_building, area_project)
        if not match:
            continue

        units = [str(u) for u in match["units"]]
        row["building"] = match["matched_entity"].title()
        row["bridge_status"] = "candidate_bridge"
        row["confidence"] = "60"
        row["verified_by"] = "anchor_candidate"
        note = f"candidate_{match['match_type']} | units={len(units)}"
        row["missing_bridge_fields"] = note
        relabelled += 1

        key = normalize_url(url)
        if key not in seen_urls:
            seen_urls.add(key)
            candidates.append(
                {
                    "listing_url": url,
                    "listing_id": ctx.get("listing_id", ""),
                    "source_platform": ctx.get("source_platform", ""),
                    "match_type": match["match_type"],
                    "matched_area": match["matched_area"].title(),
                    "matched_entity": match["matched_entity"].title(),
                    "candidate_unit_count": len(units),
                    "candidate_units": " | ".join(units[:MAX_UNITS_LISTED]),
                }
            )

    # Persist the relabelled master.
    if fieldnames:
        with MASTER_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(master_rows)
        MASTER_JSON.write_text(json.dumps(master_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Write the dedicated review artifacts.
    candidates.sort(key=lambda c: (c["match_type"], c["matched_area"], c["matched_entity"], c["listing_url"]))
    with CANDIDATE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        writer.writerows(candidates)
    CANDIDATE_JSON.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    write_report(candidates, relabelled, len(area_building), len(area_project))

    return {
        "candidate_rows": len(candidates),
        "master_rows_relabelled": relabelled,
        "area_building_groups": len(area_building),
        "area_project_groups": len(area_project),
    }


def write_report(candidates: List[Dict[str, object]], relabelled: int, ab_groups: int, ap_groups: int) -> None:
    by_type: Dict[str, int] = defaultdict(int)
    for c in candidates:
        by_type[str(c["match_type"])] += 1
    lines = [
        "# Candidate Bridges (for review)",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).isoformat()}`",
        "- Candidate bridges anchor a public listing URL to the most likely inventory",
        "  building/unit set via clean `area+building` or `area+project` matches.",
        "- **These are review candidates, not exact matches.** The audit counts them in",
        "  the *Weak* bucket; they are never scored as exact closures.",
        "",
        "## Summary",
        "",
        f"- inventory area+building groups: `{ab_groups}`",
        f"- inventory area+project groups: `{ap_groups}`",
        f"- distinct candidate listing URLs: `{len(candidates)}`",
        f"- master rows relabelled `candidate_bridge`: `{relabelled}`",
        f"- by match type: `{dict(by_type)}`",
        "",
        "## Candidates",
        "",
        "| match_type | area | entity | # units | listing_url |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in candidates:
        lines.append(
            f"| {c['match_type']} | {c['matched_area']} | {c['matched_entity']} "
            f"| {c['candidate_unit_count']} | {c['listing_url']} |"
        )
    if not candidates:
        lines.append("| _none_ | | | | |")
    CANDIDATE_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    summary = build()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
