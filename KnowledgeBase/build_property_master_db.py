from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


BASE = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/Raw/CompleteAcquisition_20260621_final")
CATALOG_CSV = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/Raw/KnowledgeBase_Master_Catalog.csv")
DB_PATH = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/Property_Master_Database.sqlite")

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

HEADER_EXACT = {
    "project": {"project", "project name"},
    "area": {"area", "location", "community", "district", "master project"},
    "developer": {"developer"},
    "property_type": {"property type", "propertytype", "propertytypeen", "property type en", "product type", "unit type", "unit category", "type"},
}

HEADER_KWS = set().union(
    *HEADER_EXACT.values(),
    {
        "serial",
        "unit no",
        "unit number",
        "unit code",
        "price",
        "contact",
        "owner",
        "availability",
        "mngt",
        "management",
        "report",
        "plot",
        "view",
        "asking price",
        "saleable area",
        "netarea",
        "net area",
        "totalarea",
        "total area",
        "floor",
        "bedroom",
    },
)

TITLE_GENERIC = {"report", "sheet1", "sheet", "data", "availability list", "list", "inventory"}


def canon(s: object) -> str:
    s = re.sub(r"[\u200e\u200f]+", "", str(s or "")).strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm(text: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\u200e\u200f]+", "", str(text or "").strip())).strip()


def safe(text: object, limit: int = 160) -> str:
    text = norm(text)
    text = re.sub(r"[^A-Za-z0-9._\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:limit] or "Unknown").strip()


def col_to_idx(col: str) -> int:
    n = 0
    for c in col:
        n = n * 26 + (ord(c.upper()) - 64)
    return n - 1


def is_num_like(s: object) -> bool:
    s = str(s or "").strip().replace(",", "")
    return bool(re.fullmatch(r"[-+]?\d+(\.\d+)?", s)) if s else False


def parse_catalog() -> list[dict]:
    with CATALOG_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_shared(z: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(t.text or "" for t in si.iterfind(".//a:t", NS)) for si in root.findall("a:si", NS)]


def sheet_targets(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("rel:Relationship", NS)}
    out = []
    for sh in wb.find("a:sheets", NS):
        name = sh.attrib.get("name", "")
        rid = sh.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_map.get(rid, "worksheets/sheet1.xml")
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        out.append((name, target))
    return out


def parse_rows(z: zipfile.ZipFile, target: str, max_rows: int = 20, max_cols: int = 24) -> list[tuple[int, list[str]]]:
    shared = parse_shared(z)
    root = ET.fromstring(z.read(target))
    rows = []
    for row in root.findall(".//a:sheetData/a:row", NS)[:max_rows]:
        row_num = int(row.attrib.get("r", "0") or 0)
        vals = [""] * max_cols
        for c in row.findall("a:c", NS):
            ref = c.attrib.get("r", "")
            m = re.match(r"([A-Z]+)(\d+)", ref)
            if not m:
                continue
            idx = col_to_idx(m.group(1))
            if idx >= max_cols:
                continue
            t = c.attrib.get("t")
            v = c.find("a:v", NS)
            text = ""
            if t == "s" and v is not None and v.text is not None:
                try:
                    text = shared[int(v.text)]
                except Exception:
                    text = v.text
            elif t == "inlineStr":
                text = "".join(tn.text or "" for tn in c.iterfind(".//a:t", NS))
            else:
                text = v.text if v is not None and v.text is not None else ""
            vals[idx] = norm(text)
        rows.append((row_num, vals))
    return rows


def count_rows(z: zipfile.ZipFile, target: str) -> int:
    count = 0
    with z.open(target) as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag.endswith("}row"):
                has = False
                for c in elem:
                    if c.tag.endswith("}c"):
                        for child in c:
                            if child.text and child.text.strip():
                                has = True
                                break
                        if has:
                            break
                if has:
                    count += 1
                elem.clear()
    return count


def infer_title(rows: list[tuple[int, list[str]]], sheet_name: str, file_stem: str) -> str:
    for _, row in rows[:4]:
        nonempty = [v for v in row if v]
        if not nonempty:
            continue
        joined = " ".join(nonempty)
        low = canon(joined)
        if len(nonempty) <= 3 and not any(k in low for k in HEADER_KWS):
            if len(joined.strip()) > 2:
                return joined.strip()
    if sheet_name and canon(sheet_name) not in TITLE_GENERIC:
        return sheet_name
    return file_stem


def detect_headers(rows: list[tuple[int, list[str]]]) -> tuple[dict[str, int | None], int | None]:
    out = {"project": None, "area": None, "developer": None, "property_type": None}
    header_row_idx = None
    for idx, (_, row) in enumerate(rows):
        labels = [canon(v) for v in row if v]
        joined = " | ".join(labels)
        if not labels:
            continue
        if any(k in joined for k in HEADER_KWS):
            if header_row_idx is None:
                header_row_idx = idx
            for cidx, cell in enumerate([canon(v) for v in row]):
                if not cell:
                    continue
                if out["project"] is None and cell in HEADER_EXACT["project"]:
                    out["project"] = cidx
                if out["area"] is None and cell in HEADER_EXACT["area"]:
                    out["area"] = cidx
                if out["developer"] is None and cell in HEADER_EXACT["developer"]:
                    out["developer"] = cidx
                if out["property_type"] is None and cell in HEADER_EXACT["property_type"]:
                    out["property_type"] = cidx
    return out, header_row_idx


def first_nonempty_row_after(rows: list[tuple[int, list[str]]], idx: int | None) -> list[str] | None:
    if idx is None:
        return None
    for _, row in rows[idx + 1 :]:
        if any(v for v in row):
            return row
    return None


def first_data_like_row(rows: list[tuple[int, list[str]]]) -> list[str] | None:
    for _, row in rows:
        nonempty = [v for v in row if v]
        if not nonempty:
            continue
        joined = canon(" ".join(nonempty))
        if len(nonempty) >= 5:
            return row
        if len(nonempty) >= 3 and any(is_num_like(v) for v in nonempty):
            return row
        if len(nonempty) >= 3 and any(k in joined for k in ["project", "unit", "price", "area", "developer", "view", "floor", "type"]):
            return row
    return None


def guess_geo_area(context_texts: list[str], developer: str = "") -> str:
    joined = canon(" | ".join(t for t in context_texts if t))
    patterns = [
        ("Yas Island", ["yas park", "yas acres", "yas island", "waters edge", "faya", "magnolias", "noya"]),
        ("Saadiyat Island", ["saadiyat", "mamsha", "the source", "dunes"]),
        ("Al Reem Island", ["al reem", "marina heights", "reeman", "reeman plot", "shams"]),
        ("Dubai", ["jvc", "jvt", "jlt", "downtown", "marina", "business bay", "mbz road", "sheikh zayed road", "jumeirah", "arabian ranches", "dubai hills", "dubai"]),
        ("Istanbul, Turkey", ["istanbul, turkey", "istanbul"]),
        ("Riyadh, KSA", ["riyadh"]),
        ("Ras Al Khaimah", ["ras al khaimah", "rak"]),
    ]
    for area, kws in patterns:
        if any(k in joined for k in kws):
            return area
    dev = canon(developer)
    if any(k in dev for k in ["binghatti", "deyaar", "tiger", "aldar", "al dar", "bloom", "wasl", "reportage", "leos", "zoya", "object 1", "igo", "hydra", "imkan"]):
        return "Dubai"
    cand = []
    for t in context_texts:
        t = norm(t)
        if not t:
            continue
        low = canon(t)
        if any(h in low for h in ["island", "city", "community", "road", "turkey", "ksa", "dubai", "abu dhabi", "rak", "jvc", "jvt", "jlt", "marina", "downtown", "golf", "park"]):
            cand.append(t)
    if len(set(cand)) == 1:
        return cand[0]
    return "Dubai"


def normalize_developer(val: str, context: str) -> str:
    s = norm(val)
    if s and not s.isnumeric():
        return {
            "ALDAR": "Aldar",
            "AL DAR": "Aldar",
            "ALDAR ": "Aldar",
            "BLOOM": "Bloom",
            "DEYAAR": "Deyaar",
            "REPORTAGE": "Reportage",
            "TIGER": "Tiger",
            "BINGHATTI": "Binghatti",
            "IGO": "IGO",
            "LEOS": "LEOS",
            "ZOYA": "Zoya",
            "DUBAI BROKERS": "Dubai Brokers",
            "OBJECT 1": "Object 1",
            "OBJECT1": "Object 1",
            "HYDRA PROPERTIES": "Hydra Properties",
            "IMKAN": "IMKAN",
        }.get(s.upper(), s)
    text = canon(context)
    mapping = [
        ("Reportage", ["reportage"]),
        ("Binghatti", ["binghatti"]),
        ("Deyaar", ["deyaar"]),
        ("Tiger", ["tiger"]),
        ("Aldar", ["aldar", "al dar"]),
        ("Bloom", ["bloom"]),
        ("Tamouh", ["tamouh"]),
        ("IGO", ["igo"]),
        ("Wasl", ["wasl"]),
        ("LEOS", ["leos"]),
        ("Zoya", ["zoya"]),
        ("Dubai Brokers", ["dubai broker"]),
        ("Object 1", ["object1", "object 1"]),
        ("Hydra Properties", ["hydra"]),
        ("IMKAN", ["imkan"]),
    ]
    for val, kws in mapping:
        if any(k in text for k in kws):
            return val
    return "Unknown"


def normalize_project(val: str) -> str:
    s = norm(val)
    if not s:
        return "Unknown"
    if s.isnumeric():
        return "Unknown"
    # Preserve common acronyms while title-casing the rest
    parts = []
    for token in re.split(r"(\W+)", s):
        if not token or re.fullmatch(r"\W+", token):
            parts.append(token)
            continue
        up = token.upper()
        if up in {"IGO", "HSH", "JVC", "JVT", "JLT", "MBZ", "Q4", "UAE", "KSA", "RAK", "RPP", "EPP", "AED", "TBD"}:
            parts.append(up)
        else:
            parts.append(token.title())
    out = "".join(parts).strip()
    out = re.sub(r"\s+", " ", out)
    return out


def normalize_area(val: str, context_texts: list[str], developer: str = "") -> str:
    s = norm(val)
    if s and not is_num_like(s):
        low = canon(s)
        if low in {"area", "location", "community", "district", "master project"}:
            s = ""
        else:
            # clean basic capitalization
            if len(s) > 1:
                s = normalize_project(s)
    if not s or is_num_like(s):
        s = guess_geo_area(context_texts, developer)
    return s or "Dubai"


def infer_property_type(rows: list[tuple[int, list[str]]], title: str, sheet_name: str) -> str:
    candidates = []
    for _, row in rows:
        for cell in row:
            low = canon(cell)
            if not low:
                continue
            if any(k in low for k in ["apartment", "villa", "townhouse", "plot", "retail", "office", "shop", "commercial", "studio", "penthouse", "duplex", "mansion", "land", "unit"]):
                if low in {"availability list", "management units", "report"}:
                    continue
                candidates.append(cell)
    if candidates:
        priority = ["commercial", "retail", "office", "shop", "apartment", "villa", "townhouse", "plot", "studio", "penthouse", "duplex", "mansion", "land", "unit"]
        for p in priority:
            for c in candidates:
                if p in canon(c):
                    return c if len(c) < 40 else p.title()
        return candidates[0]
    low = canon(f"{title} {sheet_name}")
    if "commercial" in low:
        return "Commercial"
    if "availability" in low:
        return "Unit"
    return "Unknown"


def infer_inventory_type(title: str, rows: list[tuple[int, list[str]]]) -> str:
    low = canon(" ".join(v for _, row in rows[:5] for v in row if v))
    title_low = canon(title)
    if "availability" in low or "availability" in title_low:
        return "Availability"
    if "mngt" in low or "management units" in low or "mgmt" in low:
        return "Management Units"
    if "handing over" in low or "handover" in low:
        return "Handover"
    if "asking price" in low or "full cash" in low or "saleable area" in low or "price" in low:
        return "Price List"
    if "owner" in low or "contact no" in low or "owner s name" in low:
        return "Owners List"
    if "commercial" in low or "retail" in low or "office" in low or "shop" in low:
        return "Commercial Inventory"
    return "Inventory"


def find_value_by_header(row: list[str], header_map: dict[str, int | None], key: str) -> str:
    idx = header_map.get(key)
    if idx is None or idx >= len(row):
        return ""
    return norm(row[idx])


def extract_numeric(row: list[str], header_map: dict[str, int | None], keys: list[str]) -> str:
    for key in keys:
        idx = header_map.get(key)
        if idx is not None and idx < len(row):
            val = norm(row[idx])
            if val and (is_num_like(val) or any(ch.isdigit() for ch in val)):
                return val
    for cell in row:
        val = norm(cell)
        if val and (is_num_like(val) or any(ch.isdigit() for ch in val)):
            return val
    return ""


def extract_bedrooms(row: list[str], header_map: dict[str, int | None]) -> str:
    idx = header_map.get("bedrooms")
    if idx is not None and idx < len(row):
        val = norm(row[idx])
        if val:
            return val
    for cell in row:
        val = norm(cell)
        low = canon(val)
        if not low:
            continue
        if any(
            k in low
            for k in [
                "studio",
                "1 bedroom",
                "2 bedroom",
                "3 bedroom",
                "4 bedroom",
                "5 bedroom",
                "6 bedroom",
                "1 bhk",
                "2 bhk",
                "3 bhk",
                "4 bhk",
                "5 bhk",
            ]
        ):
            return val
    return ""


def build_header_map(row: list[str]) -> dict[str, int]:
    mp = {}
    for idx, cell in enumerate(row):
        c = canon(cell)
        if not c:
            continue
        if "project" in c and "project" not in mp:
            mp["project"] = idx
        if c in {"developer"} and "developer" not in mp:
            mp["developer"] = idx
        if any(k in c for k in ["area", "saleable area", "net area", "netarea", "totalarea", "total area", "plot area", "built up area", "size", "size sqft", "area sqft"]):
            if "area" not in mp:
                mp["area"] = idx
        if any(k in c for k in ["property type", "propertytype", "product type", "unit type", "unit category", "type"]):
            if "property_type" not in mp:
                mp["property_type"] = idx
        if any(k in c for k in ["serial", "s/n", "sn", "flat no", "flat number", "unit no", "unit number", "unit code"]):
            if "unit_ref" not in mp:
                mp["unit_ref"] = idx
        if "price" in c or "asking" in c:
            if "price" not in mp:
                mp["price"] = idx
        if any(k in c for k in ["bhk", "bed room", "bedroom", "beds", "room"]):
            if "bedrooms" not in mp:
                mp["bedrooms"] = idx
        if "view" in c and "view" not in mp:
            mp["view"] = idx
        if "status" in c and "status" not in mp:
            mp["status"] = idx
        if "floor" in c and "floor" not in mp:
            mp["floor"] = idx
        if "contact" in c and "contact" not in mp:
            mp["contact"] = idx
    return mp


def load_catalog_file_meta() -> list[dict]:
    rows = parse_catalog()
    for r in rows:
        for k in list(r):
            if r[k] is None:
                r[k] = ""
    return rows


def row_hash(payload: dict) -> str:
    # dedupe identical logical listings across all source files
    key = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def main() -> None:
    catalog = load_catalog_file_meta()
    source_by_sha = {r["SHA256"]: r for r in catalog}

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE developers (
            developer_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            normalized_name TEXT NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE areas (
            area_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            normalized_name TEXT NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE property_types (
            property_type_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            normalized_name TEXT NOT NULL
        );
        CREATE TABLE projects (
            project_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            normalized_name TEXT NOT NULL,
            developer_id INTEGER,
            area_id INTEGER,
            file_count INTEGER NOT NULL DEFAULT 0,
            row_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(developer_id) REFERENCES developers(developer_id),
            FOREIGN KEY(area_id) REFERENCES areas(area_id)
        );
        CREATE TABLE inventory_files (
            source_id INTEGER PRIMARY KEY,
            file_name TEXT NOT NULL,
            source_group TEXT NOT NULL,
            source_path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL,
            last_modified TEXT NOT NULL,
            sheet_count INTEGER NOT NULL,
            record_count INTEGER NOT NULL,
            project_id INTEGER,
            developer_id INTEGER,
            area_id INTEGER,
            property_type_id INTEGER,
            inventory_type TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(project_id),
            FOREIGN KEY(developer_id) REFERENCES developers(developer_id),
            FOREIGN KEY(area_id) REFERENCES areas(area_id),
            FOREIGN KEY(property_type_id) REFERENCES property_types(property_type_id)
        );
        CREATE TABLE inventory_rows (
            inventory_row_id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            sheet_name TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            project_id INTEGER,
            developer_id INTEGER,
            area_id INTEGER,
            property_type_id INTEGER,
            inventory_type TEXT NOT NULL,
            unit_ref TEXT,
            bedrooms TEXT,
            area_value TEXT,
            price TEXT,
            view TEXT,
            status TEXT,
            raw_payload_hash TEXT NOT NULL UNIQUE,
            raw_json TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES inventory_files(source_id),
            FOREIGN KEY(project_id) REFERENCES projects(project_id),
            FOREIGN KEY(developer_id) REFERENCES developers(developer_id),
            FOREIGN KEY(area_id) REFERENCES areas(area_id),
            FOREIGN KEY(property_type_id) REFERENCES property_types(property_type_id)
        );
        CREATE TABLE source_row_map (
            source_row_map_id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            sheet_name TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            inventory_row_id INTEGER,
            raw_payload_hash TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES inventory_files(source_id),
            FOREIGN KEY(inventory_row_id) REFERENCES inventory_rows(inventory_row_id)
        );
        CREATE INDEX idx_inventory_rows_source_id ON inventory_rows(source_id);
        CREATE INDEX idx_inventory_rows_project_id ON inventory_rows(project_id);
        CREATE INDEX idx_inventory_rows_area_id ON inventory_rows(area_id);
        CREATE INDEX idx_inventory_rows_developer_id ON inventory_rows(developer_id);
        CREATE INDEX idx_inventory_rows_property_type_id ON inventory_rows(property_type_id);
        CREATE INDEX idx_inventory_rows_price ON inventory_rows(price);
        CREATE INDEX idx_inventory_rows_bedrooms ON inventory_rows(bedrooms);
        CREATE INDEX idx_source_row_map_source_id ON source_row_map(source_id);
        CREATE INDEX idx_source_row_map_inventory_row_id ON source_row_map(inventory_row_id);
        CREATE INDEX idx_projects_name ON projects(name);
        CREATE INDEX idx_developers_name ON developers(name);
        CREATE INDEX idx_areas_name ON areas(name);
        CREATE INDEX idx_property_types_name ON property_types(name);
        """
    )

    # dimension ids
    developer_id_by_name: dict[str, int] = {}
    area_id_by_name: dict[str, int] = {}
    property_type_id_by_name: dict[str, int] = {}
    project_id_by_name: dict[str, int] = {}

    # counters for dominant project associations
    project_dev_counter: dict[str, Counter] = defaultdict(Counter)
    project_area_counter: dict[str, Counter] = defaultdict(Counter)
    project_file_counter: Counter = Counter()
    project_row_counter: Counter = Counter()

    # source file metadata cache
    file_meta = []
    for r in catalog:
        source_path = Path(r["Source Path"])
        last_modified = r.get("Last Modified / Download Timestamp") or r.get("Last Modified") or ""
        file_meta.append(
            {
                "file_name": r["File Name"],
                "source_group": r["Group"],
                "source_path": r["Source Path"],
                "sha256": r["SHA256"],
                "size_bytes": int(source_path.stat().st_size) if source_path.exists() else 0,
                "last_modified": last_modified,
                "sheet_count": int(float(r["Sheet Count"] or 0)),
                "record_count": 0,
                "project": normalize_project(r["Project"]),
                "developer": normalize_developer(r["Developer"], f"{r['Project']} {r['Group']}"),
                "area": normalize_area(r["Area"], [r["Project"], r["Group"]], r["Developer"]),
                "property_type": norm(r["Property Type"]) if r["Property Type"] else "Unknown",
                "inventory_type": norm(r["Inventory Type"]) if r["Inventory Type"] else "Inventory",
            }
        )

    # Build dimension tables from file-level metadata first
    for fm in file_meta:
        developer_id_by_name.setdefault(fm["developer"], None)
        area_id_by_name.setdefault(fm["area"], None)
        property_type_id_by_name.setdefault(fm["property_type"], None)
        project_id_by_name.setdefault(fm["project"], None)
        project_dev_counter[fm["project"]][fm["developer"]] += 1
        project_area_counter[fm["project"]][fm["area"]] += 1
        project_file_counter[fm["project"]] += 1

    # Track unique inventory rows
    unique_row_ids: dict[str, int] = {}
    source_row_count = 0
    unique_row_count = 0

    # source file insert order
    file_id_by_sha: dict[str, int] = {}

    # helper insertion functions
    def ensure_developer(name: str) -> int:
        name = name or "Unknown"
        if name not in developer_id_by_name or developer_id_by_name[name] is None:
            cur.execute(
                "INSERT INTO developers(name, normalized_name, source_count) VALUES (?, ?, 0)",
                (name, name),
            )
            developer_id_by_name[name] = cur.lastrowid
        return developer_id_by_name[name]

    def ensure_area(name: str) -> int:
        name = name or "Unknown"
        if name not in area_id_by_name or area_id_by_name[name] is None:
            cur.execute(
                "INSERT INTO areas(name, normalized_name, source_count) VALUES (?, ?, 0)",
                (name, name),
            )
            area_id_by_name[name] = cur.lastrowid
        return area_id_by_name[name]

    def ensure_property_type(name: str) -> int:
        name = name or "Unknown"
        if name not in property_type_id_by_name or property_type_id_by_name[name] is None:
            cur.execute(
                "INSERT INTO property_types(name, normalized_name) VALUES (?, ?)",
                (name, name),
            )
            property_type_id_by_name[name] = cur.lastrowid
        return property_type_id_by_name[name]

    # seed dimensions with catalog names
    for name in sorted(developer_id_by_name):
        ensure_developer(name)
    for name in sorted(area_id_by_name):
        ensure_area(name)
    for name in sorted(property_type_id_by_name):
        ensure_property_type(name)

    # file metadata insert
    for idx, fm in enumerate(file_meta, 1):
        pid = ensure_developer(fm["developer"])
        aid = ensure_area(fm["area"])
        ptid = ensure_property_type(fm["property_type"])
        file_id = idx
        file_id_by_sha[fm["sha256"]] = file_id
        cur.execute(
            """
            INSERT INTO inventory_files
            (source_id, file_name, source_group, source_path, sha256, size_bytes, last_modified, sheet_count, record_count,
             project_id, developer_id, area_id, property_type_id, inventory_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                fm["file_name"],
                fm["source_group"],
                fm["source_path"],
                fm["sha256"],
                fm["size_bytes"],
                fm["last_modified"],
                fm["sheet_count"],
                0,
                None,
                pid,
                aid,
                ptid,
                fm["inventory_type"],
            ),
        )

    conn.commit()

    # Main extraction loop
    for file_index, fm in enumerate(file_meta, 1):
        path = Path(fm["source_path"])
        if not path.exists():
            raise FileNotFoundError(path)
        if file_index % 10 == 0 or file_index == 1:
            print(f"[{file_index}/{len(file_meta)}] {path.name}")

        with zipfile.ZipFile(path) as z:
            sheets = sheet_targets(z)
            file_row_count = 0
            # File-level context for fallback normalization
            file_context = [fm["project"], fm["developer"], fm["area"], fm["source_group"], path.stem]
            for sheet_name, target in sheets:
                rows_preview = parse_rows(z, target, max_rows=20, max_cols=24)
                title = infer_title(rows_preview, sheet_name, path.stem)
                header_map, header_row_idx = detect_headers(rows_preview)
                first_data_row = first_nonempty_row_after(rows_preview, header_row_idx) if header_row_idx is not None else first_data_like_row(rows_preview)

                # parse entire sheet for row rows
                # build source rows from XML stream with their row numbers
                shared = parse_shared(z)
                root = ET.fromstring(z.read(target))
                seen_header = False
                data_started = False
                local_row_num = 0
                header_row_text = None
                for row in root.findall(".//a:sheetData/a:row", NS):
                    local_row_num = int(row.attrib.get("r", "0") or 0)
                    vals = [""] * 24
                    for c in row.findall("a:c", NS):
                        ref = c.attrib.get("r", "")
                        m = re.match(r"([A-Z]+)(\d+)", ref)
                        if not m:
                            continue
                        idx = col_to_idx(m.group(1))
                        if idx >= len(vals):
                            continue
                        t = c.attrib.get("t")
                        v = c.find("a:v", NS)
                        text = ""
                        if t == "s" and v is not None and v.text is not None:
                            try:
                                text = shared[int(v.text)]
                            except Exception:
                                text = v.text
                        elif t == "inlineStr":
                            text = "".join(tn.text or "" for tn in c.iterfind(".//a:t", NS))
                        else:
                            text = v.text if v is not None and v.text is not None else ""
                        vals[idx] = norm(text)
                    nonempty = [v for v in vals if v]
                    if not nonempty:
                        continue
                    joined = canon(" ".join(nonempty))

                    # skip obvious title/metadata rows before data begins
                    if not data_started:
                        if len(nonempty) <= 2 and not any(is_num_like(v) for v in nonempty):
                            continue
                        if any(k in joined for k in ["project", "developer", "price", "unit", "area", "view", "floor", "type", "serial", "availability", "mngt", "management", "report"]) and len(nonempty) >= 2:
                            # treat as header/title unless the row also looks like data-heavy content
                            if len(nonempty) < 5:
                                header_row_text = vals
                                continue
                        data_started = True

                    # derive row fields
                    row_project = find_value_by_header(vals, header_map, "project")
                    row_developer = find_value_by_header(vals, header_map, "developer")
                    row_property_type = find_value_by_header(vals, header_map, "property_type")
                    row_unit_ref = find_value_by_header(vals, header_map, "unit_ref")
                    row_view = find_value_by_header(vals, header_map, "view")
                    row_status = find_value_by_header(vals, header_map, "status")
                    row_bedrooms = extract_bedrooms(vals, header_map)
                    row_area_value = extract_numeric(vals, header_map, ["area", "floor"])
                    row_price = extract_numeric(vals, header_map, ["price"])

                    # if project is clearly a data cell, keep; else fallback to file context
                    project = normalize_project(row_project or fm["project"] or title)
                    developer = normalize_developer(row_developer or fm["developer"], f"{project} {title} {fm['source_group']}")
                    area = normalize_area(fm["area"], [project, title, fm["source_group"]] + nonempty, developer)
                    property_type = norm(row_property_type) if row_property_type else norm(fm["property_type"])
                    if not property_type:
                        property_type = infer_property_type(rows_preview, title, sheet_name)
                    property_type = property_type or "Unknown"
                    inventory_type = infer_inventory_type(title, rows_preview)
                    unit_ref = norm(row_unit_ref)
                    if not unit_ref:
                        for idx2, cell in enumerate(vals):
                            if idx2 == 0:
                                continue
                            if cell and not is_num_like(cell):
                                unit_ref = cell
                                break
                    if not row_view:
                        # try to get a likely view-like text
                        for cell in vals:
                            low = canon(cell)
                            if low and any(k in low for k in ["view", "road", "community", "lake", "garden", "pool", "park", "sea", "golf", "city", "skyline"]):
                                row_view = cell
                                break
                    # status fallback from title
                    if not row_status:
                        if "handover" in canon(title):
                            row_status = "Handover"
                        elif "availability" in canon(title):
                            row_status = "Available"
                        else:
                            row_status = ""

                    # normalized row payload hash
                    payload = {
                        "project": project,
                        "developer": developer,
                        "area": area,
                        "property_type": property_type,
                        "inventory_type": inventory_type,
                        "unit_ref": unit_ref,
                        "bedrooms": row_bedrooms,
                        "area_value": row_area_value,
                        "price": row_price,
                        "view": row_view,
                        "status": row_status,
                        "sheet_name": sheet_name,
                        "title": title,
                        "context": fm["source_group"],
                        "raw": [v for v in vals if v],
                    }
                    payload_hash = row_hash(payload)
                    row_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)

                    dev_id = ensure_developer(developer)
                    area_id = ensure_area(area)
                    pt_id = ensure_property_type(property_type)

                    if project not in project_id_by_name or project_id_by_name[project] is None:
                        # placeholder; full project rows inserted later after counters are finalized
                        project_id_by_name[project] = 0
                    project_dev_counter[project][developer] += 1
                    project_area_counter[project][area] += 1
                    project_row_counter[project] += 1

                    source_row_count += 1
                    file_row_count += 1

                    if payload_hash not in unique_row_ids:
                        cur.execute(
                            """
                            INSERT INTO inventory_rows
                            (source_id, sheet_name, row_number, project_id, developer_id, area_id, property_type_id,
                             inventory_type, unit_ref, bedrooms, area_value, price, view, status, raw_payload_hash, raw_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                file_id_by_sha[fm["sha256"]],
                                sheet_name,
                                local_row_num,
                                None,
                                dev_id,
                                area_id,
                                pt_id,
                                inventory_type,
                                unit_ref,
                                row_bedrooms,
                                row_area_value,
                                row_price,
                                row_view,
                                row_status,
                                payload_hash,
                                row_json,
                            ),
                        )
                        unique_row_ids[payload_hash] = cur.lastrowid
                        unique_row_count += 1
                        inventory_row_id = cur.lastrowid
                    else:
                        inventory_row_id = unique_row_ids[payload_hash]

                    cur.execute(
                        """
                        INSERT INTO source_row_map
                        (source_id, sheet_name, row_number, inventory_row_id, raw_payload_hash, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            file_id_by_sha[fm["sha256"]],
                            sheet_name,
                            local_row_num,
                            inventory_row_id,
                            payload_hash,
                            row_json,
                        ),
                    )

                # end sheet

            # update file row count
            cur.execute(
                "UPDATE inventory_files SET record_count=? WHERE source_id=?",
                (file_row_count, file_id_by_sha[fm["sha256"]]),
            )

        conn.commit()

    # Final project table population using dominant developer/area for each project
    for project_name, dev_counter in project_dev_counter.items():
        if not project_name or project_name == "Unknown":
            continue
        dev = dev_counter.most_common(1)[0][0] if dev_counter else "Unknown"
        area = project_area_counter[project_name].most_common(1)[0][0] if project_area_counter[project_name] else "Dubai"
        dev_id = ensure_developer(dev)
        area_id = ensure_area(area)
        cur.execute(
            "INSERT INTO projects(name, normalized_name, developer_id, area_id, file_count, row_count) VALUES (?, ?, ?, ?, ?, ?)",
            (project_name, project_name, dev_id, area_id, project_file_counter[project_name], project_row_counter[project_name]),
        )
        project_id_by_name[project_name] = cur.lastrowid

    # Backfill project_id in inventory_files and inventory_rows from project names where possible.
    # Use file-level project info and row-level row_json payloads.
    cur.execute("SELECT source_id, sha256, file_name, source_group FROM inventory_files")
    rows = cur.fetchall()
    for source_id, sha, fname, group in rows:
        fm = source_by_sha.get(sha)
        if not fm:
            continue
        project = fm["Project"] if "Project" in fm else ""
        # source meta not directly available from source_by_sha, so use heuristics from file name and group
        project_guess = normalize_project(Path(fm["Source Path"]).stem)
        if project_guess not in project_id_by_name:
            project_guess = normalize_project(fm["Project"]) if "Project" in fm else "Unknown"
        proj_id = project_id_by_name.get(project_guess)
        if proj_id:
            cur.execute("UPDATE inventory_files SET project_id=? WHERE source_id=?", (proj_id, source_id))

    # A second pass to attach project_id to rows based on their payload JSON.
    cur.execute("SELECT inventory_row_id, raw_json FROM inventory_rows")
    row_updates = []
    for inv_id, raw_json in cur.fetchall():
        try:
            payload = json.loads(raw_json)
        except Exception:
            continue
        project = normalize_project(payload.get("project") or "Unknown")
        proj_id = project_id_by_name.get(project)
        if proj_id:
            row_updates.append((proj_id, inv_id))
    if row_updates:
        cur.executemany("UPDATE inventory_rows SET project_id=? WHERE inventory_row_id=?", row_updates)

    # Update file-level project ids based on project table if present
    cur.execute("SELECT project_id, name FROM projects")
    for proj_id, name in cur.fetchall():
        cur.execute("UPDATE inventory_files SET project_id=? WHERE project_id IS NULL AND file_name LIKE ?", (proj_id, f"%{safe(name)}%"))

    conn.commit()

    # Final counts
    total_inventory_rows = cur.execute("SELECT COUNT(*) FROM inventory_rows").fetchone()[0]
    total_projects = cur.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    total_developers = cur.execute("SELECT COUNT(*) FROM developers").fetchone()[0]
    total_areas = cur.execute("SELECT COUNT(*) FROM areas").fetchone()[0]

    # simple sanity: dedupe should have reduced row count vs source rows
    cur.execute("SELECT COUNT(*) FROM source_row_map")
    total_source_row_maps = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inventory_files")
    total_files = cur.fetchone()[0]

    conn.commit()
    conn.close()

    print("TOTAL_FILES", total_files)
    print("TOTAL_SOURCE_ROWS", total_source_row_maps)
    print("TOTAL_INVENTORY_ROWS", total_inventory_rows)
    print("TOTAL_PROJECTS", total_projects)
    print("TOTAL_DEVELOPERS", total_developers)
    print("TOTAL_AREAS", total_areas)
    print("DB_PATH", DB_PATH)
    print("DATABASE_READY", "YES")


if __name__ == "__main__":
    main()
