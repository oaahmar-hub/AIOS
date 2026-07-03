#!/usr/bin/env python3
"""Validate the GD Core Orchestrator against representative AIOS events."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from build_command_center_data import build as build_command_center_data
from ask_aios import ask
from gd_core_orchestrator import process
from local_action_runner import run as run_local_action
from approval_state_manager import APPROVAL_STATE_PATH, run as run_approval_state
from local_approval_command import run as run_local_approval_command
from connector_execution_manifest import build as build_connector_manifest
from connector_dry_run_executor import build as build_connector_dry_run
from live_run_request_builder import build as build_live_run_request
from disabled_live_connector_runner import run as run_disabled_live_connector_runner
from connector_payload_builder import build as build_connector_payloads
from connector_activation_checklist import build as build_connector_activation_checklist
from n8n_dry_import_builder import build as build_n8n_dry_import
from airtable_dry_import_builder import build as build_airtable_dry_import
from notion_dry_import_builder import build as build_notion_dry_import
from google_workspace_dry_import_builder import build as build_google_workspace_dry_import
from social_content_dry_review_builder import build as build_social_content_dry_review
from property_intelligence_runtime import build as build_property_intelligence
from operations_assistant_runtime import build as build_operations_assistant
from crm_followup_runtime import build as build_crm_followup
from knowledge_vault_runtime import build as build_knowledge_vault
from content_factory_runtime import build as build_content_factory
from mobile_command_runtime import build as build_mobile_command
from ceo_operating_runtime import build as build_ceo_operating
from impact_metrics_runtime import build as build_impact_metrics
from unified_memory_runtime import build as build_unified_memory
from aios_brain_runtime import build as build_aios_brain
from aios_interaction_architecture_runtime import build as build_aios_interaction_architecture
from connector_readiness_runtime import build as build_connector_readiness
from connector_activation_command_runtime import build as build_connector_activation_command
from aios_autopilot_runtime import build as build_aios_autopilot
from daily_command_session_runtime import build as build_daily_command_session
from usage_adoption_ledger_runtime import build as build_usage_adoption_ledger
from team_workspace_access_runtime import build as build_team_workspace_access
from client_portal_experience_runtime import build as build_client_portal_experience
from aios_customer_workspace_runtime import build as build_aios_customer_workspace
from business_data_model_runtime import build as build_business_data_model
from business_sync_queue_runtime import build as build_business_sync_queue
from weekly_operating_review_runtime import build as build_weekly_operating_review
from aios_live_api_server import AUDIT_LOG_PATH as PERMISSION_AUDIT_LOG_PATH
from aios_live_api_server import evaluate_permission_api


REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "CENTRAL_ORCHESTRATOR_VALIDATION.json"
HEALTH_PATH = Path(__file__).resolve().parents[1] / "reports" / "COMMAND_CENTER_HEALTH.json"
AIOS_ROOT = Path(__file__).resolve().parents[3]
WEBSITE_PATH = AIOS_ROOT / "AIOS-WEBSITE.html"
MOBILE_APP_PATH = AIOS_ROOT / "AIOS-MOBILE-APP.html"
PRODUCT_IDENTITY_PATH = AIOS_ROOT / "knowledge-base/branding/AIOS-PRODUCT-IDENTITY-DIRECTIVE.md"


SCENARIOS = [
    {
        "name": "whatsapp_safe_property_inquiry",
        "event": {
            "provider": "twilio",
            "SmsMessageSid": "SM-CENTRAL-001",
            "From": "whatsapp:+971555111222",
            "To": "whatsapp:+971555593714",
            "ProfileName": "Test Buyer",
            "Body": "Hi, looking to buy a 2 bed in Dubai Marina, budget AED 2.5m",
        },
        "expect": {
            "channel": "whatsapp",
            "side_effects_false": True,
            "has_whatsapp_module": True,
        },
    },
    {
        "name": "whatsapp_risky_contract_payment_hold",
        "event": {
            "provider": "twilio",
            "SmsMessageSid": "SM-CENTRAL-002",
            "From": "whatsapp:+971555333444",
            "To": "whatsapp:+971555593714",
            "ProfileName": "Risk Test",
            "Body": "Can I send passport and title deed now for DLD transfer payment?",
        },
        "expect": {
            "channel": "whatsapp",
            "safety_gate_contains": "HOLD",
            "side_effects_false": True,
        },
    },
    {
        "name": "gmail_follow_up_draft",
        "event": {
            "channel": "gmail",
            "from_email": "client@example.com",
            "from_name": "Client Example",
            "subject": "Viewing appointment",
            "body": "Please arrange a viewing today for the Palm villa.",
        },
        "expect": {
            "channel": "gmail",
            "safety_gate_contains": "DRAFT",
            "side_effects_false": True,
        },
    },
    {
        "name": "document_intake_noc",
        "event": {
            "channel": "document",
            "file_name": "nakheel_noc_request.pdf",
            "document_text": "Nakheel NOC approval request for villa modification and title deed reference.",
        },
        "expect": {
            "channel": "document",
            "domain": "knowledge_vault",
            "side_effects_false": True,
        },
    },
    {
        "name": "content_factory_reel",
        "event": {
            "channel": "content",
            "brief": "Create a reel script and caption for Dubai Hills investment listings.",
        },
        "expect": {
            "channel": "content_factory",
            "safety_gate_contains": "NO_PUBLISH",
            "side_effects_false": True,
        },
    },
    {
        "name": "command_center_health",
        "event": {
            "channel": "health",
            "command": "show AIOS dashboard health",
        },
        "expect": {
            "channel": "command_center",
            "safety_gate_contains": "READ_ONLY",
            "side_effects_false": True,
        },
    },
]


def check(result: dict, expect: dict) -> list[str]:
    errors: list[str] = []
    event = result["aios_event"]
    route = result["route"]
    if event["channel"] != expect.get("channel"):
        errors.append(f"channel expected {expect.get('channel')} got {event['channel']}")
    if expect.get("domain") and event["domain"] != expect["domain"]:
        errors.append(f"domain expected {expect['domain']} got {event['domain']}")
    if expect.get("safety_gate_contains") and expect["safety_gate_contains"] not in route.get("safety_gate", ""):
        errors.append(f"safety gate missing {expect['safety_gate_contains']}: {route.get('safety_gate')}")
    if expect.get("has_whatsapp_module") and "whatsapp_provider_gateway" not in result.get("module_output", {}):
        errors.append("whatsapp module output missing")
    if expect.get("side_effects_false"):
        side_effects = result.get("external_side_effects", {})
        bad = [key for key, value in side_effects.items() if value is not False]
        if bad:
            errors.append(f"external side effects not false: {bad}")
    interaction = result.get("interaction_contract", {})
    if not interaction.get("identity") or not interaction.get("permission") or not interaction.get("response_generation"):
        errors.append("interaction contract missing identity, permission, or response generation")
    if interaction.get("memory_update", {}).get("write_enabled") is not False:
        errors.append("interaction memory update unexpectedly enabled writes")
    if interaction.get("response_generation", {}).get("reply_enabled") is not False:
        errors.append("interaction response unexpectedly enabled auto-reply")
    health = result.get("command_center_health", {})
    required_health = {"brain", "router", "crm", "database", "whatsapp", "calendar", "gmail", "drive", "follow_up"}
    missing_health = sorted(required_health - set(health))
    if missing_health:
        errors.append(f"health keys missing: {missing_health}")
    return errors


def main() -> int:
    rows = []
    health = {}
    for scenario in SCENARIOS:
        result = process(scenario["event"])
        errors = check(result, scenario["expect"])
        rows.append(
            {
                "name": scenario["name"],
                "passed": not errors,
                "errors": errors,
                "channel": result["aios_event"]["channel"],
                "domain": result["aios_event"]["domain"],
                "priority": result["aios_event"]["priority"],
                "safety_gate": result["route"].get("safety_gate"),
                "side_effects": result["external_side_effects"],
            }
        )
        health = result.get("command_center_health", health)

    ask_response = ask("Find the NOC workflow and prepare today's AIOS daily briefing")
    action_result = run_local_action("Find the NOC workflow and required checklist")
    approval_result = run_approval_state({"action": "sync"})
    approval_state_for_command = json.loads(APPROVAL_STATE_PATH.read_text(encoding="utf-8"))
    approval_command_result = {}
    reverted_approval_command_result = {}
    live_run_request_after_approve = {}
    live_runner_after_approve_refusal = {}
    live_runner_after_approve_validated = {}
    connector_payloads_after_approve = {}
    connector_activation_after_approve = {}
    n8n_dry_import_after_approve = {}
    airtable_dry_import_after_approve = {}
    notion_dry_import_after_approve = {}
    google_workspace_briefing_after_approve = {}
    google_workspace_content_after_approve = {}
    social_content_after_approve = {}
    property_intelligence_result = build_property_intelligence(
        {
            "query": "validation property recommendation and comparison",
            "lead": {"intent": "buy", "area": "JVC", "budget": 1_000_000, "beds": 2, "purpose": "investment"},
        }
    )
    operations_assistant_result = build_operations_assistant(
        {
            "case_type": "dld_transfer",
            "property_type": "apartment",
            "purchase_price": 2_000_000,
            "mortgage": True,
            "loan_amount": 1_500_000,
            "developer": "Nakheel",
            "community": "JVC",
        }
    )
    crm_followup_result = build_crm_followup(
        {
            "leads": [
                {
                    "lead_id": "LEAD-JVC-READY-001",
                    "name": "Validation Buyer",
                    "channel": "WhatsApp",
                    "client_type": "buyer",
                    "message": "Cash buyer. Need 2 bed in JVC, budget AED 1m, viewing today if possible.",
                    "budget": "AED 1,000,000",
                    "areas": ["JVC"],
                    "timeline": "today",
                    "last_contact_hours_ago": 2,
                    "stage": "Inquiry",
                    "kyc_status": "PENDING",
                },
                {
                    "lead_id": "LEAD-PALM-SELLER-002",
                    "name": "Palm Owner",
                    "channel": "Referral call",
                    "client_type": "seller",
                    "message": "Owner wants valuation for Palm villa and may sell this month.",
                    "areas": ["Palm Jumeirah"],
                    "timeline": "this month",
                    "last_contact_hours_ago": 18,
                    "stage": "Qualified",
                    "kyc_status": "PENDING",
                },
                {
                    "lead_id": "LEAD-DH-TENANT-003",
                    "name": "Dubai Hills Tenant",
                    "channel": "Portal message",
                    "client_type": "tenant",
                    "message": "Looking for 1 bedroom in Dubai Hills, move in around 3 months, budget flexible.",
                    "budget": "flexible",
                    "areas": ["Dubai Hills"],
                    "timeline": "3 months",
                    "last_contact_hours_ago": 30,
                    "stage": "New",
                    "kyc_status": "PENDING",
                },
            ]
        }
    )
    knowledge_vault_result = build_knowledge_vault(
        {
            "queries": [
                "NOC checklist",
                "DLD transfer",
                "tenancy contract",
                "lead qualification",
                "document intake",
            ]
        }
    )
    content_factory_result = build_content_factory(
        {
            "campaign_name": "Validation JVC Content Factory",
            "property_title": "Ready 2BR Apartment",
            "community": "JVC District 12",
            "price": 980_000,
            "beds": 2,
            "baths": 2,
            "size_sqft": 1080,
            "availability": "Available, subject to confirmation",
            "key_message": "A ready two-bedroom JVC option with budget-fit investment appeal.",
            "cta": "Reply with your viewing window and I will verify availability first.",
            "permit_status": "RERA permit required before publishing",
        }
    )
    mobile_command_result = build_mobile_command(
        {
            "commands": [
                {
                    "command_id": "MOB-VALID-001",
                    "input_type": "typed",
                    "text": "Find JVC 2 bed options under AED 1m and prepare WhatsApp reply",
                },
                {
                    "command_id": "MOB-VALID-002",
                    "input_type": "voice",
                    "transcript": "Remind me to follow up with the Palm seller tomorrow and draft a valuation email",
                },
                {
                    "command_id": "MOB-VALID-003",
                    "input_type": "typed",
                    "text": "Show DLD transfer checklist with mortgage cash to close",
                },
                {
                    "command_id": "MOB-VALID-004",
                    "input_type": "voice",
                    "transcript": "Find title deed and NOC documents for Nakheel approval package",
                },
                {
                    "command_id": "MOB-VALID-005",
                    "input_type": "typed",
                    "text": "Create Instagram caption and reel script for Dubai Hills listing",
                },
            ]
        }
    )
    ceo_operating_result = build_ceo_operating({"operator": "Omar", "operating_day": "validation"})
    impact_metrics_result = build_impact_metrics({"period": "validation"})
    unified_memory_result = build_unified_memory({"scope": "validation"})
    aios_brain_result = build_aios_brain(
        {
            "queries": [
                "What should Omar do first today?",
                "Find JVC property options and prepare the safest client reply",
                "Show DLD transfer and NOC checklist risks before any submission",
                "Which leads need follow-up and what should we draft?",
                "Create campaign content but keep publishing disabled",
                "Load WhatsApp context before replying to a returning contact",
            ]
        }
    )
    aios_interaction_architecture_result = build_aios_interaction_architecture(
        {
            "events": [
                {
                    "channel": "whatsapp",
                    "profile_name": "Returning Marina Buyer",
                    "relationship": "existing_client",
                    "message": "Omar, any 2 bed available in Dubai Marina today? Budget 2.5m.",
                    "conversation_count": 7,
                    "property_interests": ["Dubai Marina", "2 bed"],
                },
                {
                    "channel": "whatsapp",
                    "profile_name": "Agent Broker",
                    "relationship": "agent_broker",
                    "message": "Send owner phone and internal commission on the Palm villa.",
                    "conversation_count": 2,
                },
                {
                    "channel": "website",
                    "profile_name": "New Website Lead",
                    "message": "Looking for payment plan options in JVC and brochures.",
                },
                {
                    "channel": "mobile_app",
                    "profile_name": "Omar",
                    "is_owner": True,
                    "message": "Show blocked workflows and today's priorities.",
                    "tasks_open": 5,
                },
                {
                    "channel": "future_voice",
                    "profile_name": "HSH Staff",
                    "relationship": "hsh_staff",
                    "transcript": "Client is angry about delayed NOC. Prepare next action.",
                },
            ]
        }
    )
    permission_api_decisions = [
        evaluate_permission_api(
            {
                "request": "Give me owner phone number",
                "channel": channel,
                "identity_type": "Unknown",
                "source": "validation",
            }
        )
        for channel in ["whatsapp", "website", "mobile_app", "future_instagram", "future_email", "future_voice"]
    ]
    connector_readiness_result = build_connector_readiness({"scope": "validation"})
    command_action_id = ""
    if approval_state_for_command.get("approvals"):
        command_action_id = str(approval_state_for_command["approvals"][0].get("action_id", ""))
        approval_command_result = run_local_approval_command(
            {
                "action_id": command_action_id,
                "decision": "approved",
                "actor": "validation_local_approval_command",
                "note": "validation rehearsal approval",
            }
        )
        live_run_request_after_approve = build_live_run_request({"label": "validation-approved", "action_id": command_action_id})
        live_runner_after_approve_refusal = run_disabled_live_connector_runner({})
        live_runner_after_approve_validated = run_disabled_live_connector_runner(
            {
                "final_approval": True,
                "approval_reference": "validation-final-approval-reference",
            }
        )
        connector_payloads_after_approve = build_connector_payloads({"label": "validation-approved"})
        connector_activation_after_approve = build_connector_activation_checklist({"label": "validation-approved"})
        n8n_dry_import_after_approve = build_n8n_dry_import({"label": "validation-approved"})
        airtable_dry_import_after_approve = build_airtable_dry_import({"label": "validation-approved"})
        notion_dry_import_after_approve = build_notion_dry_import({"label": "validation-approved"})
        reverted_approval_command_result = run_local_approval_command(
            {
                "action_id": command_action_id,
                "decision": "pending_omar_review",
                "actor": "validation_local_approval_command",
                "note": "validation reset to pending after approval rehearsal",
            }
        )
        approval_result = run_approval_state({"action": "sync"})
    google_briefing_action = run_local_action("Prepare today's AIOS daily briefing")
    google_briefing_action_id = google_briefing_action.get("action", {}).get("action_id", "")
    google_briefing_payloads = {}
    google_briefing_activation = {}
    google_briefing_reset = {}
    if google_briefing_action_id:
        run_approval_state({"action": "sync"})
        run_local_approval_command(
            {
                "action_id": google_briefing_action_id,
                "decision": "approved",
                "actor": "validation_google_workspace",
                "note": "validation rehearsal approval for Gmail and Calendar contracts",
            }
        )
        build_live_run_request({"label": "validation-google-briefing-approved", "action_id": google_briefing_action_id})
        run_disabled_live_connector_runner(
            {
                "final_approval": True,
                "approval_reference": "validation-google-workspace-briefing-reference",
            }
        )
        google_briefing_payloads = build_connector_payloads({"label": "validation-google-briefing-approved"})
        google_briefing_activation = build_connector_activation_checklist({"label": "validation-google-briefing-approved"})
        google_workspace_briefing_after_approve = build_google_workspace_dry_import({"label": "validation-google-briefing-approved"})
        google_briefing_reset = run_local_approval_command(
            {
                "action_id": google_briefing_action_id,
                "decision": "pending_omar_review",
                "actor": "validation_google_workspace",
                "note": "validation reset to pending after Google Workspace briefing rehearsal",
            }
        )
    google_content_action = run_local_action("Create a Dubai Hills reel caption and campaign draft")
    google_content_action_id = google_content_action.get("action", {}).get("action_id", "")
    google_content_payloads = {}
    google_content_activation = {}
    google_content_reset = {}
    if google_content_action_id:
        run_approval_state({"action": "sync"})
        run_local_approval_command(
            {
                "action_id": google_content_action_id,
                "decision": "approved",
                "actor": "validation_google_workspace",
                "note": "validation rehearsal approval for Google Drive draft contract",
            }
        )
        build_live_run_request({"label": "validation-google-content-approved", "action_id": google_content_action_id})
        run_disabled_live_connector_runner(
            {
                "final_approval": True,
                "approval_reference": "validation-google-workspace-content-reference",
            }
        )
        google_content_payloads = build_connector_payloads({"label": "validation-google-content-approved"})
        google_content_activation = build_connector_activation_checklist({"label": "validation-google-content-approved"})
        google_workspace_content_after_approve = build_google_workspace_dry_import({"label": "validation-google-content-approved"})
        social_content_after_approve = build_social_content_dry_review({"label": "validation-google-content-approved"})
        google_content_reset = run_local_approval_command(
            {
                "action_id": google_content_action_id,
                "decision": "pending_omar_review",
                "actor": "validation_google_workspace",
                "note": "validation reset to pending after Google Workspace content rehearsal",
            }
        )
    approval_result = run_approval_state({"action": "sync"})
    connector_manifest = build_connector_manifest()
    connector_simulated_dry_run = build_connector_dry_run({"simulate_approved": True})
    connector_dry_run = build_connector_dry_run()
    live_run_request = build_live_run_request({"label": "validation-final-pending"})
    live_connector_runner = run_disabled_live_connector_runner({})
    connector_payloads = build_connector_payloads({"label": "validation-final-pending"})
    connector_activation = build_connector_activation_checklist({"label": "validation-final-pending"})
    n8n_dry_import = build_n8n_dry_import({"label": "validation-final-pending"})
    airtable_dry_import = build_airtable_dry_import({"label": "validation-final-pending"})
    notion_dry_import = build_notion_dry_import({"label": "validation-final-pending"})
    google_workspace_dry_import = build_google_workspace_dry_import({"label": "validation-final-pending"})
    social_content_dry_review = build_social_content_dry_review({"label": "validation-final-pending"})
    connector_readiness_result = build_connector_readiness({"scope": "validation-final-pending"})
    connector_activation_command_result = build_connector_activation_command({"scope": "validation-final-pending"})
    aios_autopilot_result = build_aios_autopilot({"scope": "validation-final-pending"})
    daily_command_session_result = build_daily_command_session({"operator": "Omar", "session_date": "validation"})
    usage_adoption_ledger_result = build_usage_adoption_ledger({"scope": "validation"})
    team_workspace_access_result = build_team_workspace_access({"scope": "validation"})
    client_portal_experience_result = build_client_portal_experience({"scope": "validation"})
    aios_customer_workspace_result = build_aios_customer_workspace({"scope": "validation"})
    business_data_model_result = build_business_data_model({"scope": "validation"})
    business_sync_queue_result = build_business_sync_queue({"scope": "validation"})
    weekly_operating_review_result = build_weekly_operating_review({"scope": "validation"})
    command_center_data = build_command_center_data()
    data_errors = []
    health_keys = {"brain", "router", "crm", "database", "whatsapp", "calendar", "gmail", "drive", "follow_up", "content_factory", "content_factory_runtime", "mobile_command_runtime", "ceo_operating_runtime", "impact_metrics_runtime", "unified_memory_runtime", "aios_brain_runtime", "aios_interaction_architecture_runtime", "connector_readiness_runtime", "connector_activation_command_runtime", "aios_autopilot_runtime", "daily_command_session_runtime", "usage_adoption_ledger_runtime", "team_workspace_access_runtime", "client_portal_experience_runtime", "aios_customer_workspace_runtime", "business_data_model_runtime", "business_sync_queue_runtime", "weekly_operating_review_runtime", "property_intelligence", "operations_assistant", "crm_followup", "knowledge_vault", "website", "mobile_app", "search", "activity_feed", "ask_aios", "daily_briefing", "action_runner", "approval_gate", "approval_command", "connector_manifest", "connector_dry_run", "live_run_request", "live_connector_runner", "connector_payloads", "connector_activation", "n8n_dry_import", "airtable_dry_import", "notion_dry_import", "google_workspace_dry_import", "social_content_dry_review"}
    missing_health = sorted(health_keys - set(command_center_data.get("health", {})))
    if missing_health:
        data_errors.append(f"command center health missing {missing_health}")
    if len(command_center_data.get("search_index", [])) < 40:
        data_errors.append("search index has fewer than 40 records")
    if len(command_center_data.get("workflows", [])) < 10:
        data_errors.append("workflow catalog has fewer than 10 records")
    if len(command_center_data.get("activity", [])) < 4:
        data_errors.append("activity feed has fewer than 4 records")
    if not command_center_data.get("ask_aios", {}).get("answer"):
        data_errors.append("ask_aios last response missing answer")
    if not command_center_data.get("daily_briefing", {}).get("system_health"):
        data_errors.append("daily briefing missing system health")
    if not ask_response.get("matches"):
        data_errors.append("Ask AIOS validation query returned no matches")
    if not action_result.get("passed"):
        data_errors.append("local action runner did not pass")
    action = action_result.get("action", {})
    artifact_path = Path(__file__).resolve().parents[3] / action.get("artifact_path", "")
    if not action.get("artifact_path") or not artifact_path.exists():
        data_errors.append("local action artifact missing")
    if not command_center_data.get("action_queue", {}).get("actions"):
        data_errors.append("action queue missing actions")
    property_intelligence = command_center_data.get("property_intelligence", {})
    if not property_intelligence:
        data_errors.append("property intelligence report missing from command-center data")
    if property_intelligence.get("matched_count", 0) < 2:
        data_errors.append("property intelligence produced fewer than two local matches")
    if len(property_intelligence.get("top_matches", [])) < 3:
        data_errors.append("property intelligence top matches missing")
    if len(property_intelligence.get("comparisons", [])) < 3:
        data_errors.append("property intelligence comparisons missing")
    if "jvc" not in property_intelligence.get("community_context", {}):
        data_errors.append("property intelligence missing JVC community context")
    if not property_intelligence.get("draft_client_message"):
        data_errors.append("property intelligence draft client message missing")
    if property_intelligence.get("workflow_handoff", {}).get("command") != "@recommend":
        data_errors.append("property intelligence workflow handoff mismatch")
    bad_property_side_effects = [
        key for key, value in property_intelligence.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_property_side_effects:
        data_errors.append(f"property intelligence side effects not false: {bad_property_side_effects}")
    operations_assistant = command_center_data.get("operations_assistant", {})
    if not operations_assistant:
        data_errors.append("operations assistant report missing from command-center data")
    expected_operation_cases = {"dld_transfer", "noc", "ejari", "mortgage", "off_plan", "rera", "residency_visa"}
    operation_case_ids = {case.get("case_id") for case in operations_assistant.get("cases", [])}
    missing_operation_cases = sorted(expected_operation_cases - operation_case_ids)
    if operations_assistant.get("case_count", 0) < 7:
        data_errors.append("operations assistant produced fewer than seven operating cases")
    if missing_operation_cases:
        data_errors.append(f"operations assistant missing cases: {missing_operation_cases}")
    fee_calculator = operations_assistant.get("fee_calculator", {})
    if fee_calculator.get("transfer_fee") != 80_000:
        data_errors.append(f"operations assistant DLD transfer fee mismatch: {fee_calculator.get('transfer_fee')}")
    if fee_calculator.get("mortgage_registration") != 4_040:
        data_errors.append(f"operations assistant mortgage registration mismatch: {fee_calculator.get('mortgage_registration')}")
    if fee_calculator.get("total_estimated_cash_to_close", 0) <= 120_000:
        data_errors.append("operations assistant cash-to-close estimate is too low for validation case")
    if len(operations_assistant.get("rera_rent_cap_table", [])) != 5:
        data_errors.append("operations assistant RERA rent cap table missing")
    noc_case = next((case for case in operations_assistant.get("cases", []) if case.get("case_id") == "noc"), {})
    noc_text = " ".join(noc_case.get("required_documents", []) + noc_case.get("checklist", [])).lower()
    if not all(term in noc_text for term in ["title deed", "service charge", "noc"]):
        data_errors.append("operations assistant NOC checklist missing title deed, service charge, or NOC references")
    bad_operations_side_effects = [
        key for key, value in operations_assistant.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_operations_side_effects:
        data_errors.append(f"operations assistant side effects not false: {bad_operations_side_effects}")
    crm_followup = command_center_data.get("crm_followup", {})
    if not crm_followup:
        data_errors.append("CRM follow-up report missing from command-center data")
    if crm_followup.get("lead_count", 0) < 3:
        data_errors.append("CRM follow-up report produced fewer than three leads")
    scored_leads = crm_followup.get("scored_leads", [])
    if not any(lead.get("priority") == "Hot" and lead.get("lead_score", 0) >= 80 for lead in scored_leads):
        data_errors.append("CRM follow-up report did not identify a hot lead")
    if len(crm_followup.get("follow_up_tasks", [])) != crm_followup.get("lead_count"):
        data_errors.append("CRM follow-up task count does not match lead count")
    if len(crm_followup.get("draft_messages", [])) != crm_followup.get("lead_count"):
        data_errors.append("CRM follow-up draft message count does not match lead count")
    unsafe_drafts = [draft.get("lead_id") for draft in crm_followup.get("draft_messages", []) if draft.get("send_enabled") is not False]
    if unsafe_drafts:
        data_errors.append(f"CRM follow-up drafts enabled sending unexpectedly: {unsafe_drafts}")
    if crm_followup.get("dashboard", {}).get("open_tasks", 0) < 3:
        data_errors.append("CRM follow-up dashboard missing open tasks")
    if "Never let a qualified lead go more than 7 days without contact." not in crm_followup.get("dashboard", {}).get("follow_up_quality_rule", ""):
        data_errors.append("CRM follow-up quality rule missing")
    crm_rules = crm_followup.get("crm_rules", {})
    required_crm_fields = {"name", "phone", "email", "source", "budget_or_requirement", "score", "next_action", "next_action_date"}
    missing_crm_fields = sorted(required_crm_fields - set(crm_rules.get("mandatory_crm_fields", [])))
    if missing_crm_fields:
        data_errors.append(f"CRM follow-up mandatory fields missing: {missing_crm_fields}")
    bad_crm_side_effects = [
        key for key, value in crm_followup.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_crm_side_effects:
        data_errors.append(f"CRM follow-up side effects not false: {bad_crm_side_effects}")
    knowledge_vault = command_center_data.get("knowledge_vault", {})
    if not knowledge_vault:
        data_errors.append("Knowledge Vault report missing from command-center data")
    if knowledge_vault.get("asset_count", 0) < 100:
        data_errors.append("Knowledge Vault indexed fewer than 100 assets")
    categories = knowledge_vault.get("categories", {})
    required_knowledge_categories = {"sops", "workflows", "templates", "contracts", "documents", "cases", "playbooks", "regulatory", "market", "company", "branding", "crm", "historical_knowledge"}
    missing_knowledge_categories = sorted(required_knowledge_categories - set(categories))
    if missing_knowledge_categories:
        data_errors.append(f"Knowledge Vault missing categories: {missing_knowledge_categories}")
    coverage = knowledge_vault.get("coverage_summary", {})
    for flag in ["has_sops", "has_workflows", "has_templates", "has_contracts", "has_document_intake", "has_cases"]:
        if coverage.get(flag) is not True:
            data_errors.append(f"Knowledge Vault coverage flag not true: {flag}")
    retrieval_results = knowledge_vault.get("retrieval_results", [])
    if len(retrieval_results) < 5:
        data_errors.append("Knowledge Vault retrieval results missing validation queries")
    empty_retrievals = [row.get("query") for row in retrieval_results if not row.get("matches")]
    if empty_retrievals:
        data_errors.append(f"Knowledge Vault queries returned no matches: {empty_retrievals}")
    route_commands = {route.get("handoff") for route in knowledge_vault.get("retrieval_routes", [])}
    if not {"@noc", "@dld", "@contract", "@client", "@docs"}.issubset(route_commands):
        data_errors.append("Knowledge Vault retrieval handoffs missing required commands")
    document_cases = knowledge_vault.get("document_cases", [])
    if len(document_cases) < 3:
        data_errors.append("Knowledge Vault document cases missing")
    assigned_agents = {case.get("assigned_agent") for case in document_cases}
    if not {"@dld", "@noc"}.issubset(assigned_agents):
        data_errors.append(f"Knowledge Vault document cases missing DLD/NOC assignments: {assigned_agents}")
    bad_knowledge_side_effects = [
        key for key, value in knowledge_vault.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_knowledge_side_effects:
        data_errors.append(f"Knowledge Vault side effects not false: {bad_knowledge_side_effects}")
    content_factory = command_center_data.get("content_factory_report", {})
    if not content_factory:
        data_errors.append("Content Factory report missing from command-center data")
    expected_content_types = {"flyer", "brochure", "presentation", "reel_script", "video_script", "caption", "marketing_campaign"}
    content_types = {item.get("artifact_type") for item in content_factory.get("draft_artifacts", [])}
    missing_content_types = sorted(expected_content_types - content_types)
    if content_factory.get("artifact_count", 0) < 7:
        data_errors.append("Content Factory produced fewer than seven draft artifacts")
    if missing_content_types:
        data_errors.append(f"Content Factory missing draft artifact types: {missing_content_types}")
    if not content_factory.get("campaign_plan", {}).get("draft", {}).get("channels"):
        data_errors.append("Content Factory campaign plan missing channels")
    compliance_checks = content_factory.get("compliance_checks", [])
    if len(compliance_checks) < 5:
        data_errors.append("Content Factory compliance checks missing")
    failed_content_checks = [check.get("check") for check in compliance_checks if check.get("passed") is not True]
    if failed_content_checks:
        data_errors.append(f"Content Factory compliance checks failed: {failed_content_checks}")
    asset_register = content_factory.get("asset_register", {})
    if asset_register.get("property_campaign_assets", 0) < 5:
        data_errors.append("Content Factory property campaign asset register too small")
    if asset_register.get("presentation_assets", 0) < 1:
        data_errors.append("Content Factory presentation asset register missing")
    bad_content_side_effects = [
        key for key, value in content_factory.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_content_side_effects:
        data_errors.append(f"Content Factory side effects not false: {bad_content_side_effects}")
    mobile_command = command_center_data.get("mobile_command_report", {})
    if not mobile_command:
        data_errors.append("Mobile Command report missing from command-center data")
    expected_mobile_capabilities = {"Ask AIOS", "Property Search", "Lead Search", "Tasks", "Calendar", "Gmail", "Documents", "Operations Assistant", "Notifications", "Voice Commands"}
    mobile_capabilities = {item.get("capability") for item in mobile_command.get("capabilities", [])}
    missing_mobile_capabilities = sorted(expected_mobile_capabilities - mobile_capabilities)
    if mobile_command.get("command_count", 0) < 5:
        data_errors.append("Mobile Command runtime produced fewer than five commands")
    if mobile_command.get("voice_command_count", 0) < 2:
        data_errors.append("Mobile Command runtime produced fewer than two voice command contracts")
    if mobile_command.get("notification_count", 0) != mobile_command.get("command_count", 0):
        data_errors.append("Mobile Command notification count does not match command count")
    if missing_mobile_capabilities:
        data_errors.append(f"Mobile Command missing capabilities: {missing_mobile_capabilities}")
    mobile_intents = {action.get("intent") for action in mobile_command.get("actions", [])}
    required_mobile_intents = {"property_search", "lead_follow_up", "operations_assistant", "document_search", "content_factory"}
    missing_mobile_intents = sorted(required_mobile_intents - mobile_intents)
    if missing_mobile_intents:
        data_errors.append(f"Mobile Command missing routed intents: {missing_mobile_intents}")
    panels = mobile_command.get("mobile_panels", {})
    for panel in ["home", "search", "work", "comms", "ops"]:
        if panel not in panels:
            data_errors.append(f"Mobile Command missing panel: {panel}")
    if len(panels.get("home", {}).get("notifications", [])) < 5:
        data_errors.append("Mobile Command home panel missing notifications")
    if not panels.get("work", {}).get("tasks"):
        data_errors.append("Mobile Command work panel missing staged tasks")
    if not panels.get("comms", {}).get("gmail_contracts"):
        data_errors.append("Mobile Command comms panel missing Gmail draft contract")
    if not panels.get("comms", {}).get("document_contracts"):
        data_errors.append("Mobile Command comms panel missing document contracts")
    if len(panels.get("ops", {}).get("voice_commands", [])) < 2:
        data_errors.append("Mobile Command ops panel missing voice commands")
    bad_mobile_contracts = [
        f"{action.get('command_id')}:{contract.get('connector')}"
        for action in mobile_command.get("actions", [])
        for contract in action.get("connector_contracts", [])
        if contract.get("execution_enabled") is not False or contract.get("network_call_enabled") is not False
    ]
    if bad_mobile_contracts:
        data_errors.append(f"Mobile Command connector contracts enabled execution unexpectedly: {bad_mobile_contracts}")
    bad_mobile_voice = [
        action.get("command_id")
        for action in mobile_command.get("actions", [])
        if action.get("voice_command")
        and (
            action["voice_command"].get("audio_recorded") is not False
            or action["voice_command"].get("external_transcription_called") is not False
        )
    ]
    if bad_mobile_voice:
        data_errors.append(f"Mobile Command voice commands enabled recording/transcription unexpectedly: {bad_mobile_voice}")
    bad_mobile_side_effects = [
        key for key, value in mobile_command.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_mobile_side_effects:
        data_errors.append(f"Mobile Command side effects not false: {bad_mobile_side_effects}")
    ceo_operating = command_center_data.get("ceo_operating_report", {})
    if not ceo_operating:
        data_errors.append("CEO Operating report missing from command-center data")
    scorecard = ceo_operating.get("scorecard", {})
    for key in ["brain_health_keys", "search_records", "workflow_records", "pending_approvals", "hot_leads", "open_follow_up_tasks", "mobile_commands", "content_drafts", "operations_cases", "knowledge_assets"]:
        if key not in scorecard:
            data_errors.append(f"CEO Operating scorecard missing {key}")
    if len(ceo_operating.get("priority_stack", [])) < 6:
        data_errors.append("CEO Operating priority stack has fewer than six items")
    priority_domains = {item.get("domain") for item in ceo_operating.get("priority_stack", [])}
    required_priority_domains = {"CRM Follow-Up", "Operations", "Property Intelligence", "Content Factory", "Mobile Command", "Approval Gate"}
    missing_priority_domains = sorted(required_priority_domains - priority_domains)
    if missing_priority_domains:
        data_errors.append(f"CEO Operating priority stack missing domains: {missing_priority_domains}")
    if len(ceo_operating.get("time_blocks", [])) < 4:
        data_errors.append("CEO Operating time blocks missing")
    if len(ceo_operating.get("risk_controls", [])) < 3:
        data_errors.append("CEO Operating risk controls missing")
    risk_names = {risk.get("risk") for risk in ceo_operating.get("risk_controls", [])}
    if not {"approval_queue_bottleneck", "follow_up_quality", "connector_execution"}.issubset(risk_names):
        data_errors.append(f"CEO Operating risk controls missing required risks: {sorted(risk_names)}")
    handoff_commands = {item.get("command") for item in ceo_operating.get("workflow_handoffs", [])}
    if not {"@approve-local", "@crm-followup", "@property-intel", "@operations", "@content-factory", "@mobile-command"}.issubset(handoff_commands):
        data_errors.append("CEO Operating handoff commands missing")
    bad_ceo_side_effects = [
        key for key, value in ceo_operating.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_ceo_side_effects:
        data_errors.append(f"CEO Operating side effects not false: {bad_ceo_side_effects}")
    impact_metrics = command_center_data.get("impact_metrics_report", {})
    if not impact_metrics:
        data_errors.append("Impact Metrics report missing from command-center data")
    time_savings = impact_metrics.get("time_savings", [])
    if len(time_savings) < 7:
        data_errors.append("Impact Metrics time-savings areas missing")
    quality_metrics = impact_metrics.get("quality_metrics", {})
    if quality_metrics.get("estimated_weekly_hours_saved", 0) < 8:
        data_errors.append("Impact Metrics estimated weekly hours saved below target threshold")
    if quality_metrics.get("manual_work_reduction_units", 0) < 50:
        data_errors.append("Impact Metrics manual work reduction units below validation threshold")
    for key in ["response_quality_signals", "follow_up_quality_signals", "content_quality_signals", "platform_adoption_signals"]:
        if key not in quality_metrics:
            data_errors.append(f"Impact Metrics missing quality metric group: {key}")
    success_goals = {item.get("goal"): item.get("status") for item in impact_metrics.get("success_metric_status", [])}
    required_success_goals = {"save_significant_time_every_week", "reduce_manual_work", "improve_response_quality", "improve_follow_up_quality", "become_primary_operating_platform", "keep_approval_safety"}
    missing_success_goals = sorted(required_success_goals - set(success_goals))
    if missing_success_goals:
        data_errors.append(f"Impact Metrics missing success goals: {missing_success_goals}")
    if success_goals.get("keep_approval_safety") != "controlled":
        data_errors.append("Impact Metrics approval safety status is not controlled")
    if quality_metrics.get("follow_up_quality_signals", {}).get("draft_messages", 0) < 3:
        data_errors.append("Impact Metrics follow-up quality missing draft message evidence")
    if quality_metrics.get("platform_adoption_signals", {}).get("ceo_operating_priorities", 0) < 6:
        data_errors.append("Impact Metrics platform adoption missing CEO operating priority evidence")
    bad_impact_side_effects = [
        key for key, value in impact_metrics.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_impact_side_effects:
        data_errors.append(f"Impact Metrics side effects not false: {bad_impact_side_effects}")
    unified_memory = command_center_data.get("unified_memory_report", {})
    if not unified_memory:
        data_errors.append("Unified Memory report missing from command-center data")
    if unified_memory.get("memory_packet_count", 0) < 7:
        data_errors.append("Unified Memory produced fewer than seven context packets")
    required_memory_types = {"executive", "crm", "property", "operations", "content", "knowledge", "conversation"}
    memory_types = set(unified_memory.get("memory_types", []))
    missing_memory_types = sorted(required_memory_types - memory_types)
    if missing_memory_types:
        data_errors.append(f"Unified Memory missing memory types: {missing_memory_types}")
    packet_ids = {packet.get("packet_id") for packet in unified_memory.get("context_packets", [])}
    required_packets = {"MEM-EXEC-OMAR", "MEM-CRM-HOT-LEADS", "MEM-PROPERTY-RECOMMENDATION", "MEM-OPERATIONS-COMPLIANCE", "MEM-CONTENT-CAMPAIGN", "MEM-KNOWLEDGE-VAULT", "MEM-WHATSAPP-CONTEXT"}
    missing_packets = sorted(required_packets - packet_ids)
    if missing_packets:
        data_errors.append(f"Unified Memory missing packets: {missing_packets}")
    writeback_enabled = [packet.get("packet_id") for packet in unified_memory.get("context_packets", []) if packet.get("writeback_enabled") is not False]
    if writeback_enabled:
        data_errors.append(f"Unified Memory writeback enabled unexpectedly: {writeback_enabled}")
    retrieval_commands = {route.get("command") for route in unified_memory.get("retrieval_map", [])}
    if not {"@ceo", "@impact", "@crm-followup", "@property-intel", "@operations", "@content-factory", "@knowledge-vault", "@whatsapp"}.issubset(retrieval_commands):
        data_errors.append("Unified Memory retrieval map missing required commands")
    conversation_state = unified_memory.get("conversation_state", {})
    if conversation_state.get("read_only") is not True:
        data_errors.append("Unified Memory conversation state is not marked read-only")
    if conversation_state.get("db_exists") is not True:
        data_errors.append("Unified Memory conversation state database missing")
    if conversation_state.get("message_count", 0) < 1:
        data_errors.append("Unified Memory conversation state has no messages")
    bad_unified_memory_side_effects = [
        key for key, value in unified_memory.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_unified_memory_side_effects:
        data_errors.append(f"Unified Memory side effects not false: {bad_unified_memory_side_effects}")
    aios_brain = command_center_data.get("aios_brain_report", {})
    if not aios_brain:
        data_errors.append("AIOS Brain report missing from command-center data")
    if aios_brain.get("query_count", 0) < 6:
        data_errors.append("AIOS Brain produced fewer than six answer packets")
    required_brain_capabilities = {"ceo_operating", "property_intelligence", "operations", "crm_followup", "content_factory", "conversation_memory"}
    brain_capabilities = set(aios_brain.get("capabilities_covered", []))
    missing_brain_capabilities = sorted(required_brain_capabilities - brain_capabilities)
    if missing_brain_capabilities:
        data_errors.append(f"AIOS Brain missing capabilities: {missing_brain_capabilities}")
    if aios_brain.get("memory_packets_available", 0) < 7:
        data_errors.append("AIOS Brain did not load unified memory packets")
    unsafe_brain_packets = [
        packet.get("query")
        for packet in aios_brain.get("answer_packets", [])
        if packet.get("execution_enabled") is not False or not packet.get("evidence") or not packet.get("safety_gate")
    ]
    if unsafe_brain_packets:
        data_errors.append(f"AIOS Brain packets missing safety/evidence or enabled execution: {unsafe_brain_packets}")
    memoryless_brain_packets = [
        packet.get("query")
        for packet in aios_brain.get("answer_packets", [])
        if not packet.get("matched_memory_packets")
    ]
    if memoryless_brain_packets:
        data_errors.append(f"AIOS Brain packets missing memory grounding: {memoryless_brain_packets}")
    bad_aios_brain_side_effects = [
        key for key, value in aios_brain.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_aios_brain_side_effects:
        data_errors.append(f"AIOS Brain side effects not false: {bad_aios_brain_side_effects}")
    aios_interaction_architecture = command_center_data.get("aios_interaction_architecture", {})
    if not aios_interaction_architecture:
        data_errors.append("AIOS Interaction Architecture report missing from command-center data")
    if aios_interaction_architecture.get("summary", {}).get("pipeline_step_count") != 10:
        data_errors.append("AIOS Interaction Architecture does not contain the full 10-step pipeline")
    required_channels = {"whatsapp", "website", "mobile_app", "future_instagram", "future_email", "future_voice"}
    interaction_channels = set(aios_interaction_architecture.get("channels", []))
    missing_interaction_channels = sorted(required_channels - interaction_channels)
    if missing_interaction_channels:
        data_errors.append(f"AIOS Interaction Architecture missing channels: {missing_interaction_channels}")
    policy = aios_interaction_architecture.get("permission_policy", {})
    never_disclose = set(policy.get("never_disclose", []))
    if not {"owner_phone_numbers", "passport_details", "internal_crm_notes", "internal_commissions"}.issubset(never_disclose):
        data_errors.append("AIOS Interaction Architecture restricted disclosure policy incomplete")
    permission_runtime = aios_interaction_architecture.get("permission_runtime", {})
    if permission_runtime.get("source_of_truth") != "backend":
        data_errors.append("AIOS permission runtime is not backend-owned")
    if permission_runtime.get("no_browser_only_rules") is not True:
        data_errors.append("AIOS permission runtime allows browser-only rules")
    if permission_runtime.get("no_channel_specific_exceptions") is not True:
        data_errors.append("AIOS permission runtime allows channel-specific exceptions")
    runtime_channels = set(permission_runtime.get("channels", []))
    missing_runtime_channels = sorted(required_channels - runtime_channels)
    if missing_runtime_channels:
        data_errors.append(f"AIOS permission runtime missing channels: {missing_runtime_channels}")
    runtime_rules = permission_runtime.get("rules", [])
    if not runtime_rules or not all(rule.get("data_type") and rule.get("rule") and rule.get("terms") for rule in runtime_rules):
        data_errors.append("AIOS permission runtime rules are incomplete")
    permission_consistency = aios_interaction_architecture.get("permission_runtime_consistency", {})
    if permission_consistency.get("same_result_everywhere") is not True:
        data_errors.append("AIOS permission runtime does not produce the same restricted result everywhere")
    consistency_channels = set(permission_consistency.get("channels", []))
    missing_consistency_channels = sorted(required_channels - consistency_channels)
    if missing_consistency_channels:
        data_errors.append(f"AIOS permission consistency check missing channels: {missing_consistency_channels}")
    api_decision_signature = {
        json.dumps(
            {
                "blocked": item.get("blocked"),
                "hits": item.get("hits"),
                "rules": item.get("rules"),
                "reason": item.get("reason"),
                "allowed_alternatives": item.get("allowed_alternatives"),
                "safety_gate": item.get("safety_gate"),
                "eye_state": item.get("eye_state"),
                "source_runtime": item.get("source_runtime"),
            },
            sort_keys=True,
        )
        for item in permission_api_decisions
    }
    if len(api_decision_signature) != 1:
        data_errors.append("AIOS live permission API does not produce the same result everywhere")
    unsafe_api_decisions = [
        item.get("channel")
        for item in permission_api_decisions
        if item.get("blocked") is not True
        or item.get("source_runtime") != "backend"
        or item.get("audit_logged") is not True
        or item.get("eye_state") != "restricted"
    ]
    if unsafe_api_decisions:
        data_errors.append(f"AIOS live permission API failed restricted/audit contract: {unsafe_api_decisions}")
    if not PERMISSION_AUDIT_LOG_PATH.exists():
        data_errors.append("AIOS permission audit log was not created")
    interactions = aios_interaction_architecture.get("sample_interactions", [])
    if len(interactions) < 5:
        data_errors.append("AIOS Interaction Architecture produced fewer than five sample interactions")
    if not any(item.get("permission", {}).get("restricted_hits") for item in interactions):
        data_errors.append("AIOS Interaction Architecture did not block any restricted-information request")
    if not any(item.get("omar_personality", {}).get("goal") == "sounds_like_omar_not_chatgpt" for item in interactions):
        data_errors.append("AIOS Interaction Architecture missing Omar personality goal")
    interaction_eye_states = set(aios_interaction_architecture.get("summary", {}).get("eye_states_observed", []))
    if not {"alert", "searching", "thinking"}.issubset(interaction_eye_states):
        data_errors.append(f"AIOS Interaction Architecture missing Eye state coverage: {sorted(interaction_eye_states)}")
    unsafe_interaction_replies = [
        item.get("received_text")
        for item in interactions
        if item.get("response_generation", {}).get("reply_enabled") is not False
        or item.get("memory_update", {}).get("write_enabled") is not False
    ]
    if unsafe_interaction_replies:
        data_errors.append(f"AIOS Interaction Architecture enabled reply or memory writes unexpectedly: {unsafe_interaction_replies}")
    bad_interaction_side_effects = [
        key for key, value in aios_interaction_architecture.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_interaction_side_effects:
        data_errors.append(f"AIOS Interaction Architecture side effects not false: {bad_interaction_side_effects}")
    connector_readiness = command_center_data.get("connector_readiness_report", {})
    if not connector_readiness:
        data_errors.append("Connector Readiness report missing from command-center data")
    connectors = connector_readiness.get("connectors", [])
    connector_names = {item.get("connector") for item in connectors}
    required_connectors = {"n8n", "airtable", "gmail", "google_calendar", "google_drive", "notion", "whatsapp", "instagram", "future_channels"}
    missing_connectors = sorted(required_connectors - connector_names)
    if missing_connectors:
        data_errors.append(f"Connector Readiness missing connectors: {missing_connectors}")
    readiness_summary = connector_readiness.get("summary", {})
    if readiness_summary.get("connector_count", 0) < len(required_connectors):
        data_errors.append("Connector Readiness connector count too low")
    if readiness_summary.get("local_ready_count", 0) < 5:
        data_errors.append("Connector Readiness local-ready count too low")
    if readiness_summary.get("activation_allowed_count", 0) != 0:
        data_errors.append("Connector Readiness allowed activation unexpectedly")
    if readiness_summary.get("all_execution_disabled") is not True:
        data_errors.append("Connector Readiness execution is not fully disabled")
    if readiness_summary.get("all_credentials_excluded") is not True:
        data_errors.append("Connector Readiness credentials are not fully excluded")
    unsafe_connectors = [
        item.get("connector")
        for item in connectors
        if item.get("execution_enabled") is not False
        or item.get("network_call_enabled") is not False
        or item.get("credentials_included") is not False
        or item.get("activation_allowed") is not False
    ]
    if unsafe_connectors:
        data_errors.append(f"Connector Readiness unsafe connector flags: {unsafe_connectors}")
    bad_readiness_side_effects = [
        key for key, value in connector_readiness.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_readiness_side_effects:
        data_errors.append(f"Connector Readiness side effects not false: {bad_readiness_side_effects}")
    connector_activation_command = command_center_data.get("connector_activation_command_plan", {})
    if not connector_activation_command:
        data_errors.append("Connector Activation Command plan missing from command-center data")
    activation_steps = connector_activation_command.get("activation_steps", [])
    activation_step_names = {item.get("connector") for item in activation_steps}
    missing_activation_steps = sorted(required_connectors - activation_step_names)
    if missing_activation_steps:
        data_errors.append(f"Connector Activation Command missing connectors: {missing_activation_steps}")
    activation_command_summary = connector_activation_command.get("summary", {})
    if activation_command_summary.get("connector_count", 0) < len(required_connectors):
        data_errors.append("Connector Activation Command connector count too low")
    if activation_command_summary.get("ready_for_user_login_count", 0) < 5:
        data_errors.append("Connector Activation Command ready-for-login count too low")
    if activation_command_summary.get("activation_allowed_count", 0) != 0:
        data_errors.append("Connector Activation Command allowed activation unexpectedly")
    if activation_command_summary.get("oauth_started_count", 0) != 0:
        data_errors.append("Connector Activation Command started OAuth unexpectedly")
    if activation_command_summary.get("all_network_calls_disabled") is not True:
        data_errors.append("Connector Activation Command network calls not fully disabled")
    if activation_command_summary.get("all_credentials_excluded") is not True:
        data_errors.append("Connector Activation Command credentials are not fully excluded")
    unsafe_activation_steps = [
        item.get("connector")
        for item in activation_steps
        if item.get("network_call_enabled") is not False
        or item.get("credential_value_included") is not False
        or item.get("oauth_started") is not False
        or item.get("activation_allowed") is not False
    ]
    if unsafe_activation_steps:
        data_errors.append(f"Connector Activation Command unsafe step flags: {unsafe_activation_steps}")
    missing_activation_commands = [
        item.get("connector")
        for item in activation_steps
        if not item.get("setup_command") or not item.get("validation_command") or not item.get("risk_gate")
    ]
    if missing_activation_commands:
        data_errors.append(f"Connector Activation Command missing command contracts: {missing_activation_commands}")
    bad_activation_command_side_effects = [
        key for key, value in connector_activation_command.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_activation_command_side_effects:
        data_errors.append(f"Connector Activation Command side effects not false: {bad_activation_command_side_effects}")
    aios_autopilot = command_center_data.get("aios_autopilot_report", {})
    if not aios_autopilot:
        data_errors.append("AIOS Autopilot report missing from command-center data")
    autopilot_summary = aios_autopilot.get("summary", {})
    autopilot_actions = aios_autopilot.get("autopilot_actions", [])
    if autopilot_summary.get("action_count", 0) < 20:
        data_errors.append("AIOS Autopilot action count too low")
    if autopilot_summary.get("auto_local_count", 0) < 10:
        data_errors.append("AIOS Autopilot auto-local count too low")
    if autopilot_summary.get("stopped_for_human_count", 0) < 5:
        data_errors.append("AIOS Autopilot human-stop count too low")
    if autopilot_summary.get("high_risk_hold_count", 0) < 3:
        data_errors.append("AIOS Autopilot high-risk hold count too low")
    if autopilot_summary.get("login_or_oauth_hold_count", 0) < 3:
        data_errors.append("AIOS Autopilot login/OAuth hold count too low")
    if autopilot_summary.get("estimated_minutes_saved", 0) < 180:
        data_errors.append("AIOS Autopilot estimated minutes saved too low")
    if autopilot_summary.get("all_execution_disabled") is not True:
        data_errors.append("AIOS Autopilot execution not fully disabled")
    required_autopilot_domains = {"ceo_operating", "crm_followup", "operations", "content_factory", "one_brain", "mobile_command", "connector_activation"}
    autopilot_domains = set(aios_autopilot.get("domains_covered", []))
    missing_autopilot_domains = sorted(required_autopilot_domains - autopilot_domains)
    if missing_autopilot_domains:
        data_errors.append(f"AIOS Autopilot missing domains: {missing_autopilot_domains}")
    unsafe_autopilot_actions = [
        item.get("action_id")
        for item in autopilot_actions
        if item.get("execution_enabled") is not False or item.get("external_write_enabled") is not False
    ]
    if unsafe_autopilot_actions:
        data_errors.append(f"AIOS Autopilot unsafe action flags: {unsafe_autopilot_actions}")
    missing_autopilot_contracts = [
        item.get("action_id")
        for item in autopilot_actions
        if not item.get("command") or not item.get("human_intervention_gate") or not item.get("next_step")
    ]
    if missing_autopilot_contracts:
        data_errors.append(f"AIOS Autopilot missing command/gate contracts: {missing_autopilot_contracts}")
    bad_autopilot_side_effects = [
        key for key, value in aios_autopilot.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_autopilot_side_effects:
        data_errors.append(f"AIOS Autopilot side effects not false: {bad_autopilot_side_effects}")
    daily_session = command_center_data.get("daily_command_session", {})
    if not daily_session:
        data_errors.append("Daily Command Session report missing from command-center data")
    daily_session_summary = daily_session.get("summary", {})
    session_blocks = daily_session.get("session_blocks", [])
    block_names = {block.get("block") for block in session_blocks}
    required_blocks = {"Morning Command", "Midday Execution", "End-of-Day Closeout"}
    missing_blocks = sorted(required_blocks - block_names)
    if missing_blocks:
        data_errors.append(f"Daily Command Session missing blocks: {missing_blocks}")
    if daily_session_summary.get("session_block_count", 0) < 3:
        data_errors.append("Daily Command Session block count too low")
    if daily_session_summary.get("session_item_count", 0) < 15:
        data_errors.append("Daily Command Session item count too low")
    if daily_session_summary.get("auto_local_count", 0) < 8:
        data_errors.append("Daily Command Session auto-local count too low")
    if daily_session_summary.get("stopped_for_human_count", 0) < 5:
        data_errors.append("Daily Command Session human-stop count too low")
    if daily_session_summary.get("estimated_minutes_in_session", 0) < 200:
        data_errors.append("Daily Command Session estimated minutes too low")
    if daily_session_summary.get("weekly_hours_saved_projection", 0) < 5:
        data_errors.append("Daily Command Session weekly hours projection too low")
    if daily_session_summary.get("all_execution_disabled") is not True:
        data_errors.append("Daily Command Session execution not fully disabled")
    session_items = [item for block in session_blocks for item in block.get("items", [])]
    unsafe_session_items = [
        item.get("title")
        for item in session_items
        if item.get("execution_enabled") is not False or item.get("external_write_enabled") is not False
    ]
    if unsafe_session_items:
        data_errors.append(f"Daily Command Session unsafe item flags: {unsafe_session_items}")
    missing_session_contracts = [
        item.get("title")
        for item in session_items
        if not item.get("command") or not item.get("gate") or not item.get("detail")
    ]
    if missing_session_contracts:
        data_errors.append(f"Daily Command Session missing command/gate contracts: {missing_session_contracts}")
    bad_daily_session_side_effects = [
        key for key, value in daily_session.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_daily_session_side_effects:
        data_errors.append(f"Daily Command Session side effects not false: {bad_daily_session_side_effects}")
    usage_ledger = command_center_data.get("usage_adoption_ledger", {})
    if not usage_ledger:
        data_errors.append("Usage Adoption Ledger missing from command-center data")
    usage_summary = usage_ledger.get("summary", {})
    if usage_summary.get("session_count", 0) < 1:
        data_errors.append("Usage Adoption Ledger session count too low")
    if usage_summary.get("session_entry_count", 0) < 15:
        data_errors.append("Usage Adoption Ledger entry count too low")
    if usage_summary.get("commands_used_count", 0) < 5:
        data_errors.append("Usage Adoption Ledger command count too low")
    if usage_summary.get("modules_touched_count", 0) < 5:
        data_errors.append("Usage Adoption Ledger module coverage too low")
    if usage_summary.get("estimated_minutes_logged", 0) < 200:
        data_errors.append("Usage Adoption Ledger minutes logged too low")
    if usage_summary.get("weekly_hours_saved_projection", 0) < 5:
        data_errors.append("Usage Adoption Ledger weekly hours projection too low")
    if usage_summary.get("adoption_score", 0) < 70:
        data_errors.append("Usage Adoption Ledger adoption score too low")
    if usage_summary.get("validation_passed") is not True:
        data_errors.append("Usage Adoption Ledger missing validation-passed evidence")
    if usage_summary.get("all_execution_disabled") is not True:
        data_errors.append("Usage Adoption Ledger execution not fully disabled")
    required_usage_modules = {"ceo_operating", "crm_followup", "operations", "content_factory", "connector_activation"}
    usage_modules = set(usage_ledger.get("modules_touched", []))
    missing_usage_modules = sorted(required_usage_modules - usage_modules)
    if missing_usage_modules:
        data_errors.append(f"Usage Adoption Ledger missing modules: {missing_usage_modules}")
    unsafe_usage_entries = [
        item.get("title")
        for item in usage_ledger.get("ledger_entries", [])
        if item.get("execution_enabled") is not False or item.get("external_write_enabled") is not False
    ]
    if unsafe_usage_entries:
        data_errors.append(f"Usage Adoption Ledger unsafe entries: {unsafe_usage_entries}")
    bad_usage_side_effects = [
        key for key, value in usage_ledger.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_usage_side_effects:
        data_errors.append(f"Usage Adoption Ledger side effects not false: {bad_usage_side_effects}")
    team_workspace = command_center_data.get("team_workspace_access", {})
    if not team_workspace:
        data_errors.append("Team Workspace Access report missing from command-center data")
    team_summary = team_workspace.get("summary", {})
    if team_summary.get("role_count", 0) < 4:
        data_errors.append("Team Workspace role count too low")
    if team_summary.get("unique_module_count", 0) < 10:
        data_errors.append("Team Workspace module coverage too low")
    if team_summary.get("blocked_action_count", 0) < 8:
        data_errors.append("Team Workspace blocked-action count too low")
    if team_summary.get("published_workspace_count", 0) != 0:
        data_errors.append("Team Workspace published unexpectedly")
    if team_summary.get("live_access_enabled_count", 0) != 0:
        data_errors.append("Team Workspace live access enabled unexpectedly")
    if team_summary.get("external_invites_sent_count", 0) != 0:
        data_errors.append("Team Workspace external invites sent unexpectedly")
    if team_summary.get("all_live_access_disabled") is not True:
        data_errors.append("Team Workspace live access not fully disabled")
    if team_summary.get("all_invites_disabled") is not True:
        data_errors.append("Team Workspace invites not fully disabled")
    role_names = {role.get("role") for role in team_workspace.get("role_views", [])}
    required_roles = {"omar_owner", "hsh_team_operator", "future_client", "future_aios_customer"}
    missing_roles = sorted(required_roles - role_names)
    if missing_roles:
        data_errors.append(f"Team Workspace missing roles: {missing_roles}")
    unsafe_team_views = [
        role.get("role")
        for role in team_workspace.get("role_views", [])
        if role.get("live_access_enabled") is not False or role.get("external_invite_enabled") is not False
    ]
    if unsafe_team_views:
        data_errors.append(f"Team Workspace unsafe view flags: {unsafe_team_views}")
    missing_team_contracts = [
        role.get("role")
        for role in team_workspace.get("role_views", [])
        if not role.get("modules") or not role.get("allowed_commands") or not role.get("blocked_actions")
    ]
    if missing_team_contracts:
        data_errors.append(f"Team Workspace missing access contracts: {missing_team_contracts}")
    bad_team_side_effects = [
        key for key, value in team_workspace.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_team_side_effects:
        data_errors.append(f"Team Workspace side effects not false: {bad_team_side_effects}")
    client_portal = command_center_data.get("client_portal_experience", {})
    if not client_portal:
        data_errors.append("Client Portal Experience report missing from command-center data")
    portal_summary = client_portal.get("summary", {})
    if portal_summary.get("portal_section_count", 0) < 6:
        data_errors.append("Client Portal section count too low")
    if portal_summary.get("request_route_count", 0) < 5:
        data_errors.append("Client Portal request route count too low")
    if portal_summary.get("hidden_data_rule_count", 0) < 7:
        data_errors.append("Client Portal hidden data rule count too low")
    if portal_summary.get("published_portal_count", 0) != 0:
        data_errors.append("Client Portal published unexpectedly")
    if portal_summary.get("external_share_enabled_count", 0) != 0:
        data_errors.append("Client Portal external sharing enabled unexpectedly")
    if portal_summary.get("all_external_actions_disabled") is not True:
        data_errors.append("Client Portal external actions not fully disabled")
    if portal_summary.get("all_sensitive_data_hidden") is not True:
        data_errors.append("Client Portal sensitive data not fully hidden")
    portal_sections = client_portal.get("portal_sections", [])
    portal_section_names = {section.get("section") for section in portal_sections}
    required_portal_sections = {
        "property_recommendations",
        "document_status",
        "appointment_request",
        "operations_status",
        "approved_content_preview",
        "client_request_intake",
    }
    missing_portal_sections = sorted(required_portal_sections - portal_section_names)
    if missing_portal_sections:
        data_errors.append(f"Client Portal missing sections: {missing_portal_sections}")
    request_routes = client_portal.get("request_routes", [])
    route_names = {route.get("request") for route in request_routes}
    required_route_names = {
        "request_viewing",
        "request_documents",
        "ask_property_question",
        "request_offer_support",
        "request_marketing_preview",
    }
    missing_route_names = sorted(required_route_names - route_names)
    if missing_route_names:
        data_errors.append(f"Client Portal missing request routes: {missing_route_names}")
    required_route_commands = {"@property-intel", "@calendar-handoff", "@knowledge-vault", "@operations", "@brain", "@crm-followup", "@content-factory"}
    route_commands = {command for route in request_routes for command in route.get("route_to", [])}
    missing_route_commands = sorted(required_route_commands - route_commands)
    if missing_route_commands:
        data_errors.append(f"Client Portal missing route commands: {missing_route_commands}")
    required_route_gates = {"OMAR_APPROVAL_REQUIRED", "INTERNAL_REVIEW_REQUIRED", "DRAFT_ONLY", "HIGH_RISK_DECISION", "APPROVED_CONTENT_ONLY"}
    route_gates = {route.get("gate") for route in request_routes}
    missing_route_gates = sorted(required_route_gates - route_gates)
    if missing_route_gates:
        data_errors.append(f"Client Portal missing gates: {missing_route_gates}")
    unsafe_portal_routes = [
        route.get("request")
        for route in request_routes
        if route.get("execution_enabled") is not False or route.get("external_write_enabled") is not False
    ]
    if unsafe_portal_routes:
        data_errors.append(f"Client Portal unsafe route flags: {unsafe_portal_routes}")
    hidden_data_classes = {rule.get("data_class") for rule in client_portal.get("hidden_data_rules", [])}
    required_hidden_data = {"internal_crm_notes", "whatsapp_history", "other_clients", "owner_finance", "legal_payment_context", "connector_credentials", "team_tasks"}
    missing_hidden_data = sorted(required_hidden_data - hidden_data_classes)
    if missing_hidden_data:
        data_errors.append(f"Client Portal missing hidden data rules: {missing_hidden_data}")
    bad_portal_side_effects = [
        key for key, value in client_portal.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_portal_side_effects:
        data_errors.append(f"Client Portal side effects not false: {bad_portal_side_effects}")
    customer_workspace = command_center_data.get("aios_customer_workspace", {})
    if not customer_workspace:
        data_errors.append("AIOS Customer Workspace report missing from command-center data")
    customer_summary = customer_workspace.get("summary", {})
    if customer_summary.get("demo_module_count", 0) < 8:
        data_errors.append("AIOS Customer Workspace demo module count too low")
    if customer_summary.get("onboarding_route_count", 0) < 5:
        data_errors.append("AIOS Customer Workspace onboarding route count too low")
    if customer_summary.get("data_isolation_rule_count", 0) < 7:
        data_errors.append("AIOS Customer Workspace data isolation rule count too low")
    if customer_summary.get("published_customer_workspace_count", 0) != 0:
        data_errors.append("AIOS Customer Workspace published unexpectedly")
    if customer_summary.get("customer_account_count", 0) != 0:
        data_errors.append("AIOS Customer Workspace customer accounts created unexpectedly")
    if customer_summary.get("demo_invite_count", 0) != 0:
        data_errors.append("AIOS Customer Workspace demo invites sent unexpectedly")
    if customer_summary.get("trial_started_count", 0) != 0:
        data_errors.append("AIOS Customer Workspace trial started unexpectedly")
    if customer_summary.get("checkout_started_count", 0) != 0:
        data_errors.append("AIOS Customer Workspace checkout started unexpectedly")
    if customer_summary.get("all_external_actions_disabled") is not True:
        data_errors.append("AIOS Customer Workspace external actions not fully disabled")
    if customer_summary.get("all_hsh_private_data_isolated") is not True:
        data_errors.append("AIOS Customer Workspace HSH private data isolation not confirmed")
    demo_modules = customer_workspace.get("demo_modules", [])
    demo_module_names = {module.get("module") for module in demo_modules}
    required_demo_modules = {
        "command_center_demo",
        "one_brain_demo",
        "crm_followup_demo",
        "operations_brain_demo",
        "content_factory_demo",
        "connector_readiness_demo",
        "mobile_command_demo",
        "impact_metrics_demo",
    }
    missing_demo_modules = sorted(required_demo_modules - demo_module_names)
    if missing_demo_modules:
        data_errors.append(f"AIOS Customer Workspace missing demo modules: {missing_demo_modules}")
    onboarding_routes = customer_workspace.get("onboarding_routes", [])
    onboarding_route_names = {route.get("request") for route in onboarding_routes}
    required_onboarding_routes = {
        "request_aios_demo",
        "request_private_beta",
        "request_connector_assessment",
        "request_custom_workspace",
        "request_purchase_or_subscription",
    }
    missing_onboarding_routes = sorted(required_onboarding_routes - onboarding_route_names)
    if missing_onboarding_routes:
        data_errors.append(f"AIOS Customer Workspace missing onboarding routes: {missing_onboarding_routes}")
    required_customer_route_commands = {"@website", "@customer-workspace", "@calendar-handoff", "@readiness", "@activation-command", "@connector-manifest", "@brain", "@mobile", "@legal", "@finance"}
    customer_route_commands = {command for route in onboarding_routes for command in route.get("route_to", [])}
    missing_customer_route_commands = sorted(required_customer_route_commands - customer_route_commands)
    if missing_customer_route_commands:
        data_errors.append(f"AIOS Customer Workspace missing route commands: {missing_customer_route_commands}")
    required_customer_gates = {
        "OMAR_APPROVAL_REQUIRED",
        "SALES_QUALIFICATION_REQUIRED",
        "CONNECTOR_SCOPE_REVIEW",
        "DATA_ISOLATION_REVIEW",
        "PAYMENT_AND_LEGAL_APPROVAL_REQUIRED",
    }
    customer_route_gates = {route.get("gate") for route in onboarding_routes}
    missing_customer_gates = sorted(required_customer_gates - customer_route_gates)
    if missing_customer_gates:
        data_errors.append(f"AIOS Customer Workspace missing gates: {missing_customer_gates}")
    unsafe_customer_routes = [
        route.get("request")
        for route in onboarding_routes
        if route.get("execution_enabled") is not False or route.get("external_write_enabled") is not False
    ]
    if unsafe_customer_routes:
        data_errors.append(f"AIOS Customer Workspace unsafe route flags: {unsafe_customer_routes}")
    isolation_classes = {rule.get("data_class") for rule in customer_workspace.get("data_isolation_rules", [])}
    required_isolation_classes = {
        "hsh_private_operating_data",
        "client_records",
        "whatsapp_conversations",
        "connector_credentials",
        "financial_and_payment_data",
        "legal_and_authority_context",
        "brand_and_internal_strategy",
    }
    missing_isolation_classes = sorted(required_isolation_classes - isolation_classes)
    if missing_isolation_classes:
        data_errors.append(f"AIOS Customer Workspace missing data isolation rules: {missing_isolation_classes}")
    bad_customer_side_effects = [
        key for key, value in customer_workspace.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_customer_side_effects:
        data_errors.append(f"AIOS Customer Workspace side effects not false: {bad_customer_side_effects}")
    business_data_model = command_center_data.get("business_data_model", {})
    if not business_data_model:
        data_errors.append("Business Data Model report missing from command-center data")
    data_model_summary = business_data_model.get("summary", {})
    if data_model_summary.get("entity_count", 0) < 12:
        data_errors.append("Business Data Model entity count too low")
    if data_model_summary.get("relationship_count", 0) < 10:
        data_errors.append("Business Data Model relationship count too low")
    if data_model_summary.get("connector_mapping_count", 0) < 9:
        data_errors.append("Business Data Model connector mapping count too low")
    if data_model_summary.get("migration_gate_count", 0) < 8:
        data_errors.append("Business Data Model migration gate count too low")
    if data_model_summary.get("required_field_contracts_complete") is not True:
        data_errors.append("Business Data Model required field contracts incomplete")
    if data_model_summary.get("all_connector_writes_disabled") is not True:
        data_errors.append("Business Data Model connector writes not fully disabled")
    if data_model_summary.get("all_external_actions_disabled") is not True:
        data_errors.append("Business Data Model external actions not fully disabled")
    if data_model_summary.get("canonical_entities_ready") is not True:
        data_errors.append("Business Data Model canonical entities not ready")
    canonical_entities = business_data_model.get("canonical_entities", [])
    canonical_entity_names = {entity.get("entity") for entity in canonical_entities}
    required_entities = {
        "lead",
        "contact",
        "property",
        "deal",
        "task",
        "communication",
        "document",
        "content_asset",
        "approval",
        "workflow",
        "calendar_event",
        "knowledge_asset",
    }
    missing_entities = sorted(required_entities - canonical_entity_names)
    if missing_entities:
        data_errors.append(f"Business Data Model missing entities: {missing_entities}")
    entities_missing_required_fields = [
        entity.get("entity")
        for entity in canonical_entities
        if len(entity.get("required_fields", [])) < 5 or not entity.get("owner_module") or not entity.get("privacy_class")
    ]
    if entities_missing_required_fields:
        data_errors.append(f"Business Data Model entities missing required contracts: {entities_missing_required_fields}")
    connector_mappings = business_data_model.get("connector_mappings", [])
    data_model_connectors = {mapping.get("connector") for mapping in connector_mappings}
    required_data_model_connectors = {"airtable", "google_drive", "gmail", "google_calendar", "notion", "whatsapp", "instagram", "n8n", "future_channels"}
    missing_data_model_connectors = sorted(required_data_model_connectors - data_model_connectors)
    if missing_data_model_connectors:
        data_errors.append(f"Business Data Model missing connector mappings: {missing_data_model_connectors}")
    unsafe_data_model_connectors = [
        mapping.get("connector")
        for mapping in connector_mappings
        if mapping.get("write_enabled") is not False or mapping.get("credential_required") is not True or not mapping.get("entities")
    ]
    if unsafe_data_model_connectors:
        data_errors.append(f"Business Data Model unsafe connector mappings: {unsafe_data_model_connectors}")
    relationship_pairs = {(row.get("from"), row.get("to")) for row in business_data_model.get("relationships", [])}
    required_relationship_pairs = {
        ("contact", "lead"),
        ("lead", "deal"),
        ("property", "deal"),
        ("deal", "document"),
        ("lead", "communication"),
        ("lead", "task"),
        ("workflow", "task"),
        ("property", "content_asset"),
    }
    missing_relationship_pairs = sorted(required_relationship_pairs - relationship_pairs)
    if missing_relationship_pairs:
        data_errors.append(f"Business Data Model missing relationships: {missing_relationship_pairs}")
    bad_data_model_side_effects = [
        key for key, value in business_data_model.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_data_model_side_effects:
        data_errors.append(f"Business Data Model side effects not false: {bad_data_model_side_effects}")
    business_sync_queue = command_center_data.get("business_sync_queue", {})
    if not business_sync_queue:
        data_errors.append("Business Sync Queue report missing from command-center data")
    sync_summary = business_sync_queue.get("summary", {})
    if sync_summary.get("sync_packet_count", 0) < 25:
        data_errors.append("Business Sync Queue packet count too low")
    if sync_summary.get("connector_count", 0) < 9:
        data_errors.append("Business Sync Queue connector count too low")
    if sync_summary.get("entity_count", 0) < 12:
        data_errors.append("Business Sync Queue entity count too low")
    if sync_summary.get("blocked_packet_count", 0) != sync_summary.get("sync_packet_count", 0):
        data_errors.append("Business Sync Queue blocked packet count does not match packet count")
    for key in ["ready_for_live_sync_count", "write_enabled_count", "execution_enabled_count", "network_call_enabled_count", "credentials_included_count"]:
        if sync_summary.get(key, 0) != 0:
            data_errors.append(f"Business Sync Queue unsafe nonzero count: {key}={sync_summary.get(key)}")
    if sync_summary.get("all_packets_blocked") is not True:
        data_errors.append("Business Sync Queue packets are not all blocked")
    if sync_summary.get("all_writes_disabled") is not True:
        data_errors.append("Business Sync Queue writes are not fully disabled")
    if sync_summary.get("all_external_actions_disabled") is not True:
        data_errors.append("Business Sync Queue external actions not fully disabled")
    sync_connectors = set(business_sync_queue.get("connectors", []))
    missing_sync_connectors = sorted(required_data_model_connectors - sync_connectors)
    if missing_sync_connectors:
        data_errors.append(f"Business Sync Queue missing connectors: {missing_sync_connectors}")
    sync_entities = set(business_sync_queue.get("entities", []))
    missing_sync_entities = sorted(required_entities - sync_entities)
    if missing_sync_entities:
        data_errors.append(f"Business Sync Queue missing entities: {missing_sync_entities}")
    sync_packets = business_sync_queue.get("sync_packets", [])
    unsafe_sync_packets = [
        packet.get("packet_id")
        for packet in sync_packets
        if packet.get("write_enabled") is not False
        or packet.get("execution_enabled") is not False
        or packet.get("network_call_enabled") is not False
        or packet.get("credentials_included") is not False
        or packet.get("ready_for_live_sync") is not False
    ]
    if unsafe_sync_packets:
        data_errors.append(f"Business Sync Queue unsafe packets: {unsafe_sync_packets}")
    missing_sync_contracts = [
        packet.get("packet_id")
        for packet in sync_packets
        if not packet.get("operation_contract") or not packet.get("approval_gate") or not packet.get("target")
    ]
    if missing_sync_contracts:
        data_errors.append(f"Business Sync Queue missing packet contracts: {missing_sync_contracts}")
    bad_sync_side_effects = [
        key for key, value in business_sync_queue.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_sync_side_effects:
        data_errors.append(f"Business Sync Queue side effects not false: {bad_sync_side_effects}")
    weekly_review = command_center_data.get("weekly_operating_review", {})
    if not weekly_review:
        data_errors.append("Weekly Operating Review report missing from command-center data")
    weekly_summary = weekly_review.get("summary", {})
    if weekly_summary.get("review_section_count", 0) < 8:
        data_errors.append("Weekly Operating Review section count too low")
    if weekly_summary.get("decision_count", 0) < 4:
        data_errors.append("Weekly Operating Review decision count too low")
    if weekly_summary.get("next_week_priority_count", 0) < 5:
        data_errors.append("Weekly Operating Review priority count too low")
    if weekly_summary.get("weekly_hours_saved_projection", 0) < 5:
        data_errors.append("Weekly Operating Review weekly hours projection too low")
    if weekly_summary.get("manual_work_reduction_units", 0) < 50:
        data_errors.append("Weekly Operating Review manual-work reduction too low")
    if weekly_summary.get("adoption_score", 0) < 70:
        data_errors.append("Weekly Operating Review adoption score too low")
    if weekly_summary.get("connector_activation_allowed", 0) != 0:
        data_errors.append("Weekly Operating Review connector activation allowed unexpectedly")
    if weekly_summary.get("sync_ready_count", 0) != 0:
        data_errors.append("Weekly Operating Review sync ready count should be zero")
    if weekly_summary.get("all_decisions_execution_disabled") is not True:
        data_errors.append("Weekly Operating Review decisions are not all execution-disabled")
    if weekly_summary.get("all_external_actions_disabled") is not True:
        data_errors.append("Weekly Operating Review external actions not fully disabled")
    review_sections = weekly_review.get("review_sections", [])
    review_section_names = {section.get("section") for section in review_sections}
    required_review_sections = {
        "executive_scorecard",
        "crm_followup_quality",
        "operations_pipeline",
        "content_output",
        "connector_activation",
        "sync_readiness",
        "daily_operating_cadence",
        "ceo_decisions",
    }
    missing_review_sections = sorted(required_review_sections - review_section_names)
    if missing_review_sections:
        data_errors.append(f"Weekly Operating Review missing sections: {missing_review_sections}")
    weekly_decisions = weekly_review.get("decision_queue", [])
    unsafe_weekly_decisions = [item.get("decision") for item in weekly_decisions if item.get("execution_enabled") is not False]
    if unsafe_weekly_decisions:
        data_errors.append(f"Weekly Operating Review unsafe decisions: {unsafe_weekly_decisions}")
    weekly_priorities = weekly_review.get("next_week_priorities", [])
    missing_priority_contracts = [
        item.get("priority")
        for item in weekly_priorities
        if not item.get("title") or not item.get("source_section") or not item.get("success_check")
    ]
    if missing_priority_contracts:
        data_errors.append(f"Weekly Operating Review missing priority contracts: {missing_priority_contracts}")
    weekly_scorecard = weekly_review.get("scorecard", {})
    for key in ["adoption_score", "weekly_hours_saved_projection", "manual_work_reduction_units", "search_records", "workflow_records", "sync_packets", "sync_blocked"]:
        if key not in weekly_scorecard:
            data_errors.append(f"Weekly Operating Review scorecard missing {key}")
    bad_weekly_side_effects = [
        key for key, value in weekly_review.get("external_side_effects", {}).items() if value is not False
    ]
    if bad_weekly_side_effects:
        data_errors.append(f"Weekly Operating Review side effects not false: {bad_weekly_side_effects}")
    website_text = WEBSITE_PATH.read_text(encoding="utf-8", errors="ignore") if WEBSITE_PATH.exists() else ""
    website_required_terms = [
        "AIOS | Home Sweet Home Operating System",
        "The command layer for Home Sweet Home",
        "Business Operating System",
        "Property Intelligence",
        "Operations Brain",
        "Knowledge Vault",
        "Client Pipeline and Follow-Up",
        "Content Factory",
        "Command Center",
        "Public face. Internal cockpit.",
        "Search Everything",
        "Request a workflow, document, lead, or operation",
        "Open Command Center",
        "Open Mobile Console",
        "automation/central_orchestrator/reports/COMMAND_CENTER_DATA.json",
        "AIOS-DASHBOARD.html",
        "AIOS-MOBILE-APP.html",
        "External sends, writes, publishes, and connector execution remain disabled",
    ]
    missing_website_terms = [term for term in website_required_terms if term not in website_text]
    if not WEBSITE_PATH.exists():
        data_errors.append("AIOS website file missing")
    if missing_website_terms:
        data_errors.append(f"AIOS website missing required terms: {missing_website_terms}")
    mobile_app_text = MOBILE_APP_PATH.read_text(encoding="utf-8", errors="ignore") if MOBILE_APP_PATH.exists() else ""
    mobile_required_terms = [
        "AIOS Mobile Command Console",
        "Run HSH from the phone",
        "Mobile Operating Console",
        "Enter request",
        "Run request",
        "Property Search",
        "Lead Search",
        "Tasks",
        "Calendar",
        "Gmail",
        "Documents",
        "Operations Assistant",
        "Notifications",
        "Voice Commands",
        "automation/central_orchestrator/reports/COMMAND_CENTER_DATA.json",
        "viewport-fit=cover",
    ]
    missing_mobile_terms = [term for term in mobile_required_terms if term not in mobile_app_text]
    if not MOBILE_APP_PATH.exists():
        data_errors.append("AIOS mobile app file missing")
    if missing_mobile_terms:
        data_errors.append(f"AIOS mobile app missing required terms: {missing_mobile_terms}")
    product_identity_text = PRODUCT_IDENTITY_PATH.read_text(encoding="utf-8", errors="ignore") if PRODUCT_IDENTITY_PATH.exists() else ""
    product_identity_required_terms = [
        "Business Operating System",
        "Command Center",
        "Decision Platform",
        "Intelligence Layer",
        "AI is infrastructure, not the product experience",
        "Request -> Decision -> Action",
        "#090A0B",
        "#7B61FF",
        "Does this feel like the command center of a modern company?",
    ]
    missing_product_identity_terms = [term for term in product_identity_required_terms if term not in product_identity_text]
    if not PRODUCT_IDENTITY_PATH.exists():
        data_errors.append("AIOS product identity directive missing")
    if missing_product_identity_terms:
        data_errors.append(f"AIOS product identity directive missing terms: {missing_product_identity_terms}")
    workflow_paths = {workflow.get("path") for workflow in command_center_data.get("workflows", [])}
    if "AIOS-WEBSITE.html" not in workflow_paths:
        data_errors.append("AIOS website missing from workflow catalog")
    if "AIOS-MOBILE-APP.html" not in workflow_paths:
        data_errors.append("AIOS mobile app missing from workflow catalog")
    if not approval_result.get("passed"):
        data_errors.append("approval state manager did not pass")
    if not command_action_id:
        data_errors.append("approval command validation had no action_id to test")
    if approval_command_result and not approval_command_result.get("passed"):
        data_errors.append("local approval command did not pass approved rehearsal")
    if approval_command_result and approval_command_result.get("matching_dry_run_item", {}).get("eligible_for_connector_execution") is not True:
        data_errors.append("local approval command did not make approved packet ready in dry run")
    if approval_command_result and approval_command_result.get("matching_dry_run_item", {}).get("would_execute_external_connectors") is not False:
        data_errors.append("local approval command allowed external connector execution")
    if approval_command_result and approval_command_result.get("would_execute_dry_run_steps"):
        data_errors.append("local approval command produced dry-run steps that would execute")
    if approval_command_result:
        bad_approval_command_side_effects = [
            key for key, value in approval_command_result.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_approval_command_side_effects:
            data_errors.append(f"local approval command side effects not false: {bad_approval_command_side_effects}")
    if reverted_approval_command_result and reverted_approval_command_result.get("matching_dry_run_item", {}).get("eligible_for_connector_execution"):
        data_errors.append("local approval command reset did not return packet to blocked dry-run state")
    if live_run_request_after_approve:
        if live_run_request_after_approve.get("execution_enabled"):
            data_errors.append("live-run request after approval enabled execution unexpectedly")
        if live_run_request_after_approve.get("ready_items_count") != 1:
            data_errors.append("live-run request after approval did not package exactly one ready item")
        ready_ids = [item.get("action_id") for item in live_run_request_after_approve.get("ready_items", [])]
        if command_action_id not in ready_ids:
            data_errors.append("live-run request after approval did not include approved action")
        request_steps = [
            step
            for item in live_run_request_after_approve.get("ready_items", [])
            for step in item.get("steps", [])
        ]
        if any(step.get("would_execute") for step in request_steps):
            data_errors.append("live-run request after approval included executable steps")
        bad_live_request_side_effects = [
            key for key, value in live_run_request_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_live_request_side_effects:
            data_errors.append(f"live-run request side effects not false: {bad_live_request_side_effects}")
    if live_runner_after_approve_refusal:
        if live_runner_after_approve_refusal.get("runner_status") != "refused":
            data_errors.append("live connector runner did not refuse approved request without final approval")
        if "missing_final_approval" not in live_runner_after_approve_refusal.get("refusal_reasons", []):
            data_errors.append("live connector runner refusal did not include missing_final_approval")
        if live_runner_after_approve_refusal.get("execution_enabled"):
            data_errors.append("live connector runner refusal enabled execution unexpectedly")
    if live_runner_after_approve_validated:
        if live_runner_after_approve_validated.get("runner_status") != "validated_plan_only_no_external_calls":
            data_errors.append("live connector runner did not produce validated-plan-only status with final approval")
        if live_runner_after_approve_validated.get("planned_steps_count") != live_run_request_after_approve.get("proposed_steps_count"):
            data_errors.append("live connector runner planned step count did not match approved request")
        if live_runner_after_approve_validated.get("execution_enabled"):
            data_errors.append("live connector runner validated plan enabled execution unexpectedly")
        bad_runner_steps = [
            step for step in live_runner_after_approve_validated.get("planned_steps", []) if step.get("would_call_external_service")
        ]
        if bad_runner_steps:
            data_errors.append("live connector runner planned steps would call external service")
        bad_runner_side_effects = [
            key for key, value in live_runner_after_approve_validated.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_runner_side_effects:
            data_errors.append(f"live connector runner side effects not false: {bad_runner_side_effects}")
    if connector_payloads_after_approve:
        if connector_payloads_after_approve.get("payload_count") != 3:
            data_errors.append("connector payload builder did not create expected n8n, Airtable, and Notion payloads")
        connectors = sorted(payload.get("connector") for payload in connector_payloads_after_approve.get("payloads", []))
        if connectors != ["airtable", "n8n", "notion"]:
            data_errors.append(f"connector payload builder returned unexpected connectors: {connectors}")
        bad_payload_flags = [
            payload.get("connector")
            for payload in connector_payloads_after_approve.get("payloads", [])
            if payload.get("network_call_enabled") is not False or payload.get("execution_enabled") is not False
        ]
        if bad_payload_flags:
            data_errors.append(f"connector payloads enabled execution unexpectedly: {bad_payload_flags}")
        bad_payload_side_effects = [
            key for key, value in connector_payloads_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_payload_side_effects:
            data_errors.append(f"connector payload side effects not false: {bad_payload_side_effects}")
    if connector_activation_after_approve:
        if connector_activation_after_approve.get("checklist_item_count") != connector_payloads_after_approve.get("payload_count"):
            data_errors.append("activation checklist item count did not match approved payload count")
        if connector_activation_after_approve.get("activation_enabled"):
            data_errors.append("activation checklist enabled activation unexpectedly")
        bad_activation_items = [
            item.get("connector")
            for item in connector_activation_after_approve.get("items", [])
            if item.get("network_call_enabled") is not False or item.get("execution_enabled") is not False or item.get("activation_allowed") is not False
        ]
        if bad_activation_items:
            data_errors.append(f"activation checklist items enabled execution unexpectedly: {bad_activation_items}")
        bad_activation_side_effects = [
            key for key, value in connector_activation_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_activation_side_effects:
            data_errors.append(f"activation checklist side effects not false: {bad_activation_side_effects}")
    if n8n_dry_import_after_approve:
        if n8n_dry_import_after_approve.get("workflow_count") != 1:
            data_errors.append("n8n dry import did not create exactly one workflow draft")
        if n8n_dry_import_after_approve.get("workflow_ready") is not True:
            data_errors.append("n8n dry import approved branch was not workflow_ready")
        if n8n_dry_import_after_approve.get("import_enabled"):
            data_errors.append("n8n dry import enabled import unexpectedly")
        if n8n_dry_import_after_approve.get("activation_enabled"):
            data_errors.append("n8n dry import enabled activation unexpectedly")
        if n8n_dry_import_after_approve.get("credentials_included"):
            data_errors.append("n8n dry import included credentials unexpectedly")
        bad_n8n_side_effects = [
            key for key, value in n8n_dry_import_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_n8n_side_effects:
            data_errors.append(f"n8n dry import side effects not false: {bad_n8n_side_effects}")
    if airtable_dry_import_after_approve:
        if airtable_dry_import_after_approve.get("schema_count") != 1:
            data_errors.append("Airtable dry import did not create exactly one schema map")
        if airtable_dry_import_after_approve.get("schema_ready") is not True:
            data_errors.append("Airtable dry import approved branch was not schema_ready")
        if airtable_dry_import_after_approve.get("network_call_enabled"):
            data_errors.append("Airtable dry import enabled network calls unexpectedly")
        if airtable_dry_import_after_approve.get("write_enabled"):
            data_errors.append("Airtable dry import enabled writes unexpectedly")
        if airtable_dry_import_after_approve.get("import_enabled"):
            data_errors.append("Airtable dry import enabled import unexpectedly")
        if airtable_dry_import_after_approve.get("activation_enabled"):
            data_errors.append("Airtable dry import enabled activation unexpectedly")
        if airtable_dry_import_after_approve.get("credentials_included"):
            data_errors.append("Airtable dry import included credentials unexpectedly")
        schemas = airtable_dry_import_after_approve.get("schemas", [])
        if schemas:
            schema = schemas[0]
            if schema.get("base_contract") != "Omar RE OS CRM tables":
                data_errors.append("Airtable dry import base contract mismatch")
            if schema.get("table_contract") != "AIOS Action Queue":
                data_errors.append("Airtable dry import table contract mismatch")
            if schema.get("match_field") != "Action ID":
                data_errors.append("Airtable dry import match field mismatch")
            if not schema.get("packet_path"):
                data_errors.append("Airtable dry import packet path missing")
            unsafe_fields = [field.get("field_name") for field in schema.get("fields", []) if field.get("write_enabled") is not False]
            if unsafe_fields:
                data_errors.append(f"Airtable dry import fields enabled writes unexpectedly: {unsafe_fields}")
        bad_airtable_side_effects = [
            key for key, value in airtable_dry_import_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_airtable_side_effects:
            data_errors.append(f"Airtable dry import side effects not false: {bad_airtable_side_effects}")
    if notion_dry_import_after_approve:
        if notion_dry_import_after_approve.get("page_count") != 1:
            data_errors.append("Notion dry import did not create exactly one page draft")
        if notion_dry_import_after_approve.get("page_ready") is not True:
            data_errors.append("Notion dry import approved branch was not page_ready")
        if notion_dry_import_after_approve.get("network_call_enabled"):
            data_errors.append("Notion dry import enabled network calls unexpectedly")
        if notion_dry_import_after_approve.get("page_create_enabled"):
            data_errors.append("Notion dry import enabled page creation unexpectedly")
        if notion_dry_import_after_approve.get("activation_enabled"):
            data_errors.append("Notion dry import enabled activation unexpectedly")
        if notion_dry_import_after_approve.get("credentials_included"):
            data_errors.append("Notion dry import included credentials unexpectedly")
        pages = notion_dry_import_after_approve.get("pages", [])
        if pages:
            page = pages[0]
            if page.get("workspace_contract") != "AIOS Notion workspace":
                data_errors.append("Notion dry import workspace contract mismatch")
            if page.get("database_contract") != "AIOS Operations Knowledge Base":
                data_errors.append("Notion dry import database contract mismatch")
            if page.get("match_field") != "Action ID":
                data_errors.append("Notion dry import match field mismatch")
            if not page.get("packet_path"):
                data_errors.append("Notion dry import packet path missing")
        bad_notion_side_effects = [
            key for key, value in notion_dry_import_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_notion_side_effects:
            data_errors.append(f"Notion dry import side effects not false: {bad_notion_side_effects}")
    if google_workspace_briefing_after_approve:
        if google_briefing_payloads.get("payload_count") != 2:
            data_errors.append("Google briefing rehearsal did not create expected Gmail and Calendar payloads")
        briefing_connectors = sorted(payload.get("connector") for payload in google_briefing_payloads.get("payloads", []))
        if briefing_connectors != ["calendar_read", "gmail_draft"]:
            data_errors.append(f"Google briefing rehearsal returned unexpected connectors: {briefing_connectors}")
        if google_briefing_activation.get("checklist_item_count") != 2:
            data_errors.append("Google briefing activation checklist did not include Gmail and Calendar")
        if google_workspace_briefing_after_approve.get("artifact_count") != 2:
            data_errors.append("Google briefing dry review did not create exactly two artifacts")
        if google_workspace_briefing_after_approve.get("artifact_ready") is not True:
            data_errors.append("Google briefing dry review was not artifact_ready")
        bad_google_briefing_flags = [
            key
            for key in ["network_call_enabled", "execution_enabled", "credentials_included"]
            if google_workspace_briefing_after_approve.get(key) is not False
        ]
        if bad_google_briefing_flags:
            data_errors.append(f"Google briefing dry review enabled unsafe flags: {bad_google_briefing_flags}")
        bad_google_briefing_side_effects = [
            key for key, value in google_workspace_briefing_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_google_briefing_side_effects:
            data_errors.append(f"Google briefing dry review side effects not false: {bad_google_briefing_side_effects}")
        if google_briefing_reset and google_briefing_reset.get("matching_dry_run_item", {}).get("eligible_for_connector_execution"):
            data_errors.append("Google briefing reset did not return packet to blocked dry-run state")
    if google_workspace_content_after_approve:
        if google_content_payloads.get("payload_count") != 3:
            data_errors.append("Google content rehearsal did not create expected Drive, Content Factory, and Instagram payloads")
        content_connectors = sorted(payload.get("connector") for payload in google_content_payloads.get("payloads", []))
        if content_connectors != ["content_factory", "drive_draft", "instagram_draft"]:
            data_errors.append(f"Google content rehearsal returned unexpected connectors: {content_connectors}")
        if google_content_activation.get("checklist_item_count") != 3:
            data_errors.append("Google content activation checklist did not include Drive, Content Factory, and Instagram")
        if google_workspace_content_after_approve.get("artifact_count") != 1:
            data_errors.append("Google content dry review did not create exactly one artifact")
        if google_workspace_content_after_approve.get("artifact_ready") is not True:
            data_errors.append("Google content dry review was not artifact_ready")
        bad_google_content_flags = [
            key
            for key in ["network_call_enabled", "execution_enabled", "credentials_included"]
            if google_workspace_content_after_approve.get(key) is not False
        ]
        if bad_google_content_flags:
            data_errors.append(f"Google content dry review enabled unsafe flags: {bad_google_content_flags}")
        bad_google_content_side_effects = [
            key for key, value in google_workspace_content_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_google_content_side_effects:
            data_errors.append(f"Google content dry review side effects not false: {bad_google_content_side_effects}")
        if google_content_reset and google_content_reset.get("matching_dry_run_item", {}).get("eligible_for_connector_execution"):
            data_errors.append("Google content reset did not return packet to blocked dry-run state")
    if social_content_after_approve:
        if social_content_after_approve.get("artifact_count") != 2:
            data_errors.append("Social content dry review did not create expected Content Factory and Instagram artifacts")
        social_connectors = sorted(artifact.get("connector") for artifact in social_content_after_approve.get("artifacts", []))
        if social_connectors != ["content_factory", "instagram_draft"]:
            data_errors.append(f"Social content dry review returned unexpected connectors: {social_connectors}")
        if social_content_after_approve.get("artifact_ready") is not True:
            data_errors.append("Social content dry review was not artifact_ready")
        bad_social_flags = [
            key
            for key in ["network_call_enabled", "execution_enabled", "publish_enabled", "credentials_included"]
            if social_content_after_approve.get(key) is not False
        ]
        if bad_social_flags:
            data_errors.append(f"Social content dry review enabled unsafe flags: {bad_social_flags}")
        bad_social_side_effects = [
            key for key, value in social_content_after_approve.get("external_side_effects", {}).items() if value is not False
        ]
        if bad_social_side_effects:
            data_errors.append(f"Social content dry review side effects not false: {bad_social_side_effects}")
    if live_run_request.get("execution_enabled"):
        data_errors.append("final live-run request enabled execution unexpectedly")
    if live_run_request.get("ready_items_count", 0) != 0:
        data_errors.append("final live-run request should have zero ready items after reset")
    if live_run_request.get("proposed_steps_count", 0) != 0:
        data_errors.append("final live-run request should have zero proposed steps after reset")
    if live_connector_runner.get("runner_status") != "refused":
        data_errors.append("final live connector runner should be refused")
    if "missing_final_approval" not in live_connector_runner.get("refusal_reasons", []):
        data_errors.append("final live connector runner missing final approval refusal reason")
    if "no_ready_live_run_items" not in live_connector_runner.get("refusal_reasons", []):
        data_errors.append("final live connector runner missing no-ready-items refusal reason")
    if live_connector_runner.get("execution_enabled"):
        data_errors.append("final live connector runner enabled execution unexpectedly")
    if connector_payloads.get("payload_count", 0) != 0:
        data_errors.append("final connector payload builder should have zero payloads")
    if connector_payloads.get("execution_enabled"):
        data_errors.append("final connector payload builder enabled execution unexpectedly")
    if connector_activation.get("checklist_item_count", 0) != 0:
        data_errors.append("final activation checklist should have zero checklist items")
    if connector_activation.get("activation_enabled"):
        data_errors.append("final activation checklist enabled activation unexpectedly")
    if n8n_dry_import.get("workflow_count", 0) != 0:
        data_errors.append("final n8n dry import should have zero workflow drafts")
    if n8n_dry_import.get("import_enabled"):
        data_errors.append("final n8n dry import enabled import unexpectedly")
    if n8n_dry_import.get("activation_enabled"):
        data_errors.append("final n8n dry import enabled activation unexpectedly")
    if airtable_dry_import.get("schema_count", 0) != 0:
        data_errors.append("final Airtable dry import should have zero schema maps")
    if airtable_dry_import.get("network_call_enabled"):
        data_errors.append("final Airtable dry import enabled network calls unexpectedly")
    if airtable_dry_import.get("write_enabled"):
        data_errors.append("final Airtable dry import enabled writes unexpectedly")
    if airtable_dry_import.get("import_enabled"):
        data_errors.append("final Airtable dry import enabled import unexpectedly")
    if airtable_dry_import.get("activation_enabled"):
        data_errors.append("final Airtable dry import enabled activation unexpectedly")
    if notion_dry_import.get("page_count", 0) != 0:
        data_errors.append("final Notion dry import should have zero page drafts")
    if notion_dry_import.get("network_call_enabled"):
        data_errors.append("final Notion dry import enabled network calls unexpectedly")
    if notion_dry_import.get("page_create_enabled"):
        data_errors.append("final Notion dry import enabled page creation unexpectedly")
    if notion_dry_import.get("activation_enabled"):
        data_errors.append("final Notion dry import enabled activation unexpectedly")
    if google_workspace_dry_import.get("artifact_count", 0) != 0:
        data_errors.append("final Google Workspace dry review should have zero artifacts")
    if google_workspace_dry_import.get("network_call_enabled"):
        data_errors.append("final Google Workspace dry review enabled network calls unexpectedly")
    if google_workspace_dry_import.get("execution_enabled"):
        data_errors.append("final Google Workspace dry review enabled execution unexpectedly")
    if google_workspace_dry_import.get("credentials_included"):
        data_errors.append("final Google Workspace dry review included credentials unexpectedly")
    if social_content_dry_review.get("artifact_count", 0) != 0:
        data_errors.append("final Social Content dry review should have zero artifacts")
    if social_content_dry_review.get("network_call_enabled"):
        data_errors.append("final Social Content dry review enabled network calls unexpectedly")
    if social_content_dry_review.get("execution_enabled"):
        data_errors.append("final Social Content dry review enabled execution unexpectedly")
    if social_content_dry_review.get("publish_enabled"):
        data_errors.append("final Social Content dry review enabled publishing unexpectedly")
    if social_content_dry_review.get("credentials_included"):
        data_errors.append("final Social Content dry review included credentials unexpectedly")
    approvals = command_center_data.get("approval_state", {}).get("approvals", [])
    if len(approvals) < len(command_center_data.get("action_queue", {}).get("actions", [])):
        data_errors.append("approval state has fewer records than action queue")
    enabled = [item.get("action_id") for item in approvals if item.get("external_execution_enabled")]
    if enabled:
        data_errors.append(f"approval state enabled external execution unexpectedly: {enabled}")
    if connector_manifest.get("execution_enabled"):
        data_errors.append("connector manifest enabled execution unexpectedly")
    connector_items = connector_manifest.get("items", [])
    if len(connector_items) < len(approvals):
        data_errors.append("connector manifest has fewer items than approvals")
    enabled_ops = []
    for item in connector_items:
        for operation in item.get("operations", []):
            if operation.get("enabled"):
                enabled_ops.append(f"{item.get('action_id')}:{operation.get('connector')}")
    if enabled_ops:
        data_errors.append(f"connector operations enabled unexpectedly: {enabled_ops}")
    connector_side_effects = connector_manifest.get("external_side_effects", {})
    bad_connector_side_effects = [key for key, value in connector_side_effects.items() if value is not False]
    if bad_connector_side_effects:
        data_errors.append(f"connector manifest side effects not false: {bad_connector_side_effects}")
    if connector_dry_run.get("execution_enabled"):
        data_errors.append("connector dry run enabled execution unexpectedly")
    if connector_dry_run.get("items_count") != connector_manifest.get("items_count"):
        data_errors.append("connector dry run item count does not match connector manifest")
    if connector_dry_run.get("ready_items_count", 0) > connector_manifest.get("approved_items_count", 0):
        data_errors.append("connector dry run ready items exceed actually approved manifest items")
    dry_run_steps = [
        step
        for item in connector_dry_run.get("items", [])
        for step in item.get("steps", [])
    ]
    dry_run_would_execute = [step.get("connector") for step in dry_run_steps if step.get("would_execute")]
    if dry_run_would_execute:
        data_errors.append(f"connector dry run would execute external steps unexpectedly: {dry_run_would_execute}")
    dry_run_side_effects = connector_dry_run.get("external_side_effects", {})
    bad_dry_run_side_effects = [key for key, value in dry_run_side_effects.items() if value is not False]
    if bad_dry_run_side_effects:
        data_errors.append(f"connector dry run side effects not false: {bad_dry_run_side_effects}")
    if connector_simulated_dry_run.get("execution_enabled"):
        data_errors.append("simulated connector dry run enabled execution unexpectedly")
    if connector_simulated_dry_run.get("items_count") and connector_simulated_dry_run.get("ready_items_count") != connector_simulated_dry_run.get("items_count"):
        data_errors.append("simulated connector dry run did not rehearse every item as ready")
    simulated_steps = [
        step
        for item in connector_simulated_dry_run.get("items", [])
        for step in item.get("steps", [])
    ]
    simulated_would_execute = [step.get("connector") for step in simulated_steps if step.get("would_execute")]
    if simulated_would_execute:
        data_errors.append(f"simulated connector dry run would execute external steps unexpectedly: {simulated_would_execute}")
    action_side_effects = action_result.get("external_side_effects", {})
    bad_action_side_effects = [key for key, value in action_side_effects.items() if value is not False]
    if bad_action_side_effects:
        data_errors.append(f"local action runner side effects not false: {bad_action_side_effects}")
    side_effects = command_center_data.get("external_side_effects", {})
    bad_side_effects = [key for key, value in side_effects.items() if value is not False]
    if bad_side_effects:
        data_errors.append(f"command center data side effects not false: {bad_side_effects}")

    scenario_passed_count = sum(1 for row in rows if row["passed"])
    data_validation_passed = not data_errors
    report = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(rows),
        "passed_count": scenario_passed_count,
        "failed_count": sum(1 for row in rows if not row["passed"]),
        "passed": all(row["passed"] for row in rows) and data_validation_passed,
        "checks_passed": scenario_passed_count + (1 if data_validation_passed else 0),
        "checks_total": len(rows) + 1,
        "scenarios": rows,
        "command_center_data": {
            "passed": data_validation_passed,
            "errors": data_errors,
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "activity_records": len(command_center_data.get("activity", [])),
            "health_keys": sorted(command_center_data.get("health", {}).keys()),
            "ask_aios_intent": ask_response.get("intent"),
            "ask_aios_matches": len(ask_response.get("matches", [])),
            "action_queue_records": len(command_center_data.get("action_queue", {}).get("actions", [])),
            "latest_action_type": action.get("type", ""),
            "approval_records": len(approvals),
            "pending_approvals": command_center_data.get("approval_state", {}).get("pending_count", 0),
            "approval_command_test_action_id": command_action_id,
            "approval_command_ready_after_approve": approval_command_result.get("matching_dry_run_item", {}).get("eligible_for_connector_execution"),
            "approval_command_ready_after_reset": reverted_approval_command_result.get("matching_dry_run_item", {}).get("eligible_for_connector_execution"),
            "connector_manifest_items": len(connector_items),
            "connector_execution_enabled": connector_manifest.get("execution_enabled"),
            "connector_dry_run_items": connector_dry_run.get("items_count", 0),
            "connector_dry_run_ready_items": connector_dry_run.get("ready_items_count", 0),
            "connector_dry_run_blocked_items": connector_dry_run.get("blocked_items_count", 0),
            "connector_dry_run_steps": connector_dry_run.get("steps_count", 0),
            "live_run_request_ready_after_approve": live_run_request_after_approve.get("ready_items_count", 0),
            "live_run_request_final_ready": live_run_request.get("ready_items_count", 0),
            "live_run_request_final_steps": live_run_request.get("proposed_steps_count", 0),
            "live_runner_refusal_after_approve": live_runner_after_approve_refusal.get("runner_status"),
            "live_runner_validated_after_approve": live_runner_after_approve_validated.get("runner_status"),
            "live_runner_final_status": live_connector_runner.get("runner_status"),
            "live_runner_final_planned_steps": live_connector_runner.get("planned_steps_count", 0),
            "connector_payloads_after_approve": connector_payloads_after_approve.get("payload_count", 0),
            "connector_payloads_final_count": connector_payloads.get("payload_count", 0),
            "connector_activation_after_approve": connector_activation_after_approve.get("checklist_item_count", 0),
            "connector_activation_final_count": connector_activation.get("checklist_item_count", 0),
            "n8n_dry_import_after_approve": n8n_dry_import_after_approve.get("workflow_count", 0),
            "n8n_dry_import_final_count": n8n_dry_import.get("workflow_count", 0),
            "airtable_dry_import_after_approve": airtable_dry_import_after_approve.get("schema_count", 0),
            "airtable_dry_import_final_count": airtable_dry_import.get("schema_count", 0),
            "notion_dry_import_after_approve": notion_dry_import_after_approve.get("page_count", 0),
            "notion_dry_import_final_count": notion_dry_import.get("page_count", 0),
            "google_workspace_briefing_after_approve": google_workspace_briefing_after_approve.get("artifact_count", 0),
            "google_workspace_content_after_approve": google_workspace_content_after_approve.get("artifact_count", 0),
            "google_workspace_final_count": google_workspace_dry_import.get("artifact_count", 0),
            "social_content_after_approve": social_content_after_approve.get("artifact_count", 0),
            "social_content_final_count": social_content_dry_review.get("artifact_count", 0),
            "property_intelligence_matches": property_intelligence.get("matched_count", 0),
            "property_intelligence_top_matches": len(property_intelligence.get("top_matches", [])),
            "property_intelligence_contexts": len(property_intelligence.get("community_context", {})),
            "operations_assistant_cases": operations_assistant.get("case_count", 0),
            "operations_assistant_fee_total": operations_assistant.get("fee_calculator", {}).get("total_estimated_cash_to_close", 0),
            "operations_assistant_dld_transfer_fee": operations_assistant.get("fee_calculator", {}).get("transfer_fee", 0),
            "operations_assistant_mortgage_registration": operations_assistant.get("fee_calculator", {}).get("mortgage_registration", 0),
            "crm_followup_leads": crm_followup.get("lead_count", 0),
            "crm_followup_hot_leads": crm_followup.get("dashboard", {}).get("hot_leads", 0),
            "crm_followup_open_tasks": crm_followup.get("dashboard", {}).get("open_tasks", 0),
            "crm_followup_stale_risk_count": crm_followup.get("dashboard", {}).get("stale_risk_count", 0),
            "knowledge_vault_assets": knowledge_vault.get("asset_count", 0),
            "knowledge_vault_text_assets": knowledge_vault.get("text_asset_count", 0),
            "knowledge_vault_binary_assets": knowledge_vault.get("binary_asset_count", 0),
            "knowledge_vault_categories": len(knowledge_vault.get("categories", {})),
            "knowledge_vault_retrieval_queries": len(knowledge_vault.get("retrieval_results", [])),
            "knowledge_vault_document_cases": len(knowledge_vault.get("document_cases", [])),
            "content_factory_artifacts": content_factory.get("artifact_count", 0),
            "content_factory_types": sorted(content_types),
            "content_factory_compliance_checks": len(content_factory.get("compliance_checks", [])),
            "content_factory_property_assets": content_factory.get("asset_register", {}).get("property_campaign_assets", 0),
            "content_factory_presentation_assets": content_factory.get("asset_register", {}).get("presentation_assets", 0),
            "mobile_command_commands": mobile_command.get("command_count", 0),
            "mobile_command_voice_commands": mobile_command.get("voice_command_count", 0),
            "mobile_command_notifications": mobile_command.get("notification_count", 0),
            "mobile_command_capabilities": sorted(mobile_capabilities),
            "mobile_command_intents": sorted(mobile_intents),
            "ceo_operating_priorities": len(ceo_operating.get("priority_stack", [])),
            "ceo_operating_time_blocks": len(ceo_operating.get("time_blocks", [])),
            "ceo_operating_risk_controls": len(ceo_operating.get("risk_controls", [])),
            "ceo_operating_pending_approvals": ceo_operating.get("scorecard", {}).get("pending_approvals", 0),
            "impact_weekly_hours_saved": quality_metrics.get("estimated_weekly_hours_saved", 0),
            "impact_manual_work_units": quality_metrics.get("manual_work_reduction_units", 0),
            "impact_success_goals": sorted(success_goals.keys()),
            "unified_memory_packets": unified_memory.get("memory_packet_count", 0),
            "unified_memory_types": sorted(memory_types),
            "unified_memory_conversations": conversation_state.get("conversation_count", 0),
            "unified_memory_messages": conversation_state.get("message_count", 0),
            "aios_brain_answers": aios_brain.get("query_count", 0),
            "aios_brain_capabilities": sorted(brain_capabilities),
            "aios_brain_memory_packets": aios_brain.get("memory_packets_available", 0),
            "aios_interaction_pipeline_steps": aios_interaction_architecture.get("summary", {}).get("pipeline_step_count", 0),
            "aios_interaction_samples": aios_interaction_architecture.get("summary", {}).get("interaction_count", 0),
            "aios_interaction_restricted_requests": aios_interaction_architecture.get("summary", {}).get("restricted_request_count", 0),
            "aios_permission_runtime_source": aios_interaction_architecture.get("permission_runtime", {}).get("source_of_truth", ""),
            "aios_permission_runtime_fingerprint": aios_interaction_architecture.get("permission_runtime", {}).get("fingerprint", ""),
            "aios_permission_same_result_everywhere": aios_interaction_architecture.get("permission_runtime_consistency", {}).get("same_result_everywhere", False),
            "aios_permission_api_route": "/api/permission/evaluate",
            "aios_permission_api_decisions": len(permission_api_decisions),
            "aios_permission_api_audited": sum(1 for item in permission_api_decisions if item.get("audit_logged") is True),
            "aios_permission_audit_log": str(PERMISSION_AUDIT_LOG_PATH.relative_to(Path(__file__).resolve().parents[2])),
            "aios_interaction_eye_states": sorted(interaction_eye_states),
            "aios_interaction_identity_types": aios_interaction_architecture.get("summary", {}).get("identity_types_observed", []),
            "connector_readiness_connectors": readiness_summary.get("connector_count", 0),
            "connector_readiness_local_ready": readiness_summary.get("local_ready_count", 0),
            "connector_readiness_activation_allowed": readiness_summary.get("activation_allowed_count", 0),
            "connector_readiness_names": sorted(connector_names),
            "connector_activation_command_steps": activation_command_summary.get("connector_count", 0),
            "connector_activation_command_ready_for_login": activation_command_summary.get("ready_for_user_login_count", 0),
            "connector_activation_command_activation_allowed": activation_command_summary.get("activation_allowed_count", 0),
            "connector_activation_command_oauth_started": activation_command_summary.get("oauth_started_count", 0),
            "connector_activation_command_names": sorted(activation_step_names),
            "aios_autopilot_actions": autopilot_summary.get("action_count", 0),
            "aios_autopilot_auto_local": autopilot_summary.get("auto_local_count", 0),
            "aios_autopilot_stopped_for_human": autopilot_summary.get("stopped_for_human_count", 0),
            "aios_autopilot_minutes_saved": autopilot_summary.get("estimated_minutes_saved", 0),
            "aios_autopilot_domains": sorted(autopilot_domains),
            "daily_command_session_blocks": daily_session_summary.get("session_block_count", 0),
            "daily_command_session_items": daily_session_summary.get("session_item_count", 0),
            "daily_command_session_auto_local": daily_session_summary.get("auto_local_count", 0),
            "daily_command_session_stopped_for_human": daily_session_summary.get("stopped_for_human_count", 0),
            "daily_command_session_minutes": daily_session_summary.get("estimated_minutes_in_session", 0),
            "usage_ledger_entries": usage_summary.get("session_entry_count", 0),
            "usage_ledger_commands": usage_summary.get("commands_used_count", 0),
            "usage_ledger_modules": sorted(usage_modules),
            "usage_ledger_minutes": usage_summary.get("estimated_minutes_logged", 0),
            "usage_ledger_adoption_score": usage_summary.get("adoption_score", 0),
            "team_workspace_roles": team_summary.get("role_count", 0),
            "team_workspace_modules": team_summary.get("unique_module_count", 0),
            "team_workspace_blocked_actions": team_summary.get("blocked_action_count", 0),
            "team_workspace_role_names": sorted(role_names),
            "client_portal_sections": portal_summary.get("portal_section_count", 0),
            "client_portal_routes": portal_summary.get("request_route_count", 0),
            "client_portal_hidden_rules": portal_summary.get("hidden_data_rule_count", 0),
            "client_portal_published": portal_summary.get("published_portal_count", 0),
            "client_portal_section_names": sorted(portal_section_names),
            "client_portal_route_names": sorted(route_names),
            "aios_customer_demo_modules": customer_summary.get("demo_module_count", 0),
            "aios_customer_onboarding_routes": customer_summary.get("onboarding_route_count", 0),
            "aios_customer_isolation_rules": customer_summary.get("data_isolation_rule_count", 0),
            "aios_customer_workspace_published": customer_summary.get("published_customer_workspace_count", 0),
            "aios_customer_accounts": customer_summary.get("customer_account_count", 0),
            "aios_customer_trials_started": customer_summary.get("trial_started_count", 0),
            "aios_customer_checkouts_started": customer_summary.get("checkout_started_count", 0),
            "aios_customer_demo_module_names": sorted(demo_module_names),
            "aios_customer_onboarding_route_names": sorted(onboarding_route_names),
            "business_data_model_entities": data_model_summary.get("entity_count", 0),
            "business_data_model_relationships": data_model_summary.get("relationship_count", 0),
            "business_data_model_connector_mappings": data_model_summary.get("connector_mapping_count", 0),
            "business_data_model_migration_gates": data_model_summary.get("migration_gate_count", 0),
            "business_data_model_entity_names": sorted(canonical_entity_names),
            "business_data_model_connectors": sorted(data_model_connectors),
            "business_sync_queue_packets": sync_summary.get("sync_packet_count", 0),
            "business_sync_queue_connectors": sync_summary.get("connector_count", 0),
            "business_sync_queue_entities": sync_summary.get("entity_count", 0),
            "business_sync_queue_blocked": sync_summary.get("blocked_packet_count", 0),
            "business_sync_queue_ready": sync_summary.get("ready_for_live_sync_count", 0),
            "business_sync_queue_write_enabled": sync_summary.get("write_enabled_count", 0),
            "business_sync_queue_connector_names": sorted(sync_connectors),
            "business_sync_queue_entity_names": sorted(sync_entities),
            "weekly_review_sections": weekly_summary.get("review_section_count", 0),
            "weekly_review_decisions": weekly_summary.get("decision_count", 0),
            "weekly_review_priorities": weekly_summary.get("next_week_priority_count", 0),
            "weekly_review_hours_saved": weekly_summary.get("weekly_hours_saved_projection", 0),
            "weekly_review_adoption_score": weekly_summary.get("adoption_score", 0),
            "weekly_review_section_names": sorted(review_section_names),
            "website_ready": WEBSITE_PATH.exists() and not missing_website_terms,
            "website_required_features": len(website_required_terms),
            "mobile_app_ready": MOBILE_APP_PATH.exists() and not missing_mobile_terms,
            "mobile_app_required_features": len(mobile_required_terms),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    HEALTH_PATH.write_text(json.dumps({"updated_at": report["validated_at"], "health": health}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
