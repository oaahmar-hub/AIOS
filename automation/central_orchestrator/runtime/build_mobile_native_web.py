#!/usr/bin/env python3
"""Build the AIOS web bundle used by Capacitor native shells."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
DIST = ROOT / "mobile-dist"
REPORT_PATH = REPORTS_DIR / "MOBILE_NATIVE_WEB_BUILD.json"

FILES = [
    "AIOS-MOBILE-APP.html",
    "AIOS-DASHBOARD.html",
    "AIOS-WEBSITE.html",
    "AIOS-RUNTIME-STATUS.html",
    "offline.html",
    "aios.webmanifest",
    "aios-service-worker.js",
    "automation/central_orchestrator/reports/COMMAND_CENTER_DATA.json",
]

DIRS = [
    "assets",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def copy_file(src: Path, dst: Path) -> dict[str, object]:
    item = {"source": str(src.relative_to(ROOT)), "target": str(dst.relative_to(ROOT)), "exists": src.exists(), "copied": False}
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        item["copied"] = True
        item["bytes"] = dst.stat().st_size
    return item


def copy_dir(src: Path, dst: Path) -> dict[str, object]:
    item = {"source": str(src.relative_to(ROOT)), "target": str(dst.relative_to(ROOT)), "exists": src.exists(), "copied": False}
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst)
        ignore = shutil.ignore_patterns(
            "*.log",
            "*.sqlite",
            "*.sqlite-*",
            "deployment-bundles",
            "aios-eye-cinematic-loop-phase52.mp4",
            "aios-eye-cinematic-loop-phase53.mp4",
            "aios-eye-cinematic-loop-phase54.mp4",
        )
        shutil.copytree(src, dst, ignore=ignore)
        item["copied"] = True
        item["file_count"] = sum(1 for p in dst.rglob("*") if p.is_file())
    return item


def build() -> dict[str, object]:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    copied_files = [copy_file(ROOT / name, DIST / name) for name in FILES]
    copied_dirs = [copy_dir(ROOT / name, DIST / name) for name in DIRS]

    index = DIST / "index.html"
    if (DIST / "AIOS-MOBILE-APP.html").exists():
        shutil.copy2(DIST / "AIOS-MOBILE-APP.html", index)

    native_manifest = {
        "generated_at": _now(),
        "product": "AIOS Mobile Native Web Bundle",
        "entry": "index.html",
        "source_entry": "AIOS-MOBILE-APP.html",
        "capacitor_web_dir": "mobile-dist",
        "backend_expectation": "Hosted AIOS API must be available through production domain before store release.",
        "auth_expectation": "Production mobile auth still required before TestFlight or Play internal testing.",
        "files": copied_files,
        "directories": copied_dirs,
        "ready_for_capacitor_sync": index.exists() and all(item["copied"] for item in copied_files if item["source"] in {"AIOS-MOBILE-APP.html", "aios.webmanifest", "aios-service-worker.js"}),
    }
    (DIST / "AIOS_NATIVE_BUNDLE.json").write_text(json.dumps(native_manifest, indent=2) + "\n", encoding="utf-8")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(native_manifest, indent=2) + "\n", encoding="utf-8")
    return native_manifest


def main() -> int:
    report = build()
    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_capacitor_sync"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
