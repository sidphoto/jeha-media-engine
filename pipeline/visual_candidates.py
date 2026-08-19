"""ChatGPT browser-provider handoff contract for JEHA visual candidates."""
from __future__ import annotations

import hashlib
import json
import re

from pipeline.visual_prompts import build_three_candidate_prompts

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROMPT_HASH_FIELDS = (
    "topic_id",
    "production_spec_ref",
    "product",
    "candidate_role",
    "parent_style",
    "style_preset",
    "aspect_ratio",
    "prompt",
)


def _stable_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _prompt_lineage_hash(record: dict) -> str:
    """Recompute the canonical hash over every field bound by the handoff contract."""
    try:
        payload = {field: record[field] for field in _PROMPT_HASH_FIELDS}
    except KeyError as exc:
        raise ValueError(f"visual handoff is missing hash-bound field: {exc.args[0]}") from exc
    return _stable_hash(payload)


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
        payload["prompt_hash"] = _prompt_lineage_hash(payload)
        handoffs.append(payload)

    if [item["candidate_role"] for item in handoffs] != ["primary", "alt_a", "alt_b"]:
        raise RuntimeError("JEHA visual candidate order drifted")
    return handoffs


def attach_generated_result(handoff: dict, *, artifact_path: str, content_hash: str) -> dict:
    """Bind a returned ChatGPT image artifact only to an untampered prompt lineage."""
    if handoff.get("final_status") != "AWAITING_CHATGPT_IMAGE_GENERATION":
        raise ValueError("visual handoff is not awaiting generation")
    expected_prompt_hash = _prompt_lineage_hash(handoff)
    if handoff.get("prompt_hash") != expected_prompt_hash:
        raise ValueError("visual handoff prompt lineage is stale or has been mutated")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ValueError("artifact_path is required")
    if not isinstance(content_hash, str) or not _SHA256_RE.fullmatch(content_hash):
        raise ValueError("content_hash must be a full sha256 digest")
    result = dict(handoff)
    result.update({
        "artifact_path": artifact_path,
        "content_hash": content_hash,
        "remote_execution_allowed": False,
        "final_status": "VISUAL_CANDIDATE_READY_FOR_QA",
    })
    return result
