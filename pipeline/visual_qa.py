"""JEHA visual house-style scoring and production gate."""
from __future__ import annotations

import math

STYLE_PRESET = "jeha_cinematic_dreamy_realism_v2"
PRODUCT_STYLE_PRESETS = {
    "flow_room": "jeha_flow_focus_v2",
    "moon_room": "jeha_moon_sleep_v2",
    "cozy_room": "jeha_cozy_warm_v2",
    "nature_room": "jeha_nature_atmospheric_v2",
}

WEIGHTS = {
    "house_style": 20,
    "product_fit": 15,
    "long_view_comfort": 15,
    "composition": 10,
    "thumbnail_legibility": 10,
    "light_color": 10,
    "ai_artifact_control": 10,
    "motion_potential": 5,
    "series_scalability": 5,
}

HARD_FAIL_KEYS = (
    "pseudo_text",
    "watermark_or_logo",
    "major_structural_artifact",
    "unknown_rights",
    "non_16_9_master",
    "production_spec_mismatch",
    "missing_prompt_lineage",
)

PRODUCT_CUES = {
    "flow_room": ["rainy focus desk", "study", "coding", "calm productivity"],
    "moon_room": ["understated moonlight", "rain night", "sleep", "low contrast"],
    "cozy_room": ["warm reading", "cafe", "fireplace", "intimate calm", "no readable book text"],
    "nature_room": ["mist", "forest", "stream", "ocean", "restorative landscape"],
}

SOURCE_PRIORITY = [
    "chatgpt_image",
    "owned_flickr_reference",
    "owned_google_photos_reference",
    "free_commercial_stock_reference",
    "paid_image_api_fallback",
]


def _score_component(value: float | int, weight: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("visual QA component scores must be numeric")
    if not math.isfinite(value):
        raise ValueError("visual QA component scores must be finite")
    if not 0 <= value <= 100:
        raise ValueError("visual QA component scores must be between 0 and 100")
    return value / 100 * weight


def evaluate_visual_qa(assessment: dict) -> dict:
    """Apply JEHA Visual QA v2 weighted scoring and hard-fail rules."""
    components = assessment.get("components", {})
    missing = [key for key in WEIGHTS if key not in components]
    if missing:
        raise ValueError(f"Missing visual QA components: {', '.join(missing)}")

    weighted = {
        key: round(_score_component(components[key], weight), 2)
        for key, weight in WEIGHTS.items()
    }
    total = round(sum(weighted.values()), 2)

    flags = assessment.get("hard_fail", {})
    hard_fail_reasons = [key for key in HARD_FAIL_KEYS if flags.get(key) is True]
    if hard_fail_reasons:
        gate = "FAIL"
    elif total >= 85:
        gate = "PASS"
    elif total >= 80:
        gate = "CONDITIONAL"
    else:
        gate = "FAIL"

    return {
        "style_preset": STYLE_PRESET,
        "score": total,
        "gate": gate,
        "weighted_components": weighted,
        "hard_fail_reasons": hard_fail_reasons,
        "requires_repair": gate == "CONDITIONAL",
        "production_ready": gate == "PASS",
    }


def validate_visual_lineage(record: dict) -> list[str]:
    """Return visual lineage/policy violations that must block production."""
    issues: list[str] = []
    technical = record.get("technical", {})
    rights = record.get("rights", {})
    product = record.get("product") or technical.get("product")

    if technical.get("aspect_ratio") != "16:9":
        issues.append("non_16_9_master")
    if technical.get("style_preset") != STYLE_PRESET:
        issues.append("wrong_or_missing_style_preset")
    product_style = technical.get("product_style_preset")
    if product in PRODUCT_STYLE_PRESETS and product_style not in (None, PRODUCT_STYLE_PRESETS[product]):
        issues.append("wrong_product_style_preset")
    if not isinstance(technical.get("reference_lineage"), list):
        issues.append("missing_reference_lineage")
    if rights.get("commercial_use") is not True or not rights.get("license"):
        issues.append("unknown_rights")
    if not record.get("prompt_or_source"):
        issues.append("missing_prompt_or_source")
    if record.get("provider") == "chatgpt_image" and not record.get("prompt_hash"):
        issues.append("missing_prompt_hash")
    return issues


def visual_policy(product: str) -> dict:
    if product not in PRODUCT_CUES:
        raise ValueError(f"Unknown JEHA product: {product}")
    return {
        "style_preset": STYLE_PRESET,
        "product_style_preset": PRODUCT_STYLE_PRESETS[product],
        "product": product,
        "product_cues": PRODUCT_CUES[product],
        "source_priority": SOURCE_PRIORITY,
        "candidate_count": 3,
        "candidate_roles": ["primary", "alt_a", "alt_b"],
        "primary_provider": "chatgpt_image",
        "final_output": "ChatGPT-generated 16:9 master by default after three-candidate QA",
    }
