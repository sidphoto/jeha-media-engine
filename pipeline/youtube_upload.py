"""M5.3 private-first YouTube upload adapter.

CI uses an injected/fixture uploader only. The default live transport implements the
YouTube resumable-session protocol but is unreachable unless both OAuth and explicit
private-upload acknowledgement are present.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode, urlparse

UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def validate_upload_inputs(publish_plan: dict, metadata: dict) -> Path:
    if publish_plan.get("final_status") != "PUBLISH_PLAN_READY":
        raise ValueError("M5.3 requires PUBLISH_PLAN_READY")
    if metadata.get("final_status") != "METADATA_READY":
        raise ValueError("M5.3 requires METADATA_READY")
    for field in ("video_id", "topic_id", "product", "delivery_package_id", "source_package_hash"):
        if publish_plan.get(field) != metadata.get(field):
            raise ValueError(f"M5.3 lineage mismatch: {field}")
    if metadata.get("publish_plan_id") != publish_plan.get("publish_plan_id"):
        raise ValueError("M5.3 publish_plan_id mismatch")
    if publish_plan.get("publish_intent", {}).get("visibility") != "private_first":
        raise ValueError("M5.3 requires private-first publish intent")
    if publish_plan.get("publish_intent", {}).get("public_release_allowed") is not False:
        raise ValueError("M5.3 public release must remain disabled")
    if metadata.get("status", {}).get("privacyStatus") != "private":
        raise ValueError("M5.3 upload metadata must be private")
    if metadata.get("release_control", {}).get("public_release_allowed") is not False:
        raise ValueError("M5.3 metadata cannot allow public release")

    master = publish_plan.get("master", {})
    path_value = master.get("artifact_path")
    expected_hash = master.get("content_hash")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("M5.3 master artifact_path is required")
    path = Path(path_value)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("M5.3 master file is missing or empty")
    if _sha256_file(path) != expected_hash:
        raise RuntimeError("M5.3 master file hash mismatch")
    return path


def build_video_resource(metadata: dict) -> dict:
    status = dict(metadata["status"])
    status["privacyStatus"] = "private"
    return {"snippet": dict(metadata["snippet"]), "status": status}


class UploadTransport(Protocol):
    def upload(self, *, video_path: Path, resource: dict, access_token: str) -> dict: ...


class FixtureYouTubeUploader:
    def upload(self, *, video_path: Path, resource: dict, access_token: str) -> dict:
        assert resource["status"]["privacyStatus"] == "private"
        return {
            "id": "yt_fixture_private_000024",
            "status": {"privacyStatus": "private"},
            "snippet": {"title": resource["snippet"]["title"]},
        }


class YouTubeResumableTransport:
    """Stream one file through an official resumable upload session without buffering it all."""

    def _connection(self, url: str) -> tuple[http.client.HTTPSConnection, str]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise RuntimeError("YouTube upload URL must be HTTPS")
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        return http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=180), target

    def upload(self, *, video_path: Path, resource: dict, access_token: str) -> dict:
        size = video_path.stat().st_size
        query = urlencode({"uploadType": "resumable", "part": "snippet,status"})
        init_url = UPLOAD_ENDPOINT + "?" + query
        body = json.dumps(resource, ensure_ascii=False).encode("utf-8")
        conn, target = self._connection(init_url)
        conn.request(
            "POST",
            target,
            body=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "Content-Length": str(len(body)),
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": "video/mp4",
            },
        )
        response = conn.getresponse()
        response.read()
        location = response.getheader("Location")
        status = response.status
        conn.close()
        if status not in {200, 201} or not location:
            raise RuntimeError(f"YouTube resumable session initiation failed: HTTP {status}")

        upload_conn, upload_target = self._connection(location)
        upload_conn.putrequest("PUT", upload_target)
        upload_conn.putheader("Authorization", f"Bearer {access_token}")
        upload_conn.putheader("Content-Type", "video/mp4")
        upload_conn.putheader("Content-Length", str(size))
        upload_conn.putheader("Content-Range", f"bytes 0-{size - 1}/{size}")
        upload_conn.endheaders()
        with video_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                upload_conn.send(chunk)
        upload_response = upload_conn.getresponse()
        payload = upload_response.read()
        upload_status = upload_response.status
        upload_conn.close()
        if upload_status not in {200, 201}:
            raise RuntimeError(f"YouTube upload failed: HTTP {upload_status}")
        parsed = json.loads(payload.decode("utf-8")) if payload else {}
        if not parsed.get("id"):
            raise RuntimeError("YouTube upload response did not contain a video id")
        return parsed


def run_private_upload(
    publish_plan: dict,
    metadata: dict,
    *,
    mode: str = "fixture",
    uploader: UploadTransport | None = None,
    access_token: str | None = None,
    operator_ack: bool | None = None,
    uploaded_at: str | None = None,
) -> dict:
    video_path = validate_upload_inputs(publish_plan, metadata)
    resource = build_video_resource(metadata)

    if mode == "fixture":
        if uploader is None:
            uploader = FixtureYouTubeUploader()
        token = "fixture-token-not-secret"
    elif mode == "live":
        if uploader is None:
            uploader = YouTubeResumableTransport()
        token = access_token or os.getenv("YOUTUBE_OAUTH_ACCESS_TOKEN")
        if operator_ack is None:
            operator_ack = os.getenv("YOUTUBE_PRIVATE_UPLOAD_ACK", "").lower() in {"1", "true", "yes"}
        errors: list[str] = []
        if not token:
            errors.append("YOUTUBE_OAUTH_ACCESS_TOKEN is required")
        if not operator_ack:
            errors.append("YOUTUBE_PRIVATE_UPLOAD_ACK=true is required for an external private upload")
        if errors:
            raise RuntimeError("M5.3 live upload preflight failed: " + "; ".join(errors))
    else:
        raise ValueError("M5.3 mode must be fixture or live")

    response = uploader.upload(video_path=video_path, resource=resource, access_token=token)
    remote_id = response.get("id")
    remote_privacy = response.get("status", {}).get("privacyStatus", "private")
    if not remote_id:
        raise RuntimeError("M5.3 uploader returned no remote video id")
    if remote_privacy != "private":
        raise RuntimeError("M5.3 uploader returned non-private visibility")

    return {
        "upload_record_id": "UPLOAD-" + publish_plan["video_id"].removeprefix("VIDEO-"),
        "publish_plan_id": publish_plan["publish_plan_id"],
        "metadata_package_id": metadata["metadata_package_id"],
        "delivery_package_id": publish_plan["delivery_package_id"],
        "source_video_id": publish_plan["video_id"],
        "source_package_hash": publish_plan["source_package_hash"],
        "source_master_hash": publish_plan["master"]["content_hash"],
        "platform": "youtube",
        "remote_video_id": remote_id,
        "visibility": "private",
        "uploaded_at": uploaded_at or datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "credential_trace": "oauth_access_token_from_runtime_secret" if mode == "live" else "fixture",
        "final_status": "PRIVATE_UPLOAD_COMPLETE",
    }
