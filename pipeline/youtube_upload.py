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

from jsonschema import validate

from pipeline.security import load_json_validated, safe_run_dir, validate_https_host

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
YOUTUBE_UPLOAD_HOSTS = frozenset({"www.googleapis.com"})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    """Upload in resumable-session chunks so long JEHA masters are not buffered in memory."""

    def __init__(self, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        if chunk_size <= 0 or chunk_size % (256 * 1024) != 0:
            raise ValueError("YouTube upload chunk_size must be a positive multiple of 256 KiB")
        self.chunk_size = chunk_size

    def _connection(self, url: str) -> tuple[http.client.HTTPSConnection, str]:
        validate_https_host(
            url,
            exact_hosts=YOUTUBE_UPLOAD_HOSTS,
            label="YouTube resumable upload",
        )
        parsed = urlparse(url)
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        return http.client.HTTPSConnection(parsed.hostname, 443, timeout=180), target

    def _put_chunk(self, location: str, access_token: str, chunk: bytes, start: int, total: int) -> tuple[int, dict[str, str], bytes]:
        end = start + len(chunk) - 1
        conn, target = self._connection(location)
        conn.putrequest("PUT", target)
        conn.putheader("Authorization", f"Bearer {access_token}")
        conn.putheader("Content-Type", "video/mp4")
        conn.putheader("Content-Length", str(len(chunk)))
        conn.putheader("Content-Range", f"bytes {start}-{end}/{total}")
        conn.endheaders()
        conn.send(chunk)
        response = conn.getresponse()
        payload = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        conn.close()
        return status, headers, payload

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

        # Validate the server-supplied session URL before the OAuth token is ever attached
        # to a subsequent PUT request. The official protocol currently returns the same
        # www.googleapis.com authority for the resumable session URI.
        validate_https_host(
            location,
            exact_hosts=YOUTUBE_UPLOAD_HOSTS,
            label="YouTube resumable session",
        )

        offset = 0
        with video_path.open("rb") as handle:
            while offset < size:
                handle.seek(offset)
                chunk = handle.read(min(self.chunk_size, size - offset))
                if not chunk:
                    raise RuntimeError("YouTube upload encountered an unexpected empty source chunk")
                upload_status, headers, payload = self._put_chunk(location, access_token, chunk, offset, size)
                if upload_status == 308:
                    range_value = headers.get("range")
                    if range_value and "-" in range_value:
                        acknowledged = int(range_value.rsplit("-", 1)[1]) + 1
                        if acknowledged <= offset or acknowledged > size:
                            raise RuntimeError("YouTube resumable upload returned an invalid acknowledged range")
                        offset = acknowledged
                    else:
                        offset += len(chunk)
                    continue
                if upload_status not in {200, 201}:
                    raise RuntimeError(f"YouTube upload failed: HTTP {upload_status}")
                parsed = json.loads(payload.decode("utf-8")) if payload else {}
                if not parsed.get("id"):
                    raise RuntimeError("YouTube upload response did not contain a video id")
                return parsed
        raise RuntimeError("YouTube resumable upload ended without a completion response")


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
    remote_privacy = response.get("status", {}).get("privacyStatus")
    if not remote_id:
        raise RuntimeError("M5.3 uploader returned no remote video id")
    if remote_privacy != "private":
        raise RuntimeError("M5.3 uploader did not explicitly confirm private visibility")

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


def run_upload_pipeline(
    publish_plan_path: str | Path,
    metadata_path: str | Path,
    run_id: str,
    *,
    mode: str = "fixture",
) -> Path:
    publish_plan = load_json_validated(
        publish_plan_path,
        ROOT / "schemas" / "publish_plan.schema.json",
        label="M5.3 publish plan",
    )
    metadata = load_json_validated(
        metadata_path,
        ROOT / "schemas" / "youtube_metadata.schema.json",
        label="M5.3 YouTube metadata",
    )
    record = run_private_upload(publish_plan, metadata, mode=mode)
    schema = json.loads((ROOT / "schemas" / "youtube_upload_record.schema.json").read_text(encoding="utf-8"))
    validate(record, schema)

    out = safe_run_dir(ROOT, "upload_runs", run_id)
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "upload_record.json", record)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M5.3",
            "upload_record_id": record["upload_record_id"],
            "remote_video_id": record["remote_video_id"],
            "visibility": record["visibility"],
            "mode": record["mode"],
            "final_status": record["final_status"],
        },
    )
    return out
