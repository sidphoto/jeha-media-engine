"""M4.1 approval-bound assembly planning contract."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import validate

from pipeline.providers import sequence_from_topic_id

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLY_MODES = {"dry_run", "production"}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def asset_bundle_fingerprint(bundle: dict) -> str:
    """Hash production-relevant M3 content; status/approval metadata are excluded."""
    subject = {
        "topic_id": bundle.get("topic_id"),
        "mode": bundle.get("mode"),
        "assets": bundle.get("assets"),
        "qa": bundle.get("qa"),
        "passed": bundle.get("passed"),
    }
    return "sha256:" + hashlib.sha256(_canonical(subject)).hexdigest()


def _validate_m3_gate_state(bundle: dict) -> None:
    if bundle.get("passed") is not True or bundle.get("final_status") not in {"AWAITING_APPROVAL", "APPROVED"}:
        raise ValueError("M4 requires a passed M3 bundle at the human approval boundary")
    qa = bundle.get("qa")
    if not isinstance(qa, list) or not qa or any(item.get("passed") is not True for item in qa):
        raise ValueError("M4 requires every M3 QA result to pass")


def attach_approval(bundle: dict, approval: dict) -> dict:
    """Attach an externally supplied human approval record after validating its binding."""
    _validate_m3_gate_state(bundle)
    if bundle.get("final_status") != "AWAITING_APPROVAL":
        raise ValueError("Only an M3 bundle at AWAITING_APPROVAL may receive new approval")
    if not isinstance(approval, dict) or approval.get("decision") != "approved":
        raise ValueError("approval decision must be approved")
    for field in ("approver", "approved_at", "asset_bundle_hash"):
        value = approval.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"approval {field} is required")
    expected = asset_bundle_fingerprint(bundle)
    if approval["asset_bundle_hash"] != expected:
        raise ValueError("approval asset_bundle_hash does not match the current M3 bundle")

    approved = copy.deepcopy(bundle)
    approved["approval"] = copy.deepcopy(approval)
    approved["final_status"] = "APPROVED"
    return approved


def approve_asset_bundle(bundle: dict, *, approver: str, approved_at: str) -> dict:
    """Fixture/test helper. Production runners must consume an external approval record."""
    return attach_approval(
        bundle,
        {
            "decision": "approved",
            "approver": approver,
            "approved_at": approved_at,
            "asset_bundle_hash": asset_bundle_fingerprint(bundle),
        },
    )


def _product_namespace(product: str) -> str:
    if not isinstance(product, str) or not product.endswith("_room"):
        raise ValueError("Production Spec product must be a JEHA room product")
    return product.removesuffix("_room").upper()


def build_render_plan(bundle: dict, production_spec: dict, *, assembly_mode: str = "dry_run") -> dict:
    """Build deterministic M4 render lineage only from an explicitly approved M3 bundle."""
    if assembly_mode not in ASSEMBLY_MODES:
        raise ValueError("assembly_mode must be dry_run or production")
    if bundle.get("final_status") != "APPROVED":
        raise ValueError("M4 requires an APPROVED M3 asset bundle")
    _validate_m3_gate_state(bundle)
    if assembly_mode == "production" and bundle.get("mode") != "live":
        raise ValueError("M4 production assembly requires an M3 live asset bundle")

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
    if assembly_mode == "production" and any(item.get("provider") == "jeha_fixture" for item in assets):
        raise ValueError("M4 production assembly rejects fixture asset providers")

    spec_ref = assets[0].get("production_spec_ref")
    if not spec_ref or any(item.get("production_spec_ref") != spec_ref for item in assets):
        raise ValueError("M4 requires one consistent Production Spec reference across assets")

    duration_minutes = production_spec.get("duration_minutes")
    if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or duration_minutes <= 0:
        raise ValueError("Production Spec duration_minutes must be a positive integer")

    return {
        "render_plan_id": f"RENDER-{namespace}-{sequence:06d}",
        "video_id": f"VIDEO-{namespace}-{sequence:06d}",
        "topic_id": topic_id,
        "product": product,
        "assembly_mode": assembly_mode,
        "source_asset_mode": bundle.get("mode"),
        "source_bundle_hash": current_hash,
        "approval": copy.deepcopy(approval),
        "lineage": {
            "production_spec_ref": spec_ref,
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


def run_assembly_pipeline(
    asset_bundle_path: str | Path,
    production_spec_path: str | Path,
    approval_path: str | Path,
    run_id: str,
    assembly_mode: str = "dry_run",
) -> Path:
    """Consume external approval and persist the deterministic M4.1 render plan."""
    bundle = json.loads(Path(asset_bundle_path).read_text(encoding="utf-8"))
    production_spec = json.loads(Path(production_spec_path).read_text(encoding="utf-8"))
    approval = json.loads(Path(approval_path).read_text(encoding="utf-8"))
    approved = attach_approval(bundle, approval)
    plan = build_render_plan(approved, production_spec, assembly_mode=assembly_mode)

    schema = json.loads((ROOT / "schemas" / "render_plan.schema.json").read_text(encoding="utf-8"))
    validate(plan, schema)

    out = ROOT / "data" / "render_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "approved_asset_bundle.json", approved)
    _write(out / "render_plan.json", plan)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M4.1",
            "assembly_mode": plan["assembly_mode"],
            "source_asset_mode": plan["source_asset_mode"],
            "render_plan_id": plan["render_plan_id"],
            "video_id": plan["video_id"],
            "source_bundle_hash": plan["source_bundle_hash"],
            "final_status": plan["final_status"],
        },
    )
    return out
