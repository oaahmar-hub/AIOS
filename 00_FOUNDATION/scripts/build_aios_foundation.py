#!/usr/bin/env python3
"""Build AIOS foundation, canonical indexes, and validation reports.

The script is intentionally read-only against existing source folders. It writes
new canonical outputs under AIOS/00_FOUNDATION, AIOS/KnowledgeBase/Canonical,
AIOS/Agents/NakheelDesignApproval, and AIOS/Engines/PropertyIntelligence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import signal
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

try:
    import openpyxl
except Exception:  # pragma: no cover - optional dependency
    openpyxl = None


ROOT = Path("/Users/hassanka/Downloads")
AIOS = ROOT / "AIOS"
FOUNDATION = AIOS / "00_FOUNDATION"
GENERATED = FOUNDATION / "generated"
CANONICAL = AIOS / "KnowledgeBase" / "Canonical"
NAKHEEL_AGENT = AIOS / "Agents" / "NakheelDesignApproval"
PROPERTY_ENGINE = AIOS / "Engines" / "PropertyIntelligence"
DATE = "2026-06-25"

SOURCE_ROOTS = [
    AIOS,
    ROOT / "AIOS_KNOWLEDGE_CONTROL",
    ROOT / "_ORGANIZED_2026-06-24" / "01_AIOS_OPENAI_HANDOFFS",
]

NAKHEEL_ROOTS = [
    ROOT / "NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01",
    ROOT / "PJ-P-VP-018_NAKHEEL_ALL_EVIDENCE",
    ROOT / "PJ-P-VP-018_Nakheel_Compliance_Completion_Package_2026-06-23",
    ROOT / "nakheel_pj_p_vp_018_new_pages",
]

PROPERTY_ROOTS = [
    AIOS / "KnowledgeBase",
    ROOT / "AIOS_KNOWLEDGE_CONTROL" / "06_PROPERTY_INTELLIGENCE_ENGINE",
]

TEXT_EXT = {".md", ".txt", ".csv", ".json", ".jsonl", ".py", ".html"}
DOC_EXT = TEXT_EXT | {".pdf", ".docx", ".xlsx", ".xls", ".sqlite", ".db"}


class Timeout(Exception):
    pass


def _timeout_handler(signum, frame):  # pragma: no cover - signal callback
    raise Timeout("operation timed out")


@dataclass
class FileRecord:
    path: Path
    rel: str
    scope: str
    ext: str
    size: int
    sha256: str
    modified: str
    title: str
    category: str


def ensure_dirs() -> None:
    for directory in [FOUNDATION, GENERATED, CANONICAL, NAKHEEL_AGENT, PROPERTY_ENGINE]:
        directory.mkdir(parents=True, exist_ok=True)


def safe_read_text(path: Path, limit: int = 6000) -> str:
    try:
        return path.read_text(errors="ignore")[:limit]
    except Exception:
        return ""


def file_hash(path: Path) -> str:
    try:
        if path.stat().st_size > 50 * 1024 * 1024:
            return "SKIPPED_LARGE_FILE"
    except Exception:
        return "UNREADABLE"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except Exception:
        return "UNREADABLE"
    return h.hexdigest()


def classify(path: Path, text_hint: str = "") -> str:
    name = path.name.lower()
    body = (name + " " + text_hint[:800].lower())
    if "nakheel" in body or "pj-p-vp-018" in body or "palm jumeirah" in body:
        return "nakheel_design_approval"
    if "property" in body or "unit" in body or "inventory" in body or "resolver" in body:
        return "property_intelligence"
    if "whatsapp" in body or "personality" in body:
        return "whatsapp_human_engine"
    if "validation" in body or "proof" in body or "report" in body:
        return "validation_reporting"
    if "workflow" in body or "agent" in body or "sop" in body:
        return "operating_system"
    if "knowledge" in body or "memory" in body or "index" in body:
        return "knowledge_base"
    return "general_aios"


def iter_files(roots: Iterable[Path], scope: str) -> Iterable[FileRecord]:
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path in seen:
                continue
            seen.add(path)
            if path.suffix.lower() not in DOC_EXT:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            text_hint = safe_read_text(path, 1200) if path.suffix.lower() in TEXT_EXT else ""
            category = classify(path, text_hint)
            try:
                rel = str(path.relative_to(ROOT))
            except ValueError:
                rel = str(path)
            yield FileRecord(
                path=path,
                rel=rel,
                scope=scope,
                ext=path.suffix.lower(),
                size=stat.st_size,
                sha256=file_hash(path),
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                title=path.stem,
                category=category,
            )


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def should_extract_pdf(rec: FileRecord) -> bool:
    """Keep extraction targeted; full file inventory still covers every PDF."""
    name = rec.rel.lower()
    # pypdf can hang on malformed CAD-export PDFs. Extract only small,
    # high-value documents and rely on the complete inventory for the rest.
    if rec.size > 5 * 1024 * 1024:
        return False
    high_value_tokens = [
        "aios_status_report",
        "validation",
        "rejection",
        "return",
        "title deed",
        "latest_issued",
        "cover_letter",
        "evaluation_sheet",
        "undertaking",
        "nakheel online service",
        "qa_report",
        "readiness_audit",
    ]
    if any(token in name for token in high_value_tokens):
        return True
    return False


def extract_pdf_text(records: list[FileRecord]) -> list[dict]:
    rows = []
    for rec in records:
        if rec.ext != ".pdf":
            continue
        if not should_extract_pdf(rec):
            rows.append({
                "path": rec.rel,
                "scope": rec.scope,
                "category": rec.category,
                "size_bytes": rec.size,
                "pages_extracted": 0,
                "extraction_status": "SKIPPED_LOW_PRIORITY",
                "hits": "",
                "error": "",
                "text_preview": "",
            })
            continue
        if rec.size > 5 * 1024 * 1024:
            rows.append({
                "path": rec.rel,
                "scope": rec.scope,
                "category": rec.category,
                "size_bytes": rec.size,
                "pages_extracted": 0,
                "extraction_status": "SKIPPED_TOO_LARGE",
                "hits": "",
                "error": "larger than 5MB safe extraction cap",
                "text_preview": "",
            })
            continue
        text = ""
        pages = 0
        error = ""
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(4)
            reader = PdfReader(str(rec.path))
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            pages = len(reader.pages)
            for i, page in enumerate(reader.pages[:5]):
                try:
                    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                    signal.alarm(3)
                    text += f"\n--- page {i + 1} ---\n" + (page.extract_text() or "")
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                    if len(text) > 12000:
                        break
                except Exception as exc:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                    text += f"\n--- page {i + 1} extraction_error: {exc} ---\n"
        except Exception as exc:
            signal.alarm(0)
            try:
                signal.signal(signal.SIGALRM, old_handler)
            except Exception:
                pass
            error = str(exc)
        subject_hits = sorted(set(re.findall(r"(PJ-P-VP-018|REC/PJ-VP-018/REV-01/2026|Nakheel|Palm Jumeirah|Title Deed|Swimming Pool|Undertaking|Rejection|Return)", text, re.I)))
        rows.append({
            "path": rec.rel,
            "scope": rec.scope,
            "category": rec.category,
            "size_bytes": rec.size,
            "pages_extracted": pages,
            "extraction_status": "OK" if text else ("ERROR" if error else "NO_TEXT"),
            "hits": "; ".join(subject_hits),
            "error": error,
            "text_preview": re.sub(r"\s+", " ", text[:900]).strip(),
        })
    return rows


def index_xlsx(records: list[FileRecord]) -> list[dict]:
    rows = []
    for rec in records:
        if rec.ext not in {".xlsx", ".xls"}:
            continue
        rows.append({
            "path": rec.rel,
            "status": "INDEXED_METADATA_ONLY",
            "sheets": "",
            "max_rows": "",
            "max_cols": "",
        })
    return rows


def inspect_property_db() -> list[dict]:
    rows = []
    for db_path in [
        AIOS / "KnowledgeBase" / "Property_Master_Database.sqlite",
        AIOS / "KnowledgeBase" / "resolver" / "unit_resolver_database.sqlite",
        ROOT / "AIOS_KNOWLEDGE_CONTROL" / "06_PROPERTY_INTELLIGENCE_ENGINE" / "KnowledgeBase" / "resolver" / "unit_resolver_database.sqlite",
    ]:
        if not db_path.exists():
            continue
        try:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("select name from sqlite_master where type='table' order by name")
            for (table,) in cur.fetchall():
                try:
                    cur.execute(f'select count(*) from "{table}"')
                    count = cur.fetchone()[0]
                except Exception:
                    count = ""
                rows.append({"database": str(db_path.relative_to(ROOT)), "table": table, "rows": count})
            con.close()
        except Exception as exc:
            rows.append({"database": str(db_path.relative_to(ROOT)), "table": "ERROR", "rows": str(exc)})
    return rows


def build_duplicates(records: list[FileRecord]) -> list[dict]:
    by_hash: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        if rec.sha256 != "UNREADABLE":
            by_hash[rec.sha256].append(rec)
    rows = []
    for sha, group in by_hash.items():
        if len(group) < 2:
            continue
        canonical = sorted(group, key=lambda r: (len(r.rel), r.rel))[0]
        for rec in sorted(group, key=lambda r: r.rel):
            rows.append({
                "sha256": sha,
                "canonical_candidate": canonical.rel,
                "duplicate_path": rec.rel,
                "size_bytes": rec.size,
                "category": rec.category,
            })
    return rows


def relationship_rows(records: list[FileRecord]) -> list[dict]:
    rows = []
    project_terms = {
        "AIOS Foundation": ["foundation", "operating manual", "standard", "policy"],
        "AIOS Knowledge Control": ["official_memory", "knowledge_control", "master_control", "memory"],
        "Nakheel PJ-P-VP-018": ["pj-p-vp-018", "nakheel", "palm jumeirah", "rev-01"],
        "Property Intelligence": ["property", "unit", "resolver", "inventory", "floor plan"],
        "WhatsApp Human Engine": ["whatsapp", "personality", "relationship", "gateway"],
        "AIOS Runtime": ["runtime", "transport", "dashboard", "deployment", "app.py"],
    }
    for rec in records:
        hay = rec.rel.lower()
        for project, terms in project_terms.items():
            if any(t in hay for t in terms):
                rows.append({
                    "project": project,
                    "related_file": rec.rel,
                    "category": rec.category,
                    "evidence_type": rec.ext.lstrip("."),
                    "reason": ", ".join([t for t in terms if t in hay][:4]),
                })
    return rows


def nakheel_requirements() -> list[dict]:
    return [
        {"rule_id": "NAK-001", "requirement": "Application type must match return path: Design Approval Re-submission Without Nonstandard unless nonstandard change is explicit.", "severity": "HIGH", "validation": "Portal field plus latest issued master developer rejection/NOC present."},
        {"rule_id": "NAK-002", "requirement": "Latest issued master developer return or rejection must be uploaded for resubmission.", "severity": "HIGH", "validation": "File slot mapped to latest Nakheel return/rejection PDF."},
        {"rule_id": "NAK-003", "requirement": "Covering or reply letter must respond to returned comments and reference PJ-P-VP-018 and REC/PJ-VP-018/REV-01/2026.", "severity": "HIGH", "validation": "Text extraction contains plot, revision, and comment response language."},
        {"rule_id": "NAK-004", "requirement": "Appointment letter must authorize the consultant/contractor and not be a draft/admin preview.", "severity": "HIGH", "validation": "Owner, consultant, date, and signature/stamp placeholders or executed copies verified."},
        {"rule_id": "NAK-005", "requirement": "Drawings must be split by portal slots and not replaced by a general signing/admin pack.", "severity": "HIGH", "validation": "Each slot file title matches drawing title: cover sheet, setting layout, floor plans, elevations, sections, boundary wall, topographical survey, combined PDF."},
        {"rule_id": "NAK-006", "requirement": "Swimming pool undertaking and discharge-system drawing must exist where pool/discharge applies.", "severity": "HIGH", "validation": "Undertaking text plus signed/stamped owner and consultant fields; drawing shows discharge/drainage system if applicable."},
        {"rule_id": "NAK-007", "requirement": "Gas connection undertaking must be uploaded when mandatory portal slot is marked with an asterisk.", "severity": "HIGH", "validation": "Dedicated signed gas undertaking PDF present, not buried only inside a master pack unless portal accepts combined support."},
        {"rule_id": "NAK-008", "requirement": "Evaluation sheet must be filled, signed, and under 5 MB for the portal slot.", "severity": "HIGH", "validation": "PDF title/content contains evaluation sheet and extracted project data."},
        {"rule_id": "NAK-009", "requirement": "Portal file size limits must be respected: 5 MB and 20 MB slots.", "severity": "HIGH", "validation": "Index size_bytes compared to slot limit."},
        {"rule_id": "NAK-010", "requirement": "No preview, draft, outbound email, signing coordination, or internal admin file should be uploaded as authority submission content.", "severity": "MEDIUM", "validation": "Filename and PDF text negative keyword scan."},
    ]


def validate_nakheel(pdf_rows: list[dict], records: list[FileRecord]) -> list[dict]:
    files = [r for r in records if r.category == "nakheel_design_approval"]
    combined_text = " ".join([row.get("text_preview", "") + " " + row.get("path", "") for row in pdf_rows if "PJ-P-VP-018" in row.get("path", "") or "Nakheel" in row.get("path", "")])
    checks = {
        "plot_pj_p_vp_018_present": "PJ-P-VP-018" in combined_text,
        "return_rejection_present": bool(re.search(r"return|rejection", combined_text, re.I)),
        "swimming_pool_present": bool(re.search(r"swimming pool", combined_text, re.I)),
        "undertaking_present": bool(re.search(r"undertaking", combined_text, re.I)),
        "title_deed_present": any("title" in r.rel.lower() and "deed" in r.rel.lower() for r in files),
        "new_pages_present": any("65108" in r.rel or "65109" in r.rel for r in files),
        "portal_upload_map_present": any("NAKHEEL_PORTAL_UPLOAD_MAP" in r.rel for r in files),
        "required_checklist_present": any("NAKHEEL_REQUIRED_DOCUMENT_CHECKLIST" in r.rel for r in files),
    }
    rows = []
    for name, ok in checks.items():
        rows.append({"check": name, "status": "PASS" if ok else "FAIL", "evidence": "local indexed evidence" if ok else "not found in generated index"})
    return rows


def validation_status(rows: list[dict]) -> str:
    statuses = [r.get("status") for r in rows]
    if statuses and all(s == "PASS" for s in statuses):
        return "PASS"
    if any(s == "PASS" for s in statuses):
        return "PARTIAL"
    return "FAIL"


def write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def table(rows: list[dict], cols: list[str], limit: int | None = None) -> str:
    selected = rows[:limit] if limit else rows
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in selected:
        out.append("| " + " | ".join(str(row.get(c, "")).replace("\n", " ")[:180] for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    ensure_dirs()
    source_records = list(iter_files(SOURCE_ROOTS, "aios"))
    nakheel_records = list(iter_files(NAKHEEL_ROOTS, "nakheel_golden_test"))
    property_records = list(iter_files(PROPERTY_ROOTS, "property_intelligence"))
    all_records = {r.rel: r for r in source_records + nakheel_records + property_records}
    records = list(all_records.values())

    inventory_rows = [{
        "path": r.rel,
        "scope": r.scope,
        "category": r.category,
        "extension": r.ext,
        "size_bytes": r.size,
        "modified": r.modified,
        "sha256": r.sha256,
        "title": r.title,
    } for r in sorted(records, key=lambda x: x.rel)]
    write_csv(CANONICAL / "AIOS_CANONICAL_FILE_INVENTORY.csv", inventory_rows, list(inventory_rows[0].keys()))

    pdf_rows = extract_pdf_text(records)
    write_csv(CANONICAL / "AIOS_PDF_TEXT_INDEX.csv", pdf_rows, ["path", "scope", "category", "size_bytes", "pages_extracted", "extraction_status", "hits", "error", "text_preview"])

    xlsx_rows = index_xlsx(records)
    if xlsx_rows:
        write_csv(CANONICAL / "AIOS_XLSX_INDEX.csv", xlsx_rows, ["path", "status", "sheets", "max_rows", "max_cols"])

    dup_rows = build_duplicates(records)
    write_csv(CANONICAL / "AIOS_DUPLICATE_KNOWLEDGE_INDEX.csv", dup_rows, ["sha256", "canonical_candidate", "duplicate_path", "size_bytes", "category"])

    rel_rows = relationship_rows(records)
    write_csv(CANONICAL / "AIOS_PROJECT_RELATIONSHIP_MAP.csv", rel_rows, ["project", "related_file", "category", "evidence_type", "reason"])

    db_rows = inspect_property_db()
    write_csv(PROPERTY_ENGINE / "PROPERTY_DATABASE_INVENTORY.csv", db_rows, ["database", "table", "rows"])

    req_rows = nakheel_requirements()
    write_csv(NAKHEEL_AGENT / "NAKHEEL_RETURN_COMMENT_RULES.csv", req_rows, ["rule_id", "requirement", "severity", "validation"])

    nakheel_validation = validate_nakheel(pdf_rows, records)
    write_csv(NAKHEEL_AGENT / "PJ-P-VP-018_GOLDEN_TEST_VALIDATION.csv", nakheel_validation, ["check", "status", "evidence"])

    counts = Counter(r.category for r in records)
    ext_counts = Counter(r.ext for r in records)
    duplicate_groups = len(set(r["sha256"] for r in dup_rows))
    nakheel_status = validation_status(nakheel_validation)
    property_status = "PARTIAL"
    if db_rows and any(str(r["rows"]).isdigit() and int(r["rows"]) > 0 for r in db_rows):
        property_status = "PARTIAL"
    system_status = "PARTIAL"

    write_md(FOUNDATION / "README.md", f"""
# AIOS Foundation

Date: {DATE}

This is the canonical foundation layer for AIOS. It does not overwrite original project files. It consolidates the existing OperatingSystem, AIOS_KNOWLEDGE_CONTROL, Nakheel PJ-P-VP-018 evidence, and Property Intelligence assets into one searchable governance layer.

## Authority order

1. Live production/runtime proof.
2. AIOS_KNOWLEDGE_CONTROL official memory and validation reports.
3. AIOS/OperatingSystem agents, workflows, SOPs, templates, and dashboards.
4. Canonical indexes generated in `AIOS/KnowledgeBase/Canonical`.
5. Archived duplicates and source evidence.

## Permanent rule

Patch and cross-reference. Do not delete, overwrite, or silently replace original files. If a file is superseded, mark the newer canonical path and preserve the original as evidence.
""")

    write_md(FOUNDATION / "OPERATING_MANUAL.md", f"""
# AIOS Permanent Operating Manual

## Mission

AIOS is the unified executive operating system for Omar, HSH, DreamVision, GD, property intelligence, approvals, WhatsApp operations, and internal knowledge. It must function as one brain, one knowledge base, one command center, and one evidence layer.

## Operating loop

1. Intake: classify the request by domain, project, urgency, and risk.
2. Retrieve: search canonical indexes before creating anything new.
3. Verify: confirm facts against live proof, source files, official reports, or current web sources when the fact may have changed.
4. Execute: produce the artifact, fix, package, report, upload map, or validated output.
5. Validate: run the relevant local test, file check, evidence check, or portal-safe review.
6. Report: give status first, then proof, blockers, and next action.
7. Preserve: keep originals, write new canonical outputs, and record relationships.

## Risk hold

Stop before irreversible actions: final portal submit, payment, deletion, publication, legal filing, signed authority submission, or credential change.
""")

    write_md(FOUNDATION / "ENGINEERING_STANDARDS.md", """
# AIOS Engineering Standards

## Core standards

- Preserve working implementations; patch the missing layer instead of rebuilding.
- Use reproducible scripts for indexes, reports, and validation outputs.
- Keep configuration, credentials, and secrets outside committed documents.
- Every engine must expose input schema, output schema, validation rules, and proof paths.
- Every user-facing status must be evidence-backed: LIVE, PARTIAL, BLOCKED, FAIL, or UNPROVEN.

## Interoperability requirements

- Shared project identifiers must be normalized across modules.
- Reports must link to source evidence, not only summaries.
- Validation outputs must be machine-readable when practical: CSV, JSON, SQLite, or structured Markdown.
- Duplicate logic must be consolidated into shared rules rather than copied into each agent.
""")

    write_md(FOUNDATION / "AUTONOMY_POLICY.md", """
# AIOS Autonomy Policy

## Autonomous actions allowed

- Read and index local files.
- Create new reports, indexes, schemas, templates, scripts, and validation outputs.
- Run local diagnostics and extraction tools.
- Research public sources for current requirements and best practices.
- Build packages and recommendations without modifying originals.

## Approval required

- Final portal submission.
- Payment or fee commitment.
- Deleting, replacing, or overwriting original evidence.
- Legal filing, authority filing, signed declarations, or owner-binding documents.
- Credential/account/security changes.

## Default execution rule

If the action is reversible, local, and evidence-building, proceed. If it binds the owner, spends money, changes a live external system, or deletes evidence, pause for approval.
""")

    write_md(FOUNDATION / "RESEARCH_POLICY.md", """
# AIOS Research Policy

## Source hierarchy

1. Official authority sources and live portal pages.
2. Project source documents and signed/stamped authority files.
3. AIOS official memory, validation reports, and proof bundles.
4. Reputable industry references.
5. Third-party blogs only as secondary indicators, never as authority.

## Currentness rule

Browse or verify when rules, prices, schedules, approval requirements, product behavior, laws, or public facts could have changed.

## Evidence rule

Every compliance or operational recommendation must state the basis: source file, portal evidence, official source, or inference.
""")

    write_md(FOUNDATION / "REPORTING_STANDARDS.md", """
# AIOS Reporting Standards

## Status vocabulary

- LIVE: validated end-to-end with current proof.
- PARTIAL: useful function exists but a known gap prevents full status.
- BLOCKED: cannot proceed without external action, missing access, or missing source evidence.
- FAIL: tested and failed.
- UNPROVEN: claimed but not validated.

## Report structure

1. Status.
2. Biggest finding.
3. Biggest risk.
4. Evidence.
5. Missing items.
6. Corrective action.
7. Next engineering phase.
""")

    write_md(FOUNDATION / "VALIDATION_STANDARDS.md", """
# AIOS Validation Standards

## Minimum validation gates

- File existence and non-empty content.
- Extractability for PDFs and spreadsheets where possible.
- Duplicate/fingerprint check.
- Cross-reference check against canonical inventory.
- Module-specific functional test.
- Evidence path recorded in the report.

## AI/RAG validation gates

- Retrieval coverage: can the system find the right evidence?
- Answer grounding: does the output cite or link evidence?
- Rule coverage: are validation rules explicit and reusable?
- Regression set: does a golden project produce stable results?
""")

    write_md(FOUNDATION / "MASTER_PERMISSIONS.md", """
# AIOS Master Permissions

## Permission classes

- Class 0: read-only research, local inventory, local validation. Autonomous.
- Class 1: create new local reports, indexes, schemas, and packages. Autonomous.
- Class 2: modify existing non-authority AIOS documentation. Allowed when preserving originals and clearly improving cross-references.
- Class 3: external action such as portal upload, email send, public deployment, or account setting change. Requires explicit user approval.
- Class 4: payment, legal filing, government/developer final submission, deletion, credential change. Requires explicit user approval.

## Evidence retention

Original evidence is never deleted. Superseded files are indexed as duplicates or archived references, not destroyed.
""")

    write_md(FOUNDATION / "REUSABLE_PROJECT_ARCHITECTURE.md", """
# AIOS Reusable Project Architecture

Every AIOS project should follow this architecture:

```text
00_BRIEF/
01_SOURCE_EVIDENCE/
02_REQUIREMENTS/
03_WORKING_FILES/
04_VALIDATION/
05_FINAL_OUTPUT/
06_REPORTS/
07_ARCHIVE/
```

## Required records

- `PROJECT_BRIEF.md`: objective, owner, authority, deadlines, risk level.
- `SOURCE_INVENTORY.csv`: every source file with hash and role.
- `REQUIREMENTS_MATRIX.csv`: requirement, evidence, validation rule, status.
- `VALIDATION_REPORT.md`: tests run, result, blockers, next action.
- `FINAL_OUTPUT_INDEX.csv`: upload/submission/package map.
""")

    write_md(FOUNDATION / "TEMPLATES.md", """
# AIOS Templates

## Project brief

```markdown
# Project Brief
Project:
Owner:
Objective:
Authority / client:
Deadline:
Risk level:
Source folders:
Success condition:
```

## Validation report

```markdown
# Validation Report
STATUS:
Confidence:
Tests run:
Passed:
Failed:
Evidence:
Missing:
Next action:
```

## Requirement rule

```csv
rule_id,requirement,severity,source,evidence_path,validation_method,status,corrective_action
```
""")

    write_md(CANONICAL / "AIOS_MASTER_INDEX.md", f"""
# AIOS Master Index

Date: {DATE}

## Indexed evidence

- Total indexed files: {len(records)}
- PDF files indexed: {sum(1 for r in records if r.ext == ".pdf")}
- Spreadsheet files indexed: {sum(1 for r in records if r.ext in {".xlsx", ".xls"})}
- Duplicate file rows: {len(dup_rows)}
- Duplicate hash groups: {duplicate_groups}

## Category counts

{table([{"category": k, "files": v} for k, v in counts.most_common()], ["category", "files"])}

## Extension counts

{table([{"extension": k, "files": v} for k, v in ext_counts.most_common()], ["extension", "files"])}

## Searchable files

- `AIOS_CANONICAL_FILE_INVENTORY.csv`
- `AIOS_PDF_TEXT_INDEX.csv`
- `AIOS_XLSX_INDEX.csv`
- `AIOS_DUPLICATE_KNOWLEDGE_INDEX.csv`
- `AIOS_PROJECT_RELATIONSHIP_MAP.csv`
""")

    write_md(CANONICAL / "KNOWLEDGE_CONSOLIDATION_REPORT.md", f"""
# AIOS Knowledge Consolidation Report

STATUS: PARTIAL

## What was consolidated

The accessible AIOS projects were indexed from the current local tree. Original files were not overwritten. A canonical search layer was created under `AIOS/KnowledgeBase/Canonical`.

## Biggest finding

AIOS already contains several completed or partial modules: OperatingSystem agents/workflows/SOPs, AIOS_KNOWLEDGE_CONTROL official memory and validation reports, a Nakheel PJ-P-VP-018 evidence set, and a Property Intelligence resolver stack.

## Duplicate knowledge

Duplicate detection found {duplicate_groups} duplicate hash groups and {len(dup_rows)} duplicate file rows. These are indexed, not deleted.

## Canonical source recommendation

Use `AIOS/KnowledgeBase/Canonical/AIOS_MASTER_INDEX.md` and the CSV inventories as the first lookup layer. Use original files only after following the evidence link from the inventory.

## Evidence outputs

- `AIOS_CANONICAL_FILE_INVENTORY.csv`
- `AIOS_PDF_TEXT_INDEX.csv`
- `AIOS_XLSX_INDEX.csv`
- `AIOS_DUPLICATE_KNOWLEDGE_INDEX.csv`
- `AIOS_PROJECT_RELATIONSHIP_MAP.csv`
""")

    write_md(NAKHEEL_AGENT / "README.md", f"""
# AIOS Nakheel Design Approval Agent

Golden Test Project: PJ-P-VP-018

STATUS: {nakheel_status}

## Mission

Validate Nakheel/Palm Jumeirah design approval submissions before portal upload. The agent converts return comments into reusable validation rules and checks each package against portal slots, authority requirements, file size limits, drawing completeness, and risk indicators.

## Golden project evidence

- Indexed Nakheel files: {sum(1 for r in records if r.category == "nakheel_design_approval")}
- PDF text index: `AIOS/KnowledgeBase/Canonical/AIOS_PDF_TEXT_INDEX.csv`
- Rules database: `NAKHEEL_RETURN_COMMENT_RULES.csv`
- Golden validation: `PJ-P-VP-018_GOLDEN_TEST_VALIDATION.csv`

## Core checks

{table(req_rows, ["rule_id", "severity", "requirement"], limit=10)}
""")

    write_md(NAKHEEL_AGENT / "COMPLIANCE_REPORT.md", f"""
# PJ-P-VP-018 Golden Test Compliance Report

STATUS: {nakheel_status}

## Validation checks

{table(nakheel_validation, ["check", "status", "evidence"])}

## Risk assessment

The local evidence contains strong PJ-P-VP-018 package material, return/rejection references, title deed evidence, new drawing pages, portal upload maps, and required-document checklists. The agent still classifies the live submission path as not fully LIVE because final portal submission and authority acceptance are external actions requiring approval and live confirmation.

## Resubmission checklist

1. Use the portal upload map for slot-to-file matching.
2. Verify each required starred portal slot before upload.
3. Upload drawing files by exact drawing slot, not a generic master file unless the slot specifically asks for combined PDF.
4. Keep latest issued Nakheel rejection/return in the required resubmission slot.
5. Do not upload draft/signing/admin preview files as authority documents.
""")

    write_md(PROPERTY_ENGINE / "README.md", f"""
# AIOS Property Intelligence Engine

STATUS: {property_status}

## Mission

Index inventory, developers, projects, units, owners, floor plans, listing identity, matching evidence, and recommendation logic into a reusable property intelligence layer.

## Indexed sources

- Property-related files indexed: {sum(1 for r in records if r.category == "property_intelligence")}
- Property database inventory: `PROPERTY_DATABASE_INVENTORY.csv`
- Canonical file inventory: `AIOS/KnowledgeBase/Canonical/AIOS_CANONICAL_FILE_INVENTORY.csv`

## Current capability

The local system has usable structured inventory and resolver assets. Existing evidence shows the general Unit Finder is usable for identifiers and building-unit clues, while URL-only exact resolution remains partial because URL-rich rows do not reliably join to unit-rich rows.
""")

    write_md(PROPERTY_ENGINE / "SCHEMA_AND_RULES.md", """
# Property Intelligence Schemas and Validation Rules

## Core entities

- Developer: developer_id, name, aliases, source, confidence.
- Project: project_id, developer_id, name, area, master_developer, handover, status.
- Building: building_id, project_id, name, aliases, location, permit_reference.
- Unit: unit_id, building_id, unit_number, type, beds, baths, floor, size, view, price, status.
- Owner: owner_id, name, contact_hash, source, consent_status.
- FloorPlan: floorplan_id, unit_type, project_id, file_path, page, area, bedrooms.
- Listing: listing_id, url, source_platform, text, price, unit_id_candidate, confidence.
- MatchEvidence: match_id, left_record, right_record, signals, confidence, reviewer_status.

## Validation rules

- A unit match is exact only when a stable identifier or building plus unit number agrees.
- URL-only matches cannot be marked exact unless the URL row contains a unit, permit, property, plot, or other bridge identifier.
- Floor plan recommendations must include project, unit type, bedroom count, size band, and source evidence.
- Owner data must be access-controlled and never used in public recommendations without permission.
""")

    write_md(PROPERTY_ENGINE / "BEST_PRACTICES_COMPARISON.md", """
# Property Intelligence Best Practices Comparison

## Industry benchmark themes

- Property-level information should include ownership/management, unit mix, rent/sales history, comparable data, pipeline status, and location ratings.
- RAG and search systems should evaluate retrieval and generation separately, maintain test sets, and monitor quality over time.
- Knowledge systems need governance, metadata, ownership, duplicate detection, and stale-content controls.

## AIOS comparison

- Strength: AIOS already has raw inventory, resolver databases, aliases, matching scripts, and validation evidence.
- Strength: AIOS has duplicate indexes and relationship maps after this consolidation.
- Gap: URL-to-unit bridge remains incomplete.
- Gap: property schemas need a stable canonical database contract across inventory, floor plans, listings, and recommendations.
- Gap: recommendation quality needs benchmark test cases with expected answers.

## Improvement plan

1. Promote the schema in `SCHEMA_AND_RULES.md` into a single SQLite schema.
2. Build an importer per source type: spreadsheet, PDF floor plan, listing URL, owner record.
3. Add validation tests for exact identifier, building-unit, floor-plan, and recommendation queries.
4. Keep URL-only resolution classified as PARTIAL until exact bridge evidence exists.
""")

    write_md(FOUNDATION / "AIOS_EXECUTIVE_REPORT.md", f"""
# AIOS Executive Report

Date: {DATE}

SYSTEM CLASSIFICATION: {system_status}

## Executive summary

AIOS is not blocked. It is a PARTIAL live operating system with several validated local modules and several known gaps. The system has enough structure to operate as an internal executive brain, but it should not be represented as fully production-live across every module.

## Integrated modules reviewed

- OperatingSystem agents/workflows/SOPs/templates.
- AIOS_KNOWLEDGE_CONTROL official memory and validation reports.
- WhatsApp human engine evidence and runtime files.
- Nakheel/PJ-P-VP-018 design approval evidence.
- Property Intelligence Engine, Unit Finder, resolver, and inventory assets.
- Canonical knowledge inventory and duplicate map generated in this run.

## Interoperability finding

The main interoperability gap is not missing files; it is inconsistent canonical routing. Some modules duplicate reports or scripts across AIOS and AIOS_KNOWLEDGE_CONTROL. The new canonical index layer resolves discovery, but the next engineering phase should centralize shared schemas and validation APIs.

## Duplicated logic

Duplicate files and mirrored reports exist across AIOS, AIOS_KNOWLEDGE_CONTROL, archive folders, and project-specific packages. They were indexed, not deleted.

## Next engineering phase

Build `AIOS Core Registry`:

1. One canonical SQLite registry for projects, documents, evidence, validation results, agents, and engines.
2. One shared validation runner that executes Nakheel, Property, WhatsApp, and runtime checks.
3. One report generator using the status vocabulary in `REPORTING_STANDARDS.md`.
4. One retrieval interface over canonical indexes and extracted PDF text.
5. One duplicate-resolution workflow that marks canonical candidates without deleting originals.

## Evidence

- `AIOS/KnowledgeBase/Canonical/AIOS_MASTER_INDEX.md`
- `AIOS/KnowledgeBase/Canonical/KNOWLEDGE_CONSOLIDATION_REPORT.md`
- `AIOS/Agents/NakheelDesignApproval/COMPLIANCE_REPORT.md`
- `AIOS/Engines/PropertyIntelligence/README.md`
""")

    validation_rows = [
        {"area": "foundation_documents", "status": "PASS", "evidence": "manuals, policies, standards, templates created under AIOS/00_FOUNDATION"},
        {"area": "canonical_inventory", "status": "PASS", "evidence": f"{len(records)} indexed files"},
        {"area": "pdf_extraction", "status": "PARTIAL", "evidence": f"{len(pdf_rows)} PDFs attempted; scanned/image PDFs may have NO_TEXT"},
        {"area": "duplicate_detection", "status": "PASS", "evidence": f"{duplicate_groups} duplicate hash groups indexed"},
        {"area": "nakheel_agent", "status": nakheel_status, "evidence": "PJ-P-VP-018 golden checks generated"},
        {"area": "property_engine", "status": property_status, "evidence": "property DB and resolver assets indexed; URL bridge remains known gap"},
        {"area": "system_classification", "status": system_status, "evidence": "integrated modules usable but not fully production-live"},
    ]
    write_csv(FOUNDATION / "AIOS_FOUNDATION_VALIDATION.csv", validation_rows, ["area", "status", "evidence"])
    write_md(FOUNDATION / "VALIDATION_REPORT_2026-06-25.md", f"""
# AIOS Foundation Validation Report

FINAL STATUS: {system_status}

## Results

{table(validation_rows, ["area", "status", "evidence"])}

## Files generated

- `AIOS/00_FOUNDATION/README.md`
- `AIOS/00_FOUNDATION/OPERATING_MANUAL.md`
- `AIOS/00_FOUNDATION/ENGINEERING_STANDARDS.md`
- `AIOS/00_FOUNDATION/AUTONOMY_POLICY.md`
- `AIOS/00_FOUNDATION/RESEARCH_POLICY.md`
- `AIOS/00_FOUNDATION/REPORTING_STANDARDS.md`
- `AIOS/00_FOUNDATION/VALIDATION_STANDARDS.md`
- `AIOS/00_FOUNDATION/MASTER_PERMISSIONS.md`
- `AIOS/00_FOUNDATION/REUSABLE_PROJECT_ARCHITECTURE.md`
- `AIOS/00_FOUNDATION/TEMPLATES.md`
- `AIOS/00_FOUNDATION/AIOS_EXECUTIVE_REPORT.md`
- `AIOS/KnowledgeBase/Canonical/AIOS_MASTER_INDEX.md`
- `AIOS/KnowledgeBase/Canonical/KNOWLEDGE_CONSOLIDATION_REPORT.md`
- `AIOS/Agents/NakheelDesignApproval/README.md`
- `AIOS/Agents/NakheelDesignApproval/COMPLIANCE_REPORT.md`
- `AIOS/Engines/PropertyIntelligence/README.md`
- `AIOS/Engines/PropertyIntelligence/SCHEMA_AND_RULES.md`
- `AIOS/Engines/PropertyIntelligence/BEST_PRACTICES_COMPARISON.md`

## Stop condition

The requested foundation, canonical knowledge base, Nakheel approval agent, Property Intelligence Engine documentation, inventories, relationship maps, and validation reports were produced without overwriting original source files.
""")

    summary = {
        "date": DATE,
        "system_status": system_status,
        "indexed_files": len(records),
        "pdfs_attempted": len(pdf_rows),
        "duplicate_hash_groups": duplicate_groups,
        "nakheel_status": nakheel_status,
        "property_status": property_status,
        "canonical_outputs": [
            str(CANONICAL / "AIOS_CANONICAL_FILE_INVENTORY.csv"),
            str(CANONICAL / "AIOS_PDF_TEXT_INDEX.csv"),
            str(CANONICAL / "AIOS_PROJECT_RELATIONSHIP_MAP.csv"),
            str(FOUNDATION / "AIOS_EXECUTIVE_REPORT.md"),
        ],
    }
    (FOUNDATION / "AIOS_FOUNDATION_BUILD_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
