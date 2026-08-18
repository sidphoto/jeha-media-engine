from __future__ import annotations

import json

import pytest

from pipeline.asset_generation import generate_asset_bundle
from pipeline.assets import build_fixture_asset


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


def spec():
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "focus ambience"},
        "visual": {"brief": "rainy focus room"},
        "metadata": {"tags": ["focus", "rain"]},
    }


def live_core_providers():
    return {
        "music": LiveTestProvider(
            "music",
            {"duration_seconds": 600, "format": "wav", "sample_rate": 48000, "channels": 2},
        ),
        "visual": LiveTestProvider(
            "visual",
            {"width": 1920, "height": 1080, "aspect_ratio": "16:9", "format": "png"},
        ),
    }


def test_live_sfx_requires_manifest_when_requested(monkeypatch):
    monkeypatch.delenv("JEHA_SFX_MANIFEST", raising=False)
    with pytest.raises(RuntimeError, match="JEHA_SFX_MANIFEST"):
        generate_asset_bundle(
            spec(),
            mode="live",
            production_spec_ref="spec.json",
            providers=live_core_providers(),
        )


def test_live_sfx_uses_license_reviewed_manifest(tmp_path, monkeypatch):
    audio = tmp_path / "rain.wav"
    audio.write_bytes(b"licensed-live-rain")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "assets": [{
            "id": "rain-live-001",
            "sfx_type": "rain",
            "path": "rain.wav",
            "source_url": "https://example.invalid/free-rain",
            "license": "FREE_COMMERCIAL_TEST_LICENSE",
            "commercial_use": True,
            "duration_seconds": 600,
            "format": "wav",
            "sample_rate": 48000,
            "channels": 2,
            "priority": 1,
        }]
    }), encoding="utf-8")
    monkeypatch.setenv("JEHA_SFX_MANIFEST", str(manifest))

    bundle = generate_asset_bundle(
        spec(),
        mode="live",
        production_spec_ref="spec.json",
        providers=live_core_providers(),
    )

    assert bundle["passed"] is True
    assert bundle["final_status"] == "AWAITING_APPROVAL"
    sfx = next(asset for asset in bundle["assets"] if asset["asset_type"] == "sfx")
    assert sfx["provider"] == "jeha_local_sfx_library"
    assert sfx["rights"]["commercial_use"] is True
    assert sfx["technical"]["library_entry_id"] == "rain-live-001"
