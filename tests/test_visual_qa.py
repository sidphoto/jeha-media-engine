from __future__ import annotations

import pytest

from pipeline.visual_qa import STYLE_PRESET, evaluate_visual_qa, validate_visual_lineage, visual_policy


def assessment(score: int, **hard_fail):
    return {
        "components": {
            "house_style": score,
            "product_fit": score,
            "long_view_comfort": score,
            "composition": score,
            "thumbnail_legibility": score,
            "light_color": score,
            "ai_artifact_control": score,
            "motion_potential": score,
            "series_scalability": score,
        },
        "hard_fail": hard_fail,
    }


def test_score_gate_thresholds():
    assert evaluate_visual_qa(assessment(90))["gate"] == "PASS"
    assert evaluate_visual_qa(assessment(82))["gate"] == "CONDITIONAL"
    assert evaluate_visual_qa(assessment(79))["gate"] == "FAIL"


def test_hard_fail_overrides_high_score():
    result = evaluate_visual_qa(assessment(98, pseudo_text=True))
    assert result["score"] == 98
    assert result["gate"] == "FAIL"
    assert result["production_ready"] is False
    assert result["hard_fail_reasons"] == ["pseudo_text"]


def test_missing_or_invalid_component_is_rejected():
    data = assessment(90)
    del data["components"]["house_style"]
    with pytest.raises(ValueError, match="Missing visual QA components"):
        evaluate_visual_qa(data)
    with pytest.raises(ValueError, match="between 0 and 100"):
        evaluate_visual_qa(assessment(101))


def test_visual_lineage_contract():
    record = {
        "prompt_or_source": "JEHA cinematic dreamy realism rainy focus desk",
        "rights": {"commercial_use": True, "license": "OWNER_OR_GENERATION_RIGHTS"},
        "technical": {
            "width": 1920,
            "height": 1080,
            "aspect_ratio": "16:9",
            "format": "png",
            "style_preset": STYLE_PRESET,
            "reference_lineage": [
                {"source_type": "owned_flickr_reference", "source_ref": "flickr://kar-ten/example"}
            ],
        },
    }
    assert validate_visual_lineage(record) == []


def test_visual_lineage_blocks_missing_rights_style_and_ratio():
    record = {
        "prompt_or_source": "test",
        "rights": {"commercial_use": False, "license": ""},
        "technical": {"aspect_ratio": "1:1", "reference_lineage": []},
    }
    issues = validate_visual_lineage(record)
    assert "non_16_9_master" in issues
    assert "wrong_or_missing_style_preset" in issues
    assert "unknown_rights" in issues


def test_product_policy_is_explicit_and_ai_first():
    policy = visual_policy("nature_room")
    assert policy["style_preset"] == STYLE_PRESET
    assert policy["source_priority"][0] == "ai_generation"
    assert policy["source_priority"][1] == "owned_flickr_reference"
    assert policy["source_priority"][2] == "owned_google_photos_reference"
    assert policy["source_priority"][3] == "free_commercial_stock_reference"
