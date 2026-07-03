#!/usr/bin/env python3
"""AIOS social/content dry-review builder.

Creates local review artifacts from Content Factory and Instagram draft payload
contracts. It never generates final media, never posts to social channels, and
never calls external APIs.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_command_center_data import build as build_command_center_data
from connector_payload_builder import CONNECTOR_PAYLOADS_PATH


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
DRY_REVIEWS_DIR = REPORTS_DIR / "social_content_dry_reviews"
SOCIAL_CONTENT_DRY_REVIEW_MANIFEST_PATH = REPORTS_DIR / "SOCIAL_CONTENT_DRY_REVIEW_MANIFEST.json"
SOCIAL_CONTENT_DRY_REVIEW_RESULT_PATH = REPORTS_DIR / "SOCIAL_CONTENT_DRY_REVIEW_RESULT.json"

SOCIAL_CONNECTORS = {"content_factory", "instagram_draft"}

SIDE_EFFECTS_FALSE = {
    "n8n_workflows_called": False,
    "airtable_rows_written": False,
    "notion_pages_created": False,
    "gmail_drafts_created": False,
    "calendar_events_created": False,
    "drive_files_modified": False,
    "whatsapp_messages_sent": False,
    "instagram_posts_published": False,
    "content_assets_generated": False,
    "content_published": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    allowed = [char if char.isalnum() else "-" for char in value.upper()]
    return "-".join("".join(allowed).split("-"))[:90] or "AIOS-SOCIAL-CONTENT-DRY-REVIEW"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _artifact_for_payload(payload: dict[str, Any], label: str) -> dict[str, Any]:
    connector = payload.get("connector")
    if connector == "content_factory":
        body = payload.get("asset", {})
        title = "Content Factory Asset Review"
        action_id = str(body.get("action_id") or "NO_ACTION")
        request_id = str(body.get("request_id") or "NO_REQUEST")
        disabled_flags = {
            "asset_generation_enabled": payload.get("asset_generation_enabled") is False,
            "publish_enabled": payload.get("publish_enabled") is False,
        }
    else:
        body = payload.get("post", {})
        title = "Instagram Post Draft Review"
        action_id = str(body.get("action_id") or "NO_ACTION")
        request_id = str(body.get("request_id") or "NO_REQUEST")
        disabled_flags = {"publish_enabled": payload.get("publish_enabled") is False}
    return {
        "artifact_id": f"SCR-{_safe_slug(connector or 'social')}-{_safe_slug(action_id)}",
        "label": label,
        "title": title,
        "connector": connector,
        "payload_type": payload.get("payload_type"),
        "operation": payload.get("operation"),
        "target": payload.get("target"),
        "request_id": request_id,
        "action_id": action_id,
        "payload": payload,
        "disabled_flags": disabled_flags,
        "network_call_enabled": False,
        "execution_enabled": False,
        "publish_enabled": False,
        "credentials_included": False,
        "activation_allowed": False,
    }


def _markdown_artifact(artifact: dict[str, Any]) -> str:
    lines = [
        f"# AIOS Social Content Dry Review - {artifact['title']}",
        "",
        f"Artifact ID: `{artifact['artifact_id']}`",
        f"Request ID: `{artifact['request_id']}`",
        f"Action ID: `{artifact['action_id']}`",
        "",
        "## Target",
        "",
        f"- Connector: `{artifact.get('connector')}`",
        f"- Operation: `{artifact.get('operation')}`",
        f"- Target: `{artifact.get('target')}`",
        "",
        "## Payload Preview",
        "",
        "```json",
        json.dumps(artifact.get("payload", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Safety",
        "",
        "- Network call enabled: `false`",
        "- Execution enabled: `false`",
        "- Publish enabled: `false`",
        "- Credentials included: `false`",
        "- Activation allowed: `false`",
    ]
    for key in sorted(artifact.get("disabled_flags", {})):
        lines.append(f"- {key}: `false`")
    lines.append("")
    return "\n".join(lines)


def _validate_artifact(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    connector = artifact.get("connector")
    if connector not in SOCIAL_CONNECTORS:
        errors.append(f"unsupported_social_connector:{connector}")
    if not artifact.get("operation"):
        errors.append("missing_operation")
    if artifact.get("network_call_enabled") is not False:
        errors.append("network_call_enabled")
    if artifact.get("execution_enabled") is not False:
        errors.append("execution_enabled")
    if artifact.get("publish_enabled") is not False:
        errors.append("publish_enabled")
    if artifact.get("credentials_included") is not False:
        errors.append("credentials_included")
    if artifact.get("activation_allowed") is not False:
        errors.append("activation_allowed")
    for flag, disabled in artifact.get("disabled_flags", {}).items():
        if disabled is not True:
            errors.append(f"{flag}_not_disabled")
    return errors


def build(command: dict[str, Any] | None = None) -> dict[str, Any]:
    command = command or {}
    label = str(command.get("label", "local-social-content-dry-review"))
    payload_report = _load_json(CONNECTOR_PAYLOADS_PATH)
    social_payloads = [
        payload
        for payload in payload_report.get("payloads", [])
        if payload.get("connector") in SOCIAL_CONNECTORS
        and payload.get("network_call_enabled") is False
        and payload.get("execution_enabled") is False
    ]
    DRY_REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = []
    validation_errors = []

    for payload in social_payloads:
        artifact = _artifact_for_payload(payload, label)
        artifact_errors = _validate_artifact(artifact)
        validation_errors.extend(artifact_errors)
        file_name = f"{_safe_slug(artifact['request_id'])}-{_safe_slug(artifact['connector'])}-DRY-REVIEW.md"
        path = DRY_REVIEWS_DIR / file_name
        path.write_text(_markdown_artifact(artifact), encoding="utf-8")
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append(
            {
                **artifact,
                "packet_file": file_name,
                "packet_path": path.relative_to(REPORTS_DIR).as_posix(),
                "packet_sha256": sha256,
            }
        )

    manifest = {
        "generated_at": _now(),
        "mode": "social_content_dry_review_only",
        "payload_report_status": payload_report.get("runner_plan_status"),
        "payloads_ready": payload_report.get("payloads_ready") is True,
        "artifact_ready": bool(artifacts) and not validation_errors,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "validation_errors": validation_errors if artifacts else ["social_content_payload_not_ready"],
        "network_call_enabled": False,
        "execution_enabled": False,
        "publish_enabled": False,
        "credentials_included": False,
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    SOCIAL_CONTENT_DRY_REVIEW_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    command_center_data = build_command_center_data()
    result = {
        "ran_at": _now(),
        "passed": not validation_errors,
        "artifact_ready": manifest["artifact_ready"],
        "artifact_count": manifest["artifact_count"],
        "network_call_enabled": False,
        "execution_enabled": False,
        "publish_enabled": False,
        "credentials_included": False,
        "dashboard_records": {
            "search_records": len(command_center_data.get("search_index", [])),
            "workflow_records": len(command_center_data.get("workflows", [])),
            "approval_records": len(command_center_data.get("approval_state", {}).get("approvals", [])),
        },
        "external_side_effects": SIDE_EFFECTS_FALSE,
    }
    SOCIAL_CONTENT_DRY_REVIEW_RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _parse() -> dict[str, Any] | None:
    raw = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"label": raw}


if __name__ == "__main__":
    print(json.dumps(build(_parse()), indent=2, ensure_ascii=False))
