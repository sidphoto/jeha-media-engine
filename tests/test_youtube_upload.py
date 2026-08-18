from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pipeline.youtube_upload import build_video_resource, run_private_upload, validate_upload_inputs


def sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def inputs(tmp_path: Path) -> tuple[dict, dict]:
    payload = b"private-upload-master"
    master = tmp_path / "VIDEO-FLOW-000024.mp4"
    master.write_bytes(payload)
    publish = {
        "publish_plan_id": "PUBLISH-FLOW-000024",
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "source_package_hash": "sha256:" + "1" * 64,
        "master": {"artifact_path": str(master), "content_hash": sha(payload)},
        "publish_intent": {
            "platform": "youtube",
            "visibility": "private_first",
            "upload_allowed": False,
            "public_release_allowed": False,
        },
        "mode": "dry_run",
        "final_status": "PUBLISH_PLAN_READY",
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
            "title": "Rainy Coding Room | Flow Room",
            "description": "calm focus ambience",
            "tags": ["coding", "rain"],
            "categoryId": "10",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
        "release_control": {"visibility_intent": "private_first", "public_release_allowed": False},
        "final_status": "METADATA_READY",
    }
    return publish, metadata


class CaptureUploader:
    def __init__(self):
        self.calls = []

    def upload(self, *, video_path, resource, access_token):
        self.calls.append((video_path, resource, access_token))
        return {"id": "remote-private-123", "status": {"privacyStatus": "private"}}


def test_fixture_upload_builds_private_request_and_preserves_lineage(tmp_path):
    publish, metadata = inputs(tmp_path)
    uploader = CaptureUploader()
    record = run_private_upload(
        publish,
        metadata,
        mode="fixture",
        uploader=uploader,
        uploaded_at="2026-08-18T12:00:00+08:00",
    )
    assert len(uploader.calls) == 1
    _, resource, _ = uploader.calls[0]
    assert resource["status"]["privacyStatus"] == "private"
    assert resource["snippet"]["title"] == metadata["snippet"]["title"]
    assert record["remote_video_id"] == "remote-private-123"
    assert record["source_video_id"] == publish["video_id"]
    assert record["source_package_hash"] == publish["source_package_hash"]
    assert record["source_master_hash"] == publish["master"]["content_hash"]
    assert record["visibility"] == "private"
    assert record["final_status"] == "PRIVATE_UPLOAD_COMPLETE"


def test_master_hash_tampering_is_rejected_before_uploader_call(tmp_path):
    publish, metadata = inputs(tmp_path)
    Path(publish["master"]["artifact_path"]).write_bytes(b"tampered")
    uploader = CaptureUploader()
    with pytest.raises(RuntimeError, match="hash mismatch"):
        run_private_upload(publish, metadata, uploader=uploader)
    assert uploader.calls == []


def test_lineage_or_visibility_mismatch_is_rejected(tmp_path):
    publish, metadata = inputs(tmp_path)
    metadata["topic_id"] = "TOPIC-FLOW-999999"
    with pytest.raises(ValueError, match="lineage mismatch"):
        validate_upload_inputs(publish, metadata)

    publish, metadata = inputs(tmp_path)
    metadata["status"]["privacyStatus"] = "public"
    with pytest.raises(ValueError, match="must be private"):
        validate_upload_inputs(publish, metadata)


def test_live_mode_requires_oauth_and_operator_ack_before_network(tmp_path, monkeypatch):
    publish, metadata = inputs(tmp_path)
    monkeypatch.delenv("YOUTUBE_OAUTH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("YOUTUBE_PRIVATE_UPLOAD_ACK", raising=False)
    uploader = CaptureUploader()
    with pytest.raises(RuntimeError) as exc:
        run_private_upload(publish, metadata, mode="live", uploader=uploader)
    message = str(exc.value)
    assert "YOUTUBE_OAUTH_ACCESS_TOKEN" in message
    assert "YOUTUBE_PRIVATE_UPLOAD_ACK" in message
    assert uploader.calls == []


def test_live_injected_uploader_never_receives_public_resource(tmp_path):
    publish, metadata = inputs(tmp_path)
    uploader = CaptureUploader()
    record = run_private_upload(
        publish,
        metadata,
        mode="live",
        uploader=uploader,
        access_token="secret-test-token",
        operator_ack=True,
        uploaded_at="2026-08-18T12:00:00+08:00",
    )
    _, resource, token = uploader.calls[0]
    assert token == "secret-test-token"
    assert resource["status"]["privacyStatus"] == "private"
    assert "secret-test-token" not in str(record)
    assert record["credential_trace"] == "oauth_access_token_from_runtime_secret"
