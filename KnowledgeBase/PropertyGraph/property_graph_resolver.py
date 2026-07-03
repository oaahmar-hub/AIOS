#!/usr/bin/env python3
"""Property graph resolver with deterministic and similarity layers."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import sys

KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
GRAPH_DIR = KB / "PropertyGraph"
RESOLVER_DIR = KB / "resolver"

sys.path.append(str(RESOLVER_DIR))
import final_unit_finder as unit_finder  # noqa: E402
import listing_similarity_matcher as matcher  # noqa: E402

MASTER_CSV = GRAPH_DIR / "canonical_property_master.csv"
BRIDGE_CSV = GRAPH_DIR / "listing_bridge_master.csv"
OBS_CSV = GRAPH_DIR / "source_observations.csv"

ID_KEYS = ["property_number", "permit_number", "plot_number", "land_number", "municipality_number", "dewa_number"]


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def low(value: object) -> str:
    return norm(value).lower()


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", low(value))


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_input(input_text_or_json: object) -> Dict[str, str]:
    base = unit_finder.parse_json_or_text(input_text_or_json)
    return {
        "property_number": norm(base.get("property_number", "")),
        "permit_number": norm(base.get("permit_number", "")),
        "plot_number": norm(base.get("plot_number", "")),
        "land_number": norm(base.get("land_number", "")),
        "municipality_number": norm(base.get("municipality_number", "")),
        "dewa_number": norm(base.get("dewa_number", "")),
        "listing_url": norm(base.get("listing_url", "")),
        "listing_id": norm(base.get("listing_reference", "") or base.get("listing_id", "")),
        "broker_reference": norm(base.get("broker_reference", "")),
        "area": matcher.canonical_area(base.get("area", "")),
        "project": matcher.canonical_project(base.get("project", "")),
        "building": matcher.canonical_building(base.get("building", "")),
        "unit": matcher.normalize_unit(base.get("unit", "")),
        "bedrooms": matcher.canonical_bedrooms(base.get("bedrooms", "")),
        "size": norm(base.get("size", "")),
        "price": norm(base.get("price", "")),
        "input": norm(base.get("input", "")),
    }


class PropertyGraphResolver:
    def __init__(self) -> None:
        self.master = load_csv(MASTER_CSV)
        self.bridge = load_csv(BRIDGE_CSV)
        self.observations = load_csv(OBS_CSV)
        self.master_by_cpid = {row["cpid"]: row for row in self.master}
        self.cpid_by_record_id = {}
        self.by_identifier = {k: defaultdict(set) for k in ID_KEYS}
        self.by_building_unit = defaultdict(set)
        self.by_listing_url = defaultdict(set)
        self.by_listing_id = defaultdict(set)
        self.by_broker_ref = defaultdict(set)
        for row in self.master:
            cpid = row["cpid"]
            for field in ID_KEYS:
                for value in row.get(field + "s", "").split(" | "):
                    if norm(value):
                        self.by_identifier[field][key(value)].add(cpid)
            entity = row.get("canonical_building", "") or row.get("canonical_project", "")
            unit = row.get("canonical_unit", "")
            area = row.get("canonical_area", "")
            if entity and unit:
                self.by_building_unit[f"{key(area)}|{key(entity)}|{key(unit)}"].add(cpid)
        for row in self.bridge:
            cpid = row.get("cpid", "")
            if not cpid:
                continue
            if row.get("listing_url"):
                self.by_listing_url[key(row["listing_url"])].add(cpid)
            if row.get("listing_id"):
                self.by_listing_id[key(row["listing_id"])].add(cpid)
            if row.get("broker_reference"):
                self.by_broker_ref[key(row["broker_reference"])].add(cpid)
        for row in self.observations:
            cpid = row.get("cpid", "")
            if cpid:
                self.cpid_by_record_id[row.get("resolver_record_id", "")] = cpid

    def _existing_cpids(self, cpids) -> List[str]:
        return [cpid for cpid in cpids if cpid in self.master_by_cpid]

    def _cpid_from_unit_finder(self, payload: object) -> List[str]:
        result = unit_finder.resolve_any_clue(payload)
        cpids = []
        for candidate in result.get("top_candidates", []):
            record_id = candidate.get("resolver_record_id", "")
            cpid = self.cpid_by_record_id.get(record_id, "")
            if cpid and cpid in self.master_by_cpid and cpid not in cpids:
                cpids.append(cpid)
        return cpids

    def _format_result(self, cpid: str, match_type: str, why: str, missing: List[str], confidence: int) -> Dict[str, object]:
        row = self.master_by_cpid[cpid]
        related_listings = []
        for bridge_row in self.bridge:
            if bridge_row.get("cpid") == cpid and bridge_row.get("listing_url"):
                related_listings.append(bridge_row["listing_url"])
        return {
            "cpid": cpid,
            "classification": row["verification_state"],
            "resolution_layer": match_type,
            "confidence": confidence,
            "why_matched": why,
            "what_is_missing": missing,
            "owner_contact_available": row["owner_contact_available"],
            "best_property_match": {
                "area": row["canonical_area"],
                "project": row["canonical_project"],
                "building": row["canonical_building"],
                "unit": row["canonical_unit"],
                "developer": row["developer"],
                "last_asking_price": row["last_asking_price"],
            },
            "related_listings": related_listings[:10],
            "next_best_action": "collect broker reference or property/permit/plot/unit bridge" if row["verification_state"] in {"POSSIBLE", "UNRESOLVED"} else "use canonical property record",
        }

    def resolve_deterministic(self, input_text_or_json: object) -> Dict[str, object]:
        query = parse_input(input_text_or_json)
        for field in ID_KEYS:
            value = query.get(field, "")
            if value:
                cpids = self._existing_cpids(sorted(self.by_identifier[field].get(key(value), [])))
                if not cpids:
                    cpids = self._cpid_from_unit_finder({field: value})
                if cpids:
                    return self._format_result(cpids[0], "deterministic_identifier", f"exact {field} match", [], 99)
        if query.get("building") and query.get("unit"):
            area = query.get("area", "")
            sig = f"{key(area)}|{key(query['building'])}|{key(query['unit'])}"
            cpids = self._existing_cpids(sorted(self.by_building_unit.get(sig, [])))
            if not cpids:
                cpids = self._cpid_from_unit_finder({"building": query["building"], "unit": query["unit"], "area": query["area"]})
            if cpids:
                return self._format_result(cpids[0], "deterministic_building_unit", "exact building + unit match", [], 95)
        if query.get("listing_url"):
            cpids = self._existing_cpids(sorted(self.by_listing_url.get(key(query["listing_url"]), [])))
            if cpids:
                row = self.master_by_cpid[cpids[0]]
                missing = []
                if row["verification_state"] not in {"VERIFIED_EXACT", "VERIFIED_STRUCTURAL"}:
                    missing.append("hard property identifier bridge")
                confidence = 90 if not missing else 80
                return self._format_result(cpids[0], "bridge_listing_url", "listing URL found in bridge master", missing, confidence)
            if key(query["listing_url"]) in self.by_listing_url:
                return {
                    "classification": "POSSIBLE",
                    "resolution_layer": "bridge_listing_url",
                    "confidence": 70,
                    "why_matched": "listing URL exists in bridge master but is not linked to a verified canonical property",
                    "what_is_missing": ["hard property identifier bridge", "canonical property confirmation"],
                    "owner_contact_available": "NO",
                    "best_property_match": None,
                    "related_listings": [query["listing_url"]],
                    "next_best_action": "capture broker reference, permit, property number, plot, or building + unit",
                }
        if query.get("listing_id"):
            cpids = self._existing_cpids(sorted(self.by_listing_id.get(key(query["listing_id"]), [])))
            if cpids:
                row = self.master_by_cpid[cpids[0]]
                missing = []
                if row["verification_state"] not in {"VERIFIED_EXACT", "VERIFIED_STRUCTURAL"}:
                    missing.append("hard property identifier bridge")
                confidence = 90 if not missing else 80
                return self._format_result(cpids[0], "bridge_listing_id", "listing ID found in bridge master", missing, confidence)
            if key(query["listing_id"]) in self.by_listing_id:
                return {
                    "classification": "POSSIBLE",
                    "resolution_layer": "bridge_listing_id",
                    "confidence": 70,
                    "why_matched": "listing ID exists in bridge master but is not linked to a verified canonical property",
                    "what_is_missing": ["hard property identifier bridge", "canonical property confirmation"],
                    "owner_contact_available": "NO",
                    "best_property_match": None,
                    "related_listings": [],
                    "next_best_action": "capture broker reference, permit, property number, plot, or building + unit",
                }
        if query.get("broker_reference"):
            cpids = self._existing_cpids(sorted(self.by_broker_ref.get(key(query["broker_reference"]), [])))
            if cpids:
                return self._format_result(cpids[0], "bridge_broker_reference", "broker reference found in bridge master", [], 90)
        return {
            "classification": "UNRESOLVED",
            "resolution_layer": "deterministic",
            "confidence": 0,
            "why_matched": "no deterministic bridge or identifier hit",
            "what_is_missing": ["property number", "permit number", "plot/land number", "building + unit", "listing bridge row"],
            "owner_contact_available": "NO",
            "best_property_match": None,
            "related_listings": [],
            "next_best_action": "fall back to similarity layer",
        }

    def resolve_similarity(self, input_text_or_json: object) -> Dict[str, object]:
        base = unit_finder.resolve_any_clue(input_text_or_json)
        top_candidates = []
        for candidate in base.get("top_candidates", [])[:5]:
            resolver_record_id = candidate.get("resolver_record_id", "")
            cpid = ""
            for obs in self.observations:
                if obs.get("resolver_record_id") == resolver_record_id:
                    cpid = obs.get("cpid", "")
                    break
            row = self.master_by_cpid.get(cpid, {})
            top_candidates.append(
                {
                    "cpid": cpid,
                    "verification_state": row.get("verification_state", ""),
                    "area": row.get("canonical_area", candidate.get("area", "")),
                    "building": row.get("canonical_building", candidate.get("building", "")),
                    "unit": row.get("canonical_unit", candidate.get("unit", "")),
                    "confidence": candidate.get("confidence_score", 0),
                    "why": candidate.get("match_reason", candidate.get("matched_fields", "")),
                }
            )
        return {
            "classification": base.get("classification", "UNRESOLVED"),
            "resolution_layer": "similarity",
            "confidence": base.get("confidence_score", 0),
            "why_matched": base.get("resolution_summary", ""),
            "what_is_missing": base.get("missing_data", []),
            "owner_contact_available": self.master_by_cpid.get(top_candidates[0]["cpid"], {}).get("owner_contact_available", "NO") if top_candidates else "NO",
            "best_property_match": top_candidates[0] if top_candidates else None,
            "related_listings": [],
            "next_best_action": "supply a hard identifier or confirm one candidate" if top_candidates else "collect permit/property/building+unit",
            "candidate_matches": top_candidates,
        }

    def resolve(self, input_text_or_json: object) -> Dict[str, object]:
        deterministic = self.resolve_deterministic(input_text_or_json)
        if deterministic.get("classification") != "UNRESOLVED":
            deterministic["fallback_similarity"] = None
            return deterministic
        similarity = self.resolve_similarity(input_text_or_json)
        return {
            "classification": similarity.get("classification", "UNRESOLVED"),
            "resolution_layer": "similarity_after_deterministic_miss",
            "confidence": similarity.get("confidence", 0),
            "why_matched": similarity.get("why_matched", ""),
            "what_is_missing": similarity.get("what_is_missing", []),
            "owner_contact_available": "NO",
            "best_property_match": similarity.get("best_property_match"),
            "related_listings": similarity.get("related_listings", []),
            "next_best_action": similarity.get("next_best_action", ""),
            "candidate_matches": similarity.get("candidate_matches", []),
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="")
    parser.add_argument("--json", dest="json_input", default="")
    args = parser.parse_args()
    payload: object = args.input
    if args.json_input:
        payload = json.loads(args.json_input)
    resolver = PropertyGraphResolver()
    print(json.dumps(resolver.resolve(payload), ensure_ascii=False, indent=2))
