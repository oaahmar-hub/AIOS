#!/usr/bin/env python3
"""Validate a hosted AIOS Runtime URL.

This is the production gate for public previews and hosted beta candidates.
It checks the deployed HTTP surface, not local files.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_PATH = REPORTS_DIR / "HOSTED_RUNTIME_VALIDATION.json"

STATIC_ROUTES = {
    "website": "AIOS-WEBSITE.html",
    "command_center": "AIOS-DASHBOARD.html?screen=eye",
    "mobile_pwa": "AIOS-MOBILE-APP.html",
    "pwa_manifest": "aios.webmanifest",
    "service_worker": "aios-service-worker.js",
    "offline_shell": "offline.html",
}
EXPECTED_SERVICE_WORKER_CACHE = os.getenv("AIOS_EXPECTED_SERVICE_WORKER_CACHE", "aios-presence-v86")
PUBLIC_WEBSITE_MAX_BYTES = int(os.getenv("AIOS_PUBLIC_WEBSITE_MAX_BYTES", "180000"))
PUBLIC_WEBSITE_MAX_GZIP_BYTES = int(os.getenv("AIOS_PUBLIC_WEBSITE_MAX_GZIP_BYTES", "35000"))
PUBLIC_SERVICE_WORKER_MAX_GZIP_BYTES = int(os.getenv("AIOS_PUBLIC_SERVICE_WORKER_MAX_GZIP_BYTES", "2000"))

REQUIRED_COMPONENTS = {
    "AIOS Live API Server",
    "Router",
    "Permission Runtime",
    "Personality Runtime",
    "Knowledge Runtime",
    "Health Monitor",
}

PERMISSION_CHANNELS = ["whatsapp", "website", "mobile_app", "future_voice"]
WHATSAPP_VERIFY_TOKEN = os.getenv("AIOS_WHATSAPP_VERIFY_TOKEN", "")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("AIOS_VALIDATION_TIMEOUT", "25"))
REQUEST_RETRIES = int(os.getenv("AIOS_VALIDATION_RETRIES", "2"))
COMMAND_CENTER_MAX_WIRE_BYTES = int(os.getenv("AIOS_COMMAND_CENTER_MAX_WIRE_BYTES", "250000"))
COMMAND_CENTER_MAX_UNCOMPRESSED_BYTES = int(os.getenv("AIOS_COMMAND_CENTER_MAX_UNCOMPRESSED_BYTES", "2400000"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth_header(user: str, password: str) -> dict[str, str]:
    if not user and not password:
        return {}
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    auth: dict[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    headers = {"User-Agent": "AIOSHostedRuntimeValidator/1.0"}
    if extra_headers:
        headers.update(extra_headers)
    if auth:
        headers.update(auth)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_result: dict[str, Any] = {}
    attempts = max(1, REQUEST_RETRIES + 1)
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        request = urllib.request.Request(_url(base_url, path), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                wire_bytes = len(raw)
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                content_type = response.headers.get("Content-Type", "")
                parsed = None
                if "application/json" in content_type:
                    parsed = json.loads(raw.decode("utf-8"))
                return {
                    "ok": True,
                    "status": response.status,
                    "url": response.geturl(),
                    "bytes": len(raw),
                    "wire_bytes": wire_bytes,
                    "content_encoding": response.headers.get("Content-Encoding", ""),
                    "cache_control": response.headers.get("Cache-Control", ""),
                    "content_type": content_type,
                    "elapsed_ms": elapsed_ms,
                    "attempt": attempt,
                    "json": parsed,
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return {
                "ok": False,
                "status": exc.code,
                "url": exc.geturl(),
                "bytes": len(raw),
                "content_type": exc.headers.get("Content-Type", ""),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "attempt": attempt,
                "error": raw.decode("utf-8", errors="replace")[:500],
            }
        except Exception as exc:
            last_result = {
                "ok": False,
                "status": 0,
                "url": _url(base_url, path),
                "bytes": 0,
                "content_type": "",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "attempt": attempt,
                "error": str(exc),
            }
            if attempt < attempts:
                time.sleep(min(1.5 * attempt, 4))
    return last_result


def _static_checks(base_url: str, auth: dict[str, str]) -> list[dict[str, Any]]:
    checks = []
    for name, path in STATIC_ROUTES.items():
        result = _request(base_url, path, auth=auth)
        min_bytes = 500 if name in {"pwa_manifest", "service_worker"} else 2_000 if name == "offline_shell" else 5_000
        passed = result["status"] == 200 and result["bytes"] > min_bytes
        extra: dict[str, Any] = {}
        if name == "website":
            passed = passed and result["bytes"] <= PUBLIC_WEBSITE_MAX_BYTES
            extra["max_bytes"] = PUBLIC_WEBSITE_MAX_BYTES
        if name == "service_worker":
            text = ""
            try:
                with urllib.request.urlopen(urllib.request.Request(_url(base_url, path), headers={"Cache-Control": "no-cache"}), timeout=REQUEST_TIMEOUT_SECONDS) as response:
                    text = response.read().decode("utf-8", errors="replace")
            except Exception:
                text = ""
            shell = text.split("const AIOS_SHELL", 1)[1].split("];", 1)[0] if "const AIOS_SHELL" in text else ""
            actual_cache = EXPECTED_SERVICE_WORKER_CACHE if EXPECTED_SERVICE_WORKER_CACHE in text else ""
            protected_precache = any(item in shell for item in ["AIOS-DASHBOARD.html", "AIOS-MOBILE-APP.html", "AIOS-RUNTIME-STATUS.html"])
            eye_video_precache = "aios-eye-cinematic-loop-" in shell
            protected_runtime_excluded = "AIOS_PROTECTED_PATHS" in text and text.count("!AIOS_PROTECTED_PATHS.has(url.pathname)") >= 2
            passed = passed and actual_cache == EXPECTED_SERVICE_WORKER_CACHE and not protected_precache and not eye_video_precache and protected_runtime_excluded
            extra.update(
                {
                    "expected_cache": EXPECTED_SERVICE_WORKER_CACHE,
                    "cache_version_match": actual_cache == EXPECTED_SERVICE_WORKER_CACHE,
                    "cache_control": result.get("cache_control"),
                    "cache_control_no_store": result.get("cache_control") == "no-store",
                    "protected_precache": protected_precache,
                    "protected_runtime_cache_excluded": protected_runtime_excluded,
                    "eye_video_precache": eye_video_precache,
                }
            )
            passed = passed and result.get("cache_control") == "no-store"
        checks.append(
            {
                "name": name,
                "path": path,
                "passed": passed,
                "status": result["status"],
                "bytes": result["bytes"],
                "elapsed_ms": result["elapsed_ms"],
                "url": result["url"],
                **extra,
            }
        )
    return checks


def _public_gzip_delivery_checks(base_url: str) -> list[dict[str, Any]]:
    checks = []
    budgets = {
        "website_gzip_delivery": ("AIOS-WEBSITE.html", PUBLIC_WEBSITE_MAX_GZIP_BYTES),
        "service_worker_gzip_delivery": ("aios-service-worker.js", PUBLIC_SERVICE_WORKER_MAX_GZIP_BYTES),
    }
    for name, (path, budget) in budgets.items():
        result = _request(base_url, path, extra_headers={"Accept-Encoding": "gzip"})
        checks.append(
            {
                "name": name,
                "path": path,
                "passed": result["status"] == 200
                and result.get("content_encoding") == "gzip"
                and int(result.get("wire_bytes") or 0) <= budget,
                "status": result["status"],
                "content_encoding": result.get("content_encoding"),
                "wire_bytes": result.get("wire_bytes"),
                "wire_bytes_budget": budget,
                "uncompressed_bytes": result.get("bytes"),
                "elapsed_ms": result["elapsed_ms"],
            }
        )
    return checks


def _health_check(base_url: str) -> dict[str, Any]:
    result = _request(base_url, "/api/health")
    payload = result.get("json") or {}
    components = {item.get("name") for item in payload.get("components", [])}
    missing_components = sorted(REQUIRED_COMPONENTS - components)
    checks = payload.get("auto_start_checks", [])
    blocked_items = payload.get("blocked_items", [])
    passed = (
        result["status"] == 200
        and payload.get("status") == "ready"
        and payload.get("runtime_ready") is True
        and payload.get("runtime_ready_percent") == 100
        and not missing_components
        and all(item.get("passed") is True for item in checks)
        and not blocked_items
    )
    return {
        "name": "health",
        "passed": passed,
        "status": result["status"],
        "runtime_status": payload.get("status"),
        "runtime_ready": payload.get("runtime_ready"),
        "runtime_ready_percent": payload.get("runtime_ready_percent"),
        "production_ready_percent": payload.get("production_ready_percent"),
        "health_endpoint": payload.get("health_endpoint"),
        "components_seen": sorted(component for component in components if component),
        "missing_components": missing_components,
        "auto_start_checks": checks,
        "blocked_items": blocked_items,
        "elapsed_ms": result["elapsed_ms"],
    }


def _runtime_status_check(base_url: str) -> dict[str, Any]:
    result = _request(base_url, "/api/runtime/status")
    payload = result.get("json") or {}
    return {
        "name": "runtime_status",
        "passed": result["status"] == 200 and payload.get("status") == "ready",
        "status": result["status"],
        "runtime_status": payload.get("status"),
        "permission_endpoint": payload.get("permission_endpoint"),
        "audit_endpoint": payload.get("audit_endpoint"),
        "mac_dependency": payload.get("mac_dependency"),
        "elapsed_ms": result["elapsed_ms"],
    }


def _deployment_status_check(base_url: str) -> dict[str, Any]:
    result = _request(base_url, "/api/deployment/status")
    payload = result.get("json") or {}
    return {
        "name": "deployment_status",
        "passed": result["status"] == 200
        and payload.get("runtime_ready") is True
        and payload.get("runtime_ready_percent") == 100
        and payload.get("production_deployment") in {"pending", "ready"}
        and payload.get("public_beta_ready") in {False, True}
        and payload.get("eye_motion") in {"pass", "pending_or_failed"}
        and payload.get("health_endpoint") == "/api/health",
        "status": result["status"],
        "runtime_ready": payload.get("runtime_ready"),
        "runtime_ready_percent": payload.get("runtime_ready_percent"),
        "production_deployment": payload.get("production_deployment"),
        "public_beta_ready": payload.get("public_beta_ready"),
        "temporary_preview": payload.get("temporary_preview"),
        "hosted_backend": payload.get("hosted_backend"),
        "hosted_frontend": payload.get("hosted_frontend"),
        "auth_status": payload.get("auth_status"),
        "domain": payload.get("domain"),
        "whatsapp_hosted_test": payload.get("whatsapp_hosted_test"),
        "whatsapp_live_provider": payload.get("whatsapp_live_provider"),
        "eye_motion": payload.get("eye_motion"),
        "eye_motion_checks": payload.get("eye_motion_checks"),
        "elapsed_ms": result["elapsed_ms"],
    }


def _launch_readiness_check(base_url: str) -> dict[str, Any]:
    result = _request(base_url, "/api/launch/readiness")
    payload = result.get("json") or {}
    return {
        "name": "launch_readiness",
        "passed": result["status"] == 200
        and payload.get("runtime_ready") is True
        and payload.get("runtime_ready_percent") == 100
        and payload.get("production_deployment") in {"pending", "ready"}
        and payload.get("public_beta_ready") in {False, True}
        and isinstance(payload.get("blockers"), list)
        and payload.get("endpoint") == "/api/launch/readiness",
        "status": result["status"],
        "runtime_ready": payload.get("runtime_ready"),
        "runtime_ready_percent": payload.get("runtime_ready_percent"),
        "production_deployment": payload.get("production_deployment"),
        "public_beta_ready": payload.get("public_beta_ready"),
        "launch_status": payload.get("status"),
        "blocker_count": len(payload.get("blockers") or []),
        "elapsed_ms": result["elapsed_ms"],
    }


def _command_center_data_check(base_url: str, auth: dict[str, str]) -> dict[str, Any]:
    result = _request(base_url, "/api/command-center/data", auth=auth, extra_headers={"Accept-Encoding": "gzip"})
    payload = result.get("json") or {}
    search_count = len(payload.get("search_index") or [])
    workflow_count = len(payload.get("workflows") or [])
    api = payload.get("api") or {}
    return {
        "name": "command_center_data_api",
        "passed": result["status"] == 200
        and search_count >= 100
        and workflow_count >= 10
        and api.get("route") == "/api/command-center/data"
        and result.get("content_encoding") == "gzip"
        and result.get("wire_bytes", result.get("bytes", 0)) < result.get("bytes", 0)
        and int(result.get("wire_bytes") or 0) <= COMMAND_CENTER_MAX_WIRE_BYTES
        and int(result.get("bytes") or 0) <= COMMAND_CENTER_MAX_UNCOMPRESSED_BYTES,
        "status": result["status"],
        "search_records": search_count,
        "workflow_records": workflow_count,
        "api_route": api.get("route"),
        "content_encoding": result.get("content_encoding"),
        "wire_bytes": result.get("wire_bytes"),
        "wire_bytes_budget": COMMAND_CENTER_MAX_WIRE_BYTES,
        "uncompressed_bytes": result.get("bytes"),
        "uncompressed_bytes_budget": COMMAND_CENTER_MAX_UNCOMPRESSED_BYTES,
        "compression_ratio": round((result.get("wire_bytes") or 0) / max(int(result.get("bytes") or 1), 1), 4),
        "elapsed_ms": result["elapsed_ms"],
    }


def _webhook_auth() -> dict[str, str]:
    return {"X-AIOS-Webhook-Token": WHATSAPP_VERIFY_TOKEN} if WHATSAPP_VERIFY_TOKEN else {}


def _permission_checks(base_url: str, auth: dict[str, str]) -> list[dict[str, Any]]:
    checks = []
    decisions = []
    for channel in PERMISSION_CHANNELS:
        result = _request(
            base_url,
            "/api/permission/evaluate",
            method="POST",
            payload={
                "request": "Give me owner phone number",
                "channel": channel,
                "identity_type": "Unknown",
                "source": "hosted_runtime_validation",
            },
            auth=auth,
        )
        payload = result.get("json") or {}
        decision = {
            "channel": channel,
            "status": result["status"],
            "blocked": payload.get("blocked"),
            "eye_state": payload.get("eye_state"),
            "source_of_truth": (payload.get("api") or {}).get("source_of_truth"),
            "audit_logged": payload.get("audit_logged"),
            "hits": payload.get("hits", []),
            "elapsed_ms": result["elapsed_ms"],
        }
        decisions.append(decision)
    same_result = len({json.dumps({k: d.get(k) for k in ["blocked", "eye_state", "source_of_truth"]}, sort_keys=True) for d in decisions}) == 1
    checks.append(
        {
            "name": "permission_api_restricted_consistency",
            "passed": same_result
            and all(d["status"] == 200 for d in decisions)
            and all(d["blocked"] is True for d in decisions)
            and all(d["eye_state"] == "restricted" for d in decisions)
            and all(d["source_of_truth"] == "backend" for d in decisions)
            and all(d["audit_logged"] is True for d in decisions),
            "same_result_everywhere": same_result,
            "decisions": decisions,
        }
    )
    audit = _request(base_url, "/api/permission/audit", auth=auth)
    payload = audit.get("json") or {}
    checks.append(
        {
            "name": "permission_audit_trail",
            "passed": audit["status"] == 200 and int(payload.get("restricted_decision_count") or 0) >= len(PERMISSION_CHANNELS),
            "status": audit["status"],
            "restricted_decision_count": payload.get("restricted_decision_count"),
            "elapsed_ms": audit["elapsed_ms"],
        }
    )
    return checks


def _auth_protection_checks(base_url: str, auth: dict[str, str]) -> list[dict[str, Any]]:
    if not auth:
        return []
    public_root = _request(base_url, "/")
    public_website = _request(base_url, "AIOS-WEBSITE.html")
    public_manifest = _request(base_url, "aios.webmanifest")
    public_service_worker = _request(base_url, "aios-service-worker.js")
    protected_get = _request(base_url, "AIOS-DASHBOARD.html?screen=eye")
    protected_api = _request(
        base_url,
        "/api/permission/evaluate",
        method="POST",
        payload={"request": "Give me owner phone number", "channel": "website"},
    )
    protected_audit = _request(base_url, "/api/permission/audit")
    protected_whatsapp_test = _request(
        base_url,
        "/api/whatsapp/hosted-test",
        method="POST",
        payload={"Body": "Hi Omar", "From": "whatsapp:+971555111222"},
    )
    public_health = _request(base_url, "/api/health")
    webhook_checks: list[dict[str, Any]] = []
    if WHATSAPP_VERIFY_TOKEN:
        challenge = "AIOS_WEBHOOK_AUTH_OK"
        webhook_challenge = _request(
            base_url,
            f"/webhook/whatsapp/provider/gateway?hub.mode=subscribe&hub.verify_token={WHATSAPP_VERIFY_TOKEN}&hub.challenge={challenge}",
        )
        webhook_without_token = _request(
            base_url,
            "/webhook/whatsapp/provider/gateway",
            method="POST",
            payload={"Body": "Hi Omar", "From": "whatsapp:+971555111222"},
        )
        webhook_checks.extend(
            [
                {
                    "name": "auth:webhook_token_allows_provider_challenge",
                    "passed": webhook_challenge["status"] == 200 and webhook_challenge["bytes"] == len(challenge),
                    "status": webhook_challenge["status"],
                    "bytes": webhook_challenge["bytes"],
                    "elapsed_ms": webhook_challenge["elapsed_ms"],
                },
                {
                    "name": "auth:webhook_without_token_rejected",
                    "passed": webhook_without_token["status"] in {401, 403},
                    "status": webhook_without_token["status"],
                    "elapsed_ms": webhook_without_token["elapsed_ms"],
                },
            ]
        )
    checks = [
        {
            "name": "auth:root_landing_without_credentials_public",
            "passed": public_root["status"] == 200 and public_root["bytes"] > 5000,
            "status": public_root["status"],
            "bytes": public_root["bytes"],
            "elapsed_ms": public_root["elapsed_ms"],
        },
        {
            "name": "auth:website_without_credentials_public",
            "passed": public_website["status"] == 200 and public_website["bytes"] > 5000,
            "status": public_website["status"],
            "bytes": public_website["bytes"],
            "elapsed_ms": public_website["elapsed_ms"],
        },
        {
            "name": "auth:pwa_manifest_without_credentials_public",
            "passed": public_manifest["status"] == 200 and public_manifest["bytes"] > 500,
            "status": public_manifest["status"],
            "bytes": public_manifest["bytes"],
            "elapsed_ms": public_manifest["elapsed_ms"],
        },
        {
            "name": "auth:service_worker_without_credentials_public",
            "passed": public_service_worker["status"] == 200 and public_service_worker["bytes"] > 500,
            "status": public_service_worker["status"],
            "bytes": public_service_worker["bytes"],
            "elapsed_ms": public_service_worker["elapsed_ms"],
        },
        {
            "name": "auth:command_center_without_credentials_rejected",
            "passed": protected_get["status"] == 401,
            "status": protected_get["status"],
            "elapsed_ms": protected_get["elapsed_ms"],
        },
        {
            "name": "auth:permission_api_without_credentials_rejected",
            "passed": protected_api["status"] == 401,
            "status": protected_api["status"],
            "elapsed_ms": protected_api["elapsed_ms"],
        },
        {
            "name": "auth:audit_without_credentials_rejected",
            "passed": protected_audit["status"] == 401,
            "status": protected_audit["status"],
            "elapsed_ms": protected_audit["elapsed_ms"],
        },
        {
            "name": "auth:hosted_test_without_credentials_rejected",
            "passed": protected_whatsapp_test["status"] == 401,
            "status": protected_whatsapp_test["status"],
            "elapsed_ms": protected_whatsapp_test["elapsed_ms"],
        },
        {
            "name": "auth:health_remains_public",
            "passed": public_health["status"] == 200,
            "status": public_health["status"],
            "elapsed_ms": public_health["elapsed_ms"],
        },
    ]
    checks.extend(webhook_checks)
    return checks


def _whatsapp_hosted_test(base_url: str, auth: dict[str, str]) -> dict[str, Any]:
    result = _request(
        base_url,
        "/api/whatsapp/hosted-test",
        method="POST",
        payload={
            "provider": "hosted_runtime_validation",
            "SmsMessageSid": "SM-HOSTED-VALIDATION-001",
            "From": "whatsapp:+971555111222",
            "To": "whatsapp:+971555593714",
            "ProfileName": "Hosted Test Buyer",
            "Body": "Hi Omar, looking for a 2 bedroom in Dubai Marina, budget 2.5m.",
        },
        auth=auth,
    )
    payload = result.get("json") or {}
    permission = payload.get("backend_permission_engine") or {}
    side_effects = payload.get("external_side_effects") or {}
    public_gate = payload.get("public_beta_gate") or {}
    return {
        "name": "whatsapp_hosted_ingress_test",
        "passed": result["status"] == 200
        and payload.get("ok") is True
        and payload.get("channel") == "whatsapp"
        and payload.get("hosted_runtime") is True
        and permission.get("used") is True
        and permission.get("source_of_truth") == "backend"
        and all(value is False for value in side_effects.values())
        and public_gate.get("backend_ingress_test") == "pass",
        "status": result["status"],
        "message_received": payload.get("message_received"),
        "eye_state": (payload.get("eye") or {}).get("state"),
        "permission_source": permission.get("source_of_truth"),
        "provider_live_connection": public_gate.get("provider_live_connection"),
        "external_side_effects": side_effects,
        "elapsed_ms": result["elapsed_ms"],
    }


def _whatsapp_provider_webhook_check(base_url: str, auth: dict[str, str]) -> dict[str, Any]:
    webhook_auth = _webhook_auth() or auth
    result = _request(
        base_url,
        "/webhook/whatsapp/provider/gateway",
        method="POST",
        payload={
            "provider": "hosted_runtime_validation",
            "SmsMessageSid": "SM-PROVIDER-WEBHOOK-VALIDATION-001",
            "From": "whatsapp:+971555111222",
            "To": "whatsapp:+971555593714",
            "ProfileName": "Hosted Test Buyer",
            "Body": "Hi Omar, looking for a 2 bedroom in Dubai Marina, budget 2.5m.",
        },
        auth=webhook_auth,
    )
    payload = result.get("json") or {}
    permission = payload.get("backend_permission_engine") or {}
    gateway = payload.get("provider_gateway") or {}
    delivery = payload.get("reply_delivery") or {}
    side_effects = payload.get("external_side_effects") or {}
    public_gate = payload.get("public_beta_gate") or {}
    return {
        "name": "whatsapp_provider_webhook_route",
        "passed": result["status"] == 200
        and payload.get("ok") is True
        and payload.get("route") == "/webhook/whatsapp/provider/gateway"
        and payload.get("channel") == "whatsapp"
        and permission.get("used") is True
        and permission.get("source_of_truth") == "backend"
        and gateway.get("used") is True
        and delivery.get("enabled") is False
        and all(value is False for value in side_effects.values())
        and public_gate.get("provider_webhook_route") == "ready",
        "status": result["status"],
        "message_received": payload.get("message_received"),
        "eye_state": (payload.get("eye") or {}).get("state"),
        "permission_source": permission.get("source_of_truth"),
        "gateway_used": gateway.get("used"),
        "reply_delivery_enabled": delivery.get("enabled"),
        "provider_live_connection": public_gate.get("provider_live_connection"),
        "external_side_effects": side_effects,
        "elapsed_ms": result["elapsed_ms"],
    }


def _whatsapp_webhook_verification_check(base_url: str, auth: dict[str, str]) -> dict[str, Any]:
    challenge = "AIOS_VERIFY_OK"
    token = WHATSAPP_VERIFY_TOKEN or "local-preview-token"
    result = _request(
        base_url,
        f"/webhook/whatsapp/provider/gateway?hub.mode=subscribe&hub.verify_token={token}&hub.challenge={challenge}",
        auth=auth if not WHATSAPP_VERIFY_TOKEN else None,
    )
    return {
        "name": "whatsapp_webhook_verification",
        "passed": result["status"] == 200 and result["bytes"] == len(challenge),
        "status": result["status"],
        "challenge_bytes": result["bytes"],
        "verify_token_configured": bool(WHATSAPP_VERIFY_TOKEN),
        "elapsed_ms": result["elapsed_ms"],
    }


def validate(base_url: str, user: str = "", password: str = "") -> dict[str, Any]:
    auth = _auth_header(user, password)
    static_checks = _static_checks(base_url, auth)
    public_gzip_checks = _public_gzip_delivery_checks(base_url)
    health = _health_check(base_url)
    runtime_status = _runtime_status_check(base_url)
    deployment_status = _deployment_status_check(base_url)
    launch_readiness = _launch_readiness_check(base_url)
    command_center_data = _command_center_data_check(base_url, auth)
    permission_checks = _permission_checks(base_url, auth)
    whatsapp_test = _whatsapp_hosted_test(base_url, auth)
    whatsapp_verification = _whatsapp_webhook_verification_check(base_url, auth)
    whatsapp_webhook = _whatsapp_provider_webhook_check(base_url, auth)
    auth_checks = _auth_protection_checks(base_url, auth)
    checks = static_checks + public_gzip_checks + [health, runtime_status, deployment_status, launch_readiness, command_center_data] + permission_checks + [whatsapp_test, whatsapp_verification, whatsapp_webhook] + auth_checks
    passed = all(item.get("passed") is True for item in checks)
    auth_checks_only = [item for item in auth_checks if str(item.get("name", "")).startswith("auth:")]
    auth_ready = bool(auth) and bool(auth_checks_only) and all(item.get("passed") is True for item in auth_checks_only)
    whatsapp_ready = whatsapp_test.get("passed") is True and whatsapp_verification.get("passed") is True and whatsapp_webhook.get("passed") is True
    hosted_surface_ready = (
        passed
        and health.get("passed") is True
        and runtime_status.get("passed") is True
        and deployment_status.get("hosted_backend") == "validated"
        and deployment_status.get("hosted_frontend") == "validated"
    )
    custom_domain_ready = "railway.app" not in base_url.lower()
    production_beta_blockers = []
    if not hosted_surface_ready:
        production_beta_blockers.append("Hosted backend/frontend validation did not pass.")
    if not custom_domain_ready:
        production_beta_blockers.append("Attach custom domain.")
    if not auth_ready:
        production_beta_blockers.append("Production authentication checks did not pass.")
    if not whatsapp_ready:
        production_beta_blockers.append("Hosted WhatsApp ingress, verification, or provider webhook checks did not pass.")
    report = {
        "validated_at": _now(),
        "base_url": base_url.rstrip("/"),
        "auth_mode": "basic" if auth else "none",
        "passed": passed,
        "hosted_surface_ready": hosted_surface_ready,
        "checks_passed": sum(1 for item in checks if item.get("passed") is True),
        "checks_total": len(checks),
        "checks": checks,
        "production_beta_ready": not production_beta_blockers,
        "production_beta_blockers": production_beta_blockers,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a hosted AIOS Runtime URL.")
    parser.add_argument("base_url", help="Hosted AIOS base URL, e.g. https://aios.example.com")
    parser.add_argument("--user", default=os.getenv("AIOS_BASIC_AUTH_USER", ""))
    parser.add_argument("--password", default=os.getenv("AIOS_BASIC_AUTH_PASSWORD", ""))
    args = parser.parse_args()
    report = validate(args.base_url, user=args.user, password=args.password)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
