"""M6.1 analytics evidence contract and deterministic fixtures."""
from __future__ import annotations

import copy
import math
import re
from datetime import datetime

PRODUCTS = ("flow_room", "moon_room", "cozy_room", "nature_room")
PRODUCT_CODES = {product: product.split("_")[0].upper() for product in PRODUCTS}

_OBSERVATION_ID_RE = re.compile(r"^ANALYTICS-([A-Z]+)-([0-9]{6})$")
_VIDEO_ID_RE = re.compile(r"^VIDEO-([A-Z]+)-([0-9]{6})$")
_TOPIC_ID_RE = re.compile(r"^TOPIC-([A-Z]+)-([0-9]{6})$")

METRIC_FIELDS = ("views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "subscribersGained", "subscribersLost")

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
    for field in ("observation_id", "video_id", "topic_id", "product", "window_start", "window_end", "source", "metrics", "derived_scores"):
        if field not in observation:
            raise ValueError(f"analytics observation missing {field}")
    product = observation["product"]
    if product not in PRODUCTS:
        raise ValueError("analytics observation has invalid product")

    observation_match = _OBSERVATION_ID_RE.match(str(observation["observation_id"]))
    if not observation_match:
        raise ValueError("analytics observation requires a canonical ANALYTICS ID")
    video_match = _VIDEO_ID_RE.match(str(observation["video_id"]))
    if not video_match:
        raise ValueError("analytics observation requires canonical VIDEO ID")
    topic_match = _TOPIC_ID_RE.match(str(observation["topic_id"]))
    if not topic_match:
        raise ValueError("analytics observation requires canonical TOPIC ID")

    expected_code = PRODUCT_CODES[product]
    codes = {observation_match.group(1), video_match.group(1), topic_match.group(1)}
    if codes != {expected_code}:
        raise ValueError("analytics observation_id/video_id/topic_id/product lineage mismatch")
    suffixes = {observation_match.group(2), video_match.group(2), topic_match.group(2)}
    if len(suffixes) != 1:
        raise ValueError("analytics observation_id/video_id/topic_id must share the same run sequence")

    source = observation["source"]
    if not isinstance(source, dict):
        raise ValueError("analytics source must be an object")
    if set(source) != {"provider", "dataset"}:
        raise ValueError("analytics source must contain exactly provider and dataset")
    if source.get("provider") not in {"jeha_fixture", "youtube_analytics"}:
        raise ValueError("analytics source has invalid provider")
    if not isinstance(source.get("dataset"), str) or not source["dataset"].strip():
        raise ValueError("analytics source dataset is required")

    start = _parse_iso(observation["window_start"])
    end = _parse_iso(observation["window_end"])
    if end <= start:
        raise ValueError("analytics observation window_end must be after window_start")

    metrics = observation["metrics"]
    if not isinstance(metrics, dict):
        raise ValueError("analytics metrics must be an object")
    for name in METRIC_FIELDS:
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"analytics metric {name} must be numeric")
        if not math.isfinite(value):
            raise ValueError(f"analytics metric {name} must be finite")
        if value < 0:
            raise ValueError(f"analytics metric {name} cannot be negative")
    if metrics["averageViewPercentage"] > 100:
        raise ValueError("averageViewPercentage cannot exceed 100")

    derived_scores = observation["derived_scores"]
    if not isinstance(derived_scores, dict):
        raise ValueError("analytics derived_scores must be an object")
    overlap = set(derived_scores).intersection(METRIC_FIELDS)
    if overlap:
        raise ValueError(f"analytics derived_scores must not duplicate raw metric fields: {sorted(overlap)}")
    for name, value in derived_scores.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"analytics derived score {name} must be numeric")
        if not math.isfinite(value):
            raise ValueError(f"analytics derived score {name} must be finite")

    return observation


def fixture_observation(*, product: str, sequence: int, window_start: str, window_end: str) -> dict:
    if product not in PRODUCTS:
        raise ValueError("unsupported JEHA product")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValueError("sequence must be a positive integer")
    if sequence > 999999:
        raise ValueError("sequence must fit in the six-digit canonical ID suffix")
    code = PRODUCT_CODES[product]
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
