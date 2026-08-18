from __future__ import annotations

import pytest

from pipeline.asset_generation import generate_asset_bundle
from pipeline.assets import build_fixture_asset


def sample_spec(tags=None, topic_id="TOPIC-FLOW-000024"):
    return {
        "topic_id": topic_id,
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "Original focus rain companion audio"},
        "visual": {"brief": "Original rainy coding room"},
        "metadata": {"tags": tags or ["focus", "coding", "rain"]},
    }


class LiveTestProvider:
    def __init__(self, asset_type: str, technical: dict):
        self.asset_type = asset_type
        self.technical = technical

    def generate(self, request):
        record = build_fixture_asset(
            asset_type=self.asset_type,
            namespace="live_test",
            sequence=24,
            topic_id=request.topic_id,
            production_spec_ref=request.production_spec_ref,
            prompt_or_source="live contract test",
            technical=self.technical,
        )
        record["provider"] = "live_test_provider"
        record["model"] = "live-test-v1"
        record["provider_version"] = "1"
        record["rights"] = {
            "commercial_use": True,
            "license": "TEST_COMMERCIAL_LICENSE",
            "source_url": "https://example.invalid/source",
        }
        return record


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
    assert {asset["asset_id"] for asset in first["assets"]} == {
        "MUSIC-FLOW-000024",
        "VISUAL-FLOW-000024",
        "SFX-RAIN-000024",
    }


def test_fixture_ids_do_not_collide_across_topics():
    first = generate_asset_bundle(sample_spec(topic_id="TOPIC-FLOW-000024"), mode="fixture", production_spec_ref="spec-a.json")
    second = generate_asset_bundle(sample_spec(topic_id="TOPIC-FLOW-000025"), mode="fixture", production_spec_ref="spec-b.json")
    assert {asset["asset_id"] for asset in first["assets"]}.isdisjoint(
        {asset["asset_id"] for asset in second["assets"]}
    )


def test_noncanonical_topic_ids_still_produce_stable_distinct_asset_ids():
    first = generate_asset_bundle(sample_spec(topic_id="topic-alpha"), mode="fixture", production_spec_ref="spec-a.json")
    again = generate_asset_bundle(sample_spec(topic_id="topic-alpha"), mode="fixture", production_spec_ref="spec-a.json")
    second = generate_asset_bundle(sample_spec(topic_id="topic-beta"), mode="fixture", production_spec_ref="spec-b.json")
    assert {asset["asset_id"] for asset in first["assets"]} == {asset["asset_id"] for asset in again["assets"]}
    assert {asset["asset_id"] for asset in first["assets"]}.isdisjoint(
        {asset["asset_id"] for asset in second["assets"]}
    )


def test_sfx_is_optional_when_topic_has_no_environmental_tag():
    bundle = generate_asset_bundle(sample_spec(["focus", "coding"]), mode="fixture", production_spec_ref="spec.json")
    assert {asset["asset_type"] for asset in bundle["assets"]} == {"music", "visual"}
    assert bundle["final_status"] == "AWAITING_APPROVAL"


def test_live_mode_uses_elevenlabs_and_fails_explicitly_without_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_COMMERCIAL_USE_ACK", raising=False)
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        generate_asset_bundle(sample_spec(), mode="live", production_spec_ref="spec.json")


def test_live_provider_contract_can_be_injected_without_orchestration_changes():
    bundle = generate_asset_bundle(
        sample_spec(["focus", "coding"]),
        mode="live",
        production_spec_ref="spec.json",
        providers={
            "music": LiveTestProvider(
                "music",
                {"duration_seconds": 10800, "format": "wav", "sample_rate": 48000, "channels": 2},
            ),
            "visual": LiveTestProvider(
                "visual",
                {"width": 1920, "height": 1080, "aspect_ratio": "16:9", "format": "png"},
            ),
        },
    )
    assert bundle["passed"] is True
    assert bundle["final_status"] == "AWAITING_APPROVAL"
    assert all(asset["provider"] == "live_test_provider" for asset in bundle["assets"])


def test_invalid_technical_metadata_fails_asset_qa():
    bundle = generate_asset_bundle(
        sample_spec(["focus", "coding"]),
        mode="live",
        production_spec_ref="spec.json",
        providers={
            "music": LiveTestProvider(
                "music",
                {"duration_seconds": 10800, "format": "wav", "sample_rate": 0, "channels": 2},
            ),
            "visual": LiveTestProvider(
                "visual",
                {"width": 1920, "height": 1080, "aspect_ratio": "16:9", "format": "png"},
            ),
        },
    )
    assert bundle["passed"] is False
    assert bundle["final_status"] == "FAILED"
    music_qa = next(item for item in bundle["qa"] if item["asset_id"].startswith("MUSIC-"))
    assert music_qa["checks"]["technical_metadata"] is False
