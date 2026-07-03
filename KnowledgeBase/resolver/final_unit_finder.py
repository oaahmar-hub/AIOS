#!/usr/bin/env python3
"""AIOS Unit Finder final resolver: any clue -> best unit/property match."""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


RESOLVER_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver")
OUT_TESTS = RESOLVER_DIR / "final_unit_finder_tests.csv"
OUT_REPORT = RESOLVER_DIR / "final_unit_finder_report.md"
BENCHMARK_CSV = RESOLVER_DIR / "live_listing_benchmark_results.csv"
RAW_CHAT_CSV = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/raw_data/csv/5ca554ad55ac__omar_style_dataset_sample.csv")

import sys

sys.path.append(str(RESOLVER_DIR))
import bridge_data_layer as bridge_layer  # noqa: E402
import listing_similarity_matcher as matcher  # noqa: E402


IDENTIFIER_KEYS = [
    "permit_number",
    "property_number",
    "plot_number",
    "land_number",
    "municipality_number",
    "dewa_number",
]

EXACT_IDENTIFIER_SCORES = {
    "permit_number": 99,
    "property_number": 98,
    "plot_number": 97,
    "land_number": 97,
    "municipality_number": 96,
    "dewa_number": 95,
}

FIELD_ORDER = [
    "permit_number",
    "property_number",
    "plot_number",
    "land_number",
    "municipality_number",
    "dewa_number",
    "area",
    "project",
    "building",
    "unit",
    "bedrooms",
    "bathrooms",
    "size",
    "price",
    "property_type",
    "agent_company",
    "broker_reference",
    "status_tokens",
    "floor",
    "view",
]

PROPERTY_TEXT_HINTS = ("bed", "bath", "sqft", "sqm", "asking", "aed", "price", "vacant", "furnished", "upgraded")
BROKER_REF_RE = re.compile(r"(?:broker(?:\s+ref(?:erence)?)?)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9-]{4,40})", re.I)
FLOOR_RE = re.compile(r"\b(?:floor|flr)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9-]{1,10})\b", re.I)
VIEW_RE = re.compile(r"\b(sea view|marina view|park view|pool view|canal view|golf view|garden view|community view|burj view)\b", re.I)
URL_DOMAIN_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)\b", re.I)
PURE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9/-]{4,40}$")
PROPERTY_NUMBER_TEXT_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9 /-]{4,40}$")
AMBIGUOUS_SEARCH_RE = re.compile(
    r"\b(?:am\s+looking|i\s+am\s+looking|looking\s+for|can\s+i\s+have|please|hello|need|want|shortlist|budget|up\s+to)\b",
    re.I,
)
CONVERSATIONAL_BUILDING_TOKENS = {
    "am",
    "looking",
    "hello",
    "please",
    "can",
    "have",
    "need",
    "want",
    "send",
    "shortlist",
    "budget",
}
GENERIC_ENTITY_TOKENS = {
    "tower",
    "building",
    "residence",
    "residences",
    "park",
    "village",
    "heights",
    "bay",
    "plaza",
    "centre",
    "center",
}


def norm(value):
    return matcher.norm(value)


def low(value):
    return matcher.low(value)


def normalize_identifier(value):
    return re.sub(r"[^a-z0-9]", "", low(value))


def parse_numeric(value):
    if value in ("", None):
        return ""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(value).replace(",", ""))
    if not m:
        return ""
    try:
        return float(m.group(1))
    except Exception:
        return ""


def list_to_text_url(rec):
    return (
        rec.get("listing_url")
        or rec.get("property_finder_url")
        or rec.get("bayut_url")
        or rec.get("dubizzle_url")
        or ""
    )


def is_url_text(value):
    return bool(URL_DOMAIN_RE.search(str(value or "")))


def is_pure_identifier_text(value):
    text = norm(value)
    return bool(text and " " not in text and PURE_IDENTIFIER_RE.fullmatch(text))


def looks_like_property_number_text(value):
    text = norm(value)
    if not text or is_url_text(text):
        return False
    if not PROPERTY_NUMBER_TEXT_RE.fullmatch(text):
        return False
    lowered = low(text)
    if any(hint in lowered for hint in PROPERTY_TEXT_HINTS):
        return False
    if any(token in lowered for token in (" unit ", " building ", " tower ", " apartment ", " villa ")):
        return False
    return True


def is_generic_entity(value):
    tokens = matcher.tokenize(value)
    return bool(tokens) and len(tokens) == 1 and tokens[0] in GENERIC_ENTITY_TOKENS


def candidate_entities(building, project):
    values = []
    for raw in (project, building):
        raw_norm = norm(raw)
        if raw_norm and not is_generic_entity(raw_norm):
            values.append(raw_norm)
        proj = matcher.canonical_project(raw_norm)
        if proj and not is_generic_entity(proj):
            values.append(proj)
        bld = matcher.canonical_building(raw_norm)
        if bld and not is_generic_entity(bld):
            values.append(bld)
    ordered = []
    seen = set()
    for value in values:
        sig = low(value)
        if sig and sig not in seen:
            seen.add(sig)
            ordered.append(value)
    return ordered


def explain_missing(query, ranked):
    if ranked:
        top = ranked[0]
        missing = top.get("missing_fields", [])
        if top["classification"] == "EXACT":
            if not top["record"].get("unit"):
                return {
                    "resolution_summary": "Exact identifier matched, but the matched record does not carry a unit field.",
                    "missing_data": ["unit"],
                    "recommended_inputs": ["unit number", "building + unit", "property number", "plot/land number"],
                }
            return {
                "resolution_summary": "Exact property record found.",
                "missing_data": [],
                "recommended_inputs": [],
            }
        if top["classification"] in {"LIKELY", "PARTIAL"}:
            return {
                "resolution_summary": "No exact bridge was found. Returning the strongest local candidates.",
                "missing_data": missing,
                "recommended_inputs": ["permit number", "property number", "unit number", "building + unit"],
            }
    if query.get("listing_url") and (query.get("listing_id") or query.get("listing_reference")):
        return {
            "resolution_summary": "Listing URL or listing reference was parsed, but no internal bridge dataset links it to a unit-bearing record.",
            "missing_data": ["listing reference to unit bridge", "broker reference to unit bridge", "permit/property/plot/unit identifier"],
            "recommended_inputs": ["permit number", "property number", "plot/land number", "building + unit", "broker reference"],
        }
    if any(query.get(key) for key in IDENTIFIER_KEYS):
        return {
            "resolution_summary": "Identifier search completed, but no matching normalized identifier exists in the current resolver index.",
            "missing_data": ["matching normalized identifier in resolver index"],
            "recommended_inputs": ["alternate permit/property/plot formatting", "building + unit", "listing URL with broker reference"],
        }
    return {
        "resolution_summary": "The current clues are not enough to link to an exact property record.",
        "missing_data": ["strong identifier or stronger location/unit clues"],
        "recommended_inputs": ["permit number", "property number", "unit number", "building + unit"],
    }


def pseudo_record_from_bridge_row(row):
    return {
        "resolver_record_id": row.get("resolver_record_id", "") or row.get("canonical_property_id", ""),
        "source_file": row.get("source_file", ""),
        "source_sheet": row.get("source_sheet", ""),
        "row_number": row.get("row_number", ""),
        "source_platform": row.get("source_platform", ""),
        "listing_url": row.get("listing_url", ""),
        "area": row.get("community", ""),
        "project": row.get("project_name", ""),
        "building": row.get("building_name", ""),
        "unit": row.get("unit_number", ""),
        "bedrooms": "",
        "bathrooms": "",
        "size": row.get("size_clues", ""),
        "price": row.get("price_clues", ""),
        "permit_number": row.get("permit_number", ""),
        "property_number": row.get("property_number", ""),
        "plot_number": row.get("plot_number", ""),
        "land_number": "",
        "municipality_number": "",
        "dewa_number": "",
        "owner_contact_available": row.get("owner_contact_available", "NO"),
        "canonical_size_sqm": matcher.parse_size_value(row.get("size_clues", "")),
        "canonical_price": matcher.parse_price_value(row.get("price_clues", "")),
        "status_tokens": "",
    }


def bridge_row_to_records(row):
    records = []
    resolver_record_id = row.get("resolver_record_id", "")
    if resolver_record_id:
        records.extend(RECORDS_BY_ID.get(resolver_record_id, []))
    for key_name, index_key in [
        ("property_number", "property_number"),
        ("permit_number", "permit_number"),
        ("plot_number", "plot_number"),
    ]:
        value = normalize_identifier(row.get(key_name, ""))
        if value:
            records.extend(IDENTIFIER_INDEX[index_key].get(value, []))
    unit = matcher.normalize_unit(row.get("unit_number", ""))
    if unit:
        area = matcher.canonical_area(row.get("community", ""))
        for entity in candidate_entities(row.get("building_name", ""), row.get("project_name", "")):
            if area:
                records.extend(BUILDING_UNIT_INDEX.get((area, entity, unit), []))
            records.extend(BUILDING_UNIT_INDEX.get((entity, unit), []))
    if not records:
        records.append(pseudo_record_from_bridge_row(row))
    unique = []
    seen = set()
    for rec in records:
        sig = row_key(rec)
        if sig not in seen:
            seen.add(sig)
            unique.append(rec)
    return unique


def collect_bridge_matches(query, field_name):
    value = query.get(field_name, "")
    if not value:
        return []
    rows = bridge_layer.bridge_lookup(field_name, value)
    found = {}
    for row in rows:
        if row.get("bridge_classification") == "invalid_bridge":
            continue
        if row.get("bridge_classification") == "exact_bridge":
            score = 96
            match_type = "bridge_exact"
        elif row.get("bridge_classification") == "partial_bridge":
            score = 82
            match_type = "bridge_partial"
        else:
            score = 68
            match_type = "bridge_candidate"
        breakdown = [f"{field_name}:{row.get('bridge_classification', '')}"]
        for rec in bridge_row_to_records(row):
            found[row_key(rec)] = build_result_candidate(rec, score, query, match_type, breakdown)
    return sorted(
        found.values(),
        key=lambda item: (item["confidence_score"], item["classification"], item["resolver_record_id"]),
        reverse=True,
    )[:5]


def parse_json_or_text(input_text_or_json):
    pattern_source = ""
    if isinstance(input_text_or_json, dict):
        payload = dict(input_text_or_json)
        base = {}
        url_value = payload.get("listing_url") or payload.get("url") or ""
        if url_value:
            base.update(matcher.parse_url_fields(str(url_value)))
        seed_parts = []
        for key in FIELD_ORDER + ["description_text", "query_text", "listing_reference"]:
            value = payload.get(key, "")
            if value:
                seed_parts.append(str(value))
        pattern_source = " ".join(seed_parts)
        if seed_parts:
            parsed_seed = matcher.parse_input_text(" ".join(seed_parts))
            for key, value in parsed_seed.items():
                if value and not base.get(key):
                    base[key] = value
        base.update(payload)
        raw_input = json.dumps(payload, ensure_ascii=False)
    else:
        raw_text = str(input_text_or_json or "").strip()
        raw_input = raw_text
        pattern_source = raw_text
        if raw_text.startswith("{") and raw_text.endswith("}"):
            try:
                payload = json.loads(raw_text)
                return parse_json_or_text(payload)
            except Exception:
                pass
        base = matcher.parse_input_text(raw_text)

    raw = raw_input
    base["input"] = raw
    base["query_text"] = base.get("query_text") or raw
    base["listing_url"] = norm(base.get("listing_url") or base.get("url") or "")
    if not base.get("listing_id") and base.get("listing_reference"):
        base["listing_id"] = norm(base.get("listing_reference", ""))
    if not base.get("listing_reference") and base.get("listing_id"):
        base["listing_reference"] = norm(base.get("listing_id", ""))
    base["permit_number"] = norm(base.get("permit_number", ""))
    base["property_number"] = norm(base.get("property_number", ""))
    base["plot_number"] = norm(base.get("plot_number", ""))
    base["land_number"] = norm(base.get("land_number", ""))
    base["municipality_number"] = norm(base.get("municipality_number", ""))
    base["dewa_number"] = norm(base.get("dewa_number", ""))
    base["area"] = matcher.canonical_area(base.get("area", ""))
    base["project"] = matcher.canonical_project(base.get("project", ""))
    base["building"] = matcher.canonical_building(base.get("building", ""))
    base["unit"] = matcher.normalize_unit(base.get("unit", ""))
    base["bedrooms"] = matcher.canonical_bedrooms(base.get("bedrooms", ""))
    base["bathrooms"] = matcher.canonical_bedrooms(base.get("bathrooms", ""))
    if not base.get("size"):
        parsed_size = matcher.parse_size_value(pattern_source)
        base["size"] = f"{parsed_size} sqm" if parsed_size not in ("", None) else ""
    if not base.get("price"):
        parsed_price = matcher.parse_price_value(pattern_source)
        base["price"] = f"{parsed_price}" if parsed_price not in ("", None) else ""
    if not base.get("property_type"):
        base["property_type"] = matcher.canonical_property_type(pattern_source)
    if not base.get("agent_company"):
        base["agent_company"] = ""
    if not base.get("broker_reference"):
        m = BROKER_REF_RE.search(pattern_source)
        base["broker_reference"] = m.group(1) if m else ""
    if not base.get("floor"):
        m = FLOOR_RE.search(pattern_source)
        base["floor"] = m.group(1) if m else ""
    if not base.get("view"):
        m = VIEW_RE.search(pattern_source)
        base["view"] = m.group(1) if m else ""
    if (
        not any(base.get(key) for key in IDENTIFIER_KEYS)
        and not base.get("listing_url")
        and not base.get("area")
        and not base.get("project")
        and not base.get("building")
        and not base.get("unit")
        and looks_like_property_number_text(raw)
    ):
        base["property_number"] = norm(raw)
    if " / " in raw:
        parts = [norm(part) for part in raw.split("/") if norm(part)]
        if len(parts) >= 2:
            if not base.get("area"):
                base["area"] = matcher.canonical_area(parts[0])
            if not base.get("building"):
                base["building"] = matcher.canonical_building(parts[1])
            if len(parts) >= 3 and not base.get("unit"):
                unit_match = re.search(r"\bunit\s+([A-Za-z0-9-]+)\b", parts[2], re.I)
                if unit_match:
                    base["unit"] = matcher.normalize_unit(unit_match.group(1))
    if not base.get("unit"):
        unit_match = re.search(r"\bunit\s+([A-Za-z0-9-]+)\b", pattern_source, re.I)
        if unit_match:
            base["unit"] = matcher.normalize_unit(unit_match.group(1))
    if low(base.get("building", "")) in {"details", "detail", "finder"} or is_generic_entity(base.get("building", "")):
        base["building"] = ""
    if base.get("listing_url") and is_url_text(base["listing_url"]):
        for key in IDENTIFIER_KEYS:
            explicit_value = ""
            if isinstance(input_text_or_json, dict):
                explicit_value = norm(input_text_or_json.get(key, ""))
            if not explicit_value:
                base[key] = ""
    explicit_identifier_fields = any(
        isinstance(input_text_or_json, dict) and norm(input_text_or_json.get(key, ""))
        for key in IDENTIFIER_KEYS
    )
    explicit_listing_reference_fields = bool(
        isinstance(input_text_or_json, dict)
        and base.get("listing_url")
        and norm(input_text_or_json.get("listing_reference", "") or input_text_or_json.get("listing_id", ""))
        and not norm(input_text_or_json.get("bedrooms", ""))
        and not norm(input_text_or_json.get("size", ""))
        and not norm(input_text_or_json.get("price", ""))
    )
    if (is_pure_identifier_text(raw) and not any(base.get(key) for key in IDENTIFIER_KEYS)) or explicit_identifier_fields:
        base["bedrooms"] = ""
        base["bathrooms"] = ""
        base["size"] = ""
        base["price"] = ""
        base["building"] = ""
        base["project"] = ""
        base["property_type"] = ""
    if explicit_listing_reference_fields:
        base["bedrooms"] = ""
        base["bathrooms"] = ""
        base["size"] = ""
        base["price"] = ""
    return base


def is_conversational_building(value):
    tokens = matcher.tokenize(value)
    return bool(tokens) and any(token in CONVERSATIONAL_BUILDING_TOKENS for token in tokens[:3])


def is_ambiguous_search_request(query):
    raw = query.get("input", "")
    if not raw or not AMBIGUOUS_SEARCH_RE.search(raw):
        return False
    if any(query.get(key) for key in IDENTIFIER_KEYS):
        return False
    if query.get("listing_url") or query.get("unit") or query.get("size"):
        return False
    if query.get("project"):
        return False
    building = query.get("building", "")
    if building and not is_conversational_building(building):
        return False
    return True


def build_indexes(records):
    identifier_index = {key: defaultdict(list) for key in IDENTIFIER_KEYS}
    building_unit_index = defaultdict(list)
    all_urls = []

    for rec in records:
        for key in IDENTIFIER_KEYS:
            value = normalize_identifier(rec.get(key, ""))
            if value:
                identifier_index[key][value].append(rec)

        unit = matcher.normalize_unit(rec.get("unit", ""))
        area = matcher.canonical_area(rec.get("area", ""))
        if unit:
            for entity in candidate_entities(rec.get("building", ""), rec.get("project", "")):
                building_unit_index[(entity, unit)].append(rec)
                if area:
                    building_unit_index[(area, entity, unit)].append(rec)

        url = list_to_text_url(rec)
        if url:
            all_urls.append(url)

    return identifier_index, building_unit_index, all_urls


RECORDS = matcher.get_prepared_records()
RECORDS_BY_ID = defaultdict(list)
for _rec in RECORDS:
    RECORDS_BY_ID[_rec.get("resolver_record_id", "")].append(_rec)
IDENTIFIER_INDEX, BUILDING_UNIT_INDEX, KNOWN_URLS = build_indexes(RECORDS)


def row_key(rec):
    return "|".join(
        [
            rec.get("resolver_record_id", ""),
            rec.get("source_file", ""),
            rec.get("source_sheet", ""),
            rec.get("row_number", ""),
            list_to_text_url(rec),
            rec.get("area", ""),
            rec.get("project", ""),
            rec.get("building", ""),
            rec.get("unit", ""),
        ]
    )


def compute_matched_fields(query, rec):
    matched = []
    missing = []

    def check_exact(field, qv, rv):
        if not qv:
            return
        if qv and rv and low(qv) == low(rv):
            matched.append(field)
        else:
            missing.append(field)

    for key in IDENTIFIER_KEYS:
        check_exact(key, query.get(key, ""), rec.get(key, ""))

    check_exact("area", matcher.canonical_area(query.get("area", "")), matcher.canonical_area(rec.get("area", "")))
    check_exact("project", matcher.canonical_project(query.get("project", "")), matcher.canonical_project(rec.get("project", "")))
    check_exact("building", matcher.canonical_building(query.get("building", "")), matcher.canonical_building(rec.get("building", "")))
    check_exact("unit", matcher.normalize_unit(query.get("unit", "")), matcher.normalize_unit(rec.get("unit", "")))
    check_exact("bedrooms", matcher.canonical_bedrooms(query.get("bedrooms", "")), matcher.canonical_bedrooms(rec.get("bedrooms", "")))

    qsize = matcher.parse_size_value(query.get("size", ""))
    rsize = rec.get("canonical_size_sqm", "")
    if qsize not in ("", None):
        if rsize not in ("", None):
            try:
                diff = abs(float(qsize) - float(rsize)) / max(float(qsize), 1.0)
                if diff <= 0.05:
                    matched.append("size")
                else:
                    missing.append("size")
            except Exception:
                missing.append("size")
        else:
            missing.append("size")

    qprice = matcher.parse_price_value(query.get("price", ""))
    rprice = rec.get("canonical_price", "")
    if qprice not in ("", None):
        if rprice not in ("", None):
            try:
                diff = abs(float(qprice) - float(rprice)) / max(float(qprice), 1.0)
                if diff <= 0.10:
                    matched.append("price")
                else:
                    missing.append("price")
            except Exception:
                missing.append("price")
        else:
            missing.append("price")

    qstatus = set((query.get("status_tokens", "") or "").split())
    if qstatus:
        rstatus = set((rec.get("status_tokens", "") or "").split())
        if qstatus.intersection(rstatus):
            matched.append("status_tokens")
        else:
            missing.append("status_tokens")

    matched = sorted(set(filter(None, matched)))
    missing = sorted(set(filter(None, missing)))
    return matched, missing


def build_result_candidate(rec, score, query, match_type, breakdown):
    matched_fields, missing_fields = compute_matched_fields(query, rec)
    return {
        "resolver_record_id": rec.get("resolver_record_id", ""),
        "classification": classify_candidate(score, match_type),
        "confidence_score": score,
        "match_type": match_type,
        "matched_fields": matched_fields,
        "missing_fields": missing_fields,
        "source_record": {
            "source_file": rec.get("source_file", ""),
            "source_sheet": rec.get("source_sheet", ""),
            "row_number": rec.get("row_number", ""),
            "source_platform": rec.get("source_platform", ""),
            "listing_url": list_to_text_url(rec),
        },
        "record": {
            "area": rec.get("area", ""),
            "project": rec.get("project", ""),
            "building": rec.get("building", ""),
            "unit": rec.get("unit", ""),
            "bedrooms": rec.get("bedrooms", ""),
            "bathrooms": rec.get("bathrooms", ""),
            "size": rec.get("size", ""),
            "price": rec.get("price", ""),
            "permit_number": rec.get("permit_number", ""),
            "property_number": rec.get("property_number", ""),
            "plot_number": rec.get("plot_number", ""),
            "land_number": rec.get("land_number", ""),
            "municipality_number": rec.get("municipality_number", ""),
            "dewa_number": rec.get("dewa_number", ""),
            "owner_contact_available": "YES" if low(rec.get("owner_contact_available", "")) not in {"", "no"} else "NO",
        },
        "score_breakdown": breakdown,
    }


def classify_candidate(score, match_type):
    if match_type in {"exact_identifier", "exact_building_unit"} and score >= 90:
        return "EXACT"
    if score >= 80:
        return "LIKELY"
    if score >= 65:
        return "PARTIAL"
    return "UNRESOLVED"


def resolve_any_clue(input_text_or_json):
    query = parse_json_or_text(input_text_or_json)
    generic_identifier = ""
    if not any(query.get(key) for key in IDENTIFIER_KEYS):
        raw_ident = normalize_identifier(query.get("input", ""))
        if raw_ident and len(raw_ident) >= 4 and " " not in query.get("input", ""):
            generic_identifier = raw_ident

    def finalize(ranked):
        top = ranked[0]
        explanation = explain_missing(query, ranked)
        return {
            "input": query.get("input", ""),
            "parsed_clues": {k: query.get(k, "") for k in FIELD_ORDER if query.get(k, "")},
            "classification": top["classification"],
            "confidence_score": top["confidence_score"],
            "top_candidates": ranked,
            **explanation,
        }

    def exact_identifier_stage(keys, allow_generic=False):
        found = {}
        for key_name in keys:
            query_values = []
            qv = normalize_identifier(query.get(key_name, ""))
            if qv:
                query_values.append(qv)
            elif allow_generic and generic_identifier:
                query_values.append(generic_identifier)
            for qvalue in query_values:
                for rec in IDENTIFIER_INDEX[key_name].get(qvalue, []):
                    score = EXACT_IDENTIFIER_SCORES[key_name]
                    if query.get("area") and matcher.canonical_area(query.get("area", "")) == matcher.canonical_area(rec.get("area", "")):
                        score = min(100, score + 1)
                    if query.get("building") and matcher.canonical_building(query.get("building", "")) == matcher.canonical_building(rec.get("building", "")):
                        score = min(100, score + 1)
                    found[row_key(rec)] = build_result_candidate(rec, score, query, "exact_identifier", [f"{key_name}:exact"])
        return sorted(
            found.values(),
            key=lambda item: (item["confidence_score"], item["classification"], item["resolver_record_id"]),
            reverse=True,
        )[:5]

    ranked = exact_identifier_stage(["property_number"])
    if ranked:
        return finalize(ranked)

    found = {}
    unit = matcher.normalize_unit(query.get("unit", ""))
    area = matcher.canonical_area(query.get("area", ""))
    entities = candidate_entities(query.get("building", ""), query.get("project", ""))
    if entities and unit:
        exact_keys = []
        for entity in entities:
            if area:
                exact_keys.append((area, entity, unit))
            exact_keys.append((entity, unit))
        for idx_key in exact_keys:
            for rec in BUILDING_UNIT_INDEX.get(idx_key, []):
                score = 93
                if area and matcher.canonical_area(rec.get("area", "")) == area:
                    score += 2
                found[row_key(rec)] = build_result_candidate(rec, min(score, 100), query, "exact_building_unit", ["building+unit:exact"])
    if found:
        ranked = sorted(
            found.values(),
            key=lambda item: (item["confidence_score"], item["classification"], item["resolver_record_id"]),
            reverse=True,
        )[:5]
        return finalize(ranked)

    ranked = exact_identifier_stage(["permit_number"], allow_generic=True)
    if ranked:
        return finalize(ranked)

    ranked = exact_identifier_stage(["plot_number", "land_number", "municipality_number", "dewa_number"])
    if ranked:
        return finalize(ranked)

    for field_name in ("listing_url", "listing_id", "listing_reference"):
        bridge_ranked = collect_bridge_matches(query, field_name)
        if bridge_ranked:
            return finalize(bridge_ranked)

    bridge_ranked = collect_bridge_matches(query, "broker_reference")
    if bridge_ranked:
        return finalize(bridge_ranked)

    if is_ambiguous_search_request(query):
        return {
            "input": query.get("input", ""),
            "parsed_clues": {k: query.get(k, "") for k in FIELD_ORDER if query.get(k, "")},
            "classification": "UNRESOLVED",
            "confidence_score": 0,
            "top_candidates": [],
            **explain_missing(query, []),
        }

    found = {}
    similarity_input = " ".join(
        filter(
            None,
            [
                query.get("listing_url", ""),
                query.get("listing_id", ""),
                query.get("area", ""),
                query.get("project", ""),
                query.get("building", ""),
                query.get("unit", ""),
                query.get("property_type", ""),
                query.get("bedrooms", ""),
                query.get("size", ""),
                query.get("price", ""),
                query.get("broker_reference", ""),
                query.get("agent_company", ""),
                query.get("query_text", ""),
            ],
        )
    )
    similarity_result = matcher.resolve_listing_by_similarity(similarity_input or query.get("input", ""))
    for cand in similarity_result.get("candidates", []):
        rec_list = RECORDS_BY_ID.get(cand.get("resolver_record_id", ""), [])
        if not rec_list:
            continue
        rec = rec_list[0]
        score = int(cand.get("score", 0) or 0)
        try:
            breakdown = json.loads(cand.get("score_breakdown", "[]"))
        except Exception:
            breakdown = [cand.get("score_breakdown", "")]
        built = build_result_candidate(rec, score, query, "multi_signal", breakdown)
        current = found.get(row_key(rec))
        if not current or built["confidence_score"] > current["confidence_score"]:
            found[row_key(rec)] = built

    ranked = sorted(
        found.values(),
        key=lambda item: (item["confidence_score"], item["classification"], item["resolver_record_id"]),
        reverse=True,
    )[:5]
    if ranked:
        return {
            "input": query.get("input", ""),
            "parsed_clues": {k: query.get(k, "") for k in FIELD_ORDER if query.get(k, "")},
            "classification": ranked[0]["classification"],
            "confidence_score": ranked[0]["confidence_score"],
            "top_candidates": ranked,
            **explain_missing(query, ranked),
        }
    return {
        "input": query.get("input", ""),
        "parsed_clues": {k: query.get(k, "") for k in FIELD_ORDER if query.get(k, "")},
        "classification": "UNRESOLVED",
        "confidence_score": 0,
        "top_candidates": [],
        **explain_missing(query, []),
    }


def load_raw_text_queries():
    rows = []
    if not RAW_CHAT_CSV.exists():
        return rows
    with RAW_CHAT_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            text = norm(row.get("text", ""))
            if not text:
                continue
            if not any(token in low(text) for token in PROPERTY_TEXT_HINTS):
                continue
            parsed = matcher.parse_input_text(text)
            rows.append({"text": text, "parsed": parsed})
    return rows


def unique_by_key(items, key_fn, limit):
    out = []
    seen = set()
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def build_exact_identifier_tests(limit=20):
    pool = []
    for rec in RECORDS:
        for key in IDENTIFIER_KEYS:
            if rec.get(key):
                pool.append((key, rec))
                break
    selected = unique_by_key(pool, lambda item: (item[0], normalize_identifier(item[1].get(item[0], ""))), limit)
    tests = []
    for idx, (key, rec) in enumerate(selected, 1):
        tests.append(
            {
                "test_group": "exact_identifier",
                "test_name": f"exact_identifier_{idx:02d}",
                "input": json.dumps({key: rec.get(key, "")}, ensure_ascii=False),
                "expected_hint": key,
            }
        )
    return tests


def build_building_unit_tests(limit=20):
    pool = []
    for rec in RECORDS:
        entity = rec.get("building") or rec.get("project")
        if entity and rec.get("unit"):
            payload = {
                "area": rec.get("area", ""),
                "building": rec.get("building", "") or entity,
                "project": rec.get("project", ""),
                "unit": rec.get("unit", ""),
            }
            pool.append((json.dumps(payload, ensure_ascii=False), rec))
    selected = unique_by_key(pool, lambda item: low(item[0]), limit)
    return [
        {
            "test_group": "building_unit",
            "test_name": f"building_unit_{idx:02d}",
            "input": text,
            "expected_hint": "building+unit",
        }
        for idx, (text, _rec) in enumerate(selected, 1)
    ]


def build_multi_signal_tests(limit=20):
    base_rows = []
    for item in load_raw_text_queries():
        p = item["parsed"]
        if p.get("area") and p.get("building") and p.get("bedrooms") and p.get("size") and p.get("price"):
            base_rows.append(item)

    tests = []
    idx = 1
    for item in base_rows:
        p = item["parsed"]
        building = matcher.canonical_building(p.get("building", ""))
        if not building:
            continue
        size_val = matcher.parse_size_value(p.get("size", "")) or parse_numeric(p.get("size", ""))
        price_val = matcher.parse_price_value(p.get("price", "")) or parse_numeric(p.get("price", ""))
        if size_val in ("", None) or price_val in ("", None):
            continue
        bedrooms = p.get("bedrooms", "")
        area = p.get("area", "")
        status = p.get("status_tokens", "")
        exact_text = f"{area} / {building} / {bedrooms}BR / {size_val} sqm / AED {int(float(price_val))}"
        tests.append({"test_group": "multi_signal", "test_name": f"multi_signal_{idx:02d}", "input": exact_text, "expected_hint": "area+building+bedrooms+size+price"})
        idx += 1
        if len(tests) >= limit:
            return tests[:limit]
        tweaked_size = round(float(size_val) * 1.02, 2)
        tweaked_price = int(float(price_val) * 1.04)
        variant_text = f"{building} {area} {bedrooms} bed {tweaked_size} sqm asking AED {tweaked_price} {status}".strip()
        tests.append({"test_group": "multi_signal", "test_name": f"multi_signal_{idx:02d}", "input": variant_text, "expected_hint": "area+building+bedrooms+size+price"})
        idx += 1
        if len(tests) >= limit:
            return tests[:limit]
        relaxed_price = int(float(price_val) * 0.97)
        relaxed_text = f"{area} {building} {bedrooms}br size {round(float(size_val) * 0.99, 2)} sqm price {relaxed_price} {status}".strip()
        tests.append({"test_group": "multi_signal", "test_name": f"multi_signal_{idx:02d}", "input": relaxed_text, "expected_hint": "area+building+bedrooms+size+price"})
        idx += 1
        if len(tests) >= limit:
            return tests[:limit]

    return tests[:limit]


def build_noisy_description_tests(limit=20):
    pool = [item["text"] for item in load_raw_text_queries()]
    selected = unique_by_key(pool, lambda text: low(text), limit)
    return [
        {
            "test_group": "noisy_description",
            "test_name": f"noisy_description_{idx:02d}",
            "input": text,
            "expected_hint": "description_text",
        }
        for idx, text in enumerate(selected, 1)
    ]


def build_live_listing_tests(limit=20):
    urls = []
    if BENCHMARK_CSV.exists():
        with BENCHMARK_CSV.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                url = norm(row.get("url", ""))
                if url:
                    urls.append(url)
    if len(urls) < limit:
        urls.extend(KNOWN_URLS)
    selected = unique_by_key(urls, lambda url: low(url), limit)
    return [
        {
            "test_group": "live_listing_detail",
            "test_name": f"live_listing_detail_{idx:02d}",
            "input": url,
            "expected_hint": "listing_url",
        }
        for idx, url in enumerate(selected, 1)
    ]


def run_tests():
    tests = []
    tests.extend(build_exact_identifier_tests(20))
    tests.extend(build_building_unit_tests(20))
    tests.extend(build_multi_signal_tests(20))
    tests.extend(build_noisy_description_tests(20))
    tests.extend(build_live_listing_tests(20))

    results = []
    group_stats = defaultdict(Counter)

    for test in tests:
        result = resolve_any_clue(test["input"])
        top = result["top_candidates"][0] if result["top_candidates"] else {}
        row = {
            "test_group": test["test_group"],
            "test_name": test["test_name"],
            "input": test["input"],
            "expected_hint": test["expected_hint"],
            "classification": result["classification"],
            "confidence_score": result["confidence_score"],
            "top_resolver_record_id": top.get("resolver_record_id", ""),
            "top_match_type": top.get("match_type", ""),
            "top_area": (top.get("record") or {}).get("area", ""),
            "top_project": (top.get("record") or {}).get("project", ""),
            "top_building": (top.get("record") or {}).get("building", ""),
            "top_unit": (top.get("record") or {}).get("unit", ""),
            "top_bedrooms": (top.get("record") or {}).get("bedrooms", ""),
            "top_size": (top.get("record") or {}).get("size", ""),
            "top_price": (top.get("record") or {}).get("price", ""),
            "owner_contact_available": (top.get("record") or {}).get("owner_contact_available", "NO"),
            "matched_fields": "|".join(top.get("matched_fields", [])),
            "missing_fields": "|".join(top.get("missing_fields", [])),
            "source_file": ((top.get("source_record") or {}).get("source_file", "")),
            "source_sheet": ((top.get("source_record") or {}).get("source_sheet", "")),
            "row_number": ((top.get("source_record") or {}).get("row_number", "")),
        }
        results.append(row)
        group_stats[test["test_group"]][result["classification"]] += 1

    with OUT_TESTS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    overall = Counter(row["classification"] for row in results)
    conf_dist = Counter()
    for row in results:
        score = int(row["confidence_score"] or 0)
        if score >= 90:
            conf_dist["90_plus"] += 1
        elif score >= 80:
            conf_dist["80_89"] += 1
        elif score >= 65:
            conf_dist["65_79"] += 1
        else:
            conf_dist["below_65"] += 1

    def group_strength(counter):
        return (counter["EXACT"] * 3) + (counter["LIKELY"] * 2) + counter["PARTIAL"]

    strongest = max(group_stats.items(), key=lambda item: group_strength(item[1]))[0] if group_stats else ""
    weakest = min(group_stats.items(), key=lambda item: group_strength(item[1]))[0] if group_stats else ""

    lines = [
        "# Final Unit Finder Report",
        "",
        f"- total_tests: {len(results)}",
        f"- exact_matches: {overall['EXACT']}",
        f"- likely_matches: {overall['LIKELY']}",
        f"- partial_matches: {overall['PARTIAL']}",
        f"- unresolved: {overall['UNRESOLVED']}",
        "",
        "## Confidence distribution",
        f"- 90_plus: {conf_dist['90_plus']}",
        f"- 80_89: {conf_dist['80_89']}",
        f"- 65_79: {conf_dist['65_79']}",
        f"- below_65: {conf_dist['below_65']}",
        "",
        f"- strongest_successful_input_type: `{strongest}`",
        f"- weakest_input_type: `{weakest}`",
        "",
        "## Group breakdown",
    ]

    for group in ["exact_identifier", "building_unit", "multi_signal", "noisy_description", "live_listing_detail"]:
        stat = group_stats[group]
        lines.append(
            f"- {group}: EXACT={stat['EXACT']} LIKELY={stat['LIKELY']} PARTIAL={stat['PARTIAL']} UNRESOLVED={stat['UNRESOLVED']}"
        )

    lines.extend(
        [
            "",
            "## Evidence",
            f"- tests_csv: `{OUT_TESTS}`",
            f"- report_md: `{OUT_REPORT}`",
        ]
    )
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "exact_matches": overall["EXACT"],
        "likely_matches": overall["LIKELY"],
        "partial_matches": overall["PARTIAL"],
        "unresolved": overall["UNRESOLVED"],
        "strongest_successful_input_type": strongest,
        "weakest_input_type": weakest,
        "tests_csv": str(OUT_TESTS),
        "report_md": str(OUT_REPORT),
    }


if __name__ == "__main__":
    summary = run_tests()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
