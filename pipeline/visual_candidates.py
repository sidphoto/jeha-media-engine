"""ChatGPT browser-provider handoff contract for JEHA visual candidates."""
from __future__ import annotations

import hashlib
import json

from pipeline.visual_prompts import build_three_candidate_prompts


def _stable_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_candidate_handoffs(
    *,
    topic_id: str,
    production_spec_ref: str,
    product: str,
    scene: str,
    lighting: str,
    mood: str,
) -> list[dict]:
    """Create exactly three browser-execution handoffs without making any remote call."""
    if not isinstance(topic_id, str) or not topic_id.startswith("TOPIC-"):
        raise ValueError("canonical TOPIC ID is required")
    if not isinstance(production_spec_ref, str) or not production_spec_ref.strip():
        raise ValueError("production_spec_ref is required")

    prompts = build_three_candidate_prompts(product=product, scene=scene, lighting=lighting, mood=mood)
    handoffs: list[dict] = []
    for prompt in prompts:
        payload = {
            "topic_id": topic_id,
            "production_spec_ref": production_spec_ref,
            "product": product,
            "candidate_role": prompt["candidate_role"],
            "provider": "chatgpt_image",
            "execution_mode": "browser_handoff",
            "parent_style": prompt["parent_style"],
            "style_preset": prompt["style_preset"],
            "reference_role": prompt["reference_role"],
            "aspect_ratio": "16:9",
            "prompt": prompt["prompt"],
            "remote_execution_allowed": False,
            "final_status": "AWAITING_CHATGPT_IMAGE_GENERATION",
        }
        payload["prompt_hash"] = _stable_hash({
            "topic_id": topic_id,
            "production_spec_ref": production_spec_ref,
            "product": product,
            "candidate_role": prompt["candidate_role"],
            "parent_style": prompt["parent_style"],
            "style_preset": prompt["style_preset"],
            "aspect_ratio": "16:9",
            "prompt": prompt["prompt"],
        })
        handoffs.append(payload)

    if [item["candidate_role"] for item in handoffs] != ["primary", "alt_a", "alt_b"]:
        raise RuntimeError("JEHA visual candidate order drifted")
    return handoffs


def attach_generated_result(handoff: dict, *, artifact_path: str, content_hash: str) -> dict:
    """Bind a returned ChatGPT image artifact to the exact prompt lineage."""
    if handoff.get("final_status") != "AWAITING_CHATGPT_IMAGE_GENERATION":
        raise ValueError("visual handoff is not awaiting generation")
    if not artifact_path:
        raise ValueError("artifact_path is required")
    if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
        raise ValueError("content_hash must be a sha256 digest")
    result = dict(handoff)
    result.update({
        "artifact_path": artifact_path,
        "content_hash": content_hash,
        "remote_execution_allowed": False,
        "final_status": "VISUAL_CANDIDATE_READY_FOR_QA",
    })
    return result
