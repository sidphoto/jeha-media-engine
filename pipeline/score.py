"""Weighted candidate scoring from config/scoring.yaml."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml


def load_scoring_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    weights = config["weights"]
    if sum(weights.values()) != 100:
        raise ValueError("Scoring weights must total 100")
    return config


def score_candidate(candidate: dict, weights: dict[str, int]) -> dict:
    missing = set(weights) - set(candidate["signals"])
    if missing:
        raise ValueError(f"Missing scoring signals: {sorted(missing)}")

    breakdown = {
        name: round(candidate["signals"][name] * weight / 100, 4)
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
