#!/usr/bin/env python3
"""Unified AIOS Runtime package.

Single launch and status wrapper for the AIOS Live API Server, router,
permission runtime, personality runtime, knowledge runtime, and health monitor.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
RUNTIME_STATUS_PATH = REPORTS_DIR / "AIOS_RUNTIME_STATUS.json"
LAUNCH_READINESS_PATH = REPORTS_DIR / "PRODUCTION_LAUNCH_READINESS.json"
DEFAULT_HOST = os.getenv("AIOS_API_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("AIOS_API_PORT") or os.getenv("PORT") or "8888")
RUNTIME_STATUS_CACHE_SECONDS = float(os.getenv("AIOS_RUNTIME_STATUS_CACHE_SECONDS", "5"))
_RUNTIME_STATUS_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}

START_COMMAND = "python3 -m aios_runtime_production_up --host 0.0.0.0 --port ${PORT:-8888}"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

COMPONENTS = [
    {
        "name": "AIOS Live API Server",
        "kind": "api",
        "module": "aios_live_api_server",
        "required_file": "aios_live_api_server.py",
        "capability": "single HTTP surface for AIOS runtime endpoints",
    },
    {
        "name": "Router",
        "kind": "router",
        "module": "gd_core_orchestrator",
        "required_file": "gd_core_orchestrator.py",
        "capability": "channel detection and safe route contract",
    },
    {
        "name": "Permission Runtime",
        "kind": "permission",
        "module": "aios_interaction_architecture_runtime",
        "required_file": "aios_interaction_architecture_runtime.py",
        "capability": "central permission decisions and Eye state",
    },
    {
        "name": "Personality Runtime",
        "kind": "personality",
        "module": "aios_interaction_architecture_runtime",
        "required_file": "aios_interaction_architecture_runtime.py",
        "capability": "Omar-style response behavior",
    },
    {
        "name": "Knowledge Runtime",
        "kind": "knowledge",
        "module": "knowledge_vault_runtime",
        "required_file": "knowledge_vault_runtime.py",
        "capability": "local knowledge asset indexing and retrieval routes",
    },
    {
        "name": "Health Monitor",
        "kind": "health",
        "module": "build_command_center_data",
        "required_file": "build_command_center_data.py",
        "capability": "command-center health and runtime status data",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_import(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, "import_ok"
    except Exception as exc:
        return False, f"import_failed: {exc}"


def _component_status(component: dict[str, str]) -> dict[str, Any]:
    path = RUNTIME_DIR / component["required_file"]
    exists = path.exists()
    imported, detail = _runtime_import(component["module"]) if exists else (False, "file_missing")
    return {
        "name": component["name"],
        "kind": component["kind"],
        "status": "ready" if exists and imported else "blocked",
        "capability": component["capability"],
        "file": str(path.relative_to(AIOS_ROOT)),
        "file_exists": exists,
        "import": detail,
    }


def _smoke_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "python_version",
            "passed": sys.version_info >= (3, 9),
            "detail": platform.python_version() + " · minimum 3.9",
        }
    )
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        probe = REPORTS_DIR / ".runtime_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
        detail = "reports_dir_writable"
    except Exception as exc:
        writable = False
        detail = str(exc)
    checks.append({"name": "reports_directory", "passed": writable, "detail": detail})
    checks.append(
        {
            "name": "dashboard_file",
            "passed": (AIOS_ROOT / "AIOS-DASHBOARD.html").exists(),
            "detail": "AIOS-DASHBOARD.html",
        }
    )
    try:
        from aios_interaction_architecture_runtime import evaluate_permission_request

        permission = evaluate_permission_request("Give me owner phone number", channel="runtime_health")
        checks.append(
            {
                "name": "permission_runtime",
                "passed": permission.get("blocked") is True and permission.get("eye_state") == "restricted",
                "detail": permission.get("runtime"),
            }
        )
    except Exception as exc:
        checks.append({"name": "permission_runtime", "passed": False, "detail": str(exc)})
    try:
        from gd_core_orchestrator import process

        routed = process({"channel": "health", "command": "show AIOS runtime health"})
        checks.append(
            {
                "name": "router",
                "passed": routed.get("aios_event", {}).get("channel") == "command_center",
                "detail": routed.get("route", {}).get("safety_gate"),
            }
        )
    except Exception as exc:
        checks.append({"name": "router", "passed": False, "detail": str(exc)})
    try:
        from aios_interaction_architecture_runtime import omar_personality

        personality = omar_personality({"type": "Existing Client"}, {"response_adjustment": "warm_direct_short"})
        checks.append(
            {
                "name": "personality_runtime",
                "passed": personality.get("goal") == "sounds_like_omar_not_chatgpt",
                "detail": personality.get("style"),
            }
        )
    except Exception as exc:
        checks.append({"name": "personality_runtime", "passed": False, "detail": str(exc)})
    try:
        report_path = REPORTS_DIR / "KNOWLEDGE_VAULT_REPORT.json"
        report: dict[str, Any] = {}
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
        if int(report.get("asset_count") or 0) <= 0:
            from knowledge_vault_runtime import build as build_knowledge_vault

            report = build_knowledge_vault({})
        count = int(report.get("asset_count") or 0)
        checks.append({"name": "knowledge_runtime", "passed": count > 0, "detail": f"{count} assets indexed"})
    except Exception as exc:
        checks.append({"name": "knowledge_runtime", "passed": False, "detail": str(exc)})
    return checks


def get_runtime_status(*, force_refresh: bool = False) -> dict[str, Any]:
    if not force_refresh and RUNTIME_STATUS_CACHE_SECONDS > 0:
        now = time.monotonic()
        cached = _RUNTIME_STATUS_CACHE.get("payload")
        if cached and now < float(_RUNTIME_STATUS_CACHE.get("expires_at") or 0):
            return dict(cached)
    components = [_component_status(component) for component in COMPONENTS]
    checks = _smoke_checks()
    ready_components = sum(1 for item in components if item["status"] == "ready")
    passed_checks = sum(1 for item in checks if item["passed"])
    total = len(components) + len(checks)
    score = round(((ready_components + passed_checks) / total) * 100)
    blocked = [item for item in components if item["status"] != "ready"] + [item for item in checks if not item["passed"]]
    launch: dict[str, Any] = {}
    if LAUNCH_READINESS_PATH.exists():
        try:
            launch = json.loads(LAUNCH_READINESS_PATH.read_text(encoding="utf-8"))
        except Exception:
            launch = {}
    production_deployment = launch.get("production_deployment", "pending")
    public_beta_ready = launch.get("public_beta_ready", False) is True
    production_blockers = launch.get("blockers") or []
    status = {
        "generated_at": _now(),
        "product": "AIOS Runtime",
        "status": "ready" if not blocked else "degraded",
        "start_command": START_COMMAND,
        "health_endpoint": "/api/health",
        "runtime_status_endpoint": "/api/runtime/status",
        "deployment_status_endpoint": "/api/deployment/status",
        "permission_endpoint": "/api/permission/evaluate",
        "audit_endpoint": "/api/permission/audit",
        "whatsapp_webhook_endpoint": "/webhook/whatsapp/provider/gateway",
        "whatsapp_webhook_verification": "AIOS_WHATSAPP_VERIFY_TOKEN",
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "mac_dependency": False,
        "mac_dependency_reason": "No macOS-only runtime dependency; uses Python standard library and local files.",
        "runtime_ready_percent": score,
        "runtime_ready": not blocked and score == 100,
        "production_deployment": production_deployment,
        "public_beta_ready": public_beta_ready,
        "production_ready_percent": 100 if production_deployment == "ready" and public_beta_ready else 0,
        "production_status": "production_live" if production_deployment == "ready" and public_beta_ready else "deployment_pending",
        "production_blockers": production_blockers,
        "components": components,
        "auto_start_checks": checks,
        "blocked_items": blocked,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_STATUS_PATH.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if RUNTIME_STATUS_CACHE_SECONDS > 0:
        _RUNTIME_STATUS_CACHE["payload"] = dict(status)
        _RUNTIME_STATUS_CACHE["expires_at"] = time.monotonic() + RUNTIME_STATUS_CACHE_SECONDS
    return status


def print_status() -> int:
    print(json.dumps(get_runtime_status(force_refresh=True), indent=2, ensure_ascii=False))
    return 0


def start(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    status = get_runtime_status(force_refresh=True)
    if status["status"] != "ready":
        print(json.dumps(status, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    from aios_live_api_server import run_server

    return run_server(host=host, port=port)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS unified runtime")
    sub = parser.add_subparsers(dest="command")
    start_parser = sub.add_parser("start", help="Start AIOS Runtime")
    start_parser.add_argument("--host", default=DEFAULT_HOST)
    start_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub.add_parser("status", help="Print AIOS Runtime status")
    args = parser.parse_args()
    if args.command == "start":
        return start(host=args.host, port=args.port)
    return print_status()


if __name__ == "__main__":
    raise SystemExit(main())
