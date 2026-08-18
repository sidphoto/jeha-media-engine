"""M3 provider contracts and deterministic fixture adapters.

Live providers are configuration-gated so orchestration remains stable while production
providers, commercial-use policies, and credentials are selected independently.
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.assets import build_fixture_asset


@dataclass(frozen=True)
class AssetRequest:
    topic_id: str
    product: str
    production_spec_ref: str
    music_brief: str
    visual_brief: str
    duration_minutes: int
    sfx_type: str | None = None


class FixtureMusicProvider:
    def generate(self, request: AssetRequest) -> dict:
        return build_fixture_asset(
            asset_type="music",
            namespace=request.product.replace("_room", ""),
            sequence=1,
            topic_id=request.topic_id,
            production_spec_ref=request.production_spec_ref,
            prompt_or_source=request.music_brief,
            technical={"duration_seconds": request.duration_minutes * 60, "format": "wav", "sample_rate": 48000, "channels": 2},
        )


class FixtureVisualProvider:
    def generate(self, request: AssetRequest) -> dict:
        return build_fixture_asset(
            asset_type="visual",
            namespace=request.product.replace("_room", ""),
            sequence=1,
            topic_id=request.topic_id,
            production_spec_ref=request.production_spec_ref,
            prompt_or_source=request.visual_brief,
            technical={"width": 1920, "height": 1080, "aspect_ratio": "16:9", "format": "png"},
        )


class FixtureSFXProvider:
    def generate(self, request: AssetRequest) -> dict | None:
        if not request.sfx_type:
            return None
        return build_fixture_asset(
            asset_type="sfx",
            namespace=request.sfx_type,
            sequence=1,
            topic_id=request.topic_id,
            production_spec_ref=request.production_spec_ref,
            prompt_or_source=f"JEHA licensed {request.sfx_type} fixture",
            technical={"duration_seconds": 600, "format": "wav", "sample_rate": 48000, "channels": 2},
        )


class UnconfiguredLiveProvider:
    """Fail explicitly until a production provider and rights policy are configured."""

    def __init__(self, asset_type: str):
        self.asset_type = asset_type

    def generate(self, request: AssetRequest) -> dict:
        raise RuntimeError(
            f"Live {self.asset_type} provider is not configured. Select a provider, "
            "verify commercial-use policy, and configure credentials via environment/secrets."
        )
