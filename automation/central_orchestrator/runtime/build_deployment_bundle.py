#!/usr/bin/env python3
"""Build an AIOS deployment bundle.

Creates a local tarball and release manifest for review or manual upload to a
hosting provider. The bundle intentionally excludes secrets, git metadata,
runtime reports, caches, and local state. It does not publish anything.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
DEFAULT_OUTPUT_DIR = REPORTS_DIR / "deployment-bundles"

EXCLUDE_PATTERNS = [
    ".git",
    ".git/*",
    ".tools",
    ".tools/*",
    "__pycache__",
    "*/__pycache__/*",
    "*.pyc",
    ".DS_Store",
    ".env",
    ".env.*",
    "automation/central_orchestrator/reports",
    "automation/central_orchestrator/reports/*",
    "automation/reports",
    "automation/reports/*",
    "automation/whatsapp_provider_gateway/reports",
    "automation/whatsapp_provider_gateway/reports/*",
    "automation/whatsapp_provider_gateway/state",
    "automation/whatsapp_provider_gateway/state/*",
    "*.sqlite",
    "*.sqlite-*",
    "node_modules",
    "node_modules/*",
    "node_modules/**",
    "android",
    "android/*",
    "android/**",
    "mobile-dist",
    "mobile-dist/*",
    "mobile-dist/**",
    "evidence",
    "evidence/*",
    "evidence/**",
    "automation/evidence",
    "automation/evidence/*",
    "automation/evidence/**",
    "assets/aios-eye-cinematic-loop-phase52.mp4",
    "assets/aios-eye-cinematic-loop-phase53.mp4",
    "assets/aios-eye-cinematic-loop-phase54.mp4",
    "knowledge-base/branding/assets",
    "knowledge-base/branding/assets/*",
    "knowledge-base/branding/assets/**",
]

REQUIRED_IN_BUNDLE = [
    "Dockerfile",
    ".dockerignore",
    "render.yaml",
    "railway.json",
    ".railwayignore",
    ".env.production.example",
    "DEPLOYMENT.md",
    "PRODUCTION_DEPLOYMENT_MANIFEST.json",
    "AIOS-WEBSITE.html",
    "AIOS-DASHBOARD.html",
    "AIOS-MOBILE-APP.html",
    "aios.webmanifest",
    "aios-service-worker.js",
    "offline.html",
    "automation/central_orchestrator/runtime/aios_live_api_server.py",
    "automation/central_orchestrator/runtime/aios_runtime.py",
    "automation/central_orchestrator/runtime/validate_container_runtime.py",
    "automation/central_orchestrator/runtime/validate_host_environment.py",
    "automation/central_orchestrator/runtime/validate_runtime_performance.py",
    "automation/central_orchestrator/runtime/validate_landing_boot_performance.py",
    "automation/central_orchestrator/runtime/validate_production_launch_readiness.py",
    "automation/central_orchestrator/runtime/deployment_preflight.py",
    "automation/central_orchestrator/runtime/sync_railway_environment.py",
    "automation/central_orchestrator/runtime/build_deployment_bundle.py",
    "automation/central_orchestrator/runtime/deploy_railway_production.py",
    "automation/central_orchestrator/runtime/finalize_production_hosting.py",
    "automation/central_orchestrator/runtime/run_production_hosting_pipeline.py",
    "automation/central_orchestrator/runtime/prepare_production_release.py",
    "automation/whatsapp_provider_gateway/runtime/whatsapp_provider_gateway.py",
    "automation/whatsapp_business_os/prompts/omar_real_estate_whatsapp_agent.txt",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    return path.relative_to(AIOS_ROOT).as_posix()


def _excluded(rel: str) -> bool:
    if rel == ".env.production.example":
        return False
    return any(fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE_PATTERNS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_bundle_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(AIOS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = _rel(path)
        if _excluded(rel):
            continue
        files.append(path)
    return files


def build(output_dir: Path = DEFAULT_OUTPUT_DIR, *, dry_run: bool = False) -> dict[str, Any]:
    files = _iter_bundle_files()
    included = {_rel(path) for path in files}
    missing_required = [rel for rel in REQUIRED_IN_BUNDLE if rel not in included]
    generated_at = _now()
    name = f"AIOS_RUNTIME_DEPLOYMENT_{_stamp()}"
    tar_path = output_dir / f"{name}.tar.gz"
    manifest_path = output_dir / f"{name}.manifest.json"
    file_records = [
        {
            "path": _rel(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    report = {
        "generated_at": generated_at,
        "dry_run": dry_run,
        "passed": not missing_required,
        "bundle": str(tar_path.relative_to(AIOS_ROOT)),
        "manifest": str(manifest_path.relative_to(AIOS_ROOT)),
        "file_count": len(file_records),
        "total_bytes": sum(item["bytes"] for item in file_records),
        "missing_required": missing_required,
        "excluded_patterns": EXCLUDE_PATTERNS,
        "required_in_bundle": REQUIRED_IN_BUNDLE,
        "files": file_records,
        "external_side_effects": {
            "published": False,
            "deployed": False,
            "secrets_written": False,
            "external_network_calls": False,
        },
    }
    if dry_run:
        return report
    output_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "w:gz") as tar:
        for path in files:
            tar.add(path, arcname=_rel(path), recursive=False)
    report["bundle_sha256"] = _sha256(tar_path)
    report["bundle_bytes"] = tar_path.stat().st_size
    manifest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "generated_at",
        "dry_run",
        "passed",
        "bundle",
        "manifest",
        "bundle_sha256",
        "bundle_bytes",
        "file_count",
        "total_bytes",
        "missing_required",
        "external_side_effects",
    ]
    return {key: report.get(key) for key in keys if key in report}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the AIOS runtime deployment bundle.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    report = build(Path(args.output_dir), dry_run=args.dry_run)
    print(json.dumps(summarize(report) if args.summary else report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
