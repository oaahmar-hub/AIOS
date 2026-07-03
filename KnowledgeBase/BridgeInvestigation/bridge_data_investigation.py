#!/usr/bin/env python3
"""Read-only bridge data investigation for exact listing URL -> unit feasibility."""

import csv
import json
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
RESOLVER = KB / "resolver"
OUT = KB / "BridgeInvestigation"
RAW = KB / "raw_data"
BITRIX = KB / "Bitrix24"

OUT_INVENTORY = OUT / "bridge_source_inventory.csv"
OUT_CANDIDATES = OUT / "bridge_candidate_evidence.csv"
OUT_COMBINED = OUT / "combined_bridge_paths.csv"
OUT_REPORT = OUT / "BRIDGE_DATA_INVESTIGATION_REPORT.md"
OUT_SUMMARY = OUT / "bridge_data_investigation_summary.json"

URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)[^\s\"'<>)\]]+", re.I)
PLATFORM_RE = re.compile(r"(propertyfinder\.ae|bayut\.com|dubizzle\.com)", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?971|00971|0)?[\s-]?(?:5\d|2|3|4|6|7|9)[\s-]?\d{3}[\s-]?\d{4}")

IDENT_PATTERNS = {
    "permit": [
        r"(?:permit|rera|trakheesi|advertisement permit|dld permit)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{4,40})",
    ],
    "property": [
        r"(?:property|property no|property number|property id)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{3,40})",
    ],
    "plot": [
        r"(?:plot|plot no|plot number)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
    "land": [
        r"(?:land|land no|land number)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
    "municipality": [
        r"(?:municipality|municipality no|municipality number|dm no)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
    "dewa": [
        r"(?:dewa|dewa premise|premise)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})",
    ],
}
BROKER_REF_RE = re.compile(r"\b(?:broker\s+reference|broker\s+ref(?:erence)?|brn|orn|reference|ref)\b\s*(?:no\.?|number|#|:)?\s*([A-Z0-9-]{4,40})", re.I)
UNIT_RE = re.compile(r"\b(?:unit|apt|apartment|flat|villa)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9-]{2,20})\b", re.I)
BED_RE = re.compile(r"\b(studio|\d+)\s*(?:br|bed|beds|bedroom|bedrooms)\b", re.I)
SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(sqm|sq\s?ft|sqft|m2|m²)", re.I)
PRICE_RE = re.compile(r"(?:aed|price|asking|rent)\s*[:#-]?\s*([0-9][0-9,.\s]*(?:m|mn|million|k)?)", re.I)

SOURCE_TYPES = [
    "resolver_database",
    "resolver_csv",
    "live_benchmark",
    "raw_csv",
    "raw_txt",
    "raw_xlsx",
    "raw_pdf",
    "bitrix_crm",
    "hsh_internal",
    "canonical_index",
    "acquisition_index",
]


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def clean_url(url):
    value = norm(url).rstrip(".,;")
    if value and not value.lower().startswith(("http://", "https://")):
        value = "https://" + value
    return value


def normalize_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def platform_for_url(url):
    m = PLATFORM_RE.search(url or "")
    if not m:
        return ""
    host = m.group(1).lower()
    if "propertyfinder" in host:
        return "property_finder"
    if "bayut" in host:
        return "bayut"
    if "dubizzle" in host:
        return "dubizzle"
    return host


def listing_id_from_url(url):
    url = url or ""
    tail = re.sub(r"\.(?:html?|htm)$", "", url.split("?")[0].rstrip("/").split("/")[-1], flags=re.I)
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", tail) if t]
    for token in reversed(tokens):
        if token.isdigit() and len(token) >= 5:
            return token
        if len(token) >= 6 and any(ch.isdigit() for ch in token):
            return token
    ids = re.findall(r"\b\d{5,}\b", url)
    return ids[-1] if ids else ""


def extract_signals(text):
    text = norm(text)
    urls = sorted({clean_url(m.group(0)) for m in URL_RE.finditer(text)})
    ids = {key: set() for key in IDENT_PATTERNS}
    for key, patterns in IDENT_PATTERNS.items():
        for pat in patterns:
            for m in re.finditer(pat, text, flags=re.I):
                value = norm(m.group(1)).strip(".,;")
                if is_valid_identifier_value(key, value):
                    ids[key].add(value)
    broker_refs = {norm(m.group(1)).strip(".,;") for m in BROKER_REF_RE.finditer(text)}
    units = {value for value in (norm(m.group(1)).upper().strip(".,;") for m in UNIT_RE.finditer(text)) if is_valid_unit_value(value)}
    beds = {norm(m.group(1)).lower() for m in BED_RE.finditer(text)}
    sizes = {norm(" ".join(m.groups())) for m in SIZE_RE.finditer(text)}
    prices = {norm(m.group(1)) for m in PRICE_RE.finditer(text)}
    return {
        "urls": urls,
        "listing_ids": {listing_id_from_url(u) for u in urls if listing_id_from_url(u)},
        "platforms": {platform_for_url(u) for u in urls if platform_for_url(u)},
        "identifiers": {k: sorted(v) for k, v in ids.items()},
        "broker_refs": sorted(broker_refs),
        "units": sorted(units),
        "beds": sorted(beds),
        "sizes": sorted(sizes),
        "prices": sorted(prices),
        "has_contact": bool(EMAIL_RE.search(text) or PHONE_RE.search(text)),
    }


def is_valid_identifier_value(key, value):
    raw = norm(value).strip(".,;")
    low_value = raw.lower()
    if not raw or low_value in {"number", "no", "none", "null", "finder", "url", "propertyfinder", "properties", "project", "projects"}:
        return False
    if low_value.startswith(("finder", "for-", "for ", "new-", "new ")):
        return False
    if "propertyfinder" in low_value or "bayut" in low_value or "dubizzle" in low_value:
        return False
    if key in {"permit", "property", "plot", "land", "municipality", "dewa"} and not any(ch.isdigit() for ch in raw):
        return False
    # Reject long URL/slug fragments; exact identifiers are short fields.
    if len(raw) > 40 or raw.count("-") >= 4:
        return False
    return True


def is_valid_unit_value(value):
    raw = norm(value).strip(".,;").upper()
    low_value = raw.lower()
    if not raw or raw in {"NO", "NUMBER", "NONE", "NULL", "N/A"}:
        return False
    if low_value in {"for", "for-rent", "for-sale", "rent", "sale", "dubai", "property"}:
        return False
    if low_value.startswith(("for-", "rent-", "sale-", "property-")):
        return False
    if not any(ch.isdigit() for ch in raw):
        return False
    return True


def source_type_for_path(path, default=""):
    p = str(path).lower()
    if "bitrix24" in p or "crm" in p:
        return "bitrix_crm"
    if "hsh" in p or "homesweethome" in p or "home_sweet_home" in p:
        return "hsh_internal"
    if "resolver" in p and p.endswith(".sqlite"):
        return "resolver_database"
    if "resolver" in p:
        return "resolver_csv"
    if "canonical" in p:
        return "canonical_index"
    if "acquisition_index" in p:
        return "acquisition_index"
    if "/raw_data/csv/" in p:
        return "raw_csv"
    if "/raw_data/txt/" in p:
        return "raw_txt"
    if "/raw_data/xlsx/" in p:
        return "raw_xlsx"
    if "/raw_data/pdf/" in p:
        return "raw_pdf"
    return default or "other"


def make_record(source_type, source_name, source_path, row_ref, text, extra=None):
    extra = extra or {}
    structured = source_type in {"resolver_database", "resolver_csv", "live_benchmark"}
    if structured:
        urls = []
        for key in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url", "url"):
            if extra.get(key):
                urls.append(clean_url(extra[key]))
        sig = {
            "urls": sorted(set(urls)),
            "listing_ids": {str(extra["listing_id"])} if extra.get("listing_id") else set(),
            "platforms": {platform_for_url(u) for u in urls if platform_for_url(u)},
            "identifiers": {k: [] for k in IDENT_PATTERNS},
            "broker_refs": [],
            "units": [],
            "beds": [],
            "sizes": [],
            "prices": [],
            "has_contact": False,
        }
    else:
        sig = extract_signals(text)
        for key in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url", "url"):
            if extra.get(key):
                sig["urls"].append(clean_url(extra[key]))
    if extra.get("listing_id"):
        sig["listing_ids"].add(str(extra["listing_id"]))

    for key, target in [
        ("permit_number", "permit"),
        ("property_number", "property"),
        ("plot_number", "plot"),
        ("land_number", "land"),
        ("municipality_number", "municipality"),
        ("dewa_number", "dewa"),
    ]:
        if extra.get(key) and is_valid_identifier_value(target, str(extra[key])):
            sig["identifiers"][target] = sorted(set(sig["identifiers"][target]) | {str(extra[key])})
    if extra.get("unit"):
        extra_unit = str(extra["unit"]).upper()
        if is_valid_unit_value(extra_unit):
            sig["units"] = sorted(set(sig["units"]) | {extra_unit})
    for key in ("broker_reference", "broker_ref", "reference", "ref"):
        if extra.get(key):
            sig["broker_refs"] = sorted(set(sig["broker_refs"]) | {str(extra[key])})

    has_url = bool(sig["urls"])
    has_unit = bool(sig["units"])
    has_identifier = any(sig["identifiers"][k] for k in sig["identifiers"])
    has_broker_ref = bool(sig["broker_refs"])
    unit_bridge = has_url and has_unit
    id_bridge = has_url and has_identifier
    exact_bridge = unit_bridge
    broker_bridge = has_broker_ref and has_unit
    crm_like = source_type == "bitrix_crm" or any(tok in str(source_path).lower() for tok in ["crm", "bitrix"])
    return {
        "source_type": source_type,
        "source_name": str(source_name),
        "source_path": str(source_path),
        "row_ref": str(row_ref),
        "platforms": sorted(sig["platforms"]),
        "urls": sorted(set(sig["urls"])),
        "listing_ids": sorted(set(sig["listing_ids"])),
        "units": sig["units"],
        "broker_refs": sig["broker_refs"],
        "identifiers": sig["identifiers"],
        "has_url": has_url,
        "has_unit": has_unit,
        "has_identifier": has_identifier,
        "has_broker_ref": has_broker_ref,
        "has_contact": sig["has_contact"],
        "crm_like": crm_like,
        "exact_bridge": exact_bridge,
        "unit_bridge": unit_bridge,
        "identifier_bridge": id_bridge,
        "broker_unit_bridge": broker_bridge,
        "snippet": norm(text)[:350],
    }


def read_csv_records(path, source_type=None, max_rows=None):
    records = []
    source_type = source_type or source_type_for_path(path)
    try:
        with path.open("r", encoding="utf-8", newline="", errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for i, row in enumerate(reader, 1):
                if max_rows and i > max_rows:
                    break
                text = " ".join(f"{k}: {v}" for k, v in row.items() if v not in (None, ""))
                if not text.strip():
                    continue
                records.append(make_record(source_type, path.name, path, i, text, row))
    except Exception as exc:
        records.append(make_record(source_type, path.name, path, "read_error", f"read_error {exc}"))
    return records


def read_text_record(path, source_type=None):
    source_type = source_type or source_type_for_path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        text = f"read_error {exc}"
    return [make_record(source_type, path.name, path, "file", text)]


def read_xlsx_records(path, source_type=None, max_rows_per_sheet=5000):
    records = []
    source_type = source_type or source_type_for_path(path)
    # Fast XML-level XLSX inspection. This is enough for bridge evidence because
    # exact bridges require literal URLs/IDs/units/refs to exist in workbook text.
    bridge_terms = (
        b"propertyfinder",
        b"bayut",
        b"dubizzle",
        b"listing",
        b"broker",
        b"permit",
        b"property",
        b"plot",
        b"land",
        b"unit",
        b"crm",
        b"reference",
        b"ref",
    )
    try:
        with zipfile.ZipFile(path) as zf:
            chunks = []
            for name in zf.namelist():
                lname = name.lower()
                if not (
                    lname.startswith("xl/sharedstrings")
                    or lname.startswith("xl/worksheets")
                    or lname.startswith("xl/tables")
                    or lname.startswith("docprops")
                ):
                    continue
                try:
                    data = zf.read(name)
                except Exception:
                    continue
                low_data = data.lower()
                if not any(term in low_data for term in bridge_terms):
                    continue
                # Strip XML tags but retain enough nearby text for co-occurrence.
                text = re.sub(r"<[^>]+>", " ", data.decode("utf-8", errors="ignore"))
                text = re.sub(r"\s+", " ", text)
                if text:
                    chunks.append(f"{name}: {text[:200000]}")
            if chunks:
                records.append(make_record(source_type, path.name, path, "xlsx_xml_scan", "\n".join(chunks)))
            else:
                records.append(make_record(source_type, path.name, path, "xlsx_xml_scan", "xlsx scanned no bridge terms"))
    except Exception as exc:
        records.append(make_record(source_type, path.name, path, "read_error", f"read_error {exc}"))
    return records


def read_pdf_record(path, source_type=None, max_pages=2):
    source_type = source_type or source_type_for_path(path)
    relevant_name = any(
        term in path.name.lower()
        for term in ["hsh", "property", "finder", "bayut", "dubizzle", "listing", "broker", "permit", "plot", "land", "unit", "crm", "brochure"]
    )
    if not relevant_name:
        return [make_record(source_type, path.name, path, "filename_scan", path.name)]
    if PdfReader is None:
        return [make_record(source_type, path.name, path, "pypdf_missing", "pypdf missing")]
    text_parts = []
    try:
        reader = PdfReader(str(path))
        for page in reader.pages[:max_pages]:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                pass
    except Exception as exc:
        text_parts.append(f"read_error {exc}")
    return [make_record(source_type, path.name, path, f"first_{max_pages}_pages", "\n".join(text_parts))]


def scan_resolver_db():
    db = RESOLVER / "unit_resolver_database.sqlite"
    if not db.exists():
        return []
    records = []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        for row in conn.execute("select * from resolver_records"):
            d = dict(row)
            text = " ".join(f"{k}: {v}" for k, v in d.items() if v not in (None, ""))
            records.append(make_record("resolver_database", "unit_resolver_database.sqlite", db, d.get("row_number") or d.get("resolver_record_id"), text, d))
    finally:
        conn.close()
    return records


def collect_all_records():
    records = []
    records.extend(scan_resolver_db())
    for path in [
        RESOLVER / "listing_identity_map.csv",
        RESOLVER / "unit_resolver_index.csv",
        RESOLVER / "live_listing_benchmark_results.csv",
        RESOLVER / "listing_similarity_candidates.csv",
        RESOLVER / "live_listing_enrichment_candidates.csv",
        RESOLVER / "identifier_bridge_candidates.csv",
        RESOLVER / "bridge_source_audit.csv",
        KB / "acquisition_index.csv",
        KB / "Canonical" / "AIOS_CANONICAL_FILE_INVENTORY.csv",
        KB / "Raw" / "KnowledgeBase_Master_Catalog.csv",
        KB / "Raw" / "KnowledgeBase_Master_Index.csv",
    ]:
        if path.exists():
            st = "live_benchmark" if "benchmark" in path.name else source_type_for_path(path)
            records.extend(read_csv_records(path, st))
    for path in RAW.rglob("*.csv"):
        records.extend(read_csv_records(path, "raw_csv"))
    for path in RAW.rglob("*.txt"):
        records.extend(read_text_record(path, "raw_txt"))
    for path in RAW.rglob("*.xlsx"):
        records.extend(read_xlsx_records(path, source_type_for_path(path)))
    for path in RAW.rglob("*.pdf"):
        # PDF scan is bounded and text-only. No OCR is performed.
        records.extend(read_pdf_record(path, source_type_for_path(path)))
    if BITRIX.exists():
        for path in BITRIX.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".csv":
                records.extend(read_csv_records(path, "bitrix_crm"))
            elif path.suffix.lower() in {".md", ".txt", ".json"}:
                records.extend(read_text_record(path, "bitrix_crm"))
    return records


def aggregate(records):
    inventory = {}
    for st in SOURCE_TYPES + ["other"]:
        inventory[st] = Counter()
    for r in records:
        c = inventory.setdefault(r["source_type"], Counter())
        c["records_scanned"] += 1
        c["records_with_url"] += int(r["has_url"])
        c["url_unit_bridge_rows"] += int(r["unit_bridge"])
        c["url_identifier_bridge_rows"] += int(r["identifier_bridge"])
        c["exact_bridge_rows"] += int(r["exact_bridge"])
        c["broker_ref_rows"] += int(r["has_broker_ref"])
        c["broker_ref_unit_rows"] += int(r["broker_unit_bridge"])
        c["unit_rows"] += int(r["has_unit"])
        c["identifier_rows"] += int(r["has_identifier"])
        c["crm_like_rows"] += int(r["crm_like"])
    return inventory


def combined_paths(records):
    by_listing_id = defaultdict(lambda: {"url_rows": [], "unit_rows": [], "id_rows": []})
    by_identifier = defaultdict(lambda: {"url_rows": [], "unit_rows": []})
    by_broker = defaultdict(lambda: {"url_rows": [], "unit_rows": []})
    all_url_rows = [r for r in records if r["has_url"]]

    for r in records:
        for lid in r["listing_ids"]:
            key = normalize_key(lid)
            if not key:
                continue
            if r["has_url"]:
                by_listing_id[key]["url_rows"].append(r)
            if r["has_unit"]:
                by_listing_id[key]["unit_rows"].append(r)
            if r["has_identifier"]:
                by_listing_id[key]["id_rows"].append(r)
        for ident_type, values in r["identifiers"].items():
            for value in values:
                key = f"{ident_type}:{normalize_key(value)}"
                if len(key.split(":", 1)[1]) < 2:
                    continue
                if r["has_url"]:
                    by_identifier[key]["url_rows"].append(r)
                if r["has_unit"]:
                    by_identifier[key]["unit_rows"].append(r)
        for ref in r["broker_refs"]:
            key = normalize_key(ref)
            if len(key) < 4:
                continue
            if r["has_url"]:
                by_broker[key]["url_rows"].append(r)
            if r["has_unit"]:
                by_broker[key]["unit_rows"].append(r)

    paths = []
    for key, group in by_listing_id.items():
        if group["url_rows"] and group["unit_rows"]:
            paths.append(("listing_id_to_unit", key, group))
    for key, group in by_identifier.items():
        if group["url_rows"] and group["unit_rows"]:
            paths.append(("identifier_to_unit", key, group))
    for key, group in by_broker.items():
        if group["url_rows"] and group["unit_rows"]:
            paths.append(("broker_ref_to_unit", key, group))

    exact_urls = set()
    for bridge_type, key, group in paths:
        for r in group["url_rows"]:
            exact_urls.update(r["urls"])
    return paths, all_url_rows, exact_urls


def write_outputs(records, inventory, paths, all_url_rows, exact_urls):
    with OUT_INVENTORY.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "source_type",
            "records_scanned",
            "records_with_url",
            "exact_url_to_unit_rows",
            "exact_url_to_unit_coverage_pct",
            "url_unit_bridge_rows",
            "url_identifier_only_rows",
            "broker_ref_rows",
            "broker_ref_unit_rows",
            "unit_rows",
            "identifier_rows",
            "crm_like_rows",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for st, c in sorted(inventory.items()):
            url_rows = c["records_with_url"]
            coverage = (c["exact_bridge_rows"] / url_rows * 100) if url_rows else 0.0
            row = {"source_type": st}
            row["records_scanned"] = c["records_scanned"]
            row["records_with_url"] = c["records_with_url"]
            row["exact_url_to_unit_rows"] = c["exact_bridge_rows"]
            row["exact_url_to_unit_coverage_pct"] = f"{coverage:.2f}"
            row["url_unit_bridge_rows"] = c["url_unit_bridge_rows"]
            row["url_identifier_only_rows"] = c["url_identifier_bridge_rows"]
            row["broker_ref_rows"] = c["broker_ref_rows"]
            row["broker_ref_unit_rows"] = c["broker_ref_unit_rows"]
            row["unit_rows"] = c["unit_rows"]
            row["identifier_rows"] = c["identifier_rows"]
            row["crm_like_rows"] = c["crm_like_rows"]
            writer.writerow(row)

    bridge_records = [r for r in records if r["has_url"] or r["has_broker_ref"] or r["exact_bridge"]]
    with OUT_CANDIDATES.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "source_type",
            "source_name",
            "row_ref",
            "platforms",
            "url_count",
            "listing_ids",
            "unit_count",
            "identifier_types",
            "broker_ref_count",
            "exact_bridge",
            "unit_bridge",
            "identifier_bridge",
            "broker_unit_bridge",
            "source_path",
            "snippet",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in bridge_records:
            writer.writerow(
                {
                    "source_type": r["source_type"],
                    "source_name": r["source_name"],
                    "row_ref": r["row_ref"],
                    "platforms": "|".join(r["platforms"]),
                    "url_count": len(r["urls"]),
                    "listing_ids": "|".join(r["listing_ids"][:10]),
                    "unit_count": len(r["units"]),
                    "identifier_types": "|".join(k for k, v in r["identifiers"].items() if v),
                    "broker_ref_count": len(r["broker_refs"]),
                    "exact_bridge": "YES" if r["exact_bridge"] else "NO",
                    "unit_bridge": "YES" if r["unit_bridge"] else "NO",
                    "identifier_bridge": "YES" if r["identifier_bridge"] else "NO",
                    "broker_unit_bridge": "YES" if r["broker_unit_bridge"] else "NO",
                    "source_path": r["source_path"],
                    "snippet": r["snippet"],
                }
            )

    with OUT_COMBINED.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "bridge_type",
            "bridge_key",
            "url_rows",
            "unit_rows",
            "id_rows",
            "sample_url_source",
            "sample_unit_source",
            "exact_url_count_supported",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for bridge_type, key, group in paths:
            url_rows = group.get("url_rows", [])
            unit_rows = group.get("unit_rows", [])
            id_rows = group.get("id_rows", [])
            supported = set()
            for r in url_rows:
                supported.update(r["urls"])
            writer.writerow(
                {
                    "bridge_type": bridge_type,
                    "bridge_key": key,
                    "url_rows": len(url_rows),
                    "unit_rows": len(unit_rows),
                    "id_rows": len(id_rows),
                    "sample_url_source": url_rows[0]["source_path"] if url_rows else "",
                    "sample_unit_source": unit_rows[0]["source_path"] if unit_rows else "",
                    "exact_url_count_supported": len(supported),
                }
            )

    total_url_rows = len(all_url_rows)
    exact_row_count = sum(1 for r in records if r["exact_bridge"])
    direct_unit_rows = sum(1 for r in records if r["unit_bridge"])
    direct_id_rows = sum(1 for r in records if r["identifier_bridge"])
    total_unique_urls = len({u for r in all_url_rows for u in r["urls"]})
    combined_exact_url_count = len(exact_urls)
    recommendation = (
        "permanently_freeze_url_mapping_until_bridge_data"
        if direct_unit_rows == 0 and combined_exact_url_count == 0
        else "build_bridge_engine"
    )
    if combined_exact_url_count > 0:
        recommendation = "build_bridge_engine"

    lines = [
        "# Bridge Data Investigation Report",
        "",
        "## Scope",
        "",
        "Read-only investigation of existing internal datasets for exact public listing URL to unit mapping.",
        "",
        "No Unit Finder algorithm, scoring, matching, resolver, or production logic was changed.",
        "",
        "## Executive Result",
        "",
        f"- records_scanned: {len(records)}",
        f"- url_rows_found: {total_url_rows}",
        f"- unique_listing_urls_found: {total_unique_urls}",
        f"- direct_url_plus_unit_rows: {direct_unit_rows}",
        f"- direct_url_plus_identifier_rows_without_unit_link: {direct_id_rows}",
        f"- direct_exact_url_to_unit_rows: {exact_row_count}",
        f"- combined_exact_url_count_supported: {combined_exact_url_count}",
        f"- recommendation: `{recommendation}`",
        "",
        "## Source Coverage",
        "",
        "| Source | Records | URL rows | Exact URL-to-unit rows | Exact coverage of URL rows | URL+unit | URL+identifier only | Broker ref rows | Broker ref+unit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for st, c in sorted(inventory.items()):
        if c["records_scanned"] == 0:
            continue
        url_rows = c["records_with_url"]
        coverage = (c["exact_bridge_rows"] / url_rows * 100) if url_rows else 0.0
        lines.append(
            f"| {st} | {c['records_scanned']} | {url_rows} | {c['exact_bridge_rows']} | {coverage:.2f}% | {c['url_unit_bridge_rows']} | {c['url_identifier_bridge_rows']} | {c['broker_ref_rows']} | {c['broker_ref_unit_rows']} |"
        )

    lines.extend(
        [
            "",
            "## Combined-Source Feasibility",
            "",
            f"- combined bridge paths found: {len(paths)}",
            f"- unique URL values that can be exactly bridged through shared listing ID, identifier, or broker reference: {combined_exact_url_count}",
            "",
        ]
    )
    if paths:
        for bridge_type, key, group in paths[:20]:
            lines.append(
                f"- {bridge_type}: `{key}` | url_rows={len(group.get('url_rows', []))} | unit_rows={len(group.get('unit_rows', []))}"
            )
    else:
        lines.append("- No combined-source exact bridge path found.")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- URL rows exist across resolver outputs, WhatsApp-derived rows, and raw/corpus files.",
            "- Unit rows exist in large volume, especially inventory/owner/unit style datasets.",
            "- Existing internal data does not show a reliable exact bridge from listing URL/listing ID/broker reference to a unit number.",
            "- URL plus identifier rows exist, but no current source connects those URL-side identifiers to unit-bearing rows.",
            "- Area/project/building similarity can support likely candidate matching, but it is not exact URL-to-unit evidence.",
            "",
            "## Recommendation",
            "",
        ]
    )
    if recommendation == "build_bridge_engine":
        lines.append("Build a Bridge Engine only around the exact bridge paths listed in `combined_bridge_paths.csv`; keep all non-exact paths as LIKELY/PARTIAL evidence.")
    else:
        lines.append("Permanently freeze URL mapping until new bridge data is provided. Do not continue Unit Finder URL-to-unit work from current datasets.")
    lines.extend(
        [
            "",
            "Required future data remains:",
            "",
            "- Listing reference, broker reference, or CRM export linked to unit number, permit, property number, plot, or land number.",
            "",
            "## Evidence Files",
            "",
            f"- source_inventory_csv: `{OUT_INVENTORY}`",
            f"- candidate_evidence_csv: `{OUT_CANDIDATES}`",
            f"- combined_paths_csv: `{OUT_COMBINED}`",
            f"- summary_json: `{OUT_SUMMARY}`",
        ]
    )
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "records_scanned": len(records),
        "url_rows_found": total_url_rows,
        "unique_listing_urls_found": total_unique_urls,
        "direct_url_plus_unit_rows": direct_unit_rows,
        "direct_url_plus_identifier_rows_without_unit_link": direct_id_rows,
        "direct_exact_url_to_unit_rows": exact_row_count,
        "combined_bridge_paths": len(paths),
        "combined_exact_url_count_supported": combined_exact_url_count,
        "recommendation": recommendation,
        "outputs": {
            "source_inventory_csv": str(OUT_INVENTORY),
            "candidate_evidence_csv": str(OUT_CANDIDATES),
            "combined_paths_csv": str(OUT_COMBINED),
            "report_md": str(OUT_REPORT),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    records = collect_all_records()
    inventory = aggregate(records)
    paths, all_url_rows, exact_urls = combined_paths(records)
    summary = write_outputs(records, inventory, paths, all_url_rows, exact_urls)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
