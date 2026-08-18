"""M5.1 approval-bound publisher planning contract."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import validate

from pipeline.video_registry import delivery_package_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _underlying_delivery_package(package: dict) -> dict:
    """Return the immutable M4 package subject without M5 approval envelope fields."""
    subject = copy.deepcopy(package)
    subject.pop("delivery_approval", None)
    subject["final_status"] = "AWAITING_DELIVERY_APPROVAL"
    return subject


def _underlying_package_fingerprint(package: dict) -> str:
    return delivery_package_fingerprint(_underlying_delivery_package(package))


def attach_delivery_approval(package: dict, approval: dict) -> dict:
    if package.get("final_status") != "AWAITING_DELIVERY_APPROVAL":
        raise ValueError("M5.1 requires AWAITING_DELIVERY_APPROVAL")
    if package.get("delivery_state") != "prepared_not_delivered":
        raise ValueError("M5.1 requires an undelivered M4 package")

    expected = _underlying_package_fingerprint(package)
    if package.get("package_hash") != expected:
        raise ValueError("M5.1 delivery package hash is stale or invalid")
    if not isinstance(approval, dict) or approval.get("decision") != "approved":
        raise ValueError("M5.1 requires an approved delivery decision")
    for field in ("approver", "approved_at", "package_hash"):
        value = approval.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"delivery approval {field} is required")
    if approval["package_hash"] != expected:
        raise ValueError("delivery approval package_hash does not match the current package")

    approved = copy.deepcopy(package)
    approved["delivery_approval"] = copy.deepcopy(approval)
    approved["final_status"] = "DELIVERY_APPROVED"
    return approved


def publish_plan_id(video_id: str) -> str:
    if not isinstance(video_id, str) or not video_id.startswith("VIDEO-"):
        raise ValueError("M5.1 requires canonical VIDEO ID")
    return "PUBLISH-" + video_id.removeprefix("VIDEO-")


def build_publish_plan(approved_package: dict, *, mode: str = "dry_run") -> dict:
    if mode != "dry_run":
        raise ValueError("M5.1 supports dry_run planning only")
    if approved_package.get("final_status") != "DELIVERY_APPROVED":
        raise ValueError("M5.1 requires DELIVERY_APPROVED package")
    approval = approved_package.get("delivery_approval")
    if not isinstance(approval, dict) or approval.get("decision") != "approved":
        raise ValueError("M5.1 requires delivery approval metadata")

    expected = _underlying_package_fingerprint(approved_package)
    if approved_package.get("package_hash") != expected:
        raise ValueError("M5.1 approved package changed after delivery approval")
    if approval.get("package_hash") != expected:
        raise ValueError("M5.1 delivery approval is stale")

    return {
        "publish_plan_id": publish_plan_id(approved_package["video_id"]),
        "delivery_package_id": approved_package["delivery_package_id"],
        "video_id": approved_package["video_id"],
        "topic_id": approved_package["topic_id"],
        "product": approved_package["product"],
        "source_package_hash": expected,
        "delivery_approval": copy.deepcopy(approval),
        "lineage": copy.deepcopy(approved_package["lineage"]),
        "master": copy.deepcopy(approved_package["master"]),
        "publish_intent": {
            "platform": "youtube",
            "visibility": "private_first",
            "upload_allowed": False,
            "public_release_allowed": False,
        },
        "mode": mode,
        "final_status": "PUBLISH_PLAN_READY",
    }


def run_publish_plan(
    delivery_package_path: str | Path,
    approval_path: str | Path,
    run_id: str,
) -> Path:
    package = json.loads(Path(delivery_package_path).read_text(encoding="utf-8"))
    approval = json.loads(Path(approval_path).read_text(encoding="utf-8"))
    approved = attach_delivery_approval(package, approval)
    plan = build_publish_plan(approved)

    schema = json.loads((ROOT / "schemas" / "publish_plan.schema.json").read_text(encoding="utf-8"))
    validate(plan, schema)

    out = ROOT / "data" / "publish_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "approved_delivery_package.json", approved)
    _write(out / "publish_plan.json", plan)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M5.1",
            "publish_plan_id": plan["publish_plan_id"],
            "video_id": plan["video_id"],
            "visibility": plan["publish_intent"]["visibility"],
            "final_status": plan["final_status"],
        },
    )
    return out
