from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable, Optional


DB_PATH = Path(
    os.getenv(
        "AIOS_PROPERTY_DB_PATH",
        str(Path(__file__).resolve().parent / "Property_Master_Database.sqlite"),
    )
).expanduser().resolve()


def canon(text: object) -> str:
    s = re.sub(r"\s+", " ", re.sub(r"[\u200e\u200f]+", "", str(text or "").strip())).strip().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\u200e", "").replace("\u200f", "")).strip()


def parse_int(text: object) -> Optional[int]:
    if text is None:
        return None
    s = str(text).replace(",", "").replace("AED", "").replace("aed", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except Exception:
        return None


def parse_bedroom_count(text: object) -> Optional[int]:
    s = canon(text)
    if not s:
        return None
    if "studio" in s:
        return 0
    m = re.search(r"(\d+)\s*(?:bed|br|bdr|bedroom)", s)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d)\b", s)
    if "bed" in s or "br" in s or "bedroom" in s:
        return int(m.group(1)) if m else None
    return None


def parse_raw_json(raw_json: str) -> dict:
    try:
        return json.loads(raw_json)
    except Exception:
        return {}


def extract_numeric_candidates(payload: dict) -> list[int]:
    candidates: list[int] = []
    raw = payload.get("raw")
    if isinstance(raw, list):
        for item in raw:
            val = parse_int(item)
            if val is not None:
                candidates.append(val)
    for key in ("price", "area_value"):
        val = parse_int(payload.get(key))
        if val is not None:
            candidates.append(val)
    return [c for c in candidates if c > 0]


def inferred_price(payload: dict, inventory_type: str = "") -> Optional[int]:
    if canon(inventory_type) == "owners list":
        return None
    nums = extract_numeric_candidates(payload)
    if not nums:
        return None
    # Most inventory sheets store the actual asking price as a later/larger numeric token.
    # Using the maximum numeric candidate works reliably across the acquired spreadsheets.
    if max(nums) < 1000:
        return None
    return max(nums)


def score_row(
    row: sqlite3.Row,
    query_terms: dict,
    price_cap: Optional[int],
    ready_only: bool = False,
) -> tuple[float, Optional[int]]:
    payload = parse_raw_json(row["raw_json"])
    price = inferred_price(payload, row["inventory_type"])
    score = 0.0

    area = norm(row["area_name"])
    project = norm(row["project_name"])
    developer = norm(row["developer_name"])
    ptype = norm(row["property_type_name"])
    bedrooms_text = norm(row["bedrooms"])
    raw_text = canon(row["raw_json"])
    inventory_type = canon(row["inventory_type"])
    status = canon(row["status"])

    def has_term(field: str, term: str) -> bool:
        return bool(term) and term in canon(field)

    if query_terms.get("area") and has_term(area, query_terms["area"]):
        score += 100
    elif query_terms.get("area") and query_terms["area"] in raw_text:
        score += 60

    if query_terms.get("project") and has_term(project, query_terms["project"]):
        score += 100
    elif query_terms.get("project") and query_terms["project"] in raw_text:
        score += 60

    if query_terms.get("developer") and has_term(developer, query_terms["developer"]):
        score += 100
    elif query_terms.get("developer") and query_terms["developer"] in raw_text:
        score += 60

    if query_terms.get("property_type") and (
        has_term(ptype, query_terms["property_type"]) or query_terms["property_type"] in raw_text
    ):
        score += 70

    qb = query_terms.get("bedrooms")
    if qb is not None:
        row_beds = parse_bedroom_count(bedrooms_text)
        if row_beds == qb:
            score += 60
        elif row_beds is not None and abs(row_beds - qb) == 1:
            score += 15
        elif qb == 0 and "studio" in canon(bedrooms_text):
            score += 60

    if price_cap is not None and price is not None:
        if price <= price_cap:
            score += 40
            # Prefer lower prices within budget, but keep the ranking readable.
            score += max(0.0, 20.0 * (1.0 - (price / price_cap)))
        else:
            score -= min(30.0, (price - price_cap) / max(price_cap, 1) * 10.0)
    elif price is not None:
        score += 5

    if ready_only:
        if any(k in raw_text for k in ("ready", "available", "handover")) or inventory_type in {"availability", "handover", "price list"}:
            score += 25
        if status in {"ready", "available", "handover"}:
            score += 25

    return score, price


@dataclass
class Match:
    project: str
    area: str
    developer: str
    bedrooms: str
    property_type: str
    inventory_type: str
    status: str
    price: Optional[int]
    source_group: str
    file_name: str
    score: float


class PropertyRecommendationAgent:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _all_rows(self) -> list[sqlite3.Row]:
        con = self._connect()
        cur = con.cursor()
        rows = cur.execute(
            """
            SELECT
                ir.raw_json,
                ir.bedrooms,
                ir.status,
                ir.inventory_type,
                IFNULL(p.name, '') AS project_name,
                IFNULL(a.name, '') AS area_name,
                IFNULL(d.name, '') AS developer_name,
                IFNULL(pt.name, '') AS property_type_name,
                IFNULL(f.file_name, '') AS file_name,
                IFNULL(f.source_group, '') AS source_group
            FROM inventory_rows ir
            LEFT JOIN projects p ON ir.project_id = p.project_id
            LEFT JOIN areas a ON ir.area_id = a.area_id
            LEFT JOIN developers d ON ir.developer_id = d.developer_id
            LEFT JOIN property_types pt ON ir.property_type_id = pt.property_type_id
            LEFT JOIN inventory_files f ON ir.source_id = f.source_id
            """
        ).fetchall()
        con.close()
        return rows

    def _candidate_rows(
        self,
        *,
        area: str = "",
        project: str = "",
        developer: str = "",
        bedrooms: Optional[int] = None,
        property_type: str = "",
        limit: Optional[int] = None,
        raw_term: str = "",
    ) -> list[sqlite3.Row]:
        clauses = []
        params: list[object] = []

        if area:
            clauses.append("lower(json_extract(ir.raw_json, '$.area')) LIKE ?")
            params.append(f"%{canon(area)}%")
        if project:
            clauses.append("lower(json_extract(ir.raw_json, '$.project')) LIKE ?")
            params.append(f"%{canon(project)}%")
        if developer:
            clauses.append("lower(json_extract(ir.raw_json, '$.developer')) LIKE ?")
            params.append(f"%{canon(developer)}%")
        if property_type:
            clauses.append("lower(json_extract(ir.raw_json, '$.property_type')) LIKE ?")
            params.append(f"%{canon(property_type)}%")
        if bedrooms is not None:
            if bedrooms == 0:
                clauses.append("lower(json_extract(ir.raw_json, '$.bedrooms')) LIKE ?")
                params.append("%studio%")
            else:
                clauses.append("lower(json_extract(ir.raw_json, '$.bedrooms')) LIKE ?")
                params.append(f"%{bedrooms}%")
        if raw_term:
            clauses.append("lower(ir.raw_json) LIKE ?")
            params.append(f"%{canon(raw_term)}%")

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"""
            SELECT
                ir.raw_json,
                ir.bedrooms,
                ir.status,
                ir.inventory_type,
                IFNULL(p.name, '') AS project_name,
                IFNULL(a.name, '') AS area_name,
                IFNULL(d.name, '') AS developer_name,
                IFNULL(pt.name, '') AS property_type_name,
                IFNULL(f.file_name, '') AS file_name,
                IFNULL(f.source_group, '') AS source_group
            FROM inventory_rows ir
            LEFT JOIN projects p ON ir.project_id = p.project_id
            LEFT JOIN areas a ON ir.area_id = a.area_id
            LEFT JOIN developers d ON ir.developer_id = d.developer_id
            LEFT JOIN property_types pt ON ir.property_type_id = pt.property_type_id
            LEFT JOIN inventory_files f ON ir.source_id = f.source_id
            {where}
        """
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        con = self._connect()
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        return rows

    def search(
        self,
        *,
        area: str = "",
        project: str = "",
        developer: str = "",
        bedrooms: Optional[int] = None,
        property_type: str = "",
        max_price: Optional[int] = None,
        query_text: str = "",
        ready_only: bool = False,
        limit: int = 10,
    ) -> list[Match]:
        q = canon(query_text)
        if not area:
            for term in ("yas island", "saadiyat island", "al reem island", "abu dhabi"):
                if term in q:
                    area = term.title()
                    break
        if bedrooms is None:
            m = re.search(r"\b(\d+)\s*(?:br|bed|bedroom)\b", q)
            if m:
                bedrooms = int(m.group(1))
            elif "studio" in q:
                bedrooms = 0
        if max_price is None:
            m = re.search(r"(?:under|below|max(?:imum)?|up to)\s*(?:aed\s*)?(\d+(?:\.\d+)?)\s*(m|million)?", q)
            if m:
                amount = float(m.group(1))
                max_price = int(amount * 1_000_000 if m.group(2) else amount)

        query_terms = {
            "area": canon(area),
            "project": canon(project),
            "developer": canon(developer),
            "property_type": canon(property_type),
            "bedrooms": bedrooms,
        }
        # If the query explicitly references Abu Dhabi, search broadly by raw content.
        if canon(area) == "abu dhabi":
            area_candidates = [""]
        else:
            area_candidates = [area] if area else [""]

        rows: list[sqlite3.Row] = []
        for area_choice in area_candidates:
            rows.extend(
                self._candidate_rows(
                    area=area_choice,
                    project=project,
                    developer=developer,
                    bedrooms=bedrooms,
                    property_type=property_type,
                    raw_term=(
                        area
                        if canon(area) == "abu dhabi" or not any([area, project, developer, property_type, bedrooms is not None])
                        else ""
                    ),
                )
            )

        # De-duplicate identical source rows across area aliases.
        seen = set()
        unique_rows = []
        for row in rows:
            key = (row["file_name"], row["project_name"], row["area_name"], row["developer_name"], row["property_type_name"], row["bedrooms"], row["raw_json"])
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(row)
        rows = unique_rows

        scored: list[Match] = []
        for row in rows:
            score, price = score_row(row, query_terms, max_price, ready_only=ready_only)
            row_beds = parse_bedroom_count(row["bedrooms"])
            if bedrooms is not None:
                if row_beds != bedrooms:
                    continue
            if max_price is not None:
                if price is None or price > max_price:
                    continue
            if area and canon(area) != "abu dhabi":
                if canon(area) not in canon(row["area_name"]) and canon(area) not in canon(parse_raw_json(row["raw_json"]).get("area")):
                    continue
            if project and canon(project) not in canon(row["project_name"]) and canon(project) not in canon(parse_raw_json(row["raw_json"]).get("project")):
                continue
            if developer and canon(developer) not in canon(row["developer_name"]) and canon(developer) not in canon(parse_raw_json(row["raw_json"]).get("developer")):
                continue
            if property_type and canon(property_type) not in canon(row["property_type_name"]) and canon(property_type) not in canon(parse_raw_json(row["raw_json"]).get("property_type")):
                continue
            if ready_only:
                raw = canon(row["raw_json"])
                inv = canon(row["inventory_type"])
                stat = canon(row["status"])
                if not (any(k in raw for k in ("ready", "available", "handover")) or inv in {"availability", "handover", "price list"} or stat in {"ready", "available", "handover"}):
                    continue
            scored.append(
                Match(
                    project=norm(row["project_name"]) or "Unknown",
                    area=norm(row["area_name"]) or "Unknown",
                    developer=norm(row["developer_name"]) or "Unknown",
                    bedrooms=norm(row["bedrooms"]) or "",
                    property_type=norm(row["property_type_name"]) or "Unknown",
                    inventory_type=norm(row["inventory_type"]) or "Unknown",
                    status=norm(row["status"]) or "",
                    price=price,
                    source_group=norm(row["source_group"]) or "Unknown",
                    file_name=norm(row["file_name"]) or "Unknown",
                    score=score,
                )
            )

        scored.sort(key=lambda m: (-m.score, m.price if m.price is not None else 10**18, m.project, m.file_name))
        return scored[:limit]

    def highest_roi_projects(self, limit: int = 10) -> list[dict]:
        con = self._connect()
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT
                ir.raw_json,
                ir.inventory_type,
                IFNULL(p.name, '') AS project_name,
                IFNULL(a.name, '') AS area_name,
                IFNULL(d.name, '') AS developer_name,
                IFNULL(f.file_name, '') AS file_name
            FROM inventory_rows ir
            LEFT JOIN projects p ON ir.project_id = p.project_id
            LEFT JOIN areas a ON ir.area_id = a.area_id
            LEFT JOIN developers d ON ir.developer_id = d.developer_id
            LEFT JOIN inventory_files f ON ir.source_id = f.source_id
            """
        ).fetchall()
        con.close()

        bucket: dict[str, list[int]] = {}
        info: dict[str, dict] = {}
        for row in rows:
            payload = parse_raw_json(row["raw_json"])
            price = inferred_price(payload, row["inventory_type"])
            if price is None or price <= 0:
                continue
            project = norm(row["project_name"]) or "Unknown"
            bucket.setdefault(project, []).append(price)
            info.setdefault(project, {
                "project": project,
                "area": norm(row["area_name"]) or "Unknown",
                "developer": norm(row["developer_name"]) or "Unknown",
                "file_name": norm(row["file_name"]) or "Unknown",
            })

        ranked = []
        for project, prices in bucket.items():
            if len(prices) < 3:
                continue
            avg_price = sum(prices) / len(prices)
            med_price = median(prices)
            # Heuristic ROI proxy: more units and lower median price score higher.
            roi_score = (len(prices) / max(avg_price, 1)) * 1_000_000
            ranked.append({
                **info[project],
                "result_count": len(prices),
                "avg_price": round(avg_price, 2),
                "median_price": round(float(med_price), 2),
                "roi_score": round(roi_score, 4),
            })

        ranked.sort(key=lambda x: (-x["roi_score"], x["median_price"], x["project"]))
        return ranked[:limit]


def render_matches(matches: Iterable[Match]) -> str:
    out = []
    for m in matches:
        out.append(
            f"- {m.project} | {m.area} | {m.developer} | {m.bedrooms or 'N/A'} | {m.property_type} | "
            f"Price: {('AED {:,}'.format(m.price) if m.price is not None else 'N/A')} | "
            f"{m.inventory_type} | {m.status or 'n/a'} | score={m.score:.1f}"
        )
    return "\n".join(out) if out else "- No matches"


def run_demo(agent: PropertyRecommendationAgent) -> None:
    demos = [
        ("2BR Yas Island under 2M", dict(query_text="2BR Yas Island under 2M", area="Yas Island", bedrooms=2, max_price=2_000_000)),
        ("Villa Al Reeman under 4M", dict(query_text="Villa Al Reeman under 4M", area="Al Reem Island", project="Al Reeman Plot", property_type="Villa", max_price=4_000_000)),
        ("Highest ROI projects", dict(query_text="Highest ROI projects")),
        ("Ready properties in Abu Dhabi", dict(query_text="Ready properties in Abu Dhabi", area="Abu Dhabi", ready_only=True)),
    ]

    for title, kwargs in demos:
        print(f"QUERY: {title}")
        if "Highest ROI" in title:
            roi = agent.highest_roi_projects(limit=10)
            print(f"RESULT COUNT: {len(roi)}")
            print("TOP MATCHES:")
            for item in roi:
                print(
                    f"- {item['project']} | {item['area']} | {item['developer']} | "
                    f"count={item['result_count']} | avg_price={item['avg_price']:.0f} | "
                    f"median_price={item['median_price']:.0f} | roi_score={item['roi_score']}"
                )
        else:
            matches = agent.search(limit=10, **kwargs)
            print(f"RESULT COUNT: {len(matches)}")
            print("TOP MATCHES:")
            print(render_matches(matches))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-04 Property Recommendation Agent")
    parser.add_argument("--query", default="", help="Natural language query")
    parser.add_argument("--area", default="", help="Area filter")
    parser.add_argument("--project", default="", help="Project filter")
    parser.add_argument("--developer", default="", help="Developer filter")
    parser.add_argument("--bedrooms", type=int, default=None, help="Bedroom count")
    parser.add_argument("--property-type", default="", help="Property type filter")
    parser.add_argument("--max-price", type=int, default=None, help="Maximum price in AED")
    parser.add_argument("--ready-only", action="store_true", help="Prefer ready/available rows")
    parser.add_argument("--limit", type=int, default=10, help="Maximum results")
    parser.add_argument("--demo", action="store_true", help="Run the requested demo queries")
    args = parser.parse_args()

    agent = PropertyRecommendationAgent()
    if args.demo or not args.query:
        run_demo(agent)
        return

    matches = agent.search(
        area=args.area,
        project=args.project,
        developer=args.developer,
        bedrooms=args.bedrooms,
        property_type=args.property_type,
        max_price=args.max_price,
        query_text=args.query,
        ready_only=args.ready_only,
        limit=args.limit,
    )
    print(f"QUERY: {args.query}")
    print(f"RESULT COUNT: {len(matches)}")
    print("TOP MATCHES:")
    print(render_matches(matches))


if __name__ == "__main__":
    main()
