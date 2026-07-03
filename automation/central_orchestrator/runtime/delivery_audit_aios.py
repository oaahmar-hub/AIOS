#!/usr/bin/env python3
from __future__ import annotations

import base64
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "evidence" / "delivery-audit"
OUT.mkdir(parents=True, exist_ok=True)
DEFAULT_BASE = "https://aios-runtime-production.up.railway.app"
EXPECTED_SERVICE_WORKER_CACHE = "aios-presence-v86"
BASE = DEFAULT_BASE
AUTH_USER = ""
AUTH_PASSWORD = ""
AUTH = ""
PUBLIC_PAGES = ["/", "/AIOS-WEBSITE.html"]
PROTECTED_PAGES = ["/AIOS-DASHBOARD.html", "/AIOS-MOBILE-APP.html", "/AIOS-RUNTIME-STATUS.html"]
CORE_ASSETS = ["/aios-service-worker.js", "/aios.webmanifest", "/offline.html", "/assets/aios-eye-cinematic-loop-phase55.mp4"]
MAX_PUBLIC_HTML_BYTES = 180_000
MAX_DASHBOARD_HTML_BYTES = 380_000
SERVICE_WORKER_CACHE_RE = re.compile(r"aios-presence-v\d+")

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src", "poster"} and value:
                self.refs.append({"tag": tag, "attr": key, "value": value})

def fetch(path: str, auth: bool = False, limit: int | None = None, headers: dict[str, str] | None = None) -> dict:
    url = urllib.parse.urljoin(BASE, path)
    request_headers = {"Cache-Control": "no-cache", **(headers or {})}
    if auth:
        if not AUTH:
            return {"path": path, "status": None, "ms": 0, "bytes": 0, "body": b"", "error": "missing_basic_auth_env", "content_type": ""}
        request_headers["Authorization"] = AUTH
    req = urllib.request.Request(url, headers=request_headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read(limit or 2_000_000)
            return {
                "path": path,
                "status": resp.status,
                "ms": round((time.perf_counter() - start) * 1000, 1),
                "bytes": len(body),
                "body": body,
                "headers": dict(resp.headers.items()),
                "content_type": resp.headers.get("Content-Type", ""),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(20_000)
        return {
            "path": path,
            "status": exc.code,
            "ms": round((time.perf_counter() - start) * 1000, 1),
            "bytes": len(body),
            "body": body,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
        }
    except Exception as exc:
        return {"path": path, "status": None, "ms": round((time.perf_counter() - start) * 1000, 1), "bytes": 0, "body": b"", "headers": {}, "error": f"{type(exc).__name__}: {exc}", "content_type": ""}

def fetch_with_retry(path: str, auth: bool = False, limit: int | None = None, retries: int = 1, headers: dict[str, str] | None = None) -> dict:
    result = fetch(path, auth=auth, limit=limit, headers=headers)
    for _ in range(retries):
        if result.get("status") is not None:
            break
        time.sleep(0.6)
        result = fetch(path, auth=auth, limit=limit, headers=headers)
    return result

def page_refs(html: bytes):
    parser = LinkParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    refs = []
    for ref in parser.refs:
        val = ref["value"].strip()
        if not val or val.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if val.startswith("file://"):
            refs.append({**ref, "resolved_path": val, "local_file": True})
            continue
        parsed = urllib.parse.urlparse(val)
        if parsed.scheme and parsed.netloc and parsed.netloc != urllib.parse.urlparse(BASE).netloc:
            continue
        resolved = urllib.parse.urljoin(BASE + "/", val)
        path = urllib.parse.urlparse(resolved).path
        if path.endswith("/") and path != "/":
            continue
        refs.append({**ref, "resolved_path": path, "local_file": False})
    return refs

def unique_paths(refs):
    seen = []
    for ref in refs:
        path = ref["resolved_path"]
        if path not in seen and not path.startswith("file://"):
            seen.append(path)
    return seen

def header_value(result: dict, name: str) -> str:
    expected = name.lower()
    for key, value in (result.get("headers") or {}).items():
        if key.lower() == expected:
            return value
    return ""

def validate_gzip_and_etag(path: str, auth: bool = False) -> dict:
    if auth and not AUTH:
        return {"path": path, "pass": True, "skipped": True, "reason": "missing_basic_auth_env"}
    first = fetch_with_retry(path, auth=auth, headers={"Accept-Encoding": "gzip"})
    etag = header_value(first, "ETag")
    second = fetch_with_retry(path, auth=auth, headers={"Accept-Encoding": "gzip", "If-None-Match": etag}) if etag else {"status": None, "bytes": None, "headers": {}}
    return {
        "path": path,
        "pass": first.get("status") == 200
        and header_value(first, "Content-Encoding") == "gzip"
        and bool(etag)
        and second.get("status") == 304
        and second.get("bytes") == 0,
        "first_status": first.get("status"),
        "first_bytes": first.get("bytes"),
        "content_encoding": header_value(first, "Content-Encoding"),
        "etag": etag,
        "second_status": second.get("status"),
        "second_bytes": second.get("bytes"),
    }

def validate_security_headers(path: str, auth: bool = False) -> dict:
    if auth and not AUTH:
        return {"path": path, "pass": True, "skipped": True, "reason": "missing_basic_auth_env"}
    result = fetch_with_retry(path, auth=auth, limit=20_000)
    headers = result.get("headers", {})
    expected = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "SAMEORIGIN",
    }
    missing = {key: value for key, value in expected.items() if header_value(result, key) != value}
    return {"path": path, "pass": result.get("status") in {200, 401} and not missing, "status": result.get("status"), "missing": missing}

def main() -> int:
    parser = argparse.ArgumentParser(description="Audit hosted AIOS delivery, cache, links, and security headers.")
    parser.add_argument("base_url", nargs="?", default=os.getenv("AIOS_PUBLIC_BASE_URL", DEFAULT_BASE), help="Hosted AIOS base URL to audit.")
    parser.add_argument("--auth-user-env", default="AIOS_BASIC_AUTH_USER", help="Environment variable containing Basic Auth username.")
    parser.add_argument("--auth-password-env", default="AIOS_BASIC_AUTH_PASSWORD", help="Environment variable containing Basic Auth password.")
    parser.add_argument("--expected-cache", default=os.getenv("AIOS_EXPECTED_SERVICE_WORKER_CACHE", EXPECTED_SERVICE_WORKER_CACHE), help="Expected service worker cache name for the current release.")
    parser.add_argument("--verbose", action="store_true", help="Print human-readable PASS/FAIL lines after the JSON payload.")
    args = parser.parse_args()
    global BASE, AUTH_USER, AUTH_PASSWORD, AUTH
    BASE = args.base_url.rstrip("/") + "/"
    AUTH_USER = os.getenv(args.auth_user_env, "").strip()
    AUTH_PASSWORD = os.getenv(args.auth_password_env, "")
    AUTH = "Basic " + base64.b64encode(f"{AUTH_USER}:{AUTH_PASSWORD}".encode()).decode() if AUTH_USER and AUTH_PASSWORD else ""
    checks = []
    pages = {}
    for path in PUBLIC_PAGES:
        res = fetch_with_retry(path, auth=False)
        pages[path] = res
        checks.append({"name": f"public_page_{path}", "pass": res["status"] == 200, "status": res["status"], "ms": res["ms"], "bytes": res["bytes"]})
    for path in PROTECTED_PAGES:
        noauth = fetch_with_retry(path, auth=False, limit=20_000)
        checks.append({"name": f"protected_without_auth_{path}", "pass": noauth["status"] == 401, "status": noauth["status"], "ms": noauth["ms"]})
        if AUTH:
            authed = fetch_with_retry(path, auth=True)
            pages[path] = authed
            checks.append({"name": f"protected_with_auth_{path}", "pass": authed["status"] == 200, "status": authed["status"], "ms": authed["ms"], "bytes": authed["bytes"]})
        else:
            checks.append({"name": f"protected_with_auth_{path}", "pass": True, "skipped": True, "reason": "missing_basic_auth_env"})
    for path in CORE_ASSETS:
        res = fetch_with_retry(path, auth=False, limit=250_000)
        checks.append({"name": f"core_asset_{path}", "pass": res["status"] == 200, "status": res["status"], "ms": res["ms"], "bytes_read": res["bytes"], "content_type": res.get("content_type")})
        if path == "/aios-service-worker.js" and res["status"] == 200:
            text = res["body"].decode("utf-8", errors="replace")
            shell = text.split("const AIOS_SHELL", 1)[1].split("];", 1)[0] if "const AIOS_SHELL" in text else ""
            cache_match = SERVICE_WORKER_CACHE_RE.search(text)
            actual_cache = cache_match.group(0) if cache_match else ""
            protected_pages = ["AIOS-DASHBOARD.html", "AIOS-MOBILE-APP.html", "AIOS-RUNTIME-STATUS.html"]
            cache_control = header_value(res, "Cache-Control")
            checks.append(
                {
                    "name": "service_worker_cache_version",
                    "pass": actual_cache == args.expected_cache,
                    "cache": actual_cache,
                    "expected": args.expected_cache,
                }
            )
            checks.append({"name": "service_worker_no_old_video_preload", "pass": not any(x in text for x in ["phase52", "phase53", "phase54"])})
            checks.append(
                {
                    "name": "service_worker_no_protected_precache",
                    "pass": not any(x in shell for x in protected_pages),
                }
            )
            checks.append(
                {
                    "name": "service_worker_protected_runtime_cache_excluded",
                    "pass": "AIOS_PROTECTED_PATHS" in text
                    and all(page in text for page in protected_pages)
                    and text.count("!AIOS_PROTECTED_PATHS.has(url.pathname)") >= 2,
                }
            )
            checks.append(
                {
                    "name": "service_worker_cache_control_no_store",
                    "pass": "no-store" in cache_control.lower(),
                    "cache_control": cache_control,
                }
            )
            checks.append({"name": "service_worker_no_eye_video_precache", "pass": "aios-eye-cinematic-loop-" not in shell})
    refs = []
    for path, res in pages.items():
        if res["status"] == 200 and "html" in res.get("content_type", ""):
            for ref in page_refs(res["body"]):
                ref["page"] = path
                ref["protected_page"] = path in PROTECTED_PAGES
                refs.append(ref)
    local_file_refs = [ref for ref in refs if ref.get("local_file")]
    old_asset_refs = [ref for ref in refs if re.search(r"phase5[234]", ref.get("value", ""))]
    checks.append({"name": "no_file_url_refs", "pass": not local_file_refs, "count": len(local_file_refs), "refs": local_file_refs[:10]})
    checks.append({"name": "no_old_eye_refs", "pass": not old_asset_refs, "count": len(old_asset_refs), "refs": old_asset_refs[:10]})
    link_checks = []
    for path in unique_paths(refs):
        source_refs = [ref for ref in refs if ref["resolved_path"] == path]
        protected_child = any(ref.get("protected_page") for ref in source_refs)
        if path in {"/AIOS-DASHBOARD.html", "/AIOS-MOBILE-APP.html", "/AIOS-RUNTIME-STATUS.html"} or path.startswith("/evidence/") or protected_child:
            if not AUTH:
                link_checks.append({"path": path, "status": "skipped", "ms": 0, "pass": True, "skipped": True, "reason": "missing_basic_auth_env"})
                continue
            res = fetch_with_retry(path, auth=True, limit=80_000)
        else:
            res = fetch_with_retry(path, auth=False, limit=80_000)
        ok = res["status"] in {200, 206}
        link_checks.append({"path": path, "status": res["status"], "ms": res["ms"], "pass": ok})
    checks.append({"name": "linked_assets_and_pages", "pass": all(item["pass"] for item in link_checks), "checked": len(link_checks), "failures": [item for item in link_checks if not item["pass"]][:20]})
    sizes = {path: {"bytes": res["bytes"], "status": res["status"]} for path, res in pages.items()}
    checks.append({"name": "public_html_size_budget", "pass": all(pages[p]["bytes"] <= MAX_PUBLIC_HTML_BYTES for p in PUBLIC_PAGES), "budget": MAX_PUBLIC_HTML_BYTES, "sizes": {p: pages[p]["bytes"] for p in PUBLIC_PAGES}})
    if "/AIOS-DASHBOARD.html" in pages:
        checks.append({"name": "dashboard_size_budget", "pass": pages["/AIOS-DASHBOARD.html"]["bytes"] <= MAX_DASHBOARD_HTML_BYTES, "budget": MAX_DASHBOARD_HTML_BYTES, "bytes": pages["/AIOS-DASHBOARD.html"]["bytes"]})
    else:
        checks.append({"name": "dashboard_size_budget", "pass": True, "skipped": True, "reason": "missing_basic_auth_env", "budget": MAX_DASHBOARD_HTML_BYTES})
    gzip_checks = [
        validate_gzip_and_etag("/AIOS-WEBSITE.html"),
        validate_gzip_and_etag("/AIOS-DASHBOARD.html", auth=True),
        validate_gzip_and_etag("/AIOS-MOBILE-APP.html", auth=True),
        validate_gzip_and_etag("/aios-service-worker.js"),
    ]
    checks.append({"name": "gzip_etag_304_static_text", "pass": all(item["pass"] for item in gzip_checks), "items": gzip_checks})
    security_checks = [
        validate_security_headers("/"),
        validate_security_headers("/AIOS-DASHBOARD.html", auth=True),
        validate_security_headers("/api/health"),
    ]
    checks.append({"name": "security_headers", "pass": all(item["pass"] for item in security_checks), "items": security_checks})
    checks_passed = sum(1 for check in checks if check["pass"])
    checks_total = len(checks)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "passed": checks_passed == checks_total,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "summary": {"checks_passed": checks_passed, "checks_total": checks_total},
        "checks": checks,
        "link_checks": link_checks,
        "gzip_checks": gzip_checks,
        "security_checks": security_checks,
        "page_sizes": sizes,
    }
    (OUT / "delivery_audit_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.verbose:
        for check in checks:
            print(f"{('PASS' if check['pass'] else 'FAIL')} {check['name']}")
    return 0 if payload["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
