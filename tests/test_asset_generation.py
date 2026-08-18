from __future__ import annotations

import pytest

from pipeline.asset_generation import generate_asset_bundle


def sample_spec(tags=None):
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "Original focus rain companion audio"},
        "visual": {"brief": "Original rainy coding room"},
        "metadata": {"tags": tags or ["focus", "coding", "rain"]},
    }


def test_fixture_bundle_is_deterministic_and_traceable():
    first = generate_asset_bundle(sample_spec(), mode="fixture", production_spec_ref="spec.json")
    second = generate_asset_bundle(sample_spec(), mode="fixture", production_spec_ref="spec.json")
    assert first == second
    assert first["passed"] is True
    assert first["final_status"] == "AWAITING_APPROVAL"
    assert {asset["asset_type"] for asset in first["assets"]} == {"music", "visual", "sfx"}
    assert all(asset["topic_id"] == "TOPIC-FLOW-000024" for asset in first["assets"])
    assert all(asset["production_spec_ref"] == "spec.json" for asset in first["assets"])
    assert all(asset["qa_status"] == "passed" for asset in first["assets"])


def test_sfx_is_optional_when_topic_has_no_environmental_tag():
    bundle = generate_asset_bundle(sample_spec(["focus", "coding"]), mode="fixture", production_spec_ref="spec.json")
    assert {asset["asset_type"] for asset in bundle["assets"]} == {"music", "visual"}
    assert bundle["final_status"] == "AWAITING_APPROVAL"


def test_live_mode_fails_explicitly_instead_of_substituting_fixture():
    with pytest.raises(RuntimeError, match="Live music provider is not configured"):
        generate_asset_bundle(sample_spec(), mode="live", production_spec_ref="spec.json")
