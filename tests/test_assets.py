from __future__ import annotations

import pytest

from pipeline.assets import AssetRegistry, build_fixture_asset, make_asset_id


def test_asset_ids_are_stable_and_typed():
    assert make_asset_id("music", "flow", 23) == "MUSIC-FLOW-000023"
    assert make_asset_id("visual", "moon", 18) == "VISUAL-MOON-000018"
    assert make_asset_id("sfx", "rain", 12) == "SFX-RAIN-000012"


def test_registry_preserves_topic_lineage_and_rejects_collisions():
    registry = AssetRegistry()
    record = build_fixture_asset(
        asset_type="music", namespace="flow", sequence=1,
        topic_id="TOPIC-FLOW-000024", prompt_or_source="focus rain brief",
        technical={"duration_seconds": 180, "format": "wav"},
        production_spec_ref="data/runs/example/production_spec.json",
    )
    registry.register(record)
    assert registry.by_topic("TOPIC-FLOW-000024")[0]["asset_id"] == "MUSIC-FLOW-000001"
    with pytest.raises(ValueError, match="Duplicate asset_id"):
        registry.register(record)


def test_registry_rejects_assets_without_commercial_rights():
    registry = AssetRegistry()
    record = build_fixture_asset(
        asset_type="visual", namespace="flow", sequence=1,
        topic_id="TOPIC-FLOW-000024", prompt_or_source="rainy coding room",
        technical={"width": 1920, "height": 1080, "format": "png"},
    )
    record["rights"]["commercial_use"] = False
    with pytest.raises(ValueError, match="not cleared for commercial use"):
        registry.register(record)


def test_fixture_asset_is_deterministic():
    kwargs = dict(
        asset_type="sfx", namespace="rain", sequence=1,
        topic_id="TOPIC-FLOW-000024", prompt_or_source="rain library fixture",
        technical={"duration_seconds": 60, "format": "wav", "sample_rate": 48000},
    )
    assert build_fixture_asset(**kwargs) == build_fixture_asset(**kwargs)
