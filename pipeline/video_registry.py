"""M4.5 immutable final-video registry and delivery approval boundary."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def delivery_package_id(video_id: str) -> str:
    if not isinstance(video_id, str) or not video_id.startswith("VIDEO-"):
        raise ValueError("M4.5 requires a canonical VIDEO ID")
    return "DELIVERY-" + video_id.removeprefix("VIDEO-")


def verify_master_record(master_record: dict, qa_report: dict) -> Path:
    if master_record.get("final_status") != "MASTER_QA_PASSED":
        raise ValueError("M4.5 requires MASTER_QA_PASSED")
    if master_record.get("qa", {}).get("passed") is not True:
        raise ValueError("M4.5 requires passed embedded master QA")
    if qa_report.get("passed") is not True:
        raise ValueError("M4.5 requires a passed external QA report")
    if qa_report != master_record.get("qa"):
        raise ValueError("M4.5 QA report does not match the master record")

    path_value = master_record.get("artifact_path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("M4.5 master artifact_path is required")
    path = Path(path_value)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("M4.5 master file is missing or empty")
    actual = _sha256_file(path)
    if actual != master_record.get("content_hash"):
        raise RuntimeError("M4.5 master file hash mismatch")
    return path


def delivery_package_fingerprint(package: dict) -> str:
    subject = {key: value for key, value in package.items() if key not in {"package_hash", "final_status"}}
    return "sha256:" + hashlib.sha256(_canonical(subject)).hexdigest()


def build_delivery_package(master_record: dict, qa_report: dict, *, generated_at: str) -> dict:
    path = verify_master_record(master_record, qa_report)
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError("generated_at is required")

    package = {
        "delivery_package_id": delivery_package_id(master_record["video_id"]),
        "video_id": master_record["video_id"],
        "topic_id": master_record["topic_id"],
        "product": master_record["product"],
        "generated_at": generated_at,
        "master": {
            "artifact_path": str(path),
            "content_hash": master_record["content_hash"],
            "technical": master_record["technical"],
        },
        "lineage": {
            "render_plan_id": master_record["render_plan_id"],
            "audio_plan_id": master_record["audio_plan_id"],
            "visual_plan_id": master_record["visual_plan_id"],
            "source_bundle_hash": master_record["source_bundle_hash"],
        },
        "master_qa": qa_report,
        "delivery_state": "prepared_not_delivered",
    }
    package["package_hash"] = delivery_package_fingerprint(package)
    package["final_status"] = "AWAITING_DELIVERY_APPROVAL"
    return package


def run_video_registry(
    master_record_path: str | Path,
    qa_report_path: str | Path,
    run_id: str,
    *,
    generated_at: str | None = None,
) -> Path:
    master_record = json.loads(Path(master_record_path).read_text(encoding="utf-8"))
    qa_report = json.loads(Path(qa_report_path).read_text(encoding="utf-8"))
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    package = build_delivery_package(master_record, qa_report, generated_at=generated_at)

    schema = json.loads((ROOT / "schemas" / "delivery_package.schema.json").read_text(encoding="utf-8"))
    validate(package, schema)

    out = ROOT / "data" / "delivery_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "delivery_package.json", package)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M4.5",
            "delivery_package_id": package["delivery_package_id"],
            "video_id": package["video_id"],
            "package_hash": package["package_hash"],
            "final_status": package["final_status"],
        },
    )
    return out
