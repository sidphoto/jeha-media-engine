"""Route shortlisted topics to JEHA products."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml


def load_products(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["products"]


def route_candidate(candidate: dict, products: dict[str, dict]) -> dict:
    tags = set(candidate.get("tags", []))
    ranked_routes = []
    for order, (product_id, config) in enumerate(products.items()):
        overlap = tags.intersection(config.get("themes", []))
        ranked_routes.append((len(overlap), -order, product_id, sorted(overlap)))

    _, _, product_id, matched_themes = max(ranked_routes)
    routed = deepcopy(candidate)
    routed["product"] = product_id
    routed["route_reason"] = {
        "matched_themes": matched_themes,
        "purpose": products[product_id]["purpose"],
    }
    return routed


def route_top_candidates(candidates: list[dict], products: dict[str, dict]) -> list[dict]:
    return [route_candidate(candidate, products) for candidate in candidates]
