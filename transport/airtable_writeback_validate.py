#!/usr/bin/env python3
"""Validate AIOS WhatsApp -> Airtable CRM writeback readiness.

This script is intentionally small and operational:
- It does not create fake records.
- It checks the live gateway health endpoint.
- It calls the gateway Airtable queue replay endpoint.
- It exits non-zero while the live gateway is missing Airtable credentials.
"""

import json
import sys
import urllib.error
import urllib.request


GATEWAY_BASE_URL = "http://127.0.0.1:9010"


def _request(method, path, payload=None, timeout=10):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{GATEWAY_BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return exc.code, parsed


def main():
    health_status, health = _request("GET", "/health", timeout=5)
    replay_status, replay = _request("POST", "/admin/airtable/replay", {"limit": 25}, timeout=20)
    result = {
        "validation": "PASS" if health.get("airtable_configured") and replay.get("ok") else "FAIL",
        "gateway_health_http_status": health_status,
        "gateway_replay_http_status": replay_status,
        "gateway_running": bool(health.get("ok")),
        "airtable_configured": bool(health.get("airtable_configured")),
        "airtable_queue": health.get("airtable_queue", {}),
        "airtable_replay_worker_alive": bool(health.get("airtable_replay_worker_alive")),
        "replay_result": replay,
    }
    if not result["airtable_configured"]:
        result["blocker"] = "AIRTABLE_TOKEN / AIRTABLE_API_KEY missing from live gateway env/config.env"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["validation"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
