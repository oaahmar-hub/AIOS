#!/usr/bin/env python3
"""Modular AIOS Bridge Engine.

This is a bridge orchestration layer only. It does not change Unit Finder
matching/scoring/resolver code. Every strategy reports its own availability and
evidence instead of fabricating a match when source data is missing.
"""

from __future__ import annotations

import csv
import json
import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
RESOLVER = KB / "resolver"
OUT_DIR = KB / "BridgeEngine"
INDEX_CSV = RESOLVER / "unit_resolver_index.csv"
BRIDGE_INVESTIGATION_SUMMARY = KB / "BridgeInvestigation" / "bridge_data_investigation_summary.json"
BRIDGE_SOURCE_INVENTORY = KB / "BridgeInvestigation" / "bridge_source_inventory.csv"
OUT_TESTS = OUT_DIR / "bridge_engine_strategy_tests.csv"
OUT_REPORT = OUT_DIR / "BRIDGE_ENGINE_ARCHITECTURE_REPORT.md"
OUT_MANIFEST = OUT_DIR / "bridge_engine_manifest.json"

import sys

sys.path.append(str(RESOLVER))
import bridge_data_layer as bridge_layer  # noqa: E402

URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)[^\s\"'<>)\]]+", re.I)
LISTING_REF_RE = re.compile(r"\b(?:listing(?:\s+id|\s+reference|\s+ref)?|listing_id|listing_ref)\s*[:#-]?\s*([A-Za-z0-9_-]{5,80})", re.I)
BROKER_REF_RE = re.compile(r"\b(?:broker\s+reference|broker\s+ref|broker_ref|brn|orn)\s*[:#-]?\s*([A-Za-z0-9_-]{4,80})", re.I)
ID_PATTERNS = {
    "permit": re.compile(r"\b(?:permit|rera|trakheesi|dld permit)\s*(?:no\.?|number|#|:)?\s*([A-Za-z0-9/-]{4,40})", re.I),
    "property_number": re.compile(r"\b(?:property number|property no|property id|property)\s*(?:no\.?|number|#|:)?\s*([A-Za-z0-9/-]{3,40})", re.I),
    "plot_land": re.compile(r"\b(?:plot|plot no|plot number|land|land no|land number)\s*(?:no\.?|number|#|:)?\s*([A-Za-z0-9/-]{2,40})", re.I),
}

OUTCOMES = ("EXACT_MATCH", "HIGH_CONFIDENCE", "CANDIDATE_MATCHES", "NO_MATCH", "WAITING_FOR_DATA")
OUTCOME_PRIORITY = {
    "EXACT_MATCH": 5,
    "HIGH_CONFIDENCE": 4,
    "CANDIDATE_MATCHES": 3,
    "WAITING_FOR_DATA": 2,
    "NO_MATCH": 1,
}


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(value).lower())


def clean_url(value: str) -> str:
    value = norm(value).rstrip(".,;")
    if value and not value.lower().startswith(("http://", "https://")):
        value = "https://" + value
    return value


def listing_id_from_url(url: str) -> str:
    tail = re.sub(r"\.(?:html?|htm)$", "", clean_url(url).split("?")[0].rstrip("/").split("/")[-1], flags=re.I)
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", tail) if token]
    for token in reversed(tokens):
        if token.isdigit() and len(token) >= 5:
            return token
        if len(token) >= 6 and any(ch.isdigit() for ch in token):
            return token
    return ""


def parse_query(input_text_or_json: object) -> Dict[str, str]:
    search_text = ""
    if isinstance(input_text_or_json, dict):
        q = {str(k): norm(v) for k, v in input_text_or_json.items()}
        raw = json.dumps(q, ensure_ascii=False)
        search_text = " ".join(
            norm(v)
            for k, v in q.items()
            if k not in {"url", "listing_url"} and norm(v)
        )
    else:
        raw = norm(input_text_or_json)
        try:
            parsed = json.loads(raw) if raw.startswith("{") else {}
            if isinstance(parsed, dict):
                q = {str(k): norm(v) for k, v in parsed.items()}
                search_text = " ".join(
                    norm(v)
                    for k, v in q.items()
                    if k not in {"url", "listing_url"} and norm(v)
                )
            else:
                q = {}
        except Exception:
            q = {}
    if not search_text:
        search_text = re.sub(URL_RE, " ", raw)
    q["raw_input"] = raw

    url_match = URL_RE.search(raw)
    if url_match and not q.get("url"):
        q["url"] = clean_url(url_match.group(0))
    if q.get("url") and not q.get("listing_reference"):
        lid = listing_id_from_url(q["url"])
        if lid:
            q["listing_reference"] = lid
    for name, regex in [("listing_reference", LISTING_REF_RE), ("broker_reference", BROKER_REF_RE)]:
        if not q.get(name):
            m = regex.search(search_text)
            if m:
                q[name] = norm(m.group(1))
    for name, regex in ID_PATTERNS.items():
        if not q.get(name):
            m = regex.search(search_text)
            if m:
                q[name] = norm(m.group(1))
    return q


@dataclass
class BridgeCandidate:
    resolver_record_id: str = ""
    source_file: str = ""
    source_sheet: str = ""
    row_number: str = ""
    listing_url: str = ""
    listing_id: str = ""
    area: str = ""
    project: str = ""
    building: str = ""
    unit: str = ""
    permit_number: str = ""
    property_number: str = ""
    plot_number: str = ""
    land_number: str = ""
    confidence: int = 0
    evidence: str = ""
    owner_contact_available: str = "NO"


@dataclass
class BridgeResult:
    strategy: str
    availability: str
    outcome: str
    confidence: int
    evidence: str
    candidates: List[BridgeCandidate] = field(default_factory=list)
    required_future_data: str = ""


class BridgeContext:
    def __init__(self, index_path: Path = INDEX_CSV) -> None:
        self.index_path = index_path
        self.records = self._load_records(index_path)
        self.bridge_rows = bridge_layer.load_bridge_rows()
        self.by_url = defaultdict(list)
        self.by_listing_ref = defaultdict(list)
        self.by_broker_ref = defaultdict(list)
        self.by_permit = defaultdict(list)
        self.by_property_number = defaultdict(list)
        self.by_plot_land = defaultdict(list)
        self.unit_records = []
        for record in self.records:
            if record.get("unit"):
                self.unit_records.append(record)
            if record.get("listing_url"):
                self.by_url[key(clean_url(record["listing_url"]))].append(record)
            for url_field in ("property_finder_url", "bayut_url", "dubizzle_url"):
                if record.get(url_field):
                    self.by_url[key(clean_url(record[url_field]))].append(record)
            if record.get("listing_id"):
                self.by_listing_ref[key(record["listing_id"])].append(record)
            if record.get("permit_number"):
                self.by_permit[key(record["permit_number"])].append(record)
            if record.get("property_number"):
                self.by_property_number[key(record["property_number"])].append(record)
            if record.get("plot_number"):
                self.by_plot_land[key(record["plot_number"])].append(record)
            if record.get("land_number"):
                self.by_plot_land[key(record["land_number"])].append(record)
        for record in self.bridge_rows:
            if record.get("unit_number"):
                self.unit_records.append(record)
            if record.get("listing_url"):
                self.by_url[key(clean_url(record["listing_url"]))].append(record)
            if record.get("listing_id"):
                self.by_listing_ref[key(record["listing_id"])].append(record)
            if record.get("broker_reference"):
                self.by_broker_ref[key(record["broker_reference"])].append(record)
            if record.get("permit_number"):
                self.by_permit[key(record["permit_number"])].append(record)
            if record.get("property_number"):
                self.by_property_number[key(record["property_number"])].append(record)
            if record.get("plot_number"):
                self.by_plot_land[key(record["plot_number"])].append(record)
        self.bridge_summary = self._load_json(BRIDGE_INVESTIGATION_SUMMARY)
        self.source_inventory = self._load_source_inventory(BRIDGE_SOURCE_INVENTORY)

    def _load_records(self, path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _load_json(self, path: Path) -> Dict[str, object]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_source_inventory(self, path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def to_candidate(self, record: Dict[str, str], confidence: int, evidence: str) -> BridgeCandidate:
        return BridgeCandidate(
            resolver_record_id=record.get("resolver_record_id", "") or record.get("canonical_property_id", ""),
            source_file=record.get("source_file", ""),
            source_sheet=record.get("source_sheet", ""),
            row_number=record.get("row_number", ""),
            listing_url=record.get("listing_url") or record.get("property_finder_url") or record.get("bayut_url") or record.get("dubizzle_url") or "",
            listing_id=record.get("listing_id", ""),
            area=record.get("area", "") or record.get("community", ""),
            project=record.get("project", "") or record.get("project_name", ""),
            building=record.get("building", "") or record.get("building_name", ""),
            unit=record.get("unit", "") or record.get("unit_number", ""),
            permit_number=record.get("permit_number", ""),
            property_number=record.get("property_number", ""),
            plot_number=record.get("plot_number", ""),
            land_number=record.get("land_number", ""),
            confidence=confidence,
            evidence=evidence,
            owner_contact_available="YES" if norm(record.get("owner_contact_available")).upper() == "YES" else "NO",
        )


class BridgeStrategy(ABC):
    name = "base"
    future_data = ""

    def __init__(self, context: BridgeContext) -> None:
        self.context = context

    @abstractmethod
    def resolve(self, query: Dict[str, str]) -> BridgeResult:
        raise NotImplementedError

    def waiting(self, evidence: str = "") -> BridgeResult:
        return BridgeResult(
            strategy=self.name,
            availability="WAITING_FOR_DATA",
            outcome="WAITING_FOR_DATA",
            confidence=0,
            evidence=evidence or "Required bridge source is not available in current datasets.",
            required_future_data=self.future_data,
        )

    def no_match(self, evidence: str) -> BridgeResult:
        return BridgeResult(self.name, "AVAILABLE", "NO_MATCH", 0, evidence, [], self.future_data)


class DirectURLToUnitBridge(BridgeStrategy):
    name = "direct_url_to_unit"
    future_data = "Listing URL row containing a real unit number or linked hard identifier that resolves to a unit."

    def resolve(self, query: Dict[str, str]) -> BridgeResult:
        url = query.get("url", "")
        if not url:
            return self.no_match("No URL supplied.")
        records = self.context.by_url.get(key(clean_url(url)), [])
        unit_records = [r for r in records if r.get("unit")]
        if unit_records:
            candidates = [self.context.to_candidate(r, 100, "same row contains listing URL and unit") for r in unit_records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "EXACT_MATCH", 100, "Direct URL row contains unit.", candidates, self.future_data)
        if records:
            candidates = [self.context.to_candidate(r, 70, "URL exists but no unit in matching row") for r in records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "CANDIDATE_MATCHES", 70, "URL exists in corpus but no unit bridge is present.", candidates, self.future_data)
        return self.no_match("URL not found in current bridge indexes.")


class ListingReferenceToUnitBridge(BridgeStrategy):
    name = "listing_reference_to_unit"
    future_data = "Listing ID/reference export linked to unit number or hard property identifier."

    def resolve(self, query: Dict[str, str]) -> BridgeResult:
        ref = query.get("listing_reference", "")
        if not ref:
            return self.no_match("No listing reference supplied.")
        records = self.context.by_listing_ref.get(key(ref), [])
        unit_records = [r for r in records if r.get("unit")]
        if unit_records:
            candidates = [self.context.to_candidate(r, 100, "listing reference row contains unit") for r in unit_records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "EXACT_MATCH", 100, "Listing reference resolves directly to unit.", candidates, self.future_data)
        if records:
            candidates = [self.context.to_candidate(r, 65, "listing reference exists but no unit") for r in records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "CANDIDATE_MATCHES", 65, "Listing reference exists but lacks unit bridge.", candidates, self.future_data)
        return self.waiting("No listing reference to unit dataset is available for this reference.")


class BrokerReferenceToUnitBridge(BridgeStrategy):
    name = "broker_reference_to_unit"
    future_data = "Broker reference export linked to unit number or hard property identifier."

    def resolve(self, query: Dict[str, str]) -> BridgeResult:
        ref = query.get("broker_reference", "")
        if not ref:
            return self.no_match("No broker reference supplied.")
        records = self.context.by_broker_ref.get(key(ref), [])
        if not self.context.by_broker_ref:
            return self.waiting("Current resolver index has no structured broker reference field.")
        unit_records = [r for r in records if r.get("unit")]
        if unit_records:
            candidates = [self.context.to_candidate(r, 100, "broker reference row contains unit") for r in unit_records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "EXACT_MATCH", 100, "Broker reference resolves directly to unit.", candidates, self.future_data)
        if records:
            candidates = [self.context.to_candidate(r, 65, "broker reference exists but no unit") for r in records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "CANDIDATE_MATCHES", 65, "Broker reference exists but lacks unit bridge.", candidates, self.future_data)
        return self.no_match("Broker reference not found in current structured bridge data.")


class IdentifierToUnitBridge(BridgeStrategy):
    index_attr = ""
    query_key = ""
    name = "identifier_to_unit"
    future_data = "Identifier export linked to unit number."

    def resolve(self, query: Dict[str, str]) -> BridgeResult:
        value = query.get(self.query_key, "")
        if not value:
            return self.no_match(f"No {self.query_key} supplied.")
        records = getattr(self.context, self.index_attr).get(key(value), [])
        unit_records = [r for r in records if r.get("unit")]
        if unit_records:
            candidates = [self.context.to_candidate(r, 100, f"{self.query_key} row contains unit") for r in unit_records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "EXACT_MATCH", 100, f"{self.query_key} resolves directly to unit.", candidates, self.future_data)
        if records:
            candidates = [self.context.to_candidate(r, 75, f"{self.query_key} exists but no unit") for r in records[:5]]
            return BridgeResult(self.name, "AVAILABLE", "HIGH_CONFIDENCE", 75, f"{self.query_key} exists in corpus but no unit is attached.", candidates, self.future_data)
        return self.no_match(f"{self.query_key} not found in current resolver data.")


class PermitToUnitBridge(IdentifierToUnitBridge):
    name = "permit_to_unit"
    index_attr = "by_permit"
    query_key = "permit"
    future_data = "Permit dataset linked to unit-bearing property rows."


class PropertyNumberToUnitBridge(IdentifierToUnitBridge):
    name = "property_number_to_unit"
    index_attr = "by_property_number"
    query_key = "property_number"
    future_data = "Property number records linked to unit numbers."


class PlotLandToUnitBridge(IdentifierToUnitBridge):
    name = "plot_land_to_unit"
    index_attr = "by_plot_land"
    query_key = "plot_land"
    future_data = "Plot/land records linked to unit-bearing inventory rows."


class SimilarityCandidateBridge(BridgeStrategy):
    name = "ai_similarity_candidate_matching"
    future_data = "No mandatory new data. Higher quality area/building/size/price text improves ranking."

    def resolve(self, query: Dict[str, str]) -> BridgeResult:
        area = key(query.get("area", ""))
        building = key(query.get("building", "") or query.get("project", ""))
        bedrooms = key(query.get("bedrooms", ""))
        if not (area or building or bedrooms):
            return self.no_match("No similarity clues supplied.")
        scored: List[Tuple[int, Dict[str, str], List[str]]] = []
        for record in self.context.records:
            score = 0
            reasons = []
            if area and area == key(record.get("area", "")):
                score += 30
                reasons.append("area")
            if building and building in key(" ".join([record.get("building", ""), record.get("project", "")])):
                score += 35
                reasons.append("building_or_project")
            if bedrooms and bedrooms == key(record.get("bedrooms", "")):
                score += 15
                reasons.append("bedrooms")
            if query.get("unit") and key(query["unit"]) == key(record.get("unit", "")):
                score += 20
                reasons.append("unit")
            if score > 0:
                scored.append((score, record, reasons))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return self.no_match("No candidates found from similarity clues.")
        candidates = [self.context.to_candidate(r, min(score, 90), "matched " + ",".join(reasons)) for score, r, reasons in scored[:5]]
        top_score = scored[0][0]
        if top_score >= 80:
            outcome = "HIGH_CONFIDENCE"
            confidence = min(top_score, 90)
        else:
            outcome = "CANDIDATE_MATCHES"
            confidence = min(top_score, 79)
        return BridgeResult(self.name, "AVAILABLE", outcome, confidence, "Similarity bridge returns candidates only, not exact identity.", candidates, self.future_data)


class BridgeEngine:
    def __init__(self, context: BridgeContext | None = None) -> None:
        self.context = context or BridgeContext()
        self.strategies: List[BridgeStrategy] = [
            DirectURLToUnitBridge(self.context),
            ListingReferenceToUnitBridge(self.context),
            BrokerReferenceToUnitBridge(self.context),
            PermitToUnitBridge(self.context),
            PropertyNumberToUnitBridge(self.context),
            PlotLandToUnitBridge(self.context),
            SimilarityCandidateBridge(self.context),
        ]

    def resolve(self, input_text_or_json: object) -> Dict[str, object]:
        query = parse_query(input_text_or_json)
        results = [strategy.resolve(query) for strategy in self.strategies]
        ranked = sorted(results, key=lambda r: (OUTCOME_PRIORITY.get(r.outcome, 0), r.confidence), reverse=True)
        return {
            "input": input_text_or_json,
            "parsed_query": query,
            "best_outcome": ranked[0].outcome if ranked else "NO_MATCH",
            "best_strategy": ranked[0].strategy if ranked else "",
            "results": [asdict(r) for r in results],
        }

    def availability_manifest(self) -> Dict[str, object]:
        counts = Counter()
        for record in self.context.records:
            counts["records"] += 1
            counts["unit_records"] += int(bool(record.get("unit")))
            counts["url_records"] += int(bool(record.get("listing_url") or record.get("property_finder_url") or record.get("bayut_url") or record.get("dubizzle_url")))
            counts["listing_reference_records"] += int(bool(record.get("listing_id")))
            counts["permit_records"] += int(bool(record.get("permit_number")))
            counts["property_number_records"] += int(bool(record.get("property_number")))
            counts["plot_land_records"] += int(bool(record.get("plot_number") or record.get("land_number")))
        bridge_summary = dict(self.context.bridge_summary)
        bridge_summary["normalized_decision"] = "freeze_deterministic_url_to_unit_bridge_only"
        bridge_summary["unit_finder_state"] = "extensible_through_modular_bridge_engine"
        if bridge_summary.get("recommendation") == "permanently_freeze_url_mapping_until_bridge_data":
            bridge_summary["superseded_recommendation"] = bridge_summary.pop("recommendation")
        return {
            "engine": "AIOS Modular Bridge Engine",
            "strategies": [s.name for s in self.strategies],
            "current_data_counts": dict(counts),
            "bridge_investigation_summary": bridge_summary,
        }


def pick_sample_tests(context: BridgeContext) -> List[Dict[str, object]]:
    tests = []
    url_record = next((r for r in context.records if r.get("listing_url") or r.get("property_finder_url") or r.get("bayut_url") or r.get("dubizzle_url")), None)
    if url_record:
        tests.append({"test_name": "direct_url_current_data", "input": {"url": url_record.get("listing_url") or url_record.get("property_finder_url") or url_record.get("bayut_url") or url_record.get("dubizzle_url")}})
        if url_record.get("listing_id"):
            tests.append({"test_name": "listing_reference_current_data", "input": {"listing_reference": url_record["listing_id"]}})
    prop_unit = next((r for r in context.records if r.get("property_number") and r.get("unit")), None)
    if prop_unit:
        tests.append({"test_name": "property_number_to_unit_current_data", "input": {"property_number": prop_unit["property_number"]}})
    permit = next((r for r in context.records if r.get("permit_number")), None)
    if permit:
        tests.append({"test_name": "permit_current_data", "input": {"permit": permit["permit_number"]}})
    plot_land = next((r for r in context.records if (r.get("plot_number") or r.get("land_number"))), None)
    if plot_land:
        tests.append({"test_name": "plot_land_current_data", "input": {"plot_land": plot_land.get("plot_number") or plot_land.get("land_number")}})
    tests.append({"test_name": "broker_reference_waiting_for_data", "input": {"broker_reference": "SAMPLE-BROKER-REF"}})
    tests.append({"test_name": "similarity_candidate_current_data", "input": {"area": "JVC", "building": "Binghatti", "bedrooms": "1"}})
    return tests


def run_tests(engine: BridgeEngine) -> List[Dict[str, object]]:
    rows = []
    for test in pick_sample_tests(engine.context):
        result = engine.resolve(test["input"])
        for strategy_result in result["results"]:
            rows.append(
                {
                    "test_name": test["test_name"],
                    "input": json.dumps(test["input"], ensure_ascii=False),
                    "strategy": strategy_result["strategy"],
                    "availability": strategy_result["availability"],
                    "outcome": strategy_result["outcome"],
                    "confidence": strategy_result["confidence"],
                    "candidate_count": len(strategy_result.get("candidates", [])),
                    "evidence": strategy_result["evidence"],
                    "required_future_data": strategy_result["required_future_data"],
                }
            )
    with OUT_TESTS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_report(engine: BridgeEngine, test_rows: List[Dict[str, object]]) -> None:
    manifest = engine.availability_manifest()
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    outcomes_by_strategy = defaultdict(Counter)
    for row in test_rows:
        outcomes_by_strategy[row["strategy"]][row["outcome"]] += 1

    summary = engine.context.bridge_summary
    lines = [
        "# AIOS Bridge Engine Architecture Report",
        "",
        "## Scope",
        "",
        "This is a modular Bridge Engine framework. It does not modify Unit Finder scoring, matching, resolver logic, or production WhatsApp logic.",
        "",
        "The current deterministic URL-to-unit bridge remains frozen because current data does not provide exact URL-to-unit coverage. The Unit Finder product remains extensible through bridge strategies marked AVAILABLE or WAITING_FOR_DATA.",
        "",
        "## Current Bridge Investigation Evidence",
        "",
        f"- records_scanned: {summary.get('records_scanned', 0)}",
        f"- unique_listing_urls_found: {summary.get('unique_listing_urls_found', 0)}",
        f"- direct_url_plus_unit_rows: {summary.get('direct_url_plus_unit_rows', 0)}",
        f"- direct_exact_url_to_unit_rows: {summary.get('direct_exact_url_to_unit_rows', 0)}",
        f"- combined_exact_url_count_supported: {summary.get('combined_exact_url_count_supported', 0)}",
        "",
        "## Supported Bridges",
        "",
        "| Bridge | Current Availability | Current Evidence | Result Semantics | Future Data Required |",
        "|---|---|---|---|---|",
    ]

    strategy_descriptions = {
        "direct_url_to_unit": ("WAITING_FOR_DATA", "0 direct URL+unit rows", "EXACT only when same row has listing URL and unit"),
        "listing_reference_to_unit": ("WAITING_FOR_DATA", "Listing IDs exist, but no reliable listing ref to unit dataset", "EXACT only when listing reference row contains unit"),
        "broker_reference_to_unit": ("WAITING_FOR_DATA", "No structured broker reference index in current resolver data", "EXACT only when broker reference row contains unit"),
        "permit_to_unit": ("PARTIAL_AVAILABLE", "Permit records exist, current unit-bearing permit rows are 0", "HIGH_CONFIDENCE for identifier exists; EXACT only if unit attached"),
        "property_number_to_unit": ("AVAILABLE", "Property number records include unit-bearing rows", "EXACT when property number row contains unit"),
        "plot_land_to_unit": ("PARTIAL_AVAILABLE", "Plot/land records exist; unit-bearing coverage is limited", "EXACT when plot/land row contains unit"),
        "ai_similarity_candidate_matching": ("AVAILABLE", "Candidate matching available from area/project/building/unit clues", "Never exact by itself; returns HIGH_CONFIDENCE or CANDIDATE_MATCHES"),
    }
    future = {strategy.name: strategy.future_data for strategy in engine.strategies}
    for strategy in engine.strategies:
        availability, evidence, semantics = strategy_descriptions[strategy.name]
        lines.append(f"| {strategy.name} | {availability} | {evidence} | {semantics} | {future[strategy.name]} |")

    lines.extend(
        [
            "",
            "## Outcome Contract",
            "",
            "- `EXACT_MATCH`: the bridge has hard same-row or indexed evidence connecting input to a unit-bearing record.",
            "- `HIGH_CONFIDENCE`: a hard identifier exists or strong strategy evidence exists, but the exact unit bridge is incomplete.",
            "- `CANDIDATE_MATCHES`: usable candidate records exist, but exact identity is not proven.",
            "- `NO_MATCH`: the strategy is available but found no matching data.",
            "- `WAITING_FOR_DATA`: the capability exists, but required source data is unavailable in current datasets.",
            "",
            "## Strategy Test Output",
            "",
            f"- tests_csv: `{OUT_TESTS}`",
            f"- manifest_json: `{OUT_MANIFEST}`",
            "",
            "## Recommendation",
            "",
            "Build and keep the modular Bridge Engine. Do not continue deterministic URL-to-unit mapping until new bridge data arrives. Connect future Property Finder, Bayut, CRM, broker export, or DLD datasets by adding adapters into the existing bridge strategies rather than redesigning Unit Finder.",
        ]
    )
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    engine = BridgeEngine()
    test_rows = run_tests(engine)
    write_report(engine, test_rows)
    print(
        json.dumps(
            {
                "strategies": [strategy.name for strategy in engine.strategies],
                "tests_csv": str(OUT_TESTS),
                "report_md": str(OUT_REPORT),
                "manifest_json": str(OUT_MANIFEST),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
