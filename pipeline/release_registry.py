"""M5.5 approval-bound final release registry.

This stage binds a human release decision to the exact immutable M5.4 configuration.
It never calls YouTube. Remote execution is a later runtime action requiring credentials
and a separate operator acknowledgement.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def release_configuration_fingerprint(configuration: dict) -> str:
    """Fingerprint the underlying M5.4 configuration, excluding the M5.5 approval envelope."""
    payload = copy.deepcopy(configuration)
    payload.pop("configuration_hash", None)
    payload.pop("release_approval", None)
    if payload.get("final_status") == "RELEASE_APPROVED":
        payload["final_status"] = "RELEASE_CONFIGURATION_READY"
    return _canonical_hash(payload)


def validate_release_configuration(configuration: dict) -> str:
    if configuration.get("final_status") != "RELEASE_CONFIGURATION_READY":
        raise ValueError("M5.5 requires RELEASE_CONFIGURATION_READY")
    expected = release_configuration_fingerprint(configuration)
    if configuration.get("configuration_hash") != expected:
        raise ValueError("M5.5 release configuration hash is stale or invalid")
    gate = configuration.get("release_gate", {})
    if gate.get("public_release_allowed") is not False:
        raise ValueError("M5.5 requires an unreleased configuration")
    if gate.get("remote_mutation_allowed") is not False:
        raise ValueError("M5.5 requires remote mutation to remain disabled before approval")
    return expected


def attach_release_approval(configuration: dict, approval: dict) -> dict:
    expected = validate_release_configuration(configuration)
    if not isinstance(approval, dict) or approval.get("decision") != "approved":
        raise ValueError("M5.5 requires an approved human release decision")
    for field in ("approver", "approved_at", "configuration_hash"):
        value = approval.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"release approval {field} is required")
    if approval["configuration_hash"] != expected:
        raise ValueError("M5.5 release approval does not match the current configuration")

    approved = copy.deepcopy(configuration)
    approved["release_approval"] = copy.deepcopy(approval)
    approved["final_status"] = "RELEASE_APPROVED"
    return approved


def release_record_id(video_id: str) -> str:
    if not isinstance(video_id, str) or not video_id.startswith("VIDEO-"):
        raise ValueError("M5.5 requires canonical VIDEO ID")
    return "RELEASE-" + video_id.removeprefix("VIDEO-")


def build_release_record(approved_configuration: dict) -> dict:
    if approved_configuration.get("final_status") != "RELEASE_APPROVED":
        raise ValueError("M5.5 requires RELEASE_APPROVED configuration")
    approval = approved_configuration.get("release_approval")
    if not isinstance(approval, dict) or approval.get("decision") != "approved":
        raise ValueError("M5.5 requires release approval metadata")

    expected = release_configuration_fingerprint(approved_configuration)
    if approved_configuration.get("configuration_hash") != expected:
        raise ValueError("M5.5 approved configuration changed after release approval")
    if approval.get("configuration_hash") != expected:
        raise ValueError("M5.5 release approval is stale")

    target_visibility = approved_configuration["target_visibility"]
    schedule = copy.deepcopy(approved_configuration["schedule"])
    thumbnail = copy.deepcopy(approved_configuration["thumbnail"])
    remote_execution_required = target_visibility != "private" or schedule["enabled"] or thumbnail is not None

    action = "remain_private"
    if schedule["enabled"]:
        action = "schedule_public_release"
    elif target_visibility == "public":
        action = "publish_public"
    elif target_visibility == "unlisted":
        action = "switch_unlisted"
    elif thumbnail is not None:
        action = "apply_thumbnail_private"

    base = {
        "release_record_id": release_record_id(approved_configuration["video_id"]),
        "control_id": approved_configuration["control_id"],
        "upload_record_id": approved_configuration["upload_record_id"],
        "remote_video_id": approved_configuration["remote_video_id"],
        "publish_plan_id": approved_configuration["publish_plan_id"],
        "metadata_package_id": approved_configuration["metadata_package_id"],
        "delivery_package_id": approved_configuration["delivery_package_id"],
        "video_id": approved_configuration["video_id"],
        "topic_id": approved_configuration["topic_id"],
        "product": approved_configuration["product"],
        "source_package_hash": approved_configuration["source_package_hash"],
        "source_master_hash": approved_configuration["source_master_hash"],
        "source_configuration_hash": expected,
        "release_approval": copy.deepcopy(approval),
        "target_visibility": target_visibility,
        "schedule": schedule,
        "thumbnail": thumbnail,
        "release_action": action,
        "remote_execution_required": remote_execution_required,
        "remote_execution_allowed": False,
        "credential_material_persisted": False,
        "final_status": "RELEASE_EXECUTION_APPROVED" if remote_execution_required else "RELEASE_REGISTRY_FINALIZED_PRIVATE",
    }
    base["release_record_hash"] = _canonical_hash(base)
    return base


def run_release_registry(
    release_configuration_path: str | Path,
    approval_path: str | Path,
    run_id: str,
) -> Path:
    configuration = json.loads(Path(release_configuration_path).read_text(encoding="utf-8"))
    approval = json.loads(Path(approval_path).read_text(encoding="utf-8"))
    approved = attach_release_approval(configuration, approval)
    record = build_release_record(approved)

    schema = json.loads((ROOT / "schemas" / "release_record.schema.json").read_text(encoding="utf-8"))
    validate(record, schema)

    out = ROOT / "data" / "release_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "approved_release_configuration.json", approved)
    _write(out / "release_record.json", record)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M5.5",
            "release_record_id": record["release_record_id"],
            "remote_video_id": record["remote_video_id"],
            "release_action": record["release_action"],
            "remote_execution_required": record["remote_execution_required"],
            "final_status": record["final_status"],
        },
    )
    return out
