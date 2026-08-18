"""M3 provider contracts and deterministic fixture adapters.

Live providers are configuration-gated so orchestration remains stable while production
providers, commercial-use policies, and credentials are selected independently.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pipeline.assets import build_fixture_asset
from pipeline.visual_qa import STYLE_PRESET

MAX_FIXTURE_MUSIC_MASTER_SECONDS = 600


@dataclass(frozen=True)
class AssetRequest:
    topic_id: str
    product: str
    production_spec_ref: str
    music_brief: str
    visual_brief: str
    duration_minutes: int
    sfx_type: str | None = None


def sequence_from_topic_id(topic_id: str) -> int:
    """Derive a stable non-zero six-digit asset sequence from TOPIC lineage."""
    match = re.search(r"(\d+)$", topic_id)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 999999:
            return value
    digest = hashlib.sha256(topic_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 999999 + 1


class FixtureMusicProvider:
    def generate(self, request: AssetRequest) -> dict:
        requested_seconds = request.duration_minutes * 60
        master_seconds = min(requested_seconds, MAX_FIXTURE_MUSIC_MASTER_SECONDS)
        return build_fixture_asset(
            asset_type="music",
            namespace=request.product.replace("_room", ""),
            sequence=sequence_from_topic_id(request.topic_id),
            topic_id=request.topic_id,
            production_spec_ref=request.production_spec_ref,
            prompt_or_source=request.music_brief,
            technical={
                "duration_seconds": master_seconds,
                "format": "wav",
                "sample_rate": 48000,
                "channels": 2,
                "requested_program_minutes": request.duration_minutes,
                "master_generation_minutes": master_seconds / 60,
                "fixture_contract": "production_master_duration_cap",
            },
        )


class FixtureVisualProvider:
    def generate(self, request: AssetRequest) -> dict:
        return build_fixture_asset(
            asset_type="visual",
            namespace=request.product.replace("_room", ""),
            sequence=sequence_from_topic_id(request.topic_id),
            topic_id=request.topic_id,
            production_spec_ref=request.production_spec_ref,
            prompt_or_source=request.visual_brief,
            technical={
                "width": 1920,
                "height": 1080,
                "aspect_ratio": "16:9",
                "format": "png",
                "style_preset": STYLE_PRESET,
                "reference_lineage": [],
                "source_policy": "ai_generation",
            },
        )


class FixtureSFXProvider:
    def generate(self, request: AssetRequest) -> dict | None:
        if not request.sfx_type:
            return None
        return build_fixture_asset(
            asset_type="sfx",
            namespace=request.sfx_type,
            sequence=sequence_from_topic_id(request.topic_id),
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
