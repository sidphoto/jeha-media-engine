from __future__ import annotations

import hashlib
import json

import pytest

from pipeline.gemini_web_music import GeminiWebMusicProvider, build_music_handoff
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


def fake_probe(_path):
    return {
        "duration_seconds": 173.923208,
        "format": "mp3",
        "sample_rate": 44100,
        "channels": 2,
    }


def test_handoff_is_deterministic_and_prefers_3_7_flash():
    first = build_music_handoff(request())
    second = build_music_handoff(request())

    assert first == second
    assert first["provider"] == "gemini_web"
    assert first["preferred_model"] == "3.7 Flash"
    assert first["output_format"] == "mp3"
    assert first["download_selection"] == "audio_only_mp3"
    assert first["final_status"] == "AWAITING_GEMINI_WEB_MUSIC_GENERATION"
    assert first["remote_execution_allowed"] is False
    assert first["prompt_hash"].startswith("sha256:")
    assert "No vocals, no lyrics, no spoken words." in first["prompt"]


def test_handoff_model_preference_is_overrideable():
    handoff = build_music_handoff(request(), model_preference="3.1 Pro")
    assert handoff["preferred_model"] == "3.1 Pro"


def test_requires_browser_artifact_before_attach():
    provider = GeminiWebMusicProvider(commercial_use_ack=True)
    with pytest.raises(RuntimeError, match="browser-generated MP3"):
        provider.generate(request())


def test_requires_exact_model_and_terms_ack(tmp_path):
    source = tmp_path / "download.mp3"
    source.write_bytes(b"browser-mp3")

    no_model = GeminiWebMusicProvider(
        artifact_path=source,
        commercial_use_ack=True,
        output_dir=tmp_path / "out-1",
        probe=fake_probe,
    )
    with pytest.raises(RuntimeError, match="exact Gemini model/mode label"):
        no_model.generate(request())

    no_ack = GeminiWebMusicProvider(
        artifact_path=source,
        model_label="3.7 Flash",
        commercial_use_ack=False,
        output_dir=tmp_path / "out-2",
        probe=fake_probe,
    )
    with pytest.raises(RuntimeError, match="COMMERCIAL_USE_ACK"):
        no_ack.generate(request())


def test_attaches_verified_browser_mp3_without_moving_source(tmp_path):
    source = tmp_path / "Beneath_the_Pine_Bough.mp3"
    audio = b"browser-generated-mp3-bytes"
    source.write_bytes(audio)
    handoff_path = tmp_path / "music_handoff.json"
    handoff_path.write_text(json.dumps(build_music_handoff(request())), encoding="utf-8")

    provider = GeminiWebMusicProvider(
        artifact_path=source,
        model_label="3.7 Flash",
        commercial_use_ack=True,
        handoff_path=handoff_path,
        output_dir=tmp_path / "out",
        probe=fake_probe,
    )
    record = provider.generate(request())

    destination = tmp_path / "out" / "MUSIC-FLOW-000024.mp3"
    assert record["asset_id"] == "MUSIC-FLOW-000024"
    assert record["provider"] == "gemini_web"
    assert record["model"] == "3.7 Flash"
    assert record["rights"]["commercial_use"] is True
    assert record["technical"]["format"] == "mp3"
    assert record["technical"]["duration_seconds"] > 0
    assert record["content_hash"] == "sha256:" + hashlib.sha256(audio).hexdigest()
    assert destination.read_bytes() == audio
    assert source.read_bytes() == audio


def test_refuses_stale_handoff_lineage(tmp_path):
    source = tmp_path / "download.mp3"
    source.write_bytes(b"browser-mp3")
    handoff = build_music_handoff(request())
    handoff["prompt"] += " mutated"
    handoff_path = tmp_path / "music_handoff.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    provider = GeminiWebMusicProvider(
        artifact_path=source,
        model_label="3.7 Flash",
        commercial_use_ack=True,
        handoff_path=handoff_path,
        probe=fake_probe,
    )
    with pytest.raises(RuntimeError, match="stale or mutated"):
        provider.generate(request())
