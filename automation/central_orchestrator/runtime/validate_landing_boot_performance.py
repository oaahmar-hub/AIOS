#!/usr/bin/env python3
"""Browser-level validation for the AIOS public landing boot path."""
from __future__ import annotations

import argparse
import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_PATH = REPORTS_DIR / "LANDING_BOOT_PERFORMANCE_VALIDATION.json"
DEFAULT_BASE_URL = os.getenv("AIOS_BOOT_BASE_URL", "http://127.0.0.1:8881")
PLAYWRIGHT_HEADLESS_SHELL = Path.home() / "Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-x64/chrome-headless-shell"

BOOT_WINDOW_MS = int(os.getenv("AIOS_BOOT_WINDOW_MS", "850"))
MAX_DOM_CONTENT_LOADED_MS = int(os.getenv("AIOS_BOOT_DCL_MAX_MS", "1600"))
MAX_FIRST_PAINT_PROXY_MS = int(os.getenv("AIOS_BOOT_FIRST_PAINT_PROXY_MAX_MS", "1200"))
FORBIDDEN_VISIBLE_AI_TERMS = [
    "chatgpt",
    "openai",
    "claude",
    "gpt",
    "prompt",
    "ai agent",
    "chatbot",
    "bot",
]
TARGETS = [
    {
        "name": "website",
        "path": "/AIOS-WEBSITE.html",
        "auth": False,
        "selector": ".site-eye",
        "viewport": {"width": 1440, "height": 1000},
        "max_primary_visible_ms": 1200,
        "forbid_command_data": True,
        "section_selector": "#brains",
    },
    {
        "name": "command_center",
        "path": "/AIOS-DASHBOARD.html?screen=eye",
        "auth": True,
        "selector": ".eye-core",
        "viewport": {"width": 1440, "height": 1000},
        "max_primary_visible_ms": 1400,
        "max_command_data_requests": 1,
    },
    {
        "name": "mobile_console",
        "path": "/AIOS-MOBILE-APP.html",
        "auth": True,
        "selector": ".mobile-eye",
        "viewport": {"width": 390, "height": 844},
        "max_primary_visible_ms": 1200,
        "max_command_data_requests": 1,
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _browser_executable() -> str:
    explicit = os.getenv("AIOS_RENDER_CHROME", "").strip()
    if explicit:
        return explicit
    if PLAYWRIGHT_HEADLESS_SHELL.exists():
        return str(PLAYWRIGHT_HEADLESS_SHELL)
    return ""


def _auth_header(user: str, password: str) -> str:
    if not user and not password:
        return ""
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _validate_target(browser, base_url: str, target: dict[str, Any], *, auth_header: str) -> dict[str, Any]:
    headers = {"Cache-Control": "no-cache"}
    if target.get("auth") and auth_header:
        headers["Authorization"] = auth_header
    requests: list[dict[str, Any]] = []
    context = browser.new_context(
        viewport=target["viewport"],
        reduced_motion="no-preference",
        extra_http_headers=headers,
        is_mobile=bool(target.get("is_mobile")),
    )
    page = context.new_page()
    started = time.perf_counter()

    def on_request(request) -> None:
        requests.append(
            {
                "url": request.url,
                "resource_type": request.resource_type,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )

    page.on("request", on_request)
    response = page.goto(_url(base_url, target["path"]), wait_until="domcontentloaded", timeout=15000)
    dom_content_loaded_ms = round((time.perf_counter() - started) * 1000, 2)
    page.wait_for_selector(target["selector"], state="visible", timeout=8000)
    primary_visible_ms = round((time.perf_counter() - started) * 1000, 2)
    page.wait_for_timeout(1300)
    final_elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    section_selector = target.get("section_selector") or ""
    state = page.evaluate(
        """selector => ({
          readyState: document.readyState,
          primaryVisible: !!document.querySelector(selector),
          sectionContainment: document.querySelector('#brains') ? getComputedStyle(document.querySelector('#brains')).contentVisibility : '',
          commandDataFetchPresent: performance.getEntriesByType('resource').some(e => e.name.includes('/api/command-center/data')),
          videoFetches: performance.getEntriesByType('resource').filter(e => e.name.includes('aios-eye-cinematic-loop')).map(e => ({name: e.name, startTime: Math.round(e.startTime)})),
          visibleText: document.body ? document.body.innerText : ''
        })""",
        target["selector"],
    )
    context.close()

    video_requests = [item for item in requests if "aios-eye-cinematic-loop" in item["url"]]
    early_video_requests = [item for item in video_requests if float(item["elapsed_ms"]) <= BOOT_WINDOW_MS]
    command_data_requests = [item for item in requests if "/api/command-center/data" in item["url"]]
    visible_text = str(state.pop("visibleText", "") or "").lower()
    visible_ai_terms = [term for term in FORBIDDEN_VISIBLE_AI_TERMS if term in visible_text]
    max_primary_visible_ms = int(target.get("max_primary_visible_ms", MAX_FIRST_PAINT_PROXY_MS))
    checks = [
        {
            "name": f"{target['name']}:status_200",
            "passed": bool(response and response.status == 200),
            "status": response.status if response else 0,
        },
        {
            "name": f"{target['name']}:dom_content_loaded_fast",
            "passed": dom_content_loaded_ms <= MAX_DOM_CONTENT_LOADED_MS,
            "elapsed_ms": dom_content_loaded_ms,
            "budget_ms": MAX_DOM_CONTENT_LOADED_MS,
        },
        {
            "name": f"{target['name']}:primary_surface_visible_fast",
            "passed": primary_visible_ms <= max_primary_visible_ms,
            "elapsed_ms": primary_visible_ms,
            "budget_ms": max_primary_visible_ms,
            "selector": target["selector"],
        },
        {
            "name": f"{target['name']}:no_eye_video_request_during_boot_window",
            "passed": not early_video_requests,
            "boot_window_ms": BOOT_WINDOW_MS,
            "early_video_requests": early_video_requests,
        },
        {
            "name": f"{target['name']}:no_visible_ai_fingerprint_terms",
            "passed": not visible_ai_terms,
            "forbidden_terms": visible_ai_terms,
        },
    ]
    if target.get("forbid_command_data"):
        checks.append(
            {
                "name": f"{target['name']}:no_command_center_data_on_public_surface",
                "passed": not command_data_requests and not state.get("commandDataFetchPresent"),
                "requests": command_data_requests,
            }
        )
    else:
        max_requests = int(target.get("max_command_data_requests", 1))
        checks.append(
            {
                "name": f"{target['name']}:command_center_data_request_budget",
                "passed": len(command_data_requests) <= max_requests,
                "request_count": len(command_data_requests),
                "budget": max_requests,
            }
        )
    if section_selector:
        checks.append(
            {
                "name": f"{target['name']}:below_fold_content_visibility_active",
                "passed": state.get("sectionContainment") == "auto",
                "content_visibility": state.get("sectionContainment"),
            }
        )
    return {
        "name": target["name"],
        "path": target["path"],
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "timing": {
            "dom_content_loaded_ms": dom_content_loaded_ms,
            "primary_visible_ms": primary_visible_ms,
            "final_elapsed_ms": final_elapsed_ms,
        },
        "state": state,
        "network_summary": {
            "request_count": len(requests),
            "video_request_count": len(video_requests),
            "command_center_data_request_count": len(command_data_requests),
        },
        "requests": requests,
    }


def validate(base_url: str, *, auth_header: str) -> dict[str, Any]:
    executable = _browser_executable()
    if not executable:
        report = {
            "validated_at": _now(),
            "base_url": base_url.rstrip("/"),
            "passed": False,
            "checks_passed": 0,
            "checks_total": 1,
            "checks": [{"name": "browser_executable_available", "passed": False, "executable": ""}],
            "blockers": ["no_chromium_executable_found"],
        }
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return report
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=executable,
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        targets = [_validate_target(browser, base_url, target, auth_header=auth_header) for target in TARGETS]
        browser.close()
    checks = [check for target in targets for check in target["checks"]]
    report = {
        "validated_at": _now(),
        "base_url": base_url.rstrip("/"),
        "passed": all(item["passed"] for item in checks),
        "checks_passed": sum(1 for item in checks if item["passed"]),
        "checks_total": len(checks),
        "checks": checks,
        "browser": {"executable": executable},
        "targets": targets,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AIOS landing browser boot behavior.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--auth-user-env", default="AIOS_BASIC_AUTH_USER")
    parser.add_argument("--auth-password-env", default="AIOS_BASIC_AUTH_PASSWORD")
    args = parser.parse_args()
    auth_header = _auth_header(os.getenv(args.auth_user_env, ""), os.getenv(args.auth_password_env, ""))
    report = validate(args.base_url, auth_header=auth_header)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
