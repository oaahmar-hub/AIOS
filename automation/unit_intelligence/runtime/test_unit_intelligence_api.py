#!/usr/bin/env python3
"""Integration tests for unit-intelligence API endpoints.

Starts the AIOS Live API server in a subprocess and exercises the new endpoints.
No external network calls are made.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

API_SERVER = Path(__file__).resolve().parents[2] / "central_orchestrator" / "runtime" / "aios_live_api_server.py"
PORT = 8890
BASE = f"http://127.0.0.1:{PORT}"


def _wait_for_server(timeout: int = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=1):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("API server did not start in time")


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_tests() -> dict:
    proc = subprocess.Popen(
        [sys.executable, str(API_SERVER), "--port", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_server()

        results = {
            "health": _request("GET", "/api/health"),
            "unit_stats": _request("GET", "/api/unit/stats"),
            "unit_ingest": _request(
                "POST",
                "/api/unit/ingest",
                {"url": "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html"},
            ),
            "property_resolve": _request(
                "POST",
                "/api/property/resolve",
                {"url": "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html"},
            ),
            "webhook_status": _request("GET", "/webhook/whatsapp/provider/gateway"),
        }

        checks = {
            "health_ok": results["health"].get("status") == "ready",
            "unit_stats_ok": results["unit_stats"].get("ok") is True,
            "unit_ingest_ok": results["unit_ingest"].get("ok") is True,
            "property_resolve_ok": results["property_resolve"].get("ok") is True,
            "webhook_status_ok": results["webhook_status"].get("ok") is True,
            "webhook_not_ready": results["webhook_status"].get("ready_for_provider") is False,
        }
        results["checks"] = checks
        results["all_passed"] = all(checks.values())
        return results
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    results = run_tests()
    print(json.dumps(results, indent=2, default=str))
    if not results.get("all_passed"):
        raise SystemExit(1)
    print("\nIntegration tests passed.")
