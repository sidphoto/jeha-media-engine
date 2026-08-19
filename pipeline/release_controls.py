"""M5.4 deterministic thumbnail, schedule and visibility control planning.

This module performs no remote YouTube mutation. It only validates and freezes a
release configuration for a private M5.3 upload so M5.5 can apply a separate human
release gate later.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import validate

from pipeline.security import safe_run_dir

ROOT = Path(__file__).resolve().parents[1]
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_time(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"M5.4 {field} is required")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"M5.4 {field} must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"M5.4 {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _thumbnail_info(path_value: str | Path) -> dict:
    path = Path(path_value)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("M5.4 thumbnail file is missing or empty")
    size = path.stat().st_size
    if size > MAX_THUMBNAIL_BYTES:
        raise ValueError("M5.4 thumbnail exceeds 2 MB")

    head = path.read_bytes()[:16]
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"} and head.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif suffix == ".png" and head.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    else:
        raise ValueError("M5.4 thumbnail must be a valid JPEG or PNG")

    return {
        "path": str(path),
        "mime_type": mime,
        "size_bytes": size,
        "content_hash": _sha256_file(path),
        "remote_write_allowed": False,
    }


def validate_release_lineage(upload_record: dict, metadata: dict) -> None:
    if upload_record.get("final_status") != "PRIVATE_UPLOAD_COMPLETE":
        raise ValueError("M5.4 requires PRIVATE_UPLOAD_COMPLETE")
    if upload_record.get("visibility") != "private":
        raise ValueError("M5.4 requires the remote upload to remain private")
    if metadata.get("final_status") != "METADATA_READY":
        raise ValueError("M5.4 requires METADATA_READY")
    if metadata.get("status", {}).get("privacyStatus") != "private":
        raise ValueError("M5.4 metadata must remain private")
    if metadata.get("release_control", {}).get("public_release_allowed") is not False:
        raise ValueError("M5.4 cannot consume metadata that allows public release")

    comparisons = {
        "publish_plan_id": (upload_record.get("publish_plan_id"), metadata.get("publish_plan_id")),
        "metadata_package_id": (upload_record.get("metadata_package_id"), metadata.get("metadata_package_id")),
        "delivery_package_id": (upload_record.get("delivery_package_id"), metadata.get("delivery_package_id")),
        "video_id": (upload_record.get("source_video_id"), metadata.get("video_id")),
        "source_package_hash": (upload_record.get("source_package_hash"), metadata.get("source_package_hash")),
    }
    for field, (left, right) in comparisons.items():
        if left != right:
            raise ValueError(f"M5.4 lineage mismatch: {field}")


def build_release_configuration(
    upload_record: dict,
    metadata: dict,
    *,
    target_visibility: str = "private",
    publish_at: str | None = None,
    thumbnail_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict:
    validate_release_lineage(upload_record, metadata)
    if target_visibility not in {"private", "unlisted", "public"}:
        raise ValueError("M5.4 target_visibility must be private, unlisted, or public")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("M5.4 now must be timezone-aware")
    current = current.astimezone(timezone.utc)

    schedule: dict = {
        "enabled": False,
        "publish_at": None,
        "required_pre_schedule_privacy": "private",
        "remote_write_allowed": False,
    }
    if publish_at is not None:
        if target_visibility != "public":
            raise ValueError("M5.4 publishAt is only valid for a future public-release intent")
        scheduled = _parse_time(publish_at, field="publish_at")
        if scheduled <= current:
            raise ValueError("M5.4 publish_at must be strictly in the future")
        schedule.update({"enabled": True, "publish_at": scheduled.isoformat()})

    thumbnail = None if thumbnail_path is None else _thumbnail_info(thumbnail_path)
    control_id = "CONTROL-" + upload_record["source_video_id"].removeprefix("VIDEO-")
    base = {
        "control_id": control_id,
        "upload_record_id": upload_record["upload_record_id"],
        "remote_video_id": upload_record["remote_video_id"],
        "publish_plan_id": upload_record["publish_plan_id"],
        "metadata_package_id": upload_record["metadata_package_id"],
        "delivery_package_id": upload_record["delivery_package_id"],
        "video_id": upload_record["source_video_id"],
        "topic_id": metadata["topic_id"],
        "product": metadata["product"],
        "source_package_hash": upload_record["source_package_hash"],
        "source_master_hash": upload_record["source_master_hash"],
        "current_remote_visibility": "private",
        "target_visibility": target_visibility,
        "schedule": schedule,
        "thumbnail": thumbnail,
        "release_gate": {
            "public_release_allowed": False,
            "remote_mutation_allowed": False,
            "requires_m5_5_release_approval": target_visibility != "private",
        },
        "final_status": "RELEASE_CONFIGURATION_READY",
    }
    base["configuration_hash"] = _canonical_hash(base)
    return base


def run_release_configuration(
    upload_record_path: str | Path,
    metadata_path: str | Path,
    run_id: str,
    *,
    target_visibility: str = "private",
    publish_at: str | None = None,
    thumbnail_path: str | Path | None = None,
) -> Path:
    out = safe_run_dir(ROOT, "release_control_runs", run_id)
    upload_record = json.loads(Path(upload_record_path).read_text(encoding="utf-8"))
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    config = build_release_configuration(
        upload_record,
        metadata,
        target_visibility=target_visibility,
        publish_at=publish_at,
        thumbnail_path=thumbnail_path,
    )
    schema = json.loads((ROOT / "schemas" / "release_configuration.schema.json").read_text(encoding="utf-8"))
    validate(config, schema)

    out.mkdir(parents=True, exist_ok=False)
    _write(out / "release_configuration.json", config)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M5.4",
            "control_id": config["control_id"],
            "remote_video_id": config["remote_video_id"],
            "target_visibility": config["target_visibility"],
            "schedule_enabled": config["schedule"]["enabled"],
            "has_thumbnail": config["thumbnail"] is not None,
            "final_status": config["final_status"],
        },
    )
    return out
