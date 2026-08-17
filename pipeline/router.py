"""Route shortlisted topics to JEHA products."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

# Intent beats generic tag overlap. Rules are ordered from most specific to fallback.
INTENT_RULES = (
    ("moon_room", {"sleep"}),
    ("flow_room", {"coding", "focus", "study", "pomodoro", "deep_work"}),
    ("cozy_room", {"reading", "cafe", "jazz", "cozy", "weekend"}),
    ("nature_room", {"forest", "ocean", "fireplace", "white_noise"}),
)


def load_products(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["products"]


def _intent_route(tags: set[str]) -> tuple[str, list[str]] | None:
    for product_id, intent_tags in INTENT_RULES:
        matched = sorted(tags.intersection(intent_tags))
        if matched:
            return product_id, matched
    return None


def route_candidate(candidate: dict, products: dict[str, dict]) -> dict:
    tags = set(candidate.get("tags", []))
    intent = _intent_route(tags)

    if intent:
        product_id, intent_matches = intent
        matched_themes = sorted(tags.intersection(products[product_id].get("themes", [])))
        route_method = "intent_priority"
    else:
        ranked_routes = []
        for product_id, config in products.items():
            overlap = tags.intersection(config.get("themes", []))
            # Product id is the deterministic final tie-breaker; config order is irrelevant.
            ranked_routes.append((len(overlap), product_id, sorted(overlap)))
        _, product_id, matched_themes = max(ranked_routes)
        intent_matches = []
        route_method = "theme_overlap"

    routed = deepcopy(candidate)
    routed["product"] = product_id
    routed["route_reason"] = {
        "method": route_method,
        "intent_matches": intent_matches,
        "matched_themes": matched_themes,
        "purpose": products[product_id]["purpose"],
    }
    return routed


def route_top_candidates(candidates: list[dict], products: dict[str, dict]) -> list[dict]:
    return [route_candidate(candidate, products) for candidate in candidates]
