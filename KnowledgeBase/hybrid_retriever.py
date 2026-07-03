#!/usr/bin/env python3
from __future__ import annotations

"""Hybrid retriever for AIOS.

Path 1: deterministic SQLite search over Property_Master_Database.
Path 2: semantic Chroma vector search over unstructured/doc chunks.

The retriever returns merged data, source file references, confidence, and logs
every retrieval to retrieval_audit_log.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(os.getenv("AIOS_KNOWLEDGE_BASE_DIR", str(Path(__file__).resolve().parent))).expanduser().resolve()
SQLITE_DB = ROOT / "Property_Master_Database.sqlite"
VECTOR_DIR = ROOT / "VectorDB" / "chroma"
COLLECTION_NAME = "aios_knowledge_chunks"
OPERATIONS_CORPUS = ROOT / "Operations_Corpus"
KNOWLEDGE_VAULT = ROOT / "AIOS_Knowledge_Vault"


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u200e", "").replace("\u200f", "")).strip()


def canon(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def sha_like(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:32]


def retrieval_tokens(text: str, limit: int = 10) -> list[str]:
    stop = {
        "who", "owns", "owner", "ownership", "tell", "me", "details", "detail", "of", "the",
        "unit", "units", "property", "properties", "building", "please", "pls", "find",
        "search", "show", "give", "price", "what", "where", "how", "هل", "من", "ما",
        "شو", "تفاصيل", "وحدة", "مالك", "this", "one", "any", "record", "bro",
        "check", "project", "in", "for", "need", "do", "we", "have", "about", "عندنا",
    }
    tokens = []
    for token in canon(text).split():
        if token in stop:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens[:limit]


def raw_identifier_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in re.findall(r"\b[A-Za-z]{2,}[A-Za-z0-9]*[-_/][A-Za-z0-9][A-Za-z0-9_-]*\b", text or ""):
        if match not in terms:
            terms.append(match)
    for match in re.findall(r"\b[A-Za-z]{2,}\d{2,}[A-Za-z0-9-]*\b", text or ""):
        if match not in terms:
            terms.append(match)
    return terms[:5]


def infer_retrieval_mode(query: str) -> str:
    text = canon(query)
    if re.search(r"\b(owner|owns|ownership|مالك|صاحب|who owns)\b", text):
        return "ownership_lookup"
    if re.search(r"\b(unit|villa|apartment|studio|br|bedroom|plot|tower|building|price|rent|buy|inventory)\b", text):
        return "property_lookup"
    if re.search(r"\b(noc|dld|rera|trakheesi|tarakheesi|transfer|mortgage|oqood|title deed|visa|gdrfa|icp|procedure|fees|timeline|documents required)\b", text):
        return "operations_lookup"
    if re.search(r"\b(document|contract|pdf|file|title deed|passport|eid|emirates id|modification|nakheel|case|approval)\b", text):
        return "document_lookup"
    if re.search(r"\b(project|developer|payment plan|brochure|masterplan|floor plan)\b", text):
        return "project_lookup"
    return "semantic_lookup"


def should_run_sql(query: str, mode: str) -> bool:
    if mode in {"ownership_lookup", "property_lookup", "project_lookup"}:
        return True
    if raw_identifier_terms(query):
        return True
    if mode == "semantic_lookup":
        return True
    text = canon(query)
    return bool(re.search(r"\b(unit|villa|apartment|studio|br|bedroom|plot|tower|building|price|rent|buy|inventory|owner|owns)\b", text))


@dataclass
class HybridResult:
    query: str
    merged_data: list[dict[str, Any]]
    source_file_references: list[str]
    system_confidence_score: float
    sql: dict[str, Any]
    vector: dict[str, Any]


class HybridRetriever:
    def __init__(self, sqlite_db: Path = SQLITE_DB, vector_dir: Path = VECTOR_DIR):
        self.sqlite_db = Path(sqlite_db)
        self.vector_dir = Path(vector_dir)

    def _connect_sqlite(self):
        con = sqlite3.connect(self.sqlite_db)
        con.row_factory = sqlite3.Row
        return con

    def _collection(self):
        try:
            import chromadb
        except Exception as exc:
            raise RuntimeError("chromadb is required. Install with: python3 -m pip install --user chromadb") from exc
        client = chromadb.PersistentClient(path=str(self.vector_dir))
        return client.get_or_create_collection(name=COLLECTION_NAME)

    def ensure_audit_table(self):
        con = self._connect_sqlite()
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS retrieval_audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts INTEGER NOT NULL,
                user_query TEXT NOT NULL,
                executed_sql_query TEXT DEFAULT '',
                vector_chunks_retrieved TEXT DEFAULT '[]',
                merged_confidence_level REAL DEFAULT 0,
                sql_result_count INTEGER DEFAULT 0,
                vector_result_count INTEGER DEFAULT 0
            )
            """
        )
        con.commit()
        con.close()

    def sql_lookup(self, query: str, limit: int = 8) -> dict[str, Any]:
        tokens = retrieval_tokens(query)
        identifiers = raw_identifier_terms(query)
        if not tokens and not identifiers:
            return {"query": "", "params": [], "rows": [], "confidence": 0.0}
        numeric_tokens = [t for t in tokens if t.isdigit()]
        word_tokens = [t for t in tokens if not t.isdigit()]
        clauses: list[str] = []
        params: list[str] = []
        if identifiers:
            id_clauses = []
            for term in identifiers:
                id_clauses.append("(coalesce(ir.unit_ref,'') LIKE ? OR ir.raw_json LIKE ?)")
                params.extend([f"%{term}%", f"%{term}%"])
            clauses.append("(" + " OR ".join(id_clauses) + ")")
        if numeric_tokens:
            unit_clauses = []
            for token in numeric_tokens[:3]:
                unit_clauses.append("(coalesce(ir.unit_ref,'') LIKE ? OR ir.raw_json LIKE ?)")
                params.extend([f"%{token}%", f"%{token}%"])
            clauses.append("(" + " OR ".join(unit_clauses) + ")")
        for token in word_tokens[:6]:
            clauses.append(
                "(lower(coalesce(p.name,'')) LIKE ? OR lower(coalesce(a.name,'')) LIKE ? OR "
                "lower(coalesce(d.name,'')) LIKE ? OR lower(coalesce(pt.name,'')) LIKE ? OR "
                "lower(coalesce(f.file_name,'')) LIKE ? OR lower(ir.raw_json) LIKE ?)"
            )
            params.extend([f"%{token}%"] * 6)
        if not clauses:
            return {"query": "", "params": [], "rows": [], "confidence": 0.0}
        sql = f"""
            SELECT
                ir.inventory_row_id,
                ir.raw_json,
                ir.unit_ref,
                ir.bedrooms,
                ir.price,
                ir.status,
                ir.inventory_type,
                IFNULL(p.name, '') AS project,
                IFNULL(a.name, '') AS area,
                IFNULL(d.name, '') AS developer,
                IFNULL(pt.name, '') AS property_type,
                IFNULL(f.file_name, '') AS source_file,
                IFNULL(f.source_group, '') AS source_group,
                ir.sheet_name AS sheet,
                ir.row_number
            FROM inventory_rows ir
            LEFT JOIN projects p ON ir.project_id = p.project_id
            LEFT JOIN areas a ON ir.area_id = a.area_id
            LEFT JOIN developers d ON ir.developer_id = d.developer_id
            LEFT JOIN property_types pt ON ir.property_type_id = pt.property_type_id
            LEFT JOIN inventory_files f ON ir.source_id = f.source_id
            WHERE {" AND ".join(clauses)}
            LIMIT {int(limit)}
        """
        con = self._connect_sqlite()
        rows = [dict(row) for row in con.execute(sql, params).fetchall()]
        con.close()
        confidence = min(0.95, 0.45 + len(rows) * 0.08) if rows else 0.0
        return {"query": sql, "params": params, "rows": rows, "confidence": confidence}

    def _source_score(self, row: dict[str, Any], mode: str) -> float:
        metadata = row.get("metadata") or {}
        source = canon(metadata.get("source_file") or metadata.get("source_file_name") or row.get("source_file") or "")
        source_group = canon(metadata.get("source_group") or "")
        file_type = canon(metadata.get("file_type") or "")
        similarity = float(row.get("similarity") or 0)
        bonus = 0.0
        penalty = 0.0

        if mode == "operations_lookup":
            if "operations corpus" in source or any(k in source for k in ["noc", "dld", "rera", "mortgage", "gdrfa", "icp", "tarakheesi", "trakheesi"]):
                bonus += 0.35
            if file_type in {"xlsx", "sqlite inventory"}:
                penalty += 0.25
        elif mode == "document_lookup":
            if "knowledge vault" in source or "case library" in source or any(k in source for k in ["document", "contract", "nakheel", "modification", "approval"]):
                bonus += 0.30
            if file_type == "sqlite inventory":
                penalty += 0.20
        elif mode in {"property_lookup", "ownership_lookup", "project_lookup"}:
            if file_type in {"xlsx", "sqlite inventory", "csv"}:
                bonus += 0.12
            if source_group:
                bonus += 0.03
        return max(0.0, min(1.0, similarity + bonus - penalty))

    def _filter_vector_rows(self, rows: list[dict[str, Any]], mode: str, limit: int) -> list[dict[str, Any]]:
        if not rows:
            return []
        for row in rows:
            row["mode_adjusted_score"] = self._source_score(row, mode)

        preferred: list[dict[str, Any]] = []
        fallback: list[dict[str, Any]] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            source = canon(metadata.get("source_file") or metadata.get("source_file_name") or row.get("source_file") or "")
            file_type = canon(metadata.get("file_type") or "")
            if mode == "operations_lookup":
                if "operations corpus" in source or any(k in source for k in ["noc", "dld", "rera", "mortgage", "gdrfa", "icp", "tarakheesi", "trakheesi"]):
                    preferred.append(row)
                elif file_type not in {"xlsx", "sqlite inventory"}:
                    fallback.append(row)
            elif mode == "document_lookup":
                if "knowledge vault" in source or "case library" in source or any(k in source for k in ["document", "contract", "nakheel", "modification", "approval"]):
                    preferred.append(row)
                elif file_type not in {"sqlite inventory"}:
                    fallback.append(row)
            else:
                preferred.append(row)

        selected = preferred if preferred else fallback if fallback else rows
        selected = sorted(selected, key=lambda item: item.get("mode_adjusted_score", item.get("similarity", 0)), reverse=True)
        return selected[:limit]

    def _keyword_corpus_lookup(self, query: str, mode: str, limit: int) -> list[dict[str, Any]]:
        if mode == "operations_lookup":
            roots = [OPERATIONS_CORPUS]
        elif mode == "document_lookup":
            roots = [KNOWLEDGE_VAULT, OPERATIONS_CORPUS]
        else:
            return []

        query_terms = [t for t in retrieval_tokens(query, limit=12) if len(t) > 2]
        if not query_terms:
            return []
        candidates: list[dict[str, Any]] = []
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                haystack = canon(path.name + " " + text[:8000])
                hits = sum(1 for term in query_terms if term in haystack)
                if hits == 0:
                    continue
                score = min(0.92, 0.50 + hits * 0.08)
                snippet = clean(text[:1600])
                candidates.append(
                    {
                        "chunk_id": f"keyword:{sha_like(str(path))}",
                        "text": snippet,
                        "metadata": {
                            "project": "",
                            "building": "",
                            "unit": "",
                            "owner": "",
                            "source_file": str(path.resolve()),
                            "source_file_name": path.name,
                            "sheet": "",
                            "row_number": "1",
                            "source_group": path.parent.name,
                            "page": "",
                            "file_type": path.suffix.lower().lstrip("."),
                        },
                        "similarity": score,
                        "mode_adjusted_score": score,
                        "source_file": str(path.resolve()),
                    }
                )
        return sorted(candidates, key=lambda item: item.get("mode_adjusted_score", 0), reverse=True)[:limit]

    def vector_lookup(self, query: str, limit: int = 8, mode: str | None = None) -> dict[str, Any]:
        mode = mode or infer_retrieval_mode(query)
        try:
            collection = self._collection()
            result = collection.query(
                query_texts=[query],
                n_results=max(limit * 5, 20),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            return {"rows": [], "confidence": 0.0, "error": str(exc)}
        rows: list[dict[str, Any]] = []
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        for idx, doc in enumerate(documents):
            distance = float(distances[idx]) if idx < len(distances) and distances[idx] is not None else 1.0
            similarity = max(0.0, min(1.0, 1.0 - distance))
            metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
            rows.append(
                {
                    "chunk_id": ids[idx] if idx < len(ids) else "",
                    "text": doc,
                    "metadata": metadata,
                    "similarity": similarity,
                    "source_file": metadata.get("source_file") or metadata.get("source_file_name") or "",
                }
            )
        rows.extend(self._keyword_corpus_lookup(query, mode, limit))
        rows = self._filter_vector_rows(rows, mode, limit)
        confidence = max([r.get("mode_adjusted_score", r.get("similarity", 0)) for r in rows], default=0.0)
        return {"rows": rows, "confidence": confidence, "mode": mode}

    def merge(self, query: str, sql_result: dict[str, Any], vector_result: dict[str, Any]) -> HybridResult:
        merged: list[dict[str, Any]] = []
        seen = set()
        for row in sql_result.get("rows", []):
            key = f"sql:{row.get('inventory_row_id')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append({"type": "structured_property_record", "confidence": sql_result.get("confidence", 0), **row})
        for row in vector_result.get("rows", []):
            metadata = row.get("metadata") or {}
            key = f"vector:{row.get('chunk_id') or row.get('source_file')}:{hash(row.get('text',''))}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(
                {
                    "type": "semantic_chunk",
                    "confidence": row.get("mode_adjusted_score", row.get("similarity", 0)),
                    "raw_similarity": row.get("similarity", 0),
                    "text": row.get("text", "")[:1200],
                    "metadata": metadata,
                    "source_file": row.get("source_file", ""),
                }
            )
        sources = []
        for row in merged:
            source = row.get("source_file") or (row.get("metadata") or {}).get("source_file")
            if source and source not in sources:
                sources.append(source)
        sql_conf = float(sql_result.get("confidence") or 0)
        vector_conf = float(vector_result.get("confidence") or 0)
        confidence = round(min(0.99, max(sql_conf, vector_conf, (sql_conf * 0.65 + vector_conf * 0.35))), 4)
        return HybridResult(
            query=query,
            merged_data=merged[:12],
            source_file_references=sources[:12],
            system_confidence_score=confidence,
            sql={
                "executed_query": sql_result.get("query", ""),
                "params": sql_result.get("params", []),
                "result_count": len(sql_result.get("rows", [])),
                "confidence": sql_conf,
            },
            vector={
                "result_count": len(vector_result.get("rows", [])),
                "confidence": vector_conf,
                "error": vector_result.get("error", ""),
            },
        )

    def log_audit(self, result: HybridResult):
        self.ensure_audit_table()
        chunks = []
        for row in result.merged_data:
            if row.get("type") == "semantic_chunk":
                chunks.append(
                    {
                        "source_file": row.get("source_file"),
                        "confidence": row.get("confidence"),
                        "metadata": row.get("metadata"),
                    }
                )
        con = self._connect_sqlite()
        con.execute(
            """
            INSERT INTO retrieval_audit_log
                (created_ts, user_query, executed_sql_query, vector_chunks_retrieved,
                 merged_confidence_level, sql_result_count, vector_result_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                result.query,
                result.sql.get("executed_query", ""),
                json.dumps(chunks, ensure_ascii=False),
                result.system_confidence_score,
                result.sql.get("result_count", 0),
                result.vector.get("result_count", 0),
            ),
        )
        con.commit()
        con.close()

    def retrieve(self, query: str, limit: int = 8) -> HybridResult:
        mode = infer_retrieval_mode(query)
        if should_run_sql(query, mode):
            sql_result = self.sql_lookup(query, limit=limit)
        else:
            sql_result = {"query": "", "params": [], "rows": [], "confidence": 0.0}
        vector_result = self.vector_lookup(query, limit=limit, mode=mode)
        result = self.merge(query, sql_result, vector_result)
        self.log_audit(result)
        return result


def main():
    parser = argparse.ArgumentParser(description="AIOS hybrid SQLite + vector retrieval")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    result = HybridRetriever().retrieve(args.query, limit=args.limit)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
