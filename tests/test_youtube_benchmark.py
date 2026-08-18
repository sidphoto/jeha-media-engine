from __future__ import annotations

import pytest

from pipeline.youtube_benchmark import (
    advisory_for_product,
    build_pattern_intelligence,
    collect_fixture,
    collect_live,
)


def test_fixture_covers_all_products_deterministically():
    first = collect_fixture()
    second = collect_fixture()
    assert first == second
    assert len(first) == 12
    assert {row["product"] for row in first} == {
        "flow_room", "moon_room", "cozy_room", "nature_room"
    }
    assert all(row["views_per_day"] > 0 for row in first)
    assert all(row["duration_bucket"] != "unknown" for row in first)


def test_pattern_intelligence_is_product_specific():
    patterns = build_pattern_intelligence(collect_fixture())
    assert patterns["flow_room"]["sample_count"] == 3
    assert patterns["moon_room"]["preferred_duration_bucket"] == "8h_plus"
    assert "sleep" in patterns["moon_room"]["title_terms"]
    assert "cozy" in patterns["cozy_room"]["title_terms"]
    assert "forest" in patterns["nature_room"]["title_terms"]


def test_advisory_is_evidence_not_copy_instruction():
    patterns = build_pattern_intelligence(collect_fixture())
    advisory = advisory_for_product(patterns, "flow_room")
    assert advisory["advisory_only"] is True
    assert advisory["source"] == "youtube_benchmark"
    assert "do not copy" in advisory["guardrail"].lower()


def test_live_requires_youtube_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="YOUTUBE_API_KEY"):
        collect_live()
