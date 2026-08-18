"""ElevenLabs Music live provider for JEHA M3.

The adapter is isolated from M3 orchestration and uses only environment/secrets for
credentials. Commercial-use rights must be explicitly acknowledged before generation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from pipeline.assets import make_asset_id
from pipeline.providers import AssetRequest, sequence_from_topic_id

ELEVENLABS_MUSIC_URL = "https://api.elevenlabs.io/v1/music"
DEFAULT_MODEL = "music_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_48000_192"
MAX_GENERATION_MS = 600_000


def _http_post(url: str, headers: dict[str, str], payload: dict) -> tuple[bytes, dict[str, str]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=180) as response:  # noqa: S310 - fixed HTTPS endpoint
        return response.read(), dict(response.headers.items())


class ElevenLabsMusicProvider:
    """Generate a traceable instrumental music master with ElevenLabs Music v2."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        commercial_use_ack: bool | None = None,
        output_dir: str | Path = "data/generated_assets/music",
        requester: Callable[[str, dict[str, str], dict], tuple[bytes, dict[str, str]]] = _http_post,
        model_id: str = DEFAULT_MODEL,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ) -> None:
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if commercial_use_ack is None:
            commercial_use_ack = os.getenv("ELEVENLABS_COMMERCIAL_USE_ACK", "").lower() in {"1", "true", "yes"}
        self.commercial_use_ack = commercial_use_ack
        self.output_dir = Path(output_dir)
        self.requester = requester
        self.model_id = model_id
        self.output_format = output_format

    def generate(self, request: AssetRequest) -> dict:
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is required for live ElevenLabs Music generation")
        if not self.commercial_use_ack:
            raise RuntimeError(
                "ElevenLabs commercial-use terms must be reviewed and acknowledged via "
                "ELEVENLABS_COMMERCIAL_USE_ACK=true before live generation"
            )

        # M4 is responsible for extending masters into long-form programs. M3 generates
        # at most the ElevenLabs API maximum of 10 minutes per request.
        requested_ms = request.duration_minutes * 60_000
        music_length_ms = min(requested_ms, MAX_GENERATION_MS)
        prompt = (
            f"{request.music_brief}. Instrumental companion music only; no vocals. "
            f"Product: {request.product}. Smooth structure suitable for seamless long-form extension."
        )
        payload = {
            "prompt": prompt,
            "music_length_ms": music_length_ms,
            "model_id": self.model_id,
            "force_instrumental": True,
        }
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.api_key,
        }
        audio, response_headers = self.requester(
            f"{ELEVENLABS_MUSIC_URL}?output_format={self.output_format}",
            headers,
            payload,
        )
        if not audio:
            raise RuntimeError("ElevenLabs Music returned an empty audio payload")

        sequence = sequence_from_topic_id(request.topic_id)
        asset_id = make_asset_id(
            "music",
            request.product.replace("_room", ""),
            sequence,
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".mp3" if self.output_format.startswith("mp3_") else ".bin"
        artifact_path = self.output_dir / f"{asset_id}{suffix}"
        artifact_path.write_bytes(audio)

        return {
            "asset_id": asset_id,
            "asset_type": "music",
            "topic_id": request.topic_id,
            "production_spec_ref": request.production_spec_ref,
            "provider": "elevenlabs",
            "model": self.model_id,
            "provider_version": "Eleven Music API",
            "prompt_or_source": prompt,
            "created_at": "2026-08-18T00:00:00+00:00",
            "content_hash": "sha256:" + hashlib.sha256(audio).hexdigest(),
            "rights": {
                "commercial_use": True,
                "license": "ELEVENLABS_MUSIC_TERMS_ACKNOWLEDGED",
                "source_url": "https://elevenlabs.io/docs/overview/capabilities/music",
            },
            "technical": {
                "duration_seconds": music_length_ms / 1000,
                "format": "mp3" if suffix == ".mp3" else self.output_format,
                "sample_rate": 48000,
                "channels": 2,
                "output_format": self.output_format,
                "artifact_path": str(artifact_path),
                "song_id": response_headers.get("song-id") or response_headers.get("Song-Id"),
                "requested_program_minutes": request.duration_minutes,
                "master_generation_minutes": music_length_ms / 60_000,
            },
            "qa_status": "pending",
        }
