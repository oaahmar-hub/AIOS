#!/usr/bin/env python3
"""Build the AIOS property graph from resolver and bridge artifacts.

This creates:
- canonical_property_master.csv/json
- listing_bridge_master.csv/json
- source_observations.csv
- match_audit_log.csv
- verification_queue.csv
- manual_bridge_confirmation_template.csv
- property_graph.sqlite
- PROPERTY_GRAPH_REPORT.md
- property_graph_summary.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import sys

KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
RESOLVER_DIR = KB / "resolver"
OUT_DIR = KB / "PropertyGraph"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.append(str(RESOLVER_DIR))
import bridge_data_layer as bridge_layer  # noqa: E402
import listing_similarity_matcher as matcher  # noqa: E402

INDEX_CSV = RESOLVER_DIR / "unit_resolver_index.csv"
CLUSTERS_CSV = RESOLVER_DIR / "same_unit_clusters.csv"
UNRESOLVED_CSV = RESOLVER_DIR / "unresolved_records_review.csv"
DB_PATH = RESOLVER_DIR / "unit_resolver_database.sqlite"

OUT_MASTER_CSV = OUT_DIR / "canonical_property_master.csv"
OUT_MASTER_JSON = OUT_DIR / "canonical_property_master.json"
OUT_BRIDGE_CSV = OUT_DIR / "listing_bridge_master.csv"
OUT_BRIDGE_JSON = OUT_DIR / "listing_bridge_master.json"
OUT_OBS_CSV = OUT_DIR / "source_observations.csv"
OUT_AUDIT_CSV = OUT_DIR / "match_audit_log.csv"
OUT_QUEUE_CSV = OUT_DIR / "verification_queue.csv"
OUT_TEMPLATE_CSV = OUT_DIR / "manual_bridge_confirmation_template.csv"
OUT_REPORT_MD = OUT_DIR / "PROPERTY_GRAPH_REPORT.md"
OUT_SUMMARY_JSON = OUT_DIR / "property_graph_summary.json"
OUT_SQLITE = OUT_DIR / "property_graph.sqlite"

PROPERTY_TYPES = {"apartment", "villa", "studio", "office", "warehouse", "shop", "commercial", "townhouse", "land"}
URL_PATH_NOISE = {"details", "listed", "finder", "property", "properties", "agent", "blog", "market", "analysis", "awards"}
VALIDATION_INPUTS = {
    "property_number": "AVENUE C VP 02",
    "building": "Beach Tower",
    "unit": "2205",
    "permit": "27459",
    "listing_url": "https://www.propertyfinder.ae/en/plp/commercial-rent/warehouse-for-rent-dubai-dubai-south-dubai-world-central-dubai-logistics-city-99983886.html",
}


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def low(value: object) -> str:
    return norm(value).lower()


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", low(value))


def parse_date(value: str) -> str:
    text = norm(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        pass
    return ""


def current_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_public_url(url: str) -> str:
    return bridge_layer.clean_url(url).rstrip("/")


def clean_identifier(value: str, field_name: str = "") -> str:
    text = norm(value)
    if not text:
        return ""
    lowered = low(text)
    if "propertyfinder" in lowered or "bayut" in lowered or "dubizzle" in lowered:
        return ""
    if lowered.startswith("/details"):
        return ""
    if "/" in text and field_name not in {"listing_url"}:
        return ""
    if any(token in lowered for token in URL_PATH_NOISE):
        return ""
    if field_name in {"permit_number", "plot_number", "land_number", "municipality_number", "dewa_number"} and not re.search(r"\d", text):
        return ""
    if field_name == "property_number" and not re.search(r"\d", text):
        return ""
    if len(text) > 60:
        return ""
    return text


def source_rank(record: Dict[str, str]) -> Tuple[int, str]:
    source_file = low(record.get("source_file", ""))
    source_path = low(record.get("source_path", ""))
    has_owner = norm(record.get("owner_contact_available", "")) == "YES"
    from_sheet = norm(record.get("extracted_from_sheet", "")) == "YES"
    from_pdf = norm(record.get("extracted_from_pdf", "")) == "YES"
    from_text = norm(record.get("extracted_from_text", "")) == "YES"
    has_chat = bool(norm(record.get("source_chat_group", "")))
    has_listing = bool(norm(record.get("listing_url", "")) or norm(record.get("property_finder_url", "")) or norm(record.get("bayut_url", "")) or norm(record.get("dubizzle_url", "")))

    if "crm" in source_file or "bitrix" in source_file:
        return 1, "crm_or_system_export"
    if has_owner and from_sheet:
        return 2, "owner_or_restricted_inventory"
    if from_sheet and not has_chat:
        return 3, "validated_spreadsheet_inventory"
    if from_sheet and has_chat:
        return 4, "whatsapp_structured_attachment"
    if from_pdf:
        return 5, "pdf_extraction"
    if has_listing:
        return 6, "public_listing_scrape"
    if from_text:
        return 7, "free_text_extraction"
    if source_path.endswith(".txt"):
        return 7, "free_text_extraction"
    return 8, "unclassified_source"


class UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def ensure(self, item: str) -> None:
        if item not in self.parent:
            self.parent[item] = item
        if item not in self.rank:
            self.rank[item] = 0

    def find(self, item: str) -> str:
        self.ensure(item)
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, a: str, b: str) -> bool:
        ra = self.find(a)
        rb = self.find(b)
        self.ensure(ra)
        self.ensure(rb)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


@dataclass
class Observation:
    resolver_record_id: str
    listing_url: str
    listing_id: str
    broker_reference: str
    permit_number: str
    property_number: str
    plot_number: str
    land_number: str
    municipality_number: str
    dewa_number: str
    area: str
    project: str
    building: str
    unit: str
    bedrooms: str
    size: str
    price: str
    developer: str
    owner_contact_available: str
    source_file: str
    source_path: str
    source_chat_group: str
    source_sheet: str
    row_number: str
    source_platform: str
    extracted_from_pdf: str
    extracted_from_sheet: str
    extracted_from_text: str
    extraction_confidence: str
    source_authority_rank: int
    source_authority_label: str
    freshness_date: str
    cpid: str = ""
    quarantine_reason: str = ""


def load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_owner_rows() -> Dict[str, Dict[str, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("select * from restricted_owner_contact").fetchall()
    con.close()
    return {norm(row["resolver_record_id"]): dict(row) for row in rows}


def load_bridge_rows() -> List[Dict[str, str]]:
    return bridge_layer.load_bridge_rows()


def choose_canonical(values: Iterable[str]) -> str:
    counter = Counter(v for v in values if norm(v))
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda item: (-item[1], len(item[0]), low(item[0])))[0][0]


def collect_unique(values: Iterable[str]) -> List[str]:
    out = []
    seen = set()
    for value in values:
        n = norm(value)
        if n and low(n) not in seen:
            seen.add(low(n))
            out.append(n)
    return out


def build_observations(rows: List[Dict[str, str]], owner_rows: Dict[str, Dict[str, str]]) -> Tuple[List[Observation], List[Dict[str, str]]]:
    observations: List[Observation] = []
    audit_rows: List[Dict[str, str]] = []
    for row in rows:
        record_id = norm(row.get("resolver_record_id", ""))
        area = matcher.canonical_area(row.get("area", ""))
        project = matcher.canonical_project(row.get("project", ""))
        building = matcher.canonical_building(row.get("building", ""))
        unit = matcher.normalize_unit(row.get("unit", ""))
        listing_url = clean_public_url(row.get("listing_url") or row.get("property_finder_url") or row.get("bayut_url") or row.get("dubizzle_url") or "")
        listing_id = norm(row.get("listing_id", ""))
        broker_reference = clean_identifier(row.get("broker_reference", ""), "broker_reference")
        permit_number = clean_identifier(row.get("permit_number", ""), "permit_number")
        property_number = clean_identifier(row.get("property_number", ""), "property_number")
        plot_number = clean_identifier(row.get("plot_number", ""), "plot_number")
        land_number = clean_identifier(row.get("land_number", ""), "land_number")
        municipality_number = clean_identifier(row.get("municipality_number", ""), "municipality_number")
        dewa_number = clean_identifier(row.get("dewa_number", ""), "dewa_number")
        size = norm(row.get("size", ""))
        price = norm(row.get("price", ""))
        bedrooms = matcher.canonical_bedrooms(row.get("bedrooms", ""))
        source_path = norm(row.get("source_path", ""))
        freshness = ""
        if source_path and Path(source_path).exists():
            freshness = datetime.fromtimestamp(Path(source_path).stat().st_mtime, tz=timezone.utc).date().isoformat()
        authority_rank, authority_label = source_rank(row)
        quarantine_reasons = []
        raw_property = norm(row.get("property_number", ""))
        if raw_property and not property_number:
            quarantine_reasons.append("polluted_property_number")
        if listing_url and any(token in low(listing_url) for token in ("/blog/", "/agent/", "market-analysis", "/awards-", "/awards/")):
            quarantine_reasons.append("non_listing_public_url")
        if listing_url and not any(domain in low(listing_url) for domain in ("propertyfinder.ae", "bayut.com", "dubizzle.com")):
            quarantine_reasons.append("unsupported_public_url")
        if not any([property_number, permit_number, plot_number, land_number, municipality_number, dewa_number, unit, listing_id, listing_url]):
            if not any([area, project, building]):
                quarantine_reasons.append("no_resolver_signal")
        if building and len(matcher.tokenize(building)) == 1 and matcher.tokenize(building)[0] in {"tower", "building", "residence", "heights"}:
            quarantine_reasons.append("generic_building_name")

        obs = Observation(
            resolver_record_id=record_id,
            listing_url=listing_url,
            listing_id=listing_id,
            broker_reference=broker_reference,
            permit_number=permit_number,
            property_number=property_number,
            plot_number=plot_number,
            land_number=land_number,
            municipality_number=municipality_number,
            dewa_number=dewa_number,
            area=area,
            project=project,
            building=building,
            unit=unit,
            bedrooms=bedrooms,
            size=size,
            price=price,
            developer=norm(row.get("developer", "")),
            owner_contact_available="YES" if record_id in owner_rows or norm(row.get("owner_contact_available", "")) == "YES" else "NO",
            source_file=norm(row.get("source_file", "")),
            source_path=source_path,
            source_chat_group=norm(row.get("source_chat_group", "")),
            source_sheet=norm(row.get("source_sheet", "")),
            row_number=norm(row.get("row_number", "")),
            source_platform=norm(row.get("source_platform", "")),
            extracted_from_pdf=norm(row.get("extracted_from_pdf", "")),
            extracted_from_sheet=norm(row.get("extracted_from_sheet", "")),
            extracted_from_text=norm(row.get("extracted_from_text", "")),
            extraction_confidence=norm(row.get("extraction_confidence", "")),
            source_authority_rank=authority_rank,
            source_authority_label=authority_label,
            freshness_date=freshness,
            quarantine_reason=";".join(quarantine_reasons),
        )
        observations.append(obs)
        audit_rows.append(
            {
                "resolver_record_id": record_id,
                "source_file": obs.source_file,
                "source_authority": authority_label,
                "source_authority_rank": str(authority_rank),
                "listing_url": obs.listing_url,
                "listing_id": obs.listing_id,
                "property_number": obs.property_number,
                "permit_number": obs.permit_number,
                "plot_number": obs.plot_number,
                "area": obs.area,
                "project": obs.project,
                "building": obs.building,
                "unit": obs.unit,
                "owner_contact_available": obs.owner_contact_available,
                "quarantine_reason": obs.quarantine_reason,
            }
        )
    return observations, audit_rows


def union_by_keys(observations: List[Observation]) -> Tuple[UnionFind, List[Dict[str, str]]]:
    uf = UnionFind(obs.resolver_record_id for obs in observations)
    audit = []

    def apply_union(bucket_name: str, pairs: Dict[str, List[str]]) -> None:
        for anchor, ids in pairs.items():
            if len(ids) < 2:
                continue
            head = ids[0]
            for other in ids[1:]:
                if uf.union(head, other):
                    audit.append({"link_type": bucket_name, "anchor": anchor, "left_record_id": head, "right_record_id": other})

    strong = {
        "property_number": defaultdict(list),
        "permit_number": defaultdict(list),
        "plot_number": defaultdict(list),
        "land_number": defaultdict(list),
        "municipality_number": defaultdict(list),
        "dewa_number": defaultdict(list),
        "listing_id": defaultdict(list),
        "listing_url": defaultdict(list),
        "broker_reference": defaultdict(list),
        "building_unit": defaultdict(list),
    }
    for obs in observations:
        if obs.property_number:
            strong["property_number"][key(obs.property_number)].append(obs.resolver_record_id)
        if obs.permit_number:
            strong["permit_number"][key(obs.permit_number)].append(obs.resolver_record_id)
        if obs.plot_number:
            strong["plot_number"][key(obs.plot_number)].append(obs.resolver_record_id)
        if obs.land_number:
            strong["land_number"][key(obs.land_number)].append(obs.resolver_record_id)
        if obs.municipality_number:
            strong["municipality_number"][key(obs.municipality_number)].append(obs.resolver_record_id)
        if obs.dewa_number:
            strong["dewa_number"][key(obs.dewa_number)].append(obs.resolver_record_id)
        if obs.listing_id:
            strong["listing_id"][key(obs.listing_id)].append(obs.resolver_record_id)
        if obs.listing_url:
            strong["listing_url"][key(obs.listing_url)].append(obs.resolver_record_id)
        if obs.broker_reference:
            strong["broker_reference"][key(obs.broker_reference)].append(obs.resolver_record_id)
        entity = obs.building or obs.project
        if obs.unit and entity:
            area = obs.area or "unknown-area"
            strong["building_unit"][f"{key(area)}|{key(entity)}|{key(obs.unit)}"].append(obs.resolver_record_id)

    for name, bucket in strong.items():
        apply_union(name, bucket)
    return uf, audit


def component_cpid(component_obs: List[Observation]) -> str:
    for prefix, field in [
        ("PROP", "property_number"),
        ("PERMIT", "permit_number"),
        ("PLOT", "plot_number"),
        ("LAND", "land_number"),
        ("MUNI", "municipality_number"),
        ("DEWA", "dewa_number"),
    ]:
        values = collect_unique(getattr(obs, field) for obs in component_obs)
        if values:
            return f"CPID-{prefix}-{key(values[0])}"
    for obs in component_obs:
        entity = obs.building or obs.project
        if obs.unit and entity:
            seed = f"{obs.area}|{entity}|{obs.unit}"
            return f"CPID-UNIT-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"
    for obs in component_obs:
        if obs.listing_id:
            return f"CPID-LIST-{key(obs.listing_id)[:20]}"
    seed = "|".join(sorted(obs.resolver_record_id for obs in component_obs))
    return f"CPID-HASH-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def verification_state(component_obs: List[Observation]) -> Tuple[str, str]:
    has_unit = any(obs.unit for obs in component_obs)
    has_entity = any(obs.building or obs.project for obs in component_obs)
    strong_fields = any(
        any(getattr(obs, field) for field in ("property_number", "permit_number", "plot_number", "land_number", "municipality_number", "dewa_number"))
        for obs in component_obs
    )
    has_public = any(obs.listing_url or obs.listing_id or obs.broker_reference for obs in component_obs)
    if strong_fields and has_unit and has_entity:
        return "VERIFIED_EXACT", "hard identifier and unit/building evidence present"
    if strong_fields and (has_entity or has_unit):
        return "VERIFIED_STRUCTURAL", "hard identifier exists with partial structural evidence"
    if has_unit and has_entity and len(component_obs) > 1:
        return "LIKELY", "same unit/building observed across multiple records"
    if has_public or has_entity or has_unit:
        return "POSSIBLE", "public or structural clues exist but no hard bridge"
    return "UNRESOLVED", "record lacks enough deterministic or structural evidence"


def summarize_component(cpid: str, component_obs: List[Observation]) -> Dict[str, str]:
    verification, verification_reason = verification_state(component_obs)
    source_dates = [obs.freshness_date for obs in component_obs if obs.freshness_date]
    prices = collect_unique(obs.price for obs in component_obs)
    listing_urls = collect_unique(obs.listing_url for obs in component_obs)
    listing_ids = collect_unique(obs.listing_id for obs in component_obs)
    broker_refs = collect_unique(obs.broker_reference for obs in component_obs)
    property_numbers = collect_unique(obs.property_number for obs in component_obs)
    permit_numbers = collect_unique(obs.permit_number for obs in component_obs)
    plot_numbers = collect_unique(obs.plot_number for obs in component_obs)
    land_numbers = collect_unique(obs.land_number for obs in component_obs)
    municipality_numbers = collect_unique(obs.municipality_number for obs in component_obs)
    dewa_numbers = collect_unique(obs.dewa_number for obs in component_obs)
    areas = collect_unique(obs.area for obs in component_obs)
    projects = collect_unique(obs.project for obs in component_obs)
    buildings = collect_unique(obs.building for obs in component_obs)
    units = collect_unique(obs.unit for obs in component_obs)
    developers = collect_unique(obs.developer for obs in component_obs)
    source_files = collect_unique(obs.source_file for obs in component_obs)
    source_groups = collect_unique(obs.source_chat_group for obs in component_obs)
    owner_flag = "YES" if any(obs.owner_contact_available == "YES" for obs in component_obs) else "NO"
    highest_authority = min(obs.source_authority_rank for obs in component_obs)
    highest_authority_label = choose_canonical(obs.source_authority_label for obs in component_obs if obs.source_authority_rank == highest_authority)
    quarantine = collect_unique(obs.quarantine_reason for obs in component_obs if obs.quarantine_reason)

    return {
        "cpid": cpid,
        "verification_state": verification,
        "verification_reason": verification_reason,
        "canonical_area": choose_canonical(areas),
        "canonical_project": choose_canonical(projects),
        "canonical_building": choose_canonical(buildings),
        "canonical_unit": choose_canonical(units),
        "developer": choose_canonical(developers),
        "property_numbers": " | ".join(property_numbers),
        "permit_numbers": " | ".join(permit_numbers),
        "plot_numbers": " | ".join(plot_numbers),
        "land_numbers": " | ".join(land_numbers),
        "municipality_numbers": " | ".join(municipality_numbers),
        "dewa_numbers": " | ".join(dewa_numbers),
        "listing_ids": " | ".join(listing_ids),
        "listing_urls": " | ".join(listing_urls[:10]),
        "broker_references": " | ".join(broker_refs),
        "owner_contact_available": owner_flag,
        "record_count": str(len(component_obs)),
        "source_count": str(len(source_files)),
        "source_files": " | ".join(source_files[:20]),
        "source_groups": " | ".join(source_groups[:10]),
        "highest_authority_rank": str(highest_authority),
        "highest_authority_label": highest_authority_label,
        "oldest_seen_date": min(source_dates) if source_dates else "",
        "latest_seen_date": max(source_dates) if source_dates else "",
        "last_asking_price": prices[0] if prices else "",
        "listing_url_count": str(len(listing_urls)),
        "listing_id_count": str(len(listing_ids)),
        "broker_reference_count": str(len(broker_refs)),
        "quarantine_flags": " | ".join(quarantine),
    }


def build_bridge_master(observations: List[Observation], component_map: Dict[str, str], bridge_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    by_key = {}
    out = []

    def add_row(row: Dict[str, str]) -> None:
        unique_key = "|".join(
            [
                low(row.get("listing_url", "")),
                low(row.get("listing_id", "")),
                low(row.get("broker_reference", "")),
                low(row.get("cpid", "")),
                low(row.get("source", "")),
            ]
        )
        if unique_key in by_key:
            return
        by_key[unique_key] = True
        out.append(row)

    for obs in observations:
        if not any([obs.listing_url, obs.listing_id, obs.broker_reference]):
            continue
        cpid = component_map.get(obs.resolver_record_id, "")
        bridge_status = "waiting_for_data"
        confidence = "65"
        missing = []
        if cpid and any([obs.property_number, obs.permit_number, obs.plot_number, obs.land_number, obs.unit]):
            bridge_status = "exact_bridge"
            confidence = "100"
        elif cpid and any([obs.area, obs.project, obs.building]):
            bridge_status = "partial_bridge"
            confidence = "80"
            if not any([obs.property_number, obs.permit_number, obs.plot_number, obs.land_number, obs.unit]):
                missing.append("hard_property_identifier")
        else:
            missing.append("cpid_link")
        add_row(
            {
                "source_platform": obs.source_platform or matcher.parse_platform(obs.listing_url),
                "listing_url": obs.listing_url,
                "listing_id": obs.listing_id or matcher.parse_listing_id(obs.listing_url),
                "broker_reference": obs.broker_reference,
                "permit_number": obs.permit_number,
                "property_number": obs.property_number,
                "plot_number": obs.plot_number or obs.land_number,
                "building": obs.building or obs.project,
                "unit": obs.unit,
                "cpid": cpid,
                "source": obs.source_file,
                "freshness": obs.freshness_date,
                "confidence": confidence,
                "verified_by": "system_derived",
                "bridge_status": bridge_status,
                "missing_bridge_fields": " | ".join(missing),
            }
        )

    for row in bridge_rows:
        cpid = ""
        resolver_record_id = norm(row.get("resolver_record_id", ""))
        if resolver_record_id and resolver_record_id in component_map:
            cpid = component_map[resolver_record_id]
        if not cpid:
            cpid = norm(row.get("canonical_property_id", ""))
        bridge_status = norm(row.get("bridge_classification", ""))
        missing = []
        if bridge_status != "exact_bridge":
            if not any(norm(row.get(field, "")) for field in ("property_number", "permit_number", "plot_number", "unit_number")):
                missing.append("hard_property_identifier")
            if not cpid:
                missing.append("cpid_link")
        add_row(
            {
                "source_platform": norm(row.get("source_platform", "")),
                "listing_url": clean_public_url(row.get("listing_url", "")),
                "listing_id": norm(row.get("listing_id", "")),
                "broker_reference": clean_identifier(row.get("broker_reference", ""), "broker_reference"),
                "permit_number": clean_identifier(row.get("permit_number", ""), "permit_number"),
                "property_number": clean_identifier(row.get("property_number", ""), "property_number"),
                "plot_number": clean_identifier(row.get("plot_number", ""), "plot_number"),
                "building": norm(row.get("building_name", "")) or norm(row.get("project_name", "")),
                "unit": matcher.normalize_unit(row.get("unit_number", "")),
                "cpid": cpid,
                "source": norm(row.get("source_file", "")),
                "freshness": parse_date(row.get("source_updated_at", "")),
                "confidence": norm(row.get("confidence", "")),
                "verified_by": "bridge_import",
                "bridge_status": bridge_status or "waiting_for_data",
                "missing_bridge_fields": " | ".join(missing),
            }
        )
    return out


def build_queue(master_rows: List[Dict[str, str]], observations: List[Observation], unresolved_rows: List[Dict[str, str]], bridge_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    queue = []
    obs_by_id = {obs.resolver_record_id: obs for obs in observations}
    for row in master_rows:
        if row["verification_state"] in {"POSSIBLE", "UNRESOLVED"}:
            reason = "missing_bridge_or_structural_confirmation"
            if row["listing_url_count"] != "0" and not any([row["property_numbers"], row["permit_numbers"], row["plot_numbers"], row["canonical_unit"]]):
                reason = "public_listing_without_hard_identifier"
            queue.append(
                {
                    "queue_type": "cpid_review",
                    "cpid": row["cpid"],
                    "resolver_record_id": "",
                    "reason": reason,
                    "severity": "high" if "public_listing" in reason else "medium",
                    "recommended_action": "collect broker reference or property/permit/plot/unit bridge",
                    "source_file": row["source_files"].split(" | ")[0] if row["source_files"] else "",
                }
            )
        if row["quarantine_flags"]:
            queue.append(
                {
                    "queue_type": "quarantine_review",
                    "cpid": row["cpid"],
                    "resolver_record_id": "",
                    "reason": row["quarantine_flags"],
                    "severity": "medium",
                    "recommended_action": "validate polluted or noisy source row before reuse",
                    "source_file": row["source_files"].split(" | ")[0] if row["source_files"] else "",
                }
            )
    for row in unresolved_rows:
        queue.append(
            {
                "queue_type": "unresolved_resolver_record",
                "cpid": "",
                "resolver_record_id": "",
                "reason": norm(row.get("failure_reason", "")),
                "severity": "medium",
                "recommended_action": norm(row.get("suggested_strategy", "")),
                "source_file": norm(row.get("source_file", "")),
            }
        )
    for row in bridge_rows:
        if norm(row.get("bridge_status", "")) in {"waiting_for_data", "partial_bridge"}:
            queue.append(
                {
                    "queue_type": "bridge_gap",
                    "cpid": norm(row.get("cpid", "")),
                    "resolver_record_id": "",
                    "reason": norm(row.get("missing_bridge_fields", "")) or norm(row.get("bridge_status", "")),
                    "severity": "high" if row.get("listing_url") else "medium",
                    "recommended_action": "obtain listing reference, broker reference, or hard property identifier",
                    "source_file": norm(row.get("source", "")),
                }
            )
    deduped = []
    seen = set()
    for row in queue:
        sig = "|".join(low(row.get(k, "")) for k in ("queue_type", "cpid", "reason", "source_file"))
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(row)
    return deduped


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(master_rows: List[Dict[str, str]], bridge_rows: List[Dict[str, str]], obs_rows: List[Dict[str, str]], queue_rows: List[Dict[str, str]], audit_rows: List[Dict[str, str]]) -> None:
    if OUT_SQLITE.exists():
        OUT_SQLITE.unlink()
    con = sqlite3.connect(OUT_SQLITE)
    cur = con.cursor()
    cur.executescript(
        """
        create table canonical_properties (
            cpid text primary key,
            verification_state text,
            verification_reason text,
            canonical_area text,
            canonical_project text,
            canonical_building text,
            canonical_unit text,
            developer text,
            property_numbers text,
            permit_numbers text,
            plot_numbers text,
            land_numbers text,
            municipality_numbers text,
            dewa_numbers text,
            listing_ids text,
            listing_urls text,
            broker_references text,
            owner_contact_available text,
            record_count integer,
            source_count integer,
            source_files text,
            source_groups text,
            highest_authority_rank integer,
            highest_authority_label text,
            oldest_seen_date text,
            latest_seen_date text,
            last_asking_price text,
            listing_url_count integer,
            listing_id_count integer,
            broker_reference_count integer,
            quarantine_flags text
        );
        create table listing_bridge_master (
            source_platform text,
            listing_url text,
            listing_id text,
            broker_reference text,
            permit_number text,
            property_number text,
            plot_number text,
            building text,
            unit text,
            cpid text,
            source text,
            freshness text,
            confidence integer,
            verified_by text,
            bridge_status text,
            missing_bridge_fields text
        );
        create table source_observations (
            resolver_record_id text,
            cpid text,
            source_file text,
            source_path text,
            source_chat_group text,
            source_sheet text,
            row_number text,
            source_platform text,
            listing_url text,
            listing_id text,
            broker_reference text,
            permit_number text,
            property_number text,
            plot_number text,
            land_number text,
            municipality_number text,
            dewa_number text,
            area text,
            project text,
            building text,
            unit text,
            bedrooms text,
            size text,
            price text,
            developer text,
            owner_contact_available text,
            source_authority_rank integer,
            source_authority_label text,
            freshness_date text,
            quarantine_reason text
        );
        create table match_audit_log (
            link_type text,
            anchor text,
            left_record_id text,
            right_record_id text
        );
        create table verification_queue (
            queue_type text,
            cpid text,
            resolver_record_id text,
            reason text,
            severity text,
            recommended_action text,
            source_file text
        );
        create index idx_cp_area on canonical_properties(canonical_area);
        create index idx_cp_building on canonical_properties(canonical_building);
        create index idx_cp_property on canonical_properties(property_numbers);
        create index idx_bridge_url on listing_bridge_master(listing_url);
        create index idx_bridge_listing on listing_bridge_master(listing_id);
        create index idx_bridge_cpid on listing_bridge_master(cpid);
        """
    )
    cur.executemany(
        "insert into canonical_properties values ({})".format(",".join("?" * len(master_rows[0]))),
        [tuple(row.values()) for row in master_rows],
    )
    cur.executemany(
        "insert into listing_bridge_master values ({})".format(",".join("?" * len(bridge_rows[0]))),
        [tuple(row.values()) for row in bridge_rows],
    )
    cur.executemany(
        "insert into source_observations values ({})".format(",".join("?" * len(obs_rows[0]))),
        [tuple(row.values()) for row in obs_rows],
    )
    cur.executemany(
        "insert into match_audit_log values ({})".format(",".join("?" * len(audit_rows[0]))),
        [tuple(row.values()) for row in audit_rows],
    )
    cur.executemany(
        "insert into verification_queue values ({})".format(",".join("?" * len(queue_rows[0]))),
        [tuple(row.values()) for row in queue_rows],
    )
    con.commit()
    con.close()


def build() -> Dict[str, object]:
    owner_rows = load_owner_rows()
    rows = load_csv_rows(INDEX_CSV)
    bridge_rows = load_bridge_rows()
    unresolved_rows = load_csv_rows(UNRESOLVED_CSV) if UNRESOLVED_CSV.exists() else []
    observations, obs_audit = build_observations(rows, owner_rows)
    uf, link_audit = union_by_keys(observations)

    component_groups: Dict[str, List[Observation]] = defaultdict(list)
    for obs in observations:
        component_groups[uf.find(obs.resolver_record_id)].append(obs)

    component_map = {}
    master_rows = []
    for component_obs in component_groups.values():
        cpid = component_cpid(component_obs)
        for obs in component_obs:
            obs.cpid = cpid
            component_map[obs.resolver_record_id] = cpid
        master_rows.append(summarize_component(cpid, component_obs))
    master_rows.sort(key=lambda row: (row["verification_state"], row["canonical_area"], row["canonical_building"], row["canonical_unit"], row["cpid"]))

    bridge_master = build_bridge_master(observations, component_map, bridge_rows)
    bridge_master.sort(key=lambda row: (row["bridge_status"], row["source_platform"], row["listing_url"], row["cpid"]))

    obs_rows = [
        {
            "resolver_record_id": obs.resolver_record_id,
            "cpid": obs.cpid,
            "source_file": obs.source_file,
            "source_path": obs.source_path,
            "source_chat_group": obs.source_chat_group,
            "source_sheet": obs.source_sheet,
            "row_number": obs.row_number,
            "source_platform": obs.source_platform,
            "listing_url": obs.listing_url,
            "listing_id": obs.listing_id,
            "broker_reference": obs.broker_reference,
            "permit_number": obs.permit_number,
            "property_number": obs.property_number,
            "plot_number": obs.plot_number,
            "land_number": obs.land_number,
            "municipality_number": obs.municipality_number,
            "dewa_number": obs.dewa_number,
            "area": obs.area,
            "project": obs.project,
            "building": obs.building,
            "unit": obs.unit,
            "bedrooms": obs.bedrooms,
            "size": obs.size,
            "price": obs.price,
            "developer": obs.developer,
            "owner_contact_available": obs.owner_contact_available,
            "source_authority_rank": str(obs.source_authority_rank),
            "source_authority_label": obs.source_authority_label,
            "freshness_date": obs.freshness_date,
            "quarantine_reason": obs.quarantine_reason,
        }
        for obs in observations
    ]
    queue_rows = build_queue(master_rows, observations, unresolved_rows, bridge_master)
    audit_rows = link_audit + [
        {
            "link_type": "observation_quality",
            "anchor": row["quarantine_reason"],
            "left_record_id": row["resolver_record_id"],
            "right_record_id": "",
        }
        for row in obs_audit
        if row["quarantine_reason"]
    ]

    write_csv(OUT_MASTER_CSV, master_rows, list(master_rows[0].keys()))
    OUT_MASTER_JSON.write_text(json.dumps(master_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUT_BRIDGE_CSV, bridge_master, list(bridge_master[0].keys()))
    OUT_BRIDGE_JSON.write_text(json.dumps(bridge_master, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUT_OBS_CSV, obs_rows, list(obs_rows[0].keys()))
    write_csv(OUT_AUDIT_CSV, audit_rows, list(audit_rows[0].keys()))
    write_csv(OUT_QUEUE_CSV, queue_rows, list(queue_rows[0].keys()))
    write_csv(
        OUT_TEMPLATE_CSV,
        [],
        ["listing_url", "listing_id", "broker_reference", "permit_number", "property_number", "plot_number", "building", "unit", "cpid", "verified_by", "notes"],
    )
    write_sqlite(master_rows, bridge_master, obs_rows, queue_rows, audit_rows)

    state_counts = Counter(row["verification_state"] for row in master_rows)
    bridge_counts = Counter(row["bridge_status"] for row in bridge_master)
    summary = {
        "generated_at": current_utc(),
        "resolver_records": len(rows),
        "canonical_properties": len(master_rows),
        "source_observations": len(obs_rows),
        "bridge_rows": len(bridge_master),
        "verification_queue": len(queue_rows),
        "verification_state_counts": dict(state_counts),
        "bridge_status_counts": dict(bridge_counts),
        "owner_contact_cpid_count": sum(1 for row in master_rows if row["owner_contact_available"] == "YES"),
        "public_listing_cpid_count": sum(1 for row in master_rows if int(row["listing_url_count"]) > 0),
    }
    OUT_SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# AIOS Property Graph Report",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- resolver_records: `{summary['resolver_records']}`",
        f"- canonical_properties: `{summary['canonical_properties']}`",
        f"- source_observations: `{summary['source_observations']}`",
        f"- listing_bridge_master_rows: `{summary['bridge_rows']}`",
        f"- verification_queue_rows: `{summary['verification_queue']}`",
        f"- owner_contact_cpid_count: `{summary['owner_contact_cpid_count']}`",
        f"- public_listing_cpid_count: `{summary['public_listing_cpid_count']}`",
        "",
        "## Verification States",
    ]
    for state, count in sorted(state_counts.items()):
        lines.append(f"- {state}: `{count}`")
    lines.extend(["", "## Bridge Status"])
    for state, count in sorted(bridge_counts.items()):
        lines.append(f"- {state}: `{count}`")
    lines.extend(
        [
            "",
            "## Outputs",
            f"- `{OUT_MASTER_CSV}`",
            f"- `{OUT_BRIDGE_CSV}`",
            f"- `{OUT_OBS_CSV}`",
            f"- `{OUT_AUDIT_CSV}`",
            f"- `{OUT_QUEUE_CSV}`",
            f"- `{OUT_SQLITE}`",
        ]
    )
    OUT_REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, ensure_ascii=False, indent=2))
