#!/usr/bin/env python3
"""Validate that the AIOS Eye feels alive over a 10-second viewing window."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from PIL import Image, ImageChops, ImageStat


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
VISUAL_DIR = REPORTS_DIR / "visual-proof"
REPORT_PATH = REPORTS_DIR / "EYE_MOTION_VALIDATION.json"

DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SURFACES = [
    {
        "name": "website_eye_10s",
        "path": "AIOS-WEBSITE.html",
        "viewport": (1440, 1000),
        "first_ms": 1200,
        "second_ms": 10000,
        "min_changed_ratio": 0.018,
        "min_center_changed_ratio": 0.018,
        "min_mean_delta": 1.2,
    },
    {
        "name": "command_eye_10s",
        "path": "AIOS-DASHBOARD.html?screen=eye",
        "viewport": (1440, 1000),
        "first_ms": 1200,
        "second_ms": 10000,
        "min_changed_ratio": 0.020,
        "min_center_changed_ratio": 0.025,
        "min_mean_delta": 1.5,
    },
    {
        "name": "mobile_eye_10s",
        "path": "AIOS-MOBILE-APP.html",
        "viewport": (390, 844),
        "first_ms": 1200,
        "second_ms": 10000,
        "min_changed_ratio": 0.012,
        "min_center_changed_ratio": 0.012,
        "min_mean_delta": 0.9,
    },
]

STATIC_NEEDLES = [
    ("environment_canvas", "id=\"eyeEnvironmentCanvas\""),
    ("environment_webgl_runtime", "startEyeEnvironmentWebGL"),
    ("lens_webgl_runtime", "startEyeWebGLPortal"),
    ("business_telemetry_bridge", "updateEyeBusinessTelemetry"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_chrome(chrome_path: str) -> str:
    if Path(chrome_path).exists():
        return chrome_path
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        return found
    raise FileNotFoundError(f"Chrome executable not found: {chrome_path}")


def _surface_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path)


def _capture(chrome: str, url: str, output: Path, viewport: tuple[int, int], virtual_time_ms: int, timeout: int) -> dict[str, Any]:
    profile = Path("/tmp") / f"aios-eye-motion-{output.stem}-{int(time.time() * 1000)}"
    shutil.rmtree(profile, ignore_errors=True)
    command = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        f"--user-data-dir={profile}",
        f"--window-size={viewport[0]},{viewport[1]}",
        f"--virtual-time-budget={virtual_time_ms}",
        f"--screenshot={output}",
        url,
    ]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return {
            "returncode": completed.returncode,
            "timed_out": False,
            "virtual_time_ms": virtual_time_ms,
            "stdout_tail": completed.stdout[-400:],
            "stderr_tail": completed.stderr[-800:],
        }
    except subprocess.TimeoutExpired as exc:
        screenshot_written = output.exists() and output.stat().st_size > 10_000
        return {
            "returncode": 0 if screenshot_written else None,
            "timed_out": not screenshot_written,
            "completed_from_screenshot": screenshot_written,
            "virtual_time_ms": virtual_time_ms,
            "stdout_tail": (exc.stdout or "")[-400:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-800:] if isinstance(exc.stderr, str) else "",
        }
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _motion_metrics(first: Path, second: Path) -> dict[str, Any]:
    a = Image.open(first).convert("RGB")
    b = Image.open(second).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    width, height = diff.size
    pixels = diff.load()
    samples = 0
    changed = 0
    center_samples = 0
    center_changed = 0
    cx = width / 2
    cy = height / 2
    radius = min(width, height) * 0.30
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            r, g, b = pixels[x, y]
            delta = max(r, g, b)
            samples += 1
            in_center = ((x - cx) ** 2 + ((y - cy) * 1.12) ** 2) <= radius ** 2
            if delta > 12:
                changed += 1
            if in_center:
                center_samples += 1
                if delta > 12:
                    center_changed += 1
    diff_path = second.with_name(second.stem + "_diff.png")
    diff.save(diff_path)
    return {
        "size": [width, height],
        "mean_delta_rgb": [round(value, 3) for value in stat.mean],
        "mean_delta": round(sum(stat.mean) / 3, 3),
        "changed_ratio": round(changed / max(samples, 1), 4),
        "center_changed_ratio": round(center_changed / max(center_samples, 1), 4),
        "diff_screenshot": str(diff_path.relative_to(REPORTS_DIR.parent.parent)),
    }


def validate(base_url: str, chrome_path: str = DEFAULT_CHROME, timeout: int = 18) -> dict[str, Any]:
    chrome = _resolve_chrome(chrome_path)
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    dashboard_path = RUNTIME_DIR.parents[2] / "AIOS-DASHBOARD.html"
    dashboard_source = dashboard_path.read_text(encoding="utf-8") if dashboard_path.exists() else ""
    static_checks = [
        {
            "name": name,
            "passed": needle in dashboard_source,
            "needle": needle,
        }
        for name, needle in STATIC_NEEDLES
    ]
    checks = []
    for surface in SURFACES:
        url = _surface_url(base_url, surface["path"])
        first = VISUAL_DIR / f"{surface['name']}_t1.png"
        second = VISUAL_DIR / f"{surface['name']}_t10.png"
        first_capture = _capture(chrome, url, first, surface["viewport"], surface["first_ms"], timeout)
        second_capture = _capture(chrome, url, second, surface["viewport"], surface["second_ms"], timeout)
        metrics: dict[str, Any] = {}
        if first.exists() and first.stat().st_size > 10_000 and second.exists() and second.stat().st_size > 10_000:
            metrics = _motion_metrics(first, second)
        passed = (
            bool(metrics)
            and metrics["changed_ratio"] >= surface["min_changed_ratio"]
            and metrics["center_changed_ratio"] >= surface["min_center_changed_ratio"]
            and metrics["mean_delta"] >= surface["min_mean_delta"]
        )
        checks.append(
            {
                "name": surface["name"],
                "passed": passed,
                "url": url,
                "viewport": list(surface["viewport"]),
                "screenshots": {
                    "t1": str(first.relative_to(REPORTS_DIR.parent.parent)),
                    "t10": str(second.relative_to(REPORTS_DIR.parent.parent)),
                },
                "captures": {
                    "t1": first_capture,
                    "t10": second_capture,
                },
                "thresholds": {
                    "min_changed_ratio": surface["min_changed_ratio"],
                    "min_center_changed_ratio": surface["min_center_changed_ratio"],
                    "min_mean_delta": surface["min_mean_delta"],
                },
                "metrics": metrics,
            }
        )
    report = {
        "validated_at": _now(),
        "base_url": base_url.rstrip("/"),
        "passed": all(check["passed"] for check in checks) and all(check["passed"] for check in static_checks),
        "checks_passed": sum(1 for check in checks if check["passed"]) + sum(1 for check in static_checks if check["passed"]),
        "checks_total": len(checks) + len(static_checks),
        "chrome": chrome,
        "static_checks": static_checks,
        "checks": checks,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AIOS Eye motion over a 10-second viewing window.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8765")
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    parser.add_argument("--timeout", type=int, default=18)
    args = parser.parse_args()
    report = validate(args.base_url, chrome_path=args.chrome, timeout=args.timeout)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
