from __future__ import annotations

import copy

import pytest

from pipeline.assembly import approve_asset_bundle, build_render_plan
from pipeline.asset_generation import generate_asset_bundle
from pipeline.audio_plan import build_audio_plan


def spec(tags=None, product="flow_room", duration_minutes=180):
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": product,
        "duration_minutes": duration_minutes,
        "music": {"brief": "Original companion music"},
        "visual": {"brief": "Companion visual"},
        "metadata": {"tags": tags or ["focus", "coding"]},
    }


def approved_inputs(tags=None, product="flow_room", duration_minutes=180):
    production_spec = spec(tags, product=product, duration_minutes=duration_minutes)
    bundle = generate_asset_bundle(production_spec, mode="fixture", production_spec_ref="spec.json")
    approved = approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    render = build_render_plan(approved, production_spec, assembly_mode="dry_run")
    return production_spec, approved, render


def test_three_hour_music_plan_is_deterministic_and_covers_target():
    _, approved, render = approved_inputs()
    first = build_audio_plan(render, approved)
    second = build_audio_plan(render, approved)
    assert first == second
    assert first["audio_plan_id"] == "AUDIO-FLOW-000024"
    assert first["target_duration_seconds"] == 10800
    assert first["music"]["strategy"] == "section_cycle_crossfade"
    assert first["music"]["planned_coverage_seconds"] >= 10800
    assert first["music"]["source_asset_id"] == "MUSIC-FLOW-000024"
    assert first["mix"]["integrated_loudness_target_lufs"] == -16.0
    assert first["mix"]["true_peak_ceiling_dbtp"] == -1.5
    assert first["final_status"] == "AUDIO_PLAN_READY"
    segments = first["music"]["segments"]
    assert len(segments) > 1
    assert all(a["section_id"] != b["section_id"] for a, b in zip(segments, segments[1:]))
    assert first["music"]["crossfade_seconds"] < min(
        segment["source_end_seconds"] - segment["source_start_seconds"] for segment in segments
    )


def test_master_longer_than_program_uses_trim_only():
    _, approved, render = approved_inputs(duration_minutes=10)
    music = next(asset for asset in approved["assets"] if asset["asset_type"] == "music")
    # Fixture M3 music duration follows program duration; extend source to make trim path explicit.
    music["technical"]["duration_seconds"] = 900
    # Re-approve because approval is intentionally invalidated by asset changes.
    source_bundle = copy.deepcopy(approved)
    source_bundle.pop("approval")
    source_bundle["final_status"] = "AWAITING_APPROVAL"
    source_bundle["assets"] = approved["assets"]
    reapproved = approve_asset_bundle(
        source_bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:01:00+08:00",
    )
    rerender = build_render_plan(reapproved, spec(duration_minutes=10), assembly_mode="dry_run")
    plan = build_audio_plan(rerender, reapproved)
    assert plan["music"]["strategy"] == "trim_only"
    assert len(plan["music"]["segments"]) == 1
    assert plan["music"]["planned_coverage_seconds"] == 600


def test_sfx_gets_independent_crossfade_schedule_and_lineage():
    _, approved, render = approved_inputs(["focus", "rain"])
    plan = build_audio_plan(render, approved)
    assert len(plan["sfx_tracks"]) == 1
    sfx = plan["sfx_tracks"][0]
    assert sfx["source_asset_id"] == "SFX-RAIN-000024"
    assert sfx["planned_coverage_seconds"] >= plan["target_duration_seconds"]
    assert sfx["crossfade_seconds"] > 0
    assert plan["mix"]["sfx_gain_db"] == -14.0
    music_boundaries = {segment["timeline_start_seconds"] for segment in plan["music"]["segments"][1:]}
    sfx_boundaries = {segment["timeline_start_seconds"] for segment in sfx["segments"][1:]}
    assert music_boundaries != sfx_boundaries
    assert plan["provenance"]["audio_asset_hashes"][sfx["source_asset_id"]] == sfx["source_content_hash"]


def test_product_loudness_targets_are_internal_jeha_targets():
    for product, expected in (("flow_room", -16.0), ("cozy_room", -16.0), ("moon_room", -18.0), ("nature_room", -18.0)):
        production_spec = spec(product=product)
        production_spec["topic_id"] = f"TOPIC-{product.upper()}-000024"
        bundle = generate_asset_bundle(production_spec, mode="fixture", production_spec_ref="spec.json")
        approved = approve_asset_bundle(bundle, approver="human-owner", approved_at="2026-08-18T12:00:00+08:00")
        render = build_render_plan(approved, production_spec, assembly_mode="dry_run")
        plan = build_audio_plan(render, approved)
        assert plan["mix"]["integrated_loudness_target_lufs"] == expected
        assert plan["mix"]["target_basis"] == "JEHA internal production target"


def test_audio_plan_rejects_changed_bundle_after_render_approval():
    _, approved, render = approved_inputs()
    approved["assets"][0]["prompt_or_source"] = "changed after M4.1"
    with pytest.raises(ValueError, match="no longer matches"):
        build_audio_plan(render, approved)


def test_audio_plan_rejects_missing_or_invalid_music_duration():
    _, approved, render = approved_inputs()
    music = next(asset for asset in approved["assets"] if asset["asset_type"] == "music")
    music["technical"]["duration_seconds"] = 0
    # Make render-plan bundle hash match so duration validation is the exercised failure.
    from pipeline.assembly import asset_bundle_fingerprint
    render["source_bundle_hash"] = asset_bundle_fingerprint(approved)
    with pytest.raises(ValueError, match="music duration_seconds"):
        build_audio_plan(render, approved)


def test_audio_plan_rejects_bad_content_hash():
    _, approved, render = approved_inputs()
    music = next(asset for asset in approved["assets"] if asset["asset_type"] == "music")
    music["content_hash"] = "not-a-hash"
    from pipeline.assembly import asset_bundle_fingerprint
    render["source_bundle_hash"] = asset_bundle_fingerprint(approved)
    with pytest.raises(ValueError, match="SHA-256"):
        build_audio_plan(render, approved)
