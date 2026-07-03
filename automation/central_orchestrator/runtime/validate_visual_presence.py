#!/usr/bin/env python3
"""Validate AIOS first-impression visual presence.

This captures the user-facing entry surfaces and checks that they are not blank,
not purple-dominant, and visually signal the AIOS Eye experience.
"""
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

from PIL import Image, ImageStat


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
VISUAL_DIR = REPORTS_DIR / "visual-proof"
REPORT_PATH = REPORTS_DIR / "VISUAL_PRESENCE_VALIDATION.json"

DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SURFACES = [
    {
        "name": "website_eye",
        "path": "AIOS-WEBSITE.html",
        "viewport": (1440, 1000),
        "screenshot": "visual_presence_website_eye.png",
        "min_nonblack_ratio": 0.74,
        "min_green_signal_ratio": 0.025,
        "min_combined_signal_ratio": 0.10,
        "min_center_presence_ratio": 0.16,
        "max_purple_signal_ratio": 0.01,
    },
    {
        "name": "command_center_eye",
        "path": "AIOS-DASHBOARD.html?screen=eye",
        "viewport": (1440, 1000),
        "screenshot": "visual_presence_command_eye.png",
        "min_nonblack_ratio": 0.30,
        "min_green_signal_ratio": 0.015,
        "min_combined_signal_ratio": 0.025,
        "min_center_presence_ratio": 0.07,
        "max_purple_signal_ratio": 0.01,
    },
    {
        "name": "mobile_console",
        "path": "AIOS-MOBILE-APP.html",
        "viewport": (390, 844),
        "screenshot": "visual_presence_mobile_console.png",
        "min_nonblack_ratio": 0.44,
        "min_green_signal_ratio": 0.035,
        "min_combined_signal_ratio": 0.04,
        "min_center_presence_ratio": 0.07,
        "max_purple_signal_ratio": 0.01,
    },
    {
        "name": "offline_shell",
        "path": "offline.html",
        "viewport": (390, 844),
        "screenshot": "visual_presence_offline_shell.png",
        "min_nonblack_ratio": 0.20,
        "min_green_signal_ratio": 0.025,
        "min_combined_signal_ratio": 0.025,
        "min_center_presence_ratio": 0.035,
        "max_purple_signal_ratio": 0.01,
    },
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


def _capture(chrome: str, url: str, output: Path, viewport: tuple[int, int], timeout: int) -> dict[str, Any]:
    profile = Path("/tmp") / f"aios-visual-proof-{output.stem}-{int(time.time() * 1000)}"
    if profile.exists():
        shutil.rmtree(profile)
    command = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--user-data-dir={profile}",
        f"--window-size={viewport[0]},{viewport[1]}",
        "--virtual-time-budget=4500",
        f"--screenshot={output}",
        url,
    ]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return {
            "returncode": completed.returncode,
            "timed_out": False,
            "stdout_tail": completed.stdout[-400:],
            "stderr_tail": completed.stderr[-800:],
        }
    except subprocess.TimeoutExpired as exc:
        screenshot_written = output.exists() and output.stat().st_size > 10_000
        return {
            "returncode": 0 if screenshot_written else None,
            "timed_out": not screenshot_written,
            "completed_from_screenshot": screenshot_written,
            "stdout_tail": (exc.stdout or "")[-400:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-800:] if isinstance(exc.stderr, str) else "",
        }
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _image_metrics(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    width, height = image.size
    pixels = image.load()
    nonblack = 0
    green_signal = 0
    gold_signal = 0
    purple_signal = 0
    center_presence = 0
    center_samples = 0
    samples = 0
    cx = width / 2
    cy = height / 2
    radius = min(width, height) * 0.28
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            r, g, b = pixels[x, y]
            samples += 1
            in_center = ((x - cx) ** 2 + ((y - cy) * 1.12) ** 2) <= radius ** 2
            if in_center:
                center_samples += 1
            if max(r, g, b) > 18:
                nonblack += 1
            if g > r + 18 and g > b + 12 and g > 64:
                green_signal += 1
            if r > 110 and g > 88 and b < 96:
                gold_signal += 1
            if b > r + 30 and r > 70 and g < 120:
                purple_signal += 1
            if in_center and (
                max(r, g, b) > 54
                or (g > r + 14 and g > b + 10 and g > 54)
                or (r > 96 and g > 76 and b < 116)
            ):
                center_presence += 1
    return {
        "size": [width, height],
        "avg_rgb": [round(value, 2) for value in stat.mean],
        "nonblack_ratio": round(nonblack / samples, 4),
        "green_signal_ratio": round(green_signal / samples, 4),
        "gold_signal_ratio": round(gold_signal / samples, 4),
        "combined_signal_ratio": round((green_signal + gold_signal) / samples, 4),
        "center_presence_ratio": round(center_presence / max(center_samples, 1), 4),
        "purple_signal_ratio": round(purple_signal / samples, 4),
    }


def validate(base_url: str, chrome_path: str = DEFAULT_CHROME, timeout: int = 12) -> dict[str, Any]:
    chrome = _resolve_chrome(chrome_path)
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    checks = []
    for surface in SURFACES:
        output = VISUAL_DIR / surface["screenshot"]
        url = _surface_url(base_url, surface["path"])
        capture = _capture(chrome, url, output, surface["viewport"], timeout)
        metrics: dict[str, Any] = {}
        if output.exists() and output.stat().st_size > 10_000:
            metrics = _image_metrics(output)
        passed = (
            bool(metrics)
            and metrics["nonblack_ratio"] >= surface["min_nonblack_ratio"]
            and metrics["green_signal_ratio"] >= surface["min_green_signal_ratio"]
            and metrics["combined_signal_ratio"] >= surface["min_combined_signal_ratio"]
            and metrics["center_presence_ratio"] >= surface["min_center_presence_ratio"]
            and metrics["purple_signal_ratio"] <= surface["max_purple_signal_ratio"]
        )
        checks.append(
            {
                "name": surface["name"],
                "passed": passed,
                "url": url,
                "viewport": list(surface["viewport"]),
                "screenshot": str(output.relative_to(REPORTS_DIR.parent.parent)),
                "capture": capture,
                "thresholds": {
                    "min_nonblack_ratio": surface["min_nonblack_ratio"],
                    "min_green_signal_ratio": surface["min_green_signal_ratio"],
                    "min_combined_signal_ratio": surface["min_combined_signal_ratio"],
                    "min_center_presence_ratio": surface["min_center_presence_ratio"],
                    "max_purple_signal_ratio": surface["max_purple_signal_ratio"],
                },
                "metrics": metrics,
            }
        )
    report = {
        "validated_at": _now(),
        "base_url": base_url.rstrip("/"),
        "passed": all(check["passed"] for check in checks),
        "checks_passed": sum(1 for check in checks if check["passed"]),
        "checks_total": len(checks),
        "chrome": chrome,
        "checks": checks,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AIOS visual first-impression presence.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8765")
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()
    report = validate(args.base_url, chrome_path=args.chrome, timeout=args.timeout)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
