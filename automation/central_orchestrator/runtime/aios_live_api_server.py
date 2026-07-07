#!/usr/bin/env python3
"""AIOS live local API server.

Serves the static AIOS experience and exposes production-style API routes for
central runtime decisions. No external network calls or connector writes happen
here; this is the local live cutover path for browser/mobile/voice clients.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import hmac
import json
import logging
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from aios_interaction_architecture_runtime import evaluate_permission_request, permission_runtime_contract, process_interaction
from aios_runtime import get_runtime_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aios_live_api_server")

RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"

UNIT_INTELLIGENCE_RUNTIME = AIOS_ROOT / "automation" / "unit_intelligence" / "runtime"
if str(UNIT_INTELLIGENCE_RUNTIME) not in sys.path:
    sys.path.insert(0, str(UNIT_INTELLIGENCE_RUNTIME))
from api_handlers import ingest, enrich_pending, get_stats, resolve_property
AUDIT_LOG_PATH = REPORTS_DIR / "PERMISSION_AUDIT_LOG.jsonl"
AUDIT_SUMMARY_PATH = REPORTS_DIR / "PERMISSION_AUDIT_TRAIL.json"
WHATSAPP_TEST_LOG_PATH = REPORTS_DIR / "WHATSAPP_HOSTED_TEST_LOG.jsonl"
WHATSAPP_TEST_REPORT_PATH = REPORTS_DIR / "WHATSAPP_HOSTED_TEST_REPORT.json"
WHATSAPP_WEBHOOK_LOG_PATH = REPORTS_DIR / "WHATSAPP_PROVIDER_WEBHOOK_LOG.jsonl"
WHATSAPP_WEBHOOK_REPORT_PATH = REPORTS_DIR / "WHATSAPP_PROVIDER_WEBHOOK_REPORT.json"
PUBLIC_BETA_REPORT_PATH = REPORTS_DIR / "PUBLIC_BETA_VALIDATION.json"
HOSTED_RUNTIME_REPORT_PATH = REPORTS_DIR / "HOSTED_RUNTIME_VALIDATION.json"
EYE_MOTION_REPORT_PATH = REPORTS_DIR / "EYE_MOTION_VALIDATION.json"
LAUNCH_READINESS_REPORT_PATH = REPORTS_DIR / "PRODUCTION_LAUNCH_READINESS.json"
DEFAULT_HOST = os.getenv("AIOS_API_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("AIOS_API_PORT") or os.getenv("PORT") or "8888")
PUBLIC_API_BASE_URL = os.getenv("AIOS_PUBLIC_API_BASE_URL", "").strip().rstrip("/")
AUTH_MODE = os.getenv("AIOS_AUTH_MODE", "off").strip().lower()
AUTH_USER = os.getenv("AIOS_BASIC_AUTH_USER", "").strip()
AUTH_PASSWORD = os.getenv("AIOS_BASIC_AUTH_PASSWORD", "")
WHATSAPP_WEBHOOK_PATH = "/webhook/whatsapp/provider/gateway"
WHATSAPP_REPLY_MODE = os.getenv("AIOS_WHATSAPP_REPLY_MODE", "hold").strip().lower()
WHATSAPP_VERIFY_TOKEN = os.getenv("AIOS_WHATSAPP_VERIFY_TOKEN", "").strip()
# Wasender delivers inbound events with a shared secret in the
# ``X-Webhook-Signature`` header (see wasender_live_relay_server._verify_signature).
# Accept either env var name so the hosted runtime authorizes provider POSTs
# without depending on the Meta-style verify token being smuggled into them.
WASENDER_WEBHOOK_SECRET = (
    os.getenv("WASENDER_WEBHOOK_SECRET", "").strip()
    or os.getenv("AIOS_WEBHOOK_SECRET", "").strip()
)
PUBLIC_STATIC_PATHS = {
    "/",
    "/index.html",
    "/AIOS-WEBSITE.html",
    "/AIOS-MOBILE-APP.html",
    "/aios-service-worker.js",
    "/aios.webmanifest",
    "/offline.html",
    "/app/",
    "/app/index.html",
}
# NOTE: a blanket ".html" suffix here previously made EVERY html file public,
# including AIOS-DASHBOARD.html (the command center). Public pages must be
# listed explicitly in PUBLIC_STATIC_PATHS; everything else requires auth.
PUBLIC_STATIC_SUFFIXES = ()
PUBLIC_STATIC_PREFIXES = ("/assets/", "/app/assets/")
GZIP_STATIC_SUFFIXES = {".html", ".js", ".json", ".md", ".webmanifest", ".txt", ".css", ".svg"}
STATIC_GZIP_CACHE: dict[str, dict[str, Any]] = {}
COMMAND_CENTER_DATA_CACHE_SECONDS = int(os.getenv("AIOS_COMMAND_CENTER_DATA_CACHE_SECONDS", "30"))
COMMAND_CENTER_DATA_CACHE: dict[str, Any] = {}
PRETTY_JSON_RESPONSES = os.getenv("AIOS_JSON_PRETTY", "").strip().lower() in {"1", "true", "yes"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _read_json_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _read_request_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace")
    content_type = handler.headers.get("Content-Type", "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        return {key: value[0] if len(value) == 1 else value for key, value in parse_qs(text).items()}
    if "application/json" in content_type or text.strip().startswith("{"):
        return json.loads(text)
    return {"raw": text}


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, ensure_ascii=False)
        if PRETTY_JSON_RESPONSES
        else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    ).encode("utf-8")


def _write_json_bytes(
    handler: SimpleHTTPRequestHandler,
    status: int,
    body: bytes,
    *,
    gzip_body: bytes | None = None,
) -> None:
    compressed = "gzip" in handler.headers.get("Accept-Encoding", "").lower() and len(body) > 1024
    if compressed:
        body = gzip_body if gzip_body is not None else gzip.compress(body)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    if compressed:
        handler.send_header("Content-Encoding", "gzip")
        handler.send_header("Vary", "Accept-Encoding")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_json(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    _write_json_bytes(handler, status, _json_bytes(payload))


def _write_text(handler: SimpleHTTPRequestHandler, status: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _path(raw_path: str) -> str:
    return urlparse(raw_path).path


def _query(raw_path: str) -> dict[str, str]:
    parsed = parse_qs(urlparse(raw_path).query)
    return {key: value[0] if value else "" for key, value in parsed.items()}


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _public_static_path(path: str) -> bool:
    return path in PUBLIC_STATIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_STATIC_PREFIXES)


def _content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".json" or suffix == ".webmanifest":
        return "application/json; charset=utf-8"
    if suffix == ".md" or suffix == ".txt":
        return "text/plain; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def _gzip_static_entry(path: Path) -> dict[str, Any]:
    stat = path.stat()
    cache_key = str(path)
    etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
    cached = STATIC_GZIP_CACHE.get(cache_key)
    if cached and cached.get("mtime_ns") == stat.st_mtime_ns and cached.get("size") == stat.st_size:
        return cached
    raw = path.read_bytes()
    body = gzip.compress(raw, compresslevel=6)
    entry = {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "etag": etag,
        "body": body,
        "content_type": _content_type_for_path(path),
    }
    STATIC_GZIP_CACHE[cache_key] = entry
    return entry


def _append_restricted_audit(entry: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    rows = _audit_rows(limit=250)
    summary = {
        "generated_at": _now(),
        "audit_log": str(AUDIT_LOG_PATH.relative_to(AIOS_ROOT)),
        "restricted_decision_count": len(rows),
        "latest_decision": rows[-1] if rows else None,
        "entries": rows,
    }
    AUDIT_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _audit_rows(limit: int = 100) -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _read_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def get_command_center_data() -> dict[str, Any]:
    if COMMAND_CENTER_DATA_CACHE_SECONDS > 0:
        cached = COMMAND_CENTER_DATA_CACHE.get("payload")
        expires_at = float(COMMAND_CENTER_DATA_CACHE.get("expires_at") or 0)
        if cached and time.monotonic() < expires_at:
            return dict(cached)
    payload = _read_report(REPORTS_DIR / "COMMAND_CENTER_DATA.json")
    if not payload:
        from build_command_center_data import build as build_command_center_data

        payload = build_command_center_data()
    payload.setdefault("api", {})
    payload["api"].update(
        {
            "route": "/api/command-center/data",
            "generated_live": True,
            "cache_seconds": COMMAND_CENTER_DATA_CACHE_SECONDS,
        }
    )
    if COMMAND_CENTER_DATA_CACHE_SECONDS > 0:
        COMMAND_CENTER_DATA_CACHE["payload"] = dict(payload)
        COMMAND_CENTER_DATA_CACHE["expires_at"] = time.monotonic() + COMMAND_CENTER_DATA_CACHE_SECONDS
    return payload


def _write_command_center_data(handler: SimpleHTTPRequestHandler) -> None:
    if COMMAND_CENTER_DATA_CACHE_SECONDS > 0:
        json_body = COMMAND_CENTER_DATA_CACHE.get("json_body")
        gzip_body = COMMAND_CENTER_DATA_CACHE.get("gzip_body")
        expires_at = float(COMMAND_CENTER_DATA_CACHE.get("expires_at") or 0)
        if isinstance(json_body, bytes) and isinstance(gzip_body, bytes) and time.monotonic() < expires_at:
            _write_json_bytes(handler, 200, json_body, gzip_body=gzip_body)
            return
    payload = get_command_center_data()
    json_body = _json_bytes(payload)
    gzip_body = gzip.compress(json_body)
    if COMMAND_CENTER_DATA_CACHE_SECONDS > 0:
        COMMAND_CENTER_DATA_CACHE["json_body"] = json_body
        COMMAND_CENTER_DATA_CACHE["gzip_body"] = gzip_body
        COMMAND_CENTER_DATA_CACHE["expires_at"] = time.monotonic() + COMMAND_CENTER_DATA_CACHE_SECONDS
    _write_json_bytes(handler, 200, json_body, gzip_body=gzip_body)


def get_deployment_status() -> dict[str, Any]:
    runtime = get_runtime_status()
    beta = _read_report(PUBLIC_BETA_REPORT_PATH)
    hosted = _read_report(HOSTED_RUNTIME_REPORT_PATH)
    motion = _read_report(EYE_MOTION_REPORT_PATH)
    motion_checks = motion.get("checks") or []
    motion_summary = []
    for check in motion_checks:
        metrics = check.get("metrics") or {}
        motion_summary.append(
            {
                "name": check.get("name"),
                "passed": check.get("passed"),
                "changed_ratio": metrics.get("changed_ratio"),
                "center_changed_ratio": metrics.get("center_changed_ratio"),
                "mean_delta": metrics.get("mean_delta"),
            }
        )
    eye_motion_pass = motion.get("passed") is True
    eye_motion_checks = (
        f"{motion.get('checks_passed', 0)}/{motion.get('checks_total', 0)}" if motion else "not_validated"
    )
    runtime_ready_percent = int(runtime.get("runtime_ready_percent") or runtime.get("production_ready_percent") or beta.get("runtime_ready_percent") or 0)
    runtime_ready = runtime.get("status") == "ready" and runtime_ready_percent == 100
    derived_base_url = (
        beta.get("base_url")
        or hosted.get("base_url")
        or os.getenv("AIOS_PUBLIC_BASE_URL", "").strip().rstrip("/")
        or PUBLIC_API_BASE_URL
        or (
            f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()}"
            if os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
            else ""
        )
    )
    hosted_runtime_validated = hosted.get("passed") is True or (runtime_ready and bool(derived_base_url))
    auth_configured = AUTH_MODE == "basic" and bool(AUTH_USER) and bool(AUTH_PASSWORD)
    whatsapp_ingress_validated = (
        beta.get("whatsapp_backend_ingress_pass") is True
        or os.getenv("AIOS_WHATSAPP_HOSTED_TEST", "").strip().lower() == "pass"
    )
    webhook_verification_ready = bool(WHATSAPP_VERIFY_TOKEN)
    default_blockers = [
        "Run hosted validation against the public runtime URL.",
        "Attach permanent production backend/frontend host.",
        "Attach custom domain.",
        "Enable production authentication secrets.",
        "Set AIOS_WHATSAPP_VERIFY_TOKEN in Railway and switch Wasender webhook to the hosted runtime URL.",
    ]
    blockers = beta.get("blockers") or hosted.get("production_beta_blockers") or default_blockers
    if hosted_runtime_validated:
        blockers = [
            item
            for item in blockers
            if "hosted runtime" not in item.lower()
            and "public health endpoint" not in item.lower()
            and item not in {"Run hosted validation against the public runtime URL.", "Attach permanent production backend/frontend host."}
        ]
    if runtime_ready:
        blockers = [item for item in blockers if "orchestrator validation" not in item.lower()]
    if auth_configured:
        blockers = [item for item in blockers if item != "Enable production authentication secrets." and "authentication" not in item.lower()]
    if whatsapp_ingress_validated and webhook_verification_ready:
        blockers = [item for item in blockers if "whatsapp" not in item.lower() and "wasender" not in item.lower()]
    current_auth_status = (
        "basic"
        if auth_configured
        else "misconfigured"
        if AUTH_MODE == "basic"
        else "none"
        if AUTH_MODE in {"", "off", "none", "disabled"}
        else AUTH_MODE
    )
    return {
        "generated_at": _now(),
        "product": "AIOS",
        "status": "public_beta_live" if beta.get("public_beta_ready") is True else "deployment_pending",
        "runtime_ready": runtime_ready,
        "runtime_ready_percent": runtime_ready_percent,
        "production_deployment": runtime.get("production_deployment") or beta.get("production_deployment", "pending"),
        "public_beta_ready": runtime.get("public_beta_ready") is True or beta.get("public_beta_ready", False),
        "temporary_preview": beta.get("temporary_preview", True),
        "public_url": derived_base_url,
        "hosted_backend": "validated" if hosted_runtime_validated else "pending",
        "hosted_frontend": "validated" if hosted_runtime_validated else "pending",
        "auth_status": current_auth_status,
        "domain": "attached" if beta and beta.get("temporary_preview") is False else "pending",
        "whatsapp_hosted_test": "pass" if whatsapp_ingress_validated else "fail",
        "whatsapp_live_provider": "ready_for_provider" if webhook_verification_ready else "pending",
        "eye_motion": "pass" if eye_motion_pass else "pending_or_failed",
        "eye_motion_checks": eye_motion_checks,
        "eye_motion_report": str(EYE_MOTION_REPORT_PATH.relative_to(AIOS_ROOT)),
        "eye_motion_summary": motion_summary,
        "health_endpoint": "/api/health",
        "deployment_status_endpoint": "/api/deployment/status",
        "permission_endpoint": "/api/permission/evaluate",
        "whatsapp_webhook_endpoint": WHATSAPP_WEBHOOK_PATH,
        "unit_intelligence_endpoints": {
            "ingest": "/api/unit/ingest",
            "resolve": "/api/property/resolve",
            "enrich": "/api/unit/enrich",
            "stats": "/api/unit/stats",
        },
        "blockers": blockers,
        "reports": {
            "hosted_runtime": str(HOSTED_RUNTIME_REPORT_PATH.relative_to(AIOS_ROOT)),
            "public_beta": str(PUBLIC_BETA_REPORT_PATH.relative_to(AIOS_ROOT)),
            "eye_motion": str(EYE_MOTION_REPORT_PATH.relative_to(AIOS_ROOT)),
        },
        "next_action": "Resolve remaining deployment blockers, then rerun the public beta gate."
        if blockers
        else "Public beta gate passed. Proceed with controlled launch approval.",
    }


def get_launch_readiness() -> dict[str, Any]:
    readiness = _read_report(LAUNCH_READINESS_REPORT_PATH)
    if readiness:
        readiness.setdefault("report", str(LAUNCH_READINESS_REPORT_PATH.relative_to(AIOS_ROOT)))
        readiness.setdefault("endpoint", "/api/launch/readiness")
        return readiness
    deployment = get_deployment_status()
    blockers = list(deployment.get("blockers") or [])
    if deployment.get("eye_motion") != "pass":
        blocker_text = " ".join(blockers).lower()
        if "eye motion" not in blocker_text and "10-second" not in blocker_text:
            blockers.append("The 10-second Eye motion validation must pass.")
        if "visual presence" not in blocker_text:
            blockers.append("Visual presence validation must pass.")
    if deployment.get("public_beta_ready") is not True:
        blockers.append("Public beta gate must pass after permanent host, domain, auth, and WhatsApp provider are live.")
    deduped_blockers = []
    for item in blockers:
        if item and item not in deduped_blockers:
            deduped_blockers.append(item)
    runtime_ready = deployment.get("runtime_ready") is True
    public_beta_ready = deployment.get("public_beta_ready", False)
    return {
        "generated_at": _now(),
        "product": "AIOS",
        "feature": "Production Launch Readiness",
        "runtime_ready_percent": deployment.get("runtime_ready_percent", 0),
        "runtime_ready": runtime_ready,
        "production_deployment": deployment.get("production_deployment", "pending"),
        "public_beta_ready": public_beta_ready,
        "status": "public_beta_ready" if public_beta_ready else "runtime_ready_pending_external_launch" if runtime_ready else "runtime_not_ready",
        "public_url": deployment.get("public_url", ""),
        "blockers": deduped_blockers,
        "source_reports": deployment.get("reports", {}),
        "report": str(LAUNCH_READINESS_REPORT_PATH.relative_to(AIOS_ROOT)),
        "endpoint": "/api/launch/readiness",
    }


def get_client_config() -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "product": "AIOS",
        "api_base_url": PUBLIC_API_BASE_URL,
        "same_origin_api": not bool(PUBLIC_API_BASE_URL),
        "health_endpoint": "/api/health",
        "runtime_status_endpoint": "/api/runtime/status",
        "permission_endpoint": "/api/permission/evaluate",
        "deployment_status_endpoint": "/api/deployment/status",
        "launch_readiness_endpoint": "/api/launch/readiness",
        "unit_intelligence_endpoints": {
            "ingest": "/api/unit/ingest",
            "resolve": "/api/property/resolve",
            "enrich": "/api/unit/enrich",
            "stats": "/api/unit/stats",
        },
        "whatsapp_webhook_endpoint": WHATSAPP_WEBHOOK_PATH,
        "auth_mode": "basic" if AUTH_MODE == "basic" else "none",
    }


def evaluate_permission_api(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("request") or payload.get("text") or payload.get("message") or "").strip()
    channel = str(payload.get("channel") or "website").strip() or "website"
    identity_type = str(payload.get("identity_type") or payload.get("identity") or "Unknown").strip() or "Unknown"
    runtime_contract = permission_runtime_contract()
    decision = evaluate_permission_request(text, channel=channel, identity_type=identity_type)
    decision_id = "PERM-" + uuid.uuid4().hex[:12].upper()
    decision.update(
        {
            "decision_id": decision_id,
            "evaluated_at": _now(),
            "request_hash": _request_hash(text),
            "runtime_fingerprint": runtime_contract["fingerprint"],
            "audit_logged": False,
            "api": {
                "route": "/api/permission/evaluate",
                "server": "aios_live_api_server",
                "latency_budget_ms": 250,
                "source_of_truth": runtime_contract["source_of_truth"],
                "runtime_version": runtime_contract["version"],
            },
        }
    )
    if decision["blocked"]:
        audit_entry = {
            "decision_id": decision_id,
            "logged_at": decision["evaluated_at"],
            "channel": channel,
            "identity_type": identity_type,
            "request_hash": decision["request_hash"],
            "request_preview": text[:160],
            "blocked": decision["blocked"],
            "hits": decision["hits"],
            "rules": decision["rules"],
            "reason": decision["reason"],
            "allowed_alternatives": decision["allowed_alternatives"],
            "safety_gate": decision["safety_gate"],
            "eye_state": decision["eye_state"],
            "source_runtime": decision["source_runtime"],
        }
        _append_restricted_audit(audit_entry)
        decision["audit_logged"] = True
        decision["audit"] = {
            "decision_id": decision_id,
            "log": str(AUDIT_LOG_PATH.relative_to(AIOS_ROOT)),
            "summary": str(AUDIT_SUMMARY_PATH.relative_to(AIOS_ROOT)),
        }
    return decision


def _whatsapp_text(payload: dict[str, Any]) -> str:
    return str(
        payload.get("Body")
        or payload.get("body")
        or payload.get("message")
        or payload.get("text")
        or payload.get("message_text")
        or ""
    ).strip()


def _whatsapp_sender(payload: dict[str, Any]) -> str:
    return str(payload.get("From") or payload.get("from") or payload.get("waId") or payload.get("phone") or "unknown").strip()


def _append_whatsapp_test(entry: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with WHATSAPP_TEST_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    lines = WHATSAPP_TEST_LOG_PATH.read_text(encoding="utf-8").splitlines()[-50:]
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    WHATSAPP_TEST_REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "test_log": str(WHATSAPP_TEST_LOG_PATH.relative_to(AIOS_ROOT)),
                "hosted_test_count": len(rows),
                "latest_test": rows[-1] if rows else None,
                "entries": rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _append_whatsapp_webhook(entry: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with WHATSAPP_WEBHOOK_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    lines = WHATSAPP_WEBHOOK_LOG_PATH.read_text(encoding="utf-8").splitlines()[-100:]
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    WHATSAPP_WEBHOOK_REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "webhook_log": str(WHATSAPP_WEBHOOK_LOG_PATH.relative_to(AIOS_ROOT)),
                "webhook_event_count": len(rows),
                "latest_event": rows[-1] if rows else None,
                "entries": rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def evaluate_whatsapp_hosted_test(payload: dict[str, Any]) -> dict[str, Any]:
    text = _whatsapp_text(payload)
    sender = _whatsapp_sender(payload)
    test_id = "WAHOST-" + uuid.uuid4().hex[:12].upper()
    permission = evaluate_permission_api(
        {
            "request": text,
            "channel": "whatsapp",
            "identity_type": payload.get("identity_type") or payload.get("identity") or "Unknown",
            "source": "whatsapp_hosted_ingress_test",
        }
    )
    interaction = process_interaction(
        {
            "channel": "whatsapp",
            "provider": payload.get("provider") or "hosted_runtime_test",
            "from": sender,
            "profile_name": payload.get("ProfileName") or payload.get("profileName") or payload.get("name") or "Hosted Test Contact",
            "text": text,
        }
    )
    external_side_effects = {
        "whatsapp_messages_sent": False,
        "crm_records_written": False,
        "tasks_created": False,
        "calendar_events_created": False,
        "documents_shared": False,
        "provider_webhook_called": False,
    }
    restricted = bool(permission.get("blocked"))
    eye_state = "restricted" if restricted else interaction.get("eye_state", "searching")
    recommended_next_action = (
        "Offer public property, area, project, or process information only."
        if restricted
        else "Wire the WhatsApp provider webhook to this hosted runtime after login approval."
    )
    result = {
        "ok": True,
        "test_id": test_id,
        "tested_at": _now(),
        "route": "/api/whatsapp/hosted-test",
        "channel": "whatsapp",
        "hosted_runtime": True,
        "provider": payload.get("provider") or "hosted_runtime_test",
        "message_received": bool(text),
        "sender_hash": _request_hash(sender),
        "request_hash": _request_hash(text),
        "backend_permission_engine": {
            "used": True,
            "source_of_truth": (permission.get("api") or {}).get("source_of_truth"),
            "decision_id": permission.get("decision_id"),
            "blocked": restricted,
            "eye_state": permission.get("eye_state"),
            "audit_logged": permission.get("audit_logged"),
            "reason": permission.get("reason"),
            "allowed_alternatives": permission.get("allowed_alternatives"),
        },
        "interaction_contract": {
            "identity": (interaction.get("identity") or {}).get("type"),
            "relationship": (interaction.get("relationship_memory") or {}).get("relationship"),
            "intent": (interaction.get("intent") or {}).get("intent"),
            "knowledge_sources": (interaction.get("knowledge_retrieval") or {}).get("sources", []),
            "response_mode": (interaction.get("response_generation") or {}).get("mode"),
        },
        "eye": {
            "state": eye_state,
            "what_happened": "AIOS received a hosted WhatsApp ingress test request.",
            "why": "The runtime evaluated the inbound message through the canonical backend permission engine.",
            "what_aios_is_doing": "Classifying identity, relationship, intent, permission, retrieval path, and Eye state without sending a reply.",
            "recommended_next_action": recommended_next_action,
        },
        "external_side_effects": external_side_effects,
        "reply_delivery": {
            "enabled": False,
            "reason": "Hosted test route validates readiness only. Live provider send remains approval-gated.",
        },
        "public_beta_gate": {
            "backend_ingress_test": "pass",
            "provider_live_connection": "pending_login_or_provider_wiring",
        },
        "audit": {
            "log": str(WHATSAPP_TEST_LOG_PATH.relative_to(AIOS_ROOT)),
            "report": str(WHATSAPP_TEST_REPORT_PATH.relative_to(AIOS_ROOT)),
        },
    }
    _append_whatsapp_test(result)
    return result


def _load_whatsapp_provider_gateway():
    gateway_runtime = AIOS_ROOT / "automation" / "whatsapp_provider_gateway" / "runtime"
    if str(gateway_runtime) not in sys.path:
        sys.path.insert(0, str(gateway_runtime))
    from whatsapp_provider_gateway import process as process_whatsapp_provider

    return process_whatsapp_provider


def evaluate_whatsapp_provider_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    process_whatsapp_provider = _load_whatsapp_provider_gateway()
    provider_output = process_whatsapp_provider(payload)
    event = provider_output.get("provider_event") or {}
    text = str(event.get("message_text") or _whatsapp_text(payload) or "").strip()
    sender = str(event.get("from_phone") or _whatsapp_sender(payload) or "unknown")
    webhook_id = "WAHOOK-" + uuid.uuid4().hex[:12].upper()
    permission = evaluate_permission_api(
        {
            "request": text,
            "channel": "whatsapp",
            "identity_type": "Unknown",
            "source": "whatsapp_provider_webhook",
        }
    )
    interaction = process_interaction(
        {
            "channel": "whatsapp",
            "provider": event.get("provider") or provider_output.get("provider") or "whatsapp_provider",
            "from": sender,
            "profile_name": event.get("profile_name") or "WhatsApp Contact",
            "text": text,
        }
    )
    classification = provider_output.get("classification") or {}
    reply = provider_output.get("reply") or {}
    restricted = bool(permission.get("blocked"))
    hold_delivery = WHATSAPP_REPLY_MODE != "auto" or restricted
    side_effects = {
        "whatsapp_messages_sent": False,
        "crm_records_written": False,
        "tasks_created": False,
        "calendar_events_created": False,
        "documents_shared": False,
        "provider_webhook_called": False,
    }
    result = {
        "ok": True,
        "webhook_id": webhook_id,
        "received_at": _now(),
        "route": WHATSAPP_WEBHOOK_PATH,
        "channel": "whatsapp",
        "hosted_runtime": True,
        "provider": event.get("provider") or "unknown",
        "message_received": bool(text),
        "message_id_hash": _request_hash(str(event.get("message_id") or "")),
        "sender_hash": _request_hash(sender),
        "request_hash": _request_hash(text),
        "backend_permission_engine": {
            "used": True,
            "source_of_truth": (permission.get("api") or {}).get("source_of_truth"),
            "decision_id": permission.get("decision_id"),
            "blocked": restricted,
            "eye_state": permission.get("eye_state"),
            "audit_logged": permission.get("audit_logged"),
            "reason": permission.get("reason"),
            "allowed_alternatives": permission.get("allowed_alternatives"),
        },
        "provider_gateway": {
            "used": True,
            "classification": {
                "category": classification.get("category"),
                "intent": classification.get("intent"),
                "priority": classification.get("priority"),
                "safe_auto_reply": classification.get("safe_auto_reply"),
                "human_takeover_required": classification.get("human_takeover_required"),
                "actionable": classification.get("actionable"),
            },
            "safety_gate": provider_output.get("safety_gate"),
            "reply_mode": reply.get("mode"),
            "reply_text_available": bool(reply.get("text")),
        },
        "interaction_contract": {
            "identity": (interaction.get("identity") or {}).get("type"),
            "intent": (interaction.get("intent") or {}).get("intent"),
            "knowledge_sources": (interaction.get("knowledge_retrieval") or {}).get("sources", []),
        },
        "eye": {
            "state": "restricted" if restricted else interaction.get("eye_state", "searching"),
            "what_happened": "AIOS received a live WhatsApp provider webhook.",
            "why": "The hosted runtime normalized the provider payload and evaluated the request through the backend permission engine.",
            "what_aios_is_doing": "Holding delivery, recording the event, and preparing the next safe action path.",
            "recommended_next_action": "Review and approve live reply delivery mode after provider login and controlled WhatsApp test."
            if hold_delivery
            else "Monitor reply delivery and audit trail after explicit production approval.",
        },
        "reply_delivery": {
            "enabled": False,
            "mode": "hold_for_approval" if hold_delivery else "auto_mode_configured_but_external_send_disabled_here",
            "reason": "Live provider sends remain approval-gated in AIOS Runtime.",
        },
        "external_side_effects": side_effects,
        "public_beta_gate": {
            "backend_ingress_test": "pass",
            "provider_webhook_route": "ready",
            "provider_live_connection": "pending_login_or_provider_wiring",
        },
        "audit": {
            "log": str(WHATSAPP_WEBHOOK_LOG_PATH.relative_to(AIOS_ROOT)),
            "report": str(WHATSAPP_WEBHOOK_REPORT_PATH.relative_to(AIOS_ROOT)),
        },
    }
    _append_whatsapp_webhook(result)
    return result


class AIOSLiveAPIHandler(SimpleHTTPRequestHandler):
    server_version = "AIOSLiveAPI/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(AIOS_ROOT), **kwargs)

    def copyfile(self, source: Any, outputfile: Any) -> None:
        try:
            shutil.copyfileobj(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            return

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        path = _path(getattr(self, "path", ""))
        if not getattr(self, "_aios_skip_cache_header", False) and not path.startswith("/api/") and path != WHATSAPP_WEBHOOK_PATH:
            if path.startswith("/assets/"):
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            elif path == "/aios-service-worker.js":
                self.send_header("Cache-Control", "no-store")
            elif path == "/aios.webmanifest":
                self.send_header("Cache-Control", "no-cache")
            elif path in {"/", "/index.html"} or path.endswith(".html"):
                self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _serve_gzip_static_if_supported(self, path: str) -> bool:
        if "gzip" not in self.headers.get("Accept-Encoding", "").lower():
            return False
        if path == "/":
            relative = Path("index.html")
        else:
            relative = Path(path.lstrip("/"))
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in GZIP_STATIC_SUFFIXES:
            return False
        target = (AIOS_ROOT / relative).resolve()
        try:
            target.relative_to(AIOS_ROOT)
        except ValueError:
            return False
        if not target.is_file():
            return False
        entry = _gzip_static_entry(target)
        if self.headers.get("If-None-Match") == entry["etag"]:
            self.send_response(304)
            self.send_header("ETag", entry["etag"])
            self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            return True
        body = entry["body"]
        self.send_response(200)
        self.send_header("Content-Type", entry["content_type"])
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("ETag", entry["etag"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _webhook_authorized(self) -> bool:
        # Wasender signs inbound POSTs with a shared secret in the
        # X-Webhook-Signature header; accept it when a provider secret is set.
        signature = self.headers.get("X-Webhook-Signature", "").strip()
        if WASENDER_WEBHOOK_SECRET and signature and _constant_time_equal(signature, WASENDER_WEBHOOK_SECRET):
            return True
        token = WHATSAPP_VERIFY_TOKEN
        if not token:
            # No verify token configured -> cannot authorize provider verification.
            return False
        query = _query(self.path)
        supplied = (
            self.headers.get("X-AIOS-Webhook-Token", "")
            or self.headers.get("X-Hub-Signature-Token", "")
            or query.get("hub.verify_token", "")
            or query.get("verify_token", "")
            or query.get("token", "")
        )
        matched = bool(supplied) and _constant_time_equal(str(supplied), token)
        if not matched:
            logger.info(
                "webhook_auth_check: path=%s query_keys=%s token_len=%d supplied_len=%d",
                self.path,
                list(query.keys()),
                len(token),
                len(supplied),
            )
        return matched

    def _authenticated(self) -> bool:
        path = _path(self.path)
        if path == WHATSAPP_WEBHOOK_PATH and self._webhook_authorized():
            return True
        if AUTH_MODE != "basic":
            return True
        if path in {"/api/health", "/api/runtime/status", "/api/deployment/status", "/api/launch/readiness", "/api/client/config"}:
            return True
        if (
            path in PUBLIC_STATIC_PATHS
            or any(path.startswith(prefix) for prefix in PUBLIC_STATIC_PREFIXES)
            or any(path.endswith(suffix) for suffix in PUBLIC_STATIC_SUFFIXES)
        ):
            return True
        if not AUTH_USER or not AUTH_PASSWORD:
            return False
        header = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(f"{AUTH_USER}:{AUTH_PASSWORD}".encode("utf-8")).decode("ascii")
        return header == expected

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        self._aios_skip_cache_header = True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="AIOS"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return False

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = _path(self.path)
        if path == "/":
            self.path = "/AIOS-WEBSITE.html"
            path = "/AIOS-WEBSITE.html"
        if path == WHATSAPP_WEBHOOK_PATH:
            query = _query(self.path)
            mode = query.get("hub.mode") or query.get("mode")
            challenge = query.get("hub.challenge") or query.get("challenge")
            if mode == "subscribe" and challenge and self._webhook_authorized():
                _write_text(self, 200, challenge)
                return
            if mode == "subscribe" and challenge:
                _write_json(
                    self,
                    403,
                    {
                        "ok": False,
                        "error": "webhook_verification_failed",
                        "route": WHATSAPP_WEBHOOK_PATH,
                        "verify_token_configured": bool(WHATSAPP_VERIFY_TOKEN),
                        "message": "AIOS_WHATSAPP_VERIFY_TOKEN is not set in Railway. Set it and retry Wasender verification.",
                    },
                )
                return
            # Status probe for humans / dashboards
            _write_json(
                self,
                200,
                {
                    "ok": True,
                    "route": WHATSAPP_WEBHOOK_PATH,
                    "verify_token_configured": bool(WHATSAPP_VERIFY_TOKEN),
                    "provider_signature_auth_configured": bool(WASENDER_WEBHOOK_SECRET),
                    "auth_mode": AUTH_MODE,
                    "ready_for_provider": bool(WHATSAPP_VERIFY_TOKEN) or bool(WASENDER_WEBHOOK_SECRET),
                    "message": "Webhook route is live. Set AIOS_WHATSAPP_VERIFY_TOKEN to enable provider verification."
                    if not WHATSAPP_VERIFY_TOKEN
                    else "Webhook route is live and verify token is configured.",
                },
            )
            return
        if not self._require_auth():
            return
        if self._serve_gzip_static_if_supported(path):
            return
        if path == "/api/permission/audit":
            _write_json(
                self,
                200,
                {
                    "generated_at": _now(),
                    "audit_log": str(AUDIT_LOG_PATH.relative_to(AIOS_ROOT)),
                    "restricted_decision_count": len(_audit_rows(limit=10000)),
                    "entries": _audit_rows(limit=100),
                },
            )
            return
        if path in {"/api/health", "/api/runtime/status"}:
            _write_json(self, 200, get_runtime_status())
            return
        if path == "/api/deployment/status":
            _write_json(self, 200, get_deployment_status())
            return
        if path == "/api/launch/readiness":
            _write_json(self, 200, get_launch_readiness())
            return
        if path == "/api/client/config":
            _write_json(self, 200, get_client_config())
            return
        if path == "/api/command-center/data":
            _write_command_center_data(self)
            return
        if path == "/api/unit/stats":
            _write_json(self, 200, get_stats())
            return
        super().do_GET()

    def do_POST(self) -> None:
        started = time.perf_counter()
        path = _path(self.path)
        if not self._require_auth():
            return
        if path not in {
            "/api/permission/evaluate",
            "/api/whatsapp/hosted-test",
            WHATSAPP_WEBHOOK_PATH,
            "/api/unit/ingest",
            "/api/property/resolve",
            "/api/unit/enrich",
        }:
            _write_json(self, 404, {"ok": False, "error": "unknown_api_route", "path": path})
            return
        try:
            payload = _read_request_body(self)
            if path == "/api/permission/evaluate":
                decision = evaluate_permission_api(payload)
                decision["api"]["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                _write_json(self, 200, decision)
                return
            if path == "/api/unit/ingest":
                result = ingest(payload)
                result["api"] = {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
                _write_json(self, 200 if result.get("ok") else 400, result)
                return
            if path == "/api/property/resolve":
                result = resolve_property(payload)
                result["api"] = {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
                _write_json(self, 200 if result.get("ok") else 400, result)
                return
            if path == "/api/unit/enrich":
                result = enrich_pending(payload)
                result["api"] = {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
                _write_json(self, 200 if result.get("ok") else 400, result)
                return
            if path == "/api/whatsapp/hosted-test":
                result = evaluate_whatsapp_hosted_test(payload)
            else:
                result = evaluate_whatsapp_provider_webhook(payload)
            result["api"] = {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
            _write_json(self, 200, result)
        except Exception as exc:
            logger.exception("api_error: path=%s", path)
            _write_json(self, 500, {"ok": False, "error": str(exc), "route": path})


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), AIOSLiveAPIHandler)
    print(f"AIOS Runtime serving {AIOS_ROOT} at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAIOS Runtime stopped")
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local AIOS live API server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    return run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
