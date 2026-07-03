#!/usr/bin/env python3
"""Validate the AIOS deployment package before external hosting."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "DEPLOYMENT_PACKAGE_VALIDATION.json"
MANIFEST_PATH = AIOS_ROOT / "PRODUCTION_DEPLOYMENT_MANIFEST.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _check_required_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    for rel in manifest.get("required_files", []):
        path = AIOS_ROOT / rel
        checks.append(
            {
                "name": f"file:{rel}",
                "passed": path.exists() and path.stat().st_size > 0,
                "path": rel,
                "bytes": path.stat().st_size if path.exists() else 0,
            }
        )
    return checks


def _check_env_template(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / ".env.production.example")
    return [
        {
            "name": f"env:{key}",
            "passed": f"{key}=" in text,
            "key": key,
        }
        for key in manifest.get("required_environment", [])
    ]


def _check_render_yaml() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "render.yaml")
    required = {
        "runtime: docker": "render docker runtime",
        "healthCheckPath: /api/health": "render health endpoint",
        "AIOS_AUTH_MODE": "render auth mode env",
        "AIOS_BASIC_AUTH_USER": "render auth user secret",
        "AIOS_BASIC_AUTH_PASSWORD": "render auth password secret",
        "AIOS_WHATSAPP_REPLY_MODE": "render whatsapp hold mode env",
        "AIOS_WHATSAPP_VERIFY_TOKEN": "render whatsapp verify token secret",
    }
    return [
        {"name": f"render:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_railway_config() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "railway.json")
    ignore_text = _read_text(AIOS_ROOT / ".railwayignore")
    checks = []
    try:
        config = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        config = {}
        checks.append({"name": "railway:valid json", "passed": False, "error": str(exc)})
    else:
        checks.append({"name": "railway:valid json", "passed": bool(config), "path": "railway.json"})
    start_command = str((config.get("deploy") or {}).get("startCommand", ""))
    checks.extend(
        [
            {
                "name": "railway:dockerfile builder",
                "passed": (config.get("build") or {}).get("builder") == "DOCKERFILE",
                "value": (config.get("build") or {}).get("builder"),
            },
            {
                "name": "railway:dockerfile path",
                "passed": (config.get("build") or {}).get("dockerfilePath") == "Dockerfile",
                "value": (config.get("build") or {}).get("dockerfilePath"),
            },
            {
                "name": "railway:start command",
                "passed": "python3 -m aios_runtime_production_up" in start_command
                and "--host 0.0.0.0" in start_command
                and "--port ${PORT:-8765}" in start_command
                and start_command.startswith("sh -c"),
                "value": start_command,
            },
            {
                "name": "railway:python wrapper present",
                "passed": (AIOS_ROOT / "aios_runtime_production_up.py").exists(),
                "path": "aios_runtime_production_up.py",
            },
            {
                "name": "docker:runtime script still bundled",
                "passed": "aios_live_api_server.py" in _read_text(AIOS_ROOT / "Dockerfile"),
                "path": "Dockerfile",
            },
            {
                "name": "railway:legacy unsafe shell port expansion removed",
                "passed": (
                    "aios_live_api_server.py" not in start_command
                    and "--port $PORT" not in start_command
                    and "--port ${PORT}" not in start_command
                ),
                "value": start_command,
            },
            {
                "name": "railway:wrapper dispatches live server",
                "passed": "aios_live_api_server import main" in _read_text(AIOS_ROOT / "aios_runtime_production_up.py")
                and "--host 0.0.0.0" in start_command
                and "raise SystemExit(main())" in _read_text(AIOS_ROOT / "aios_runtime_production_up.py"),
                "path": "aios_runtime_production_up.py",
            },
            {
                "name": "railway:health endpoint",
                "passed": (config.get("deploy") or {}).get("healthcheckPath") == "/api/health",
                "value": (config.get("deploy") or {}).get("healthcheckPath"),
            },
            {
                "name": "railway:health timeout",
                "passed": int((config.get("deploy") or {}).get("healthcheckTimeout") or 0) >= 300,
                "value": (config.get("deploy") or {}).get("healthcheckTimeout"),
            },
            {
                "name": "railway:runtime reports ignored",
                "passed": "automation/central_orchestrator/reports" in ignore_text,
                "path": ".railwayignore",
            },
            {
                "name": "railway:local tools ignored",
                "passed": ".tools" in ignore_text and ".tools/**" in ignore_text,
                "path": ".railwayignore",
            },
            {
                "name": "railway:mobile build outputs ignored",
                "passed": "android/**" in ignore_text and "mobile-dist/**" in ignore_text,
                "path": ".railwayignore",
            },
            {
                "name": "railway:evidence outputs ignored",
                "passed": "evidence/**" in ignore_text and "automation/evidence/**" in ignore_text,
                "path": ".railwayignore",
            },
            {
                "name": "railway:large brand binaries ignored",
                "passed": "knowledge-base/branding/assets/**" in ignore_text,
                "path": ".railwayignore",
            },
            {
                "name": "railway:secrets ignored",
                "passed": ".env.production" in ignore_text and ".env" in ignore_text,
                "path": ".railwayignore",
            },
        ]
    )
    return checks


def _check_dockerfile() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "Dockerfile")
    required = {
        "FROM python:3.12-slim": "python base image",
        "EXPOSE 8765": "runtime port",
        "aios_live_api_server.py": "runtime start command",
    }
    return [
        {"name": f"docker:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_service_worker_delivery_contract() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "aios-service-worker.js")
    shell = ""
    if "const AIOS_SHELL" in text:
        shell = text.split("const AIOS_SHELL", 1)[1].split("];", 1)[0]
    protected_pages = ["AIOS-DASHBOARD.html", "AIOS-MOBILE-APP.html", "AIOS-RUNTIME-STATUS.html"]
    return [
        {
            "name": "service-worker:current cache version",
            "passed": 'AIOS_CACHE = "aios-presence-v86"' in text,
            "path": "aios-service-worker.js",
        },
        {
            "name": "service-worker:no protected page precache",
            "passed": not any(page in shell for page in protected_pages),
            "protected_pages": protected_pages,
        },
        {
            "name": "service-worker:defines protected runtime cache exclusions",
            "passed": "AIOS_PROTECTED_PATHS" in text
            and all(page in text for page in protected_pages)
            and text.count("!AIOS_PROTECTED_PATHS.has(url.pathname)") >= 2,
            "protected_pages": protected_pages,
        },
        {
            "name": "service-worker:no cinematic video precache",
            "passed": "aios-eye-cinematic-loop-" not in shell,
            "path": "aios-service-worker.js",
        },
        {
            "name": "service-worker:no cinematic video runtime cache",
            "passed": '!url.pathname.startsWith("/assets/aios-eye-cinematic-loop-")' in text,
            "path": "aios-service-worker.js",
        },
    ]


def _check_public_website_delivery_contract() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "AIOS-WEBSITE.html")
    dashboard_text = _read_text(AIOS_ROOT / "AIOS-DASHBOARD.html")
    mobile_text = _read_text(AIOS_ROOT / "AIOS-MOBILE-APP.html")
    runtime_status_text = _read_text(AIOS_ROOT / "AIOS-RUNTIME-STATUS.html")
    offline_text = _read_text(AIOS_ROOT / "offline.html")
    return [
        {
            "name": "website:no protected command data fetch on hosted landing",
            "passed": 'location.protocol === "file:"' in text
            and 'fetch("/api/health", { cache: "no-store" })' in text,
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "website:eye video delayed load",
            "passed": 'preload="none"' in text
            and 'data-src="assets/aios-eye-cinematic-loop-phase55.mp4"' in text
            and "loadCinematicEyeVideo" in text
            and "schedulePremiumMotion(loadCinematicEyeVideo" in text,
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "website:eye visible from first frame",
            "passed": "@keyframes siteEyeWake { 0% { opacity: .92;" in text,
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "website:premium motion respects device constraints",
            "passed": "shouldUsePremiumMotion" in text
            and "connection.saveData" in text
            and "navigator.hardwareConcurrency" in text
            and "navigator.deviceMemory" in text,
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "website:background motion starts after critical entry",
            "passed": "schedulePremiumMotion(startPresenceMaterialWebGL" in text
            and "schedulePremiumMotion(startSiteCinematicCanvas" in text
            and "schedulePremiumMotion(startSiteEyeCanvas" in text
            and "schedulePremiumMotion(startSiteEyeWebGL" in text
            and "window.setTimeout(releaseEntry, 1900)" in text,
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "website:defer hosted data until after entry",
            "passed": "scheduleAfterEntry(loadData" in text
            and "window.setTimeout(startCinematicEntry, 1300);" in text
            and "schedulePremiumMotion(startSiteEyeCanvas" in text
            and "schedulePremiumMotion(startSiteEyeWebGL" in text
            and text.index("scheduleAfterEntry(loadData") > text.index("window.setTimeout(startCinematicEntry, 1300);"),
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "website:below fold render containment",
            "passed": "content-visibility: auto" in text and "contain-intrinsic-size" in text,
            "path": "AIOS-WEBSITE.html",
        },
        {
            "name": "dashboard:premium motion respects device constraints",
            "passed": "shouldRunEyePremiumMotion" in dashboard_text
            and "connection.saveData" in dashboard_text
            and "navigator.hardwareConcurrency" in dashboard_text
            and "navigator.deviceMemory" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:no native browser dialogs",
            "passed": all(term not in dashboard_text for term in ("prompt(", "alert(", "confirm(")),
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:planner edits inline",
            "passed": "slot-editor" in dashboard_text
            and "aria-label=\"Plan item" in dashboard_text
            and "editor.addEventListener('keydown'" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:command eye has measurable ambient motion",
            "passed": "eyeCommandLivingFloat" in dashboard_text
            and "eyeCommandLivingLight" in dashboard_text
            and "animation: eyeCommandLivingFloat" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:api base storage access guarded",
            "passed": "try {\n      configured = configured || localStorage.getItem('AIOS_API_BASE_URL')" in dashboard_text
            and "catch (_) {}" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "mobile:api base storage access guarded",
            "passed": 'try {\n      configured = configured || localStorage.getItem("AIOS_API_BASE_URL")' in mobile_text
            and "catch (_) {}" in mobile_text,
            "path": "AIOS-MOBILE-APP.html",
        },
        {
            "name": "runtime-status:component output escaped",
            "passed": "function escapeHTML(value)" in runtime_status_text
            and "function renderComponents(components)" in runtime_status_text
            and "escapeHTML(item.name)" in runtime_status_text
            and "escapeHTML(item.capability)" in runtime_status_text
            and "escapeHTML(item.file)" in runtime_status_text,
            "path": "AIOS-RUNTIME-STATUS.html",
        },
        {
            "name": "runtime-status:api base storage access guarded",
            "passed": "function safeConfiguredApiBase()" in runtime_status_text
            and "try {" in runtime_status_text
            and "localStorage.getItem('AIOS_API_BASE_URL')" in runtime_status_text
            and "catch (_)" in runtime_status_text,
            "path": "AIOS-RUNTIME-STATUS.html",
        },
        {
            "name": "offline:declares favicon to avoid browser fallback 404",
            "passed": '<link rel="icon" href="/assets/aios-icon-192.png" type="image/png">' in offline_text,
            "path": "offline.html",
        },
    ]


def _check_live_api_contract() -> list[dict[str, Any]]:
    server_text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/aios_live_api_server.py")
    hosted_validator_text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/validate_hosted_runtime.py")
    performance_validator_text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/validate_runtime_performance.py")
    landing_boot_validator_text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/validate_landing_boot_performance.py")
    visual_validator_text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/validate_visual_presence.py")
    dashboard_text = _read_text(AIOS_ROOT / "AIOS-DASHBOARD.html")
    mobile_text = _read_text(AIOS_ROOT / "AIOS-MOBILE-APP.html")
    return [
        {
            "name": "api:command center data route",
            "passed": 'path == "/api/command-center/data"' in server_text and "get_command_center_data()" in server_text,
            "path": "automation/central_orchestrator/runtime/aios_live_api_server.py",
        },
        {
            "name": "api:gzip json responses",
            "passed": "Content-Encoding" in server_text and "gzip.compress(body)" in server_text,
            "path": "automation/central_orchestrator/runtime/aios_live_api_server.py",
        },
        {
            "name": "api:compact json responses by default",
            "passed": "separators=(\",\", \":\")" in server_text and "AIOS_JSON_PRETTY" in server_text,
            "path": "automation/central_orchestrator/runtime/aios_live_api_server.py",
        },
        {
            "name": "api:command center serialized response cache",
            "passed": "_write_command_center_data" in server_text
            and '"json_body"' in server_text
            and '"gzip_body"' in server_text
            and "_write_json_bytes(handler, 200, json_body, gzip_body=gzip_body)" in server_text,
            "path": "automation/central_orchestrator/runtime/aios_live_api_server.py",
        },
        {
            "name": "api:service worker served no-store",
            "passed": 'path == "/aios-service-worker.js"' in server_text and '"Cache-Control", "no-store"' in server_text,
            "path": "automation/central_orchestrator/runtime/aios_live_api_server.py",
        },
        {
            "name": "auth:server keeps public landing unauthenticated",
            "passed": "PUBLIC_STATIC_PATHS" in server_text
            and '"/AIOS-WEBSITE.html"' in server_text
            and '"/index.html"' in server_text
            and "PUBLIC_STATIC_PREFIXES = (\"/assets/\",)" in server_text
            and "if _public_static_path(path):" in server_text,
            "path": "automation/central_orchestrator/runtime/aios_live_api_server.py",
        },
        {
            "name": "hosted-validator:checks command center data api",
            "passed": "command_center_data_api" in hosted_validator_text and '"/api/command-center/data"' in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "hosted-validator:checks gzip command data",
            "passed": '"Accept-Encoding": "gzip"' in hosted_validator_text and "wire_bytes" in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "hosted-validator:checks command data size budgets",
            "passed": "COMMAND_CENTER_MAX_WIRE_BYTES" in hosted_validator_text
            and "COMMAND_CENTER_MAX_UNCOMPRESSED_BYTES" in hosted_validator_text
            and "compression_ratio" in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "performance-validator:checks command data warm-cache speed",
            "passed": "RUNTIME_PERFORMANCE_VALIDATION.json" in performance_validator_text
            and "command_center_warm_p95_response" in performance_validator_text
            and "command_center_warm_best_response" in performance_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_runtime_performance.py",
        },
        {
            "name": "landing-boot-validator:blocks early heavy video and command data",
            "passed": "LANDING_BOOT_PERFORMANCE_VALIDATION.json" in landing_boot_validator_text
            and "no_eye_video_request_during_boot_window" in landing_boot_validator_text
            and "no_command_center_data_on_public_surface" in landing_boot_validator_text
            and "command_center_data_request_budget" in landing_boot_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_landing_boot_performance.py",
        },
        {
            "name": "landing-boot-validator:blocks visible ai fingerprint terms",
            "passed": "FORBIDDEN_VISIBLE_AI_TERMS" in landing_boot_validator_text
            and "no_visible_ai_fingerprint_terms" in landing_boot_validator_text
            and "visibleText" in landing_boot_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_landing_boot_performance.py",
        },
        {
            "name": "visual-validator:uses combined gold green signal",
            "passed": "min_combined_signal_ratio" in visual_validator_text
            and "combined_signal_ratio" in visual_validator_text
            and "green_signal + gold_signal" in visual_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_visual_presence.py",
        },
        {
            "name": "hosted-validator:checks public website size budget",
            "passed": "PUBLIC_WEBSITE_MAX_BYTES" in hosted_validator_text and "max_bytes" in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "hosted-validator:checks public gzip delivery budgets",
            "passed": "PUBLIC_WEBSITE_MAX_GZIP_BYTES" in hosted_validator_text
            and "PUBLIC_SERVICE_WORKER_MAX_GZIP_BYTES" in hosted_validator_text
            and "_public_gzip_delivery_checks" in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "hosted-validator:checks current service worker delivery contract",
            "passed": "EXPECTED_SERVICE_WORKER_CACHE" in hosted_validator_text
            and "protected_precache" in hosted_validator_text
            and "protected_runtime_cache_excluded" in hosted_validator_text
            and "cache_control_no_store" in hosted_validator_text
            and "eye_video_precache" in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "hosted-validator:checks public landing without credentials",
            "passed": "auth:root_landing_without_credentials_public" in hosted_validator_text
            and "auth:website_without_credentials_public" in hosted_validator_text
            and "auth:service_worker_without_credentials_public" in hosted_validator_text
            and "auth:command_center_without_credentials_rejected" in hosted_validator_text,
            "path": "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
        },
        {
            "name": "dashboard:uses live command center data api when hosted",
            "passed": "aiosApiUrl('/api/command-center/data')" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:boots eye before command center hydration",
            "passed": "function bootEyeExperience()" in dashboard_text
            and "bootEyeExperience();" in dashboard_text
            and "scheduleCommandCenterHydration(() => loadCommandCenterData()" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:applies initial route before hydration",
            "passed": "const initialRouteParams = new URLSearchParams(window.location.search)" in dashboard_text
            and "if (allowedScreens.includes(initialScreen)) showPage(initialScreen);" in dashboard_text
            and dashboard_text.find("if (allowedScreens.includes(initialScreen)) showPage(initialScreen);") < dashboard_text.find("bootEyeExperience();"),
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "dashboard:uses live runtime status api when hosted",
            "passed": "aiosApiUrl('/api/runtime/status')" in dashboard_text
            and "location.protocol === 'file:' ? 'automation/central_orchestrator/reports/AIOS_RUNTIME_STATUS.json'" in dashboard_text,
            "path": "AIOS-DASHBOARD.html",
        },
        {
            "name": "mobile:uses live command center data api when hosted",
            "passed": "aiosApiUrl(\"/api/command-center/data\")" in mobile_text,
            "path": "AIOS-MOBILE-APP.html",
        },
    ]


def _check_docs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "DEPLOYMENT.md")
    needles = [
        "Hosted Validation",
        "Visual Presence Validation",
        "Eye Motion Validation",
        "Public Beta Gate",
        "AIOS_BASIC_AUTH_USER",
        "validate_public_beta.py",
        "validate_eye_motion.py",
        "validate_container_runtime.py",
        "validate_host_environment.py",
        "validate_production_launch_readiness.py",
        "deployment_preflight.py",
        "sync_railway_environment.py",
        "deploy_railway_production.py",
        "finalize_production_hosting.py",
        "run_production_hosting_pipeline.py",
        "build_deployment_bundle.py",
        "prepare_production_release.py",
        "/api/deployment/status",
        "/api/launch/readiness",
        "/api/whatsapp/hosted-test",
        "/webhook/whatsapp/provider/gateway",
        "AIOS_WHATSAPP_REPLY_MODE=hold",
        "AIOS_WHATSAPP_VERIFY_TOKEN",
        "unauthenticated access",
        "DEPLOYMENT_PREFLIGHT.json",
        "PRODUCTION_LAUNCH_READINESS.json",
        "PRODUCTION_RELEASE_CANDIDATE.json",
        "CONTAINER_RUNTIME_VALIDATION.json",
        "HOST_ENVIRONMENT_VALIDATION.json",
        "RAILWAY_ENVIRONMENT_SYNC.json",
        "deployment-bundles",
        "PRODUCTION_HOSTING_PUBLIC_FINALIZATION.json",
        "PRODUCTION_HOSTING_PIPELINE_RUN.json",
    ]
    return [{"name": f"docs:{needle}", "passed": needle in text, "needle": needle} for needle in needles]


def _check_bundle_builder() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/build_deployment_bundle.py")
    required = {
        '".tools"': "exclude local tool root",
        '".tools/*"': "exclude local tool contents",
        '"android/**"': "exclude native Android build outputs",
        '"mobile-dist/**"': "exclude generated mobile web build",
        '"evidence/**"': "exclude generated evidence screenshots",
        '"automation/evidence/**"': "exclude generated automation evidence",
        '"assets/aios-eye-cinematic-loop-phase52.mp4"': "exclude stale Eye video phase 52",
        '"assets/aios-eye-cinematic-loop-phase53.mp4"': "exclude stale Eye video phase 53",
        '"assets/aios-eye-cinematic-loop-phase54.mp4"': "exclude stale Eye video phase 54",
        '"knowledge-base/branding/assets/**"': "exclude large brand binary assets",
        '"railway.json"': "require railway config in bundle",
        '".railwayignore"': "require railway ignore in bundle",
        '"automation/central_orchestrator/runtime/sync_railway_environment.py"': "require railway env sync in bundle",
        '"automation/central_orchestrator/runtime/validate_runtime_performance.py"': "require runtime performance validator in bundle",
        '"automation/central_orchestrator/runtime/validate_landing_boot_performance.py"': "require landing boot performance validator in bundle",
        '"automation/central_orchestrator/runtime/deploy_railway_production.py"': "require railway deploy runner in bundle",
        '"automation/central_orchestrator/runtime/finalize_production_hosting.py"': "require production hosting finalizer in bundle",
        '"automation/central_orchestrator/runtime/run_production_hosting_pipeline.py"': "require production hosting pipeline in bundle",
    }
    return [
        {"name": f"bundle:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_railway_deploy_runner() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/deploy_railway_production.py")
    required = {
        '"domain", "list", "--json"': "collect railway domain list",
        '"variable", "list", "--json"': "inspect remote railway env without printing values",
        "for timeout in (45, 90)": "retry slow railway env inspection",
        "effective_environment": "separate local env from effective deployment env",
        "LOCAL_RELEASE_REFRESH_COMMANDS": "defines local release refresh commands",
        "_refresh_local_release": "refreshes local release evidence before readiness",
        "_refresh_local_speed_evidence": "refreshes local boot and runtime speed evidence",
        "validate_landing_boot_performance.py": "refreshes browser boot performance evidence",
        "validate_runtime_performance.py": "refreshes runtime performance evidence",
        "local_validation_server_health_timeout": "blocks release when local speed server is not healthy",
        "terminate local validation server": "stops local validation server after speed refresh",
        "_source_freshness": "checks validation freshness against source files",
        "stale_sources": "reports stale source files for release evidence",
        "validate_deployment_package.py": "refreshes deployment package validation",
        "deployment_package_validation_stale": "blocks stale deployment package validation",
        "validate_container_runtime.py": "refreshes container runtime validation",
        "container_runtime_validation_stale": "blocks stale container runtime validation",
        "LANDING_BOOT_PERFORMANCE_VALIDATION.json": "requires boot performance validation for readiness",
        "boot_performance_validation_not_passed": "blocks release when boot performance fails",
        "boot_performance_validation_stale": "blocks stale boot performance validation",
        "RUNTIME_PERFORMANCE_VALIDATION.json": "requires runtime performance validation for readiness",
        "runtime_performance_validation_not_passed": "blocks release when runtime performance fails",
        "runtime_performance_validation_stale": "blocks stale runtime performance validation",
        "build_deployment_bundle.py": "refreshes deployment bundle artifact",
        "blocked_local_release_refresh_failed": "blocks deploy when refresh fails",
        "--no-refresh-local-release": "allows explicit refresh bypass for diagnostics",
        "ensure_domain": "support explicit domain generation",
        "public_url_candidates": "capture public url candidates",
        "_extract_domains_from_service_instance": "capture existing service domains in check mode",
        "PUBLIC_URL_PATTERN": "extract public urls from railway output",
    }
    return [
        {"name": f"railway-runner:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_delivery_audit_tooling() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/delivery_audit_aios.py")
    required = {
        '"base_url"': "accepts explicit hosted base url argument",
        "AIOS_PUBLIC_BASE_URL": "uses public base url env fallback",
        "--auth-user-env": "supports configurable auth user env",
        "--auth-password-env": "supports configurable auth password env",
        "--expected-cache": "supports exact service worker cache assertion",
        "EXPECTED_SERVICE_WORKER_CACHE = \"aios-presence-v86\"": "requires current release service worker cache",
        "service_worker_protected_runtime_cache_excluded": "audits protected runtime cache exclusion",
        "service_worker_cache_control_no_store": "audits service worker no-store delivery",
        "BASE = args.base_url.rstrip": "normalizes audited base url",
    }
    return [
        {"name": f"delivery-audit:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_railway_env_sync() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/sync_railway_environment.py")
    required = {
        "RAILWAY_ENVIRONMENT_SYNC.json": "writes redacted env sync report",
        '"--stdin"': "uses stdin for secret values",
        "SECRET_ENV": "tracks secret env keys",
        "stdout\": \"\" if stdin is not None": "suppresses secret command stdout",
    }
    return [
        {"name": f"railway-env:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_public_finalizer() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/finalize_production_hosting.py")
    required = {
        "RAILWAY_PRODUCTION_DEPLOYMENT_RUN.json": "read railway deploy-run evidence",
        "public_url_candidates": "use railway url candidates",
        "AIOS_PUBLIC_BASE_URL": "use public base url env",
        "RAILWAY_PUBLIC_DOMAIN": "use railway public domain env",
        ".railway/bin/railway": "find local railway cli install",
    }
    return [
        {"name": f"finalizer:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def _check_production_hosting_pipeline() -> list[dict[str, Any]]:
    text = _read_text(AIOS_ROOT / "automation/central_orchestrator/runtime/run_production_hosting_pipeline.py")
    required = {
        "sync_railway_environment.py": "runs railway env sync",
        "deploy_railway_production.py": "runs railway deploy runner",
        "finalize_production_hosting.py": "runs public finalizer",
        "PRODUCTION_HOSTING_PIPELINE_RUN.json": "writes pipeline report",
        "classification": "emits final classification",
    }
    return [
        {"name": f"pipeline:{label}", "passed": needle in text, "needle": needle}
        for needle, label in required.items()
    ]


def validate() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    checks = []
    checks.extend(_check_required_files(manifest))
    checks.extend(_check_env_template(manifest))
    checks.extend(_check_render_yaml())
    checks.extend(_check_railway_config())
    checks.extend(_check_dockerfile())
    checks.extend(_check_service_worker_delivery_contract())
    checks.extend(_check_public_website_delivery_contract())
    checks.extend(_check_live_api_contract())
    checks.extend(_check_docs(manifest))
    checks.extend(_check_bundle_builder())
    checks.extend(_check_railway_env_sync())
    checks.extend(_check_railway_deploy_runner())
    checks.extend(_check_delivery_audit_tooling())
    checks.extend(_check_public_finalizer())
    checks.extend(_check_production_hosting_pipeline())
    passed = all(item["passed"] for item in checks)
    report = {
        "validated_at": _now(),
        "passed": passed,
        "checks_passed": sum(1 for item in checks if item["passed"]),
        "checks_total": len(checks),
        "manifest": str(MANIFEST_PATH.relative_to(AIOS_ROOT)) if MANIFEST_PATH.exists() else "",
        "checks": checks,
        "next_action": "Deploy to permanent host and run validate_public_beta.py." if passed else "Fix failed deployment package checks before hosting.",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = validate()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
