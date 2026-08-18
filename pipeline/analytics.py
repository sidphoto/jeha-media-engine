"""M6.1 analytics evidence contract and deterministic fixtures."""
from __future__ import annotations

import copy
from datetime import datetime

PRODUCTS = ("flow_room", "moon_room", "cozy_room", "nature_room")

_FIXTURES = {
    "flow_room": {"views": 1200, "estimatedMinutesWatched": 54000, "averageViewDuration": 2700, "averageViewPercentage": 25.0, "likes": 96, "subscribersGained": 18, "subscribersLost": 2},
    "moon_room": {"views": 900, "estimatedMinutesWatched": 64800, "averageViewDuration": 4320, "averageViewPercentage": 40.0, "likes": 81, "subscribersGained": 14, "subscribersLost": 1},
    "cozy_room": {"views": 1050, "estimatedMinutesWatched": 47250, "averageViewDuration": 2700, "averageViewPercentage": 25.0, "likes": 105, "subscribersGained": 20, "subscribersLost": 3},
    "nature_room": {"views": 800, "estimatedMinutesWatched": 57600, "averageViewDuration": 4320, "averageViewPercentage": 40.0, "likes": 88, "subscribersGained": 16, "subscribersLost": 1},
}


def _parse_iso(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("analytics observation timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("analytics observation timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("analytics observation timestamp must be timezone-aware")
    return parsed


def validate_observation(observation: dict) -> dict:
    for field in ("observation_id", "video_id", "topic_id", "product", "window_start", "window_end", "source", "metrics"):
        if field not in observation:
            raise ValueError(f"analytics observation missing {field}")
    if observation["product"] not in PRODUCTS:
        raise ValueError("analytics observation has invalid product")
    if not str(observation["video_id"]).startswith("VIDEO-"):
        raise ValueError("analytics observation requires canonical VIDEO ID")
    if not str(observation["topic_id"]).startswith("TOPIC-"):
        raise ValueError("analytics observation requires canonical TOPIC ID")
    start = _parse_iso(observation["window_start"])
    end = _parse_iso(observation["window_end"])
    if end <= start:
        raise ValueError("analytics observation window_end must be after window_start")
    metrics = observation["metrics"]
    required = ("views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "subscribersGained", "subscribersLost")
    for name in required:
        value = metrics.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"analytics metric {name} must be numeric")
        if value < 0:
            raise ValueError(f"analytics metric {name} cannot be negative")
    if metrics["averageViewPercentage"] > 100:
        raise ValueError("averageViewPercentage cannot exceed 100")
    return observation


def fixture_observation(*, product: str, sequence: int, window_start: str, window_end: str) -> dict:
    if product not in PRODUCTS:
        raise ValueError("unsupported JEHA product")
    if not isinstance(sequence, int) or sequence <= 0:
        raise ValueError("sequence must be a positive integer")
    code = product.split("_")[0].upper()
    suffix = f"{sequence:06d}"
    observation = {
        "observation_id": f"ANALYTICS-{code}-{suffix}",
        "video_id": f"VIDEO-{code}-{suffix}",
        "topic_id": f"TOPIC-{code}-{suffix}",
        "product": product,
        "window_start": window_start,
        "window_end": window_end,
        "source": {"provider": "jeha_fixture", "dataset": "m6_analytics_v1"},
        "metrics": copy.deepcopy(_FIXTURES[product]),
        "derived_scores": {},
        "final_status": "ANALYTICS_OBSERVATION_READY",
    }
    return validate_observation(observation)


def ensure_unique_observation_ids(observations: list[dict]) -> None:
    ids = [item.get("observation_id") for item in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate analytics observation id")
