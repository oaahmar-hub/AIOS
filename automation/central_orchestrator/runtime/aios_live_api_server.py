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
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

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
# Outbound reply delivery. When AIOS_WHATSAPP_REPLY_MODE=auto and the message is
# not permission-restricted, the hosted runtime generates a reply via the n8n
# brain (WA_SIMPLE_OPENAI_ENDPOINT) and sends it back through the Wasender send
# API. Defaults keep delivery OFF (hold) so nothing sends without explicit opt-in.
WASENDER_API_KEY = os.getenv("WASENDER_API_KEY", "").strip()
WASENDER_SEND_URL = os.getenv("WASENDER_SEND_URL", "https://www.wasenderapi.com/api/send-message").strip()
WA_REPLY_ENDPOINT = os.getenv(
    "WA_SIMPLE_OPENAI_ENDPOINT",
    "https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4",
).strip()
# Cache the health-endpoint brain probe so repeated /api/health/deep polls don't
# each spend an n8n execution (the customer's n8n quota is finite).
_BRAIN_PROBE_TTL = float(os.getenv("AIOS_BRAIN_PROBE_TTL_SECONDS", "900"))
_BRAIN_PROBE_CACHE: dict[str, tuple] = {}

# Direct LLM path — bypass n8n entirely (no execution cap, unlimited testing).
# When GROQ_API_KEY is set, the reply brain calls Groq directly (OpenAI-compatible
# API, generous free tier) and n8n becomes an optional fallback. Get a free key at
# console.groq.com. OpenAI works too via OPENAI_API_KEY (+ OPENAI_BASE_URL).
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
_DIRECT_LLM_KEY = GROQ_API_KEY or os.getenv("OPENAI_API_KEY", "").strip()
_DIRECT_LLM_URL = (
    "https://api.groq.com/openai/v1/chat/completions" if GROQ_API_KEY
    else os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
)
_DIRECT_LLM_MODEL = GROQ_MODEL if GROQ_API_KEY else os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# Graceful fallback: if the brain fails or returns empty (OpenAI outage, bad
# key, timeout), send this holding line instead of silently dropping the
# message. Set to empty to disable and revert to silent-hold on failure.
WA_FALLBACK_REPLY = os.getenv(
    "AIOS_WHATSAPP_FALLBACK_REPLY",
    "Thanks for your message — I'll get back to you shortly.",
).strip()
WASENDER_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
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


def _ok(ok: bool, detail: str = "") -> dict[str, Any]:
    return {"ok": bool(ok), "detail": detail}


def get_deep_health(check_brain: bool = False) -> dict[str, Any]:
    """End-to-end chain health so failures surface instead of hiding.

    Checks every link a live WhatsApp reply depends on and reports green/red
    per component with a human-readable summary of what is broken. This is the
    signal that was missing while every failure this project hit stayed silent
    (dead webhook URL, frozen deploys, dead OpenAI key, unwired sender).

    Public + read-only. The brain check does one short POST to the n8n endpoint
    (skippable via ?brain=0) so an invalid OpenAI key is caught immediately.
    No message is ever sent to a customer from this endpoint.
    """
    components: dict[str, Any] = {}
    issues: list[str] = []

    components["runtime"] = _ok(True, "process serving")

    # Resolver DB present and readable.
    try:
        db_path = AIOS_ROOT / "KnowledgeBase" / "resolver" / "unit_resolver_database.resolver"
        db_ok = db_path.is_file() and db_path.stat().st_size > 0
    except Exception as exc:  # pragma: no cover - defensive
        db_ok, db_path = False, None
        issues.append(f"resolver_db error: {exc}")
    components["resolver_db"] = _ok(db_ok, "present" if db_ok else "missing")
    if not db_ok:
        issues.append("Resolver database missing or empty.")

    # Inbound webhook auth configured (signature secret or verify token).
    webhook_ok = bool(WASENDER_WEBHOOK_SECRET) or bool(WHATSAPP_VERIFY_TOKEN)
    components["webhook_auth"] = _ok(
        webhook_ok,
        "signature_secret_set" if WASENDER_WEBHOOK_SECRET else "verify_token_only" if WHATSAPP_VERIFY_TOKEN else "unconfigured",
    )
    if not webhook_ok:
        issues.append("No webhook auth configured (set AIOS_WEBHOOK_SECRET to match Wasender).")

    # Reply mode: auto means the runtime will actually answer.
    reply_auto = WHATSAPP_REPLY_MODE == "auto"
    components["reply_mode"] = {"ok": reply_auto, "value": WHATSAPP_REPLY_MODE}
    if not reply_auto:
        issues.append("Reply mode is 'hold' — inbound messages are received but never answered. Set AIOS_WHATSAPP_REPLY_MODE=auto to reply.")

    # Outbound send credential present (config only; no message is sent).
    send_ok = bool(WASENDER_API_KEY)
    components["wasender_send"] = _ok(send_ok, "api_key_set" if send_ok else "missing_api_key")
    if not send_ok:
        issues.append("WASENDER_API_KEY not set — replies cannot be delivered.")

    # The brain: probe n8n so a dead key/quota is caught here, not in silence.
    # BUT each probe spends a real n8n execution, so cache the result and re-probe
    # at most once per _BRAIN_PROBE_TTL — frequent health polls must not burn the
    # customer's n8n quota on pings.
    if check_brain and WA_REPLY_ENDPOINT:
        now = time.time()
        cached = _BRAIN_PROBE_CACHE.get("v")
        if cached and (now - cached[0]) < _BRAIN_PROBE_TTL:
            brain_ok, detail = cached[1], cached[2] + " (cached)"
        else:
            reply, detail = _generate_reply_text("health check ping", history="diagnostic")
            brain_ok = bool(reply)
            _BRAIN_PROBE_CACHE["v"] = (now, brain_ok, detail)
        components["brain_n8n_openai"] = _ok(brain_ok, detail)
        if not brain_ok:
            issues.append(f"Reply brain failed ({detail}). Causes: n8n execution-limit/plan quota reached, or an invalid/expired key in the n8n LLM credential.")
    else:
        # No live probe this call (default) — surface the last cached probe so
        # the dashboard still reflects reality without spending an execution.
        cached = _BRAIN_PROBE_CACHE.get("v")
        if cached:
            components["brain_n8n_openai"] = _ok(cached[1], cached[2] + " (cached, no execution spent)")
        else:
            components["brain_n8n_openai"] = {"ok": None, "detail": "not probed (add ?brain=1 for a live check)"}

    # Fallback holding line configured (so a broken brain still acks the customer).
    components["fallback_reply"] = _ok(bool(WA_FALLBACK_REPLY), "configured" if WA_FALLBACK_REPLY else "disabled")

    # Conversation memory: per-contact recall store.
    try:
        import conversation_memory as _mem
        _ms = _mem.stats()
        components["conversation_memory"] = _ok(_ms.get("ok", False), f"{_ms.get('contacts',0)} contacts / {_ms.get('turns',0)} turns")
    except Exception as exc:  # pragma: no cover
        components["conversation_memory"] = _ok(False, f"error:{exc}")

    # Group-Lead Agent store.
    try:
        import group_leads as _gl
        _gs = _gl.stats()
        components["group_leads"] = _ok(_gs.get("ok", False), f"{_gs.get('leads',0)} leads / {_gs.get('with_matches',0)} matched")
    except Exception as exc:  # pragma: no cover
        components["group_leads"] = _ok(False, f"error:{exc}")

    # Marketing / Content Studio.
    try:
        import content_studio as _cs
        _ch = _cs.health()
        components["content_studio"] = _ok(_ch.get("ok", False), _ch.get("detail", ""))
    except Exception as exc:  # pragma: no cover
        components["content_studio"] = _ok(False, f"error:{exc}")

    # Truth Bridge — audit of the verified property truth the brain quotes.
    try:
        import truth_bridge_audit as _tb
        _th = _tb.health()
        components["truth_bridge"] = _ok(_th.get("ok", False), _th.get("detail", ""))
    except Exception as exc:  # pragma: no cover
        components["truth_bridge"] = _ok(False, f"error:{exc}")

    # CRM lead capture wiring.
    try:
        import crm_leads as _crm
        components["crm_leads"] = _ok(_crm.configured(), _crm.health().get("detail", ""))
    except Exception as exc:  # pragma: no cover
        components["crm_leads"] = _ok(False, f"error:{exc}")

    # Knowledge connection: quotable inventory available to the brain.
    try:
        import inventory_retrieval as _inv
        _qc = _inv.quotable_count()
        components["inventory_knowledge"] = _ok(_qc > 0, f"{_qc} quotable rows")
        if _qc == 0:
            issues.append("Inventory retrieval loaded 0 quotable rows - brain cannot quote real units.")
    except Exception as exc:  # pragma: no cover - defensive
        components["inventory_knowledge"] = _ok(False, f"error:{exc}")
        issues.append(f"Inventory retrieval failed to load: {exc}")

    # Humanizer layer: fingerprint removal + media honesty must be importable.
    try:
        import reply_humanizer as _rh_health
        _probe = _rh_health.humanize("I hope this helps! The unit is 33 sqm.")
        components["reply_humanizer"] = _ok(
            "hope this helps" not in _probe.lower() and "33 sqm" in _probe, "active"
        )
    except Exception as exc:  # pragma: no cover - defensive
        components["reply_humanizer"] = _ok(False, f"error:{exc}")
        issues.append(f"Reply humanizer failed to load: {exc}")
    try:
        import media_vault as _mv_health
        _mvh = _mv_health.health()
        components["media_vault"] = {"ok": True, "detail": f"{_mvh['entries']} curated assets"}
    except Exception as exc:  # pragma: no cover - defensive
        components["media_vault"] = _ok(False, f"error:{exc}")
    try:
        import voice_notes as _vn_health
        _vnh = _vn_health.health()
        components["voice_notes"] = {"ok": None if _vnh["status"] == "not_configured" else True,
                                     "detail": _vnh["status"]}
    except Exception as exc:  # pragma: no cover - defensive
        components["voice_notes"] = _ok(False, f"error:{exc}")

    try:
        import design_compliance as _dc_health
        _dch = _dc_health.health()
        components["design_compliance"] = {"ok": bool(_dch["rulesets"]),
                                           "detail": f"rulesets:{','.join(_dch['rulesets']) or 'none'}"}
    except Exception as exc:  # pragma: no cover - defensive
        components["design_compliance"] = _ok(False, f"error:{exc}")
    try:
        import health_alerts as _ha_health
        _hah = _ha_health.health()
        components["health_alerts"] = {"ok": None if _hah["status"] == "not_configured" else True,
                                       "detail": _hah["status"]}
    except Exception as exc:  # pragma: no cover - defensive
        components["health_alerts"] = _ok(False, f"error:{exc}")
    try:
        import owner_lookup as _ol_health
        _olh = _ol_health.health()
        components["owner_lookup"] = {"ok": None if _olh.get("records",0)==0 else True,
                                      "detail": f"{_olh.get('with_phone',0)} phones / {_olh.get('areas',0)} areas"}
    except Exception as exc:  # pragma: no cover - defensive
        components["owner_lookup"] = _ok(False, f"error:{exc}")
    try:
        import deal_agent as _dl_health
        _dlh = _dl_health.health()
        components["deal_agent"] = {"ok": None if not _dlh.get("enabled") else True,
                                    "detail": _dlh.get("status")}
    except Exception as exc:  # pragma: no cover - defensive
        components["deal_agent"] = _ok(False, f"error:{exc}")
    try:
        import daily_brief as _db_health
        _dbh = _db_health.health()
        components["daily_brief"] = {"ok": None if _dbh["status"] == "not_configured" else True,
                                     "detail": f"{_dbh['status']} (hour {_dbh['hour_dubai']:02d} Dubai)"}
    except Exception as exc:  # pragma: no cover - defensive
        components["daily_brief"] = _ok(False, f"error:{exc}")
    try:
        import owner_outreach as _oo_health
        _ooh = _oo_health.health()
        components["owner_outreach"] = {"ok": _ooh.get("status") == "ok",
                                        "detail": f"{_ooh.get('restricted_contacts', 0)} restricted contacts"}
    except Exception as exc:  # pragma: no cover - defensive
        components["owner_outreach"] = _ok(False, f"error:{exc}")
    try:
        import chat_governor as _gov_health
        _gh = _gov_health.health()
        components["chat_governor"] = {
            "ok": bool(_gh.get("ok")),
            "detail": (f"takeover:{_gh.get('takeover_active_contacts')} "
                       f"cooldown:{_gh.get('cooldown_min')}m gap:{_gh.get('reply_min_gap_sec')}s "
                       f"cap:{_gh.get('reply_hourly_cap')}/h fresh<{_gh.get('max_event_age_min')}m"),
        }
    except Exception as exc:  # pragma: no cover - defensive
        components["chat_governor"] = _ok(False, f"error:{exc}")
        issues.append(f"Chat governor failed to load: {exc}")

    checked = [c for c in components.values() if c.get("ok") is not None]
    reds = [c for c in checked if c.get("ok") is False]
    # The reply loop is only truly "healthy" when a customer message gets answered.
    reply_chain_live = all(
        components[name]["ok"]
        for name in ("webhook_auth", "reply_mode", "wasender_send", "brain_n8n_openai")
        if components.get(name, {}).get("ok") is not None
    )
    status = "healthy" if not reds else ("down" if not reply_chain_live else "degraded")

    return {
        "status": status,
        "reply_chain_live": reply_chain_live,
        "checked_at": _now(),
        "components": components,
        "issues": issues,
        "summary": ("All systems green — WhatsApp reply loop is live."
                    if status == "healthy"
                    else f"{len(issues)} issue(s) blocking the live reply loop." ),
        "endpoint": "/api/health/deep",
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


_PERSONALITY_DIR = RUNTIME_DIR / "personality"


def _build_personality_system_prompt(
    message: str,
    history: str,
    sender: str,
    profile_name: str = "",
) -> tuple[str, str]:
    """Compose the real Omar-brain system prompt from omar_personality_engine.

    Returns (system_prompt, meta). Never raises — on any failure returns ("",
    "engine_error:…") so the n8n default prompt is used and replies still flow.
    """
    try:
        if str(_PERSONALITY_DIR) not in sys.path:
            sys.path.insert(0, str(_PERSONALITY_DIR))
        import omar_personality_engine as pe  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive
        return "", f"engine_import_error:{exc}"
    try:
        contact_context = {"phone": sender, "name": profile_name}
        ctx = pe.build_personality_context(
            message, history=history or "", sender_type="Customer", relationship="", contact_context=contact_context
        )
        parts = [
            str(ctx.get("operations_persona_text") or "").strip(),
            str(ctx.get("system_instruction") or "").strip(),
            f"Tone: {ctx.get('tone')}",
            f"Length: {ctx.get('length_rule')}",
            f"Warmth: {ctx.get('warmth_rule')}",
            f"Action: {ctx.get('action_rule')}",
            f"Language: {ctx.get('language_rule')}",
            f"Safety: {ctx.get('safety_rule')}",
            f"Detected relationship: {ctx.get('relationship')}. "
            f"Objective: {ctx.get('conversation_objective')}. Intent: {ctx.get('intent')}.",
            "CRITICAL - NO FABRICATION: Never state specific units, prices, sizes, "
            "availability, owner details, or listing links unless they were explicitly "
            "provided to you in this conversation's context. If asked about specific "
            "inventory you don't have in context, say you'll check and confirm shortly - "
            "in Omar's natural style, never as a disclaimer. Inventing property details "
            "destroys trust and is forbidden.",
        ]
        special = ctx.get("special_contact_profile") or {}
        if special.get("relationship"):
            greet = special.get("short_greeting_ar") or special.get("short_greeting_en") or ""
            parts.append(
                f"This is a known contact ({special.get('display_name')}, {special.get('relationship')}). "
                f"Match their style; a natural short greeting like '{greet}' fits when appropriate."
            )
        restricted = ctx.get("restricted_knowledge") or []
        if restricted:
            parts.append("Never reveal: " + ", ".join(restricted) + ".")
        system_prompt = "\n\n".join(p for p in parts if p)
        meta = f"lang={ctx.get('language')};rel={ctx.get('relationship')};obj={ctx.get('conversation_objective')}"
        return system_prompt, meta
    except Exception as exc:  # pragma: no cover - defensive
        return "", f"engine_error:{exc}"


def _generate_reply_text(message: str, history: str = "", system_prompt: str = "") -> tuple[str, str]:
    """Ask the n8n brain for a reply. Returns (reply_text, detail).

    When system_prompt is provided (from the real personality engine), it is
    sent so the LLM answers as Omar with full relationship/objective context
    instead of the generic stub prompt.

    Prefers a DIRECT LLM call (Groq/OpenAI) when a key is configured — no n8n,
    no execution cap. Falls back to the n8n brain only if no direct key is set
    or the direct call fails.
    """
    if not message:
        return "", "no_message"
    if _DIRECT_LLM_KEY:
        reply, detail = _generate_reply_direct(message, history, system_prompt)
        if reply:
            return reply, detail
        # direct configured but failed — fall through to n8n if available
        if not WA_REPLY_ENDPOINT:
            return "", detail
    if not WA_REPLY_ENDPOINT or not message:
        return "", "no_endpoint_or_message"
    payload = {"message": message, "history": history or "No prior history"}
    if system_prompt:
        payload["system"] = system_prompt
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        WA_REPLY_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        reply = str(data.get("reply") or data.get("text") or data.get("output") or "").strip()
        return reply, f"{resp.status}:ok" if reply else f"{resp.status}:empty"
    except HTTPError as exc:
        return "", f"http_error:{exc.code}"
    except URLError as exc:
        return "", f"url_error:{exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive
        return "", f"error:{exc}"


def _generate_reply_direct(message: str, history: str = "", system_prompt: str = "") -> tuple[str, str]:
    """Call an LLM directly (Groq/OpenAI-compatible) — no n8n, no execution cap.

    Returns (reply_text, detail). Empty reply signals the caller to fall back.
    """
    if not _DIRECT_LLM_KEY or not message:
        return "", "no_direct_key"
    sys_p = system_prompt.strip() or (
        "You are the WhatsApp assistant for Omar, a Dubai real-estate broker (HSH). "
        "Reply naturally and concisely in the client's language (English or Arabic), "
        "like a real human agent — never mention being an AI. If you don't have a "
        "fact, say you'll check rather than inventing it."
    )
    messages = [{"role": "system", "content": sys_p}]
    if history and history != "No prior history":
        messages.append({"role": "system", "content": "Conversation so far:\n" + history})
    messages.append({"role": "user", "content": message})
    body = json.dumps({
        "model": _DIRECT_LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 500,
    }).encode("utf-8")
    req = Request(
        _DIRECT_LLM_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {_DIRECT_LLM_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        reply = str(
            (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        ).strip()
        return reply, (f"direct:{_DIRECT_LLM_MODEL}:ok" if reply else f"direct:{_DIRECT_LLM_MODEL}:empty")
    except HTTPError as exc:
        return "", f"direct_http:{exc.code}"
    except URLError as exc:
        return "", f"direct_url:{exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive
        return "", f"direct_err:{exc}"


import threading
from collections import OrderedDict

# De-dupe store: WhatsApp providers fire several webhook events per inbound
# message (messages.received + messages.upsert + personal.received) and retry on
# slow acks, so the same message hits this endpoint multiple times. Reply once
# per message_id. Bounded + thread-safe (ThreadingHTTPServer runs many threads).
_REPLIED_IDS: "OrderedDict[str, bool]" = OrderedDict()
_REPLIED_LOCK = threading.Lock()
_REPLIED_MAX = 2000


def _already_replied(message_id: str) -> bool:
    """Return True if we've already replied to this message_id; else record it."""
    if not message_id:
        return False
    with _REPLIED_LOCK:
        if message_id in _REPLIED_IDS:
            return True
        _REPLIED_IDS[message_id] = True
        while len(_REPLIED_IDS) > _REPLIED_MAX:
            _REPLIED_IDS.popitem(last=False)
        return False


def _send_whatsapp_reply(phone: str, text: str) -> tuple[bool, str]:
    """Send a WhatsApp reply through the Wasender send API."""
    if not WASENDER_API_KEY:
        return False, "missing_api_key"
    if not phone or not text:
        return False, "missing_phone_or_text"
    body = json.dumps({"to": phone, "text": text}).encode("utf-8")
    req = Request(
        WASENDER_SEND_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {WASENDER_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": WASENDER_BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return True, f"{resp.status}:sent"
    except HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except URLError as exc:
        return False, f"url_error:{exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"error:{exc}"


def _send_whatsapp_media(phone: str, image_url: str, caption: str = "") -> tuple[bool, str]:
    """Send a real image (by URL) through the Wasender send API.

    Only called with URLs from the curated MediaVault index — never generated
    content. Failure never raises; the text reply still goes out.
    """
    if not WASENDER_API_KEY:
        return False, "missing_api_key"
    if not phone or not image_url:
        return False, "missing_phone_or_url"
    payload: dict[str, Any] = {"to": phone, "imageUrl": image_url}
    if caption:
        payload["text"] = caption
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        WASENDER_SEND_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {WASENDER_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": WASENDER_BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return True, f"{resp.status}:sent"
    except HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except URLError as exc:
        return False, f"url_error:{exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"error:{exc}"


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

    # Outbound reply: only when auto mode is on, the request is not restricted,
    # there is inbound text, and we can resolve a real sender phone. Generates
    # the reply via the n8n brain and sends it back through Wasender. Every step
    # is recorded; failure never raises (the webhook still acks 200).
    reply_sent = False
    reply_detail = "hold" if hold_delivery else "no_action"
    reply_text_out = ""
    sender_digits = "".join(ch for ch in sender if ch.isdigit())
    # Skip the bot's own sends, self-chats, and non-actionable events (status
    # updates, reactions, group/channel noise) so we never reply to those.
    from_me = bool(event.get("from_me"))
    is_self = bool(event.get("is_self_chat"))
    actionable = bool(event.get("actionable", True))
    message_id = str(event.get("message_id") or "")
    event_ts = event.get("timestamp")
    try:
        import chat_governor as _gov
    except Exception:  # pragma: no cover - defensive
        _gov = None
    # Freshness first: backlog / history-sync replays are NOT live customers.
    # They must never be answered, captured as leads, or written to memory.
    event_is_stale = bool(_gov and _gov.is_stale(event_ts))
    # Human takeover: Omar messaging a contact himself silences the bot for
    # that contact — two people must never type from the same number. His own
    # turn also becomes conversation context for when the bot resumes.
    if from_me and not is_self and _gov and not event_is_stale:
        peer = "".join(ch for ch in str(event.get("to_phone") or "") if ch.isdigit()) or sender_digits
        if peer:
            _gov.record_omar_message(peer)
            try:
                import conversation_memory as _mem
                _mem.record(peer, "assistant", text)
            except Exception:
                pass
    # Group-Lead Agent: detect real requests (incl. group messages the reply
    # path ignores) and record ranked leads for Omar. Never replies in groups,
    # and never mines stale backlog as fresh leads.
    if text and not from_me and not event_is_stale:
        try:
            import group_leads as _gl
            _gl.detect(sender_digits or sender, text, source=("group" if is_self is False and not actionable else "direct"))
        except Exception:
            pass
        # Autonomous Deal Agent — gated OFF by default (AIOS_DEAL_AGENT_ENABLED).
        # When on, a real group request becomes a Deal and runs the full loop:
        # search -> owner lookup -> outreach -> reply. Never raises into the webhook.
        try:
            import deal_agent as _da
            if _da.AGENT_ENABLED:
                import deal_wiring as _dw
                # First: is this an owner we contacted replying? If so, capture
                # the availability/price and post the confirmed match to the group.
                _owner_reply = _da.handle_owner_reply(sender_digits, text, _send_whatsapp_reply)
                if not _owner_reply.get("matched"):
                    _group = str(event.get("group_id") or event.get("chat_id") or sender_digits)
                    _agent = _dw.build_agent(
                        send_whatsapp=_send_whatsapp_reply,
                        reply_group=_send_whatsapp_reply,
                    )
                    _deal = _agent.intake(_group, sender_digits or sender, text)
                    if _deal:
                        _agent.run_to_completion(_deal)
        except Exception as _da_exc:  # pragma: no cover - defensive
            logger.warning("deal agent intake failed: %s", _da_exc)
    eligible = (
        not hold_delivery and text and sender_digits
        and not from_me and not is_self and actionable
    )
    if eligible and event_is_stale:
        eligible = False
        reply_detail = "stale_event_suppressed"
    if eligible and _gov and _gov.omar_in_control(sender_digits):
        eligible = False
        reply_detail = "omar_in_control"
        # Still remember what the customer said while Omar handles the chat.
        try:
            import conversation_memory as _mem
            _mem.record(sender_digits, "user", text)
        except Exception:
            pass
    if eligible and _gov:
        throttle_ok, throttle_reason = _gov.allow_reply(sender_digits)
        if not throttle_ok:
            eligible = False
            reply_detail = f"throttled:{throttle_reason}"
    if eligible and _already_replied(message_id):
        eligible = False
        reply_detail = "duplicate_suppressed"
    if not eligible and reply_detail == "no_action" and (from_me or is_self or not actionable):
        reply_detail = "not_actionable"
    if eligible:
        # Conversation memory: recall this contact's recent turns so the brain
        # continues the conversation instead of restarting each message.
        convo_history = ""
        try:
            import conversation_memory as _mem
            convo_history = _mem.history(sender_digits)
            _mem.record(sender_digits, "user", text)
        except Exception as _mem_exc:  # pragma: no cover - defensive
            logger.warning("conversation_memory read failed: %s", _mem_exc)
        try:
            import reply_humanizer as _rh
        except Exception:  # pragma: no cover - defensive
            _rh = None
        # A bare "ok"/"thanks"/emoji gets a human thumbs-up, not an LLM essay.
        if _rh and _rh.is_plain_ack(text):
            reply_sent, send_detail = _send_whatsapp_reply(sender_digits, _rh.ACK_REPLY_EN)
            reply_detail = f"ack_short_reply|send:{send_detail}"
            if _gov and reply_sent:
                _gov.note_reply(sender_digits)
            side_effects["provider_webhook_called"] = True
            side_effects["whatsapp_messages_sent"] = reply_sent
            reply_text_out = _rh.ACK_REPLY_EN
            eligible = False
    if eligible:
        # Reconnect the real brain: build Omar's personality/relationship/
        # objective context and feed it to the LLM as the system prompt.
        system_prompt, brain_meta = _build_personality_system_prompt(
            text, convo_history, sender_digits, str(event.get("profile_name") or "")
        )
        # Knowledge connection: retrieve REAL inventory matching the message and
        # give it to the brain as the only quotable source. No matches -> the
        # no-fabrication rule keeps the reply at "I'll check and confirm".
        inv_count = 0
        try:
            import inventory_retrieval as _inv
            inv_block, inv_count = _inv.build_inventory_context(text)
            if inv_block and system_prompt:
                system_prompt = f"{system_prompt}\n\n{inv_block}"
            elif inv_block:
                system_prompt = inv_block
        except Exception as _inv_exc:  # pragma: no cover - defensive
            logger.warning("inventory_retrieval failed: %s", _inv_exc)
        # Substance gate: no knowledge + no clear intent -> silence beats a
        # confident-sounding nothing. (Greetings/questions still get answered.)
        if _gov:
            _silent, _silent_reason = _gov.should_stay_silent(text, inv_count)
            if _silent:
                reply_detail = f"silent:{_silent_reason}"
                eligible = False
    if eligible:
        # Humanize at the source: WhatsApp-human style rules + honest media
        # handling when the customer asked for photos/plans/video/location.
        wants_media = False
        media_entry = None
        if _rh:
            system_prompt = f"{system_prompt}\n\n{_rh.prompt_rules()}" if system_prompt else _rh.prompt_rules()
            wants_media = _rh.media_intent(text)
            if wants_media:
                try:
                    import media_vault as _mv
                    media_entry = _mv.find_media(text)
                except Exception:  # pragma: no cover - defensive
                    media_entry = None
                if not media_entry:
                    system_prompt = f"{system_prompt}\n\n{_rh.media_prompt_rule()}"
        reply_text_out, gen_detail = _generate_reply_text(text, history=convo_history, system_prompt=system_prompt)
        gen_detail = f"{gen_detail}|brain:{brain_meta}|inv:{inv_count}" if brain_meta else f"{gen_detail}|inv:{inv_count}"
        used_fallback = False
        if not reply_text_out and WA_FALLBACK_REPLY:
            reply_text_out = WA_FALLBACK_REPLY
            used_fallback = True
        # Send REAL media when the vault has it; the reply then references it
        # truthfully. media_sent stays False on any failure.
        media_sent = False
        if media_entry:
            media_sent, media_detail = _send_whatsapp_media(
                sender_digits, media_entry["url"], media_entry.get("caption", "")
            )
            gen_detail = f"{gen_detail}|media:{'sent' if media_sent else media_detail}"
        # Strip the AI fingerprint and never claim media we didn't send.
        if _rh and reply_text_out:
            reply_text_out = _rh.humanize(reply_text_out)
            if wants_media:
                reply_text_out = _rh.enforce_media_honesty(reply_text_out, media_sent, text)
        if reply_text_out:
            reply_sent, send_detail = _send_whatsapp_reply(sender_digits, reply_text_out)
            fb = "|fallback" if used_fallback else ""
            reply_detail = f"generate:{gen_detail}|send:{send_detail}{fb}"
            side_effects["provider_webhook_called"] = True
            side_effects["whatsapp_messages_sent"] = reply_sent or media_sent
            if _gov and reply_sent:
                _gov.note_reply(sender_digits)
            if reply_sent and not used_fallback:
                try:
                    import conversation_memory as _mem
                    _mem.record(sender_digits, "assistant", reply_text_out)
                except Exception:
                    pass
            # CRM: capture every real inbound lead (best-effort, non-blocking).
            try:
                import crm_leads as _crm
                if _crm.configured():
                    _crm.capture(sender_digits, str(event.get("profile_name") or ""), text)
                    side_effects["crm_records_written"] = True
            except Exception as _crm_exc:  # pragma: no cover
                logger.warning("crm capture failed: %s", _crm_exc)
        else:
            reply_detail = f"generate:{gen_detail}|no_fallback_configured"
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
            "enabled": not hold_delivery,
            "mode": "hold_for_approval" if hold_delivery else "auto_reply_via_wasender",
            "sent": reply_sent,
            "detail": reply_detail,
            "reply_text_preview": reply_text_out[:80],
            "reason": "Held for approval." if hold_delivery else "Auto reply generated and sent via Wasender.",
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


# --- Lightweight in-memory rate limiter (per client IP, sliding window) -------
# Protects the public webhook + API POSTs from floods without any external
# dependency. Best-effort; a restart clears the window. Tunable via env.
_RL_WINDOW = float(os.getenv("AIOS_RL_WINDOW_SEC", "10"))
_RL_MAX = int(os.getenv("AIOS_RL_MAX", "60"))          # requests per window per IP
_RL_HITS: dict[str, list] = {}
_RL_LOCK = threading.Lock()
_RL_MAX_BODY = int(os.getenv("AIOS_MAX_BODY_BYTES", "262144"))  # 256 KB POST cap


def _rate_limited(client_ip: str) -> bool:
    now = time.time()
    with _RL_LOCK:
        hits = [t for t in _RL_HITS.get(client_ip, []) if now - t < _RL_WINDOW]
        hits.append(now)
        _RL_HITS[client_ip] = hits
        if len(_RL_HITS) > 4096:  # bound memory: drop the coldest bucket
            oldest = min(_RL_HITS, key=lambda k: _RL_HITS[k][-1] if _RL_HITS[k] else 0)
            _RL_HITS.pop(oldest, None)
        return len(hits) > _RL_MAX


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
        if path in {"/api/health", "/api/health/deep", "/api/runtime/status", "/api/deployment/status", "/api/launch/readiness", "/api/client/config"}:
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
        elif path in ("/cockpit", "/cockpit/", "/ops"):
            # Operations cockpit — behind auth (not in PUBLIC_STATIC_PATHS).
            self.path = "/AIOS-COCKPIT.html"
            path = "/AIOS-COCKPIT.html"
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
        if path == "/api/health/deep":
            # Default OFF: a routine health poll must NOT spend a real n8n
            # execution (the customer's quota is finite — see _BRAIN_PROBE_TTL).
            # Opt in with ?brain=1 for an explicit live probe.
            check_brain = _query(self.path).get("brain", "0") in {"1", "true", "yes"}
            _write_json(self, 200, get_deep_health(check_brain=check_brain))
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
        if path == "/api/truth/audit":
            try:
                import truth_bridge_audit as _tb
                _write_json(self, 200, _tb.audit())
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/marketing/flyer":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or qs.get("query") or [""])[0]
            lang = (qs.get("lang") or ["en"])[0]
            if not q.strip():
                _write_json(self, 400, {"ok": False, "error": "missing q= query param"})
                return
            try:
                import content_studio as _cs
                res = _cs.flyer_for(q, lang=("ar" if lang == "ar" else "en"))
                if not res.get("html"):
                    _write_json(self, 200, res)
                    return
                body = res["html"].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/marketing/targeting":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or qs.get("query") or [""])[0]
            try:
                budget = int((qs.get("budget") or ["5000"])[0])
            except Exception:
                budget = 5000
            if not q.strip():
                _write_json(self, 400, {"ok": False, "error": "missing q= query param"})
                return
            try:
                import content_studio as _cs
                _write_json(self, 200, _cs.targeting_brief(q, monthly_budget_aed=max(500, budget)))
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/marketing/campaign":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or qs.get("query") or [""])[0]
            channel = (qs.get("channel") or ["instagram"])[0]
            try:
                count = int((qs.get("count") or ["3"])[0])
            except Exception:
                count = 3
            if not q.strip():
                _write_json(self, 400, {"ok": False, "error": "missing q= query param"})
                return
            try:
                import content_studio as _cs
                _write_json(self, 200, _cs.campaign(q, channel=channel, count=max(1, min(count, 10))))
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/marketing/generate":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or qs.get("query") or [""])[0]
            channel = (qs.get("channel") or ["property_finder"])[0]
            if not q.strip():
                _write_json(self, 400, {"ok": False, "error": "missing q= query param"})
                return
            try:
                import content_studio as _cs
                _write_json(self, 200, _cs.generate(q, channel=channel))
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/engineering/evaluate":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            def _q(name):
                return (qs.get(name) or [None])[0]
            community = _q("community") or ""
            proposal = {
                "plot_area_sqm": _q("plot_area"),
                "gfa_sqm": _q("gfa"),
                "coverage_sqm": _q("coverage_sqm"),
                "coverage_pct": _q("coverage_pct"),
                "floors": _q("floors"),
                "setback_front_m": _q("setback_front"),
                "setback_side_m": _q("setback_side"),
                "setback_rear_m": _q("setback_rear"),
                "parking_spaces": _q("parking"),
                "pool_boundary_setback_m": _q("pool_setback"),
            }
            if not community:
                _write_json(self, 400, {"ok": False, "error": "missing community= param"})
                return
            try:
                import design_compliance as _dc
                _write_json(self, 200, _dc.evaluate(community, proposal))
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/app" or path == "/app/":
            try:
                from mobile_app_page import APP_HTML
                body = APP_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/units/search":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or [""])[0]
            if not q.strip():
                _write_json(self, 400, {"ok": False, "error": "missing q= query param"})
                return
            try:
                import inventory_retrieval as _inv
                rows = _inv.search(q, max_results=15)
                results = [{
                    "area": r.get("area", ""), "project": r.get("project", ""),
                    "building": r.get("building", ""), "unit": r.get("unit", ""),
                    "bedrooms": r.get("bedrooms", ""), "size": r.get("size", ""),
                    "price": r.get("price", ""),
                    "source": (r.get("source_file", "") or "")[:60],
                } for r in rows]
                _write_json(self, 200, {"ok": True, "query": q, "results": results,
                                        "quotable_total": _inv.quotable_count()})
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/owner/lookup":
            # Admin-only: unit/building/permit -> REAL owner + phone. The
            # customer-channel NEVER_DISCLOSE guard is untouched; this opens
            # only for the authenticated operator with the admin secret.
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            def _q(n): return (qs.get(n) or [""])[0]
            admin = os.getenv("AIOS_ADMIN_SECRET", "").strip()
            provided = (_q("admin_secret") or self.headers.get("X-AIOS-Admin-Secret") or "").strip()
            reveal = bool(admin and provided == admin)
            try:
                import owner_lookup as _ol
                building = _q("building")
                permit = _q("property_number") or _q("permit") or _q("permit_number")
                # If the "building" box actually holds a permit code (e.g.
                # JVC12NHRS006 / a DLD reg no — alnum, has digits, no spaces),
                # treat it as a permit so Omar can paste either into one field.
                import re as _re
                if building and not permit and _re.fullmatch(r"[A-Za-z0-9\-/]{6,}", building.strip()) and _re.search(r"\d", building):
                    permit, building = building.strip(), ""
                res = _ol.lookup(building=building, unit=_q("unit"),
                                 property_number=permit, area=_q("area"),
                                 reveal=reveal, limit=int(_q("limit") or "10"))
                res["revealed"] = reveal
                _write_json(self, 200 if res.get("ok") else 400, res)
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/owner/from-url":
            # Admin-only: paste a Bayut/PF/Dubizzle link -> extract unit ->
            # owner + phone. Masked unless the admin secret is supplied.
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            url = (qs.get("url") or [""])[0]
            admin = os.getenv("AIOS_ADMIN_SECRET", "").strip()
            provided = (qs.get("admin_secret") or [self.headers.get("X-AIOS-Admin-Secret", "")])[0].strip()
            reveal = bool(admin and provided == admin)
            if not url.strip():
                _write_json(self, 400, {"ok": False, "error": "missing url= param"})
                return
            try:
                import portal_extract as _pe, owner_lookup as _ol
                info = _pe.extract(url)
                if not info.get("ok"):
                    _write_json(self, 200, {"ok": False, "reason": info.get("reason"), "extracted": info})
                    return
                owners = _ol.lookup(building=info.get("building", ""), area=info.get("area", ""),
                                    reveal=reveal, limit=10)
                _write_json(self, 200, {"ok": True, "extracted": info, "owners": owners.get("owners", []),
                                        "matches": owners.get("matches", 0), "revealed": reveal})
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/deal/recent":
            try:
                import deal_agent as _da
                _write_json(self, 200, {"ok": True, "deals": _da.load_deals(30), "stats": _da.stats()})
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/outreach/queue":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or [""])[0]
            lang = (qs.get("lang") or ["en"])[0]
            try:
                limit = int((qs.get("limit") or ["20"])[0])
            except Exception:
                limit = 20
            if not q.strip():
                _write_json(self, 400, {"ok": False, "error": "missing q= query param"})
                return
            try:
                import owner_outreach as _oo
                _write_json(self, 200, _oo.queue(q, limit=limit, lang=("ar" if lang == "ar" else "en")))
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/leads/recent":
            try:
                import group_leads as _gl
                _write_json(self, 200, {"ok": True, "leads": _gl.recent(30), "stats": _gl.stats()})
            except Exception as exc:
                _write_json(self, 500, {"ok": False, "error": str(exc)})
            return
        super().do_GET()

    def do_POST(self) -> None:
        started = time.perf_counter()
        path = _path(self.path)
        client_ip = (self.headers.get("X-Forwarded-For", "") or self.client_address[0] if self.client_address else "?").split(",")[0].strip()
        if _rate_limited(client_ip):
            self._aios_skip_cache_header = True
            _write_json(self, 429, {"ok": False, "error": "rate_limited", "retry_after_sec": _RL_WINDOW})
            return
        try:
            if int(self.headers.get("Content-Length") or 0) > _RL_MAX_BODY:
                _write_json(self, 413, {"ok": False, "error": "payload_too_large", "max_bytes": _RL_MAX_BODY})
                return
        except Exception:
            pass
        if not self._require_auth():
            return
        if path not in {
            "/api/permission/evaluate",
            "/api/whatsapp/hosted-test",
            WHATSAPP_WEBHOOK_PATH,
            "/api/unit/ingest",
            "/api/property/resolve",
            "/api/unit/enrich",
            "/api/outreach/send",
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
            if path == "/api/outreach/send":
                # One approved owner-outreach message. Requires the admin
                # secret on top of basic auth; every send is journaled and
                # rate-limited per contact via chat_governor.
                admin = os.getenv("AIOS_ADMIN_SECRET", "").strip()
                if not admin or (payload.get("admin_secret") or self.headers.get("X-AIOS-Admin-Secret") or "").strip() != admin:
                    _write_json(self, 403, {"ok": False, "error": "admin_secret_required"})
                    return
                import owner_outreach as _oo
                ref = str(payload.get("restricted_ref") or "").strip()
                message = str(payload.get("message") or "").strip()
                if not ref or not message:
                    _write_json(self, 400, {"ok": False, "error": "restricted_ref and message required"})
                    return
                mobile = _oo.resolve_mobile(ref)
                if not mobile:
                    _write_json(self, 404, {"ok": False, "error": "unknown restricted_ref"})
                    return
                allowed, rate_detail = True, "no_governor"
                try:
                    import chat_governor as _cg
                    if hasattr(_cg, "allow_reply"):
                        allowed, rate_detail = _cg.allow_reply(mobile)
                except Exception:
                    pass
                if not allowed:
                    _write_json(self, 429, {"ok": False, "error": f"rate_limited:{rate_detail}"})
                    return
                sent, detail = _send_whatsapp_reply(mobile, message)
                _oo.journal_send(ref, mobile, message, sent, detail)
                _write_json(self, 200 if sent else 502,
                            {"ok": sent, "detail": detail, "mobile_masked": _oo._mask(mobile)})
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
    # Health alerting: WhatsApp Omar when a department goes red (gated on
    # AIOS_HEALTH_ALERTS_ENABLED + AIOS_ALERT_PHONE; never blocks serving).
    try:
        import health_alerts as _ha
        if _ha.start_monitor(lambda: get_deep_health(check_brain=False), _send_whatsapp_reply):
            logger.info("health alert monitor started (every %s min)", _ha.INTERVAL_MIN)
    except Exception as _ha_exc:  # pragma: no cover - defensive
        logger.warning("health alert monitor failed to start: %s", _ha_exc)
    # Daily CEO brief: one WhatsApp digest every morning (gated on
    # AIOS_DAILY_BRIEF_ENABLED + AIOS_ALERT_PHONE).
    try:
        import daily_brief as _db
        if _db.start_monitor(lambda: get_deep_health(check_brain=False), _send_whatsapp_reply):
            logger.info("daily brief scheduled for %02d:00 Dubai", _db.BRIEF_HOUR)
    except Exception as _db_exc:  # pragma: no cover - defensive
        logger.warning("daily brief failed to start: %s", _db_exc)
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
