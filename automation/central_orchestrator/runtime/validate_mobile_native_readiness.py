#!/usr/bin/env python3
"""Audit AIOS mobile native build readiness."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "MOBILE_NATIVE_READINESS.json"
BUNDLED_NODE = Path("/Users/hassanka/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
BUNDLED_PNPM = Path("/Users/hassanka/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pnpm")
PROJECT_JDK = ROOT / ".tools/jdk/jdk-17/Contents/Home/bin/java"
PROJECT_ANDROID_SDK = ROOT / ".tools/android-sdk"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def text(path: str) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main() -> int:
    package_json = exists("package.json")
    capacitor_config = exists("capacitor.config.json")
    mobile_html = exists("AIOS-MOBILE-APP.html")
    manifest = exists("aios.webmanifest")
    service_worker = exists("aios-service-worker.js")
    dist_index = exists("mobile-dist/index.html")
    ios_project = exists("ios")
    android_project = exists("android")
    node_available = shutil.which("node") is not None or BUNDLED_NODE.exists()
    npm_available = shutil.which("npm") is not None
    pnpm_available = shutil.which("pnpm") is not None or BUNDLED_PNPM.exists()
    npx_available = shutil.which("npx") is not None
    java_home_probe = __import__("subprocess").run(["/usr/libexec/java_home", "-V"], stdout=__import__("subprocess").PIPE, stderr=__import__("subprocess").STDOUT, text=True).stdout
    java_available = PROJECT_JDK.exists() or (shutil.which("java") is not None and "Unable to locate a Java Runtime" not in java_home_probe)
    android_sdk_available = (PROJECT_ANDROID_SDK / "platforms").exists() or Path("/Users/hassanka/Library/Android/sdk/platforms").exists()
    pod_available = shutil.which("pod") is not None or (Path.home() / ".gem/ruby/2.6.0/bin/pod").exists()
    xcode_project = any((ROOT / "ios").glob("**/*.xcodeproj")) if ios_project else False
    android_gradle = exists("android/gradlew") or exists("android/build.gradle") or exists("android/app/build.gradle")
    mobile_source = text("AIOS-MOBILE-APP.html")
    env_source = text(".env.production.example")
    backend_connection = "/api/permission/evaluate" in mobile_source
    auth_contract = "AIOS_AUTH_MODE" in env_source and "AIOS_BASIC_AUTH" in env_source
    push_native = "@capacitor/push-notifications" in text("package.json") or "PushNotifications" in mobile_source
    ui_notifications = "notificationsList" in mobile_source
    app_store_ready = ios_project and xcode_project and pod_available and auth_contract and backend_connection and push_native
    google_play_ready = android_project and android_gradle and java_available and android_sdk_available and auth_contract and backend_connection and push_native
    native_scaffold_ready = package_json and capacitor_config and dist_index and mobile_html and manifest and service_worker
    blocker_count = 0
    blockers = []
    if not node_available or not pnpm_available:
      blockers.append("Node/pnpm not available; cannot run Capacitor CLI locally.")
    if not ios_project:
      blockers.append("iOS native project not generated yet. CocoaPods is blocked by old system Ruby; install modern Ruby/Homebrew CocoaPods or generate iOS on a Mac with CocoaPods.")
    if not android_project:
      blockers.append("Android native project not generated yet. Run pnpm install, then pnpm exec cap add android.")
    if android_project and not java_available:
      blockers.append("Java runtime/JDK missing; Android APK cannot build locally until JDK is installed.")
    if android_project and not android_sdk_available:
      blockers.append("Android SDK missing; install command-line tools/platform/build-tools after accepting the Android SDK license.")
    if ios_project and not pod_available:
      blockers.append("CocoaPods missing; iOS build cannot sync dependencies locally.")
    if not auth_contract:
      blockers.append("Production mobile auth contract is not fully configured with real hosted secrets.")
    if not backend_connection:
      blockers.append("Mobile app does not call backend API.")
    if not push_native:
      blockers.append("Native push notifications are not configured with APNs/FCM.")
    blocker_count = len(blockers)
    readiness = 55
    if ios_project:
        readiness += 10
    if android_project:
        readiness += 10
    if node_available and pnpm_available:
        readiness += 5
    if android_project:
        readiness += 5
    if java_available:
        readiness += 5
    if android_sdk_available:
        readiness += 5
    if auth_contract:
        readiness += 5
    if push_native:
        readiness += 5
    if app_store_ready and google_play_ready:
        readiness = 95
    readiness = min(readiness, 95)
    report = {
        "validated_at": _now(),
        "mobile_project": "EXISTS" if mobile_html else "DOES NOT EXIST",
        "framework": "Capacitor scaffold over HTML/CSS/JS PWA" if capacitor_config else "HTML/CSS/JS PWA only",
        "native_scaffold_ready": native_scaffold_ready,
        "ios_build": "READY" if ios_project and xcode_project and pod_available else "NOT READY",
        "android_build": "READY" if android_project and android_gradle and java_available and android_sdk_available else "NOT READY",
        "auth": "Runtime Basic Auth contract exists; native mobile login/session flow still pending." if auth_contract else "Not ready; production auth contract missing.",
        "backend_connection": "Partial; mobile calls backend Permission API and local command data, but permanent hosted URL/domain still pending." if backend_connection else "Not connected.",
        "push_notifications": "UI-only notifications; native APNs/FCM not configured." if ui_notifications and not push_native else "Native push configured." if push_native else "Not configured.",
        "app_store_package": "READY" if app_store_ready else "NOT READY",
        "google_play_package": "READY" if google_play_ready else "NOT READY",
        "estimated_completion_percent": readiness,
        "fastest_path_to_testflight": "Install modern Ruby/Homebrew CocoaPods or use a Mac with CocoaPods, run pnpm exec cap add ios, configure signing/backend/auth in Xcode, archive, upload to TestFlight.",
        "fastest_path_to_android_apk": "Accept Android SDK license, install Android command-line tools/platform/build-tools, set ANDROID_HOME, run ./gradlew assembleDebug or assembleRelease.",
        "files": {
            "package_json": package_json,
            "capacitor_config": capacitor_config,
            "mobile_html": mobile_html,
            "web_manifest": manifest,
            "service_worker": service_worker,
            "mobile_dist_index": dist_index,
            "ios_project": ios_project,
            "android_project": android_project,
        },
        "local_tools": {
            "node": node_available,
            "npm": npm_available,
            "pnpm": pnpm_available,
            "npx": npx_available,
            "java_runtime": java_available,
            "project_jdk": PROJECT_JDK.exists(),
            "android_sdk": android_sdk_available,
            "cocoapods": pod_available,
        },
        "blockers": blockers,
        "blocker_count": blocker_count,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if native_scaffold_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
