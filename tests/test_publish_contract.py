from __future__ import annotations

import copy

import pytest

from pipeline.publish_contract import attach_delivery_approval, build_publish_plan
from pipeline.video_registry import delivery_package_fingerprint


def package() -> dict:
    value = {
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "generated_at": "2026-08-18T12:00:00+08:00",
        "master": {
            "artifact_path": "data/video_runs/demo/VIDEO-FLOW-000024.mp4",
            "content_hash": "sha256:" + "1" * 64,
            "technical": {"container": "mp4", "width": 1920, "height": 1080},
        },
        "lineage": {
            "render_plan_id": "RENDER-FLOW-000024",
            "audio_plan_id": "AUDIO-FLOW-000024",
            "visual_plan_id": "VISPLAN-FLOW-000024",
            "source_bundle_hash": "sha256:" + "2" * 64,
        },
        "master_qa": {"passed": True},
        "delivery_state": "prepared_not_delivered",
        "final_status": "AWAITING_DELIVERY_APPROVAL",
    }
    value["package_hash"] = delivery_package_fingerprint(value)
    return value


def approval(value: dict) -> dict:
    return {
        "decision": "approved",
        "approver": "human",
        "approved_at": "2026-08-18T12:30:00+08:00",
        "package_hash": value["package_hash"],
    }


def test_exact_delivery_approval_builds_private_first_publish_plan():
    value = package()
    approved = attach_delivery_approval(value, approval(value))
    plan = build_publish_plan(approved)
    assert plan["publish_plan_id"] == "PUBLISH-FLOW-000024"
    assert plan["source_package_hash"] == value["package_hash"]
    assert plan["publish_intent"] == {
        "platform": "youtube",
        "visibility": "private_first",
        "upload_allowed": False,
        "public_release_allowed": False,
    }
    assert plan["mode"] == "dry_run"
    assert plan["final_status"] == "PUBLISH_PLAN_READY"


def test_stale_approval_is_rejected_after_package_change():
    value = package()
    stale = approval(value)
    changed = copy.deepcopy(value)
    changed["master"]["artifact_path"] = "different.mp4"
    with pytest.raises(ValueError, match="stale or invalid"):
        attach_delivery_approval(changed, stale)


def test_publish_plan_detects_change_after_approval():
    value = package()
    approved = attach_delivery_approval(value, approval(value))
    approved["master"]["artifact_path"] = "changed-after-approval.mp4"
    with pytest.raises(ValueError, match="changed after delivery approval"):
        build_publish_plan(approved)


def test_m51_cannot_enable_upload_or_live_mode():
    value = package()
    approved = attach_delivery_approval(value, approval(value))
    with pytest.raises(ValueError, match="dry_run"):
        build_publish_plan(approved, mode="live")
