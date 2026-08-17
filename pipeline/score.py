"""Weighted candidate scoring from config/scoring.yaml."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

POSITIVE_SIGNALS = {
    "search_demand",
    "recent_growth",
    "historical_performance",
    "returning_viewer_potential",
    "long_session_potential",
    "brand_fit",
}
INVERSE_SIGNALS = {"production_cost", "competition"}


def load_scoring_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    weights = config["weights"]
    if sum(weights.values()) != 100:
        raise ValueError("Scoring weights must total 100")
    unknown = set(weights) - POSITIVE_SIGNALS - INVERSE_SIGNALS
    if unknown:
        raise ValueError(f"Scoring direction undefined for: {sorted(unknown)}")
    return config


def normalized_signal(name: str, value: float) -> float:
    if not 0 <= value <= 100:
        raise ValueError(f"Signal {name} must be between 0 and 100")
    if name in INVERSE_SIGNALS:
        return 100 - value
    if name in POSITIVE_SIGNALS:
        return value
    raise ValueError(f"Scoring direction undefined for: {name}")


def score_candidate(candidate: dict, weights: dict[str, int]) -> dict:
    missing = set(weights) - set(candidate["signals"])
    if missing:
        raise ValueError(f"Missing scoring signals: {sorted(missing)}")

    breakdown = {
        name: round(normalized_signal(name, candidate["signals"][name]) * weight / 100, 4)
        for name, weight in weights.items()
    }
    scored = deepcopy(candidate)
    scored["score_breakdown"] = breakdown
    scored["score"] = round(sum(breakdown.values()), 4)
    return scored


def rank_candidates(candidates: list[dict], scoring_config: dict) -> list[dict]:
    weights = scoring_config["weights"]
    scored = [score_candidate(candidate, weights) for candidate in candidates]
    return sorted(scored, key=lambda item: (-item["score"], item["id"]))
