from __future__ import annotations

import json
from pathlib import Path

from jsonschema import validate

from pipeline.planner import build_production_spec
from pipeline.qa import build_qa_report
from pipeline.research import generate_candidates
from pipeline.router import load_products, route_candidate, route_top_candidates
from pipeline.score import load_scoring_config, rank_candidates, score_candidate

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_outputs():
    scoring = load_scoring_config(ROOT / "config" / "scoring.yaml")
    products = load_products(ROOT / "config" / "products.yaml")
    candidates = generate_candidates()
    ranked = rank_candidates(candidates, scoring)
    top5 = route_top_candidates(ranked[:5], products)
    spec = build_production_spec(top5[0], products)
    qa = build_qa_report(spec, scoring["thresholds"]["originality_minimum"])
    return candidates, ranked, top5, spec, qa


def test_exactly_20_candidates_and_all_scored():
    candidates, ranked, *_ = build_outputs()
    assert len(candidates) == 20
    assert len(ranked) == 20
    assert all(0 <= item["score"] <= 100 for item in ranked)
    assert all(len(item["score_breakdown"]) == 8 for item in ranked)


def test_inverse_signals_reward_lower_cost_and_competition():
    scoring = load_scoring_config(ROOT / "config" / "scoring.yaml")
    base = {name: 50 for name in scoring["weights"]}
    cheap = {"id": "cheap", "signals": {**base, "production_cost": 10, "competition": 10}}
    expensive = {"id": "expensive", "signals": {**base, "production_cost": 90, "competition": 90}}
    assert score_candidate(cheap, scoring["weights"])["score"] > score_candidate(expensive, scoring["weights"])["score"]


def test_top5_descending_and_routed():
    _, ranked, top5, *_ = build_outputs()
    assert [item["score"] for item in top5] == sorted(
        [item["score"] for item in top5], reverse=True
    )
    assert [item["id"] for item in top5] == [item["id"] for item in ranked[:5]]
    assert all(item["product"] in {"flow_room", "moon_room", "cozy_room", "nature_room"} for item in top5)


def test_rain_routing_uses_primary_intent():
    products = load_products(ROOT / "config" / "products.yaml")
    cases = [
        ({"id": "sleep-rain", "tags": ["sleep", "rain"]}, "moon_room"),
        ({"id": "forest-rain", "tags": ["forest", "rain"]}, "nature_room"),
        ({"id": "coding-rain", "tags": ["coding", "rain"]}, "flow_room"),
        ({"id": "reading-rain", "tags": ["reading", "rain"]}, "cozy_room"),
    ]
    for candidate, expected in cases:
        routed = route_candidate(candidate, products)
        assert routed["product"] == expected
        assert routed["route_reason"]["method"] == "intent_priority"


def test_production_spec_and_qa_validate():
    *_, spec, qa = build_outputs()
    validate(spec, load_json(ROOT / "schemas" / "production_spec.schema.json"))
    validate(qa, load_json(ROOT / "schemas" / "qa_report.schema.json"))
    assert qa["passed"] is True
    assert spec["status"] == "awaiting_approval"
    assert spec["metadata"]["brand_fit"] > 0


def test_brand_fit_zero_fails_qa_and_normal_signal_passes():
    *_, spec, qa = build_outputs()
    normal_check = next(check for check in qa["checks"] if check["id"] == "brand_fit")
    assert normal_check["passed"] is True
    assert normal_check["evidence"]["brand_fit"] == spec["metadata"]["brand_fit"]

    invalid_spec = {**spec, "metadata": {**spec["metadata"], "brand_fit": 0}}
    invalid_qa = build_qa_report(invalid_spec, originality_minimum=60)
    invalid_check = next(check for check in invalid_qa["checks"] if check["id"] == "brand_fit")
    assert invalid_check["passed"] is False
    assert invalid_qa["passed"] is False


def test_same_seed_is_reproducible():
    first = build_outputs()[1:]
    second = build_outputs()[1:]
    assert first == second
