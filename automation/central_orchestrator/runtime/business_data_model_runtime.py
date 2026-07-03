#!/usr/bin/env python3
"""Build the AIOS canonical business data model.

This local runtime defines the source-of-truth entities, relationships, and
connector sync contracts for HSH. It does not create Airtable tables, write CRM
rows, create Drive/Notion files, send messages, create calendar events, or call
external services.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "BUSINESS_DATA_MODEL_REPORT.json"

SOURCE_REPORTS = {
    "command_center_data": "COMMAND_CENTER_DATA.json",
    "crm_followup": "CRM_FOLLOWUP_REPORT.json",
    "property_intelligence": "PROPERTY_INTELLIGENCE_REPORT.json",
    "operations_assistant": "OPERATIONS_ASSISTANT_REPORT.json",
    "knowledge_vault": "KNOWLEDGE_VAULT_REPORT.json",
    "content_factory": "CONTENT_FACTORY_REPORT.json",
    "connector_readiness": "CONNECTOR_READINESS_REPORT.json",
    "client_portal_experience": "CLIENT_PORTAL_EXPERIENCE_REPORT.json",
    "aios_customer_workspace": "AIOS_CUSTOMER_WORKSPACE_REPORT.json",
}

EXTERNAL_SIDE_EFFECTS = {
    "airtable_tables_created": False,
    "airtable_rows_written": False,
    "crm_rows_written": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_created": False,
    "drive_files_shared": False,
    "notion_pages_created": False,
    "whatsapp_messages_sent": False,
    "instagram_posts_published": False,
    "n8n_workflows_imported": False,
    "network_calls_made": False,
    "credentials_read": False,
    "oauth_started": False,
}


CANONICAL_ENTITIES = [
    {
        "entity": "lead",
        "label": "Lead",
        "owner_module": "@crm-followup",
        "record_id_pattern": "LEAD-{area_or_source}-{sequence}",
        "required_fields": ["lead_id", "name", "channel", "client_type", "requirement", "stage", "score", "next_action", "next_action_date", "consent_status"],
        "optional_fields": ["phone", "email", "budget", "areas", "timeline", "source_campaign", "assigned_owner", "risk_flags"],
        "privacy_class": "client_confidential",
    },
    {
        "entity": "contact",
        "label": "Contact",
        "owner_module": "@crm-followup",
        "record_id_pattern": "CONTACT-{normalized_phone_or_email}",
        "required_fields": ["contact_id", "display_name", "primary_channel", "relationship_type", "consent_status", "last_interaction_at"],
        "optional_fields": ["phone", "email", "whatsapp_id", "preferred_language", "notes_redacted"],
        "privacy_class": "client_confidential",
    },
    {
        "entity": "property",
        "label": "Property",
        "owner_module": "@property-intel",
        "record_id_pattern": "PROP-{community}-{unit_or_slug}",
        "required_fields": ["property_id", "community", "property_type", "beds", "price", "availability_status", "source_status"],
        "optional_fields": ["developer", "project", "size_sqft", "service_charge", "permit_status", "owner_contact_id"],
        "privacy_class": "business_internal",
    },
    {
        "entity": "deal",
        "label": "Deal",
        "owner_module": "@operations",
        "record_id_pattern": "DEAL-{lead_id}-{property_id}",
        "required_fields": ["deal_id", "lead_id", "property_id", "deal_type", "stage", "risk_gate", "next_step"],
        "optional_fields": ["offer_amount", "commission_model", "expected_close_date", "documents_required", "authority_case_id"],
        "privacy_class": "commercial_confidential",
    },
    {
        "entity": "task",
        "label": "Task",
        "owner_module": "@daily-command",
        "record_id_pattern": "TASK-{source}-{timestamp}",
        "required_fields": ["task_id", "title", "owner", "due_at", "priority", "status", "source_entity", "approval_gate"],
        "optional_fields": ["description", "related_lead_id", "related_deal_id", "related_document_id", "automation_packet"],
        "privacy_class": "business_internal",
    },
    {
        "entity": "communication",
        "label": "Communication",
        "owner_module": "@brain",
        "record_id_pattern": "COMMS-{channel}-{message_id}",
        "required_fields": ["communication_id", "channel", "direction", "contact_id", "summary", "safety_gate", "occurred_at"],
        "optional_fields": ["thread_id", "draft_response", "related_lead_id", "related_task_id", "redaction_status"],
        "privacy_class": "client_confidential",
    },
    {
        "entity": "document",
        "label": "Document",
        "owner_module": "@knowledge-vault",
        "record_id_pattern": "DOC-{case_or_entity}-{slug}",
        "required_fields": ["document_id", "document_type", "owner_entity", "status", "storage_contract", "review_gate"],
        "optional_fields": ["drive_path", "notion_page", "expiry_date", "authority_reference", "redacted_summary"],
        "privacy_class": "document_confidential",
    },
    {
        "entity": "content_asset",
        "label": "Content Asset",
        "owner_module": "@content-factory",
        "record_id_pattern": "CONTENT-{campaign}-{asset_type}",
        "required_fields": ["content_id", "asset_type", "campaign", "status", "compliance_gate", "publish_allowed"],
        "optional_fields": ["property_id", "caption", "script", "design_path", "channel", "approval_reference"],
        "privacy_class": "marketing_internal",
    },
    {
        "entity": "approval",
        "label": "Approval",
        "owner_module": "@approve-local",
        "record_id_pattern": "APPROVAL-{action_id}",
        "required_fields": ["approval_id", "action_id", "decision", "actor", "decided_at", "external_execution_enabled"],
        "optional_fields": ["note", "packet_path", "connector_manifest_id", "final_approval_reference"],
        "privacy_class": "business_internal",
    },
    {
        "entity": "workflow",
        "label": "Workflow",
        "owner_module": "@aios",
        "record_id_pattern": "WF-{domain}-{sequence}",
        "required_fields": ["workflow_id", "name", "domain", "command", "run_mode", "approval_required"],
        "optional_fields": ["source_path", "last_validated_at", "n8n_contract", "owner_role"],
        "privacy_class": "business_internal",
    },
    {
        "entity": "calendar_event",
        "label": "Calendar Event",
        "owner_module": "@calendar-handoff",
        "record_id_pattern": "CAL-{request_id}",
        "required_fields": ["calendar_event_id", "title", "requested_window", "attendees_redacted", "status", "approval_gate"],
        "optional_fields": ["related_lead_id", "related_deal_id", "location", "calendar_id_contract"],
        "privacy_class": "client_confidential",
    },
    {
        "entity": "knowledge_asset",
        "label": "Knowledge Asset",
        "owner_module": "@knowledge-vault",
        "record_id_pattern": "KNOW-{category}-{slug}",
        "required_fields": ["knowledge_id", "category", "title", "source_path", "retrieval_tags", "last_indexed_at"],
        "optional_fields": ["related_workflow_id", "authority_reference", "version", "redaction_status"],
        "privacy_class": "business_internal",
    },
]

RELATIONSHIPS = [
    {"from": "contact", "to": "lead", "type": "can_have_many", "key": "contact_id"},
    {"from": "lead", "to": "deal", "type": "can_create_many", "key": "lead_id"},
    {"from": "property", "to": "deal", "type": "can_attach_to_many", "key": "property_id"},
    {"from": "deal", "to": "document", "type": "requires_many", "key": "deal_id"},
    {"from": "lead", "to": "communication", "type": "has_many", "key": "lead_id"},
    {"from": "lead", "to": "task", "type": "generates_many", "key": "lead_id"},
    {"from": "task", "to": "approval", "type": "may_require", "key": "action_id"},
    {"from": "workflow", "to": "task", "type": "creates_many", "key": "workflow_id"},
    {"from": "property", "to": "content_asset", "type": "can_generate_many", "key": "property_id"},
    {"from": "knowledge_asset", "to": "workflow", "type": "supports_many", "key": "knowledge_id"},
    {"from": "calendar_event", "to": "lead", "type": "can_reference", "key": "lead_id"},
]

CONNECTOR_MAPPINGS = [
    {"connector": "airtable", "target": "CRM source of truth tables", "entities": ["lead", "contact", "deal", "task", "approval", "workflow"], "write_enabled": False, "credential_required": True},
    {"connector": "google_drive", "target": "document and content storage", "entities": ["document", "content_asset", "knowledge_asset"], "write_enabled": False, "credential_required": True},
    {"connector": "gmail", "target": "draft communications and support threads", "entities": ["communication", "task", "lead"], "write_enabled": False, "credential_required": True},
    {"connector": "google_calendar", "target": "viewing, call, and deadline scheduling", "entities": ["calendar_event", "task", "lead", "deal"], "write_enabled": False, "credential_required": True},
    {"connector": "notion", "target": "knowledge workspace and operating pages", "entities": ["knowledge_asset", "workflow", "document", "task"], "write_enabled": False, "credential_required": True},
    {"connector": "whatsapp", "target": "client communication summaries and reply drafts", "entities": ["communication", "lead", "contact", "task"], "write_enabled": False, "credential_required": True},
    {"connector": "instagram", "target": "approved marketing content publishing", "entities": ["content_asset", "property"], "write_enabled": False, "credential_required": True},
    {"connector": "n8n", "target": "workflow automation runner", "entities": ["workflow", "task", "approval"], "write_enabled": False, "credential_required": True},
    {"connector": "future_channels", "target": "future communication and sales channels", "entities": ["communication", "lead", "task"], "write_enabled": False, "credential_required": True},
]

MIGRATION_GATES = [
    "Omar approves canonical entity names and required fields.",
    "Airtable base/table/field mapping is manually confirmed.",
    "Google Drive folder contracts and sharing rules are confirmed.",
    "Gmail and Calendar OAuth scopes are approved.",
    "Notion workspace/database contracts are approved.",
    "WhatsApp provider write policy is approved without Meta/Facebook login dependency.",
    "Instagram publishing stays disabled until content compliance and account authorization are approved.",
    "n8n import and activation remain disabled until final live-run approval.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_report(name: str) -> dict[str, Any]:
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    reports = {key: _load_report(name) for key, name in SOURCE_REPORTS.items()}
    entity_names = [entity["entity"] for entity in CANONICAL_ENTITIES]
    connector_names = [mapping["connector"] for mapping in CONNECTOR_MAPPINGS]
    missing_required = [entity["entity"] for entity in CANONICAL_ENTITIES if len(entity.get("required_fields", [])) < 5]
    unsafe_mappings = [mapping["connector"] for mapping in CONNECTOR_MAPPINGS if mapping.get("write_enabled") is not False]
    result = {
        "generated_at": _now(),
        "mode": "safe_local_business_data_model_no_external_side_effects",
        "summary": {
            "entity_count": len(CANONICAL_ENTITIES),
            "relationship_count": len(RELATIONSHIPS),
            "connector_mapping_count": len(CONNECTOR_MAPPINGS),
            "migration_gate_count": len(MIGRATION_GATES),
            "required_field_contracts_complete": not missing_required,
            "all_connector_writes_disabled": not unsafe_mappings,
            "all_external_actions_disabled": all(value is False for value in EXTERNAL_SIDE_EFFECTS.values()),
            "canonical_entities_ready": len(CANONICAL_ENTITIES) >= 12 and not missing_required,
        },
        "canonical_entities": CANONICAL_ENTITIES,
        "relationships": RELATIONSHIPS,
        "connector_mappings": CONNECTOR_MAPPINGS,
        "migration_gates": MIGRATION_GATES,
        "entity_names": entity_names,
        "connector_names": connector_names,
        "source_metrics": {
            "crm_leads": reports["crm_followup"].get("lead_count", 0),
            "property_matches": reports["property_intelligence"].get("matched_count", 0),
            "operations_cases": reports["operations_assistant"].get("case_count", 0),
            "knowledge_assets": reports["knowledge_vault"].get("asset_count", 0),
            "content_artifacts": reports["content_factory"].get("artifact_count", 0),
            "command_center_workflows": len(reports["command_center_data"].get("workflows", [])),
            "connector_count": reports["connector_readiness"].get("summary", {}).get("connector_count", 0),
        },
        "governance_policy": {
            "source_of_truth_rule": "AIOS canonical entities define the HSH business data model before any live connector writes are enabled.",
            "write_rule": "Airtable, Drive, Gmail, Calendar, Notion, WhatsApp, Instagram, n8n, and future-channel writes remain disabled until migration gates are approved.",
            "privacy_rule": "Client-confidential and document-confidential fields require redaction before customer demos, exports, or shared views.",
        },
        "source_reports": SOURCE_REPORTS,
        "external_side_effects": EXTERNAL_SIDE_EFFECTS,
        "requested_payload": payload,
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
