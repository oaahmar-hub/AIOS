#!/usr/bin/env python3
"""Build the AIOS command-center data contract.

This scanner is local-only. It reads AIOS files and reports, then emits a JSON
payload the dashboard can load for search, activity, workflow launch metadata,
and system health. It does not call external services or mutate business data.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "COMMAND_CENTER_DATA.json"

INDEX_EXTENSIONS = {".md", ".json", ".html", ".css", ".py"}
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".DS_Store",
    "conversation_state.sqlite",
    "aios_dashboard_desktop.png",
    "aios_dashboard_mobile.png",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_read(path: Path, limit: int = 7000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return ""


def _title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:120] or path.stem
    return path.stem.replace("-", " ").replace("_", " ").title()


def _category_for(path: Path) -> str:
    rel = path.relative_to(AIOS_ROOT)
    parts = rel.parts
    if not parts:
        return "system"
    if parts[0] in {"agents", "workflows", "sops", "templates", "crm", "planning", "knowledge-base"}:
        return parts[0]
    if parts[0] == "automation" and len(parts) > 1:
        return f"automation/{parts[1]}"
    if path.name in {"AIOS-DASHBOARD.html", "AIOS-MOBILE-APP.html", "AIOS-WEBSITE.html"}:
        return "command-center"
    return parts[0]


def _tags_for(path: Path, text: str) -> list[str]:
    lowered = f"{path.as_posix()} {text[:2000]}".lower()
    tags = []
    checks = {
        "whatsapp": ["whatsapp", "wa-"],
        "crm": ["crm", "lead", "contact", "task"],
        "operations": ["dld", "rera", "noc", "ejari", "transfer", "mortgage", "visa"],
        "content": ["content", "caption", "campaign", "reel", "video", "flyer", "brochure"],
        "knowledge": ["knowledge", "sop", "playbook", "contract", "document"],
        "property": ["property", "listing", "buyer", "seller", "tenant", "investment"],
        "command-center": ["dashboard", "health", "router", "orchestrator", "command"],
    }
    for tag, needles in checks.items():
        if any(needle in lowered for needle in needles):
            tags.append(tag)
    return tags[:6]


def build_search_index() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(AIOS_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in INDEX_EXTENSIONS:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts) or path.name in EXCLUDED_PARTS:
            continue
        text = _safe_read(path)
        rel = path.relative_to(AIOS_ROOT).as_posix()
        rows.append(
            {
                "title": _title_for(path, text),
                "path": rel,
                "category": _category_for(path),
                "tags": _tags_for(path, text),
                "excerpt": re.sub(r"\s+", " ", text).strip()[:260],
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return rows


def build_workflows() -> list[dict[str, Any]]:
    workflows = []
    for path in sorted((AIOS_ROOT / "workflows").glob("WF-*.md")):
        if path.name == "WF-LIBRARY.md":
            continue
        text = _safe_read(path)
        workflows.append(
            {
                "name": _title_for(path, text),
                "path": path.relative_to(AIOS_ROOT).as_posix(),
                "type": "operating_workflow",
                "run_mode": "draft_contract",
                "approval_required": True,
                "command": "@" + path.stem.split("-")[1].lower() if "-" in path.stem else "@workflow",
            }
        )
    automation = [
        ("GD Core Orchestrator", "automation/central_orchestrator/runtime/gd_core_orchestrator.py", "@aios"),
        ("Ask AIOS Local Brain", "automation/central_orchestrator/runtime/ask_aios.py", "@ask"),
        ("Local Action Runner", "automation/central_orchestrator/runtime/local_action_runner.py", "@run-local"),
        ("Approval State Manager", "automation/central_orchestrator/runtime/approval_state_manager.py", "@approve-local"),
        ("Local Approval Command", "automation/central_orchestrator/runtime/local_approval_command.py", "@decision-local"),
        ("Connector Execution Manifest", "automation/central_orchestrator/runtime/connector_execution_manifest.py", "@connector-manifest"),
        ("Connector Dry Run Executor", "automation/central_orchestrator/runtime/connector_dry_run_executor.py", "@connector-dry-run"),
        ("Live Run Request Builder", "automation/central_orchestrator/runtime/live_run_request_builder.py", "@live-run-request"),
        ("Disabled Live Connector Runner", "automation/central_orchestrator/runtime/disabled_live_connector_runner.py", "@live-runner"),
        ("Connector Payload Builder", "automation/central_orchestrator/runtime/connector_payload_builder.py", "@connector-payloads"),
        ("Connector Activation Checklist", "automation/central_orchestrator/runtime/connector_activation_checklist.py", "@connector-activation"),
        ("n8n Dry Import Builder", "automation/central_orchestrator/runtime/n8n_dry_import_builder.py", "@n8n-dry-import"),
        ("Airtable Dry Import Builder", "automation/central_orchestrator/runtime/airtable_dry_import_builder.py", "@airtable-dry-import"),
        ("Notion Dry Import Builder", "automation/central_orchestrator/runtime/notion_dry_import_builder.py", "@notion-dry-import"),
        ("Google Workspace Dry Review Builder", "automation/central_orchestrator/runtime/google_workspace_dry_import_builder.py", "@google-workspace-dry-review"),
        ("Social Content Dry Review Builder", "automation/central_orchestrator/runtime/social_content_dry_review_builder.py", "@social-content-dry-review"),
        ("Property Intelligence Runtime", "automation/central_orchestrator/runtime/property_intelligence_runtime.py", "@property-intel"),
        ("Operations Assistant Runtime", "automation/central_orchestrator/runtime/operations_assistant_runtime.py", "@operations"),
        ("Client Pipeline Runtime", "automation/central_orchestrator/runtime/crm_followup_runtime.py", "@crm-followup"),
        ("Knowledge Vault Runtime", "automation/central_orchestrator/runtime/knowledge_vault_runtime.py", "@knowledge-vault"),
        ("Content Factory Runtime", "automation/central_orchestrator/runtime/content_factory_runtime.py", "@content-factory"),
        ("Mobile Command Runtime", "automation/central_orchestrator/runtime/mobile_command_runtime.py", "@mobile-command"),
        ("CEO Operating Runtime", "automation/central_orchestrator/runtime/ceo_operating_runtime.py", "@ceo"),
        ("Impact Metrics Runtime", "automation/central_orchestrator/runtime/impact_metrics_runtime.py", "@impact"),
        ("Unified Memory Runtime", "automation/central_orchestrator/runtime/unified_memory_runtime.py", "@memory"),
        ("Integrated AIOS Brain Runtime", "automation/central_orchestrator/runtime/aios_brain_runtime.py", "@brain"),
        ("A-Z Interaction Architecture Runtime", "automation/central_orchestrator/runtime/aios_interaction_architecture_runtime.py", "@interaction"),
        ("Connector Readiness Runtime", "automation/central_orchestrator/runtime/connector_readiness_runtime.py", "@readiness"),
        ("Connector Activation Command Runtime", "automation/central_orchestrator/runtime/connector_activation_command_runtime.py", "@activation-command"),
        ("AIOS Autopilot Runtime", "automation/central_orchestrator/runtime/aios_autopilot_runtime.py", "@autopilot"),
        ("Daily Command Session Runtime", "automation/central_orchestrator/runtime/daily_command_session_runtime.py", "@daily-command"),
        ("Usage Adoption Ledger Runtime", "automation/central_orchestrator/runtime/usage_adoption_ledger_runtime.py", "@usage-ledger"),
        ("Team Workspace Access Runtime", "automation/central_orchestrator/runtime/team_workspace_access_runtime.py", "@team-workspace"),
        ("Client Portal Experience Runtime", "automation/central_orchestrator/runtime/client_portal_experience_runtime.py", "@client-portal"),
        ("AIOS Customer Workspace Runtime", "automation/central_orchestrator/runtime/aios_customer_workspace_runtime.py", "@customer-workspace"),
        ("Business Data Model Runtime", "automation/central_orchestrator/runtime/business_data_model_runtime.py", "@data-model"),
        ("Business Sync Queue Runtime", "automation/central_orchestrator/runtime/business_sync_queue_runtime.py", "@sync-queue"),
        ("Weekly Operating Review Runtime", "automation/central_orchestrator/runtime/weekly_operating_review_runtime.py", "@weekly-review"),
        ("AIOS Website Platform", "AIOS-WEBSITE.html", "@website"),
        ("AIOS Mobile Command Console", "AIOS-MOBILE-APP.html", "@mobile"),
        ("WhatsApp Provider Gateway", "automation/whatsapp_provider_gateway/runtime/whatsapp_provider_gateway.py", "@whatsapp"),
        ("Lead Pipeline Engine", "automation/lead_pipeline_os/runtime/lead_pipeline_engine.py", "@lead"),
        ("CRM Lead Scorer", "automation/crm_business_os/runtime/crm_lead_scorer.py", "@crm"),
        ("Content Factory Request", "automation/marketing_automation/MARKETING-AUTOMATION-CONTROL.md", "@marketing"),
    ]
    for name, rel, command in automation:
        if (AIOS_ROOT / rel).exists():
            workflows.append(
                {
                    "name": name,
                    "path": rel,
                    "type": "automation_contract",
                    "run_mode": "safe_local_or_n8n_contract",
                    "approval_required": True,
                    "command": command,
                }
            )
    return workflows


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_health() -> dict[str, Any]:
    health_path = REPORTS_DIR / "COMMAND_CENTER_HEALTH.json"
    health = _load_json(health_path).get("health", {})
    defaults = {
        "brain": "online_local_router",
        "router": "ready",
        "crm": "writeback_contract_ready",
        "database": "local_state_ready",
        "whatsapp": "provider_gateway_contract_ready",
        "calendar": "handoff_contract_ready",
        "gmail": "draft_contract_ready",
        "drive": "knowledge_contract_ready",
        "follow_up": "task_contract_ready",
        "content_factory": "draft_contract_ready",
        "property_intelligence": "local_recommend_compare_runtime_ready",
        "operations_assistant": "local_operations_checklist_runtime_ready",
        "crm_followup": "local_lead_scoring_followup_runtime_ready",
        "knowledge_vault": "local_knowledge_retrieval_runtime_ready",
        "content_factory_runtime": "local_content_draft_generation_runtime_ready",
        "mobile_command_runtime": "local_mobile_command_routing_runtime_ready",
        "ceo_operating_runtime": "local_daily_operating_plan_runtime_ready",
        "impact_metrics_runtime": "local_success_metric_tracking_runtime_ready",
        "unified_memory_runtime": "local_one_brain_context_memory_ready",
        "aios_brain_runtime": "local_integrated_answer_brain_ready",
        "aios_interaction_architecture_runtime": "local_a_to_z_interaction_contract_ready",
        "connector_readiness_runtime": "local_end_state_connector_readiness_ready",
        "connector_activation_command_runtime": "local_connector_activation_command_plan_ready",
        "aios_autopilot_runtime": "local_autopilot_queue_ready",
        "daily_command_session_runtime": "local_daily_operating_session_ready",
        "usage_adoption_ledger_runtime": "local_usage_adoption_ledger_ready",
        "team_workspace_access_runtime": "local_team_workspace_access_ready",
        "client_portal_experience_runtime": "local_client_portal_experience_ready",
        "aios_customer_workspace_runtime": "local_aios_customer_workspace_ready",
        "business_data_model_runtime": "local_canonical_business_data_model_ready",
        "business_sync_queue_runtime": "local_connector_sync_queue_ready",
        "weekly_operating_review_runtime": "local_weekly_operating_review_ready",
        "website": "local_public_internal_platform_ready",
        "mobile_app": "local_mobile_console_ready",
        "search": "index_ready",
        "activity_feed": "ready",
        "ask_aios": "local_answer_runtime_ready",
        "daily_briefing": "local_briefing_ready",
        "action_runner": "local_packet_runner_ready",
        "approval_gate": "local_approval_state_ready",
        "approval_command": "local_decision_command_ready",
        "connector_manifest": "disabled_manifest_ready",
        "connector_dry_run": "local_connector_rehearsal_ready",
        "live_run_request": "local_final_review_packet_ready",
        "live_connector_runner": "disabled_runner_ready",
        "connector_payloads": "local_payload_contracts_ready",
        "connector_activation": "local_activation_checklist_ready",
        "n8n_dry_import": "local_n8n_import_draft_ready",
        "airtable_dry_import": "local_airtable_schema_map_ready",
        "notion_dry_import": "local_notion_page_draft_ready",
        "google_workspace_dry_import": "local_google_workspace_review_ready",
        "social_content_dry_review": "local_social_content_review_ready",
    }
    defaults.update({k: v for k, v in health.items() if v})
    return defaults


def build_activity(search_index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    files = []
    for rel in [
        "automation/central_orchestrator/reports/CENTRAL_ORCHESTRATOR_VALIDATION.json",
        "automation/central_orchestrator/reports/COMMAND_CENTER_HEALTH.json",
        "automation/central_orchestrator/reports/COMMAND_CENTER_DATA.json",
        "automation/central_orchestrator/reports/ASK_AIOS_LAST_RESPONSE.json",
        "automation/central_orchestrator/reports/AIOS_DAILY_BRIEFING.json",
        "automation/central_orchestrator/reports/ACTION_QUEUE.json",
        "automation/central_orchestrator/reports/LOCAL_ACTION_RUNNER_RESULT.json",
        "automation/central_orchestrator/reports/APPROVAL_STATE.json",
        "automation/central_orchestrator/reports/APPROVAL_MANAGER_RESULT.json",
        "automation/central_orchestrator/reports/LOCAL_APPROVAL_COMMAND_RESULT.json",
        "automation/central_orchestrator/reports/CONNECTOR_EXECUTION_MANIFEST.json",
        "automation/central_orchestrator/reports/CONNECTOR_EXECUTION_RESULT.json",
        "automation/central_orchestrator/reports/CONNECTOR_DRY_RUN_PLAN.json",
        "automation/central_orchestrator/reports/CONNECTOR_DRY_RUN_RESULT.json",
        "automation/central_orchestrator/reports/LIVE_RUN_REQUEST.json",
        "automation/central_orchestrator/reports/LIVE_RUN_REQUEST_RESULT.json",
        "automation/central_orchestrator/reports/LIVE_CONNECTOR_RUNNER_PLAN.json",
        "automation/central_orchestrator/reports/LIVE_CONNECTOR_RUNNER_RESULT.json",
        "automation/central_orchestrator/reports/CONNECTOR_PARAMETER_PAYLOADS.json",
        "automation/central_orchestrator/reports/CONNECTOR_PARAMETER_PAYLOADS_RESULT.json",
        "automation/central_orchestrator/reports/CONNECTOR_ACTIVATION_CHECKLIST.json",
        "automation/central_orchestrator/reports/CONNECTOR_ACTIVATION_CHECKLIST_RESULT.json",
        "automation/central_orchestrator/reports/N8N_DRY_IMPORT_MANIFEST.json",
        "automation/central_orchestrator/reports/N8N_DRY_IMPORT_RESULT.json",
        "automation/central_orchestrator/reports/AIRTABLE_DRY_IMPORT_SCHEMA.json",
        "automation/central_orchestrator/reports/AIRTABLE_DRY_IMPORT_RESULT.json",
        "automation/central_orchestrator/reports/NOTION_DRY_IMPORT_MANIFEST.json",
        "automation/central_orchestrator/reports/NOTION_DRY_IMPORT_RESULT.json",
        "automation/central_orchestrator/reports/GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json",
        "automation/central_orchestrator/reports/GOOGLE_WORKSPACE_DRY_IMPORT_RESULT.json",
        "automation/central_orchestrator/reports/SOCIAL_CONTENT_DRY_REVIEW_MANIFEST.json",
        "automation/central_orchestrator/reports/SOCIAL_CONTENT_DRY_REVIEW_RESULT.json",
        "automation/central_orchestrator/reports/PROPERTY_INTELLIGENCE_REPORT.json",
        "automation/central_orchestrator/reports/OPERATIONS_ASSISTANT_REPORT.json",
        "automation/central_orchestrator/reports/CRM_FOLLOWUP_REPORT.json",
        "automation/central_orchestrator/reports/KNOWLEDGE_VAULT_REPORT.json",
        "automation/central_orchestrator/reports/CONTENT_FACTORY_REPORT.json",
        "automation/central_orchestrator/reports/MOBILE_COMMAND_REPORT.json",
        "automation/central_orchestrator/reports/CEO_OPERATING_REPORT.json",
        "automation/central_orchestrator/reports/IMPACT_METRICS_REPORT.json",
        "automation/central_orchestrator/reports/UNIFIED_MEMORY_REPORT.json",
        "automation/central_orchestrator/reports/AIOS_BRAIN_REPORT.json",
        "automation/central_orchestrator/reports/AIOS_INTERACTION_ARCHITECTURE_REPORT.json",
        "automation/central_orchestrator/reports/CONNECTOR_READINESS_REPORT.json",
        "automation/central_orchestrator/reports/CONNECTOR_ACTIVATION_COMMAND_PLAN.json",
        "automation/central_orchestrator/reports/AIOS_AUTOPILOT_REPORT.json",
        "automation/central_orchestrator/reports/DAILY_COMMAND_SESSION.json",
        "automation/central_orchestrator/reports/USAGE_ADOPTION_LEDGER.json",
        "automation/central_orchestrator/reports/TEAM_WORKSPACE_ACCESS_REPORT.json",
        "automation/central_orchestrator/reports/CLIENT_PORTAL_EXPERIENCE_REPORT.json",
        "automation/central_orchestrator/reports/AIOS_CUSTOMER_WORKSPACE_REPORT.json",
        "automation/central_orchestrator/reports/BUSINESS_DATA_MODEL_REPORT.json",
        "automation/central_orchestrator/reports/BUSINESS_SYNC_QUEUE_REPORT.json",
        "automation/central_orchestrator/reports/WEEKLY_OPERATING_REVIEW_REPORT.json",
        "AIOS-DASHBOARD.html",
        "AIOS-WEBSITE.html",
        "AIOS-MOBILE-APP.html",
        "knowledge-base/branding/AIOS-BRAND-IDENTITY.md",
        "00-MASTER-HUB.md",
    ]:
        path = AIOS_ROOT / rel
        if path.exists():
            files.append(path)
    latest = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    activity = []
    for path in latest:
        rel = path.relative_to(AIOS_ROOT).as_posix()
        activity.append(
            {
                "time": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                "type": "system_update",
                "title": path.stem.replace("-", " ").replace("_", " ").title(),
                "path": rel,
                "summary": f"Updated {rel}",
            }
        )
    validation = _load_json(REPORTS_DIR / "CENTRAL_ORCHESTRATOR_VALIDATION.json")
    if validation:
        activity.insert(
            0,
            {
                "time": validation.get("validated_at", _now()),
                "type": "validation",
                "title": "Central Orchestrator Validation",
                "path": "automation/central_orchestrator/reports/CENTRAL_ORCHESTRATOR_VALIDATION.json",
                "summary": f"{validation.get('passed_count', 0)} passed / {validation.get('failed_count', 0)} failed",
            },
        )
    if search_index:
        activity.insert(
            0,
            {
                "time": _now(),
                "type": "index",
                "title": "Search Everything Index",
                "path": "automation/central_orchestrator/reports/COMMAND_CENTER_DATA.json",
                "summary": f"{len(search_index)} searchable AIOS records indexed",
            },
        )
    return activity[:12]


def build() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    search_index = build_search_index()
    last_response = _load_json(REPORTS_DIR / "ASK_AIOS_LAST_RESPONSE.json")
    daily_briefing = _load_json(REPORTS_DIR / "AIOS_DAILY_BRIEFING.json")
    action_queue = _load_json(REPORTS_DIR / "ACTION_QUEUE.json")
    action_result = _load_json(REPORTS_DIR / "LOCAL_ACTION_RUNNER_RESULT.json")
    approval_state = _load_json(REPORTS_DIR / "APPROVAL_STATE.json")
    approval_result = _load_json(REPORTS_DIR / "APPROVAL_MANAGER_RESULT.json")
    approval_command_result = _load_json(REPORTS_DIR / "LOCAL_APPROVAL_COMMAND_RESULT.json")
    connector_manifest = _load_json(REPORTS_DIR / "CONNECTOR_EXECUTION_MANIFEST.json")
    connector_result = _load_json(REPORTS_DIR / "CONNECTOR_EXECUTION_RESULT.json")
    connector_dry_run = _load_json(REPORTS_DIR / "CONNECTOR_DRY_RUN_PLAN.json")
    connector_dry_run_result = _load_json(REPORTS_DIR / "CONNECTOR_DRY_RUN_RESULT.json")
    live_run_request = _load_json(REPORTS_DIR / "LIVE_RUN_REQUEST.json")
    live_run_request_result = _load_json(REPORTS_DIR / "LIVE_RUN_REQUEST_RESULT.json")
    live_connector_runner = _load_json(REPORTS_DIR / "LIVE_CONNECTOR_RUNNER_PLAN.json")
    live_connector_runner_result = _load_json(REPORTS_DIR / "LIVE_CONNECTOR_RUNNER_RESULT.json")
    connector_payloads = _load_json(REPORTS_DIR / "CONNECTOR_PARAMETER_PAYLOADS.json")
    connector_payloads_result = _load_json(REPORTS_DIR / "CONNECTOR_PARAMETER_PAYLOADS_RESULT.json")
    connector_activation = _load_json(REPORTS_DIR / "CONNECTOR_ACTIVATION_CHECKLIST.json")
    connector_activation_result = _load_json(REPORTS_DIR / "CONNECTOR_ACTIVATION_CHECKLIST_RESULT.json")
    n8n_dry_import = _load_json(REPORTS_DIR / "N8N_DRY_IMPORT_MANIFEST.json")
    n8n_dry_import_result = _load_json(REPORTS_DIR / "N8N_DRY_IMPORT_RESULT.json")
    airtable_dry_import = _load_json(REPORTS_DIR / "AIRTABLE_DRY_IMPORT_SCHEMA.json")
    airtable_dry_import_result = _load_json(REPORTS_DIR / "AIRTABLE_DRY_IMPORT_RESULT.json")
    notion_dry_import = _load_json(REPORTS_DIR / "NOTION_DRY_IMPORT_MANIFEST.json")
    notion_dry_import_result = _load_json(REPORTS_DIR / "NOTION_DRY_IMPORT_RESULT.json")
    google_workspace_dry_import = _load_json(REPORTS_DIR / "GOOGLE_WORKSPACE_DRY_IMPORT_MANIFEST.json")
    google_workspace_dry_import_result = _load_json(REPORTS_DIR / "GOOGLE_WORKSPACE_DRY_IMPORT_RESULT.json")
    social_content_dry_review = _load_json(REPORTS_DIR / "SOCIAL_CONTENT_DRY_REVIEW_MANIFEST.json")
    social_content_dry_review_result = _load_json(REPORTS_DIR / "SOCIAL_CONTENT_DRY_REVIEW_RESULT.json")
    property_intelligence = _load_json(REPORTS_DIR / "PROPERTY_INTELLIGENCE_REPORT.json")
    operations_assistant = _load_json(REPORTS_DIR / "OPERATIONS_ASSISTANT_REPORT.json")
    crm_followup = _load_json(REPORTS_DIR / "CRM_FOLLOWUP_REPORT.json")
    knowledge_vault = _load_json(REPORTS_DIR / "KNOWLEDGE_VAULT_REPORT.json")
    content_factory_report = _load_json(REPORTS_DIR / "CONTENT_FACTORY_REPORT.json")
    mobile_command_report = _load_json(REPORTS_DIR / "MOBILE_COMMAND_REPORT.json")
    ceo_operating_report = _load_json(REPORTS_DIR / "CEO_OPERATING_REPORT.json")
    impact_metrics_report = _load_json(REPORTS_DIR / "IMPACT_METRICS_REPORT.json")
    unified_memory_report = _load_json(REPORTS_DIR / "UNIFIED_MEMORY_REPORT.json")
    aios_brain_report = _load_json(REPORTS_DIR / "AIOS_BRAIN_REPORT.json")
    aios_interaction_architecture = _load_json(REPORTS_DIR / "AIOS_INTERACTION_ARCHITECTURE_REPORT.json")
    connector_readiness_report = _load_json(REPORTS_DIR / "CONNECTOR_READINESS_REPORT.json")
    connector_activation_command_plan = _load_json(REPORTS_DIR / "CONNECTOR_ACTIVATION_COMMAND_PLAN.json")
    aios_autopilot_report = _load_json(REPORTS_DIR / "AIOS_AUTOPILOT_REPORT.json")
    daily_command_session = _load_json(REPORTS_DIR / "DAILY_COMMAND_SESSION.json")
    usage_adoption_ledger = _load_json(REPORTS_DIR / "USAGE_ADOPTION_LEDGER.json")
    team_workspace_access = _load_json(REPORTS_DIR / "TEAM_WORKSPACE_ACCESS_REPORT.json")
    client_portal_experience = _load_json(REPORTS_DIR / "CLIENT_PORTAL_EXPERIENCE_REPORT.json")
    aios_customer_workspace = _load_json(REPORTS_DIR / "AIOS_CUSTOMER_WORKSPACE_REPORT.json")
    business_data_model = _load_json(REPORTS_DIR / "BUSINESS_DATA_MODEL_REPORT.json")
    business_sync_queue = _load_json(REPORTS_DIR / "BUSINESS_SYNC_QUEUE_REPORT.json")
    weekly_operating_review = _load_json(REPORTS_DIR / "WEEKLY_OPERATING_REVIEW_REPORT.json")
    payload = {
        "generated_at": _now(),
        "system": "AIOS Command Center",
        "mode": "safe_local_no_external_side_effects",
        "health": build_health(),
        "search_index": search_index,
        "workflows": build_workflows(),
        "activity": build_activity(search_index),
        "ask_aios": last_response,
        "daily_briefing": daily_briefing,
        "action_queue": action_queue,
        "action_result": action_result,
        "approval_state": approval_state,
        "approval_result": approval_result,
        "approval_command_result": approval_command_result,
        "connector_manifest": connector_manifest,
        "connector_result": connector_result,
        "connector_dry_run": connector_dry_run,
        "connector_dry_run_result": connector_dry_run_result,
        "live_run_request": live_run_request,
        "live_run_request_result": live_run_request_result,
        "live_connector_runner": live_connector_runner,
        "live_connector_runner_result": live_connector_runner_result,
        "connector_payloads": connector_payloads,
        "connector_payloads_result": connector_payloads_result,
        "connector_activation": connector_activation,
        "connector_activation_result": connector_activation_result,
        "n8n_dry_import": n8n_dry_import,
        "n8n_dry_import_result": n8n_dry_import_result,
        "airtable_dry_import": airtable_dry_import,
        "airtable_dry_import_result": airtable_dry_import_result,
        "notion_dry_import": notion_dry_import,
        "notion_dry_import_result": notion_dry_import_result,
        "google_workspace_dry_import": google_workspace_dry_import,
        "google_workspace_dry_import_result": google_workspace_dry_import_result,
        "social_content_dry_review": social_content_dry_review,
        "social_content_dry_review_result": social_content_dry_review_result,
        "property_intelligence": property_intelligence,
        "operations_assistant": operations_assistant,
        "crm_followup": crm_followup,
        "knowledge_vault": knowledge_vault,
        "content_factory_report": content_factory_report,
        "mobile_command_report": mobile_command_report,
        "ceo_operating_report": ceo_operating_report,
        "impact_metrics_report": impact_metrics_report,
        "unified_memory_report": unified_memory_report,
        "aios_brain_report": aios_brain_report,
        "aios_interaction_architecture": aios_interaction_architecture,
        "connector_readiness_report": connector_readiness_report,
        "connector_activation_command_plan": connector_activation_command_plan,
        "aios_autopilot_report": aios_autopilot_report,
        "daily_command_session": daily_command_session,
        "usage_adoption_ledger": usage_adoption_ledger,
        "team_workspace_access": team_workspace_access,
        "client_portal_experience": client_portal_experience,
        "aios_customer_workspace": aios_customer_workspace,
        "business_data_model": business_data_model,
        "business_sync_queue": business_sync_queue,
        "weekly_operating_review": weekly_operating_review,
        "external_side_effects": {
            "messages_sent": False,
            "crm_rows_written": False,
            "airtable_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "content_published": False,
            "portal_submissions": False,
            "payments_made": False,
            "legal_claims_finalized": False,
            "gmail_drafts_created": False,
            "tasks_created_externally": False,
            "notion_pages_created": False,
            "vector_db_written": False,
            "documents_uploaded": False,
            "external_search_called": False,
            "content_assets_generated": False,
            "instagram_posts_published": False,
            "whatsapp_broadcasts_sent": False,
            "canva_designs_created": False,
            "video_jobs_started": False,
            "paid_ads_launched": False,
            "notifications_pushed_to_device": False,
            "voice_audio_recorded": False,
            "external_transcription_called": False,
            "external_analytics_called": False,
            "conversation_state_written": False,
            "vector_db_written": False,
            "external_llm_called": False,
            "workflow_executed": False,
            "network_calls_made": False,
            "credentials_read": False,
            "oauth_started": False,
            "n8n_workflows_imported": False,
            "n8n_workflows_activated": False,
            "future_channel_activated": False,
            "connector_activation_command_started_oauth": False,
            "autopilot_live_execution": False,
            "daily_command_live_execution": False,
            "usage_analytics_sent": False,
            "team_workspace_published": False,
            "client_portal_published": False,
            "client_accounts_created": False,
            "client_files_shared": False,
            "customer_workspace_published": False,
            "customer_accounts_created": False,
            "demo_invites_sent": False,
            "trial_started": False,
            "checkout_started": False,
            "business_data_model_written": False,
            "canonical_schema_published": False,
            "connector_schema_synced": False,
            "business_sync_packets_executed": False,
            "connector_sync_queue_published": False,
            "weekly_report_sent": False,
            "weekly_review_published": False,
            "external_invites_sent": False,
        },
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False))
