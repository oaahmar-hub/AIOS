#!/usr/bin/env python3
"""Build a local AIOS operations-assistant report.

This runtime turns local DLD, RERA, NOC, Ejari, mortgage, off-plan, and visa
knowledge into approval-gated checklists. It does not submit portals, send
messages, make payments, write CRM rows, or create legal conclusions.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "OPERATIONS_ASSISTANT_REPORT.json"

SOURCE_PATHS = {
    "dld_fee_schedule": "knowledge-base/regulatory/DLD-FEE-SCHEDULE.md",
    "rera_quick_reference": "knowledge-base/regulatory/RERA-QUICK-REFERENCE.md",
    "noc_sop": "sops/SOP-01-NOC-APPLICATION.md",
    "ejari_sop": "sops/SOP-05-EJARI-REGISTRATION.md",
    "handover_sop": "sops/SOP-06-HANDOVER-INSPECTION.md",
    "noc_workflow": "workflows/WF-01-NOC-APPLICATION.md",
    "dld_transfer_workflow": "workflows/WF-02-DLD-TRANSFER.md",
    "ejari_workflow": "workflows/WF-03-TENANCY-EJARI.md",
    "mou_transfer_workflow": "workflows/WF-06-MOU-TO-TRANSFER.md",
    "handover_workflow": "workflows/WF-07-PROPERTY-HANDOVER.md",
    "noc_agent": "agents/01-NOC-APPROVALS-AGENT.md",
    "dld_ejari_agent": "agents/02-DLD-EJARI-AGENT.md",
}

DEFAULT_REQUEST = {
    "case_type": "dld_transfer",
    "property_type": "apartment",
    "purchase_price": 2_000_000,
    "mortgage": True,
    "loan_amount": 1_500_000,
    "developer": "Nakheel",
    "community": "JVC",
}

RENT_CAP_TABLE = [
    {"below_market_rate": "less_than_10_percent", "max_allowed_increase_percent": 0},
    {"below_market_rate": "11_to_20_percent", "max_allowed_increase_percent": 5},
    {"below_market_rate": "21_to_30_percent", "max_allowed_increase_percent": 10},
    {"below_market_rate": "31_to_40_percent", "max_allowed_increase_percent": 15},
    {"below_market_rate": "more_than_40_percent", "max_allowed_increase_percent": 20},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _property_type(value: Any) -> str:
    text = str(value or "apartment").strip().lower()
    if text in {"villa", "land", "commercial", "retail"}:
        return text
    return "apartment"


def calculate_fees(request: dict[str, Any]) -> dict[str, Any]:
    purchase_price = _money(request.get("purchase_price"))
    loan_amount = _money(request.get("loan_amount"))
    property_type = _property_type(request.get("property_type"))
    trustee_fee = 4_200 if property_type in {"villa", "land", "commercial", "retail"} else 2_100
    transfer_fee = round(purchase_price * 0.04, 2)
    title_admin_fee = 290.0
    mortgage_registration = round((loan_amount * 0.0025) + 290, 2) if request.get("mortgage") else 0.0
    agency_commission = round(purchase_price * 0.02, 2)
    total = round(transfer_fee + trustee_fee + title_admin_fee + mortgage_registration + agency_commission, 2)
    return {
        "currency": "AED",
        "purchase_price": purchase_price,
        "property_type": property_type,
        "transfer_fee": transfer_fee,
        "trustee_fee_including_vat": float(trustee_fee),
        "title_deed_admin_fees": title_admin_fee,
        "mortgage_registration": mortgage_registration,
        "agency_commission_estimate": agency_commission,
        "agency_commission_note": "2% estimate only; confirm signed agency agreement before collection.",
        "total_estimated_cash_to_close": total,
        "authority_verification_required": True,
        "source_path": SOURCE_PATHS["dld_fee_schedule"],
    }


def build_cases(request: dict[str, Any], fees: dict[str, Any]) -> list[dict[str, Any]]:
    developer = str(request.get("developer") or "developer").strip()
    community = str(request.get("community") or "Dubai").strip()
    return [
        {
            "case_id": "dld_transfer",
            "title": "DLD Transfer",
            "command": "@dld",
            "timeline": "cash transfer about 7 days; mortgage transfer about 21 days",
            "fee_summary": f"AED {fees['transfer_fee']:,.0f} transfer fee; AED {fees['total_estimated_cash_to_close']:,.0f} estimated over-price cash to close",
            "required_documents": [
                "signed MOU / Form F",
                "seller Emirates ID and passport",
                "buyer Emirates ID and passport",
                "original title deed",
                "developer NOC",
                "service charge clearance",
                "manager's cheques for seller and DLD fees",
                "mortgage preapproval and final offer if financed",
            ],
            "checklist": [
                "confirm MOU terms and parties match IDs",
                "confirm developer NOC is issued and valid",
                "confirm outstanding service charges are cleared",
                "confirm mortgage clearance or bank appointment if applicable",
                "calculate DLD, trustee, admin, mortgage, and commission amounts",
                "book trustee appointment only after all documents are complete",
            ],
            "risk_flags": [
                "portal booking, cheque instructions, and final DLD figures require live authority and trustee verification",
                "passport, Emirates ID, title deed, and payment details require Omar approval before external sharing",
            ],
            "next_actions": [
                "Collect final title deed, IDs, NOC, service charge clearance, and finance status.",
                "Prepare cheque schedule and trustee appointment request for approval.",
            ],
            "approval_required": True,
            "source_paths": [
                SOURCE_PATHS["dld_fee_schedule"],
                SOURCE_PATHS["dld_transfer_workflow"],
                SOURCE_PATHS["mou_transfer_workflow"],
            ],
        },
        {
            "case_id": "noc",
            "title": f"{developer} NOC",
            "command": "@noc",
            "timeline": "3 to 15 working days depending on developer and work type",
            "required_documents": [
                "title deed",
                "owner Emirates ID and passport",
                "developer NOC application form",
                "service charge clearance",
                "MOU and buyer ID for sale NOC",
                "contractor documents and drawings for modification NOC",
            ],
            "checklist": [
                f"identify exact {developer} NOC type for {community}",
                "clear service charges before submission",
                "verify owner details against title deed",
                "attach contractor trade license, insurance, and drawings for alteration scopes",
                "track day 3, day 5, day 8, and day 15 escalation points",
            ],
            "risk_flags": [
                "developer NOC fee and processing time can change",
                "modification NOC may require additional drawings, method statements, or community approval",
            ],
            "next_actions": [
                "Build NOC upload pack and reviewer note.",
                "Hold portal submission until Omar approves the final document set.",
            ],
            "approval_required": True,
            "source_paths": [SOURCE_PATHS["noc_sop"], SOURCE_PATHS["noc_workflow"], SOURCE_PATHS["noc_agent"]],
        },
        {
            "case_id": "ejari",
            "title": "Ejari Registration",
            "command": "@ejari",
            "timeline": "register within 30 days of tenancy contract signing",
            "fee_summary": "AED 175 official fee plus possible AED 20 to AED 50 typing-center charge",
            "required_documents": [
                "signed tenancy contract",
                "title deed",
                "landlord Emirates ID or passport",
                "tenant Emirates ID or passport",
                "DEWA premises number",
                "company trade license and authorization if company tenant or landlord",
            ],
            "checklist": [
                "confirm contract dates, rent amount, cheques, deposit, and maintenance clauses",
                "remove prohibited clauses before signature",
                "confirm registration deadline and portal route",
                "prepare cancellation or renewal path if an active Ejari exists",
            ],
            "risk_flags": [
                "late Ejari can create enforceability and utility activation issues",
                "rent increase needs 90-day notice and RERA index support",
            ],
            "next_actions": [
                "Audit tenancy contract clauses before upload.",
                "Prepare Ejari submission packet for approval.",
            ],
            "approval_required": True,
            "source_paths": [
                SOURCE_PATHS["rera_quick_reference"],
                SOURCE_PATHS["ejari_sop"],
                SOURCE_PATHS["ejari_workflow"],
                SOURCE_PATHS["dld_ejari_agent"],
            ],
        },
        {
            "case_id": "mortgage",
            "title": "Mortgage Registration",
            "command": "@mortgage",
            "timeline": "coordinate with bank and trustee; usually inside the financed transfer timeline",
            "fee_summary": f"AED {fees['mortgage_registration']:,.0f} mortgage registration estimate for the current request",
            "required_documents": [
                "bank final offer letter",
                "mortgage preapproval",
                "liability letter if seller has existing mortgage",
                "seller bank clearance or blocking letter",
                "buyer KYC and income documents as requested by bank",
            ],
            "checklist": [
                "confirm loan amount and bank appointment requirements",
                "calculate 0.25% mortgage registration plus AED 290",
                "align manager's cheques and bank disbursement instructions",
                "confirm mortgage release if seller loan exists",
            ],
            "risk_flags": [
                "bank figures and DLD mortgage registration must be confirmed live before cheque issuance",
                "seller mortgage discharge can delay transfer if liability letter expires",
            ],
            "next_actions": [
                "Request bank final transfer checklist.",
                "Prepare mortgage fee and cheque schedule for approval.",
            ],
            "approval_required": True,
            "source_paths": [SOURCE_PATHS["dld_fee_schedule"], SOURCE_PATHS["dld_transfer_workflow"]],
        },
        {
            "case_id": "off_plan",
            "title": "Off-plan / Oqood",
            "command": "@offplan",
            "timeline": "Oqood registration within 30 days of SPA signing",
            "fee_summary": "Oqood 4% of purchase price plus AED 290 admin; E-NOC often AED 1,000 to AED 2,000",
            "required_documents": [
                "signed SPA",
                "buyer passport and Emirates ID if available",
                "developer payment plan",
                "project registration evidence",
                "escrow account details",
                "developer marketing authorization for advertising",
            ],
            "checklist": [
                "verify project is RERA registered",
                "verify escrow account before recommendation",
                "confirm Oqood submission status and deadline",
                "disclose completion percentage and delivery date",
                "confirm advertising authorization before publishing",
            ],
            "risk_flags": [
                "off-plan claims must be backed by developer and RERA project evidence",
                "no listing or paid promotion without valid permit or developer authorization",
            ],
            "next_actions": [
                "Build project due diligence packet.",
                "Hold client recommendation until registration, escrow, and authorization are checked.",
            ],
            "approval_required": True,
            "source_paths": [SOURCE_PATHS["rera_quick_reference"], SOURCE_PATHS["dld_fee_schedule"]],
        },
        {
            "case_id": "rera",
            "title": "RERA Listing and Rental Compliance",
            "command": "@rera",
            "timeline": "permit before publishing; rent-change notice 90 days before expiry",
            "fee_summary": "Advertising permit AED 1,010; rent cap depends on RERA Rental Index gap",
            "required_documents": [
                "title deed",
                "signed listing agreement",
                "broker license copy",
                "owner ID documents",
                "property media and listing description",
                "RERA rental index result for rent increase cases",
            ],
            "checklist": [
                "obtain RERA permit before portal or paid advertising",
                "confirm listing agreement and owner authorization",
                "run rent increase against the RERA index and cap table",
                "confirm 90-day written notice for rent changes",
                "confirm 12-month notary or registered-mail notice for eviction cases",
            ],
            "risk_flags": [
                "permit-free publishing can trigger portal removal or fines",
                "WhatsApp/email/verbal eviction notices are not valid Form 12 service",
            ],
            "next_actions": [
                "Prepare listing permit packet.",
                "For rent changes, save RERA index evidence before advising landlord or tenant.",
            ],
            "approval_required": True,
            "source_paths": [SOURCE_PATHS["rera_quick_reference"], SOURCE_PATHS["dld_fee_schedule"]],
        },
        {
            "case_id": "residency_visa",
            "title": "Property-linked Residency Visa",
            "command": "@visa",
            "timeline": "timeline depends on property value, title status, mortgage position, and immigration appointment availability",
            "required_documents": [
                "title deed",
                "property valuation or value evidence",
                "passport",
                "Emirates ID if renewing or already resident",
                "health insurance evidence",
                "mortgage statement or NOC if financed",
                "passport photo and medical/biometric requirements as applicable",
            ],
            "checklist": [
                "verify current visa category threshold with official UAE authority before advising",
                "confirm title deed owner name and property value",
                "confirm mortgage status and required bank NOC",
                "prepare immigration document checklist for approval",
                "avoid legal or immigration guarantees in client communication",
            ],
            "risk_flags": [
                "visa thresholds and immigration rules change and require live official verification",
                "AIOS can prepare a checklist but cannot give legal immigration advice",
            ],
            "next_actions": [
                "Verify current GDRFA/ICP eligibility route.",
                "Prepare document collection checklist and Omar review note.",
            ],
            "approval_required": True,
            "source_paths": [SOURCE_PATHS["dld_fee_schedule"]],
        },
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = {**DEFAULT_REQUEST, **(payload or {})}
    fees = calculate_fees(request)
    cases = build_cases(request, fees)
    selected_case = str(request.get("case_type") or "dld_transfer").strip().lower()
    result = {
        "generated_at": _now(),
        "mode": "safe_local_operations_assistant_no_external_side_effects",
        "request": request,
        "case_count": len(cases),
        "cases": cases,
        "selected_case": selected_case,
        "selected_case_detail": next((case for case in cases if case["case_id"] == selected_case), cases[0]),
        "fee_calculator": fees,
        "rera_rent_cap_table": RENT_CAP_TABLE,
        "workflow_handoffs": [
            {"command": "@dld", "scope": "DLD transfer, trustee, mortgage registration"},
            {"command": "@noc", "scope": "developer NOC and alteration approvals"},
            {"command": "@contract", "scope": "MOU, tenancy, SPA, and clause review packet"},
            {"command": "@handover", "scope": "inspection, snagging, key handover"},
            {"command": "@operations", "scope": "case triage and document control"},
        ],
        "recommended_next_actions": [
            "Use this report as local preparation only; verify current government/developer fees before submission.",
            "Keep all portal submissions, payments, and legal/immigration advice behind Omar approval.",
            "Attach source documents and reviewer notes before moving any case from checklist to live execution.",
        ],
        "external_side_effects": {
            "portal_submissions": False,
            "messages_sent": False,
            "crm_rows_written": False,
            "payments_made": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "legal_claims_finalized": False,
        },
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(build(payload), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
