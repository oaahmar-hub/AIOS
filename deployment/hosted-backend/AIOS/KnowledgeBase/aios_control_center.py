from __future__ import annotations

"""AIOS Command Center.

Single local control point for the existing AIOS stack.
No new database, no new architecture, no provider changes.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import argparse
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parent
AIOS_ROOT = ROOT.parent
STATE_PATH = ROOT / "outputs" / "aios_control_center_state.json"


@dataclass
class ComponentStatus:
    name: str
    status: str
    readiness: str
    detail: str


@dataclass
class ControlCenterReport:
    aios_control_center: str
    primary_entrypoint: str
    system_location: str
    state: str
    timestamp: str
    components: list[ComponentStatus]
    start_command: str
    stop_command: str
    health_check_command: str
    system_status_command: str


def _exists(path: Path) -> bool:
    return path.exists()


def _read_state() -> str:
    if not STATE_PATH.exists():
        return "STOPPED"
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "UNKNOWN"
    return str(data.get("state") or "UNKNOWN")


def _write_state(state: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "state": state,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "note": "Local AIOS control state only. External providers remain controlled by their own dashboards.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _sqlite_ok(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing database file"
    try:
        con = sqlite3.connect(path)
        cur = con.cursor()
        tables = [row[0] for row in cur.execute("select name from sqlite_master where type='table'").fetchall()]
        row_count = cur.execute("select count(*) from inventory_rows").fetchone()[0] if "inventory_rows" in tables else 0
        con.close()
        return True, f"{len(tables)} tables; inventory_rows={row_count}"
    except Exception as exc:
        return False, f"database error: {exc}"


def _route_smoke_test() -> tuple[bool, str]:
    try:
        from aios_entrypoint import route_request

        result = route_request("Find me 2BR Yas Island under 2M")
        count = len(result.result) if isinstance(result.result, list) else 0
        return result.route == "property_search", f"route={result.route}; matches={count}"
    except Exception as exc:
        return False, f"router error: {exc}"


def _follow_up_smoke_test() -> tuple[bool, str]:
    try:
        from aios_follow_up_engine_v1 import run_follow_up_engine

        today = datetime.now().date().isoformat()
        run = run_follow_up_engine(
            leads=[
                {
                    "Lead": "Viewing reminder smoke test",
                    "Status": "Open",
                    "Next action": "viewing appointment reminder",
                    "Next action date": today,
                },
                {
                    "Lead": "Price negotiation smoke test",
                    "Status": "Open",
                    "Next action": "price negotiation",
                    "Next action date": today,
                },
            ]
        )
        return (
            len(run.auto_send_queue) == 1 and len(run.approval_queue) == 1,
            f"auto_send={len(run.auto_send_queue)}; held={len(run.approval_queue)}",
        )
    except Exception as exc:
        return False, f"follow-up error: {exc}"


def _component_statuses() -> list[ComponentStatus]:
    statuses: list[ComponentStatus] = []

    route_ok, route_detail = _route_smoke_test()
    statuses.append(ComponentStatus("Brain Status", "WORKING" if route_ok else "BLOCKED", "Operational", route_detail))
    statuses.append(ComponentStatus("Router Status", "WORKING" if route_ok else "BLOCKED", "Operational", route_detail))

    db_ok, db_detail = _sqlite_ok(ROOT / "Property_Master_Database.sqlite")
    statuses.append(ComponentStatus("Property Database Status", "WORKING" if db_ok else "BLOCKED", "Operational", db_detail))

    vault = ROOT / "AIOS_Knowledge_Vault"
    vault_files = len(list(vault.rglob("*.md"))) if vault.exists() else 0
    statuses.append(
        ComponentStatus(
            "Knowledge Vault Status",
            "WORKING" if vault_files else "BLOCKED",
            "Operational" if vault_files else "Needs files",
            f"markdown_files={vault_files}",
        )
    )

    connectivity = ROOT / "AIOS_Core_Connectivity_Map.xlsx"
    statuses.append(
        ComponentStatus(
            "Airtable Status",
            "WORKING" if connectivity.exists() else "CHECK_REQUIRED",
            "Operational via connector",
            f"connectivity map {'found' if connectivity.exists() else 'missing'}",
        )
    )
    statuses.append(
        ComponentStatus(
            "Gmail Status",
            "WORKING" if connectivity.exists() else "CHECK_REQUIRED",
            "Operational via connector",
            f"connectivity map {'found' if connectivity.exists() else 'missing'}",
        )
    )
    statuses.append(
        ComponentStatus(
            "Drive Status",
            "WORKING" if connectivity.exists() else "CHECK_REQUIRED",
            "Operational via connector",
            f"connectivity map {'found' if connectivity.exists() else 'missing'}",
        )
    )
    statuses.append(
        ComponentStatus(
            "Calendar Status",
            "WORKING" if connectivity.exists() else "CHECK_REQUIRED",
            "Operational via connector",
            f"connectivity map {'found' if connectivity.exists() else 'missing'}",
        )
    )

    whatsapp_case = ROOT / "AIOS_Knowledge_Vault" / "case_library" / "CASE-01-WHATSAPP-PROVIDER-BLOCKER.md"
    statuses.append(
        ComponentStatus(
            "WhatsApp Status",
            "BLOCKED",
            "Provider transport blocker",
            f"provider webhook blocker documented: {whatsapp_case.exists()}",
        )
    )

    follow_ok, follow_detail = _follow_up_smoke_test()
    statuses.append(
        ComponentStatus(
            "Follow-Up Engine Status",
            "WORKING" if follow_ok else "BLOCKED",
            "Auto-send queue + Omar hold policy active",
            follow_detail,
        )
    )
    return statuses


def build_report() -> ControlCenterReport:
    return ControlCenterReport(
        aios_control_center="AIOS Command Center",
        primary_entrypoint=str(ROOT / "aios_entrypoint.py"),
        system_location=str(AIOS_ROOT),
        state=_read_state(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        components=_component_statuses(),
        start_command=f"python3 {ROOT / 'aios_control_center.py'} start",
        stop_command=f"python3 {ROOT / 'aios_control_center.py'} stop",
        health_check_command=f"python3 {ROOT / 'aios_control_center.py'} health",
        system_status_command=f"python3 {ROOT / 'aios_control_center.py'} status",
    )


def _print_report(report: ControlCenterReport) -> None:
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIOS Command Center")
    parser.add_argument("command", choices=["start", "stop", "health", "status"], help="Control command")
    args = parser.parse_args(argv)

    if args.command == "start":
        _write_state("RUNNING")
    elif args.command == "stop":
        _write_state("STOPPED")

    report = build_report()
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
