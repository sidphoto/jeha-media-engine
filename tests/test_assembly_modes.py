from __future__ import annotations

import copy

import pytest

from pipeline.assembly import approve_asset_bundle, build_render_plan
from pipeline.asset_generation import generate_asset_bundle


def spec():
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "Original focus ambience"},
        "visual": {"brief": "Rainy focus desk"},
        "metadata": {"tags": ["focus", "coding"]},
    }


def approved_fixture():
    bundle = generate_asset_bundle(spec(), mode="fixture", production_spec_ref="spec.json")
    return approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )


def test_fixture_bundle_is_only_ready_for_dry_run():
    approved = approved_fixture()
    dry_plan = build_render_plan(approved, spec(), assembly_mode="dry_run")
    assert dry_plan["assembly_mode"] == "dry_run"
    assert dry_plan["source_asset_mode"] == "fixture"
    with pytest.raises(ValueError, match="requires an M3 live asset bundle"):
        build_render_plan(approved, spec(), assembly_mode="production")


def test_invalid_assembly_mode_is_rejected():
    with pytest.raises(ValueError, match="assembly_mode"):
        build_render_plan(approved_fixture(), spec(), assembly_mode="publish")


def test_m4_rejects_bundle_when_any_m3_qa_result_failed():
    bundle = generate_asset_bundle(spec(), mode="fixture", production_spec_ref="spec.json")
    bundle["qa"][0]["passed"] = False
    with pytest.raises(ValueError, match="every M3 QA result"):
        approve_asset_bundle(
            bundle,
            approver="human-owner",
            approved_at="2026-08-18T12:00:00+08:00",
        )


def test_production_rejects_live_bundle_containing_fixture_provider():
    bundle = generate_asset_bundle(spec(), mode="fixture", production_spec_ref="spec.json")
    bundle["mode"] = "live"
    approved = approve_asset_bundle(
        bundle,
        approver="human-owner",
        approved_at="2026-08-18T12:00:00+08:00",
    )
    # This test documents the adversarial case: changing only the bundle mode must not
    # be sufficient to turn fixture assets into production assets.
    assert any(asset["provider"] == "jeha_fixture" for asset in approved["assets"])
    with pytest.raises(ValueError, match="fixture asset"):
        build_render_plan(approved, spec(), assembly_mode="production")
