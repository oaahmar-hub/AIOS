#!/usr/bin/env python3
"""Build a local Knowledge Vault report for AIOS.

The runtime indexes local AIOS knowledge assets, maps retrieval routes, checks
coverage for SOPs, workflows, templates, contracts, cases, documents, and
historical knowledge, and prepares document-intake examples. It does not write
Drive, Notion, Airtable, or external files.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "KNOWLEDGE_VAULT_REPORT.json"

INDEX_EXTENSIONS = {".md", ".json", ".html", ".css", ".py", ".txt"}
ASSET_EXTENSIONS = {".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg", ".xlsx"}

CATEGORY_RULES = {
    "sops": ["sops/"],
    "workflows": ["workflows/"],
    "templates": ["templates/"],
    "contracts": ["templates/TPL-03", "templates/TPL-04", "templates/TPL-05", "templates/TPL-06", "agents/05-CONTRACT"],
    "documents": ["automation/ai_agents_production/runtime/document_intake_agent.py", "agents/12-DOCUMENT-INTAKE-AGENT.md"],
    "cases": ["automation/central_orchestrator/reports/actions/", "planning/DECISION-LOG.md"],
    "playbooks": ["agents/", "activation/prompts/", "MASTER-BRAIN.md", "00-MASTER-HUB.md"],
    "regulatory": ["knowledge-base/regulatory/"],
    "market": ["knowledge-base/market/"],
    "company": ["knowledge-base/company/"],
    "branding": ["knowledge-base/branding/"],
    "crm": ["crm/"],
    "historical_knowledge": ["knowledge-base/AIOS-MASTER-KNOWLEDGE-INDEX.md", "knowledge-base/AIOS-KNOWLEDGE-MAP.json"],
}

RETRIEVAL_ROUTES = [
    {
        "query": "NOC checklist",
        "intent": "government_approval",
        "open_first": "sops/SOP-01-NOC-APPLICATION.md",
        "then_use": ["workflows/WF-01-NOC-APPLICATION.md", "agents/01-NOC-APPROVALS-AGENT.md"],
        "handoff": "@noc",
    },
    {
        "query": "DLD transfer",
        "intent": "transfer_operations",
        "open_first": "workflows/WF-02-DLD-TRANSFER.md",
        "then_use": ["knowledge-base/regulatory/DLD-FEE-SCHEDULE.md", "agents/02-DLD-EJARI-AGENT.md"],
        "handoff": "@dld",
    },
    {
        "query": "tenancy contract",
        "intent": "contract_drafting",
        "open_first": "templates/TPL-05-TENANCY-CONTRACT.md",
        "then_use": ["workflows/WF-03-TENANCY-EJARI.md", "knowledge-base/regulatory/RERA-QUICK-REFERENCE.md"],
        "handoff": "@contract",
    },
    {
        "query": "lead qualification",
        "intent": "crm_followup",
        "open_first": "sops/SOP-09-LEAD-QUALIFICATION.md",
        "then_use": ["agents/04-CLIENT-MANAGER-AGENT.md", "crm/CRM-GUIDE.md"],
        "handoff": "@client",
    },
    {
        "query": "investment brief",
        "intent": "market_research",
        "open_first": "templates/TPL-08-INVESTMENT-BRIEF.md",
        "then_use": ["workflows/WF-09-INVESTMENT-RESEARCH.md", "knowledge-base/market/DUBAI-COMMUNITIES.md"],
        "handoff": "@research",
    },
    {
        "query": "brand voice",
        "intent": "content_factory",
        "open_first": "knowledge-base/branding/BRAND-GUIDELINES.md",
        "then_use": ["knowledge-base/branding/AIOS-BRAND-IDENTITY.md", "agents/08-MARKETING-AGENT.md"],
        "handoff": "@marketing",
    },
    {
        "query": "document intake",
        "intent": "document_classification",
        "open_first": "agents/12-DOCUMENT-INTAKE-AGENT.md",
        "then_use": ["automation/ai_agents_production/runtime/document_intake_agent.py"],
        "handoff": "@docs",
    },
]

SAMPLE_DOCUMENTS = [
    {
        "sample_id": "doc-title-deed-transfer",
        "text": "Title Deed. Name: Validation Buyer. Property: Unit 1508, Sadaf 6. DLD transfer and mortgage bank payment pending.",
    },
    {
        "sample_id": "doc-nakheel-noc",
        "text": "Nakheel NOC request. Name: Palm Owner. Unit: Palm Villa. Modification scope and contractor drawings missing.",
    },
    {
        "sample_id": "doc-tenancy-ejari",
        "text": "Tenancy contract for Ejari. Name: Dubai Hills Tenant. Property: Dubai Hills 1BR. Missing tenant Emirates ID.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_read(path: Path, limit: int = 5000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return ""


def _relative(path: Path) -> str:
    return path.relative_to(AIOS_ROOT).as_posix()


def _title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:120] or path.stem
    return path.stem.replace("-", " ").replace("_", " ").title()


def should_index(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in {".git", "__pycache__", ".DS_Store"} for part in path.parts):
        return False
    return path.suffix.lower() in INDEX_EXTENSIONS or path.suffix.lower() in ASSET_EXTENSIONS


def scan_assets() -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for path in sorted(AIOS_ROOT.rglob("*")):
        if not should_index(path):
            continue
        rel = _relative(path)
        text = _safe_read(path) if path.suffix.lower() in INDEX_EXTENSIONS else ""
        assets.append(
            {
                "title": _title_for(path, text),
                "path": rel,
                "extension": path.suffix.lower(),
                "asset_type": "text_knowledge" if path.suffix.lower() in INDEX_EXTENSIONS else "binary_asset",
                "size_bytes": path.stat().st_size,
                "tags": tags_for(rel, text),
                "excerpt": re.sub(r"\s+", " ", text).strip()[:220],
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return assets


def tags_for(rel: str, text: str) -> list[str]:
    lowered = f"{rel} {text[:1500]}".lower()
    checks = {
        "sop": ["sop", "procedure"],
        "workflow": ["workflow", "stage", "trigger"],
        "template": ["template", "tpl"],
        "contract": ["contract", "mou", "form f", "tenancy"],
        "document": ["document", "title deed", "passport", "emirates id"],
        "case": ["case", "decision", "action packet"],
        "regulatory": ["dld", "rera", "aml", "ejari", "noc"],
        "market": ["market", "community", "developer", "investment"],
        "crm": ["crm", "lead", "client", "follow-up"],
        "brand": ["brand", "logo", "campaign", "content"],
    }
    tags = [tag for tag, needles in checks.items() if any(needle in lowered for needle in needles)]
    return tags[:7]


def category_for_path(rel: str) -> list[str]:
    matches = []
    lowered = rel.lower()
    for category, needles in CATEGORY_RULES.items():
        if any(lowered.startswith(needle.lower()) or needle.lower() in lowered for needle in needles):
            matches.append(category)
    return matches or ["general"]


def build_categories(assets: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, Any] = {}
    for category in CATEGORY_RULES:
        categories[category] = {
            "asset_count": 0,
            "text_count": 0,
            "binary_count": 0,
            "sample_paths": [],
            "status": "missing",
        }
    for asset in assets:
        for category in category_for_path(asset["path"]):
            if category not in categories:
                continue
            row = categories[category]
            row["asset_count"] += 1
            if asset["asset_type"] == "text_knowledge":
                row["text_count"] += 1
            else:
                row["binary_count"] += 1
            if len(row["sample_paths"]) < 6:
                row["sample_paths"].append(asset["path"])
    for category, row in categories.items():
        if row["asset_count"] >= 5:
            row["status"] = "strong"
        elif row["asset_count"] >= 2:
            row["status"] = "usable"
        elif row["asset_count"] == 1:
            row["status"] = "thin"
    return categories


def retrieve(query: str, assets: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    terms = [term for term in re.split(r"[^a-z0-9]+", query.lower()) if len(term) > 2]
    scored = []
    for asset in assets:
        haystack = f"{asset['path']} {asset['title']} {' '.join(asset.get('tags', []))} {asset.get('excerpt', '')}".lower()
        score = sum(5 if term in asset["path"].lower() else 1 for term in terms if term in haystack)
        if score:
            scored.append(
                {
                    "score": score,
                    "title": asset["title"],
                    "path": asset["path"],
                    "tags": asset.get("tags", []),
                    "excerpt": asset.get("excerpt", ""),
                }
            )
    scored.sort(key=lambda row: (-row["score"], row["path"]))
    return scored[:limit]


def classify_document(text: str) -> dict[str, Any]:
    low = text.lower()
    document_type = "Unknown"
    case_type = "General"
    assigned_agent = "@client"
    missing_items = []
    if "title deed" in low:
        document_type = "Title Deed"
        case_type = "DLD Transfer"
        assigned_agent = "@dld"
    if "tenancy" in low or "ejari" in low:
        document_type = "Tenancy / Ejari"
        case_type = "Ejari"
        assigned_agent = "@dld"
    if "noc" in low or "nakheel" in low:
        document_type = "NOC Document"
        case_type = "NOC"
        assigned_agent = "@noc"
    if "name:" not in low:
        missing_items.append("Client name")
    if "unit" not in low and "property" not in low:
        missing_items.append("Property/unit reference")
    if "emirates id" in low and "missing" in low:
        missing_items.append("Emirates ID")
    if "drawings missing" in low:
        missing_items.append("Contractor drawings")
    risk_level = "High" if any(word in low for word in ["payment", "bank", "poa", "court", "dispute", "legal"]) else "Normal"
    return {
        "document_type": document_type,
        "case_type": case_type,
        "missing_items": missing_items,
        "risk_level": risk_level,
        "assigned_agent": assigned_agent,
        "approval_required": risk_level == "High" or assigned_agent in {"@dld", "@noc", "@contract"},
        "summary": text[:240],
    }


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    assets = scan_assets()
    categories = build_categories(assets)
    queries = payload.get("queries") or [route["query"] for route in RETRIEVAL_ROUTES]
    retrieval_results = [
        {
            "query": query,
            "matches": retrieve(query, assets),
        }
        for query in queries
    ]
    sample_documents = payload.get("documents") or SAMPLE_DOCUMENTS
    document_cases = [
        {
            "sample_id": item.get("sample_id", f"doc-{index + 1}"),
            **classify_document(str(item.get("text", ""))),
        }
        for index, item in enumerate(sample_documents)
    ]
    top_assets = sorted(assets, key=lambda item: item["updated_at"], reverse=True)[:12]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_knowledge_vault_no_external_side_effects",
        "asset_count": len(assets),
        "text_asset_count": len([asset for asset in assets if asset["asset_type"] == "text_knowledge"]),
        "binary_asset_count": len([asset for asset in assets if asset["asset_type"] == "binary_asset"]),
        "categories": categories,
        "retrieval_routes": RETRIEVAL_ROUTES,
        "retrieval_results": retrieval_results,
        "document_cases": document_cases,
        "recent_assets": top_assets,
        "coverage_summary": {
            "required_categories": sorted(CATEGORY_RULES),
            "strong_categories": sorted(category for category, row in categories.items() if row["status"] == "strong"),
            "thin_or_missing_categories": sorted(category for category, row in categories.items() if row["status"] in {"thin", "missing"}),
            "has_sops": categories["sops"]["asset_count"] >= 10,
            "has_workflows": categories["workflows"]["asset_count"] >= 10,
            "has_templates": categories["templates"]["asset_count"] >= 10,
            "has_contracts": categories["contracts"]["asset_count"] >= 4,
            "has_document_intake": categories["documents"]["asset_count"] >= 2,
            "has_cases": categories["cases"]["asset_count"] >= 1,
        },
        "workflow_handoffs": [
            {"command": "@docs", "scope": "classify documents, extract missing items, create case packet"},
            {"command": "@ask", "scope": "retrieve answer from local AIOS corpus"},
            {"command": "@research", "scope": "market and investment research retrieval"},
            {"command": "@contract", "scope": "contract and clause template retrieval"},
            {"command": "@operations", "scope": "DLD, RERA, NOC, Ejari, mortgage, off-plan, visa retrieval"},
        ],
        "recommended_next_actions": [
            "Use Knowledge Vault retrieval before creating new documents to avoid duplicates.",
            "Add future live property inventory, clause bank, access register, portal register, and lessons learned as source-of-truth files.",
            "Keep external sync to Drive, Notion, Airtable, or vector databases disabled until credentials and approval gates are ready.",
        ],
        "external_side_effects": {
            "drive_files_modified": False,
            "notion_pages_created": False,
            "airtable_rows_written": False,
            "vector_db_written": False,
            "documents_uploaded": False,
            "files_deleted": False,
            "external_search_called": False,
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
