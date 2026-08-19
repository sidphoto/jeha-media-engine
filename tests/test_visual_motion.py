from __future__ import annotations

import pytest

from pipeline.assembly import approve_asset_bundle, build_render_plan
from pipeline.asset_generation import generate_asset_bundle
from pipeline.visual_motion import MOTION_PROFILES, build_visual_motion_plan


def spec(product="flow_room", duration_minutes=180):
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": product,
        "duration_minutes": duration_minutes,
        "music": {"brief": "Original companion music"},
        "visual": {"brief": "Rainy companion visual"},
        "metadata": {"tags": ["focus", "coding"]},
    }


def approved_inputs(product="flow_room", duration_minutes=180):
    production_spec = spec(product, duration_minutes)
    bundle = generate_asset_bundle(production_spec, mode="fixture", production_spec_ref="spec.json")
    approved = approve_asset_bundle(bundle, approver="human-owner", approved_at="2026-08-18T12:00:00+08:00")
    render = build_render_plan(approved, production_spec, assembly_mode="dry_run")
    return approved, render


def test_three_hour_visual_plan_is_deterministic_and_covers_target():
    approved, render = approved_inputs()
    first = build_visual_motion_plan(render, approved)
    second = build_visual_motion_plan(render, approved)
    assert first == second
    assert first["visual_plan_id"] == "VISPLAN-FLOW-000024"
    assert first["source_visual"]["asset_id"] == "VISUAL-FLOW-000024"
    assert first["target_duration_seconds"] == 10800
    assert first["planned_coverage_seconds"] >= first["target_duration_seconds"]
    assert first["execution_profile"]["width"] == 1920
    assert first["execution_profile"]["height"] == 1080
    assert first["execution_profile"]["fps"] == 30
    assert first["final_status"] == "VISUAL_PLAN_READY"
    phases = first["phases"]
    assert len(phases) > 1
    assert all(a["motif"] != b["motif"] for a, b in zip(phases, phases[1:]))
    assert first["execution_profile"]["crossfade_seconds"] < first["execution_profile"]["phase_seconds"]
    assert max(max(p["transform"]["scale_start"], p["transform"]["scale_end"]) for p in phases) <= 1.05


def test_product_profiles_remain_within_low_motion_bounds():
    for product, profile in MOTION_PROFILES.items():
        approved, render = approved_inputs(product=product, duration_minutes=20)
        plan = build_visual_motion_plan(render, approved)
        execution = plan["execution_profile"]
        assert execution["phase_seconds"] == profile["phase_seconds"]
        assert execution["max_scale"] == profile["max_scale"]
        assert 1.0 <= execution["max_scale"] <= 1.05
        assert execution["max_pan_x_fraction"] <= 0.03
        assert execution["max_pan_y_fraction"] <= 0.02
        assert plan["planned_coverage_seconds"] >= 1200


def test_visual_motion_preserves_source_hash_and_house_style():
    approved, render = approved_inputs()
    source = next(asset for asset in approved["assets"] if asset["asset_type"] == "visual")
    plan = build_visual_motion_plan(render, approved)
    assert plan["source_visual"]["content_hash"] == source["content_hash"]
    assert plan["source_visual"]["style_preset"] == "jeha_cinematic_dreamy_realism_v2"
    assert plan["source_bundle_hash"] == render["source_bundle_hash"]


def test_visual_motion_rejects_changed_bundle_after_m4_1():
    approved, render = approved_inputs()
    visual = next(asset for asset in approved["assets"] if asset["asset_type"] == "visual")
    visual["prompt_or_source"] = "changed after approval"
    with pytest.raises(ValueError, match="no longer matches"):
        build_visual_motion_plan(render, approved)


def test_visual_motion_rejects_non_16_9_master():
    approved, render = approved_inputs()
    visual = next(asset for asset in approved["assets"] if asset["asset_type"] == "visual")
    visual["technical"]["aspect_ratio"] = "1:1"
    from pipeline.assembly import asset_bundle_fingerprint
    render["source_bundle_hash"] = asset_bundle_fingerprint(approved)
    with pytest.raises(ValueError, match="16:9"):
        build_visual_motion_plan(render, approved)


def test_visual_motion_rejects_missing_house_style_lineage():
    approved, render = approved_inputs()
    visual = next(asset for asset in approved["assets"] if asset["asset_type"] == "visual")
    visual["technical"]["style_preset"] = "other_style"
    from pipeline.assembly import asset_bundle_fingerprint
    render["source_bundle_hash"] = asset_bundle_fingerprint(approved)
    with pytest.raises(ValueError, match="house-style"):
        build_visual_motion_plan(render, approved)


def test_visual_motion_rejects_invalid_dimensions():
    approved, render = approved_inputs()
    visual = next(asset for asset in approved["assets"] if asset["asset_type"] == "visual")
    visual["technical"]["width"] = 0
    from pipeline.assembly import asset_bundle_fingerprint
    render["source_bundle_hash"] = asset_bundle_fingerprint(approved)
    with pytest.raises(ValueError, match="visual width"):
        build_visual_motion_plan(render, approved)
