#!/usr/bin/env python3
"""Benchmark AIOS runtime delivery and API warm-cache behavior."""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_PATH = REPORTS_DIR / "RUNTIME_PERFORMANCE_VALIDATION.json"

DEFAULT_BASE_URL = os.getenv("AIOS_PERFORMANCE_BASE_URL", "http://127.0.0.1:8881")
DEFAULT_REQUESTS = int(os.getenv("AIOS_PERFORMANCE_REQUESTS", "6"))
WEBSITE_MAX_MS = float(os.getenv("AIOS_PERFORMANCE_WEBSITE_MAX_MS", "250"))
SERVICE_WORKER_MAX_MS = float(os.getenv("AIOS_PERFORMANCE_SERVICE_WORKER_MAX_MS", "100"))
COMMAND_CENTER_COLD_MAX_MS = float(os.getenv("AIOS_PERFORMANCE_COMMAND_COLD_MAX_MS", "350"))
COMMAND_CENTER_WARM_P95_MAX_MS = float(os.getenv("AIOS_PERFORMANCE_COMMAND_WARM_P95_MAX_MS", "120"))
COMMAND_CENTER_WARM_BEST_MAX_MS = float(os.getenv("AIOS_PERFORMANCE_COMMAND_WARM_BEST_MAX_MS", "60"))
COMMAND_CENTER_MAX_WIRE_BYTES = int(os.getenv("AIOS_COMMAND_CENTER_MAX_WIRE_BYTES", "250000"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _auth_header(user: str, password: str) -> dict[str, str]:
    if not user and not password:
        return {}
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _request(base_url: str, path: str, *, auth: dict[str, str] | None = None) -> dict[str, Any]:
    headers = {"Accept-Encoding": "gzip", "Cache-Control": "no-cache", "User-Agent": "AIOSRuntimePerformance/1.0"}
    if auth:
        headers.update(auth)
    req = urllib.request.Request(_url(base_url, path), headers=headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            wire_bytes = len(raw)
            body = gzip.decompress(raw) if resp.headers.get("Content-Encoding", "").lower() == "gzip" else raw
            return {
                "path": path,
                "status": resp.status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "wire_bytes": wire_bytes,
                "body_bytes": len(body),
                "content_encoding": resp.headers.get("Content-Encoding", ""),
                "cache_control": resp.headers.get("Cache-Control", ""),
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        exc.read()
        return {
            "path": path,
            "status": exc.code,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "wire_bytes": 0,
            "body_bytes": 0,
            "content_encoding": "",
            "cache_control": exc.headers.get("Cache-Control", "") if exc.headers else "",
            "error": f"HTTPError:{exc.code}",
        }
    except Exception as exc:
        return {
            "path": path,
            "status": 0,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "wire_bytes": 0,
            "body_bytes": 0,
            "content_encoding": "",
            "cache_control": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def validate(base_url: str, *, auth: dict[str, str], requests: int) -> dict[str, Any]:
    website = _request(base_url, "/AIOS-WEBSITE.html")
    service_worker = _request(base_url, "/aios-service-worker.js")
    command_runs = [_request(base_url, "/api/command-center/data", auth=auth) for _ in range(max(2, requests))]
    command_times = [float(item["elapsed_ms"]) for item in command_runs if item.get("status") == 200]
    warm_times = command_times[1:] if len(command_times) > 1 else command_times
    command_summary = {
        "requests": len(command_runs),
        "cold_ms": command_times[0] if command_times else 0,
        "warm_best_ms": round(min(warm_times), 2) if warm_times else 0,
        "warm_mean_ms": round(statistics.mean(warm_times), 2) if warm_times else 0,
        "warm_p95_ms": _percentile(warm_times, 0.95),
        "wire_bytes": command_runs[-1].get("wire_bytes", 0) if command_runs else 0,
        "body_bytes": command_runs[-1].get("body_bytes", 0) if command_runs else 0,
    }
    checks = [
        {
            "name": "website_first_response",
            "passed": website.get("status") == 200 and float(website.get("elapsed_ms") or 0) <= WEBSITE_MAX_MS,
            "status": website.get("status"),
            "elapsed_ms": website.get("elapsed_ms"),
            "budget_ms": WEBSITE_MAX_MS,
        },
        {
            "name": "service_worker_first_response",
            "passed": service_worker.get("status") == 200
            and float(service_worker.get("elapsed_ms") or 0) <= SERVICE_WORKER_MAX_MS
            and service_worker.get("cache_control") == "no-store",
            "status": service_worker.get("status"),
            "elapsed_ms": service_worker.get("elapsed_ms"),
            "budget_ms": SERVICE_WORKER_MAX_MS,
            "cache_control": service_worker.get("cache_control"),
        },
        {
            "name": "command_center_cold_response",
            "passed": bool(command_times) and command_summary["cold_ms"] <= COMMAND_CENTER_COLD_MAX_MS,
            "elapsed_ms": command_summary["cold_ms"],
            "budget_ms": COMMAND_CENTER_COLD_MAX_MS,
        },
        {
            "name": "command_center_warm_p95_response",
            "passed": bool(warm_times) and command_summary["warm_p95_ms"] <= COMMAND_CENTER_WARM_P95_MAX_MS,
            "elapsed_ms": command_summary["warm_p95_ms"],
            "budget_ms": COMMAND_CENTER_WARM_P95_MAX_MS,
        },
        {
            "name": "command_center_warm_best_response",
            "passed": bool(warm_times) and command_summary["warm_best_ms"] <= COMMAND_CENTER_WARM_BEST_MAX_MS,
            "elapsed_ms": command_summary["warm_best_ms"],
            "budget_ms": COMMAND_CENTER_WARM_BEST_MAX_MS,
        },
        {
            "name": "command_center_wire_size",
            "passed": command_summary["wire_bytes"] <= COMMAND_CENTER_MAX_WIRE_BYTES,
            "wire_bytes": command_summary["wire_bytes"],
            "budget_bytes": COMMAND_CENTER_MAX_WIRE_BYTES,
        },
    ]
    report = {
        "validated_at": _now(),
        "base_url": base_url.rstrip("/"),
        "passed": all(item["passed"] for item in checks),
        "checks_passed": sum(1 for item in checks if item["passed"]),
        "checks_total": len(checks),
        "checks": checks,
        "website": website,
        "service_worker": service_worker,
        "command_center_data": {
            "summary": command_summary,
            "runs": command_runs,
        },
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark AIOS runtime response speed.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument("--auth-user-env", default="AIOS_BASIC_AUTH_USER")
    parser.add_argument("--auth-password-env", default="AIOS_BASIC_AUTH_PASSWORD")
    args = parser.parse_args()
    auth = _auth_header(os.getenv(args.auth_user_env, ""), os.getenv(args.auth_password_env, ""))
    report = validate(args.base_url, auth=auth, requests=args.requests)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
