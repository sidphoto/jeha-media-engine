from __future__ import annotations

import copy

import pytest

from pipeline.release_registry import (
    attach_release_approval,
    build_release_record,
    release_configuration_fingerprint,
)


def configuration(target_visibility: str = "public", scheduled: bool = False) -> dict:
    value = {
        "control_id": "CONTROL-FLOW-000024",
        "upload_record_id": "UPLOAD-FLOW-000024",
        "remote_video_id": "yt_fixture_private_000024",
        "publish_plan_id": "PUBLISH-FLOW-000024",
        "metadata_package_id": "META-FLOW-000024",
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "source_package_hash": "sha256:" + "1" * 64,
        "source_master_hash": "sha256:" + "2" * 64,
        "current_remote_visibility": "private",
        "target_visibility": target_visibility,
        "schedule": {
            "enabled": scheduled,
            "publish_at": "2026-08-20T04:00:00+00:00" if scheduled else None,
            "required_pre_schedule_privacy": "private",
            "remote_write_allowed": False,
        },
        "thumbnail": None,
        "release_gate": {
            "public_release_allowed": False,
            "remote_mutation_allowed": False,
            "requires_m5_5_release_approval": target_visibility != "private",
        },
        "final_status": "RELEASE_CONFIGURATION_READY",
    }
    value["configuration_hash"] = release_configuration_fingerprint(value)
    return value


def approval(value: dict) -> dict:
    return {
        "decision": "approved",
        "approver": "human-chairman",
        "approved_at": "2026-08-18T12:50:00+08:00",
        "configuration_hash": value["configuration_hash"],
    }


def test_exact_approval_builds_remote_execution_manifest():
    value = configuration("public")
    approved = attach_release_approval(value, approval(value))
    record = build_release_record(approved)
    assert record["release_record_id"] == "RELEASE-FLOW-000024"
    assert record["release_action"] == "publish_public"
    assert record["remote_execution_required"] is True
    assert record["remote_execution_allowed"] is False
    assert record["credential_material_persisted"] is False
    assert record["final_status"] == "RELEASE_EXECUTION_APPROVED"
    assert record["source_configuration_hash"] == value["configuration_hash"]


def test_scheduled_public_release_has_distinct_action():
    value = configuration("public", scheduled=True)
    approved = attach_release_approval(value, approval(value))
    record = build_release_record(approved)
    assert record["release_action"] == "schedule_public_release"
    assert record["schedule"]["enabled"] is True


def test_private_noop_can_finalize_registry_without_remote_execution():
    value = configuration("private")
    approved = attach_release_approval(value, approval(value))
    record = build_release_record(approved)
    assert record["release_action"] == "remain_private"
    assert record["remote_execution_required"] is False
    assert record["final_status"] == "RELEASE_REGISTRY_FINALIZED_PRIVATE"


def test_thumbnail_only_private_still_requires_remote_execution():
    value = configuration("private")
    value["thumbnail"] = {
        "path": "/tmp/thumb.png",
        "mime_type": "image/png",
        "size_bytes": 10,
        "content_hash": "sha256:" + "3" * 64,
        "remote_write_allowed": False,
    }
    value["configuration_hash"] = release_configuration_fingerprint(value)
    approved = attach_release_approval(value, approval(value))
    record = build_release_record(approved)
    assert record["release_action"] == "apply_thumbnail_private"
    assert record["remote_execution_required"] is True


def test_stale_approval_is_rejected_after_configuration_mutation():
    value = configuration("public")
    old_approval = approval(value)
    changed = copy.deepcopy(value)
    changed["target_visibility"] = "unlisted"
    changed["configuration_hash"] = release_configuration_fingerprint(changed)
    with pytest.raises(ValueError, match="does not match"):
        attach_release_approval(changed, old_approval)


def test_mutation_after_approval_invalidates_release_record():
    value = configuration("public")
    approved = attach_release_approval(value, approval(value))
    approved["schedule"]["enabled"] = True
    approved["schedule"]["publish_at"] = "2026-08-20T04:00:00+00:00"
    with pytest.raises(ValueError, match="changed after release approval"):
        build_release_record(approved)


def test_missing_or_nonapproved_decision_is_rejected():
    value = configuration("public")
    with pytest.raises(ValueError, match="approved human release decision"):
        attach_release_approval(value, {"decision": "rejected"})
