from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "launch_support_questions.json"


@dataclass(frozen=True)
class LaunchScenario:
    id: str
    question: str
    source_text: str | None
    expected_state: str
    expected_citation: bool


@dataclass(frozen=True)
class LaunchDataset:
    name: str
    description: str
    scenarios: list[LaunchScenario]


@lru_cache(maxsize=1)
def load_launch_dataset() -> LaunchDataset:
    """Load the curated launch evaluation dataset from disk.

    Cached so repeated evaluation runs do not re-read the file. The dataset gives the
    launch gate concrete, representative scenarios (answered, refused, clarification)
    instead of static placeholder scores.
    """
    raw = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    scenarios = [
        LaunchScenario(
            id=item["id"],
            question=item["question"],
            source_text=item.get("source_text"),
            expected_state=item["expected_state"],
            expected_citation=bool(item.get("expected_citation", False)),
        )
        for item in raw["scenarios"]
    ]
    return LaunchDataset(name=raw["name"], description=raw["description"], scenarios=scenarios)
