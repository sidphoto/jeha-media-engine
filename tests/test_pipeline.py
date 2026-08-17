from __future__ import annotations

import json
from pathlib import Path

from jsonschema import validate

from pipeline.planner import build_production_spec
from pipeline.qa import build_qa_report
from pipeline.research import generate_candidates
from pipeline.router import load_products, route_top_candidates
from pipeline.score import load_scoring_config, rank_candidates

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


def test_top5_descending_and_routed():
    _, ranked, top5, *_ = build_outputs()
    assert [item["score"] for item in top5] == sorted(
        [item["score"] for item in top5], reverse=True
    )
    assert [item["id"] for item in top5] == [item["id"] for item in ranked[:5]]
    assert all(item["product"] in {"flow_room", "moon_room", "cozy_room", "nature_room"} for item in top5)


def test_production_spec_and_qa_validate():
    *_, spec, qa = build_outputs()
    validate(spec, load_json(ROOT / "schemas" / "production_spec.schema.json"))
    validate(qa, load_json(ROOT / "schemas" / "qa_report.schema.json"))
    assert qa["passed"] is True
    assert spec["status"] == "awaiting_approval"


def test_same_seed_is_reproducible():
    first = build_outputs()[1:]
    second = build_outputs()[1:]
    assert first == second
