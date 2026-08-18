"""Gemini 3.1 Flash Image live provider for JEHA M3 visuals."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from pipeline.assets import make_asset_id
from pipeline.providers import AssetRequest, sequence_from_topic_id
from pipeline.visual_qa import STYLE_PRESET, visual_policy

GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.1-flash-image"
DEFAULT_IMAGE_SIZE = "2K"
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_MIME_TYPE = "image/png"
RESOLUTIONS = {
    ("16:9", "1K"): (1376, 768),
    ("16:9", "2K"): (2752, 1536),
    ("16:9", "4K"): (5504, 3072),
}


def _extract_image(response: dict) -> tuple[bytes, str, str | None]:
    """Extract the final image block from an Interactions API REST response."""
    interaction_id = response.get("id")
    for step in reversed(response.get("steps", [])):
        if step.get("type") != "model_output":
            continue
        for block in reversed(step.get("content", [])):
            if block.get("type") == "image" and block.get("data"):
                return base64.b64decode(block["data"]), block.get("mime_type", DEFAULT_MIME_TYPE), interaction_id
    raise RuntimeError("Gemini image generation returned no image output")


def _http_generate(url: str, api_key: str, payload: dict) -> tuple[bytes, str, str | None]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:  # noqa: S310 - fixed HTTPS endpoint
        parsed = json.loads(response.read().decode("utf-8"))
    return _extract_image(parsed)


class GeminiVisualProvider:
    """Generate a JEHA house-style 16:9 master using Gemini 3.1 Flash Image."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        commercial_use_ack: bool | None = None,
        output_dir: str | Path = "data/generated_assets/visual",
        requester: Callable[[str, str, dict], tuple[bytes, str, str | None]] = _http_generate,
        model_id: str = DEFAULT_MODEL,
        image_size: str = DEFAULT_IMAGE_SIZE,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if commercial_use_ack is None:
            commercial_use_ack = os.getenv("GEMINI_COMMERCIAL_USE_ACK", "").lower() in {"1", "true", "yes"}
        self.commercial_use_ack = commercial_use_ack
        self.output_dir = Path(output_dir)
        self.requester = requester
        self.model_id = model_id
        self.image_size = image_size
        self.aspect_ratio = aspect_ratio

    def generate(self, request: AssetRequest) -> dict:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for live Gemini visual generation")
        if not self.commercial_use_ack:
            raise RuntimeError(
                "Gemini commercial-use terms must be reviewed and acknowledged via "
                "GEMINI_COMMERCIAL_USE_ACK=true before live generation"
            )
        resolution = RESOLUTIONS.get((self.aspect_ratio, self.image_size))
        if resolution is None:
            raise ValueError("JEHA Gemini visual provider supports 16:9 at 1K, 2K, or 4K")

        policy = visual_policy(request.product)
        cues = ", ".join(policy["product_cues"])
        prompt = (
            f"{request.visual_brief}. JEHA house style: cinematic dreamy realism; realistic base, "
            "soft atmospheric light, air depth, refined harmonious color, immersive low-stimulation "
            f"long-form companion-media composition. Product cues: {cues}. "
            "Wide cinematic frame with clear visual hierarchy and motion-friendly depth layers. "
            "No text, letters, numbers, logos, watermarks, signatures, malformed objects, or pseudo-text."
        )
        payload = {
            "model": self.model_id,
            "input": prompt,
            "response_format": {
                "type": "image",
                "mime_type": DEFAULT_MIME_TYPE,
                "aspect_ratio": self.aspect_ratio,
                "image_size": self.image_size,
            },
        }
        image, mime_type, interaction_id = self.requester(GEMINI_INTERACTIONS_URL, self.api_key, payload)
        if not image:
            raise RuntimeError("Gemini image generation returned an empty image payload")

        sequence = sequence_from_topic_id(request.topic_id)
        asset_id = make_asset_id("visual", request.product.replace("_room", ""), sequence)
        suffix = ".png" if mime_type == "image/png" else ".jpg"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = self.output_dir / f"{asset_id}{suffix}"
        artifact_path.write_bytes(image)
        width, height = resolution

        return {
            "asset_id": asset_id,
            "asset_type": "visual",
            "topic_id": request.topic_id,
            "production_spec_ref": request.production_spec_ref,
            "provider": "google_gemini",
            "model": self.model_id,
            "provider_version": "Gemini Interactions API v1beta",
            "prompt_or_source": prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": "sha256:" + hashlib.sha256(image).hexdigest(),
            "rights": {
                "commercial_use": True,
                "license": "GOOGLE_GEMINI_API_TERMS_ACKNOWLEDGED",
                "source_url": "https://ai.google.dev/gemini-api/terms",
            },
            "technical": {
                "width": width,
                "height": height,
                "aspect_ratio": self.aspect_ratio,
                "format": suffix.lstrip("."),
                "mime_type": mime_type,
                "image_size": self.image_size,
                "artifact_path": str(artifact_path),
                "interaction_id": interaction_id,
                "style_preset": STYLE_PRESET,
                "reference_lineage": [],
                "source_policy": policy["source_priority"],
                "synthid_expected": True,
            },
            "qa_status": "pending",
        }
