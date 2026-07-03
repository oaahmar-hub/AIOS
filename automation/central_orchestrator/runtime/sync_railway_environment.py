#!/usr/bin/env python3
"""Sync AIOS production environment variables to Railway with redacted proof.

This script requires Railway login and local environment variables to be
exported. Secret values are passed through stdin and are never printed into the
report.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "RAILWAY_ENVIRONMENT_SYNC.json"
SECRET_ENV = {"AIOS_BASIC_AUTH_USER", "AIOS_BASIC_AUTH_PASSWORD", "AIOS_WHATSAPP_VERIFY_TOKEN"}
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
    "RAILWAY_PUBLIC_DOMAIN",
]


def _railway_cli() -> str | None:
    return shutil.which("railway") or (str(Path.home() / ".railway" / "bin" / "railway") if (Path.home() / ".railway" / "bin" / "railway").exists() else None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_cmd(args: list[str]) -> str:
    safe: list[str] = []
    for item in args:
        if "=" in item:
            key = item.split("=", 1)[0]
            safe.append(f"{key}=<redacted>")
        else:
            safe.append(item)
    return " ".join(safe)


def _run(args: list[str], *, stdin: str | None = None) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=AIOS_ROOT, input=stdin, text=True, capture_output=True)
    return {
        "cmd": _safe_cmd(args),
        "returncode": proc.returncode,
        "stdout": "" if stdin is not None else proc.stdout[-1000:],
        "stderr": proc.stderr[-1000:],
    }


def _whoami(railway: str) -> dict[str, Any]:
    result = _run([railway, "whoami"])
    return {"authenticated": result["returncode"] == 0, "result": result}


def _env_presence() -> dict[str, Any]:
    all_keys = REQUIRED_ENV + OPTIONAL_ENV
    return {
        "required": {
            key: {
                "present": bool(os.getenv(key)),
                "secret": key in SECRET_ENV,
            }
            for key in REQUIRED_ENV
        },
        "optional": {
            key: {
                "present": bool(os.getenv(key)),
                "secret": key in SECRET_ENV,
            }
            for key in OPTIONAL_ENV
        },
        "missing_required": [key for key in REQUIRED_ENV if not os.getenv(key)],
        "present_keys": [key for key in all_keys if os.getenv(key)],
    }


def _set_variable(railway: str, key: str, value: str, service: str, environment: str) -> dict[str, Any]:
    if key in SECRET_ENV:
        args = [railway, "variable", "set", key, "--stdin", "--skip-deploys", "--json"]
        stdin = value
    else:
        args = [railway, "variable", "set", f"{key}={value}", "--skip-deploys", "--json"]
        stdin = None
    if service:
        args.extend(["--service", service])
    if environment:
        args.extend(["--environment", environment])
    result = _run(args, stdin=stdin)
    return {
        "key": key,
        "secret": key in SECRET_ENV,
        "present": bool(value),
        "synced": result["returncode"] == 0,
        "result": result,
    }


def sync(args: argparse.Namespace) -> dict[str, Any]:
    railway = _railway_cli()
    report: dict[str, Any] = {
        "generated_at": _now(),
        "mode": "execute" if args.execute else "check",
        "railway_available": bool(railway),
        "whoami": {},
        "environment": _env_presence(),
        "actions": [],
        "status": "not_started",
        "next_action": "",
    }
    if not railway:
        report["status"] = "blocked_no_railway_cli"
        report["next_action"] = "Install Railway CLI and rerun."
    else:
        report["whoami"] = _whoami(railway)
        if not report["whoami"].get("authenticated"):
            report["status"] = "blocked_railway_auth"
            report["next_action"] = "Approve Railway login, export AIOS env vars, then rerun with --execute."
        elif report["environment"]["missing_required"]:
            report["status"] = "blocked_missing_required_env"
            report["next_action"] = "Export required AIOS env vars locally before syncing Railway environment."
        elif not args.execute:
            report["status"] = "ready_to_execute"
            report["next_action"] = "Run with --execute to sync Railway environment variables."
        else:
            keys = REQUIRED_ENV + [key for key in OPTIONAL_ENV if os.getenv(key)]
            for key in keys:
                report["actions"].append(_set_variable(railway, key, os.getenv(key, ""), args.service, args.environment))
            failed = [item["key"] for item in report["actions"] if item.get("synced") is not True]
            report["status"] = "synced" if not failed else "sync_failed"
            report["failed_keys"] = failed
            report["next_action"] = "Run production hosting pipeline." if not failed else "Fix failed Railway env sync keys, then rerun."
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync AIOS environment variables to Railway with redacted evidence.")
    parser.add_argument("--execute", action="store_true", help="Write variables to Railway.")
    parser.add_argument("--service", default="", help="Optional Railway service name.")
    parser.add_argument("--environment", default="", help="Optional Railway environment name.")
    return parser.parse_args()


def main() -> int:
    report = sync(parse_args())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] in {"ready_to_execute", "synced"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
