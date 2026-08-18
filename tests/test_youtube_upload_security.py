from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pipeline.youtube_upload import YouTubeResumableTransport, run_private_upload


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _inputs(tmp_path: Path) -> tuple[dict, dict]:
    payload = b"master"
    path = tmp_path / "master.mp4"
    path.write_bytes(payload)
    publish = {
        "publish_plan_id": "PUBLISH-FLOW-000024",
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "source_package_hash": "sha256:" + "1" * 64,
        "master": {"artifact_path": str(path), "content_hash": _sha(payload)},
        "publish_intent": {"visibility": "private_first", "public_release_allowed": False},
        "final_status": "PUBLISH_PLAN_READY",
    }
    metadata = {
        "metadata_package_id": "META-FLOW-000024",
        "publish_plan_id": publish["publish_plan_id"],
        "delivery_package_id": publish["delivery_package_id"],
        "video_id": publish["video_id"],
        "topic_id": publish["topic_id"],
        "product": publish["product"],
        "source_package_hash": publish["source_package_hash"],
        "snippet": {"title": "title", "description": "description", "tags": [], "categoryId": "10", "defaultLanguage": "en"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
        "release_control": {"public_release_allowed": False},
        "final_status": "METADATA_READY",
    }
    return publish, metadata


class MissingPrivacyUploader:
    def upload(self, *, video_path, resource, access_token):
        return {"id": "remote-id", "status": {}}


class PublicUploader:
    def upload(self, *, video_path, resource, access_token):
        return {"id": "remote-id", "status": {"privacyStatus": "public"}}


def test_remote_response_must_explicitly_confirm_private(tmp_path):
    publish, metadata = _inputs(tmp_path)
    with pytest.raises(RuntimeError, match="explicitly confirm private"):
        run_private_upload(publish, metadata, uploader=MissingPrivacyUploader())
    with pytest.raises(RuntimeError, match="explicitly confirm private"):
        run_private_upload(publish, metadata, uploader=PublicUploader())


def test_resumable_chunk_size_must_follow_youtube_alignment():
    YouTubeResumableTransport(chunk_size=8 * 1024 * 1024)
    with pytest.raises(ValueError, match="multiple of 256 KiB"):
        YouTubeResumableTransport(chunk_size=1000)
