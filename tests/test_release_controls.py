from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.release_controls import build_release_configuration, validate_release_lineage


def fixture_inputs(tmp_path: Path) -> tuple[dict, dict]:
    upload = {
        "upload_record_id": "UPLOAD-FLOW-000024",
        "publish_plan_id": "PUBLISH-FLOW-000024",
        "metadata_package_id": "META-FLOW-000024",
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "source_video_id": "VIDEO-FLOW-000024",
        "source_package_hash": "sha256:" + "1" * 64,
        "source_master_hash": "sha256:" + "2" * 64,
        "platform": "youtube",
        "remote_video_id": "yt_fixture_private_000024",
        "visibility": "private",
        "uploaded_at": "2026-08-18T04:00:00+00:00",
        "mode": "fixture",
        "credential_trace": "fixture",
        "final_status": "PRIVATE_UPLOAD_COMPLETE",
    }
    metadata = {
        "metadata_package_id": "META-FLOW-000024",
        "publish_plan_id": "PUBLISH-FLOW-000024",
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "source_package_hash": "sha256:" + "1" * 64,
        "snippet": {
            "title": "Deep Focus Flow Room",
            "description": "JEHA companion audio.",
            "tags": ["focus", "ambient"],
            "categoryId": "10",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
        "constraints": {"title_chars": 20, "description_utf8_bytes": 21, "tags_accounted_chars": 13},
        "release_control": {"visibility_intent": "private_first", "public_release_allowed": False},
        "final_status": "METADATA_READY",
    }
    return upload, metadata


def test_private_configuration_is_deterministic_and_remote_write_disabled(tmp_path):
    upload, metadata = fixture_inputs(tmp_path)
    now = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)
    first = build_release_configuration(upload, metadata, now=now)
    second = build_release_configuration(upload, metadata, now=now)
    assert first == second
    assert first["control_id"] == "CONTROL-FLOW-000024"
    assert first["target_visibility"] == "private"
    assert first["schedule"]["enabled"] is False
    assert first["release_gate"]["remote_mutation_allowed"] is False
    assert first["release_gate"]["public_release_allowed"] is False
    assert first["release_gate"]["requires_m5_5_release_approval"] is False
    assert first["configuration_hash"].startswith("sha256:")


def test_future_public_schedule_is_planned_but_not_applied(tmp_path):
    upload, metadata = fixture_inputs(tmp_path)
    now = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)
    config = build_release_configuration(
        upload,
        metadata,
        target_visibility="public",
        publish_at="2026-08-19T12:30:00+08:00",
        now=now,
    )
    assert config["schedule"]["enabled"] is True
    assert config["schedule"]["publish_at"] == "2026-08-19T04:30:00+00:00"
    assert config["schedule"]["required_pre_schedule_privacy"] == "private"
    assert config["schedule"]["remote_write_allowed"] is False
    assert config["release_gate"]["requires_m5_5_release_approval"] is True


def test_past_schedule_and_non_public_schedule_are_rejected(tmp_path):
    upload, metadata = fixture_inputs(tmp_path)
    now = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="strictly in the future"):
        build_release_configuration(
            upload,
            metadata,
            target_visibility="public",
            publish_at="2026-08-18T03:59:59+00:00",
            now=now,
        )
    with pytest.raises(ValueError, match="only valid"):
        build_release_configuration(
            upload,
            metadata,
            target_visibility="unlisted",
            publish_at="2026-08-19T04:00:00+00:00",
            now=now,
        )


def test_lineage_and_private_remote_state_are_required(tmp_path):
    upload, metadata = fixture_inputs(tmp_path)
    upload["visibility"] = "public"
    with pytest.raises(ValueError, match="remain private"):
        validate_release_lineage(upload, metadata)

    upload, metadata = fixture_inputs(tmp_path)
    metadata["delivery_package_id"] = "DELIVERY-FLOW-999999"
    with pytest.raises(ValueError, match="lineage mismatch"):
        validate_release_lineage(upload, metadata)


def test_valid_png_thumbnail_is_hashed_and_never_remote_written(tmp_path):
    upload, metadata = fixture_inputs(tmp_path)
    thumb = tmp_path / "thumb.png"
    thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture-thumbnail")
    config = build_release_configuration(
        upload,
        metadata,
        thumbnail_path=thumb,
        now=datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc),
    )
    assert config["thumbnail"]["mime_type"] == "image/png"
    assert config["thumbnail"]["size_bytes"] == thumb.stat().st_size
    assert config["thumbnail"]["content_hash"].startswith("sha256:")
    assert config["thumbnail"]["remote_write_allowed"] is False


def test_invalid_thumbnail_type_or_size_is_rejected(tmp_path):
    upload, metadata = fixture_inputs(tmp_path)
    bad = tmp_path / "thumb.png"
    bad.write_bytes(b"not-a-real-png")
    with pytest.raises(ValueError, match="valid JPEG or PNG"):
        build_release_configuration(upload, metadata, thumbnail_path=bad)

    too_large = tmp_path / "huge.jpg"
    too_large.write_bytes(b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024))
    with pytest.raises(ValueError, match="exceeds 2 MB"):
        build_release_configuration(upload, metadata, thumbnail_path=too_large)
