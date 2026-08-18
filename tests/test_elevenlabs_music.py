from __future__ import annotations

import hashlib

import pytest

from pipeline.elevenlabs_music import ElevenLabsMusicProvider
from pipeline.providers import AssetRequest


def request(duration_minutes: int = 180) -> AssetRequest:
    return AssetRequest(
        topic_id="TOPIC-FLOW-000024",
        product="flow_room",
        production_spec_ref="spec.json",
        music_brief="Soft rainy focus ambience with restrained piano and warm pads",
        visual_brief="Rainy focus desk",
        duration_minutes=duration_minutes,
        sfx_type="rain",
    )


def test_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    provider = ElevenLabsMusicProvider(
        commercial_use_ack=True,
        output_dir=tmp_path,
    )
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        provider.generate(request())


def test_requires_commercial_use_ack(tmp_path):
    provider = ElevenLabsMusicProvider(
        api_key="test-key",
        commercial_use_ack=False,
        output_dir=tmp_path,
    )
    with pytest.raises(RuntimeError, match="commercial-use terms"):
        provider.generate(request())


def test_generates_traceable_music_v2_master_without_exposing_secret(tmp_path):
    captured = {}
    audio = b"fake-elevenlabs-music-bytes"

    def fake_requester(url, headers, payload):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return audio, {"song-id": "song-test-123"}

    provider = ElevenLabsMusicProvider(
        api_key="super-secret-test-key",
        commercial_use_ack=True,
        output_dir=tmp_path,
        requester=fake_requester,
    )
    record = provider.generate(request())

    assert captured["url"].endswith("/v1/music?output_format=mp3_48000_192")
    assert captured["headers"]["xi-api-key"] == "super-secret-test-key"
    assert captured["payload"]["model_id"] == "music_v2"
    assert captured["payload"]["force_instrumental"] is True
    assert captured["payload"]["music_length_ms"] == 600_000

    assert record["asset_id"] == "MUSIC-FLOW-000024"
    assert record["provider"] == "elevenlabs"
    assert record["model"] == "music_v2"
    assert record["rights"]["commercial_use"] is True
    assert record["technical"]["master_generation_minutes"] == 10
    assert record["technical"]["requested_program_minutes"] == 180
    assert record["technical"]["song_id"] == "song-test-123"
    assert record["content_hash"] == "sha256:" + hashlib.sha256(audio).hexdigest()
    assert "super-secret-test-key" not in repr(record)

    artifact = tmp_path / "MUSIC-FLOW-000024.mp3"
    assert artifact.read_bytes() == audio


def test_short_program_does_not_expand_to_api_maximum(tmp_path):
    captured = {}

    def fake_requester(url, headers, payload):
        captured.update(payload)
        return b"short-track", {}

    provider = ElevenLabsMusicProvider(
        api_key="test-key",
        commercial_use_ack=True,
        output_dir=tmp_path,
        requester=fake_requester,
    )
    record = provider.generate(request(duration_minutes=5))

    assert captured["music_length_ms"] == 300_000
    assert record["technical"]["duration_seconds"] == 300
    assert record["technical"]["master_generation_minutes"] == 5


def test_empty_audio_is_hard_failure(tmp_path):
    provider = ElevenLabsMusicProvider(
        api_key="test-key",
        commercial_use_ack=True,
        output_dir=tmp_path,
        requester=lambda *_: (b"", {}),
    )
    with pytest.raises(RuntimeError, match="empty audio"):
        provider.generate(request())
