#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import http.client
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_ENV = ROOT / "config.env"
GITIGNORE = ROOT / ".gitignore"
GATEWAY = ROOT / "transport" / "simple_whatsapp_openai_gateway.py"
ROUTER_CANONICAL = ROOT / "KnowledgeBase" / "aios_brain_router.py"
ROUTER_HOSTED = ROOT / "deployment" / "hosted-backend" / "AIOS" / "KnowledgeBase" / "aios_brain_router.py"
HOSTED_BACKEND = ROOT / "deployment" / "hosted-backend"
PY_COMPILE_TARGETS = [
    ROOT / "transport" / "simple_whatsapp_openai_gateway.py",
    ROOT / "transport" / "aios_response_policy_layer.py",
    ROOT / "KnowledgeBase" / "aios_brain_router.py",
    ROOT / "deployment" / "hosted-backend" / "AIOS" / "KnowledgeBase" / "aios_brain_router.py",
    ROOT / "KnowledgeBase" / "hybrid_retriever.py",
    ROOT / "KnowledgeBase" / "aios_memory_layer_v1.py",
    ROOT / "KnowledgeBase" / "aios_entrypoint.py",
    ROOT / "KnowledgeBase" / "property_recommendation_agent.py",
    ROOT / "deployment" / "hosted-backend" / "app.py",
    ROOT / "deployment" / "hosted-backend" / "AIOS" / "KnowledgeBase" / "aios_entrypoint.py",
    ROOT / "deployment" / "hosted-backend" / "AIOS" / "KnowledgeBase" / "property_recommendation_agent.py",
]
REQUIRED_RAILWAY_VARS = [
    "WASENDER_API_KEY",
    "WA_SIMPLE_OPENAI_ENDPOINT",
    "AIOS_ALLOWED_ORIGIN",
    "AIOS_BASIC_AUTH_USER",
    "AIOS_BASIC_AUTH_PASSWORD",
    "AIOS_WEBHOOK_SECRET",
]
SECRET_SCAN_SUFFIXES = {".py", ".md", ".example", ".js", ".json", ".yml", ".yaml", ".txt"}
SECRET_SCAN_EXCLUDE_PARTS = {"data", "proofs", ".tmp_work", "tmp", "run", "__pycache__"}
SECRET_PATTERNS = [
    ("airtable_pat", re.compile(r"pat[a-zA-Z0-9._-]{12,}")),
    ("api_key", re.compile(r"(?<!action-token-)key-[a-zA-Z0-9_-]{12,}")),
    (
        "env_secret_assignment",
        re.compile(r"(?i)(AIRTABLE_TOKEN|AIRTABLE_API_KEY|WASENDER_API_KEY|AIOS_WEBHOOK_SECRET)=[^<\s][^\n]+"),
    ),
]


def load_config_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def sha16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def redact_token(value: str) -> str:
    if not value:
        return ""
    return f"sha256:{sha16(value)}"


def check_airtable_token(token: str, config: dict[str, str], phone: str = "+971500000000") -> tuple[bool, str]:
    if not token:
        return False, "missing_token"
    base_id = config.get("AIRTABLE_BASE_ID", "")
    table_id = config.get("AIRTABLE_CONTACTS_TABLE", "")
    if not base_id or not table_id:
        return False, "missing_airtable_base_or_table"
    formula = "{Phone} = '%s'" % phone.replace("'", "\\'")
    query = urllib.parse.urlencode({"filterByFormula": formula, "maxRecords": 1, "returnFieldsByFieldId": "true"})
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}?{query}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
            return True, f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        reason = raw[:300]
        return False, f"http_{exc.code}:{reason}"
    except Exception as exc:
        return False, str(exc)


def check_gitignore() -> tuple[bool, str]:
    required = [
        "config.env",
        ".env",
        "*.env",
        "*.sqlite",
        "*.db",
        "__pycache__/",
        ".DS_Store",
        "*.log",
        "*.jsonl",
    ]
    if not GITIGNORE.exists():
        return False, "missing_.gitignore"
    lines = [line.rstrip("\n") for line in GITIGNORE.read_text(encoding="utf-8", errors="ignore").splitlines()]
    missing = [pattern for pattern in required if pattern not in lines]
    if missing:
        return False, f"missing:{','.join(missing)}"

    ignored = False
    tracked = False
    try:
        ignored_proc = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", str(CONFIG_ENV)],
            capture_output=True,
            text=True,
        )
        ignored = ignored_proc.returncode == 0
    except Exception:
        ignored = False

    try:
        tracked_proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", str(CONFIG_ENV)],
            capture_output=True,
            text=True,
        )
        tracked = tracked_proc.returncode == 0
    except Exception:
        tracked = False

    if not ignored:
        return False, "config_env_not_gitignored"
    if tracked:
        return False, "config_env_still_tracked"
    return True, "patterns_present_and_config_env_ignored_untracked"


def get_tracked_files() -> tuple[list[Path], str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"],
            check=True,
            text=True,
            capture_output=True,
        )
        if proc.stdout.strip() != "true":
            raise RuntimeError("not_git_repo")
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"],
            check=True,
            text=True,
            capture_output=True,
        )
        files = [ROOT / line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return files, "git_tracked_files"
    except Exception:
        files: list[Path] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if path.name == "config.env":
                continue
            if any(part in SECRET_SCAN_EXCLUDE_PARTS for part in rel.parts):
                continue
            if rel.parts and rel.parts[0] == "transport" and path.suffix.lower() not in {".py", ".md"}:
                continue
            if path.suffix.lower() not in SECRET_SCAN_SUFFIXES and path.name not in {".gitignore", "config.env.example"}:
                continue
            files.append(path)
        return files, "shareable_file_scan_fallback"


def check_tracked_files_for_secrets() -> tuple[bool, str, str]:
    files, mode = get_tracked_files()
    hits: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for _name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(str(path.relative_to(ROOT)))
                break
    detail = "no_secret_hits" if not hits else f"hits:{','.join(hits[:10])}"
    return not hits, detail, mode


def check_router_sync() -> tuple[bool, str]:
    if not ROUTER_CANONICAL.exists() or not ROUTER_HOSTED.exists():
        return False, "router_file_missing"
    same = ROUTER_CANONICAL.read_bytes() == ROUTER_HOSTED.read_bytes()
    return same, "byte_identical" if same else "router_drift_detected"


def check_python_compile() -> tuple[bool, str]:
    try:
        subprocess.run(
            [sys.executable, "-m", "py_compile", *[str(path) for path in PY_COMPILE_TARGETS]],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "py_compile_pass"
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "py_compile_failed").strip().splitlines()[-1][:300]
        return False, detail


def railway_service_name() -> tuple[str | None, str]:
    railway = os.path.expanduser("~/.railway/bin/railway")
    if not Path(railway).exists():
        return None, "railway_cli_missing"
    try:
        proc = subprocess.run(
            [railway, "status", "--json"],
            cwd=str(HOSTED_BACKEND),
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
        return data["services"]["edges"][0]["node"]["name"], "railway_status_ok"
    except Exception as exc:
        return None, f"railway_status_failed:{str(exc)[:200]}"


def check_railway_env_vars() -> tuple[bool, str]:
    railway = os.path.expanduser("~/.railway/bin/railway")
    service_name, status_detail = railway_service_name()
    if not service_name:
        return False, status_detail
    try:
        proc = subprocess.run(
            [railway, "variable", "list", "--service", service_name, "--json"],
            cwd=str(HOSTED_BACKEND),
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
        present = {
            item["name"]: bool(str(item.get("value") or "").strip())
            for item in data
            if isinstance(item, dict) and item.get("name")
        }
        missing = [name for name in REQUIRED_RAILWAY_VARS if not present.get(name)]
        return not missing, "all_required_present" if not missing else f"missing:{','.join(missing)}"
    except Exception as exc:
        return False, f"railway_variable_list_failed:{str(exc)[:200]}"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def start_gateway(extra_env: dict[str, str]) -> tuple[int, subprocess.Popen[str], Path]:
    port = free_port()
    data_dir = Path(tempfile.mkdtemp(prefix="aios-predeploy-gateway-"))
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("AIOS_") or key.startswith("WA_SIMPLE_") or key.startswith("WASENDER") or key.startswith("AIRTABLE"):
            env.pop(key, None)
    env.update(
        {
            "WA_SIMPLE_GATEWAY_PORT": str(port),
            "AIOS_SKIP_CONFIG_ENV": "1",
            "AIOS_PROJECT_DIR": str(ROOT),
            "AIOS_DATA_DIR": str(data_dir),
            "WA_SIMPLE_REFLECTIVE_DELAY_SECONDS": "0",
            "PYTHONUNBUFFERED": "1",
        }
    )
    env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, str(GATEWAY)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError((proc.stdout.read() or "") + (proc.stderr.read() or ""))
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/health")
            response = conn.getresponse()
            response.read()
            conn.close()
            return port, proc, data_dir
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("gateway_start_timeout")


def stop_gateway(proc: subprocess.Popen[str]) -> tuple[str, str]:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
    stdout = proc.stdout.read() if proc.stdout else ""
    stderr = proc.stderr.read() if proc.stderr else ""
    return stdout, stderr


def post_json(port: int, path: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, dict | str | None]:
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    conn.request("POST", path, body=body, headers=req_headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8", errors="replace")
    conn.close()
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:
        parsed = raw
    return response.status, parsed


def check_gateway_auth() -> tuple[bool, str]:
    payload = {
        "data": {
            "messages": [
                {
                    "key": {"remoteJid": "971501234567@s.whatsapp.net", "fromMe": True},
                    "messageId": "mid-rotation-check",
                    "messageBody": "ignore me",
                }
            ]
        },
        "event": "message",
    }
    try:
        port, proc, _data_dir = start_gateway({})
        try:
            code, _ = post_json(port, "/webhook/whatsapp/simple", payload)
            if code != 401:
                return False, f"webhook_without_secret_expected_401_got_{code}"
            code, _ = post_json(port, "/admin/airtable/replay", {"limit": 1})
            if code != 401:
                return False, f"admin_without_auth_expected_401_got_{code}"
        finally:
            stop_gateway(proc)

        port, proc, _data_dir = start_gateway({"AIOS_WEBHOOK_SECRET": "good", "AIOS_ADMIN_SECRET": "admin"})
        try:
            code, _ = post_json(port, "/webhook/whatsapp/simple", payload, {"X-AIOS-Webhook-Secret": "bad"})
            if code != 401:
                return False, f"webhook_wrong_secret_expected_401_got_{code}"
            code, _ = post_json(port, "/webhook/whatsapp/simple", payload, {"X-AIOS-Webhook-Secret": "good"})
            if code != 200:
                return False, f"webhook_correct_secret_expected_200_got_{code}"
            code, _ = post_json(port, "/admin/airtable/replay", {"limit": 1}, {"X-AIOS-Admin-Secret": "bad"})
            if code != 401:
                return False, f"admin_wrong_secret_expected_401_got_{code}"
            code, _ = post_json(port, "/admin/airtable/replay", {"limit": 1}, {"X-AIOS-Admin-Secret": "admin"})
            if code == 401:
                return False, "admin_correct_secret_still_401"
        finally:
            stop_gateway(proc)

        port, proc, _data_dir = start_gateway({"AIOS_BASIC_AUTH_USER": "admin", "AIOS_BASIC_AUTH_PASSWORD": "pw"})
        try:
            code, _ = post_json(port, "/admin/airtable/replay", {"limit": 1})
            if code != 401:
                return False, f"admin_missing_basic_expected_401_got_{code}"
            token = base64.b64encode(b"admin:pw").decode("ascii")
            code, _ = post_json(port, "/admin/airtable/replay", {"limit": 1}, {"Authorization": f"Basic {token}"})
            if code == 401:
                return False, "admin_basic_auth_still_401"
        finally:
            stop_gateway(proc)
        return True, "webhook_and_basic_auth_enforcement_pass"
    except Exception as exc:
        return False, str(exc)[:300]


def build_report(results: list[dict[str, str]]) -> str:
    all_ready = all(item["result"] == "READY" for item in results)
    final = "READY" if all_ready else "BLOCKED"
    lines = [
        "# Final Pre-Deploy Verification Report",
        "",
        f"Status: {final}",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for item in results:
        lines.append(f"| {item['check']} | {item['result']} | {item['evidence']} |")
    lines.extend(
        [
            "",
            "Final classification:",
            final,
            "",
            "This verifier does not deploy and does not push to GitHub.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run final pre-deploy verification after Omar confirms Airtable PAT rotation."
    )
    parser.add_argument(
        "--omar-confirmed-airtable-rotation",
        action="store_true",
        help="Required gate. Refuses to run the final checks without explicit Omar confirmation.",
    )
    parser.add_argument(
        "--old-airtable-token-env",
        default="AIOS_OLD_AIRTABLE_TOKEN",
        help="Environment variable name holding the revoked old Airtable token for invalidation verification.",
    )
    parser.add_argument(
        "--write-report",
        default=str(ROOT / "00_FOUNDATION" / "PRE_DEPLOY_VERIFICATION_AFTER_AIRTABLE_ROTATION_RESULT.md"),
        help="Write the final report to this path.",
    )
    args = parser.parse_args()

    if not args.omar_confirmed_airtable_rotation:
        print("BLOCKED: waiting for Omar confirmation that Airtable PAT rotation is complete.")
        return 2

    config = load_config_env(CONFIG_ENV)
    current_token = config.get("AIRTABLE_TOKEN", "")
    old_token = os.environ.get(args.old_airtable_token_env, "")

    results: list[dict[str, str]] = []

    ok, detail = check_airtable_token(current_token, config)
    results.append(
        {
            "check": "1. New Airtable token works",
            "result": "READY" if ok else "BLOCKED",
            "evidence": detail,
        }
    )

    if not old_token:
        results.append(
            {
                "check": "2. Old Airtable token is invalid",
                "result": "BLOCKED",
                "evidence": f"missing_env:{args.old_airtable_token_env}",
            }
        )
    else:
        ok, detail = check_airtable_token(old_token, config)
        results.append(
            {
                "check": "2. Old Airtable token is invalid",
                "result": "READY" if not ok else "BLOCKED",
                "evidence": detail if not ok else "old_token_still_valid",
            }
        )

    ok, detail = check_gitignore()
    results.append({"check": "3. config.env is still gitignored", "result": "READY" if ok else "BLOCKED", "evidence": detail})

    ok, detail, mode = check_tracked_files_for_secrets()
    results.append(
        {
            "check": "4. No real secrets exist in tracked files",
            "result": "READY" if ok else "BLOCKED",
            "evidence": f"{mode}:{detail}",
        }
    )

    ok, detail = check_gateway_auth()
    results.append(
        {
            "check": "5. Webhook secret enforcement still passes",
            "result": "READY" if ok else "BLOCKED",
            "evidence": detail,
        }
    )
    results.append(
        {
            "check": "6. Basic Auth still passes",
            "result": "READY" if ok else "BLOCKED",
            "evidence": detail,
        }
    )

    ok, detail = check_router_sync()
    results.append(
        {
            "check": "7. Hosted backend router copy is still synced",
            "result": "READY" if ok else "BLOCKED",
            "evidence": detail,
        }
    )

    ok, detail = check_python_compile()
    results.append(
        {
            "check": "8. Python compile passes",
            "result": "READY" if ok else "BLOCKED",
            "evidence": detail,
        }
    )

    ok, detail = check_railway_env_vars()
    results.append(
        {
            "check": "9. Railway env vars are ready",
            "result": "READY" if ok else "BLOCKED",
            "evidence": detail,
        }
    )

    final_ready = all(item["result"] == "READY" for item in results)
    results.append(
        {
            "check": "10. Final classification",
            "result": "READY" if final_ready else "BLOCKED",
            "evidence": "all_checks_ready" if final_ready else "one_or_more_checks_blocked",
        }
    )

    report = build_report(results)
    report_path = Path(args.write_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    return 0 if final_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
