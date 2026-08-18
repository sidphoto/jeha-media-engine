from __future__ import annotations

import copy

import pytest

from pipeline.assembly import approve_asset_bundle, asset_bundle_fingerprint, build_render_plan
from pipeline.asset_generation import generate_asset_bundle


def spec(tags=None):
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "Original focus ambience"},
        "visual": {"brief": "Rainy focus desk"},
        "metadata": {"tags": tags or ["focus", "coding"]},
    }


def fixture_bundle(tags=None):
    return generate_asset_bundle(spec(tags), mode="fixture", production_spec_ref="spec.json")


def test_approval_binds_exact_bundle_and_render_plan_is_deterministic():
    bundle = fixture_bundle()
    fingerprint = asset_bundle_fingerprint(bundle)
    approved = approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )

    assert approved["final_status"] == "APPROVED"
    assert approved["approval"]["asset_bundle_hash"] == fingerprint
    assert bundle["final_status"] == "AWAITING_APPROVAL"
    assert "approval" not in bundle

    first = build_render_plan(approved, spec())
    second = build_render_plan(approved, spec())
    assert first == second
    assert first["render_plan_id"] == "RENDER-FLOW-000024"
    assert first["video_id"] == "VIDEO-FLOW-000024"
    assert first["final_status"] == "READY_FOR_RENDER"
    assert first["source_bundle_hash"] == fingerprint
    assert first["lineage"]["music_id"] == "MUSIC-FLOW-000024"
    assert first["lineage"]["visual_id"] == "VISUAL-FLOW-000024"
    assert first["lineage"]["sfx_ids"] == []


def test_m4_rejects_unapproved_bundle():
    with pytest.raises(ValueError, match="APPROVED"):
        build_render_plan(fixture_bundle(), spec())


def test_m4_rejects_stale_approval_after_asset_change():
    approved = approve_asset_bundle(
        fixture_bundle(),
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    approved["assets"][0]["prompt_or_source"] = "changed after approval"
    with pytest.raises(ValueError, match="stale"):
        build_render_plan(approved, spec())


def test_m4_rejects_missing_required_asset_type():
    bundle = fixture_bundle()
    bundle["assets"] = [asset for asset in bundle["assets"] if asset["asset_type"] != "visual"]
    approved = approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    with pytest.raises(ValueError, match="MUSIC and VISUAL"):
        build_render_plan(approved, spec())


def test_m4_rejects_failed_asset_even_when_bundle_is_manually_tampered_to_pass():
    bundle = fixture_bundle()
    bundle["assets"][0]["qa_status"] = "failed"
    approved = approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    with pytest.raises(ValueError, match="did not pass M3 QA"):
        build_render_plan(approved, spec())


def test_m4_rejects_production_spec_topic_mismatch():
    approved = approve_asset_bundle(
        fixture_bundle(),
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    other = copy.deepcopy(spec())
    other["topic_id"] = "TOPIC-FLOW-000025"
    with pytest.raises(ValueError, match="topic lineage"):
        build_render_plan(approved, other)


def test_optional_sfx_is_preserved_in_render_lineage():
    rain_spec = spec(["focus", "rain"])
    bundle = generate_asset_bundle(rain_spec, mode="fixture", production_spec_ref="spec.json")
    approved = approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    plan = build_render_plan(approved, rain_spec)
    assert plan["lineage"]["sfx_ids"] == ["SFX-RAIN-000024"]


def test_approval_requires_human_identity_and_timestamp():
    bundle = fixture_bundle()
    with pytest.raises(ValueError, match="approver"):
        approve_asset_bundle(bundle, approver="", approved_at="2026-08-18T12:00:00+08:00")
    with pytest.raises(ValueError, match="approved_at"):
        approve_asset_bundle(bundle, approver="human-owner", approved_at="")
