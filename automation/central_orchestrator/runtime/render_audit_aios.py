#!/usr/bin/env python3
from __future__ import annotations

import base64
from html.parser import HTMLParser
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "evidence" / "render-audit"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://aios-runtime-production.up.railway.app"
USER = os.getenv("AIOS_BASIC_AUTH_USER", "").strip()
PASSWORD = os.getenv("AIOS_BASIC_AUTH_PASSWORD", "")
AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode() if USER and PASSWORD else ""
CHROME = os.getenv("AIOS_RENDER_CHROME", "").strip()
PLAYWRIGHT_HEADLESS_SHELL = Path.home() / "Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-x64/chrome-headless-shell"

TARGETS = [
    {"name": "home_desktop", "path": "/", "auth": False, "viewport": {"width": 1440, "height": 1000}},
    {"name": "website_desktop", "path": "/AIOS-WEBSITE.html", "auth": False, "viewport": {"width": 1440, "height": 1000}},
    {"name": "website_mobile", "path": "/AIOS-WEBSITE.html", "auth": False, "viewport": {"width": 390, "height": 844}, "is_mobile": True},
    {"name": "dashboard_desktop", "path": "/AIOS-DASHBOARD.html", "auth": True, "viewport": {"width": 1440, "height": 1000}},
    {"name": "mobile_console", "path": "/AIOS-MOBILE-APP.html", "auth": True, "viewport": {"width": 390, "height": 844}, "is_mobile": True},
    {"name": "runtime_status", "path": "/AIOS-RUNTIME-STATUS.html", "auth": True, "viewport": {"width": 1440, "height": 900}},
]


class SurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.h1 = ""
        self.links: list[str] = []
        self.assets: list[str] = []
        self.text_parts: list[str] = []
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        self._tag_stack.append(tag.lower())
        attr = {key.lower(): value for key, value in attrs if key and value}
        if tag.lower() == "a" and attr.get("href"):
            self.links.append(attr["href"])
        if tag.lower() in {"img", "script", "video", "source", "link"}:
            ref = attr.get("src") or attr.get("href")
            if ref:
                self.assets.append(ref)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index] == tag:
                del self._tag_stack[index:]
                break

    def handle_data(self, data: str) -> None:
        stripped = " ".join(data.split())
        if not stripped:
            return
        self.text_parts.append(stripped)
        if self._tag_stack and self._tag_stack[-1] == "title" and not self.title:
            self.title = stripped[:160]
        if "h1" in self._tag_stack and not self.h1:
            self.h1 = stripped[:160]


def browser_executable() -> str:
    if CHROME:
        return CHROME
    if PLAYWRIGHT_HEADLESS_SHELL.exists():
        return str(PLAYWRIGHT_HEADLESS_SHELL)
    return ""


def chromium_smoke_test() -> dict:
    executable = browser_executable()
    if not executable:
        return {"pass": False, "error": "no_chromium_executable_found", "executable": ""}
    profile = tempfile.mkdtemp(prefix="aios-render-smoke-")
    screenshot = OUT / "chromium_smoke.png"
    cmd = [
        executable,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        "--window-size=800,600",
        f"--screenshot={screenshot}",
        "data:text/html,<h1>ok</h1>",
    ]
    started = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return {
            "pass": False,
            "error": "chromium_smoke_timeout",
            "executable": executable,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "stderr_tail": (stderr or "")[-800:],
            "stdout_tail": (stdout or "")[-800:],
        }
    return {
        "pass": proc.returncode == 0 and screenshot.exists() and screenshot.stat().st_size > 0,
        "returncode": proc.returncode,
        "executable": executable,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "screenshot": str(screenshot.relative_to(ROOT)) if screenshot.exists() else None,
        "screenshot_bytes": screenshot.stat().st_size if screenshot.exists() else 0,
        "stderr_tail": (stderr or "")[-800:],
        "stdout_tail": (stdout or "")[-800:],
    }


def request_url(url: str, auth: bool = False) -> dict:
    headers = {"User-Agent": "AIOSRenderFallbackAudit/1.0", "Accept-Encoding": "identity"}
    if auth:
        if not AUTH:
            return {
                "status": 0,
                "bytes": 0,
                "text": "",
                "content_type": "",
                "elapsed_ms": 0,
                "attempt": 0,
                "error": "missing_basic_auth_env",
                "url": url,
            }
        headers["Authorization"] = AUTH
    last: dict = {}
    for attempt in range(1, 4):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                raw = response.read()
                return {
                    "status": response.status,
                    "bytes": len(raw),
                    "text": raw.decode("utf-8", errors="ignore"),
                    "content_type": response.headers.get("Content-Type", ""),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                    "attempt": attempt,
                    "url": response.geturl(),
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return {
                "status": exc.code,
                "bytes": len(raw),
                "text": raw.decode("utf-8", errors="ignore"),
                "content_type": exc.headers.get("Content-Type", ""),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "attempt": attempt,
                "error": raw.decode("utf-8", errors="replace")[:400],
                "url": exc.geturl(),
            }
        except Exception as exc:
            last = {
                "status": 0,
                "bytes": 0,
                "text": "",
                "content_type": "",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "attempt": attempt,
                "error": str(exc),
                "url": url,
            }
            time.sleep(min(1.5 * attempt, 4))
    return last


def audit_static_surface(target: dict) -> dict:
    url = BASE + target["path"]
    result = request_url(url, auth=bool(target.get("auth")))
    parser = SurfaceParser()
    if result["text"]:
        parser.feed(result["text"])
    text = " ".join(parser.text_parts)
    file_refs = [ref for ref in parser.links + parser.assets if ref.startswith("file://")]
    old_eye_refs = [ref for ref in parser.links + parser.assets if any(phase in ref for phase in ["phase52", "phase53", "phase54"])]
    asset_refs = []
    for ref in parser.assets:
        if not ref or ref.startswith(("data:", "mailto:", "tel:", "#")):
            continue
        parsed = urlparse(ref)
        if parsed.scheme and parsed.netloc and parsed.netloc != urlparse(BASE).netloc:
            continue
        if ref.startswith("#"):
            continue
        asset_refs.append(urljoin(url, ref))
    checked_assets = []
    for asset_url in sorted(set(asset_refs))[:24]:
        asset = request_url(asset_url, auth=bool(target.get("auth")) and not _public_asset(asset_url))
        checked_assets.append(
            {
                "url": asset_url,
                "status": asset["status"],
                "bytes": asset["bytes"],
                "content_type": asset.get("content_type", ""),
                "pass": asset["status"] == 200 and asset["bytes"] > 0,
            }
        )
    min_bytes = 500 if target["name"] in {"pwa_manifest", "service_worker"} else 5000
    minimum_text = 200 if target["path"].endswith(".html") or ".html" in target["path"] or target["path"] == "/" else 0
    passed = (
        result["status"] == 200
        and result["bytes"] >= min_bytes
        and len(text) >= minimum_text
        and not file_refs
        and not old_eye_refs
        and all(item["pass"] for item in checked_assets)
    )
    return {
        "name": target["name"],
        "url": url,
        "status": result["status"],
        "bytes": result["bytes"],
        "elapsed_ms": result.get("elapsed_ms", 0),
        "attempt": result.get("attempt"),
        "error": result.get("error", ""),
        "title": parser.title,
        "h1": parser.h1,
        "text_length": len(text),
        "asset_count": len(asset_refs),
        "checked_assets": checked_assets,
        "file_refs": file_refs,
        "old_eye_refs": old_eye_refs,
        "pass": passed,
    }


def _public_asset(asset_url: str) -> bool:
    path = urlparse(asset_url).path
    return path.startswith("/assets/") or path in {"/aios-service-worker.js", "/aios.webmanifest", "/offline.html"}


def static_surface_audit() -> dict:
    results = [audit_static_surface(target) for target in TARGETS]
    return {
        "passed": all(item["pass"] for item in results),
        "summary": {"checks_passed": sum(1 for item in results if item["pass"]), "checks_total": len(results)},
        "results": results,
    }


def write_blocker_payload(smoke: dict) -> int:
    static_audit = static_surface_audit()
    static_checks_passed = static_audit["summary"]["checks_passed"]
    static_checks_total = static_audit["summary"]["checks_total"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "passed": False,
        "checks_passed": 0,
        "checks_total": len(TARGETS),
        "summary": {
            "screenshot_checks_passed": 0,
            "screenshot_checks_total": len(TARGETS),
            "static_checks_passed": static_checks_passed,
            "static_checks_total": static_checks_total,
        },
        "blocker": "local_chromium_cannot_start",
        "chromium_smoke": smoke,
        "static_surface_audit": static_audit,
        "static_surface_passed": static_audit["passed"],
        "static_checks_passed": static_checks_passed,
        "static_checks_total": static_checks_total,
        "results": [],
    }
    (OUT / "render_audit_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 2


def audit_page(browser, target: dict) -> dict:
    context_kwargs = {
        "viewport": target["viewport"],
        "device_scale_factor": 1,
        "is_mobile": bool(target.get("is_mobile")),
        "has_touch": bool(target.get("is_mobile")),
    }
    if target.get("auth"):
        if not AUTH:
            raise RuntimeError("missing_basic_auth_env")
        context_kwargs["extra_http_headers"] = {"Authorization": AUTH}
    context = browser.new_context(**context_kwargs)
    page = context.new_page()
    page.set_default_timeout(12000)
    console = []
    requests = []
    failed = []
    page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text[:500]}))
    page.on("requestfinished", lambda req: requests.append(req.url))
    page.on("requestfailed", lambda req: failed.append({"url": req.url, "failure": (req.failure or {}).get("errorText", "unknown")}))
    url = BASE + target["path"]
    started = time.perf_counter()
    response = page.goto(url, wait_until="domcontentloaded", timeout=22000)
    dom_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        page.wait_for_load_state("load", timeout=8000)
    except Exception:
        pass
    loaded_ms = round((time.perf_counter() - started) * 1000, 1)
    page.wait_for_timeout(1200)
    metrics = page.evaluate(
        """() => {
            const body = document.body;
            const html = document.documentElement;
            const rect = body ? body.getBoundingClientRect() : {width:0,height:0};
            const firstH1 = document.querySelector('h1')?.innerText || '';
            const videos = Array.from(document.querySelectorAll('video')).map(v => ({
                src: v.currentSrc || v.src,
                readyState: v.readyState,
                paused: v.paused,
                width: v.videoWidth,
                height: v.videoHeight
            }));
            const canvases = Array.from(document.querySelectorAll('canvas')).map(c => ({
                w: c.width,
                h: c.height,
                cssW: Math.round(c.getBoundingClientRect().width),
                cssH: Math.round(c.getBoundingClientRect().height)
            }));
            const links = Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href'));
            return {
                title: document.title,
                firstH1,
                bodyTextLength: body?.innerText?.trim().length || 0,
                scrollWidth: html.scrollWidth,
                clientWidth: html.clientWidth,
                scrollHeight: html.scrollHeight,
                clientHeight: html.clientHeight,
                horizontalOverflow: html.scrollWidth > html.clientWidth + 2,
                viewport: {w: innerWidth, h: innerHeight},
                bodyRect: {width: Math.round(rect.width), height: Math.round(rect.height)},
                videos,
                canvases,
                fileLinks: links.filter(h => h && h.startsWith('file://')),
                oldEyeRefs: links.filter(h => h && /phase5[234]/.test(h)),
                visibleTextStart: (body?.innerText || '').trim().slice(0, 220)
            };
        }"""
    )
    screenshot = OUT / f"{target['name']}.png"
    screenshot_error = None
    try:
        page.evaluate("() => Array.from(document.querySelectorAll('video')).forEach(v => v.pause())")
        page.screenshot(path=str(screenshot), full_page=False, timeout=15000)
    except Exception as exc:
        screenshot_error = f"{type(exc).__name__}: {exc}"
    context.close()
    error_console = [m for m in console if m["type"] in {"error", "warning"}]
    return {
        "name": target["name"],
        "url": url,
        "status": response.status if response else None,
        "dom_ms": dom_ms,
        "loaded_ms": loaded_ms,
        "request_count": len(requests),
        "failed_requests": failed,
        "console_errors_warnings": error_console,
        "metrics": metrics,
        "screenshot": str(screenshot.relative_to(ROOT)) if screenshot.exists() else None,
        "screenshot_error": screenshot_error,
        "pass": bool((response and response.status == 200) and not failed and not metrics["horizontalOverflow"] and not metrics["fileLinks"] and not screenshot_error),
    }


def main() -> int:
    smoke = chromium_smoke_test()
    if not smoke["pass"]:
        return write_blocker_payload(smoke)
    with sync_playwright() as p:
        launch_kwargs = {"headless": True, "args": ["--disable-dev-shm-usage", "--disable-gpu"]}
        executable = browser_executable()
        if executable:
            launch_kwargs["executable_path"] = executable
        browser = p.chromium.launch(**launch_kwargs)
        results = []
        for target in TARGETS:
            try:
                results.append(audit_page(browser, target))
            except Exception as exc:
                results.append(
                    {
                        "name": target["name"],
                        "url": BASE + target["path"],
                        "status": None,
                        "dom_ms": None,
                        "loaded_ms": None,
                        "request_count": 0,
                        "failed_requests": [],
                        "console_errors_warnings": [],
                        "metrics": {},
                        "screenshot": None,
                        "screenshot_error": f"{type(exc).__name__}: {exc}",
                        "pass": False,
                    }
                )
        browser.close()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "results": results,
        "passed": all(result["pass"] for result in results),
        "checks_passed": sum(1 for result in results if result["pass"]),
        "checks_total": len(results),
        "summary": {"checks_passed": sum(1 for result in results if result["pass"]), "checks_total": len(results)},
    }
    (OUT / "render_audit_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    for result in results:
        metrics = result.get("metrics") or {}
        print(
            f"{result['name']} pass={result['pass']} status={result['status']} "
            f"dom_ms={result['dom_ms']} loaded_ms={result['loaded_ms']} "
            f"overflow={metrics.get('horizontalOverflow')} "
            f"screenshot_error={bool(result.get('screenshot_error'))} "
            f"console={len(result['console_errors_warnings'])} "
            f"failed={len(result['failed_requests'])} screenshot={result['screenshot']}"
        )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
