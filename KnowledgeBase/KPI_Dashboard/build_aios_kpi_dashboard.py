#!/usr/bin/env python3
"""Build the permanent AIOS KPI dashboard."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
OUT_DIR = KB / "KPI_Dashboard"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRUTH_QUALITY_JSON = KB / "TruthIngestion" / "outputs" / "truth_bridge_quality_summary.json"
TRUTH_INGESTION_JSON = KB / "TruthIngestion" / "outputs" / "truth_ingestion_summary.json"
TRUTH_SOURCE_STATUS_CSV = KB / "TruthIngestion" / "outputs" / "truth_ingestion_source_status.csv"
PROPERTY_GRAPH_JSON = KB / "PropertyGraph" / "property_graph_summary.json"
RUN_SUMMARY_JSON = KB / "resolver" / "run_summary.json"
CONTROL_STATE_JSON = KB / "outputs" / "aios_control_center_state.json"
CANONICAL_INVENTORY_CSV = KB / "Canonical" / "AIOS_CANONICAL_FILE_INVENTORY.csv"
VAULT_SOURCE_INVENTORY_CSV = KB / "AIOS_Knowledge_Vault" / "indexes" / "AIOS_Knowledge_Vault_Source_Inventory.csv"
OPERATIONS_CORPUS_INDEX_CSV = KB / "Operations_Knowledge_Corpus_Index.csv"
CASE_LIBRARY_DIR = KB / "AIOS_Knowledge_Vault" / "case_library"
PLAYBOOK_DIR = KB / "AIOS_Knowledge_Vault" / "category_playbooks"

DASHBOARD_MD = OUT_DIR / "AIOS_KPI_DASHBOARD.md"
DASHBOARD_JSON = OUT_DIR / "aios_kpi_dashboard.json"
CURRENT_JSON = OUT_DIR / "aios_kpi_current.json"
HISTORY_CSV = OUT_DIR / "aios_kpi_history.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def read_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def count_files(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    return len(list(path.glob(pattern)))


def score_label(score: float) -> str:
    if score >= 80:
        return "STRONG"
    if score >= 60:
        return "STABLE"
    if score >= 40:
        return "PARTIAL"
    return "WEAK"


def trend_label(previous: float | None, current: float) -> str:
    if previous is None:
        return "BASELINE"
    delta = round(current - previous, 2)
    if delta > 1:
        return f"UP {delta}"
    if delta < -1:
        return f"DOWN {abs(delta)}"
    return f"FLAT {delta}"


def load_previous_scores() -> Dict[str, float]:
    if not HISTORY_CSV.exists():
        return {}
    rows = read_csv_rows(HISTORY_CSV)
    if not rows:
        return {}
    last = rows[-1]
    return {
        "truth_health": float(last.get("truth_health", "0") or 0),
        "memory_health": float(last.get("memory_health", "0") or 0),
        "knowledge_health": float(last.get("knowledge_health", "0") or 0),
        "decision_health": float(last.get("decision_health", "0") or 0),
    }


def build_truth_health(truth_quality: Dict[str, object], truth_ingestion: Dict[str, object], property_graph: Dict[str, object]) -> Dict[str, object]:
    quality_score = float(truth_quality.get("truth_bridge_quality_score", 0) or 0)
    exact_pct = float(truth_quality.get("percentages", {}).get("Exact", 0) or 0)
    high_pct = float(truth_quality.get("percentages", {}).get("High-confidence", 0) or 0)
    ingestion_class = str(truth_ingestion.get("classification", "FAILED"))
    ingestion_score = {"LIVE": 100, "PARTIAL": 65, "FAILED": 25}.get(ingestion_class, 25)
    bridge_rows = float(property_graph.get("bridge_rows", 0) or 0)
    exact_strength = clamp(exact_pct * 8 + high_pct * 4)
    coverage_strength = clamp((bridge_rows / 1500) * 100)
    score = round(quality_score * 0.5 + ingestion_score * 0.25 + exact_strength * 0.15 + coverage_strength * 0.10, 2)
    gaps = truth_quality.get("remaining_data_gaps", [])
    recs = truth_quality.get("recommended_high_value_sources", [])
    return {
        "score": score,
        "bottleneck": gaps[0] if gaps else "Trusted exact bridge relationships remain thin.",
        "improvement": recs[0] if recs else "Improve exact bridge sources over partial bridge volume.",
        "notes": {
            "truth_bridge_quality_score": quality_score,
            "exact_bridge_pct": exact_pct,
            "high_confidence_pct": high_pct,
            "bridge_rows": bridge_rows,
        },
    }


def build_memory_health(control_state: Dict[str, object], source_status_rows: List[Dict[str, str]], vault_rows: List[Dict[str, str]], ops_rows: List[Dict[str, str]], canonical_rows: List[Dict[str, str]]) -> Dict[str, object]:
    state = str(control_state.get("state", "UNKNOWN"))
    control_score = 15 if state == "RUNNING" else 0
    vault_score = clamp(len(vault_rows) / 5 * 20)
    downloaded_ratio = 0.0
    if ops_rows:
        downloaded = sum(1 for row in ops_rows if row.get("Downloaded", "").upper() == "YES")
        downloaded_ratio = downloaded / len(ops_rows)
    ops_score = round(downloaded_ratio * 20, 2)
    canonical_score = 15 if len(canonical_rows) >= 1000 else clamp(len(canonical_rows) / 1000 * 15)
    memory_rows = {row["source"]: row for row in source_status_rows}
    runtime_rows = int(memory_rows.get("Runtime Memory Ledger", {}).get("imported_rows", "0") or 0)
    bitrix_rows = int(memory_rows.get("Bitrix24/raw", {}).get("imported_rows", "0") or 0)
    structured_memory_score = 30 if runtime_rows > 0 else (15 if bitrix_rows > 0 else 5)
    score = round(control_score + vault_score + ops_score + canonical_score + structured_memory_score, 2)
    bottleneck = "Runtime memory ledger is present but not producing structured trusted memory rows."
    improvement = "Convert runtime memory and Bitrix raw history into structured, source-linked memory packets with entity-level provenance."
    return {
        "score": score,
        "bottleneck": bottleneck,
        "improvement": improvement,
        "notes": {
            "control_state": state,
            "vault_sources": len(vault_rows),
            "operations_corpus_rows": len(ops_rows),
            "canonical_inventory_rows": len(canonical_rows),
            "runtime_memory_rows": runtime_rows,
            "bitrix_memory_rows": bitrix_rows,
        },
    }


def build_knowledge_health(vault_rows: List[Dict[str, str]], ops_rows: List[Dict[str, str]], canonical_rows: List[Dict[str, str]], case_count: int, playbook_count: int) -> Dict[str, object]:
    vault_score = clamp(len(vault_rows) / 10 * 20)
    ops_downloaded = sum(1 for row in ops_rows if row.get("Downloaded", "").upper() == "YES")
    ops_score = clamp((ops_downloaded / max(1, len(ops_rows))) * 30)
    canonical_score = 20 if len(canonical_rows) >= 2000 else clamp(len(canonical_rows) / 2000 * 20)
    case_score = clamp(case_count / 8 * 15)
    playbook_score = clamp(playbook_count / 8 * 15)
    score = round(vault_score + ops_score + canonical_score + case_score + playbook_score, 2)
    bottleneck = "Knowledge provenance is concentrated in a small set of explicit vault sources relative to the wider canonical corpus."
    improvement = "Expand source-indexed Knowledge Vault ingestion and attach stronger provenance links from canonical files into reusable case/playbook knowledge."
    return {
        "score": score,
        "bottleneck": bottleneck,
        "improvement": improvement,
        "notes": {
            "vault_sources": len(vault_rows),
            "operations_downloaded": ops_downloaded,
            "operations_total": len(ops_rows),
            "canonical_inventory_rows": len(canonical_rows),
            "case_library_files": case_count,
            "playbook_files": playbook_count,
        },
    }


def build_decision_health(run_summary: Dict[str, object], property_graph: Dict[str, object], truth_quality: Dict[str, object], control_state: Dict[str, object]) -> Dict[str, object]:
    total_records = float(run_summary.get("total_records_indexed", 0) or 0)
    high_conf = float(run_summary.get("confidence_distribution_90_plus", 0) or 0) + float(run_summary.get("confidence_distribution_80_89", 0) or 0)
    high_conf_rate = (high_conf / total_records * 100) if total_records else 0.0
    verification_queue = float(property_graph.get("verification_queue", 0) or 0)
    queue_score = clamp((1 - (verification_queue / max(1.0, total_records))) * 100)
    bridge_quality_score = float(truth_quality.get("truth_bridge_quality_score", 0) or 0)
    public_listing_cpid_count = float(property_graph.get("public_listing_cpid_count", 0) or 0)
    public_listing_score = 20 if public_listing_cpid_count >= 20 else clamp(public_listing_cpid_count / 20 * 20)
    control_bonus = 10 if str(control_state.get("state", "")) == "RUNNING" else 0
    score = round(high_conf_rate * 0.45 + queue_score * 0.25 + bridge_quality_score * 0.20 + public_listing_score * 0.10 + control_bonus, 2)
    failures = run_summary.get("top_failure_reasons", [])
    bottleneck = failures[0] if failures else "High-confidence decisions are constrained by weak exact bridge coverage."
    improvement = "Promote exact bridge sources into canonical property links and reduce the verification queue by resolving bridge rows with hard identifiers."
    return {
        "score": score,
        "bottleneck": bottleneck,
        "improvement": improvement,
        "notes": {
            "high_confidence_rate_pct": round(high_conf_rate, 2),
            "verification_queue": verification_queue,
            "truth_bridge_quality_score": bridge_quality_score,
            "public_listing_cpid_count": public_listing_cpid_count,
        },
    }


def append_history(timestamp: str, metrics: Dict[str, Dict[str, object]]) -> None:
    fieldnames = ["timestamp", "truth_health", "memory_health", "knowledge_health", "decision_health"]
    row = {
        "timestamp": timestamp,
        "truth_health": metrics["Truth Health"]["score"],
        "memory_health": metrics["Memory Health"]["score"],
        "knowledge_health": metrics["Knowledge Health"]["score"],
        "decision_health": metrics["Decision Health"]["score"],
    }
    exists = HISTORY_CSV.exists()
    with HISTORY_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    truth_quality = read_json(TRUTH_QUALITY_JSON)
    truth_ingestion = read_json(TRUTH_INGESTION_JSON)
    property_graph = read_json(PROPERTY_GRAPH_JSON)
    run_summary = read_json(RUN_SUMMARY_JSON)
    control_state = read_json(CONTROL_STATE_JSON)
    source_status_rows = read_csv_rows(TRUTH_SOURCE_STATUS_CSV)
    canonical_rows = read_csv_rows(CANONICAL_INVENTORY_CSV)
    vault_rows = read_csv_rows(VAULT_SOURCE_INVENTORY_CSV)
    ops_rows = read_csv_rows(OPERATIONS_CORPUS_INDEX_CSV)
    case_count = count_files(CASE_LIBRARY_DIR, "*.md")
    playbook_count = count_files(PLAYBOOK_DIR, "*.md")

    previous = load_previous_scores()

    metrics = {
        "Truth Health": build_truth_health(truth_quality, truth_ingestion, property_graph),
        "Memory Health": build_memory_health(control_state, source_status_rows, vault_rows, ops_rows, canonical_rows),
        "Knowledge Health": build_knowledge_health(vault_rows, ops_rows, canonical_rows, case_count, playbook_count),
        "Decision Health": build_decision_health(run_summary, property_graph, truth_quality, control_state),
    }

    timestamp = now_iso()
    for key, previous_key in [
        ("Truth Health", "truth_health"),
        ("Memory Health", "memory_health"),
        ("Knowledge Health", "knowledge_health"),
        ("Decision Health", "decision_health"),
    ]:
        metrics[key]["trend"] = trend_label(previous.get(previous_key), float(metrics[key]["score"]))
        metrics[key]["label"] = score_label(float(metrics[key]["score"]))

    append_history(timestamp, metrics)

    dashboard = {
        "generated_at": timestamp,
        "metrics": metrics,
        "ceo_summary": {
            "strongest_metric": max(metrics.items(), key=lambda item: item[1]["score"])[0],
            "weakest_metric": min(metrics.items(), key=lambda item: item[1]["score"])[0],
        },
        "evidence": {
            "truth_quality": str(TRUTH_QUALITY_JSON),
            "truth_ingestion": str(TRUTH_INGESTION_JSON),
            "property_graph": str(PROPERTY_GRAPH_JSON),
            "resolver_run_summary": str(RUN_SUMMARY_JSON),
            "history_csv": str(HISTORY_CSV),
        },
    }

    lines = [
        "# AIOS KPI Dashboard",
        "",
        f"- generated_at: `{timestamp}`",
        f"- strongest_metric: `{dashboard['ceo_summary']['strongest_metric']}`",
        f"- weakest_metric: `{dashboard['ceo_summary']['weakest_metric']}`",
        "",
        "| Metric | Score | Status | Trend | Biggest bottleneck | Highest-impact improvement |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for metric_name in ["Truth Health", "Memory Health", "Knowledge Health", "Decision Health"]:
        metric = metrics[metric_name]
        lines.append(
            f"| {metric_name} | {metric['score']} | {metric['label']} | {metric['trend']} | {metric['bottleneck']} | {metric['improvement']} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Scores optimize for trusted intelligence, not raw row volume.",
            "- `BASELINE` trend means this is the first permanent snapshot for that metric in the KPI history.",
            "",
            "## Evidence",
            "",
            f"- current_json: `{CURRENT_JSON}`",
            f"- history_csv: `{HISTORY_CSV}`",
        ]
    )

    DASHBOARD_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    DASHBOARD_JSON.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    CURRENT_JSON.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dashboard, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
