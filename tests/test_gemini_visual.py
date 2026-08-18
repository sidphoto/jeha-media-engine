from __future__ import annotations

import base64
import hashlib

import pytest

from pipeline.gemini_visual import GeminiVisualProvider, _extract_image
from pipeline.providers import AssetRequest
from pipeline.visual_qa import STYLE_PRESET, validate_visual_lineage


def request() -> AssetRequest:
    return AssetRequest(
        topic_id="TOPIC-NATURE-000031",
        product="nature_room",
        production_spec_ref="spec.json",
        music_brief="Soft ambient music",
        visual_brief="Misty forest stream at dawn",
        duration_minutes=180,
        sfx_type="forest",
    )


def test_extract_image_from_interactions_rest_response():
    raw = b"image-bytes"
    image, mime, interaction_id = _extract_image({
        "id": "int-123",
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "x"}]},
            {"type": "model_output", "content": [
                {"type": "text", "text": "done"},
                {"type": "image", "mime_type": "image/png", "data": base64.b64encode(raw).decode()},
            ]},
        ],
    })
    assert image == raw
    assert mime == "image/png"
    assert interaction_id == "int-123"


def test_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = GeminiVisualProvider(commercial_use_ack=True, output_dir=tmp_path)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        provider.generate(request())


def test_requires_commercial_use_ack(tmp_path):
    provider = GeminiVisualProvider(api_key="test-key", commercial_use_ack=False, output_dir=tmp_path)
    with pytest.raises(RuntimeError, match="commercial-use terms"):
        provider.generate(request())


def test_generates_traceable_house_style_2k_master_without_exposing_secret(tmp_path):
    captured = {}
    image = b"fake-gemini-image-bytes"

    def fake_requester(url, api_key, payload):
        captured["url"] = url
        captured["api_key"] = api_key
        captured["payload"] = payload
        return image, "image/png", "int-test-123"

    provider = GeminiVisualProvider(
        api_key="super-secret-gemini-key",
        commercial_use_ack=True,
        output_dir=tmp_path,
        requester=fake_requester,
    )
    record = provider.generate(request())

    assert captured["url"].endswith("/v1beta/interactions")
    assert captured["api_key"] == "super-secret-gemini-key"
    assert captured["payload"]["model"] == "gemini-3.1-flash-image"
    assert captured["payload"]["response_format"] == {
        "type": "image",
        "mime_type": "image/png",
        "aspect_ratio": "16:9",
        "image_size": "2K",
    }
    assert "cinematic dreamy realism" in captured["payload"]["input"]
    assert "No text" in captured["payload"]["input"]

    assert record["asset_id"] == "VISUAL-NATURE-000031"
    assert record["provider"] == "google_gemini"
    assert record["model"] == "gemini-3.1-flash-image"
    assert record["technical"]["width"] == 2752
    assert record["technical"]["height"] == 1536
    assert record["technical"]["aspect_ratio"] == "16:9"
    assert record["technical"]["style_preset"] == STYLE_PRESET
    assert record["technical"]["interaction_id"] == "int-test-123"
    assert record["technical"]["synthid_expected"] is True
    assert record["rights"]["commercial_use"] is True
    assert record["content_hash"] == "sha256:" + hashlib.sha256(image).hexdigest()
    assert validate_visual_lineage(record) == []
    assert (tmp_path / "VISUAL-NATURE-000031.png").read_bytes() == image
    assert "super-secret-gemini-key" not in str(record)


def test_rejects_non_jeha_output_shape(tmp_path):
    provider = GeminiVisualProvider(
        api_key="test-key",
        commercial_use_ack=True,
        output_dir=tmp_path,
        aspect_ratio="1:1",
        requester=lambda *_: (b"x", "image/png", None),
    )
    with pytest.raises(ValueError, match="supports 16:9"):
        provider.generate(request())
