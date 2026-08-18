from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import validate

from pipeline.analytics import METRIC_FIELDS, ensure_unique_observation_ids, fixture_observation, validate_observation

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


def test_sequence_rejects_bool_even_though_bool_is_an_int_subclass():
    # isinstance(True, int) is True in Python, so a naive `isinstance(sequence, int)`
    # check would silently accept sequence=True as sequence=1.
    with pytest.raises(ValueError, match="positive integer"):
        fixture_observation(product="flow_room", sequence=True, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")


def test_sequence_overflowing_six_digit_suffix_is_rejected():
    with pytest.raises(ValueError, match="six-digit"):
        fixture_observation(product="flow_room", sequence=1_000_000, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("metric_name", METRIC_FIELDS)
def test_non_finite_metrics_are_rejected(bad_value, metric_name):
    value = fixture_observation(product="flow_room", sequence=1, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
    broken = copy.deepcopy(value)
    broken["metrics"][metric_name] = bad_value
    with pytest.raises(ValueError, match="finite"):
        validate_observation(broken)


def test_bool_metric_value_is_rejected():
    value = fixture_observation(product="flow_room", sequence=1, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
    broken = copy.deepcopy(value)
    broken["metrics"]["likes"] = True
    with pytest.raises(ValueError, match="must be numeric"):
        validate_observation(broken)


def test_mismatched_video_topic_or_product_lineage_is_rejected():
    value = fixture_observation(product="flow_room", sequence=1, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")

    wrong_video = copy.deepcopy(value)
    wrong_video["video_id"] = "VIDEO-NATURE-000001"
    with pytest.raises(ValueError, match="lineage mismatch"):
        validate_observation(wrong_video)

    wrong_topic = copy.deepcopy(value)
    wrong_topic["topic_id"] = "TOPIC-MOON-000001"
    with pytest.raises(ValueError, match="lineage mismatch"):
        validate_observation(wrong_topic)

    wrong_sequence = copy.deepcopy(value)
    wrong_sequence["video_id"] = "VIDEO-FLOW-000002"
    with pytest.raises(ValueError, match="run sequence"):
        validate_observation(wrong_sequence)


def test_derived_scores_cannot_duplicate_raw_metric_fields():
    value = fixture_observation(product="flow_room", sequence=1, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
    broken = copy.deepcopy(value)
    broken["derived_scores"] = {"views": 1200}
    with pytest.raises(ValueError, match="must not duplicate raw metric fields"):
        validate_observation(broken)


def test_derived_scores_must_be_finite_numeric():
    value = fixture_observation(product="flow_room", sequence=1, window_start="2026-08-01T00:00:00+08:00", window_end="2026-08-08T00:00:00+08:00")
    broken = copy.deepcopy(value)
    broken["derived_scores"] = {"engagement_index": float("nan")}
    with pytest.raises(ValueError, match="finite"):
        validate_observation(broken)
