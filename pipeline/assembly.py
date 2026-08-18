"""M4.1 approval-bound assembly planning contract."""
from __future__ import annotations

import copy
import hashlib
import json

from pipeline.providers import sequence_from_topic_id


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def asset_bundle_fingerprint(bundle: dict) -> str:
    """Hash only production-relevant M3 content; status/approval metadata are excluded."""
    subject = {
        "topic_id": bundle.get("topic_id"),
        "mode": bundle.get("mode"),
        "assets": bundle.get("assets"),
        "qa": bundle.get("qa"),
        "passed": bundle.get("passed"),
    }
    return "sha256:" + hashlib.sha256(_canonical(subject)).hexdigest()


def approve_asset_bundle(bundle: dict, *, approver: str, approved_at: str) -> dict:
    """Return an approved copy of an M3 bundle bound to its exact content fingerprint."""
    if bundle.get("passed") is not True or bundle.get("final_status") != "AWAITING_APPROVAL":
        raise ValueError("Only a passed M3 bundle at AWAITING_APPROVAL may be approved")
    if not isinstance(approver, str) or not approver.strip():
        raise ValueError("approver is required")
    if not isinstance(approved_at, str) or not approved_at.strip():
        raise ValueError("approved_at is required")

    approved = copy.deepcopy(bundle)
    approved["approval"] = {
        "decision": "approved",
        "approver": approver.strip(),
        "approved_at": approved_at,
        "asset_bundle_hash": asset_bundle_fingerprint(bundle),
    }
    approved["final_status"] = "APPROVED"
    return approved


def _product_namespace(product: str) -> str:
    if not isinstance(product, str) or not product.endswith("_room"):
        raise ValueError("Production Spec product must be a JEHA room product")
    return product.removesuffix("_room").upper()


def build_render_plan(bundle: dict, production_spec: dict) -> dict:
    """Build deterministic M4 render lineage only from an explicitly approved M3 bundle."""
    if bundle.get("final_status") != "APPROVED":
        raise ValueError("M4 requires an APPROVED M3 asset bundle")
    if bundle.get("passed") is not True:
        raise ValueError("M4 requires a passed M3 asset bundle")

    approval = bundle.get("approval")
    if not isinstance(approval, dict) or approval.get("decision") != "approved":
        raise ValueError("M4 requires explicit approval metadata")
    for field in ("approver", "approved_at", "asset_bundle_hash"):
        if not approval.get(field):
            raise ValueError(f"M4 approval is missing {field}")
    current_hash = asset_bundle_fingerprint(bundle)
    if approval["asset_bundle_hash"] != current_hash:
        raise ValueError("M4 approval is stale: asset bundle content changed after approval")

    topic_id = production_spec.get("topic_id")
    if not topic_id or topic_id != bundle.get("topic_id"):
        raise ValueError("Production Spec topic lineage does not match M3 bundle")
    product = production_spec.get("product")
    namespace = _product_namespace(product)
    sequence = sequence_from_topic_id(topic_id)

    assets = bundle.get("assets")
    if not isinstance(assets, list):
        raise ValueError("M3 assets must be a list")
    asset_types = [item.get("asset_type") for item in assets]
    if "music" not in asset_types or "visual" not in asset_types:
        raise ValueError("M4 requires MUSIC and VISUAL assets")
    if len({item.get("asset_id") for item in assets}) != len(assets):
        raise ValueError("M4 requires unique asset IDs")
    if any(item.get("qa_status") != "passed" for item in assets):
        raise ValueError("M4 rejects assets that did not pass M3 QA")

    duration_minutes = production_spec.get("duration_minutes")
    if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or duration_minutes <= 0:
        raise ValueError("Production Spec duration_minutes must be a positive integer")

    return {
        "render_plan_id": f"RENDER-{namespace}-{sequence:06d}",
        "video_id": f"VIDEO-{namespace}-{sequence:06d}",
        "topic_id": topic_id,
        "product": product,
        "source_bundle_hash": current_hash,
        "approval": copy.deepcopy(approval),
        "lineage": {
            "production_spec_ref": assets[0].get("production_spec_ref"),
            "asset_ids": [item["asset_id"] for item in assets],
            "music_id": next(item["asset_id"] for item in assets if item["asset_type"] == "music"),
            "visual_id": next(item["asset_id"] for item in assets if item["asset_type"] == "visual"),
            "sfx_ids": [item["asset_id"] for item in assets if item["asset_type"] == "sfx"],
        },
        "target": {
            "duration_minutes": duration_minutes,
            "aspect_ratio": "16:9",
            "status": "READY_FOR_RENDER",
        },
        "final_status": "READY_FOR_RENDER",
    }
