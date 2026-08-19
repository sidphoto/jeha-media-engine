"""Deterministic JEHA visual prompt construction for ChatGPT-first generation."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE_CONFIG = ROOT / "configs" / "visual_styles.json"
CANDIDATE_ROLES = ("primary", "alt_a", "alt_b")


def load_visual_styles(path: str | Path = STYLE_CONFIG) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("candidate_policy", {}).get("count") != 3:
        raise ValueError("JEHA visual v2 requires exactly three candidates")
    if tuple(data.get("candidate_policy", {}).get("roles", [])) != CANDIDATE_ROLES:
        raise ValueError("JEHA visual v2 candidate roles must be primary, alt_a, alt_b")
    return data


def _clean(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return " ".join(value.split())


def build_visual_prompt(
    *,
    product: str,
    scene: str,
    lighting: str,
    mood: str,
    candidate_role: str = "primary",
    composition: str = "wide cinematic frame with clear visual hierarchy and motion-friendly depth",
) -> dict:
    """Build one stable prompt and return its explicit style lineage."""
    styles = load_visual_styles()
    products = styles["products"]
    if product not in products:
        raise ValueError(f"Unknown JEHA product: {product}")
    if candidate_role not in CANDIDATE_ROLES:
        raise ValueError(f"Unknown visual candidate role: {candidate_role}")

    parent = styles["parent_style"]
    product_style = products[product]
    variant = styles["candidate_policy"][candidate_role]
    scene = _clean(scene, "scene")
    lighting = _clean(lighting, "lighting")
    mood = _clean(mood, "mood")
    composition = _clean(composition, "composition")

    parts = [
        parent["base_prompt"],
        product_style["prompt"],
        f"Scene: {scene}.",
        f"Lighting: {lighting}.",
        f"Composition: {composition}.",
        f"Mood: {mood}.",
        f"Candidate instruction: {variant}",
        parent["negative_guidance"],
    ]
    prompt = " ".join(parts)
    return {
        "provider": "chatgpt_image",
        "parent_style": parent["id"],
        "style_preset": product_style["preset"],
        "reference_role": product_style["reference_role"],
        "product": product,
        "candidate_role": candidate_role,
        "aspect_ratio": "16:9",
        "prompt": prompt,
    }


def build_three_candidate_prompts(*, product: str, scene: str, lighting: str, mood: str) -> list[dict]:
    """Return exactly three purposeful variants: canonical, composition, atmosphere."""
    return [
        build_visual_prompt(product=product, scene=scene, lighting=lighting, mood=mood, candidate_role=role)
        for role in CANDIDATE_ROLES
    ]
