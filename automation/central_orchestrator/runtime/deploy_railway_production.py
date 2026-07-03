#!/usr/bin/env python3
"""Deploy AIOS to Railway after account login is approved.

This runner is intentionally conservative:
- it never prints secret values
- it refuses to deploy when Railway is not authenticated
- it can run a readiness check without creating external resources
- it writes an evidence report for every run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "RAILWAY_PRODUCTION_DEPLOYMENT_RUN.json"
PROJECT_NAME = "aios-runtime"
REQUIRED_ENV = [
    "AIOS_ENV",
    "AIOS_AUTH_MODE",
    "AIOS_BASIC_AUTH_USER",
    "AIOS_BASIC_AUTH_PASSWORD",
    "AIOS_WHATSAPP_REPLY_MODE",
    "AIOS_WHATSAPP_VERIFY_TOKEN",
]
OPTIONAL_ENV = [
    "AIOS_PUBLIC_BASE_URL",
    "AIOS_PUBLIC_API_BASE_URL",
    "AIOS_CUSTOM_DOMAIN",
    "AIOS_WHATSAPP_HOSTED_TEST",
]
PUBLIC_URL_PATTERN = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
DEPLOYMENT_BUNDLE_DIR = REPORTS_DIR / "deployment-bundles"
PACKAGE_VALIDATION_PATH = REPORTS_DIR / "DEPLOYMENT_PACKAGE_VALIDATION.json"
CONTAINER_VALIDATION_PATH = REPORTS_DIR / "CONTAINER_RUNTIME_VALIDATION.json"
BOOT_PERFORMANCE_VALIDATION_PATH = REPORTS_DIR / "LANDING_BOOT_PERFORMANCE_VALIDATION.json"
RUNTIME_PERFORMANCE_VALIDATION_PATH = REPORTS_DIR / "RUNTIME_PERFORMANCE_VALIDATION.json"
PACKAGE_VALIDATION_SOURCES = [
    "AIOS-WEBSITE.html",
    "AIOS-DASHBOARD.html",
    "AIOS-MOBILE-APP.html",
    "aios-service-worker.js",
    "Dockerfile",
    "railway.json",
    ".railwayignore",
    "automation/central_orchestrator/runtime/aios_live_api_server.py",
    "automation/central_orchestrator/runtime/validate_deployment_package.py",
    "automation/central_orchestrator/runtime/deploy_railway_production.py",
]
CONTAINER_VALIDATION_SOURCES = [
    "Dockerfile",
    ".dockerignore",
    "render.yaml",
    "railway.json",
    ".railwayignore",
    "automation/central_orchestrator/runtime/aios_live_api_server.py",
    "automation/central_orchestrator/runtime/validate_container_runtime.py",
]
BOOT_PERFORMANCE_SOURCES = [
    "AIOS-WEBSITE.html",
    "AIOS-DASHBOARD.html",
    "AIOS-MOBILE-APP.html",
    "aios-service-worker.js",
    "automation/central_orchestrator/runtime/aios_live_api_server.py",
    "automation/central_orchestrator/runtime/validate_landing_boot_performance.py",
]
RUNTIME_PERFORMANCE_SOURCES = [
    "AIOS-WEBSITE.html",
    "aios-service-worker.js",
    "automation/central_orchestrator/runtime/aios_live_api_server.py",
    "automation/central_orchestrator/runtime/validate_runtime_performance.py",
]
LOCAL_RELEASE_REFRESH_COMMANDS = [
    ["python3", "automation/central_orchestrator/runtime/validate_deployment_package.py"],
    ["python3", "automation/central_orchestrator/runtime/validate_container_runtime.py"],
]
BUNDLE_REFRESH_COMMAND = ["python3", "automation/central_orchestrator/runtime/build_deployment_bundle.py", "--summary"]


def _railway_cli() -> str | None:
    return shutil.which("railway") or (str(Path.home() / ".railway" / "bin" / "railway") if (Path.home() / ".railway" / "bin" / "railway").exists() else None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(
    args: list[str],
    *,
    check: bool = False,
    timeout: int = 120,
    stdout_limit: int | None = 4000,
    env_updates: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    if env_updates:
        env.update(env_updates)
    try:
        proc = subprocess.run(args, cwd=AIOS_ROOT, text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": _safe_cmd(args),
            "returncode": 124,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
        }
    result = {
        "cmd": _safe_cmd(args),
        "returncode": proc.returncode,
        "stdout": proc.stdout if stdout_limit is None else proc.stdout[-stdout_limit:],
        "stderr": proc.stderr[-4000:],
    }
    if check and proc.returncode != 0:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


def _safe_cmd(args: list[str]) -> str:
    return " ".join(args)


def _env_presence() -> dict[str, Any]:
    required = {
        key: {
            "present": bool(os.getenv(key)),
            "secret": key in {"AIOS_BASIC_AUTH_USER", "AIOS_BASIC_AUTH_PASSWORD", "AIOS_WHATSAPP_VERIFY_TOKEN"},
        }
        for key in REQUIRED_ENV
    }
    optional = {key: {"present": bool(os.getenv(key)), "secret": False} for key in OPTIONAL_ENV}
    return {
        "required": required,
        "optional": optional,
        "missing_required": [key for key, item in required.items() if not item["present"]],
    }


def _railway_variable_presence(railway: str | None, service: str | None) -> dict[str, Any]:
    if not railway:
        return {"available": False, "error": "railway cli not found", "missing_required": REQUIRED_ENV}
    args = [railway, "variable", "list", "--json"]
    if service:
        args.extend(["--service", service])
    proc = None
    attempts: list[dict[str, Any]] = []
    for timeout in (45, 90):
        try:
            proc = subprocess.run(args, cwd=AIOS_ROOT, text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            attempts.append({"timeout_seconds": timeout, "returncode": 124, "error": "timeout"})
            continue
        attempts.append({"timeout_seconds": timeout, "returncode": proc.returncode})
        if proc.returncode == 0:
            break
    if proc is None:
        return {
            "available": False,
            "error": "railway_variable_list_timeout",
            "attempts": attempts,
            "missing_required": REQUIRED_ENV,
        }
    if proc.returncode != 0:
        return {
            "available": False,
            "error": "railway_variable_list_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr[-1000:],
            "attempts": attempts,
            "missing_required": REQUIRED_ENV,
        }
    try:
        parsed = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"available": False, "error": f"railway_variable_list_json_error:{exc}", "missing_required": REQUIRED_ENV}
    if isinstance(parsed, list):
        keys = {str(item.get("name") or item.get("key") or "") for item in parsed if isinstance(item, dict)}
    elif isinstance(parsed, dict):
        keys = set(parsed.keys())
    else:
        keys = set()
    required = {
        key: {
            "present": key in keys,
            "secret": key in {"AIOS_BASIC_AUTH_USER", "AIOS_BASIC_AUTH_PASSWORD", "AIOS_WHATSAPP_VERIFY_TOKEN"},
        }
        for key in REQUIRED_ENV
    }
    optional = {key: {"present": key in keys, "secret": False} for key in OPTIONAL_ENV}
    return {
        "available": True,
        "required": required,
        "optional": optional,
        "missing_required": [key for key, item in required.items() if not item["present"]],
        "present_required_count": sum(1 for item in required.values() if item["present"]),
        "present_optional_count": sum(1 for item in optional.values() if item["present"]),
        "attempts": attempts,
    }


def _effective_env_presence(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    required: dict[str, Any] = {}
    for key in REQUIRED_ENV:
        local_present = bool(((local.get("required") or {}).get(key) or {}).get("present"))
        remote_present = bool(((remote.get("required") or {}).get(key) or {}).get("present"))
        required[key] = {
            "present": local_present or remote_present,
            "local_present": local_present,
            "railway_present": remote_present,
            "secret": key in {"AIOS_BASIC_AUTH_USER", "AIOS_BASIC_AUTH_PASSWORD", "AIOS_WHATSAPP_VERIFY_TOKEN"},
        }
    return {
        "required": required,
        "missing_required": [key for key, item in required.items() if not item["present"]],
        "source": "local_or_railway",
    }


def _tooling() -> dict[str, Any]:
    railway = _railway_cli()
    return {
        "railway_cli": railway,
        "railway_available": bool(railway),
        "railway_json": (AIOS_ROOT / "railway.json").exists(),
        "railwayignore": (AIOS_ROOT / ".railwayignore").exists(),
        "dockerfile": (AIOS_ROOT / "Dockerfile").exists(),
    }


def _whoami() -> dict[str, Any]:
    railway = _railway_cli()
    if not railway:
        return {"authenticated": False, "error": "railway cli not found"}
    result = _run([railway, "whoami"])
    return {
        "authenticated": result["returncode"] == 0,
        "result": result,
    }


def _set_non_secret_defaults(railway: str, service: str | None) -> list[dict[str, Any]]:
    commands = []
    defaults = {
        "AIOS_ENV": os.getenv("AIOS_ENV", "production"),
        "AIOS_AUTH_MODE": os.getenv("AIOS_AUTH_MODE", "basic"),
        "AIOS_WHATSAPP_REPLY_MODE": os.getenv("AIOS_WHATSAPP_REPLY_MODE", "hold"),
        "AIOS_WHATSAPP_HOSTED_TEST": os.getenv("AIOS_WHATSAPP_HOSTED_TEST", "fail"),
    }
    for key, value in defaults.items():
        args = [railway, "variable", "set", f"{key}={value}", "--skip-deploys", "--json"]
        if service:
            args.extend(["--service", service])
        commands.append(_run(args))
    return commands


def _deploy(railway: str, args: argparse.Namespace) -> dict[str, Any]:
    deploy_args = [
        railway,
        "up",
        "--detach",
        "--json",
        "--message",
        args.message,
    ]
    if args.new:
        deploy_args.extend(["--new", "--name", args.name])
    if args.service:
        deploy_args.extend(["--service", args.service])
    return _run(deploy_args)


def _domain_list(railway: str, service: str | None) -> dict[str, Any]:
    args = [railway, "domain", "list", "--json"]
    if service:
        args.extend(["--service", service])
    return _run(args)


def _local_start_command() -> str:
    try:
        config = json.loads((AIOS_ROOT / "railway.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str((config.get("deploy") or {}).get("startCommand") or "")


def _railway_status_inspection(railway: str, service: str | None = None) -> dict[str, Any]:
    result = _run([railway, "status", "--json"], timeout=30, stdout_limit=None)
    local_start = _local_start_command()
    inspection: dict[str, Any] = {
        "status_command": result,
        "local_start_command": local_start,
        "services": [],
        "active_start_matches_local": False,
        "active_start_command": "",
        "public_url_candidates": [],
    }
    if result["returncode"] != 0:
        inspection["error"] = "railway_status_failed"
        return inspection
    try:
        status = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError as exc:
        inspection["error"] = f"railway_status_json_error:{exc}"
        return inspection
    for env_edge in (status.get("environments") or {}).get("edges", []):
        env = env_edge.get("node") or {}
        for svc_edge in (env.get("serviceInstances") or {}).get("edges", []):
            node = svc_edge.get("node") or {}
            service_name = str(node.get("serviceName") or "")
            latest = node.get("latestDeployment") or {}
            meta = latest.get("meta") or {}
            active_start = str((((meta.get("serviceManifest") or {}).get("deploy") or {}).get("startCommand")) or node.get("startCommand") or "")
            item = {
                "environment": env.get("name"),
                "service": service_name,
                "deployment_id": latest.get("id"),
                "deployment_status": latest.get("status"),
                "active_start_command": active_start,
                "matches_local_start_command": bool(local_start and active_start == local_start),
                "public_url_candidates": _extract_domains_from_service_instance(node),
            }
            inspection["services"].append(item)
            for candidate in item["public_url_candidates"]:
                if candidate not in inspection["public_url_candidates"]:
                    inspection["public_url_candidates"].append(candidate)
            if (not service or service_name == service) and not inspection["active_start_command"]:
                inspection["active_start_command"] = active_start
                inspection["active_start_matches_local"] = item["matches_local_start_command"]
    return inspection


def _ensure_domain(railway: str, service: str | None) -> dict[str, Any]:
    args = [railway, "domain", "--port", os.getenv("PORT", "8080"), "--json"]
    if service:
        args.extend(["--service", service])
    return _run(args)


def _extract_public_urls(actions: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for action in actions:
        for stream in ("stdout", "stderr"):
            for match in PUBLIC_URL_PATTERN.findall(str(action.get(stream, ""))):
                cleaned = match.rstrip(".,);]")
                if cleaned not in urls:
                    urls.append(cleaned)
        for stream in ("stdout",):
            try:
                parsed = json.loads(str(action.get(stream, "")) or "{}")
            except json.JSONDecodeError:
                continue
            payloads = parsed if isinstance(parsed, list) else [parsed]
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                for value in payload.values():
                    if isinstance(value, str):
                        candidate = value.strip().rstrip("/")
                        if "." in candidate and " " not in candidate:
                            if not candidate.startswith(("http://", "https://")):
                                candidate = f"https://{candidate}"
                            if candidate not in urls:
                                urls.append(candidate)
    return urls


def _normalize_public_url(candidate: str) -> str:
    cleaned = candidate.strip().rstrip(".,);]/")
    if not cleaned or " " in cleaned or "." not in cleaned:
        return ""
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def _extract_domains_from_service_instance(node: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    domains = node.get("domains") or {}
    service_domains = domains.get("serviceDomains") or []
    custom_domains = domains.get("customDomains") or []
    for item in [*service_domains, *custom_domains]:
        if not isinstance(item, dict):
            continue
        for key in ("domain", "publicDomain", "host"):
            url = _normalize_public_url(str(item.get(key) or ""))
            if url and url not in urls:
                urls.append(url)
    return urls


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _latest_release_artifact() -> dict[str, Any]:
    manifests = sorted(DEPLOYMENT_BUNDLE_DIR.glob("AIOS_RUNTIME_DEPLOYMENT_*.manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not manifests:
        return {"available": False, "error": "no_deployment_bundle_manifest"}
    manifest_path = manifests[0]
    manifest = _read_json(manifest_path)
    bundle_path = AIOS_ROOT / str(manifest.get("bundle") or "")
    return {
        "available": bool(manifest.get("passed") is True and bundle_path.exists()),
        "manifest": str(manifest_path.relative_to(AIOS_ROOT)),
        "bundle": str(bundle_path.relative_to(AIOS_ROOT)) if bundle_path.exists() else manifest.get("bundle"),
        "bundle_exists": bundle_path.exists(),
        "bundle_bytes": bundle_path.stat().st_size if bundle_path.exists() else manifest.get("bundle_bytes"),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "file_count": manifest.get("file_count"),
        "missing_required": manifest.get("missing_required", []),
        "published": False,
        "deployed": False,
    }


def _source_freshness(path: Path, sources: list[str] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"fresh": False, "report_mtime": 0, "newest_source_mtime": 0, "stale_sources": []}
    report_mtime = path.stat().st_mtime
    source_items: list[dict[str, Any]] = []
    for source in sources or []:
        source_path = AIOS_ROOT / source
        source_mtime = source_path.stat().st_mtime if source_path.exists() else 0
        source_items.append(
            {
                "path": source,
                "exists": source_path.exists(),
                "mtime": source_mtime,
                "stale": source_mtime > report_mtime,
            }
        )
    stale_sources = [item for item in source_items if item["stale"] or not item["exists"]]
    return {
        "fresh": not stale_sources,
        "report_mtime": report_mtime,
        "newest_source_mtime": max([item["mtime"] for item in source_items] or [0]),
        "stale_sources": stale_sources,
    }


def _validation_summary(path: Path, name: str, sources: list[str] | None = None) -> dict[str, Any]:
    report = _read_json(path)
    freshness = _source_freshness(path, sources)
    return {
        "name": name,
        "available": bool(report),
        "path": str(path.relative_to(AIOS_ROOT)),
        "passed": report.get("passed") is True,
        "checks_passed": report.get("checks_passed"),
        "checks_total": report.get("checks_total"),
        "blockers": report.get("blockers", []),
        "fresh": freshness["fresh"],
        "report_mtime": freshness["report_mtime"],
        "newest_source_mtime": freshness["newest_source_mtime"],
        "stale_sources": freshness["stale_sources"],
    }


def _find_open_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return int(sock.getsockname()[1])
    raise RuntimeError("no_local_validation_port_available")


def _wait_for_health(base_url: str, timeout_seconds: float = 18.0) -> bool:
    deadline = time.time() + timeout_seconds
    url = base_url.rstrip("/") + "/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.35)
    return False


def _local_validation_env(port: int) -> dict[str, str]:
    return {
        "AIOS_ENV": os.getenv("AIOS_ENV", "local-validation"),
        "AIOS_API_PORT": str(port),
        "AIOS_AUTH_MODE": os.getenv("AIOS_AUTH_MODE", "basic"),
        "AIOS_BASIC_AUTH_USER": os.getenv("AIOS_BASIC_AUTH_USER", "localtest"),
        "AIOS_BASIC_AUTH_PASSWORD": os.getenv("AIOS_BASIC_AUTH_PASSWORD", "localtestpass"),
        "AIOS_WHATSAPP_REPLY_MODE": os.getenv("AIOS_WHATSAPP_REPLY_MODE", "hold"),
        "AIOS_WHATSAPP_VERIFY_TOKEN": os.getenv("AIOS_WHATSAPP_VERIFY_TOKEN", "local-preview-token"),
    }


def _refresh_local_speed_evidence() -> dict[str, Any]:
    port = _find_open_port(int(os.getenv("AIOS_LOCAL_VALIDATION_PORT", "8881")))
    base_url = f"http://127.0.0.1:{port}"
    env = _local_validation_env(port)
    server_args = [
        "python3",
        "automation/central_orchestrator/runtime/aios_live_api_server.py",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    started_at = _now()
    process = subprocess.Popen(
        server_args,
        cwd=AIOS_ROOT,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    commands: list[dict[str, Any]] = [
        {
            "cmd": _safe_cmd(server_args),
            "returncode": None,
            "started": True,
            "pid": process.pid,
            "base_url": base_url,
            "started_at": started_at,
        }
    ]
    blockers: list[str] = []
    try:
        if not _wait_for_health(base_url):
            blockers.append("local_validation_server_health_timeout")
            return {"passed": False, "base_url": base_url, "commands": commands, "blockers": blockers}
        boot_command = ["python3", "automation/central_orchestrator/runtime/validate_landing_boot_performance.py", base_url]
        boot = _run(boot_command, timeout=180, stdout_limit=3000, env_updates=env)
        commands.append(boot)
        if boot.get("returncode") != 0:
            time.sleep(1.25)
            boot_retry = _run(boot_command, timeout=180, stdout_limit=3000, env_updates=env)
            boot_retry["retry_of"] = _safe_cmd(boot_command)
            commands.append(boot_retry)
            boot = boot_retry
        if boot.get("returncode") != 0:
            blockers.append("command_failed:validate_landing_boot_performance.py")
            return {"passed": False, "base_url": base_url, "commands": commands, "blockers": blockers}
        runtime_command = ["python3", "automation/central_orchestrator/runtime/validate_runtime_performance.py", base_url, "--requests", "8"]
        runtime = _run(runtime_command, timeout=180, stdout_limit=3000, env_updates=env)
        commands.append(runtime)
        if runtime.get("returncode") != 0:
            time.sleep(1.25)
            runtime_retry = _run(runtime_command, timeout=180, stdout_limit=3000, env_updates=env)
            runtime_retry["retry_of"] = _safe_cmd(runtime_command)
            commands.append(runtime_retry)
            runtime = runtime_retry
        if runtime.get("returncode") != 0:
            blockers.append("command_failed:validate_runtime_performance.py")
    finally:
        process.terminate()
        try:
            returncode = process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait(timeout=8)
        commands.append({"cmd": "terminate local validation server", "returncode": returncode, "pid": process.pid})
    return {
        "passed": not blockers,
        "base_url": base_url,
        "commands": commands,
        "blockers": blockers,
    }


def _refresh_local_release(skip: bool = False) -> dict[str, Any]:
    if skip:
        return {
            "skipped": True,
            "passed": None,
            "commands": [],
            "blockers": [],
        }
    commands: list[dict[str, Any]] = []
    blockers: list[str] = []
    for command in LOCAL_RELEASE_REFRESH_COMMANDS:
        result = _run(command, timeout=240, stdout_limit=3000)
        commands.append(result)
        if result.get("returncode") != 0:
            blockers.append(f"command_failed:{_safe_cmd(command)}")
            break
    speed_refresh: dict[str, Any] = {"passed": None, "commands": [], "blockers": []}
    if not blockers:
        speed_refresh = _refresh_local_speed_evidence()
        commands.extend(speed_refresh.get("commands") or [])
        blockers.extend(speed_refresh.get("blockers") or [])
    if not blockers:
        result = _run(BUNDLE_REFRESH_COMMAND, timeout=240, stdout_limit=3000)
        commands.append(result)
        if result.get("returncode") != 0:
            blockers.append(f"command_failed:{_safe_cmd(BUNDLE_REFRESH_COMMAND)}")
    return {
        "skipped": False,
        "passed": not blockers,
        "commands": commands,
        "speed_refresh": speed_refresh,
        "blockers": blockers,
    }


def _local_release_readiness() -> dict[str, Any]:
    artifact = _latest_release_artifact()
    package = _validation_summary(PACKAGE_VALIDATION_PATH, "deployment_package", PACKAGE_VALIDATION_SOURCES)
    container = _validation_summary(CONTAINER_VALIDATION_PATH, "container_runtime", CONTAINER_VALIDATION_SOURCES)
    boot_performance = _validation_summary(BOOT_PERFORMANCE_VALIDATION_PATH, "boot_performance", BOOT_PERFORMANCE_SOURCES)
    runtime_performance = _validation_summary(RUNTIME_PERFORMANCE_VALIDATION_PATH, "runtime_performance", RUNTIME_PERFORMANCE_SOURCES)
    blockers = []
    if not artifact.get("available"):
        blockers.append("latest_release_artifact_missing_or_failed")
    if package.get("passed") is not True:
        blockers.append("deployment_package_validation_not_passed")
    if package.get("fresh") is not True:
        blockers.append("deployment_package_validation_stale")
    if container.get("passed") is not True:
        blockers.append("container_runtime_validation_not_passed")
    if container.get("fresh") is not True:
        blockers.append("container_runtime_validation_stale")
    if boot_performance.get("passed") is not True:
        blockers.append("boot_performance_validation_not_passed")
    if boot_performance.get("fresh") is not True:
        blockers.append("boot_performance_validation_stale")
    if runtime_performance.get("passed") is not True:
        blockers.append("runtime_performance_validation_not_passed")
    if runtime_performance.get("fresh") is not True:
        blockers.append("runtime_performance_validation_stale")
    return {
        "ready": not blockers,
        "latest_release_artifact": artifact,
        "validations": {
            "deployment_package": package,
            "container_runtime": container,
            "boot_performance": boot_performance,
            "runtime_performance": runtime_performance,
        },
        "blockers": blockers,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    railway = _railway_cli()
    local_environment = _env_presence()
    railway_environment = _railway_variable_presence(railway, args.service)
    effective_environment = _effective_env_presence(local_environment, railway_environment)
    local_release_refresh = _refresh_local_release(args.no_refresh_local_release)
    local_release_readiness = _local_release_readiness()
    report: dict[str, Any] = {
        "generated_at": _now(),
        "mode": "execute" if args.execute else "check",
        "package_root": str(AIOS_ROOT),
        "tooling": _tooling(),
        "environment": local_environment,
        "railway_environment": railway_environment,
        "effective_environment": effective_environment,
        "whoami": _whoami(),
        "railway_status": _railway_status_inspection(railway, args.service) if railway else {},
        "local_release_refresh": local_release_refresh,
        "local_release_readiness": local_release_readiness,
        "status": "not_started",
        "actions": [],
        "public_url_candidates": [],
        "next_action": "",
    }
    report["public_url_candidates"] = list((report.get("railway_status") or {}).get("public_url_candidates") or [])
    if not railway:
        report["status"] = "blocked_no_railway_cli"
        report["next_action"] = "Install Railway CLI and rerun."
    elif not report["whoami"].get("authenticated"):
        report["status"] = "blocked_railway_auth"
        report["next_action"] = "Approve Railway login, then rerun with --execute."
    elif effective_environment["missing_required"]:
        report["status"] = "blocked_missing_required_env"
        report["next_action"] = "Export missing AIOS env vars locally or set them on Railway before executing deploy."
    elif report["local_release_refresh"]["blockers"]:
        report["status"] = "blocked_local_release_refresh_failed"
        report["next_action"] = "Fix local validation or bundle refresh failure before executing deploy."
    elif report["local_release_readiness"]["blockers"]:
        report["status"] = "blocked_local_release_not_ready"
        report["next_action"] = "Fix local release readiness blockers before executing deploy."
    elif not args.execute:
        report["status"] = "ready_to_execute"
        report["next_action"] = "Run with --execute to set non-secret variables and deploy."
    else:
        report["actions"].extend(_set_non_secret_defaults(railway, args.service))
        report["actions"].append(_deploy(railway, args))
        report["actions"].append(_run([railway, "status"]))
        report["actions"].append(_run([railway, "deployment", "list", "--json"]))
        report["actions"].append(_domain_list(railway, args.service))
        if args.ensure_domain:
            report["actions"].append(_ensure_domain(railway, args.service))
            report["actions"].append(_domain_list(railway, args.service))
        report["actions"].append(_run([railway, "logs", "--lines", "100"], timeout=20))
        for candidate in _extract_public_urls(report["actions"]):
            if candidate not in report["public_url_candidates"]:
                report["public_url_candidates"].append(candidate)
        report["status"] = "deploy_command_finished"
        report["next_action"] = (
            "Run finalize_production_hosting.py with the first public_url_candidate."
            if report["public_url_candidates"]
            else "Create or attach a Railway domain, then run finalize_production_hosting.py."
        )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy AIOS to Railway after login approval.")
    parser.add_argument("--execute", action="store_true", help="Run external Railway deploy commands.")
    parser.add_argument("--new", action="store_true", default=False, help="Create a new Railway project/service.")
    parser.add_argument("--existing", dest="new", action="store_false", help="Deploy into the linked existing Railway project/service. This is the default.")
    parser.add_argument("--name", default=PROJECT_NAME, help="Railway project name.")
    parser.add_argument("--service", default="", help="Optional existing Railway service name.")
    parser.add_argument("--message", default="AIOS production hosting deploy", help="Railway deployment message.")
    parser.add_argument("--ensure-domain", action="store_true", help="Generate a Railway-provided public domain after deploy if the project is authenticated.")
    parser.add_argument("--no-refresh-local-release", action="store_true", help="Use existing local validation and bundle reports instead of regenerating them first.")
    return parser.parse_args()


def main() -> int:
    report = run(parse_args())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not str(report["status"]).startswith("blocked_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
