#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DATE = "2026-06-25"
ROOT = Path("/Users/hassanka")
AUDIT_DIR = Path("/Users/hassanka/Downloads/AIOS/Agents/NakheelDesignApproval/PJ-P-VP-018_AUDIT_2026-06-25")

SEARCH_ROOTS = [
    Path("/Users/hassanka/Downloads"),
    Path("/Users/hassanka/Documents"),
    Path("/Users/hassanka/Desktop"),
    Path("/Users/hassanka/Downloads/AIOS"),
]

KEYWORDS = [
    "pj-p-vp-018",
    "pjp",
    "palm villa",
    "nakheel",
    "renaissance",
    "rec",
    "plot 18",
    "big basement",
    "pdf binder",
    "design approval",
    "trakhees",
    "noc",
]

IMPORTANT_PATHS = {
    "current_upload_folder": "/Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01",
    "evidence_folder": "/Users/hassanka/Downloads/PJ-P-VP-018_NAKHEEL_ALL_EVIDENCE",
    "signing_pack": "/Users/hassanka/Downloads/PJ-P-VP-018_Nakheel_Signing_Pack_2026-06-23",
    "original_heavy_binder": "/Users/hassanka/Downloads/PDF Binder (Plot-18) Palm Villa (Big Basement) (1).pdf",
    "return_rejection_pdf": "/Users/hassanka/Downloads/FIRST_RETURN_NAKHEEL_ARCHITECTURAL_REJECTION_2026-05-22.pdf",
    "owner_authorization_ready": "/Users/hassanka/Downloads/01A_OWNER_AUTHORIZATION_SIGN_STAMP_EXECUTION_READY.pdf",
    "wrong_trade_license_candidate": "/Users/hassanka/Downloads/License Letter (1).pdf",
}


@dataclass
class Requirement:
    key: str
    label: str
    classification: str
    evidence_path: str
    why: str
    consultant_action: str
    omar_action: str
    aios_action: str
    weight: int


REQUIREMENTS: list[Requirement] = [
    Requirement(
        "original_returned_pdf_binder",
        "Original returned PDF binder",
        "FOUND",
        "/Users/hassanka/Downloads/PDF Binder (Plot-18) Palm Villa (Big Basement) (1).pdf",
        "Heavy original binder exists and is referenced in existing review notes.",
        "None.",
        "Keep as evidence only.",
        "Index and keep as return-history evidence.",
        5,
    ),
    Requirement(
        "latest_revised_pdf_binder",
        "Latest / revised PDF binder",
        "FOUND",
        "/Users/hassanka/Downloads/Plot-18_PJ-P-VP-018_REV-01_Binder_Nakheel_Resubmission.pdf",
        "Latest revised binder and final submission variants exist in Downloads and evidence folders.",
        "Confirm which revised binder is the official one for authority use.",
        "Request consultant to identify the final issue set by revision and date.",
        "Cross-reference all binder variants.",
        8,
    ),
    Requirement(
        "nakheel_return_comments",
        "Nakheel return comments",
        "FOUND",
        "/Users/hassanka/Downloads/FIRST_RETURN_NAKHEEL_ARCHITECTURAL_REJECTION_2026-05-22.pdf",
        "Return letter, comment matrix, QA report, and readiness audit all exist.",
        "None.",
        "Keep as evidence package.",
        "Convert comments into reusable rule rows.",
        8,
    ),
    Requirement(
        "consultant_trade_license",
        "Consultant trade license",
        "MISSING",
        "/Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01/09_CONSULTANT_CONTRACTOR/01_License_Letter_CANDIDATE_VERIFY.pdf",
        "Current candidate is for ERDINC PROPERTY HOLDING Limited, not Renaissance Engineering Consultants.",
        "Provide the actual Renaissance Engineering Consultants trade license or valid consultant license letter.",
        "Ask for the correct Renaissance license PDF immediately.",
        "Flag the current candidate as invalid evidence.",
        10,
    ),
    Requirement(
        "owner_authorization_appointment_letter",
        "Owner authorization / appointment letter",
        "REQUIRES_HUMAN_CONFIRMATION",
        "/Users/hassanka/Downloads/01A_OWNER_AUTHORIZATION_SIGN_STAMP_EXECUTION_READY.pdf",
        "Execution-ready authorization exists, but execution/signature status is not proven from current evidence.",
        "Confirm whether Nakheel accepts this form and whether consultant signature/stamp is also required.",
        "Have the owner sign the authorization and confirm if notarization or wet signature is required.",
        "Keep the best execution-ready version isolated.",
        8,
    ),
    Requirement(
        "project_evaluation_sheet",
        "Project evaluation sheet",
        "REQUIRES_HUMAN_CONFIRMATION",
        "/Users/hassanka/Downloads/PJ-P-VP-018_Nakheel_Signing_Pack_2026-06-23/02_PROJECT_EVALUATION_SHEET.pdf",
        "Completed sheet exists with correct project values, but signature/date/stamp fields are blank.",
        "Review values against final drawings and sign/stamp if authority requests executed copy.",
        "Get owner signature if the live portal or consultant requires it.",
        "Keep the best filled version and flag missing execution.",
        8,
    ),
    Requirement(
        "gas_undertaking",
        "Gas undertaking",
        "MISSING",
        "",
        "Portal mapping explicitly lists signed gas connection undertaking as missing.",
        "Provide signed gas connection undertaking letter.",
        "Request the signed gas undertaking from consultant immediately.",
        "Keep item red-flagged in checklist.",
        8,
    ),
    Requirement(
        "combined_cad_dwg_dxf",
        "Combined CAD DWG/DXF",
        "MISSING",
        "",
        "Portal mapping explicitly lists no DWG/DXF/CAD file found.",
        "Provide combined CAD package in DWG/DXF if the portal slot is mandatory.",
        "Request the CAD export from consultant.",
        "Keep missing in matrix; AIOS cannot fabricate CAD.",
        10,
    ),
    Requirement(
        "topographical_survey_pdf_cad",
        "Topographical survey PDF/CAD",
        "MISSING",
        "",
        "No topographical survey PDF/CAD was found in searched project evidence.",
        "Provide topo survey PDF and CAD if required by the portal slot.",
        "Request topo survey from consultant or surveyor.",
        "Track as missing evidence.",
        7,
    ),
    Requirement(
        "infrastructure_details",
        "Infrastructure details",
        "MISSING",
        "",
        "Portal report explicitly states no clearly named plot infrastructure details file found.",
        "Provide plot infrastructure details sheet/file.",
        "Ask consultant to send the exact infrastructure details attachment.",
        "Keep missing in readiness score.",
        6,
    ),
    Requirement(
        "perspectives_front_back_top",
        "3D perspectives front/back/top",
        "UNCLEAR",
        "/Users/hassanka/Downloads/PJ-P-VP-018_NAKHEEL_ALL_EVIDENCE/nakheel_pj_p_vp_018_new_pages/651082_G 102 Perspective.pdf",
        "Perspective evidence exists, but not clearly as the portal's minimum front/back/top set in separate verified files.",
        "Confirm whether bundled G001-G004 renders satisfy the live slot or provide separate front/back/top renders.",
        "Ask whether Nakheel insists on separate perspective sheets.",
        "Preserve bundled render package and mark slot uncertain.",
        4,
    ),
    Requirement(
        "structural_drawings",
        "Structural drawings",
        "MISSING",
        "/Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01/05_STRUCTURAL_DRAWINGS",
        "Latest structural folder exists but contains no files.",
        "Provide structural drawings if scope or portal requires them.",
        "Ask consultant whether structural is not required or missing.",
        "Mark as missing until explicit not-required proof exists.",
        6,
    ),
    Requirement(
        "mep_drawings",
        "MEP drawings",
        "MISSING",
        "/Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01/06_MEP_OR_SERVICES",
        "Latest MEP/services folder exists but contains no files.",
        "Provide MEP/services drawings if scope or portal requires them.",
        "Ask consultant whether MEP is not required or missing.",
        "Mark as missing until explicit not-required proof exists.",
        6,
    ),
    Requirement(
        "signed_stamped_final_package",
        "Signed / stamped final package",
        "MISSING",
        "/Users/hassanka/Downloads/PJ-P-VP-018_Nakheel_Final_Verified_Package_2026-06-23/99_REMAINING_BLOCKERS.md",
        "Existing blockers explicitly say owner signature, consultant signature, consultant stamp, and live portal confirmation are still required.",
        "Issue the final signed/stamped package after review.",
        "Do not submit until owner and consultant execution is complete.",
        "Keep all sign-ready files grouped for execution.",
        12,
    ),
]

RETURN_COMMENT_ROWS = [
    ("Full compliance with Palm Jumeirah architectural guidelines", "PARTIAL", "Existing matrix says draft created only."),
    ("Contemporary / modern design style required", "PARTIAL", "QA report says response exists but final architectural issue set is still inconsistent."),
    ("Boundary wall height/material/design compliance", "PARTIAL", "Prior matrix and QA report both say this remains risky."),
    ("All heights measured from +0.00 gate level", "UNCLEAR", "Datum note exists but live authority acceptance not proven."),
    ("Privacy to neighbours", "PARTIAL", "Response exists but final geometry/privacy implementation is not proven."),
    ("Accurately filled evaluation sheet", "REQUIRES_HUMAN_CONFIRMATION", "Filled sheet exists but execution/sign-off is still open."),
    ("Swimming pool undertaking", "REQUIRES_HUMAN_CONFIRMATION", "Undertaking exists but execution/signature status remains open."),
    ("Fresh clean resubmission", "UNCLEAR", "Clean package exists; portal-side alignment still needs human confirmation."),
]


def normalize(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ")


def path_matches(path: Path) -> bool:
    s = normalize(str(path))
    return any(k in s for k in KEYWORDS)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files() -> list[Path]:
    out: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path_matches(path):
                out.append(path)
    return sorted(set(out))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def status_score(req: Requirement) -> float:
    return {
        "FOUND": 1.0,
        "NOT_REQUIRED": 1.0,
        "REQUIRES_HUMAN_CONFIRMATION": 0.5,
        "UNCLEAR": 0.25,
        "MISSING": 0.0,
    }.get(req.classification, 0.0)


def build_readiness_score(requirements: Iterable[Requirement]) -> int:
    total_weight = sum(r.weight for r in requirements)
    achieved = sum(r.weight * status_score(r) for r in requirements)
    return round((achieved / total_weight) * 100) if total_weight else 0


def build_classification(score: int, requirements: list[Requirement]) -> str:
    hard_missing = {
        "consultant_trade_license",
        "gas_undertaking",
        "combined_cad_dwg_dxf",
        "topographical_survey_pdf_cad",
        "signed_stamped_final_package",
    }
    if any(r.key in hard_missing and r.classification == "MISSING" for r in requirements):
        return "BLOCKED_MISSING_REQUIRED_DOCUMENTS"
    if score >= 85:
        return "READY_TO_SUBMIT"
    if score >= 55:
        return "PARTIAL_READY"
    return "FAIL_INCOMPLETE_PACKAGE"


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    files = collect_files()

    file_rows = []
    pdf_rows = []
    drawing_rows = []
    for path in files:
        rel = str(path)
        stat = path.stat()
        row = {
            "path": rel,
            "size_mb": round(stat.st_size / (1024 * 1024), 3),
            "extension": path.suffix.lower(),
            "sha256": sha256(path),
        }
        file_rows.append(row)
        if path.suffix.lower() == ".pdf":
            pdf_rows.append(row | {"kind": "pdf"})
        name = path.name.lower()
        if any(token in name for token in ["g-100", "a 100", "a100", "plan", "elevation", "section", "render", "perspective", "setting-out", "wall", "cover sheet"]):
            drawing_rows.append({
                "drawing_file": rel,
                "drawing_type": "drawing",
                "notes": "matched by drawing-style filename",
            })

    requirement_rows = []
    for req in REQUIREMENTS:
        requirement_rows.append({
            "key": req.key,
            "item": req.label,
            "classification": req.classification,
            "evidence_path": req.evidence_path,
            "why": req.why,
            "consultant_action": req.consultant_action,
            "omar_action": req.omar_action,
            "aios_action": req.aios_action,
        })

    return_comment_rows = []
    for comment, status, note in RETURN_COMMENT_ROWS:
        return_comment_rows.append({
            "nakheel_comment": comment,
            "classification": status,
            "evidence_note": note,
        })

    missing_rows = [r for r in requirement_rows if r["classification"] in {"MISSING", "UNCLEAR", "REQUIRES_HUMAN_CONFIRMATION"}]

    write_csv(AUDIT_DIR / "PJ-P-VP-018_FILE_INVENTORY.csv", file_rows, ["path", "size_mb", "extension", "sha256"])
    write_csv(AUDIT_DIR / "PJ-P-VP-018_PDF_INVENTORY.csv", pdf_rows, ["path", "size_mb", "extension", "sha256", "kind"])
    write_csv(AUDIT_DIR / "PJ-P-VP-018_DRAWING_INDEX.csv", drawing_rows, ["drawing_file", "drawing_type", "notes"])
    write_csv(AUDIT_DIR / "PJ-P-VP-018_DOCUMENT_CHECKLIST.csv", requirement_rows, ["key", "item", "classification", "evidence_path", "why", "consultant_action", "omar_action", "aios_action"])
    write_csv(AUDIT_DIR / "PJ-P-VP-018_MISSING_DOCUMENT_MATRIX.csv", missing_rows, ["key", "item", "classification", "evidence_path", "why", "consultant_action", "omar_action", "aios_action"])
    write_csv(AUDIT_DIR / "PJ-P-VP-018_RETURN_COMMENT_DATABASE.csv", return_comment_rows, ["nakheel_comment", "classification", "evidence_note"])

    score = build_readiness_score(REQUIREMENTS)
    classification = build_classification(score, REQUIREMENTS)

    consultant_items = [
        "Correct Renaissance Engineering Consultants trade license.",
        "Combined CAD DWG/DXF package if the portal CAD slot is mandatory.",
        "Topographical survey PDF/CAD if required by Nakheel.",
        "Infrastructure details sheet/file.",
        "Structural drawings if required.",
        "MEP/services drawings if required.",
        "Consultant signature and stamp on the final package, evaluation sheet, pool undertaking, and consultant undertaking.",
        "Consultant-reviewed final issue set confirming which revision is the actual authority package.",
    ]
    omar_items = [
        "Owner signature on authorization / appointment letter.",
        "Owner signature on project evaluation sheet if required.",
        "Owner signature on swimming pool undertaking.",
        "Gas undertaking from consultant/owner.",
        "Human confirmation that the live Nakheel portal record is PJ-P-VP-018 and not PJ-P-VP-015.",
    ]
    aios_fixes = [
        "Locate and index all evidence files.",
        "Detect that the current trade license candidate is the wrong company.",
        "Identify that structural and MEP folders are empty.",
        "Maintain the best current split upload basis and signing-pack basis.",
        "Draft the exact consultant message and submission checklist.",
    ]
    cannot_fix = [
        "Official Renaissance trade license.",
        "Executed signatures/stamps.",
        "Gas undertaking.",
        "CAD/DWG/DXF source files.",
        "Topographical survey.",
        "Official structural / MEP files if the authority requires them.",
    ]
    exact_message = (
        "Please send today the missing authority files for PJ-P-VP-018 so we can close the Nakheel resubmission set: "
        "1) Renaissance Engineering Consultants trade license, "
        "2) signed owner authorization / appointment letter, "
        "3) signed project evaluation sheet, "
        "4) signed swimming pool undertaking, "
        "5) signed gas undertaking, "
        "6) combined CAD DWG/DXF, "
        "7) topographical survey PDF/CAD, "
        "8) infrastructure details, "
        "9) structural drawings if required, "
        "10) MEP/services drawings if required, "
        "11) consultant-signed and stamped final issue set. "
        "The current license candidate is not valid because it is for ERDINC PROPERTY HOLDING Limited, not Renaissance Engineering Consultants."
    )

    readiness_md = f"""# PJ-P-VP-018 Ready To Submit Status

Date: {DATE}

Classification: {classification}
Readiness score: {score}/100

Current best upload basis:
- {IMPORTANT_PATHS['current_upload_folder']}

Current best signing basis:
- {IMPORTANT_PATHS['signing_pack']}

Why not ready:
- Missing valid consultant trade license.
- Missing gas undertaking.
- Missing CAD/DWG/DXF.
- Missing topographical survey.
- Missing infrastructure details.
- Structural and MEP folders are empty.
- Final signed/stamped authority set is not complete.
- Live portal record still requires human confirmation before any submission.
"""
    (AUDIT_DIR / "PJ-P-VP-018_READINESS_REPORT.md").write_text(readiness_md, encoding="utf-8")

    full_audit = f"""# PJ-P-VP-018 Full Audit Report

Date: {DATE}

Project: Palm Jumeirah Villa
Plot: PJ-P-VP-018
Authority: Nakheel / Palm Jumeirah Design Approval / NOC

## Executive result

Classification: {classification}
Readiness score: {score}/100

This package is not ready for a real Nakheel submission. Strong local evidence exists for the returned history, revised binders, title deed, split architectural package, comment analysis, and signing-pack drafts. The submission remains blocked by missing or unverified authority-required documents and incomplete execution.

## What we have

- Original heavy binder: {IMPORTANT_PATHS['original_heavy_binder']}
- Nakheel return letter: {IMPORTANT_PATHS['return_rejection_pdf']}
- Revised binder / final submission variants in Downloads and the evidence folder.
- Split portal-ready architectural package under: {IMPORTANT_PATHS['current_upload_folder']}
- Signing pack under: {IMPORTANT_PATHS['signing_pack']}
- Execution-ready owner authorization draft: {IMPORTANT_PATHS['owner_authorization_ready']}
- Filled project evaluation sheet in the signing pack and clean portal upload set.
- Swimming pool undertaking draft/support file.
- Title deed and owner ID/passport evidence.
- Return-comment matrices, QA report, readiness audit, and upload manifests.

## What is missing

- Correct Renaissance Engineering Consultants trade license.
- Signed gas undertaking.
- Combined CAD DWG/DXF package.
- Topographical survey PDF/CAD.
- Infrastructure details file.
- Structural drawings.
- MEP/services drawings.
- Final signed/stamped authority package.

## What is unclear

- Whether Nakheel will accept the existing execution-ready owner authorization without further notarization/witnessing.
- Whether separate front/back/top perspectives are mandatory, or whether the bundled render set is acceptable.
- Whether structural and MEP are truly not required for this exact scope or simply not supplied.
- Whether the evaluation sheet and pool undertaking must be uploaded as executed copies in the current live portal path.

## Consultant must provide

{chr(10).join(f"- {item}" for item in consultant_items)}

## Omar must request

{chr(10).join(f"- {item}" for item in omar_items)}

## AIOS can fix alone

{chr(10).join(f"- {item}" for item in aios_fixes)}

## Cannot be fixed without official documents

{chr(10).join(f"- {item}" for item in cannot_fix)}

## Exact next message Omar should send

{exact_message}

## Evidence anchors

- Current upload review: /Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01/_REPORTS/NAKHEEL_FINAL_SUBMISSION_REVIEW.md
- Portal checklist: /Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01/_REPORTS/NAKHEEL_REQUIRED_DOCUMENT_CHECKLIST.csv
- Portal map: /Users/hassanka/Downloads/NAKHEEL_FINAL_PORTAL_UPLOAD_READY_20260624_01/_REPORTS/NAKHEEL_PORTAL_UPLOAD_MAP.csv
- QA attack report: /Users/hassanka/Downloads/PJ-P-VP-018_NAKHEEL_ALL_EVIDENCE/Nakheel_Approval_QA_Report.md
- Signing blockers: /Users/hassanka/Downloads/PJ-P-VP-018_Nakheel_Final_Verified_Package_2026-06-23/99_REMAINING_BLOCKERS.md
"""
    (AUDIT_DIR / "PJ-P-VP-018_FULL_AUDIT_REPORT.md").write_text(full_audit, encoding="utf-8")

    missing_md = "# PJ-P-VP-018 Missing Documents\n\n" + "\n".join(
        f"- {row['item']}: {row['classification']} - {row['why']}" for row in missing_rows
    ) + "\n"
    (AUDIT_DIR / "PJ-P-VP-018_MISSING_DOCUMENTS.md").write_text(missing_md, encoding="utf-8")

    checklist_md = "# PJ-P-VP-018 Resubmission Checklist\n\n" + "\n".join(
        [
            "- Confirm live Nakheel record is PJ-P-VP-018.",
            "- Replace invalid consultant license candidate with the real Renaissance trade license.",
            "- Get owner authorization executed.",
            "- Get evaluation sheet executed if required.",
            "- Get swimming pool undertaking executed.",
            "- Obtain gas undertaking.",
            "- Obtain CAD/DWG/DXF package.",
            "- Obtain topographical survey PDF/CAD.",
            "- Obtain infrastructure details.",
            "- Obtain structural drawings if required.",
            "- Obtain MEP/services drawings if required.",
            "- Obtain consultant signature/stamp on final issue set.",
            "- Re-check slot mapping against live portal before upload.",
            "- Do not submit until all hard blockers are closed.",
        ]
    ) + "\n"
    (AUDIT_DIR / "PJ-P-VP-018_RESUBMISSION_CHECKLIST.md").write_text(checklist_md, encoding="utf-8")

    return_analysis_md = "# PJ-P-VP-018 Return Comment Analysis\n\n" + "\n".join(
        f"- {comment}: {status} - {note}" for comment, status, note in RETURN_COMMENT_ROWS
    ) + "\n"
    (AUDIT_DIR / "PJ-P-VP-018_RETURN_COMMENT_ANALYSIS.md").write_text(return_analysis_md, encoding="utf-8")

    ready_status_md = readiness_md + "\n## Exact next message Omar should send\n\n" + exact_message + "\n"
    (AUDIT_DIR / "PJ-P-VP-018_READY_TO_SUBMIT_STATUS.md").write_text(ready_status_md, encoding="utf-8")

    summary = {
        "date": DATE,
        "classification": classification,
        "score": score,
        "matched_files": len(files),
        "hard_blockers": [
            r.label for r in REQUIREMENTS
            if r.classification == "MISSING" and r.key in {
                "consultant_trade_license",
                "gas_undertaking",
                "combined_cad_dwg_dxf",
                "topographical_survey_pdf_cad",
                "signed_stamped_final_package",
            }
        ],
    }
    (AUDIT_DIR / "PJ-P-VP-018_READINESS_REPORT.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
