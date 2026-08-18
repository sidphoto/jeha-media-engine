"""Production spec generation for the selected M1 topic."""

from __future__ import annotations


def build_production_spec(topic: dict, products: dict[str, dict]) -> dict:
    product_id = topic["product"]
    product = products[product_id]
    matched = topic.get("route_reason", {}).get("matched_themes", [])
    primary_theme = matched[0] if matched else product["purpose"]

    return {
        "topic_id": topic["id"],
        "product": product_id,
        "duration_minutes": product["default_duration_minutes"],
        "music": {
            "mode": "planning_only",
            "brief": f"Original {primary_theme} companion audio for {product['name']}",
            "generation_status": "not_started",
        },
        "visual": {
            "mode": "planning_only",
            "brief": f"Original calm loop visual matching: {topic['title']}",
            "generation_status": "not_started",
        },
        "metadata": {
            "working_title": topic["title"],
            "product_name": product["name"],
            "purpose": product["purpose"],
            "tags": topic.get("tags", []),
            "source_trace": topic.get("source_trace", {}),
            "candidate_score": topic["score"],
            "brand_fit": topic["signals"]["brand_fit"],
        },
        "originality_target": 85,
        "status": "awaiting_approval",
    }
