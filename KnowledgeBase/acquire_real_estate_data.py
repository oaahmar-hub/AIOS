#!/usr/bin/env python3
import csv
import hashlib
import os
import re
import shutil
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path("/Users/hassanka")
AIOS_ROOT = HOME / "Downloads" / "AIOS"
KB_ROOT = AIOS_ROOT / "KnowledgeBase"
RAW_ROOT = KB_ROOT / "raw_data"
INDEX_PATH = KB_ROOT / "acquisition_index.csv"
REPORT_PATH = KB_ROOT / "acquisition_report.md"
WHATSAPP_SHARED = HOME / "Library" / "Group Containers" / "group.net.whatsapp.WhatsApp.shared"
WHATSAPP_MEDIA = WHATSAPP_SHARED / "Message" / "Media"
WHATSAPP_DB = WHATSAPP_SHARED / "ChatStorage.sqlite"

DOC_EXTS = {".xlsx", ".csv", ".pdf", ".txt", ".zip"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALL_EXTS = DOC_EXTS | IMAGE_EXTS
FOLDER_BY_EXT = {
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".pdf": "pdf",
    ".txt": "txt",
    ".zip": "zip",
    ".jpg": "images",
    ".jpeg": "images",
    ".png": "images",
    ".webp": "images",
    ".heic": "images",
}

ROOTS = [
    HOME / "Downloads",
    HOME / "Documents",
    HOME / "Desktop",
    AIOS_ROOT,
]

AREA_PATTERNS = {
    "Dubai Hills": [r"dubai\s+hills"],
    "Downtown": [r"downtown", r"downtown\s+dubai"],
    "Business Bay": [r"business\s+bay"],
    "JVC": [r"\bjvc\b", r"jumeirah\s+village\s+circle"],
    "JVT": [r"\bjvt\b", r"jumeirah\s+village\s+triangle"],
    "Al Furjan": [r"\bal\s+furjan\b", r"\bfurjan\b"],
    "Dubai Marina": [r"dubai\s+marina", r"\bmarina\b"],
    "Palm Jumeirah": [r"palm\s+jumeirah", r"\bpj-p-vp\b", r"\bpalm\b"],
    "JLT": [r"\bjlt\b", r"jumeirah\s+lake\s+towers"],
    "JBR": [r"\bjbr\b", r"jumeirah\s+beach\s+residence"],
    "Creek Harbour": [r"creek\s+harbour", r"dubai\s+creek"],
    "Meydan": [r"\bmeydan\b"],
    "Meydan One": [r"meydan\s+one"],
    "MBR City": [r"\bmbr\b", r"mohammed\s+bin\s+rashid"],
    "Arjan": [r"\barjan\b"],
    "Dubai South": [r"dubai\s+south"],
    "Emaar South": [r"emaar\s+south"],
    "Town Square": [r"town\s+square"],
    "Arabian Ranches": [r"arabian\s+ranches"],
    "Dubai Islands": [r"dubai\s+islands"],
    "Sobha Hartland": [r"sobha\s+hartland"],
    "Yas Island": [r"yas\s+island"],
    "Saadiyat": [r"\bsaadiyat\b"],
    "Reem Island": [r"reem\s+island", r"\bal\s+reem\b"],
    "Al Raha": [r"\bal\s+raha\b"],
    "Port De La Mer": [r"port\s+de\s+la\s+mer", r"\bla\s+mer\b"],
    "Palm Jebel Ali": [r"palm\s+jebel\s+ali"],
    "Damac Hills": [r"damac\s+hills"],
    "Dubai Land": [r"dubai\s*land", r"dubailand"],
    "Dubai Investment Park": [r"\bdip\b", r"dubai\s+investment\s+park"],
    "Dubai Silicon Oasis": [r"\bdso\b", r"dubai\s+silicon\s+oasis"],
    "Dubai Sports City": [r"sports\s+city"],
    "Dubai Production City": [r"production\s+city", r"\bimpz\b"],
    "Dubai Healthcare City": [r"healthcare\s+city"],
    "Dubai Maritime City": [r"maritime\s+city"],
    "Dubai Science Park": [r"science\s+park"],
    "Dubai Studio City": [r"studio\s+city"],
    "Dubai Waterfront": [r"dubai\s+waterfront"],
    "Emaar Beachfront": [r"emaar\s+beachfront"],
    "Bluewaters": [r"bluewaters"],
    "City Walk": [r"city\s+walk"],
    "Jumeirah": [r"\bjumeirah\b"],
    "Jumeirah Golf Estates": [r"jumeirah\s+golf\s+estates"],
    "Jumeirah Park": [r"jumeirah\s+park"],
    "Jumeirah Islands": [r"jumeirah\s+islands"],
    "Jumeirah Bay": [r"jumeirah\s+bay"],
    "Jumeirah Heights": [r"jumeirah\s+heights"],
    "Jumeirah Village": [r"jumeirah\s+village"],
    "Al Barsha": [r"\bal\s+barsha\b"],
    "Barsha Heights": [r"barsha\s+heights", r"\btecom\b"],
    "Al Wasl": [r"\bal\s+wasl\b"],
    "Al Quoz": [r"\bal\s+quoz\b"],
    "Deira": [r"\bdeira\b"],
    "Bur Dubai": [r"bur\s+dubai"],
    "Dubai Festival City": [r"festival\s+city"],
    "Dubai Harbour": [r"dubai\s+harbou?r"],
    "Discovery Gardens": [r"discovery\s+gardens"],
    "International City": [r"international\s+city"],
    "Motor City": [r"motor\s+city"],
    "Mudon": [r"\bmudon\b"],
    "Nad Al Sheba": [r"nad\s+al\s+sheba"],
    "Tilal Al Ghaf": [r"tilal\s+al\s+ghaf"],
    "The Greens": [r"the\s+greens"],
    "The Springs": [r"the\s+springs"],
    "The Meadows": [r"the\s+meadows"],
    "The Lakes": [r"the\s+lakes"],
    "Umm Suqeim": [r"umm\s+suqeim"],
    "Wadi Al Safa": [r"wadi\s+al\s+safa"],
    "World Islands": [r"world\s+islands"],
    "Abu Dhabi": [r"abu\s+dhabi"],
    "Sharjah": [r"\bsharjah\b"],
    "Ajman": [r"\bajman\b"],
    "Ras Al Khaimah": [r"ras\s+al\s+khaimah", r"\brak\b"],
}

PROJECT_PATTERNS = {
    "Reportage": [r"\breportage\b"],
    "Binghatti": [r"\bbinghatti\b"],
    "Deyaar": [r"\bdeyaar\b"],
    "Tiger": [r"\btiger\b"],
    "Object1": [r"\bobject\s*1\b", r"\bobject1\b"],
    "HSH": [r"\bhsh\b", r"home\s+sweet\s+home"],
    "DCR": [r"\bdcr\b"],
    "Nakheel": [r"\bnakheel\b"],
    "Emaar": [r"\bemaar\b"],
    "Damac": [r"\bdamac\b"],
    "Sobha": [r"\bsobha\b"],
    "Meraas": [r"\bmeraas\b"],
    "Azizi": [r"\bazizi\b"],
    "Danube": [r"\bdanube\b"],
    "Ellington": [r"\bellington\b"],
    "Omniyat": [r"\bomniyat\b"],
    "Aldar": [r"\baldar\b"],
    "Mag": [r"\bmag\b"],
    "Select Group": [r"select\s+group"],
    "Dubai Holding": [r"dubai\s+holding"],
    "Palm Crown": [r"palm\s+crown"],
    "Tiger Sky Tower": [r"tiger\s+sky\s+tower"],
    "Sadaf": [r"\bsadaf\b"],
    "Oxford Terraces": [r"oxford\s+terraces"],
}

FOCUS_TERMS = [
    "data",
    "data pack",
    "data pak",
    "uae data",
    "database",
    "inventory",
    "reportage",
    "binghatti",
    "deyaar",
    "tiger",
    "object1",
    "hsh",
    "dcr",
    "commercial",
    "abu dhabi",
    "dubai",
]


def ensure_dirs():
    for folder in ["xlsx", "csv", "pdf", "txt", "zip", "images", "unknown"]:
        (RAW_ROOT / folder).mkdir(parents=True, exist_ok=True)


def norm_text(value):
    return re.sub(r"\s+", " ", (value or "").replace("_", " ").replace("-", " ")).strip().lower()


def detect(patterns, text):
    found = []
    for label, regexes in patterns.items():
        for regex in regexes:
            if re.search(regex, text, flags=re.I):
                found.append(label)
                break
    return sorted(set(found))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(path):
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", path.stem).strip(" .") or "file"
    ext = path.suffix.lower()
    return f"{stem}{ext}"


def unique_dest(path, digest):
    folder = FOLDER_BY_EXT.get(path.suffix.lower(), "unknown")
    short = digest[:12]
    return RAW_ROOT / folder / f"{short}__{safe_name(path)}"


def whatsapp_metadata():
    meta = {}
    missing = []
    if not WHATSAPP_DB.exists():
        return meta, ["WhatsApp ChatStorage.sqlite not found"]
    con = sqlite3.connect(str(WHATSAPP_DB))
    con.row_factory = sqlite3.Row
    sql = """
        select
            mi.ZMEDIALOCALPATH as media_path,
            mi.ZTITLE as title,
            mi.ZFILESIZE as db_size,
            m.ZTEXT as message_text,
            m.ZFROMJID as from_jid,
            m.ZTOJID as to_jid,
            cs.ZCONTACTJID as chat_jid,
            cs.ZPARTNERNAME as chat_name
        from ZWAMEDIAITEM mi
        left join ZWAMESSAGE m on m.ZMEDIAITEM = mi.Z_PK
        left join ZWACHATSESSION cs on m.ZCHATSESSION = cs.Z_PK
        where mi.ZMEDIALOCALPATH is not null
    """
    for row in con.execute(sql):
        rel = (row["media_path"] or "").replace("Media/", "", 1)
        full = WHATSAPP_MEDIA / rel
        key = str(full)
        meta[key] = {
            "source_chat": row["chat_name"] or row["chat_jid"] or row["from_jid"] or row["to_jid"] or "",
            "source_jid": row["chat_jid"] or row["from_jid"] or row["to_jid"] or "",
            "message_text": row["message_text"] or row["title"] or "",
            "db_size": row["db_size"] or "",
        }
        if not full.exists():
            label = row["message_text"] or row["title"] or row["media_path"] or "unknown media"
            missing.append(f"{label} :: {row['chat_name'] or row['chat_jid'] or 'unknown chat'}")
    con.close()
    return meta, missing


def candidate_files():
    seen_paths = set()
    raw_root_resolved = RAW_ROOT.resolve()
    generated = {INDEX_PATH.resolve(), REPORT_PATH.resolve(), Path(__file__).resolve()}

    for root in ROOTS:
        if not root.exists():
            continue
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            try:
                resolved = current_path.resolve()
            except OSError:
                continue
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and "node_modules" not in d
                and "Library" not in d
                and not (resolved / d).resolve().is_relative_to(raw_root_resolved)
            ]
            for name in files:
                path = current_path / name
                ext = path.suffix.lower()
                if ext not in DOC_EXTS:
                    continue
                try:
                    resolved_file = path.resolve()
                except OSError:
                    continue
                if resolved_file in generated or str(resolved_file) in seen_paths:
                    continue
                seen_paths.add(str(resolved_file))
                yield path, "local"

    if WHATSAPP_MEDIA.exists():
        for current, dirs, files in os.walk(WHATSAPP_MEDIA):
            current_path = Path(current)
            for name in files:
                path = current_path / name
                ext = path.suffix.lower()
                if ext not in ALL_EXTS:
                    continue
                try:
                    resolved_file = path.resolve()
                except OSError:
                    continue
                if str(resolved_file) in seen_paths:
                    continue
                seen_paths.add(str(resolved_file))
                yield path, "whatsapp"


def text_sample(path, metadata_text=""):
    parts = [path.name, str(path.parent), metadata_text]
    ext = path.suffix.lower()
    try:
        if ext in {".txt", ".csv"}:
            parts.append(path.read_text(errors="ignore")[:4000])
        elif ext == ".xlsx":
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                parts.extend(names[:50])
                for member in [
                    "xl/sharedStrings.xml",
                    "xl/workbook.xml",
                    "docProps/core.xml",
                    "docProps/app.xml",
                ]:
                    if member in names:
                        with zf.open(member) as f:
                            parts.append(f.read(250000).decode("utf-8", "ignore"))
        elif ext == ".zip":
            with zipfile.ZipFile(path) as zf:
                parts.extend(zf.namelist()[:80])
    except Exception:
        pass
    return norm_text(" ".join(parts))


def classify_focus(text):
    hits = []
    for term in FOCUS_TERMS:
        if term in text:
            hits.append(term)
    return sorted(set(hits))


def write_report(rows, missing):
    total = len(rows)
    unique = sum(1 for r in rows if r["duplicate_status"] == "unique")
    duplicate = total - unique
    area_counts = Counter()
    project_counts = Counter()
    for row in rows:
        for area in row["detected_area"].split("; "):
            if area:
                area_counts[area] += 1
        for project in row["detected_project"].split("; "):
            if project:
                project_counts[project] += 1

    live_status = "LIVE" if unique and total else "FAILED"
    if missing:
        live_status = "PARTIAL" if unique else "FAILED"

    samples = [r["filename"] for r in rows if r["duplicate_status"] == "unique"][:25]
    evidence = [
        f"Knowledge base raw data path: {RAW_ROOT}",
        f"CSV index: {INDEX_PATH}",
        f"Report: {REPORT_PATH}",
        f"WhatsApp media path inspected: {WHATSAPP_MEDIA}",
        f"WhatsApp DB inspected: {WHATSAPP_DB}",
        "Duplicate detection: SHA-256 content hash",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
    ]

    lines = [
        "# AIOS Real Estate Data Acquisition Report",
        "",
        f"Classification: {live_status}",
        "",
        f"Total files found: {total}",
        f"Total unique files: {unique}",
        f"Duplicates skipped: {duplicate}",
        "",
        "## Areas detected",
    ]
    lines.extend(f"- {name}: {count}" for name, count in area_counts.most_common())
    if not area_counts:
        lines.append("- None detected")
    lines.append("")
    lines.append("## Projects detected")
    lines.extend(f"- {name}: {count}" for name, count in project_counts.most_common())
    if not project_counts:
        lines.append("- None detected")
    lines.append("")
    lines.append("## Missing downloads")
    if missing:
        lines.extend(f"- {item}" for item in missing[:200])
        if len(missing) > 200:
            lines.append(f"- ... {len(missing) - 200} more")
    else:
        lines.append("- None detected in WhatsApp local media database")
    lines.append("")
    lines.append("## Sample filenames")
    lines.extend(f"- {name}" for name in samples)
    lines.append("")
    lines.append("## Evidence")
    lines.extend(f"- {item}" for item in evidence)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main():
    ensure_dirs()
    wa_meta, missing = whatsapp_metadata()
    rows = []
    hash_first = {}

    for path, source_kind in candidate_files():
        if not path.exists() or not path.is_file():
            continue
        ext = path.suffix.lower()
        try:
            size = path.stat().st_size
            digest = sha256(path)
        except OSError:
            continue

        meta = wa_meta.get(str(path), {})
        source_chat = meta.get("source_chat", "") if source_kind == "whatsapp" else ""
        message_text = meta.get("message_text", "")
        sample = text_sample(path, message_text)
        areas = detect(AREA_PATTERNS, sample)
        projects = detect(PROJECT_PATTERNS, sample)
        focus = classify_focus(sample)

        duplicate_of = hash_first.get(digest, "")
        duplicate_status = "duplicate" if duplicate_of else "unique"
        copied_to = ""
        if not duplicate_of:
            dest = unique_dest(path, digest)
            if not dest.exists():
                shutil.copy2(path, dest)
            hash_first[digest] = str(dest)
            copied_to = str(dest)
        else:
            copied_to = duplicate_of

        rows.append({
            "filename": path.name,
            "file_type": ext.lstrip(".") or "unknown",
            "source_folder": str(path.parent),
            "source_chat_group": source_chat,
            "size_bytes": size,
            "detected_area": "; ".join(areas),
            "detected_project": "; ".join(projects),
            "focus_terms": "; ".join(focus),
            "duplicate_status": duplicate_status,
            "duplicate_of_or_copied_to": copied_to,
            "sha256": digest,
        })

    fieldnames = [
        "filename",
        "file_type",
        "source_folder",
        "source_chat_group",
        "size_bytes",
        "detected_area",
        "detected_project",
        "focus_terms",
        "duplicate_status",
        "duplicate_of_or_copied_to",
        "sha256",
    ]
    with INDEX_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    write_report(rows, missing)
    print(f"indexed={len(rows)} unique={sum(1 for r in rows if r['duplicate_status'] == 'unique')} duplicates={sum(1 for r in rows if r['duplicate_status'] == 'duplicate')} missing={len(missing)}")
    print(f"index={INDEX_PATH}")
    print(f"report={REPORT_PATH}")
    print(f"raw={RAW_ROOT}")


if __name__ == "__main__":
    main()
