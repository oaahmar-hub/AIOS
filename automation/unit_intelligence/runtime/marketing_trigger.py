#!/usr/bin/env python3
"""Marketing automation trigger for unit intelligence.

When a unit is resolved with sufficient confidence, this module stages the
creative production workflow (video, poster, flyer, social content) and writes
the planned actions to a staging table. It does not render media, publish ads,
or spend money without explicit approval.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "marketing_staging.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS marketing_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_job_id INTEGER,
    unit_id TEXT,
    confidence TEXT,
    trigger_reason TEXT,
    status TEXT DEFAULT 'staged', -- staged, approved, rejected, in_progress, completed, failed
    assets TEXT, -- JSON list of planned assets
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marketing_assets (
    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    asset_type TEXT NOT NULL, -- video, poster, flyer, social_post, brochure, email
    channel TEXT, -- instagram, facebook, linkedin, whatsapp, email, portal
    format TEXT, -- mp4, jpg, pdf, html
    content_brief TEXT,
    status TEXT DEFAULT 'staged',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES marketing_jobs(job_id)
);
"""


ASSET_TEMPLATES = {
    "video": {
        "asset_type": "video",
        "format": "mp4",
        "channels": ["instagram", "facebook", "whatsapp"],
        "duration_seconds": 30,
        "content_brief": "Cinematic walkthrough / feature highlights with unit facts, location, and price.",
    },
    "poster": {
        "asset_type": "poster",
        "format": "jpg",
        "channels": ["instagram", "facebook", "linkedin", "whatsapp"],
        "content_brief": "High-resolution listing poster with hero image, key facts, price, and contact QR.",
    },
    "flyer": {
        "asset_type": "flyer",
        "format": "pdf",
        "channels": ["email", "whatsapp"],
        "content_brief": "Print-ready PDF flyer with unit details, floor plan placeholder, and broker branding.",
    },
    "social_post": {
        "asset_type": "social_post",
        "format": "jpg",
        "channels": ["instagram", "facebook", "linkedin"],
        "content_brief": "Carousel / single-image post with hook, 3-5 bullets, and CTA.",
    },
    "brochure": {
        "asset_type": "brochure",
        "format": "pdf",
        "channels": ["email", "portal"],
        "content_brief": "Multi-page project brochure with project overview, amenities, unit mix, and payment plan placeholder.",
    },
}


@dataclass
class MarketingPlan:
    source_job_id: int | None
    unit_id: str
    confidence: str
    trigger_reason: str
    assets: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_job_id": self.source_job_id,
            "unit_id": self.unit_id,
            "confidence": self.confidence,
            "trigger_reason": self.trigger_reason,
            "assets": self.assets,
        }


class MarketingStaging:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def stage_plan(self, plan: MarketingPlan) -> int:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO marketing_jobs (source_job_id, unit_id, confidence, trigger_reason, assets, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.source_job_id,
                    plan.unit_id,
                    plan.confidence,
                    plan.trigger_reason,
                    json.dumps(plan.assets, ensure_ascii=False),
                    "staged",
                    now,
                    now,
                ),
            )
            job_id = cursor.lastrowid
            for asset in plan.assets:
                conn.execute(
                    """
                    INSERT INTO marketing_assets (job_id, asset_type, channel, format, content_brief, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        asset.get("asset_type"),
                        ", ".join(asset.get("channels", [])),
                        asset.get("format"),
                        asset.get("content_brief"),
                        "staged",
                        now,
                        now,
                    ),
                )
            conn.commit()
        return job_id

    def get_staged_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM marketing_jobs WHERE status = 'staged' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]


def build_plan(source_job_id: int | None, unit_id: str, confidence: str, *, unit_facts: dict[str, Any] | None = None) -> MarketingPlan:
    """Build a staged marketing plan for a resolved unit."""
    if confidence not in {"exact", "likely"}:
        return MarketingPlan(
            source_job_id=source_job_id,
            unit_id=unit_id,
            confidence=confidence,
            trigger_reason="confidence_too_low",
            assets=[],
        )

    facts = unit_facts or {}
    trigger_reason = "unit_resolved_exact" if confidence == "exact" else "unit_resolved_likely"
    assets = []
    for key, template in ASSET_TEMPLATES.items():
        asset = dict(template)
        asset["unit_facts_snapshot"] = facts
        asset["approval_required"] = True
        assets.append(asset)

    return MarketingPlan(
        source_job_id=source_job_id,
        unit_id=unit_id,
        confidence=confidence,
        trigger_reason=trigger_reason,
        assets=assets,
    )


def trigger_from_resolution(
    job_id: int,
    unit_id: str,
    confidence: str,
    unit_facts: dict[str, Any] | None = None,
    staging: MarketingStaging | None = None,
) -> dict[str, Any]:
    """Stage marketing assets after a unit resolution."""
    plan = build_plan(job_id, unit_id, confidence, unit_facts=unit_facts)
    if not plan.assets:
        return {
            "ok": True,
            "staged": False,
            "reason": "confidence_too_low",
            "unit_id": unit_id,
            "confidence": confidence,
        }
    staging = staging or MarketingStaging()
    marketing_job_id = staging.stage_plan(plan)
    return {
        "ok": True,
        "staged": True,
        "marketing_job_id": marketing_job_id,
        "unit_id": unit_id,
        "confidence": confidence,
        "assets_count": len(plan.assets),
    }


if __name__ == "__main__":
    result = trigger_from_resolution(
        job_id=1,
        unit_id="7f9f69f79ea5c7e8",
        confidence="exact",
        unit_facts={"area": "Jumeirah Village Circle", "property_type": "townhouse", "bedrooms": 2},
    )
    print(json.dumps(result, indent=2))
