#!/usr/bin/env python3
"""Real-media lookup for WhatsApp replies.

The honesty rule: we only ever send media we actually have. This module maps
an inbound request onto curated media entries in
``KnowledgeBase/MediaVault/media_index.json`` — a hand-maintained file of
REAL asset URLs (Drive/CDN links to actual photos, floor plans, brochures).

Index format (list of entries):
    [{"keywords": ["verdana", "فيردانا"],
      "kind": "photos",
      "url": "https://.../verdana_gallery.jpg",
      "caption": "Verdana - actual site photos"}]

``find_media(text)`` returns the first entry whose every-keyword-set matches
the message (case-insensitive substring), or None. No index file, no matches,
any error -> None. Pure stdlib, never raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_RUNTIME_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _RUNTIME_DIR.parents[2]
MEDIA_INDEX = _REPO_ROOT / "KnowledgeBase" / "MediaVault" / "media_index.json"


def _load_index() -> list:
    try:
        data = json.loads(MEDIA_INDEX.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def find_media(text: str) -> Optional[dict]:
    """Return a matching real-media entry for this message, or None."""
    try:
        t = (text or "").lower()
        if not t:
            return None
        for entry in _load_index():
            keywords = [str(k).lower() for k in (entry.get("keywords") or []) if str(k).strip()]
            url = str(entry.get("url") or "").strip()
            if not keywords or not url.startswith("https://"):
                continue
            if any(k in t for k in keywords):
                return {
                    "url": url,
                    "kind": str(entry.get("kind") or "photos"),
                    "caption": str(entry.get("caption") or ""),
                }
        return None
    except Exception:  # pragma: no cover - defensive
        return None


def health() -> dict:
    entries = _load_index()
    return {
        "component": "media_vault",
        "index_exists": MEDIA_INDEX.is_file(),
        "entries": len(entries),
        "status": "ok" if entries else "empty_index",
    }
