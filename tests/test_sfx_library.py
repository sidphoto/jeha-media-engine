from __future__ import annotations

import hashlib
import json

import pytest

from pipeline.providers import AssetRequest
from pipeline.sfx_library import LocalSFXLibraryProvider


def request(sfx_type="rain"):
    return AssetRequest(
        topic_id="TOPIC-MOON-000012",
        product="moon_room",
        production_spec_ref="spec.json",
        music_brief="sleep ambience",
        visual_brief="rainy night",
        duration_minutes=480,
        sfx_type=sfx_type,
    )


def write_library(tmp_path, entries):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"assets": entries}), encoding="utf-8")
    return manifest


def valid_entry(path, **overrides):
    data = {
        "id": "rain-001",
        "sfx_type": "rain",
        "path": path,
        "source_url": "https://example.invalid/rain-source",
        "license": "FREE_COMMERCIAL_TEST_LICENSE",
        "commercial_use": True,
        "duration_seconds": 600,
        "format": "wav",
        "sample_rate": 48000,
        "channels": 2,
        "priority": 10,
    }
    data.update(overrides)
    return data


def test_local_library_returns_traceable_hashed_asset(tmp_path):
    audio = b"licensed-rain-audio"
    source = tmp_path / "rain.wav"
    source.write_bytes(audio)
    manifest = write_library(tmp_path, [valid_entry("rain.wav")])

    record = LocalSFXLibraryProvider(manifest_path=manifest).generate(request())

    assert record["asset_id"] == "SFX-RAIN-000012"
    assert record["provider"] == "jeha_local_sfx_library"
    assert record["rights"]["commercial_use"] is True
    assert record["rights"]["license"] == "FREE_COMMERCIAL_TEST_LICENSE"
    assert record["content_hash"] == "sha256:" + hashlib.sha256(audio).hexdigest()
    assert record["technical"]["artifact_path"].endswith("rain.wav")


def test_optional_sfx_returns_none(tmp_path):
    manifest = write_library(tmp_path, [])
    assert LocalSFXLibraryProvider(manifest_path=manifest).generate(request(None)) is None


def test_missing_rights_metadata_is_hard_failure(tmp_path):
    source = tmp_path / "rain.wav"
    source.write_bytes(b"audio")
    entry = valid_entry("rain.wav")
    del entry["license"]
    manifest = write_library(tmp_path, [entry])
    with pytest.raises(RuntimeError, match="missing required metadata"):
        LocalSFXLibraryProvider(manifest_path=manifest).generate(request())


def test_noncommercial_entry_is_hard_failure(tmp_path):
    source = tmp_path / "rain.wav"
    source.write_bytes(b"audio")
    manifest = write_library(tmp_path, [valid_entry("rain.wav", commercial_use=False)])
    with pytest.raises(RuntimeError, match="not cleared for commercial use"):
        LocalSFXLibraryProvider(manifest_path=manifest).generate(request())


def test_missing_local_file_is_hard_failure(tmp_path):
    manifest = write_library(tmp_path, [valid_entry("missing.wav")])
    with pytest.raises(RuntimeError, match="file not found"):
        LocalSFXLibraryProvider(manifest_path=manifest).generate(request())


def test_selection_is_deterministic_by_priority_then_path(tmp_path):
    first = tmp_path / "a.wav"
    second = tmp_path / "b.wav"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    manifest = write_library(tmp_path, [
        valid_entry("b.wav", id="b", priority=20),
        valid_entry("a.wav", id="a", priority=10),
    ])
    record = LocalSFXLibraryProvider(manifest_path=manifest).generate(request())
    assert record["technical"]["library_entry_id"] == "a"
