#!/usr/bin/env python3
"""Prepare minimal AIOS runtime files for Docker deploy context."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOWNLOADS_AIOS = Path("/Users/hassanka/Downloads/AIOS")
TARGET = ROOT / "AIOS"

FILES = [
    ("KnowledgeBase/aios_entrypoint.py", "KnowledgeBase/aios_entrypoint.py"),
    ("KnowledgeBase/aios_brain_router.py", "KnowledgeBase/aios_brain_router.py"),
    ("KnowledgeBase/property_recommendation_agent.py", "KnowledgeBase/property_recommendation_agent.py"),
    ("KnowledgeBase/Property_Master_Database.sqlite", "KnowledgeBase/Property_Master_Database.sqlite"),
    ("KnowledgeBase/aios_control_center.py", "KnowledgeBase/aios_control_center.py"),
    ("KnowledgeBase/aios_follow_up_engine_v1.py", "KnowledgeBase/aios_follow_up_engine_v1.py"),
    (
        "automation/central_orchestrator/runtime/aios_interaction_architecture_runtime.py",
        "automation/central_orchestrator/runtime/aios_interaction_architecture_runtime.py",
    ),
    ("PersonalityEngine/OMAR_REPLY_POLICY.md", "PersonalityEngine/OMAR_REPLY_POLICY.md"),
    ("PersonalityEngine/OMAR_PERSONALITY_PROFILE_V1.json", "PersonalityEngine/OMAR_PERSONALITY_PROFILE_V1.json"),
    ("PersonalityEngine/omar_personality_engine.py", "PersonalityEngine/omar_personality_engine.py"),
]

DIRS = [
    ("KnowledgeBase/Operations_Corpus/text", "KnowledgeBase/Operations_Corpus/text"),
    ("KnowledgeBase/AIOS_Knowledge_Vault", "KnowledgeBase/AIOS_Knowledge_Vault"),
]


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)

    for source_rel, target_rel in FILES:
        source = DOWNLOADS_AIOS / source_rel
        target = TARGET / target_rel
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    for source_rel, target_rel in DIRS:
        source = DOWNLOADS_AIOS / source_rel
        target = TARGET / target_rel
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)

    print(f"Prepared deploy context: {TARGET}")


if __name__ == "__main__":
    main()
