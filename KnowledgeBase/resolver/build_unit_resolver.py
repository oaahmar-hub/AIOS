#!/usr/bin/env python3
import csv
import hashlib
import io
import json
import logging
import os
import random
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from contextlib import redirect_stderr
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
RAW = KB / "raw_data"
ORG = KB / "organized_master"
ACQ = KB / "acquisition_index.csv"
OUT = KB / "resolver"
WHATSAPP_DB = Path("/Users/hassanka/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite")

IDENTITY_CSV = OUT / "listing_identity_map.csv"
IDENTITY_JSON = OUT / "listing_identity_map.json"
INDEX_CSV = OUT / "unit_resolver_index.csv"
DB_PATH = OUT / "unit_resolver_database.sqlite"
REPORT = OUT / "resolver_test_report.md"
UNRESOLVED_CSV = OUT / "unresolved_records_review.csv"
AREA_ALIAS_PATH = OUT / "area_aliases.json"
PROJECT_ALIAS_PATH = OUT / "project_aliases.json"
BUILDING_ALIAS_PATH = OUT / "building_aliases.json"
DEVELOPER_ALIAS_PATH = OUT / "developer_aliases.json"
UNRESOLVED_GROUPS_CSV = OUT / "unresolved_failure_groups.csv"
UNIT_COMPLETION_EVIDENCE_CSV = OUT / "unit_completion_merge_evidence.csv"

URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)[^\s\"'<>)]+", re.I)
PLATFORM_RE = re.compile(r"(propertyfinder\.ae|bayut\.com|dubizzle\.com)", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?971|00971|0)?[\s-]?(?:5\d|2|3|4|6|7|9)[\s-]?\d{3}[\s-]?\d{4}")

NUMBER_PATTERNS = {
    "permit_number": [
        r"(?:permit|rera|trakheesi|advertisement permit|brn|orn)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{4,40})",
        r"\b(?:permit)\s*([0-9]{5,20})\b",
    ],
    "property_number": [
        r"(?:property|property no|property number|property id)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{3,40})",
        r"\b(?:prop(?:erty)?)[\s_-]?([0-9]{3,20})\b",
    ],
    "plot_number": [
        r"(?:plot|plot no|plot number)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
    "land_number": [
        r"(?:land|land no|land number)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
    "municipality_number": [
        r"(?:municipality|municipality no|municipality number|dm no)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
    "dewa_number": [
        r"(?:dewa|dewa premise|premise)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
}

AREA_ALIAS_HINTS = {
    "JVC": ["jvc", "jumeirah village circle"],
    "JVT": ["jvt", "jumeirah village triangle"],
    "Meydan": ["meydan", "midan", "maidan"],
    "MBR City": ["mbr city", "mbr", "mohammed bin rashid"],
    "Al Furjan": ["al furjan", "furjan"],
    "Creek Harbour": ["creek harbour", "dubai creek harbour"],
    "Palm Jumeirah": ["palm jumeirah", "palm", "pj-p-vp"],
    "Dubai Marina": ["dubai marina", "marina"],
    "Business Bay": ["business bay", "bussiness bay"],
    "Downtown": ["downtown", "downtown dubai"],
    "Dubai Hills": ["dubai hills", "dubai hills estate"],
    "Dubai Land": ["dubailand", "dubai land"],
    "Dubai South": ["dubai south"],
    "Arjan": ["arjan"],
    "JLT": ["jlt", "jumeirah lake towers"],
    "JBR": ["jbr", "jumeirah beach residence"],
    "Yas Island": ["yas island"],
    "Saadiyat": ["saadiyat"],
    "Reem Island": ["reem island", "al reem"],
    "Al Raha": ["al raha"],
    "Port De La Mer": ["port de la mer", "la mer"],
    "Abu Dhabi": ["abu dhabi"],
    "Sharjah": ["sharjah"],
    "Ajman": ["ajman"],
    "Ras Al Khaimah": ["ras al khaimah", "rak"],
}

PROJECT_ALIAS_HINTS = {
    "Jumeirah Village Circle": ["jvc", "jumeirah village circle"],
    "Jumeirah Village Triangle": ["jvt", "jumeirah village triangle"],
    "Meydan": ["meydan", "midan", "maidan"],
    "Dubai Hills Estate": ["dubai hills", "dubai hills estate"],
    "Business Bay": ["business bay", "bussiness bay"],
    "Downtown Dubai": ["downtown", "downtown dubai"],
    "Palm Jumeirah": ["palm", "palm jumeirah"],
    "Dubai Marina": ["dubai marina", "marina"],
    "Dubai South": ["dubai south"],
    "JLT": ["jlt", "jumeirah lake towers"],
    "JBR": ["jbr", "jumeirah beach residence"],
    "MBR City": ["mbr city", "mbr", "mohammed bin rashid city"],
}

BUILDING_ALIAS_HINTS = {
    "Tower": ["tower", "twr"],
    "Building": ["building", "bldg"],
}

DEVELOPER_ALIAS_HINTS = {
    "Object 1": ["object1", "object 1"],
    "Emaar": ["emaar", "emar"],
    "Damac": ["damac"],
    "Nakheel": ["nakheel"],
    "Sobha": ["sobha"],
    "Aldar": ["aldar"],
    "Reportage": ["reportage"],
    "Binghatti": ["binghatti"],
    "Deyaar": ["deyaar", "deyar"],
    "Tiger": ["tiger"],
    "Meraas": ["meraas"],
    "Select Group": ["select group", "selectgroup"],
    "London Gate": ["london gate"],
    "Azizi": ["azizi"],
    "Danube": ["danube"],
    "HSH": ["hsh"],
    "Imtiaz": ["imtiaz"],
    "Samana": ["samana"],
    "Leos": ["leos"],
    "Omniyat": ["omniyat"],
}

DEVELOPERS = [
    "Emaar", "Damac", "Sobha", "Nakheel", "Aldar", "Reportage", "Binghatti",
    "Deyaar", "Azizi", "Danube", "Tiger", "Object1", "Ellington", "Meraas",
    "Select Group", "Omniyat", "London Gate", "Leos", "Samana", "Imtiaz",
    "HSH", "Mag", "Dubai Holding",
]

DEVELOPER_ALIASES = sorted({*DEVELOPERS, *DEVELOPER_ALIAS_HINTS.keys()})

NUMERIC_TOKEN_NOISE = {
    "area", "use", "details", "property", "land", "department", "allowed", "info",
    "registration", "service", "financial", "map", "scape", "stamp", "useratio", "services",
    "title", "unit", "building", "project", "developer", "plot", "per", "avg", "rate",
}

COMMON_UNIT_NOISE = {"na", "n/a", "none", "null", "-", "--", "nil"}


def normalize_identifier(value):
    cleaned = re.sub(r"\s+", "", norm(value).lower())
    return re.sub(r"[^a-z0-9]", "", cleaned)

MAX_ROWS_PER_SHEET = 2500
MAX_XLSX_FILES = 200
MAX_PDF_TEXT_FILES = 80
PRIORITY_TERMS = [
    "inventory", "data", "uae", "pak", "hsh", "binghatti", "deyaar", "tiger",
    "object", "reportage", "jvc", "unit", "property", "master_inventory_index",
]
PDF_RELEVANCE_TERMS = [
    "permit", "property", "plot", "land", "unit", "title deed", "contract",
    "floor", "sadaf", "tiger", "nakheel", "palm", "dld", "rera", "dewa",
]

HEADER_MAP = {
    "area": ["area", "community", "location", "district", "neighborhood", "region", "city", "area name"],
    "project": ["project", "project name", "development", "property", "property name", "projectname", "community", "project code"],
    "building": ["building", "building name", "tower", "tower name", "block", "block name"],
    "unit": ["unit", "unit no", "unit number", "property no", "apartment", "villa no", "flat", "unit no.", "no. of unit", "no of unit", "number of unit", "unit no of", "unit number of"],
    "size": ["size", "sqft", "sq.ft", "bua", "plot size", "built up area", "built-up area", "sqm"],
    "bedrooms": ["bed", "beds", "bedroom", "bedrooms", "br", "studio"],
    "price": ["price", "selling price", "sale price", "rent", "amount", "value"],
    "developer": ["developer", "brand", "master developer"],
    "owner": ["owner", "owner name", "landlord", "seller", "client name", "contact name", "name"],
    "mobile": ["mobile", "phone", "telephone", "contact", "contact no", "phone number", "whatsapp"],
    "email": ["email", "e-mail", "mail"],
    "permit_number": ["permit", "permit number", "rera", "trakheesi permit", "advertisement permit"],
    "property_number": ["property number", "property no", "property id"],
    "plot_number": ["plot", "plot number", "plot no"],
    "land_number": ["land", "land number", "land no"],
    "municipality_number": ["municipality", "municipality number", "municipality no"],
    "dewa_number": ["dewa", "dewa number", "premise", "premise number"],
    "url": ["url", "link", "property finder link", "bayut link", "dubizzle link"],
}


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").replace("-", " ")).strip()


def low(value):
    return norm(value).lower()


def canonical_area(text):
    t = f" {low(text)} "
    for canon, aliases in AREA_ALIAS_HINTS.items():
        for alias in aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", t):
                return canon
    return norm(text)[:120]


def detect_developer(text):
    t = f" {low(text)} "
    for dev in DEVELOPER_ALIASES:
        if re.search(rf"(?<![a-z0-9]){re.escape(dev.lower())}(?![a-z0-9])", t):
            return dev
    return ""


def canonical_developer(text):
    return detect_developer(text)


def canonical_project(text):
    t = f" {low(text)} "
    for canon, aliases in PROJECT_ALIAS_HINTS.items():
        for alias in aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", t):
                return canon
    return norm(text)[:160]


def canonical_project_from_text(text):
    """Best-effort project extraction from URL slug-like text."""
    cleaned = low(text)
    if not cleaned:
        return ""
    for canon, aliases in PROJECT_ALIAS_HINTS.items():
        for alias in aliases:
            if alias in cleaned:
                return canon
    return ""


def canonical_area_from_text(text):
    cleaned = low(text)
    if not cleaned:
        return ""
    for canon, aliases in AREA_ALIAS_HINTS.items():
        for alias in aliases:
            if alias in cleaned:
                return canon
    return ""


def canonical_building(text):
    t = f" {low(text)} "
    for canon, aliases in BUILDING_ALIAS_HINTS.items():
        for alias in aliases:
            if alias in t:
                return canon if canon in {norm(text), norm(text).lower()} else norm(text)
    return norm(text)[:200]


def split_compound_unit(value):
    text = low(norm(value))
    if not text:
        return "", ""
    m = re.search(r"^([a-z0-9\'&\-\s]{1,80}?)[-\s]+([a-z0-9]{1,10}(?:-[0-9]{1,8}(?:-[0-9]{1,4})?)+)$", text)
    if m:
        return canonical_building(norm(m.group(1))), norm(m.group(2)).replace(" ", "")
    m = re.search(r"^([a-z0-9&'\- ]{1,60}?)\s*-\s*([0-9]{1,10}(?:-[0-9]{1,4})?)$", text)
    if m:
        return canonical_building(norm(m.group(1))), norm(m.group(2)).replace(" ", "")
    return "", ""


def canonical_bedrooms(raw):
    if not raw:
        return ""
    text = low(raw)
    if "studio" in text:
        return "studio"
    m = re.search(r"\b(\d+)\s*(?:br|bed|beds|bedroom|bedrooms)\b", text)
    if m:
        return m.group(1)
    return re.sub(r"\s+", " ", text).strip()[:20]


def normalize_unit(raw):
    if not raw:
        return ""
    text = norm(raw)
    if low(text) in COMMON_UNIT_NOISE:
        return ""
    m = re.search(r"\b(?:unit|apt|apartment|villa|flat)\s*(?:no\.?|number|#)?\s*([a-z0-9]+)\b", low(text))
    if m:
        return m.group(1).upper()
    return re.sub(r"[^a-zA-Z0-9-]", "", text).strip("-")[:80]


def normalize_size(text):
    if not text:
        return ""
    cleaned = norm(text).replace(",", "")
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(sqm|sqft|sq\.?m|m2|m²)", low(cleaned))
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        if "sqf" in unit or "sqft" in unit:
            value = round(value * 0.092903, 2)
        else:
            value = round(value, 2)
        return f"{value:.2f} sqm"
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m:
        return m.group(1)
    return cleaned[:80]


def is_noise_number(value):
    return low(value) in NUMERIC_TOKEN_NOISE


NOISE_IDENTIFIER_TEXT = {
    "finder", "listing", "agent", "report", "campaigns", "type", "hand over", "handover", "holding",
    "recommendation", "owner", "owners", "studio", "villa", "apartment", "of", "and", "certified", "data",
    "quick", "reference", "holding", "property number", "and", "ownership", "declaration"
}


def is_value_identifier_noise(key, value):
    if not value:
        return True
    v = low(value)
    if v in NOISE_IDENTIFIER_TEXT:
        return True
    if key in {"property_number", "permit_number", "plot_number", "land_number", "municipality_number", "dewa_number"}:
        if len(v) < 3:
            return True
        if not any(ch.isdigit() for ch in v) and len(v) < 6:
            return True
    return False


def header_key(value):
    h = re.sub(r"[^a-z0-9]+", " ", low(value)).strip()
    for key, aliases in HEADER_MAP.items():
        if h in aliases:
            return key
    return ""


def detect_header(row):
    mapped = {}
    for i, v in enumerate(row):
        key = header_key(v)
        if key and key not in mapped:
            mapped[key] = i
    useful = set(mapped) & {"area", "project", "building", "unit", "size", "bedrooms", "price", "permit_number", "property_number", "plot_number", "url"}
    return mapped if len(useful) >= 2 else {}


def cell(row, mapping, key):
    idx = mapping.get(key)
    if idx is None or idx >= len(row):
        return ""
    return norm(row[idx])[:500]


def parse_building_unit_fallback(text):
    t = f" {low(text)} "
    unit = ""
    building = ""
    compound_building, compound_unit = split_compound_unit(text)
    if compound_unit:
        unit = compound_unit
    if compound_building:
        building = compound_building
    m_unit = re.search(r"\b(?:flat|apartment|unit|villa|studio|terrace)\s*(?:no\.?|number|#)?\s*([0-9]{1,6}[a-z]?)\b", t)
    if m_unit:
        unit = m_unit.group(1).upper()
    m_building = re.search(r"\b([a-z0-9][a-z0-9\s&'\-]*?(?:tower|tower\s*\d+|building|block))\s+[0-9]{0,4}\b", t)
    if m_building:
        building = norm(m_building.group(1).replace("  ", " "))
    m_alt = re.search(r"\b([a-z]{2,}\s+tower)\s+([0-9]{1,6})\b", t)
    if m_alt:
        alt_building = norm(f"{m_alt.group(1)} {m_alt.group(2)}")
        if len(alt_building) > len(building):
            building = alt_building
    if not building:
        m_inline = re.search(r"\b([a-z0-9][a-z0-9\s&'\-]{0,50}?)(?:\s+([0-9]{1,6}[a-z]?(?:-[0-9]{1,3})?))\s+(?:apartment|flat|studio|unit)\b", t)
        if m_inline:
            if m_inline.group(1).strip():
                building = norm(m_inline.group(1))
            if not unit and m_inline.group(2):
                unit = m_inline.group(2).upper()
    if not unit:
        m_trailing = re.search(r"\b(?:^|[\s-])(?:\d+[a-z]?(?:-\d{1,3})?)\s+[a-z0-9 ]+(?:tower|building|block)\b", t)
        if m_trailing:
            m_alt_unit = re.search(r"(\d+[a-z]?(?:-\d{1,3})?)", m_trailing.group(0))
            if m_alt_unit:
                unit = m_alt_unit.group(1).upper()
    if not building:
        m_tower = re.search(r"\b([a-z0-9\s&'\-]{1,70}tower\s*[0-9]{0,4}[a-z]?)\b", t)
        if m_tower and re.search(r"\b(apt|apartment|unit|flat|villa)\b", t):
            building = norm(m_tower.group(1))
    return canonical_building(building), unit


def infer_building_unit_from_context(text, project="", unit=""):
    t = low(text)
    found_building = ""
    found_unit = ""

    if not t:
        return found_building, found_unit

    if project:
        p = low(project)
        p_re = re.escape(p)
        m_project = re.search(rf"(?<![a-z0-9]){p_re}\s+(?:v|tower|building|block)?\s*([0-9]{{1,6}}[a-z]?)\b", t)
        if m_project:
            found_building = p
            found_unit = m_project.group(1)
        m_project_compact = re.search(rf"(?<![a-z0-9]){p_re}(?:[\\-/\\s]*|[a-z]{0,2})?\s*(?:v|tower|building|block)?[\\s\\-/]*([0-9]{{1,6}}[a-z]?)\b", t)
        if m_project_compact and m_project_compact.group(1):
            found_building = p
            found_unit = m_project_compact.group(1)

        if unit:
            u = low(unit)
            u_compact = re.sub(r"[^a-z0-9]", "", u)
            p_compact = re.sub(r"[^a-z0-9]", "", p)
            if p_compact and p_compact in u_compact:
                tail = u_compact.split(p_compact, 1)[1]
                tail = re.sub(r"^(?:v|tower|t|b|bl|building|block)?", "", tail)
                if re.fullmatch(r"[0-9]{1,6}[a-z]?", tail):
                    found_building = p
                    found_unit = tail

    if not found_building:
        m = re.search(r"\b([a-z][a-z0-9&'\-\\s]{2,})\s+v\s*([0-9]{1,6}[a-z]?)\b", t)
        if m:
            found_building, found_unit = m.group(1).strip(), m.group(2)
        m = re.search(r"\b([a-z][a-z0-9&'\-\\s]{2,})\s+(?:tower|building|block)\s*([0-9]{1,8}[a-z]?)\b", t)
        if m and not found_building:
            found_building, found_unit = m.group(1).strip(), m.group(2)

    if not found_unit and unit:
        m_tail = re.search(r"([0-9]{1,6}[a-z]?)$", re.sub(r"[^a-z0-9]", "", low(unit)))
        if m_tail:
            found_unit = m_tail.group(1)

    if project and not found_building and found_unit:
        found_building = project

    return canonical_building(found_building), normalize_unit(found_unit)


def normalize_record_fields(rec):
    rec["area"] = canonical_area(rec.get("area", ""))
    if rec.get("project"):
        rec["project"] = canonical_project(rec["project"])
    if rec.get("building"):
        rec["building"] = canonical_building(rec["building"])
    rec["unit"] = normalize_unit(rec.get("unit", ""))
    rec["bedrooms"] = canonical_bedrooms(rec.get("bedrooms", ""))
    rec["size"] = normalize_size(rec.get("size", ""))
    rec["developer"] = canonical_developer(rec.get("developer", ""))
    for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]:
        if rec.get(key):
            rec[key] = norm(rec[key])[:60]
            rec[f"match_key_{key}"] = normalize_identifier(rec[key])
        else:
            rec[f"match_key_{key}"] = ""
    return rec


def merge_record_groups(records):
    out_records = [dict(r) for r in records]
    out_by_id = {r.get("resolver_record_id", str(i)): r for i, r in enumerate(out_records)}
    evidence = []
    changed = True
    for _ in range(6):
        if not changed:
            break
        changed = False
        key_indices = defaultdict(list)
        for r in out_records:
            for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number", "listing_id"]:
                if r.get(key):
                    if key == "listing_id":
                        idx_key = low(r[key])
                    else:
                        idx_key = r.get(f"match_key_{key}") or normalize_identifier(r[key])
                    key_indices[(key, idx_key)].append(r)
            if r.get("area") and r.get("project"):
                area_proj_key = ("area_project", canonical_area(r.get("area", "")), canonical_project(r.get("project", "")))
                key_indices[area_proj_key].append(r)
                key_indices[("source_file", r.get("source_file", ""))].append(r)
                key_indices[("source_file_area_project", r.get("source_file", ""), canonical_area(r.get("area", "")), canonical_project(r.get("project", "")))].append(r)
            if r.get("source_file") and (r.get("building") or r.get("unit") or r.get("project") or r.get("area")):
                key_indices[("source_file_project_building_unit", r.get("source_file", ""), canonical_project(r.get("project", "")), canonical_building(r.get("building", "")), r.get("unit", ""))].append(r)

        for key, group in list(key_indices.items()):
            if len(group) < 2:
                continue
            agg = {}
            for field in [
                "area",
                "project",
                "building",
                "unit",
                "size",
                "bedrooms",
                "developer",
                "permit_number",
                "property_number",
                "plot_number",
                "land_number",
                "municipality_number",
                "dewa_number",
                "listing_id",
                "listing_url",
            ]:
                values = [g.get(field, "") for g in group if g.get(field)]
                if values:
                    agg[field] = Counter(values).most_common(1)[0][0]
            if not agg:
                continue
            for source_rec in group:
                rid = source_rec.get("resolver_record_id")
                rec = out_by_id.get(rid)
                if rec is None:
                    continue
                filled = []
                for field in [
                    "area",
                    "project",
                    "building",
                    "unit",
                    "size",
                    "bedrooms",
                    "developer",
                    "permit_number",
                    "property_number",
                    "plot_number",
                    "land_number",
                    "municipality_number",
                    "dewa_number",
                    "listing_id",
                    "listing_url",
                ]:
                    if not rec.get(field) and agg.get(field):
                        rec[field] = agg[field]
                        if field in {"building", "unit"}:
                            filled.append(field)
                        if field in {"permit_number", "property_number", "plot_number", "land_number"}:
                            filled.append(field)
                        if field in {"listing_id", "listing_url"}:
                            filled.append(field)
                if filled:
                    changed = True
                    base_basis = rec.get("match_basis", "")
                    rec["match_basis"] = f"{base_basis};cross_record_merge_{key[0]}" if base_basis else f"cross_record_merge_{key[0]}"
                    rec["confidence_score"] = str(max(int(rec.get("confidence_score", 0) or 0), 91))
                    evidence.append({
                        "source_file": rec.get("source_file", ""),
                        "merge_key": str(key),
                        "filled_fields": ",".join(sorted(set(filled))),
                        "target_resolver_record_id": rec.get("resolver_record_id", ""),
                    })
    return out_records, evidence


def enrich_records_from_reference(records):
    records, unit_completion_evidence = merge_record_groups([dict(r) for r in records])

    complete = [r for r in records if r.get("building") and r.get("unit")]
    source_complete_index = defaultdict(list)
    all_key_indices = defaultdict(list)

    for r in records:
        sf = r.get("source_file", "")
        if sf and r.get("building") and r.get("unit"):
            source_complete_index[(sf, "building")].append(r)
            if r.get("area"):
                source_complete_index[(sf, "area", canonical_area(r["area"]))].append(r)
            if r.get("project"):
                source_complete_index[(sf, "project", canonical_project(r["project"]))].append(r)
            for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]:
                idx = r.get(f"match_key_{key}", "")
                if idx:
                    source_complete_index[(sf, key.split("_")[0], idx)].append(r)

        for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]:
            idx = r.get(f"match_key_{key}", "")
            if idx:
                all_key_indices[(key, idx)].append(r)
        if r.get("listing_id"):
            all_key_indices[("listing_id", low(r["listing_id"]) )].append(r)
        if r.get("area") and r.get("project"):
            all_key_indices[("area_project", canonical_area(r.get("area", "")), canonical_project(r.get("project", "")))].append(r)
        if sf and (r.get("area") or r.get("project") or r.get("building") or r.get("unit")):
            all_key_indices[("source_file_context", sf, canonical_area(r.get("area", "")), canonical_project(r.get("project", "")))].append(r)

    key_indices = defaultdict(list)
    for r in complete:
        for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number", "listing_id"]:
            if r.get(key):
                if key == "listing_id":
                    key_indices[(key, low(r[key]))].append(r)
                else:
                    key_indices[(key, r.get(f"match_key_{key}", normalize_identifier(r[key])) )].append(r)
        if r.get("area") and r.get("project"):
            key_indices[("area_project", canonical_area(r.get("area", "")), canonical_project(r.get("project", "")))].append(r)

    def best_unit_match(candidates, rec):
        scored = []
        for c in candidates:
            if not (c.get("building") and c.get("unit")):
                continue
            score = 0
            if c.get("source_file") == rec.get("source_file"):
                score += 40
            if rec.get("area") and c.get("area") and canonical_area(rec["area"]) == canonical_area(c["area"]):
                score += 15
            if rec.get("project") and c.get("project") and canonical_project(rec["project"]) == canonical_project(c["project"]):
                score += 15
            if c.get("developer") and rec.get("developer") and c.get("developer") == rec.get("developer"):
                score += 5
            if c.get("confidence_score"):
                score += int(float(c.get("confidence_score", "0")) > 88) * 10
            scored.append((score, c))
        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[0][1] if scored else None

    out = []
    for rec in records:
        if rec.get("building") and rec.get("unit"):
            out.append(rec)
            continue

        missing_fields = []
        if not rec.get("building"):
            missing_fields.append("building")
        if not rec.get("unit"):
            missing_fields.append("unit")

        matched = None
        match_basis = ""
        match_conf = int(rec.get("confidence_score") or 0)

        # 1) exact ids against complete records
        for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number", "listing_id"]:
            if not rec.get(key):
                continue
            idx = low(rec[key]) if key == "listing_id" else rec.get(f"match_key_{key}")
            if not idx:
                continue
            candidates = key_indices.get((key, idx), [])
            if candidates:
                best = best_unit_match(candidates, rec)
                if best:
                    matched = best
                    match_basis = f"exact_{key}_unit_fill"
                    match_conf = max(match_conf, 95)
                    break

        # 2) same source-file and identifier (even if incomplete source had id)
        if not matched:
            sf = rec.get("source_file", "")
            if sf:
                for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]:
                    val = rec.get(key, "")
                    idx = rec.get(f"match_key_{key}", normalize_identifier(val))
                    if val:
                        by_source = source_complete_index.get((sf, key.split("_")[0], idx), [])
                        if by_source:
                            candidate = best_unit_match(by_source, rec)
                            if candidate:
                                matched = candidate
                                match_basis = f"source_file_{key}_unit_fill"
                                match_conf = max(match_conf, 92)
                                break

        # 3) area/project context merge from any source records
        if not matched and rec.get("area") and rec.get("project"):
            candidates = key_indices.get(("area_project", canonical_area(rec["area"]), canonical_project(rec["project"])), [])
            if candidates:
                candidate = best_unit_match(candidates, rec)
                if candidate:
                    matched = candidate
                    match_basis = "area_project_unit_fill"
                    match_conf = max(match_conf, 84)

        # 4) same source context fallback
        if not matched and rec.get("source_file") and (rec.get("area") or rec.get("project") or rec.get("developer")):
            sf = rec.get("source_file", "")
            candidates = all_key_indices.get(("source_file_context", sf, canonical_area(rec.get("area", "")), canonical_project(rec.get("project", ""))), [])
            candidate = best_unit_match(candidates, rec)
            if candidate:
                matched = candidate
                match_basis = "source_file_context_unit_fill"
                match_conf = max(match_conf, 85)

        # 5) fuzzy area/project/size/bedrooms match
        if matched is None and rec.get("area") and rec.get("project") and (rec.get("size") or rec.get("bedrooms")):
            target_area = low(rec["area"])
            target_project = low(rec["project"])
            target_size = rec.get("size", "")
            target_bed = rec.get("bedrooms", "")
            best = None
            best_score = 0.0
            for r in complete:
                if not r.get("area") or not r.get("project"):
                    continue
                score = 0.0
                score += SequenceMatcher(None, target_area, low(r.get("area", ""))).ratio() * 40
                score += SequenceMatcher(None, target_project, low(r.get("project", ""))).ratio() * 35
                if target_size and r.get("size"):
                    score += SequenceMatcher(None, target_size, low(r.get("size", ""))).ratio() * 15
                if target_bed and r.get("bedrooms"):
                    score += SequenceMatcher(None, target_bed, low(r.get("bedrooms", ""))).ratio() * 10
                if score > best_score and score >= 58:
                    best = r
                    best_score = score
            if best:
                matched = best
                match_basis = "area_project_size_bedrooms_unit_fill"
                match_conf = max(match_conf, 78)

        if not matched:
            out.append(rec)
            continue

        for field in ["area", "project", "building", "unit", "size", "bedrooms", "developer"]:
            if (field in missing_fields) or not rec.get(field):
                rec[field] = matched.get(field, rec.get(field, ""))
        if matched.get("source_file"):
            rec["source_file"] = matched.get("source_file")
        if matched.get("source_row"):
            rec["source_row"] = matched.get("source_row")
        rec["match_basis"] = match_basis
        rec["confidence_score"] = str(max(match_conf, int(rec.get("confidence_score") or 0)))
        out.append(rec)

    return out, unit_completion_evidence


def build_alias_files(records):
    area_map = defaultdict(set)
    project_map = defaultdict(set)
    building_map = defaultdict(set)
    developer_map = defaultdict(set)
    for r in records:
        if r.get("area"):
            area_map[canonical_area(r["area"])].add(low(r["area"]))
        if r.get("project"):
            project_map[canonical_project(r["project"])].add(low(r["project"]))
        if r.get("building"):
            building_map[canonical_building(r["building"])].add(low(r["building"]))
        if r.get("developer"):
            developer_map[canonical_developer(r["developer"])].add(low(r["developer"]))
    for base_map, hints in [
        (area_map, AREA_ALIAS_HINTS),
        (project_map, PROJECT_ALIAS_HINTS),
        (building_map, BUILDING_ALIAS_HINTS),
        (developer_map, DEVELOPER_ALIAS_HINTS),
    ]:
        pass
    AREA_ALIAS_PATH.write_text(json.dumps({canon: sorted(v) for canon, v in area_map.items() if canon}, indent=2) + "\n")
    PROJECT_ALIAS_PATH.write_text(json.dumps({canon: sorted(v) for canon, v in project_map.items() if canon}, indent=2) + "\n")
    BUILDING_ALIAS_PATH.write_text(json.dumps({canon: sorted(v) for canon, v in building_map.items() if canon}, indent=2) + "\n")
    DEVELOPER_ALIAS_PATH.write_text(json.dumps({canon: sorted(v) for canon, v in developer_map.items() if canon}, indent=2) + "\n")


def unresolved_review(records):
    rows = []
    categories = Counter()
    signature_count = Counter()
    for rec in records:
        if rec.get("building") and rec.get("unit"):
            continue
        sig = "|".join([rec.get("source_file", ""), rec.get("area", ""), rec.get("project", ""), rec.get("listing_id", ""), rec.get("permit_number", ""), rec.get("property_number", ""), rec.get("plot_number", ""), rec.get("land_number", "")])
        signature_count[sig] += 1
    for rec in records:
        if rec.get("building") and rec.get("unit"):
            continue
        extracted = {k: rec.get(k, "") for k in ["area", "project", "building", "unit", "size", "bedrooms", "permit_number", "property_number", "plot_number", "land_number", "listing_id", "listing_url", "match_basis", "developer", "confidence_score"]}
        missing = []
        if not rec.get("building"):
            missing.append("building")
        if not rec.get("unit"):
            missing.append("unit")
        reason = ""
        strategy = ""
        if rec.get("owner_contact_available") == "YES":
            reason = "owner/contact-only signals with missing unit/building"
            strategy = "complete against matching identifier + source file/project records only, keep contact fields restricted"
            category = "owner/contact-only"
        elif any(rec.get(k) for k in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]):
            reason = "identifier present but no matching complete record in extracted set"
            strategy = "exact id match against complete records, then size/bedroom fuzzy fallback"
            category = "identifier-only"
        elif rec.get("listing_url") or rec.get("listing_id"):
            reason = "listing link only"
            strategy = "listing ID + slug token match against resolved groups"
            category = "URL/listing-only"
        elif rec.get("area") or rec.get("project") or rec.get("building"):
            reason = "has project/building text but unit not resolved"
            strategy = "cross record completion via same source file + project + source/ID anchors"
            category = "project/building-only"
        elif rec.get("source_file") and rec.get("source_row"):
            reason = "text/PDF extraction fragment too noisy"
            strategy = "manual review on source file row context, strengthen extractor"
            category = "noisy PDF/text extraction"
        else:
            reason = "insufficient extracted structure"
            strategy = "manual curation / stronger parser"
            category = "duplicate/near-duplicate"
        if rec.get("extracted_from_pdf") == "YES" or rec.get("extracted_from_text") == "YES":
            if not reason:
                reason = "noisy PDF/text extraction record"
            category = category or "noisy PDF/text extraction"
        if signature_count["|".join([rec.get("source_file", ""), rec.get("area", ""), rec.get("project", ""), rec.get("listing_id", ""), rec.get("permit_number", ""), rec.get("property_number", ""), rec.get("plot_number", ""), rec.get("land_number", "")])] > 1:
            category = "duplicate/near-duplicate"
            reason = "near-duplicate signature rows detected"
        rows.append({
            "source_file": rec.get("source_file", ""),
            "extracted_keys": json.dumps(extracted, ensure_ascii=False),
            "missing_key": ",".join(missing) or "unit_and_building",
            "failure_reason": reason,
            "suggested_strategy": strategy,
            "category": category,
        })
        categories[category] += 1
    return rows, categories


def unresolved_category_breakdown(categories):
    ordered = [
        "identifier-only",
        "URL/listing-only",
        "project/building-only",
        "owner/contact-only",
        "noisy PDF/text extraction",
        "duplicate/near-duplicate",
    ]
    return [{"category": category, "count": str(categories.get(category, 0))} for category in ordered]


def unresolved_top_reasons(records):
    cnt = Counter()
    for rec in records:
        if rec.get("building") and rec.get("unit"):
            continue
        if rec.get("owner_contact_available") == "YES":
            cnt["owner/contact-only signals with missing unit/building"] += 1
        elif any(rec.get(k) for k in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]):
            cnt["identifier present but no matching complete record"] += 1
        elif rec.get("listing_url") or rec.get("listing_id"):
            cnt["listing links without unit/building"] += 1
        elif rec.get("area") or rec.get("project") or rec.get("building"):
            cnt["missing unit/building despite project/context"] += 1
        else:
            cnt["insufficient keys"] += 1
    return cnt


def completion_success_counts(records):
    unmatched_ids = sum(1 for r in records if (r.get("permit_number") or r.get("property_number") or r.get("plot_number") or r.get("land_number")) and not (r.get("building") and r.get("unit")))
    unmatched_urls = sum(1 for r in records if r.get("listing_url") and not (r.get("building") and r.get("unit")))
    matched_urls = sum(1 for r in records if r.get("listing_url") and r.get("building") and r.get("unit"))
    matched_ids = sum(1 for r in records if (r.get("permit_number") or r.get("property_number") or r.get("plot_number") or r.get("land_number")) and r.get("building") and r.get("unit"))
    return {
        "url_success": matched_urls,
        "id_success": matched_ids,
        "unmatched_ids": unmatched_ids,
        "unmatched_urls": unmatched_urls,
    }


def listing_id_from_url(url):
    u = url.rstrip("/.,)")
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    platform_match = PLATFORM_RE.search(u)
    platform = platform_match.group(1).lower().replace("www.", "") if platform_match else ""
    digits = re.findall(r"\d{5,}", u)
    if digits:
        return platform, digits[-1]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", u.split("/")[-1]).strip("-")
    if slug == "en" or slug == "go":
        return platform, ""
    return platform, slug[:80]


def is_valid_identifier(key, value):
    if not value:
        return False
    v = low(str(value)).strip()
    if not v:
        return False
    if v in {"en", "null", "na", "n/a", "none", "new", "home"}:
        return False
    if len(v) < 1:
        return False
    if key in {"listing_id"} and not re.search(r"[a-z0-9]", v):
        return False
    if key in {"permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"}:
        # keep id-like strings with at least one digit
        if not re.search(r"\d", v):
            return False
    return True


def url_tokens(url):
    clean = re.sub(r"https?://|www\.|propertyfinder\.ae|bayut\.com|dubizzle\.com", " ", url, flags=re.I)
    clean = re.sub(r"[^A-Za-z0-9]+", " ", clean)
    tokens = [t.lower() for t in clean.split() if len(t) > 2 and not t.isdigit()]
    return {
        "slug_title_tokens": " ".join(tokens[:30]),
        "area_tokens": " ".join(t for t in tokens if t in {a for aliases in AREA_ALIAS_HINTS.values() for a in aliases})[:300],
        "project_building_tokens": " ".join(tokens[:30]),
    }


def url_slug_fields(url):
    """Infer additional canonical fields from URL slug text."""
    clean = url.lower()
    clean = re.sub(r"https?://|www\.|propertyfinder\.ae|bayut\.com|dubizzle\.com|/en/|/en$", " ", clean)
    clean = re.sub(r"[^a-z0-9\s]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    text = low(clean)
    area = canonical_area_from_text(text)
    project = canonical_project_from_text(text)
    return area, project


def extract_numbers(text):
    out = defaultdict(list)
    for key, patterns in NUMBER_PATTERNS.items():
        for pattern in patterns:
            for m in re.finditer(pattern, text, flags=re.I):
                value = norm(m.group(1)).strip(" .,:;")
                if value and not is_noise_number(value) and not is_value_identifier_noise(key, value) and not value.lower() in {"no", "number"}:
                    out[key].append(value[:60])
    return {k: sorted(set(v)) for k, v in out.items()}


def text_sample(path, file_type):
    pieces = [path.name]
    flags = []
    try:
        if file_type == "txt":
            pieces.append(path.read_text(errors="ignore")[:50000])
        elif file_type == "csv":
            with path.open(errors="ignore", newline="") as f:
                for i, row in enumerate(csv.reader(f)):
                    pieces.append(" ".join(row[:60]))
                    if i >= 200:
                        break
        elif file_type == "xlsx":
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                pieces.extend(names[:100])
                for member in ["xl/sharedStrings.xml", "xl/workbook.xml", "docProps/core.xml", "docProps/app.xml"]:
                    if member in names:
                        pieces.append(zf.read(member)[:800000].decode("utf-8", "ignore"))
        elif file_type == "pdf":
            if PdfReader is None:
                flags.append("pdf_reader_unavailable")
            else:
                try:
                    logging.getLogger("pypdf").setLevel(logging.ERROR)
                    with redirect_stderr(io.StringIO()):
                        reader = PdfReader(str(path), strict=False)
                        if reader.is_encrypted:
                            flags.append("password_protected")
                        else:
                            for page in reader.pages[:3]:
                                extracted = page.extract_text() or ""
                                if extracted:
                                    pieces.append(extracted[:12000])
                except Exception as e:
                    flags.append(f"pdf_text_unreadable:{type(e).__name__}")
        elif file_type == "zip":
            with zipfile.ZipFile(path) as zf:
                pieces.extend(zf.namelist()[:250])
    except Exception as e:
        flags.append(f"unreadable:{type(e).__name__}")
    return "\n".join(pieces), flags


def read_acq():
    with ACQ.open(newline="") as f:
        return list(csv.DictReader(f))


def unique_source_records(acq_rows):
    seen = set()
    out = []
    for r in acq_rows:
        sha = r["sha256"]
        if sha in seen:
            continue
        seen.add(sha)
        p = Path(r["duplicate_of_or_copied_to"])
        if p.exists():
            rr = dict(r)
            rr["path"] = str(p)
            out.append(rr)
    return out


def base_record(source, path, source_file, source_chat=""):
    return {
        "resolver_record_id": hashlib.sha1(f"{source}|{path}|{source_file}".encode()).hexdigest()[:16],
        "source_platform": "",
        "listing_url": "",
        "property_finder_url": "",
        "bayut_url": "",
        "dubizzle_url": "",
        "listing_id": "",
        "listing_platform": "",
        "slug_title_tokens": "",
        "area_tokens": "",
        "project_building_tokens": "",
        "permit_number": "",
        "property_number": "",
        "plot_number": "",
        "land_number": "",
        "municipality_number": "",
        "dewa_number": "",
        "area": "",
        "project": "",
        "building": "",
        "unit": "",
        "size": "",
        "bedrooms": "",
        "price": "",
        "developer": "",
        "owner_contact_available": "NO",
        "source_file": source_file,
        "source_path": str(path),
        "source_chat_group": source_chat,
        "source_sheet": "",
        "source_row": "",
        "row_number": "",
        "extracted_from_pdf": "NO",
        "extracted_from_sheet": "NO",
        "extracted_from_text": "NO",
        "extraction_confidence": "0",
        "confidence_score": "0",
        "match_basis": source,
        "restricted_ref": "",
    }


def add_url(record, url):
    platform, listing_id = listing_id_from_url(url)
    normalized_url = url if url.lower().startswith(("http://", "https://")) else "https://" + url
    record.update(url_tokens(normalized_url))
    record["source_platform"] = platform
    record["listing_url"] = normalized_url
    record["listing_platform"] = platform
    record["listing_id"] = listing_id if is_valid_identifier("listing_id", listing_id) else ""
    if "propertyfinder" in platform:
        record["property_finder_url"] = normalized_url
    elif "bayut" in platform:
        record["bayut_url"] = normalized_url
    elif "dubizzle" in platform:
        record["dubizzle_url"] = normalized_url


def extract_document_records(unique_records):
    records = []
    quality = []
    pdf_text_scanned = 0
    for src in unique_records:
        path = Path(src["path"])
        if src["file_type"] == "pdf":
            relevant = any(term in low(src["filename"]) for term in PDF_RELEVANCE_TERMS)
            if relevant and pdf_text_scanned < MAX_PDF_TEXT_FILES:
                text, flags = text_sample(path, src["file_type"])
                pdf_text_scanned += 1
            else:
                text, flags = (src["filename"], ["pdf_text_skipped_not_resolver_priority"])
        else:
            text, flags = text_sample(path, src["file_type"])
        text = "\n".join([src["filename"], src.get("source_folder", ""), src.get("source_chat_group", ""), text])
        quality.extend((src["filename"], flag) for flag in flags)
        urls = URL_RE.findall(text)
        nums = extract_numbers(text)
        area = canonical_area(text)
        developer = detect_developer(text)
        for url in sorted(set(urls)):
            rec = base_record("document_url", path, src["filename"], src.get("source_chat_group", ""))
            add_url(rec, url)
            parsed_area, parsed_project = url_slug_fields(rec.get("listing_url", ""))
            if parsed_area:
                rec["area"] = parsed_area
            if parsed_project:
                rec["project"] = parsed_project
            if not rec.get("area") and area and len(area) < 80:
                rec["area"] = area
            rec["developer"] = developer
            rec["confidence_score"] = "85"
            rec["extraction_confidence"] = "90"
            rec["extracted_from_pdf"] = "YES" if src["file_type"] == "pdf" else "NO"
            rec["extracted_from_text"] = "YES" if src["file_type"] in {"txt", "csv"} else "NO"
            rec["match_basis"] = "listing_url"
            records.append(rec)
        for key, values in nums.items():
            for value in values:
                if not is_valid_identifier(key, value):
                    continue
                rec = base_record(f"document_{key}", path, src["filename"], src.get("source_chat_group", ""))
                rec[key] = norm(value)
                rec["area"] = area if area and len(area) < 80 else ""
                rec["developer"] = developer
                rec["confidence_score"] = "95" if key in {"permit_number", "property_number", "plot_number", "land_number"} else "90"
                rec["extraction_confidence"] = "85" if src["file_type"] == "pdf" else "80"
                rec["extracted_from_pdf"] = "YES" if src["file_type"] == "pdf" else "NO"
                rec["extracted_from_text"] = "YES" if src["file_type"] in {"txt", "csv"} else "NO"
                rec["match_basis"] = f"exact_{key}"
                records.append(rec)
    return records, quality


def extract_inventory_records(unique_records):
    records = []
    restricted = []
    quality = []
    tabular_sources = [src for src in unique_records if src["file_type"] in {"xlsx", "csv"}]
    def priority(src):
        name = low(src["filename"])
        score = sum(1 for term in PRIORITY_TERMS if term in name)
        if src["file_type"] == "csv":
            score += 2
        return -score, name
    tabular_sources.sort(key=priority)
    xlsx_seen = 0
    for src in tabular_sources:
        if src["file_type"] not in {"xlsx", "csv"}:
            continue
        if src["file_type"] == "xlsx":
            xlsx_seen += 1
            if xlsx_seen > MAX_XLSX_FILES:
                continue
        path = Path(src["path"])

        def process_row(row, mapping, sheet, row_num):
            joined = " ".join(norm(v) for v in row if v is not None)
            if not joined:
                return
            rec = base_record("inventory_row", path, src["filename"], src.get("source_chat_group", ""))
            rec["area"] = canonical_area(cell(row, mapping, "area") or joined)
            rec["project"] = canonical_project(cell(row, mapping, "project"))
            rec["building"] = canonical_building(cell(row, mapping, "building"))
            rec["unit"] = normalize_unit(cell(row, mapping, "unit"))
            raw_unit = cell(row, mapping, "unit")
            if raw_unit:
                rec_unit_building, rec_unit = split_compound_unit(raw_unit)
                if rec_unit and not rec.get("unit"):
                    rec["unit"] = normalize_unit(rec_unit)
                if rec_unit_building and not rec.get("building"):
                    rec["building"] = rec_unit_building
            rec["size"] = normalize_size(cell(row, mapping, "size"))
            rec["bedrooms"] = canonical_bedrooms(cell(row, mapping, "bedrooms"))
            rec["price"] = cell(row, mapping, "price")
            rec["developer"] = canonical_developer(cell(row, mapping, "developer") or detect_developer(joined))
            for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]:
                val = cell(row, mapping, key)
                if is_valid_identifier(key, val):
                    rec[key] = val
            if not (rec["building"] and rec["unit"]):
                parsed_building, parsed_unit = parse_building_unit_fallback(joined)
            if not rec["building"]:
                rec["building"] = parsed_building
            if not rec["unit"]:
                rec["unit"] = parsed_unit
            if not rec["building"] or not rec["unit"]:
                inf_building, inf_unit = infer_building_unit_from_context(joined, rec.get("project", ""), rec.get("unit", ""))
                if not rec["building"] and inf_building:
                    rec["building"] = inf_building
                if not rec["unit"] and inf_unit:
                    rec["unit"] = inf_unit
            url = cell(row, mapping, "url")
            if url and ("propertyfinder" in url.lower() or "bayut" in url.lower() or "dubizzle" in url.lower()):
                add_url(rec, url)
            else:
                urls = URL_RE.findall(joined)
                if urls:
                    add_url(rec, urls[0])
            if not any(rec[k] for k in ["area", "project", "building", "unit", "size", "bedrooms", "price", "permit_number", "property_number", "plot_number", "listing_id"]):
                return
            owner = cell(row, mapping, "owner")
            mobile = cell(row, mapping, "mobile")
            email = cell(row, mapping, "email")
            phones = PHONE_RE.findall(joined)
            emails = EMAIL_RE.findall(joined)
            if not mobile and phones:
                mobile = phones[0]
            if not email and emails:
                email = emails[0]
            if owner or mobile or email:
                rec["owner_contact_available"] = "YES"
                restricted_id = hashlib.sha1(f"{rec['resolver_record_id']}|{owner}|{mobile}|{email}".encode()).hexdigest()[:16]
                rec["restricted_ref"] = restricted_id
                restricted.append({
                    "restricted_ref": restricted_id,
                    "resolver_record_id": rec["resolver_record_id"],
                    "owner_name": owner,
                    "mobile": mobile,
                    "email": email,
                    "source_file": src["filename"],
                    "source_chat_group": src.get("source_chat_group", ""),
                    "restricted": "RESTRICTED",
                })
            rec["source_sheet"] = sheet
            rec["source_row"] = str(row_num)
            rec["row_number"] = str(row_num)
            rec["extracted_from_sheet"] = "YES"
            rec["extraction_confidence"] = "80"
            if rec["permit_number"] or rec["property_number"] or rec["plot_number"] or rec["land_number"]:
                rec["confidence_score"] = "95"
                rec["match_basis"] = "exact_authority_number"
            elif rec["building"] and rec["unit"]:
                rec["confidence_score"] = "92"
                rec["match_basis"] = "exact_building_unit"
            elif rec["listing_id"]:
                rec["confidence_score"] = "88"
                rec["match_basis"] = "listing_id"
            elif rec["area"] and rec["project"] and (rec["size"] or rec["bedrooms"]):
                rec["confidence_score"] = "75"
                rec["match_basis"] = "area_project_size_bedrooms"
            elif rec["developer"] and rec["project"]:
                rec["confidence_score"] = "62"
                rec["match_basis"] = "developer_project_fuzzy"
            else:
                rec["confidence_score"] = "55"
                rec["match_basis"] = "vector_retrieval_fallback"
            records.append(rec)

        try:
            if src["file_type"] == "csv":
                with path.open(errors="ignore", newline="") as f:
                    reader = csv.reader(f)
                    mapping = {}
                    for row_num, row in enumerate(reader, start=1):
                        if row_num > MAX_ROWS_PER_SHEET:
                            quality.append((src["filename"], f"row_cap_reached:{MAX_ROWS_PER_SHEET}"))
                            break
                        if row_num <= 30 and not mapping:
                            maybe = detect_header(row)
                            if maybe:
                                mapping = maybe
                                continue
                        elif mapping:
                            process_row(row, mapping, "CSV", row_num)
                    if not mapping:
                        quality.append((src["filename"], "missing_key_columns"))
            else:
                wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
                for ws in wb.worksheets:
                    mapping = {}
                    for row_num, row in enumerate(ws.iter_rows(values_only=True), start=1):
                        if row_num > MAX_ROWS_PER_SHEET:
                            quality.append((src["filename"], f"row_cap_reached:{ws.title}:{MAX_ROWS_PER_SHEET}"))
                            break
                        values = list(row)
                        if row_num <= 30 and not mapping:
                            maybe = detect_header(values)
                            if maybe:
                                mapping = maybe
                                continue
                        elif mapping:
                            process_row(values, mapping, ws.title, row_num)
                    if not mapping:
                        quality.append((src["filename"], f"missing_key_columns:{ws.title}"))
                wb.close()
        except Exception as e:
            quality.append((src["filename"], f"unreadable:{type(e).__name__}"))
    return records, restricted, quality


def extract_whatsapp_url_records():
    records = []
    quality = []
    if not WHATSAPP_DB.exists():
        return records, quality
    try:
        con = sqlite3.connect(str(WHATSAPP_DB))
        con.row_factory = sqlite3.Row
        sql = """
            select m.ZTEXT as text, cs.ZPARTNERNAME as chat_name, cs.ZCONTACTJID as chat_jid
            from ZWAMESSAGE m
            left join ZWACHATSESSION cs on m.ZCHATSESSION = cs.Z_PK
            where lower(coalesce(m.ZTEXT,'')) like '%propertyfinder.ae%'
               or lower(coalesce(m.ZTEXT,'')) like '%bayut.com%'
               or lower(coalesce(m.ZTEXT,'')) like '%dubizzle.com%'
        """
        for row in con.execute(sql):
            text = row["text"] or ""
            source_chat = row["chat_name"] or row["chat_jid"] or ""
            for url in sorted(set(URL_RE.findall(text))):
                rec = base_record("whatsapp_text_url", WHATSAPP_DB, "WhatsApp ChatStorage.sqlite", source_chat)
                add_url(rec, url)
                nums = extract_numbers(text)
                for key, vals in nums.items():
                    if vals:
                        rec[key] = vals[0]
                rec["extracted_from_text"] = "YES"
                rec["extraction_confidence"] = "90"
                rec["confidence_score"] = "88"
                rec["match_basis"] = "listing_url"
                records.append(rec)
        con.close()
    except Exception as e:
        quality.append(("WhatsApp ChatStorage.sqlite", f"whatsapp_url_scan_failed:{type(e).__name__}"))
    return records, quality


def dedupe_records(records):
    seen = set()
    out = []
    for r in records:
        key = "|".join(r.get(k, "") for k in ["listing_platform", "listing_id", "permit_number", "property_number", "plot_number", "land_number", "area", "project", "building", "unit", "source_file", "source_sheet", "source_row"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def write_csv(path, rows, fields):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def build_sqlite(records, restricted):
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    fields = list(records[0].keys()) if records else list(base_record("", "", "").keys())
    con.execute(f"create table resolver_records ({', '.join(f + ' text' for f in fields)})")
    con.executemany(
        f"insert into resolver_records ({', '.join(fields)}) values ({', '.join('?' for _ in fields)})",
        [[r.get(f, "") for f in fields] for r in records],
    )
    con.execute("create table restricted_owner_contact (restricted_ref text, resolver_record_id text, owner_name text, mobile text, email text, source_file text, source_chat_group text, restricted text)")
    con.executemany(
        "insert into restricted_owner_contact values (?, ?, ?, ?, ?, ?, ?, ?)",
        [[r.get(k, "") for k in ["restricted_ref", "resolver_record_id", "owner_name", "mobile", "email", "source_file", "source_chat_group", "restricted"]] for r in restricted],
    )
    for col in ["permit_number", "property_number", "plot_number", "land_number", "listing_id", "area", "project", "building", "unit", "developer"]:
        con.execute(f"create index idx_{col} on resolver_records({col})")
    con.commit()
    con.close()


def confidence_for_query(query, record):
    q = {k: low(v) for k, v in query.items() if v}
    if q.get("listing_url") and record.get("listing_url"):
        _, qid = listing_id_from_url(query["listing_url"])
        if qid and qid == low(record.get("listing_id")):
            return 92, "exact_listing_id_from_url"
        q_tokens = set(url_tokens(query["listing_url"])["slug_title_tokens"].split())
        r_tokens = set((record.get("slug_title_tokens") or record.get("project_building_tokens") or "").split())
        overlap = len(q_tokens & r_tokens)
        if overlap >= 4:
            return 78, "url_slug_area_project_tokens"
    if q.get("permit_number") and q["permit_number"] == low(record.get("permit_number")):
        return 99, "exact_permit_number"
    if q.get("property_number") and q["property_number"] == low(record.get("property_number")):
        return 98, "exact_property_number"
    if q.get("plot_number") and q["plot_number"] == low(record.get("plot_number")):
        return 96, "exact_plot_number"
    if q.get("land_number") and q["land_number"] == low(record.get("land_number")):
        return 96, "exact_land_number"
    if q.get("listing_id") and q["listing_id"] == low(record.get("listing_id")):
        return 90, "exact_listing_id"
    if q.get("building") and q.get("unit") and q["building"] == low(record.get("building")) and q["unit"] == low(record.get("unit")):
        return 92, "exact_building_unit"
    score = 0
    basis = []
    for key, points in [("area", 20), ("project", 25), ("size", 20), ("bedrooms", 15), ("developer", 20)]:
        if q.get(key) and record.get(key):
            ratio = SequenceMatcher(None, q[key], low(record.get(key))).ratio()
            if ratio >= 0.85:
                score += points
                basis.append(key)
            elif ratio >= 0.65:
                score += int(points * 0.7)
                basis.append(f"fuzzy_{key}")
    if score >= 65:
        return min(85, score), "area_project_size_bedrooms_fuzzy"
    if q.get("developer") and q.get("project"):
        dev_ratio = SequenceMatcher(None, q["developer"], low(record.get("developer"))).ratio() if record.get("developer") else 0
        proj_ratio = SequenceMatcher(None, q["project"], low(record.get("project"))).ratio() if record.get("project") else 0
        if dev_ratio >= 0.75 and proj_ratio >= 0.65:
            return 62, "developer_project_fuzzy"
    return min(64, score), "vector_retrieval_fallback"


def resolve(query, records):
    best = None
    best_score = -1
    best_basis = ""
    for r in records:
        score, basis = confidence_for_query(query, r)
        if score > best_score:
            best, best_score, best_basis = r, score, basis
    public = {k: best.get(k, "") for k in ["resolver_record_id", "area", "project", "building", "unit", "size", "bedrooms", "price", "developer", "owner_contact_available", "source_file"]} if best else {}
    if best_score < 70 and public:
        public["owner_contact_available"] = "RESTRICTED_CONFIDENCE_BELOW_70"
    return {"query": query, "confidence_score": best_score, "basis": best_basis, "record": public}


def build_tests(records):
    tests = []

    for r in records:
        if r["property_finder_url"] or r["bayut_url"] or r["dubizzle_url"]:
            url = r["property_finder_url"] or r["bayut_url"] or r["dubizzle_url"]
            tests.append({"type": "listing_link", "query": {"listing_url": url}})
            if len([t for t in tests if t["type"] == "listing_link"]) >= 10:
                break

    if len([t for t in tests if t["type"] == "listing_link"]) < 10:
        seen_urls = {t["query"]["listing_url"] for t in tests if t["type"] == "listing_link"}
        for r in records:
            if not r.get("listing_url"):
                continue
            if len([t for t in tests if t["type"] == "listing_link"]) >= 10:
                break
            if r["listing_url"] not in seen_urls:
                tests.append({"type": "listing_link", "query": {"listing_url": r["listing_url"]}})
                seen_urls.add(r["listing_url"])

    for field in ["permit_number", "property_number", "plot_number", "land_number"]:
        values = []
        for r in records:
            value = r.get(field, "")
            if value:
                values.append(value)
        for value in sorted(set(values)):
            tests.append({"type": field, "query": {field: value}})
            if len([t for t in tests if t["type"] in ["permit_number", "property_number", "plot_number", "land_number"]]) >= 10:
                break
        if len([t for t in tests if t["type"] in ["permit_number", "property_number", "plot_number", "land_number"]]) >= 10:
            break

    for r in records:
        if r.get("extracted_from_pdf") == "YES" and any(r.get(k) for k in ["permit_number", "property_number", "plot_number", "land_number", "unit"]):
            q = {}
            for key in ["permit_number", "property_number", "plot_number", "land_number"]:
                if r.get(key):
                    q[key] = r[key]
                    break
            if not q:
                q = {"building": r.get("building", ""), "unit": r.get("unit", "")}
            tests.append({"type": "pdf_extraction", "query": q})
            if len([t for t in tests if t["type"] == "pdf_extraction"]) >= 10:
                break

    for r in records:
        if r.get("area") and (r.get("project") or r.get("building")):
            tests.append({"type": "area_project_building", "query": {"area": r["area"], "project": r.get("project", ""), "building": r.get("building", "")}})
            if len([t for t in tests if t["type"] == "area_project_building"]) >= 10:
                break

    inv = [r for r in records if r.get("source_sheet") and (r.get("unit") or r.get("project") or r.get("building"))]
    random.seed(7)
    for r in random.sample(inv, min(10, len(inv))):
        tests.append({"type": "random_inventory_row", "query": {"area": r.get("area", ""), "project": r.get("project", ""), "building": r.get("building", ""), "unit": r.get("unit", ""), "size": r.get("size", ""), "bedrooms": r.get("bedrooms", "")}})

    results = [resolve(t["query"], records) | {"type": t["type"]} for t in tests]
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    previous = {}
    if (OUT / "run_summary.json").exists():
        try:
            previous = json.loads((OUT / "run_summary.json").read_text()) or {}
        except Exception:
            previous = {}
    acq = read_acq()
    uniques = unique_source_records(acq)
    doc_records, doc_quality = extract_document_records(uniques)
    inv_records, restricted, inv_quality = extract_inventory_records(uniques)
    wa_records, wa_quality = extract_whatsapp_url_records()
    records = [normalize_record_fields(r) for r in dedupe_records(doc_records + inv_records + wa_records)]
    records, unit_completion_evidence = enrich_records_from_reference(records)
    build_alias_files(records)
    unresolved_rows, unresolved_categories = unresolved_review(records)
    unresolved_summary_rows = unresolved_category_breakdown(unresolved_categories)
    write_csv(UNRESOLVED_CSV, unresolved_rows, ["source_file", "extracted_keys", "missing_key", "failure_reason", "suggested_strategy", "category"])
    write_csv(UNRESOLVED_GROUPS_CSV, unresolved_summary_rows, ["category", "count"])
    write_csv(UNIT_COMPLETION_EVIDENCE_CSV, unit_completion_evidence, ["source_file", "merge_key", "filled_fields", "target_resolver_record_id"])

    resolved_before = previous.get("unit_records_resolved", 0)
    fields = list(base_record("", "", "").keys())
    write_csv(IDENTITY_CSV, records, fields)
    IDENTITY_JSON.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    write_csv(INDEX_CSV, records, fields)
    build_sqlite(records, restricted)
    tests = build_tests(records)
    pdf_relevant = [r for r in uniques if r["file_type"] == "pdf" and any(term in low(r["filename"]) for term in PDF_RELEVANCE_TERMS)]
    pdf_files_scanned = min(len(pdf_relevant), MAX_PDF_TEXT_FILES)
    pdf_ids_extracted = len(set(
        (r["source_file"], r["permit_number"], r["property_number"], r["plot_number"], r["land_number"], r["municipality_number"], r["dewa_number"])
        for r in records
        if r.get("extracted_from_pdf") == "YES"
        and any(r.get(k) for k in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"])
    ))

    confidence_distribution = Counter()
    for r in records:
        score = int(r.get("confidence_score", 0) or 0)
        if score >= 90:
            confidence_distribution["90+"] += 1
        elif score >= 80:
            confidence_distribution["80-89"] += 1
        elif score >= 70:
            confidence_distribution["70-79"] += 1
        else:
            confidence_distribution["<70"] += 1
    resolved_after = sum(1 for r in records if r["building"] and r["unit"])
    previous_candidate = resolved_before if resolved_before <= resolved_after else 0

    completion_counts = completion_success_counts(records)
    unresolved = len(records) - resolved_after
    top_failure_reasons = unresolved_top_reasons(records)
    classification = "FAILED"
    if resolved_after > 0:
        classification = "PARTIAL"
    if unresolved <= max(1, resolved_after - 200):
        classification = "LIVE"

    counts = {
        "previous_unit_records_resolved": previous_candidate,
        "classification": classification,
        "total_records_indexed": len(records),
        "permit_numbers_found": len(set(r["permit_number"] for r in records if r["permit_number"])),
        "property_numbers_found": len(set(r["property_number"] for r in records if r["property_number"])),
        "plot_land_numbers_found": len(set((r["plot_number"] or r["land_number"]) for r in records if r["plot_number"] or r["land_number"])),
        "listing_urls_ids_found": len(set((r["listing_platform"], r["listing_id"]) for r in records if r["listing_id"])),
        "urls_found": len(set(r["listing_url"] for r in records if r.get("listing_url"))),
        "listing_ids_extracted": len(set(r["listing_id"] for r in records if r.get("listing_id"))),
        "pdf_files_scanned": pdf_files_scanned,
        "pdf_ids_extracted": pdf_ids_extracted,
        "unit_records_resolved": resolved_after,
        "new_unit_records_resolved": resolved_after - previous_candidate,
        "remaining_unresolved_records": len(records) - resolved_after,
        "confidence_distribution_90_plus": confidence_distribution["90+"],
        "confidence_distribution_80_89": confidence_distribution["80-89"],
        "confidence_distribution_70_79": confidence_distribution["70-79"],
        "confidence_distribution_below_70": confidence_distribution["<70"],
        "restricted_owner_contact_rows": len(restricted),
        "quality_flags": len(doc_quality) + len(inv_quality) + len(wa_quality),
        "test_count": len(tests),
        "url_success_matches": completion_counts["url_success"],
        "id_success_matches": completion_counts["id_success"],
        "top_failure_reasons": [f"{k}:{v}" for k, v in top_failure_reasons.items()],
        "remaining_unresolved_records": unresolved,
    }

    with REPORT.open("w") as f:
        f.write("# AIOS Unit Resolver Test Report\n\n")
        for k, v in counts.items():
            f.write(f"- {k}: {v}\n")
        f.write(f"- database: {DB_PATH}\n")
        f.write("\n## Test results\n")
        for i, t in enumerate(tests, start=1):
            rec = t.get("record", {})
            f.write(f"{i}. {t['type']} | confidence={t['confidence_score']} | basis={t['basis']} | source={rec.get('source_file', '')} | area={rec.get('area', '')} | project={rec.get('project', '')} | building={rec.get('building', '')} | unit={rec.get('unit', '')} | owner_contact={rec.get('owner_contact_available', '')}\n")
        f.write("\n## Quality flags\n")
        for name, flag in (doc_quality + inv_quality + wa_quality)[:200]:
            f.write(f"- {name}: {flag}\n")
        f.write(f"\n## Unresolved records\n")
        f.write(f"- unresolved_records_review: {UNRESOLVED_CSV}\n")
        f.write(f"- unresolved_count: {counts['remaining_unresolved_records']}\n")
        f.write(f"- unresolved_failure_categories: {UNRESOLVED_GROUPS_CSV}\n")
        f.write(f"- unit_completion_evidence: {UNIT_COMPLETION_EVIDENCE_CSV}\n")

    (OUT / "run_summary.json").write_text(json.dumps(counts | {
        "database_path": str(DB_PATH),
        "identity_csv": str(IDENTITY_CSV),
        "identity_json": str(IDENTITY_JSON),
        "resolver_index": str(INDEX_CSV),
        "unresolved_records_review": str(UNRESOLVED_CSV),
        "unresolved_failure_groups": str(UNRESOLVED_GROUPS_CSV),
        "unit_completion_evidence": str(UNIT_COMPLETION_EVIDENCE_CSV),
        "aliases": {
            "area_aliases": str(AREA_ALIAS_PATH),
            "project_aliases": str(PROJECT_ALIAS_PATH),
            "building_aliases": str(BUILDING_ALIAS_PATH),
            "developer_aliases": str(DEVELOPER_ALIAS_PATH),
        },
        "test_report": str(REPORT),
        "tests": tests,
    }, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
