from __future__ import annotations

import pytest

from pipeline.asset_generation import generate_asset_bundle
from pipeline.assets import build_fixture_asset
from pipeline.visual_qa import STYLE_PRESET


def sample_spec(tags=None, topic_id="TOPIC-FLOW-000024"):
    return {
        "topic_id": topic_id,
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "Original focus rain companion audio"},
        "visual": {"brief": "Original rainy coding room"},
        "metadata": {"tags": tags or ["focus", "coding", "rain"]},
    }


def visual_technical(**overrides):
    value = {
        "width": 1920,
        "height": 1080,
        "aspect_ratio": "16:9",
        "format": "png",
        "style_preset": STYLE_PRESET,
        "reference_lineage": [],
    }
    value.update(overrides)
    return value


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
    assert first["visual_handoffs"] == []
    assert first["pending_dependencies"] == []
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


def test_live_mode_preflight_requires_music_but_not_gemini_or_sfx(monkeypatch):
    for name in (
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_COMMERCIAL_USE_ACK",
        "GEMINI_API_KEY",
        "GEMINI_COMMERCIAL_USE_ACK",
        "JEHA_SFX_MANIFEST",
        "JEHA_VISUAL_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError) as exc:
        generate_asset_bundle(sample_spec(), mode="live", production_spec_ref="spec.json")
    message = str(exc.value)
    assert "ELEVENLABS_API_KEY" in message
    assert "GEMINI_API_KEY" not in message
    assert "JEHA_SFX_MANIFEST" not in message


def test_live_default_routes_visual_to_three_chatgpt_handoffs_and_keeps_sfx_pending(monkeypatch):
    monkeypatch.delenv("JEHA_VISUAL_PROVIDER", raising=False)
    monkeypatch.delenv("JEHA_SFX_MANIFEST", raising=False)
    bundle = generate_asset_bundle(
        sample_spec(),
        mode="live",
        production_spec_ref="spec.json",
        providers={
            "music": LiveTestProvider(
                "music",
                {"duration_seconds": 10800, "format": "wav", "sample_rate": 48000, "channels": 2},
            ),
        },
    )
    assert {asset["asset_type"] for asset in bundle["assets"]} == {"music"}
    assert len(bundle["visual_handoffs"]) == 3
    assert [item["candidate_role"] for item in bundle["visual_handoffs"]] == ["primary", "alt_a", "alt_b"]
    assert all(item["provider"] == "chatgpt_image" for item in bundle["visual_handoffs"])
    assert all(item["remote_execution_allowed"] is False for item in bundle["visual_handoffs"])
    assert bundle["pending_dependencies"] == ["visual", "sfx"]
    assert bundle["passed"] is False
    assert bundle["final_status"] == "AWAITING_CHATGPT_VISUAL_GENERATION"


def test_gemini_is_explicit_opt_in_fallback(monkeypatch):
    monkeypatch.setenv("JEHA_VISUAL_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_COMMERCIAL_USE_ACK", raising=False)
    with pytest.raises(RuntimeError) as exc:
        generate_asset_bundle(
            sample_spec(["focus", "coding"]),
            mode="live",
            production_spec_ref="spec.json",
            providers={
                "music": LiveTestProvider(
                    "music",
                    {"duration_seconds": 10800, "format": "wav", "sample_rate": 48000, "channels": 2},
                ),
            },
        )
    message = str(exc.value)
    assert "JEHA_VISUAL_PROVIDER=gemini" in message
    assert "GEMINI_API_KEY" in message


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
            "visual": LiveTestProvider("visual", visual_technical()),
        },
    )
    assert bundle["passed"] is True
    assert bundle["final_status"] == "AWAITING_APPROVAL"
    assert bundle["visual_handoffs"] == []
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
            "visual": LiveTestProvider("visual", visual_technical()),
        },
    )
    assert bundle["passed"] is False
    assert bundle["final_status"] == "FAILED"
    music_qa = next(item for item in bundle["qa"] if item["asset_id"].startswith("MUSIC-"))
    assert music_qa["checks"]["technical_metadata"] is False


def test_visual_without_house_style_lineage_fails_asset_qa():
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
    assert bundle["passed"] is False
    visual_qa = next(item for item in bundle["qa"] if item["asset_id"].startswith("VISUAL-"))
    assert visual_qa["checks"]["visual_house_style_lineage"] is False
    assert "wrong_or_missing_style_preset" in visual_qa["visual_lineage_issues"]
