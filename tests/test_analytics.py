from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import validate

from pipeline.analytics import ensure_unique_observation_ids, fixture_observation, validate_observation

ROOT = Path(__file__).resolve().parents[1]


def test_all_product_fixtures_are_deterministic_and_schema_valid():
    schema = json.loads((ROOT / "schemas" / "analytics_observation.schema.json").read_text(encoding="utf-8"))
    products = ["flow_room", "moon_room", "cozy_room", "nature_room"]
    observations = []
    for index, product in enumerate(products, start=1):
        first = fixture_observation(product=product, sequence=index, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
        second = fixture_observation(product=product, sequence=index, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
        assert first == second
        assert first["derived_scores"] == {}
        validate(first, schema)
        observations.append(first)
    ensure_unique_observation_ids(observations)


def test_invalid_window_and_metrics_fail():
    value = fixture_observation(product="flow_room", sequence=1, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
    broken = copy.deepcopy(value)
    broken["window_end"] = broken["window_start"]
    with pytest.raises(ValueError, match="window_end"):
        validate_observation(broken)

    broken = copy.deepcopy(value)
    broken["metrics"]["views"] = -1
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_observation(broken)

    broken = copy.deepcopy(value)
    broken["metrics"]["averageViewPercentage"] = 101
    with pytest.raises(ValueError, match="cannot exceed 100"):
        validate_observation(broken)


def test_duplicate_observation_ids_fail():
    value = fixture_observation(product="moon_room", sequence=2, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
    with pytest.raises(ValueError, match="duplicate analytics observation id"):
        ensure_unique_observation_ids([value, copy.deepcopy(value)])
