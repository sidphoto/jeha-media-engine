from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import validate

from pipeline.visual_candidates import attach_generated_result, build_candidate_handoffs
from pipeline.visual_prompts import build_three_candidate_prompts
from pipeline.visual_qa import evaluate_visual_qa, visual_policy

ROOT = Path(__file__).resolve().parents[1]


def test_three_prompts_are_deterministic_and_purposeful():
    first = build_three_candidate_prompts(
        product="flow_room",
        scene="rainy focus desk beside a large window",
        lighting="warm task lamp with cool rainy exterior",
        mood="calm focused low-distraction",
    )
    second = build_three_candidate_prompts(
        product="flow_room",
        scene="rainy focus desk beside a large window",
        lighting="warm task lamp with cool rainy exterior",
        mood="calm focused low-distraction",
    )
    assert first == second
    assert [item["candidate_role"] for item in first] == ["primary", "alt_a", "alt_b"]
    assert len({item["prompt"] for item in first}) == 3
    assert all(item["aspect_ratio"] == "16:9" for item in first)
    assert all(item["provider"] == "chatgpt_image" for item in first)


def test_product_presets_are_locked():
    expected = {
        "flow_room": "jeha_flow_focus_v2",
        "moon_room": "jeha_moon_sleep_v2",
        "cozy_room": "jeha_cozy_warm_v2",
        "nature_room": "jeha_nature_atmospheric_v2",
    }
    for product, preset in expected.items():
        policy = visual_policy(product)
        assert policy["primary_provider"] == "chatgpt_image"
        assert policy["candidate_count"] == 3
        assert policy["product_style_preset"] == preset


def test_handoffs_validate_against_schema():
    schema = json.loads((ROOT / "schemas" / "visual_candidate.schema.json").read_text(encoding="utf-8"))
    handoffs = build_candidate_handoffs(
        topic_id="TOPIC-FLOW-000001",
        production_spec_ref="SPEC-FLOW-000001",
        product="flow_room",
        scene="rainy focus desk",
        lighting="warm desk light and blue rainy window",
        mood="quiet deep focus",
    )
    assert len(handoffs) == 3
    assert len({item["prompt_hash"] for item in handoffs}) == 3
    for handoff in handoffs:
        validate(handoff, schema)
        assert handoff["remote_execution_allowed"] is False


def test_generated_result_binds_exact_prompt_lineage():
    handoff = build_candidate_handoffs(
        topic_id="TOPIC-NATURE-000001",
        production_spec_ref="SPEC-NATURE-000001",
        product="nature_room",
        scene="misty forest stream",
        lighting="soft morning rays through mist",
        mood="restorative spacious calm",
    )[0]
    ready = attach_generated_result(
        handoff,
        artifact_path="data/generated_assets/visual/example.png",
        content_hash="sha256:" + "a" * 64,
    )
    assert ready["prompt_hash"] == handoff["prompt_hash"]
    assert ready["final_status"] == "VISUAL_CANDIDATE_READY_FOR_QA"


def test_visual_qa_rejects_non_finite_score_and_pseudo_text():
    components = {
        "house_style": 90,
        "product_fit": 90,
        "long_view_comfort": 90,
        "composition": 90,
        "thumbnail_legibility": 90,
        "light_color": 90,
        "ai_artifact_control": 90,
        "motion_potential": 90,
        "series_scalability": 90,
    }
    broken = dict(components)
    broken["house_style"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        evaluate_visual_qa({"components": broken, "hard_fail": {}})

    result = evaluate_visual_qa({"components": components, "hard_fail": {"pseudo_text": True}})
    assert result["gate"] == "FAIL"
    assert result["production_ready"] is False
