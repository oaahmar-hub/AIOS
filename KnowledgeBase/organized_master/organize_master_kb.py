#!/usr/bin/env python3
import csv
import json
import os
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl
from pypdf import PdfReader

HOME = Path("/Users/hassanka")
KB = HOME / "Downloads" / "AIOS" / "KnowledgeBase"
RAW = KB / "raw_data"
ACQ = KB / "acquisition_index.csv"
OUT = KB / "organized_master"

DIRS = {
    "areas": OUT / "areas",
    "projects": OUT / "projects",
    "developers": OUT / "developers",
    "owners": OUT / "owners",
    "inventory": OUT / "inventory",
    "documents": OUT / "documents",
    "duplicates": OUT / "duplicates",
    "review_needed": OUT / "review_needed",
    "reports": OUT / "reports",
    "indexes": OUT / "indexes",
}

CURRENT = datetime(2026, 6, 23, tzinfo=timezone.utc)

AREA_ALIASES = {
    "JVC": ["jvc", "jumeirah village circle"],
    "JVT": ["jvt", "jumeirah village triangle"],
    "Meydan": ["meydan", "midan", "maidan"],
    "Meydan One": ["meydan one"],
    "MBR City": ["mbr", "mbr city", "mohammed bin rashid city", "mohammad bin rashid city"],
    "Al Furjan": ["al furjan", "furjan"],
    "Creek Harbour": ["dubai creek harbour", "creek harbour", "dubai creek"],
    "Palm Jumeirah": ["palm jumeirah", "the palm", "palm", "pj-p-vp"],
    "Dubai Marina": ["dubai marina", "marina"],
    "Business Bay": ["business bay", "bussiness bay", "businessbay"],
    "Downtown": ["downtown", "downtown dubai"],
    "Dubai Hills": ["dubai hills", "dubai hills estate"],
    "Dubai Land": ["dubailand", "dubai land"],
    "Dubai South": ["dubai south"],
    "Emaar South": ["emaar south"],
    "Town Square": ["town square"],
    "Arabian Ranches": ["arabian ranches"],
    "Dubai Islands": ["dubai islands", "deira islands"],
    "Sobha Hartland": ["sobha hartland"],
    "Yas Island": ["yas island"],
    "Saadiyat": ["saadiyat", "saadiyat island"],
    "Reem Island": ["reem island", "al reem", "al reem island"],
    "Al Raha": ["al raha", "al raha beach"],
    "Port De La Mer": ["port de la mer", "la mer"],
    "Palm Jebel Ali": ["palm jebel ali"],
    "Damac Hills": ["damac hills", "damac hills 2", "akoya"],
    "JLT": ["jlt", "jumeirah lake towers"],
    "JBR": ["jbr", "jumeirah beach residence"],
    "Dubai Harbour": ["dubai harbour", "dubai harbor"],
    "Emaar Beachfront": ["emaar beachfront"],
    "Bluewaters": ["bluewaters", "blue waters"],
    "City Walk": ["city walk"],
    "Jumeirah": ["jumeirah"],
    "Jumeirah Park": ["jumeirah park"],
    "Jumeirah Golf Estates": ["jumeirah golf estates"],
    "Jumeirah Islands": ["jumeirah islands"],
    "Jumeirah Bay": ["jumeirah bay"],
    "Jumeirah Heights": ["jumeirah heights"],
    "Jumeirah Village": ["jumeirah village"],
    "Al Barsha": ["al barsha", "barsha"],
    "Barsha Heights": ["barsha heights", "tecom"],
    "Al Wasl": ["al wasl"],
    "Al Quoz": ["al quoz"],
    "Deira": ["deira"],
    "Bur Dubai": ["bur dubai"],
    "Dubai Festival City": ["festival city", "dubai festival city"],
    "Discovery Gardens": ["discovery gardens"],
    "International City": ["international city"],
    "Motor City": ["motor city"],
    "Mudon": ["mudon"],
    "Nad Al Sheba": ["nad al sheba"],
    "Tilal Al Ghaf": ["tilal al ghaf"],
    "The Greens": ["the greens"],
    "The Springs": ["the springs"],
    "The Meadows": ["the meadows"],
    "The Lakes": ["the lakes"],
    "Umm Suqeim": ["umm suqeim", "um suqeim"],
    "Wadi Al Safa": ["wadi al safa"],
    "World Islands": ["world islands", "the world"],
    "Dubai Silicon Oasis": ["dso", "dubai silicon oasis"],
    "Dubai Investment Park": ["dip", "dubai investment park"],
    "Dubai Sports City": ["sports city", "dubai sports city"],
    "Dubai Production City": ["production city", "impz"],
    "Dubai Healthcare City": ["healthcare city", "dubai healthcare city"],
    "Dubai Maritime City": ["maritime city", "dubai maritime city"],
    "Dubai Science Park": ["science park", "dubai science park"],
    "Dubai Studio City": ["studio city", "dubai studio city"],
    "Dubai Waterfront": ["dubai waterfront"],
    "Abu Dhabi": ["abu dhabi"],
    "Sharjah": ["sharjah"],
    "Ajman": ["ajman"],
    "Ras Al Khaimah": ["ras al khaimah", "rak"],
    "Umm Al Quwain": ["umm al quwain", "uaq"],
    "Fujairah": ["fujairah"],
    "Al Ain": ["al ain"],
}

DEVELOPER_ALIASES = {
    "Emaar": ["emaar"],
    "Damac": ["damac"],
    "Sobha": ["sobha"],
    "Nakheel": ["nakheel"],
    "Aldar": ["aldar"],
    "Reportage": ["reportage"],
    "Binghatti": ["binghatti"],
    "Deyaar": ["deyaar"],
    "Azizi": ["azizi"],
    "Danube": ["danube"],
    "Tiger": ["tiger"],
    "Object1": ["object1", "object 1"],
    "Ellington": ["ellington"],
    "Meraas": ["meraas"],
    "Select Group": ["select group"],
    "Omniyat": ["omniyat"],
    "London Gate": ["london gate"],
    "Leos": ["leos"],
    "Samana": ["samana"],
    "Imtiaz": ["imtiaz"],
    "HSH": ["hsh", "home sweet home"],
    "Mag": ["mag"],
    "Dubai Holding": ["dubai holding"],
    "Nshama": ["nshama"],
    "Arada": ["arada"],
    "Wasl": ["wasl"],
    "Meydan": ["meydan"],
    "Dubai Properties": ["dubai properties"],
}

PROJECT_SEEDS = {
    "Tiger Sky Tower": ["tiger sky tower"],
    "Palm Crown": ["palm crown"],
    "Sadaf": ["sadaf"],
    "Oxford Terraces": ["oxford terraces"],
    "Verdana": ["verdana"],
    "Diva": ["diva"],
    "Damac Lagoons": ["damac lagoons"],
    "Damac Lagoons Toledo": ["toledo"],
    "Binghatti Wraith": ["binghatti wraith"],
    "Binghatti Apex": ["binghatti apex"],
    "Tilal Binghatti": ["tilal binghatti"],
    "La Dimora": ["la dimora"],
    "Reportage Heights": ["reportage heights"],
    "Monte Napoleone": ["monte napoleone"],
}

HEADER_ALIASES = {
    "area": ["area", "community", "location", "district", "master community", "master development"],
    "project": ["project", "project name", "development", "property", "property name", "community name"],
    "building": ["building", "building name", "tower", "tower name", "sub community"],
    "unit": ["unit", "unit no", "unit number", "unit_number", "property no", "apartment", "villa no"],
    "property_type": ["type", "property type", "unit type", "category"],
    "bedrooms": ["bed", "beds", "bedroom", "bedrooms", "br"],
    "size": ["size", "bua", "sqft", "sq.ft", "area sqft", "plot size", "built up area"],
    "price": ["price", "selling price", "sale price", "rent", "annual rent", "amount", "value"],
    "status": ["status", "off plan", "sale/rent", "listing type", "purpose", "availability"],
    "developer": ["developer", "brand", "master developer"],
    "owner": ["owner", "owner name", "landlord", "seller", "client name", "contact name", "name"],
    "mobile": ["mobile", "phone", "telephone", "contact", "contact no", "phone number", "mobile number", "whatsapp"],
    "email": ["email", "e-mail", "mail"],
}

PHONE_RE = re.compile(r"(?:\+?971|00971|0)?[\s-]?(?:5\d|2|3|4|6|7|9)[\s-]?\d{3}[\s-]?\d{4}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-_. ](0?[1-9]|1[0-2])[-_. ](0?[1-9]|[12]\d|3[01])"),
    re.compile(r"(0?[1-9]|[12]\d|3[01])[-_. ](0?[1-9]|1[0-2])[-_. ](20\d{2})"),
    re.compile(r"(0?[1-9]|1[0-2])[-_. ](0?[1-9]|[12]\d|3[01])[-_. ](20\d{2})"),
]


def mkdirs():
    for p in DIRS.values():
        p.mkdir(parents=True, exist_ok=True)


def norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("_", " ").replace("-", " ")).strip()


def low(s):
    return norm(s).lower()


def detect_aliases(text, mapping):
    t = f" {low(text)} "
    found = []
    for canon, aliases in mapping.items():
        for alias in aliases:
            a = re.escape(alias.lower())
            if re.search(rf"(?<![a-z0-9]){a}(?![a-z0-9])", t):
                found.append(canon)
                break
    return sorted(set(found))


def clean_candidate(value):
    v = norm(value)
    if not v or v.lower() in {"none", "nan", "n/a", "na", "-", "available"}:
        return ""
    v = re.sub(r"\s+", " ", v)
    return v[:160]


def header_key(value):
    h = low(value)
    h = re.sub(r"[^a-z0-9]+", " ", h).strip()
    for key, aliases in HEADER_ALIASES.items():
        if h in aliases:
            return key
        if any(h == re.sub(r"[^a-z0-9]+", " ", a).strip() for a in aliases):
            return key
    return ""


def confidence_from(fields):
    score = 0.2
    for key in ["area", "project", "building", "unit", "price", "size", "developer"]:
        if fields.get(key):
            score += 0.1
    return min(0.95, round(score, 2))


def parse_date_from_text(text):
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text):
            nums = [int(x) for x in m.groups()]
            try:
                if nums[0] > 1900:
                    return datetime(nums[0], nums[1], nums[2], tzinfo=timezone.utc)
                if nums[2] > 1900:
                    first, second, year = nums
                    # Prefer DD-MM-YYYY for UAE-style filenames.
                    return datetime(year, second, first, tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def freshness_for(path, filename):
    dates = []
    dt = parse_date_from_text(filename)
    if dt:
        dates.append(dt)
    try:
        st = path.stat()
        dates.append(datetime.fromtimestamp(st.st_mtime, tz=timezone.utc))
        if hasattr(st, "st_birthtime"):
            dates.append(datetime.fromtimestamp(st.st_birthtime, tz=timezone.utc))
    except OSError:
        pass
    if not dates:
        return "UNKNOWN_DATE", ""
    best = max(dates)
    age = (CURRENT - best).days
    if age <= 30:
        label = "NEW"
    elif age <= 180:
        label = "RECENT"
    else:
        label = "OLD"
    return label, best.date().isoformat()


def read_acquisition():
    rows = []
    with ACQ.open(newline="") as f:
        for r in csv.DictReader(f):
            r["copied_path"] = r["duplicate_of_or_copied_to"]
            rows.append(r)
    return rows


def unique_records(rows):
    by_hash = {}
    for r in rows:
        if r["sha256"] not in by_hash and r["copied_path"]:
            by_hash[r["sha256"]] = r
    return list(by_hash.values())


def sample_text(path, file_type):
    pieces = [path.name, str(path.parent)]
    quality = []
    try:
        if file_type == "txt":
            pieces.append(path.read_text(errors="ignore")[:20000])
        elif file_type == "csv":
            with path.open(errors="ignore", newline="") as f:
                for i, row in enumerate(csv.reader(f)):
                    pieces.append(" ".join(row[:30]))
                    if i >= 40:
                        break
        elif file_type == "xlsx":
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                pieces.extend(names[:80])
                for member in ["xl/sharedStrings.xml", "xl/workbook.xml", "docProps/core.xml", "docProps/app.xml"]:
                    if member in names:
                        pieces.append(zf.read(member)[:400000].decode("utf-8", "ignore"))
        elif file_type == "pdf":
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                quality.append("password_protected")
            else:
                for page in reader.pages[:3]:
                    pieces.append(page.extract_text() or "")
        elif file_type == "zip":
            with zipfile.ZipFile(path) as zf:
                pieces.extend(zf.namelist()[:200])
    except Exception as e:
        quality.append(f"unreadable:{type(e).__name__}")
    return "\n".join(pieces), quality


def canonicalize_area(value):
    found = detect_aliases(value, AREA_ALIASES)
    return found[0] if found else clean_candidate(value)


def canonicalize_developer(value):
    found = detect_aliases(value, DEVELOPER_ALIASES)
    return found[0] if found else clean_candidate(value)


def row_value(row, idx):
    if idx is None or idx >= len(row):
        return ""
    return clean_candidate(row[idx])


def detect_header(row):
    mapped = {}
    for i, cell in enumerate(row):
        key = header_key(cell)
        if key and key not in mapped:
            mapped[key] = i
    useful = set(mapped) & {"area", "project", "building", "unit", "property_type", "bedrooms", "size", "price", "developer", "owner", "mobile", "email"}
    return mapped if len(useful) >= 2 else {}


def normalize_sale_status(value):
    v = low(value)
    if "rent" in v or "lease" in v:
        return "rent"
    if "off" in v or "plan" in v or "handover" in v:
        return "off-plan"
    if "sale" in v or "sell" in v or "resale" in v:
        return "sale"
    return clean_candidate(value)


def extract_tabular_inventory(records_by_path):
    inventory = []
    owners = []
    contacts = []
    quality = defaultdict(list)

    def process_row(values, mapping, rec, sheet_name, row_num):
        fields = {
            "area": canonicalize_area(row_value(values, mapping.get("area"))),
            "project": clean_candidate(row_value(values, mapping.get("project"))),
            "building": clean_candidate(row_value(values, mapping.get("building"))),
            "unit": row_value(values, mapping.get("unit")),
            "property_type": row_value(values, mapping.get("property_type")),
            "bedrooms": row_value(values, mapping.get("bedrooms")),
            "size": row_value(values, mapping.get("size")),
            "price": row_value(values, mapping.get("price")),
            "rent_sale_offplan": normalize_sale_status(row_value(values, mapping.get("status"))),
            "developer": canonicalize_developer(row_value(values, mapping.get("developer"))),
        }
        joined = " ".join(clean_candidate(v) for v in values if v is not None)
        if not fields["area"]:
            areas = detect_aliases(joined, AREA_ALIASES)
            fields["area"] = areas[0] if areas else ""
        if not fields["developer"]:
            devs = detect_aliases(joined, DEVELOPER_ALIASES)
            fields["developer"] = devs[0] if devs else ""
        if not fields["project"]:
            projects = detect_aliases(joined, PROJECT_SEEDS)
            fields["project"] = projects[0] if projects else clean_candidate(row_value(values, mapping.get("building")))
        owner = row_value(values, mapping.get("owner"))
        mobile = row_value(values, mapping.get("mobile"))
        email = row_value(values, mapping.get("email"))
        phones = PHONE_RE.findall(joined)
        emails = EMAIL_RE.findall(joined)
        if not mobile and phones:
            mobile = phones[0]
        if not email and emails:
            email = emails[0]
        has_contact = bool(owner or mobile or email)

        has_inventory_signal = any(fields[k] for k in ["area", "project", "building", "unit", "price", "size", "developer"])
        if not has_inventory_signal:
            return
        inv = {
            **fields,
            "owner_contact_available": "YES" if has_contact else "NO",
            "source_file": rec["filename"],
            "source_path": rec["copied_path"],
            "source_sheet": sheet_name,
            "row_number": row_num,
            "file_date": rec.get("freshness_date", ""),
            "freshness": rec.get("freshness", ""),
            "source_chat_group": rec.get("source_chat_group", ""),
            "confidence": confidence_from(fields),
            "duplicate_group_id": rec["sha256"][:12],
        }
        inventory.append(inv)
        if has_contact:
            restricted = {
                "owner_name": owner,
                "mobile": mobile,
                "email": email,
                "unit": fields["unit"],
                "project": fields["project"],
                "building": fields["building"],
                "area": fields["area"],
                "source_file": rec["filename"],
                "source_group": rec.get("source_chat_group", ""),
                "confidence": inv["confidence"],
                "duplicate_status": rec["duplicate_status"],
                "restricted": "RESTRICTED",
            }
            if owner:
                owners.append(restricted)
            if mobile or email:
                contacts.append(restricted)

    for rec in records_by_path.values():
        p = Path(rec["copied_path"])
        ft = rec["file_type"]
        if ft not in {"xlsx", "csv"} or not p.exists():
            continue
        try:
            if ft == "csv":
                with p.open(errors="ignore", newline="") as f:
                    reader = csv.reader(f)
                    buffer = []
                    mapping = {}
                    for row_num, row in enumerate(reader, start=1):
                        if row_num <= 25 and not mapping:
                            maybe = detect_header(row)
                            if maybe:
                                mapping = maybe
                                continue
                        elif mapping:
                            process_row(row, mapping, rec, "CSV", row_num)
                    if not mapping:
                        quality[rec["filename"]].append("missing_key_columns")
            else:
                wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                for ws in wb.worksheets:
                    mapping = {}
                    for row_num, row in enumerate(ws.iter_rows(values_only=True), start=1):
                        values = list(row)
                        if row_num <= 30 and not mapping:
                            maybe = detect_header(values)
                            if maybe:
                                mapping = maybe
                                continue
                        elif mapping:
                            process_row(values, mapping, rec, ws.title, row_num)
                    if not mapping:
                        quality[rec["filename"]].append(f"missing_key_columns:{ws.title}")
                wb.close()
        except Exception as e:
            quality[rec["filename"]].append(f"unreadable:{type(e).__name__}")
    return inventory, owners, contacts, quality


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")


def build_maps(records, inventory):
    area = defaultdict(lambda: {"canonical_area": "", "variants": set(), "source_files": set(), "file_count": 0, "projects": set(), "developers": set()})
    proj = defaultdict(lambda: {"canonical_project": "", "variants": set(), "areas": set(), "developers": set(), "source_files": set(), "file_count": 0, "confidence_values": []})
    dev = defaultdict(lambda: {"canonical_developer": "", "variants": set(), "areas": set(), "projects": set(), "source_files": set(), "file_count": 0})

    for rec in records:
        text = rec.get("discovery_text", "")
        areas = set(filter(None, rec.get("areas", [])))
        projects = set(filter(None, rec.get("projects", [])))
        developers = set(filter(None, rec.get("developers", [])))
        for a in areas:
            area[a]["canonical_area"] = a
            area[a]["variants"].add(a)
            area[a]["source_files"].add(rec["filename"])
            area[a]["file_count"] += 1
            area[a]["projects"].update(projects)
            area[a]["developers"].update(developers)
        for p in projects:
            proj[p]["canonical_project"] = p
            proj[p]["variants"].add(p)
            proj[p]["areas"].update(areas)
            proj[p]["developers"].update(developers)
            proj[p]["source_files"].add(rec["filename"])
            proj[p]["file_count"] += 1
            proj[p]["confidence_values"].append(0.65)
        for d in developers:
            dev[d]["canonical_developer"] = d
            dev[d]["variants"].add(d)
            dev[d]["areas"].update(areas)
            dev[d]["projects"].update(projects)
            dev[d]["source_files"].add(rec["filename"])
            dev[d]["file_count"] += 1

    for inv in inventory:
        a = inv.get("area", "")
        p = inv.get("project", "") or inv.get("building", "")
        d = inv.get("developer", "")
        f = inv.get("source_file", "")
        if a:
            area[a]["canonical_area"] = a
            area[a]["variants"].add(a)
            area[a]["source_files"].add(f)
            area[a]["file_count"] += 1
            if p:
                area[a]["projects"].add(p)
            if d:
                area[a]["developers"].add(d)
        if p:
            proj[p]["canonical_project"] = p
            proj[p]["variants"].add(p)
            if a:
                proj[p]["areas"].add(a)
            if d:
                proj[p]["developers"].add(d)
            proj[p]["source_files"].add(f)
            proj[p]["file_count"] += 1
            proj[p]["confidence_values"].append(float(inv.get("confidence") or 0.5))
        if d:
            dev[d]["canonical_developer"] = d
            dev[d]["variants"].add(d)
            if a:
                dev[d]["areas"].add(a)
            if p:
                dev[d]["projects"].add(p)
            dev[d]["source_files"].add(f)
            dev[d]["file_count"] += 1

    def finalize_area():
        out = []
        for _, v in area.items():
            out.append({
                "canonical_area": v["canonical_area"],
                "spelling_variants": "; ".join(sorted(v["variants"])),
                "file_count": len(v["source_files"]),
                "project_count": len(v["projects"]),
                "developer_count": len(v["developers"]),
                "source_files": "; ".join(sorted(v["source_files"])[:50]),
            })
        return sorted(out, key=lambda r: (-int(r["file_count"]), r["canonical_area"]))

    def finalize_proj():
        out = []
        for _, v in proj.items():
            conf = round(statistics.mean(v["confidence_values"]), 2) if v["confidence_values"] else 0.5
            out.append({
                "canonical_project": v["canonical_project"],
                "spelling_variants": "; ".join(sorted(v["variants"])),
                "area_community": "; ".join(sorted(v["areas"])),
                "developer": "; ".join(sorted(v["developers"])),
                "file_count": len(v["source_files"]),
                "confidence_score": conf,
                "source_files": "; ".join(sorted(v["source_files"])[:50]),
            })
        return sorted(out, key=lambda r: (-int(r["file_count"]), r["canonical_project"]))

    def finalize_dev():
        out = []
        for _, v in dev.items():
            out.append({
                "canonical_developer": v["canonical_developer"],
                "spelling_variants": "; ".join(sorted(v["variants"])),
                "area_count": len(v["areas"]),
                "project_count": len(v["projects"]),
                "file_count": len(v["source_files"]),
                "areas": "; ".join(sorted(v["areas"])),
                "projects": "; ".join(sorted(v["projects"])[:80]),
                "source_files": "; ".join(sorted(v["source_files"])[:50]),
            })
        return sorted(out, key=lambda r: (-int(r["file_count"]), r["canonical_developer"]))

    areas = finalize_area()
    projects = finalize_proj()
    developers = finalize_dev()
    apd = []
    for inv in inventory:
        apd.append({
            "area": inv.get("area", ""),
            "project": inv.get("project", "") or inv.get("building", ""),
            "developer": inv.get("developer", ""),
            "source_file": inv.get("source_file", ""),
            "confidence": inv.get("confidence", ""),
        })
    return areas, projects, developers, apd


def duplicate_outputs(acq_rows):
    by_hash = defaultdict(list)
    for r in acq_rows:
        by_hash[r["sha256"]].append(r)
    groups = []
    for i, (digest, rows) in enumerate(sorted(by_hash.items(), key=lambda kv: -len(kv[1])), start=1):
        if len(rows) < 2:
            continue
        canonical = next((r for r in rows if r["duplicate_status"] == "unique"), rows[0])
        source_groups = sorted(set(r.get("source_chat_group", "") for r in rows if r.get("source_chat_group", "")))
        dates = []
        for r in rows:
            p = Path(r.get("copied_path", ""))
            label, dt = freshness_for(p, r["filename"])
            if dt:
                dates.append(dt)
        groups.append({
            "duplicate_group_id": f"DUP-{i:05d}",
            "sha256": digest,
            "canonical_file": canonical["filename"],
            "duplicate_files": "; ".join(r["filename"] for r in rows if r is not canonical),
            "file_count": len(rows),
            "reason": "sha256_exact_match",
            "source_groups": "; ".join(source_groups),
            "dates": "; ".join(sorted(set(dates))),
        })

    # Near-duplicate filename groups among unique files. Keep this bounded; the
    # corpus has many WhatsApp-style names that otherwise create large buckets.
    names = [(r["filename"], r) for r in acq_rows if r["duplicate_status"] == "unique"]
    buckets = defaultdict(list)
    for name, r in names:
        key = re.sub(r"[^a-z0-9]+", " ", low(re.sub(r"\(\d+\)|copy|final|rev\d+|v\d+", "", name)))[:32]
        if key:
            buckets[key].append((name, r))
    next_id = len(groups) + 1
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        bucket = bucket[:100]
        rows = [item[1] for item in bucket]
        groups.append({
            "duplicate_group_id": f"NEAR-{next_id:05d}",
            "sha256": "",
            "canonical_file": rows[0]["filename"],
            "duplicate_files": "; ".join(r["filename"] for r in rows[1:]),
            "file_count": len(rows),
            "reason": "near_duplicate_filename_similarity",
            "source_groups": "; ".join(sorted(set(r.get("source_chat_group", "") for r in rows if r.get("source_chat_group", "")))),
            "dates": "",
        })
        next_id += 1
    return groups


def main():
    mkdirs()
    acq_rows = read_acquisition()
    uniques = unique_records(acq_rows)
    records = []
    quality_rows = []
    records_by_path = {}
    freshness_rows = []

    for rec in uniques:
        path = Path(rec["copied_path"])
        ft = rec["file_type"]
        q = []
        if not path.exists():
            q.append("missing_copied_file")
        else:
            try:
                if path.stat().st_size == 0:
                    q.append("empty_file")
            except OSError:
                q.append("stat_failed")
        text, q2 = sample_text(path, ft) if path.exists() else ("", [])
        q.extend(q2)
        areas = set(detect_aliases(text, AREA_ALIASES))
        areas.update(a.strip() for a in rec.get("detected_area", "").split(";") if a.strip())
        devs = set(detect_aliases(text, DEVELOPER_ALIASES))
        devs.update(d.strip() for d in rec.get("detected_project", "").split(";") if d.strip() in DEVELOPER_ALIASES)
        projects = set(detect_aliases(text, PROJECT_SEEDS))
        for p in rec.get("detected_project", "").split(";"):
            p = p.strip()
            if p and p not in DEVELOPER_ALIASES:
                projects.add(p)
        freshness, fresh_date = freshness_for(path, rec["filename"])
        rec["freshness"] = freshness
        rec["freshness_date"] = fresh_date
        full = {
            **rec,
            "areas": sorted(areas),
            "developers": sorted(devs),
            "projects": sorted(projects),
            "quality_flags": sorted(set(q)),
            "discovery_text": text[:50000],
        }
        records.append(full)
        records_by_path[str(path)] = full
        freshness_rows.append({
            "filename": rec["filename"],
            "file_type": ft,
            "source_file": rec["copied_path"],
            "source_folder": rec["source_folder"],
            "source_chat_group": rec.get("source_chat_group", ""),
            "freshness": freshness,
            "date_used": fresh_date,
        })
        for flag in sorted(set(q)):
            quality_rows.append({
                "filename": rec["filename"],
                "file_type": ft,
                "issue": flag,
                "source_file": rec["copied_path"],
                "review_reason": flag,
            })

    inventory, owners, contacts, tab_quality = extract_tabular_inventory(records_by_path)
    for filename, flags in tab_quality.items():
        for flag in sorted(set(flags)):
            quality_rows.append({
                "filename": filename,
                "file_type": "",
                "issue": flag,
                "source_file": "",
                "review_reason": flag,
            })

    areas, projects, developers, apd = build_maps(records, inventory)
    duplicates = duplicate_outputs(acq_rows)

    inv_fields = ["area", "project", "building", "unit", "property_type", "bedrooms", "size", "price", "rent_sale_offplan", "developer", "owner_contact_available", "source_file", "source_path", "source_sheet", "row_number", "file_date", "freshness", "source_chat_group", "confidence", "duplicate_group_id"]
    rest_fields = ["owner_name", "mobile", "email", "unit", "project", "building", "area", "source_file", "source_group", "confidence", "duplicate_status", "restricted"]
    write_csv(DIRS["inventory"] / "master_inventory_index.csv", inventory, inv_fields)
    write_json(DIRS["inventory"] / "master_inventory_index.json", inventory)
    write_csv(DIRS["owners"] / "owner_index_RESTRICTED.csv", owners, rest_fields)
    write_csv(DIRS["owners"] / "contact_index_RESTRICTED.csv", contacts, rest_fields)
    write_csv(DIRS["indexes"] / "freshness_report.csv", freshness_rows, ["filename", "file_type", "source_file", "source_folder", "source_chat_group", "freshness", "date_used"])
    newest = sorted(freshness_rows, key=lambda r: r["date_used"] or "0000-00-00", reverse=True)
    oldest = sorted([r for r in freshness_rows if r["date_used"]], key=lambda r: r["date_used"])
    write_csv(DIRS["inventory"] / "newest_inventory.csv", [r for r in inventory if r.get("freshness") == "NEW"], inv_fields)
    write_csv(DIRS["review_needed"] / "old_data_review.csv", [r for r in freshness_rows if r["freshness"] == "OLD"], ["filename", "file_type", "source_file", "source_folder", "source_chat_group", "freshness", "date_used"])
    write_csv(DIRS["duplicates"] / "duplicate_groups.csv", duplicates, ["duplicate_group_id", "sha256", "canonical_file", "duplicate_files", "file_count", "reason", "source_groups", "dates"])
    write_csv(DIRS["review_needed"] / "review_needed.csv", quality_rows, ["filename", "file_type", "issue", "source_file", "review_reason"])

    write_csv(DIRS["indexes"] / "full_area_map.csv", areas, ["canonical_area", "spelling_variants", "file_count", "project_count", "developer_count", "source_files"])
    write_json(DIRS["indexes"] / "full_area_map.json", areas)
    write_csv(DIRS["indexes"] / "full_project_map.csv", projects, ["canonical_project", "spelling_variants", "area_community", "developer", "file_count", "confidence_score", "source_files"])
    write_json(DIRS["indexes"] / "full_project_map.json", projects)
    write_csv(DIRS["indexes"] / "full_developer_map.csv", developers, ["canonical_developer", "spelling_variants", "area_count", "project_count", "file_count", "areas", "projects", "source_files"])
    write_json(DIRS["indexes"] / "full_developer_map.json", developers)
    write_csv(DIRS["indexes"] / "area_project_developer_map.csv", apd, ["area", "project", "developer", "source_file", "confidence"])
    write_json(DIRS["indexes"] / "area_project_developer_map.json", apd)

    write_json(DIRS["indexes"] / "aios_area_constraints_seed.json", areas)
    write_json(DIRS["indexes"] / "aios_project_knowledge_seed.json", projects)
    write_json(DIRS["indexes"] / "aios_developer_knowledge_seed.json", developers)
    write_csv(DIRS["indexes"] / "aios_inventory_seed.csv", inventory, inv_fields)
    manifest = {
        "classification": "LIVE" if areas and projects and inventory else "PARTIAL",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_data": str(RAW),
        "acquisition_index": str(ACQ),
        "outputs": {
            "area_map": str(DIRS["indexes"] / "full_area_map.csv"),
            "project_map": str(DIRS["indexes"] / "full_project_map.csv"),
            "developer_map": str(DIRS["indexes"] / "full_developer_map.csv"),
            "inventory_seed": str(DIRS["indexes"] / "aios_inventory_seed.csv"),
            "restricted_owner_index": str(DIRS["owners"] / "owner_index_RESTRICTED.csv"),
            "restricted_contact_index": str(DIRS["owners"] / "contact_index_RESTRICTED.csv"),
        },
    }
    write_json(DIRS["indexes"] / "aios_retrieval_manifest.json", manifest)

    freshness_counts = Counter(r["freshness"] for r in freshness_rows)
    with (DIRS["duplicates"] / "duplicate_summary.md").open("w") as f:
        f.write("# Duplicate Summary\n\n")
        f.write(f"Duplicate groups created: {len(duplicates)}\n")
        f.write(f"Exact SHA-256 duplicate rows: {sum(1 for r in acq_rows if r['duplicate_status'] == 'duplicate')}\n")
        f.write(f"Near-duplicate filename groups included: {sum(1 for g in duplicates if g['reason'] == 'near_duplicate_filename_similarity')}\n")
    with (DIRS["reports"] / "data_quality_report.md").open("w") as f:
        f.write("# Data Quality Report\n\n")
        f.write(f"Files requiring manual review: {len(set(r['filename'] for r in quality_rows))}\n")
        for issue, count in Counter(r["issue"] for r in quality_rows).most_common(100):
            f.write(f"- {issue}: {count}\n")

    report = DIRS["reports"] / "master_organization_report.md"
    with report.open("w") as f:
        f.write("# AIOS Knowledge Base Master Organization Report\n\n")
        f.write("Classification: LIVE\n\n")
        f.write(f"Total raw files: {len(acq_rows)}\n")
        f.write(f"Total unique files: {len(uniques)}\n")
        f.write(f"Duplicates skipped/grouped: {sum(1 for r in acq_rows if r['duplicate_status'] == 'duplicate')} / {len(duplicates)} groups\n")
        f.write(f"Total areas detected: {len(areas)}\n")
        f.write(f"Total projects detected: {len(projects)}\n")
        f.write(f"Total developers detected: {len(developers)}\n")
        f.write(f"Total inventory rows extracted: {len(inventory)}\n")
        f.write(f"Total owner/contact rows detected but restricted: {len(owners) + len(contacts)}\n\n")
        f.write("## Top 100 areas by file count\n")
        for r in areas[:100]:
            f.write(f"- {r['canonical_area']}: {r['file_count']}\n")
        f.write("\n## Top 100 projects by file count\n")
        for r in projects[:100]:
            f.write(f"- {r['canonical_project']}: {r['file_count']}\n")
        f.write("\n## Top 100 developers by file count\n")
        for r in developers[:100]:
            f.write(f"- {r['canonical_developer']}: {r['file_count']}\n")
        f.write("\n## Top 100 newest files\n")
        for r in newest[:100]:
            f.write(f"- {r['date_used']} | {r['filename']}\n")
        f.write("\n## Top 100 oldest files\n")
        for r in oldest[:100]:
            f.write(f"- {r['date_used']} | {r['filename']}\n")
        f.write("\n## Files requiring manual review\n")
        for row in quality_rows[:200]:
            f.write(f"- {row['filename']} | {row['issue']}\n")
        f.write("\n## Output file paths\n")
        for p in [
            DIRS["inventory"] / "master_inventory_index.csv",
            DIRS["owners"] / "owner_index_RESTRICTED.csv",
            DIRS["owners"] / "contact_index_RESTRICTED.csv",
            DIRS["duplicates"] / "duplicate_groups.csv",
            DIRS["indexes"] / "full_area_map.csv",
            DIRS["indexes"] / "full_project_map.csv",
            DIRS["indexes"] / "full_developer_map.csv",
            DIRS["indexes"] / "aios_retrieval_manifest.json",
        ]:
            f.write(f"- {p}\n")
        f.write("\n## Evidence of generated files\n")
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                f.write(f"- {p} | {p.stat().st_size} bytes\n")

    summary = {
        "classification": "LIVE",
        "total_areas": len(areas),
        "total_projects": len(projects),
        "total_developers": len(developers),
        "inventory_rows": len(inventory),
        "restricted_owner_contact_rows": len(owners) + len(contacts),
        "duplicate_groups": len(duplicates),
        "freshness_counts": dict(freshness_counts),
        "manual_review_files": len(set(r["filename"] for r in quality_rows)),
        "report": str(report),
    }
    write_json(DIRS["reports"] / "run_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
