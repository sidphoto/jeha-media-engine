"""M4.3 deterministic low-stimulation visual motion planning."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import validate

from pipeline.assembly import asset_bundle_fingerprint
from pipeline.security import safe_run_dir
from pipeline.visual_qa import STYLE_PRESET

ROOT = Path(__file__).resolve().parents[1]

MOTION_PROFILES = {
    "flow_room": {"phase_seconds": 180.0, "max_scale": 1.035, "pan_x": 0.014, "pan_y": 0.008, "crossfade": 3.0},
    "moon_room": {"phase_seconds": 240.0, "max_scale": 1.020, "pan_x": 0.008, "pan_y": 0.005, "crossfade": 4.0},
    "cozy_room": {"phase_seconds": 180.0, "max_scale": 1.030, "pan_x": 0.012, "pan_y": 0.007, "crossfade": 3.0},
    "nature_room": {"phase_seconds": 210.0, "max_scale": 1.040, "pan_x": 0.020, "pan_y": 0.010, "crossfade": 4.0},
}
MOTIFS = ("push_in", "drift_left", "pull_out", "drift_right")


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _validate_hash(value: object, asset_id: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"Visual asset {asset_id} requires a SHA-256 content hash")
    return value


def _transform(motif: str, profile: dict) -> dict:
    max_scale = profile["max_scale"]
    x = profile["pan_x"]
    y = profile["pan_y"]
    mid_scale = round(1.0 + (max_scale - 1.0) * 0.65, 6)
    if motif == "push_in":
        return {
            "scale_start": 1.0, "scale_end": max_scale,
            "pan_x_start": -x / 3, "pan_x_end": x / 3,
            "pan_y_start": y / 3, "pan_y_end": -y / 3,
        }
    if motif == "pull_out":
        return {
            "scale_start": max_scale, "scale_end": 1.0,
            "pan_x_start": x / 3, "pan_x_end": -x / 3,
            "pan_y_start": -y / 3, "pan_y_end": y / 3,
        }
    if motif == "drift_left":
        return {
            "scale_start": mid_scale, "scale_end": mid_scale,
            "pan_x_start": x, "pan_x_end": -x,
            "pan_y_start": -y / 2, "pan_y_end": y / 2,
        }
    if motif == "drift_right":
        return {
            "scale_start": mid_scale, "scale_end": mid_scale,
            "pan_x_start": -x, "pan_x_end": x,
            "pan_y_start": y / 2, "pan_y_end": -y / 2,
        }
    raise ValueError(f"Unknown visual motion motif: {motif}")


def build_visual_motion_plan(render_plan: dict, approved_bundle: dict) -> dict:
    if render_plan.get("final_status") != "READY_FOR_RENDER":
        raise ValueError("M4.3 requires an M4.1 READY_FOR_RENDER plan")
    if approved_bundle.get("final_status") != "APPROVED":
        raise ValueError("M4.3 requires the approved M3 asset bundle")
    current_hash = asset_bundle_fingerprint(approved_bundle)
    if render_plan.get("source_bundle_hash") != current_hash:
        raise ValueError("M4.3 source bundle no longer matches the approved render plan")

    product = render_plan.get("product")
    profile = MOTION_PROFILES.get(product)
    if profile is None:
        raise ValueError("M4.3 requires a known JEHA product")
    target_minutes = render_plan.get("target", {}).get("duration_minutes")
    target_seconds = _positive_number(target_minutes, "target duration_minutes") * 60

    visual_assets = [asset for asset in approved_bundle.get("assets", []) if asset.get("asset_type") == "visual"]
    if len(visual_assets) != 1:
        raise ValueError("M4.3 requires exactly one primary VISUAL asset")
    visual = visual_assets[0]
    asset_id = visual.get("asset_id", "")
    content_hash = _validate_hash(visual.get("content_hash"), asset_id)
    technical = visual.get("technical", {})
    width = _positive_number(technical.get("width"), "visual width")
    height = _positive_number(technical.get("height"), "visual height")
    if technical.get("aspect_ratio") != "16:9":
        raise ValueError("M4.3 requires a 16:9 visual master")
    if technical.get("style_preset") != STYLE_PRESET:
        raise ValueError("M4.3 requires JEHA house-style visual lineage")

    phase_seconds = profile["phase_seconds"]
    crossfade = profile["crossfade"]
    if crossfade <= 0 or crossfade >= phase_seconds:
        raise ValueError("visual crossfade must be shorter than each motion phase")
    if profile["max_scale"] < 1.0 or profile["max_scale"] > 1.05:
        raise ValueError("visual motion scale exceeds JEHA low-motion bounds")

    seed = int(hashlib.sha256(render_plan["render_plan_id"].encode("utf-8")).hexdigest()[:8], 16)
    start_index = seed % len(MOTIFS)
    motif_order = MOTIFS[start_index:] + MOTIFS[:start_index]

    phases: list[dict] = []
    timeline_end = 0.0
    cursor = 0
    while timeline_end < target_seconds:
        motif = motif_order[cursor % len(motif_order)]
        timeline_start = 0.0 if not phases else timeline_end - crossfade
        timeline_end = timeline_start + phase_seconds
        phases.append({
            "sequence": len(phases) + 1,
            "motif": motif,
            "timeline_start_seconds": round(timeline_start, 3),
            "timeline_end_seconds": round(timeline_end, 3),
            "crossfade_in_seconds": 0.0 if not phases else crossfade,
            "transform": _transform(motif, profile),
        })
        cursor += 1

    for previous, current in zip(phases, phases[1:]):
        if previous["motif"] == current["motif"]:
            raise RuntimeError("visual motion schedule produced adjacent identical motifs")

    max_seen_scale = max(
        max(phase["transform"]["scale_start"], phase["transform"]["scale_end"])
        for phase in phases
    )
    if max_seen_scale > 1.05:
        raise RuntimeError("visual motion plan exceeds JEHA scale ceiling")

    return {
        "visual_plan_id": render_plan["render_plan_id"].replace("RENDER-", "VISPLAN-", 1),
        "render_plan_id": render_plan["render_plan_id"],
        "video_id": render_plan["video_id"],
        "topic_id": render_plan["topic_id"],
        "product": product,
        "source_bundle_hash": current_hash,
        "source_visual": {
            "asset_id": asset_id,
            "content_hash": content_hash,
            "width": int(width),
            "height": int(height),
            "aspect_ratio": "16:9",
            "style_preset": technical["style_preset"],
        },
        "execution_profile": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "motion_class": "low_stimulation_ken_burns",
            "phase_seconds": phase_seconds,
            "crossfade_seconds": crossfade,
            "max_scale": profile["max_scale"],
            "max_pan_x_fraction": profile["pan_x"],
            "max_pan_y_fraction": profile["pan_y"],
        },
        "target_duration_seconds": round(target_seconds, 3),
        "phases": phases,
        "planned_coverage_seconds": round(timeline_end, 3),
        "output_trim_seconds": round(max(0.0, timeline_end - target_seconds), 3),
        "final_status": "VISUAL_PLAN_READY",
    }


def run_visual_motion_pipeline(
    render_plan_path: str | Path,
    approved_bundle_path: str | Path,
    run_id: str,
) -> Path:
    out = safe_run_dir(ROOT, "visual_runs", run_id)
    render_plan = json.loads(Path(render_plan_path).read_text(encoding="utf-8"))
    approved_bundle = json.loads(Path(approved_bundle_path).read_text(encoding="utf-8"))
    plan = build_visual_motion_plan(render_plan, approved_bundle)
    schema = json.loads((ROOT / "schemas" / "visual_motion_plan.schema.json").read_text(encoding="utf-8"))
    validate(plan, schema)

    out.mkdir(parents=True, exist_ok=False)
    _write(out / "visual_motion_plan.json", plan)
    _write(out / "run_summary.json", {
        "run_id": run_id,
        "pipeline_version": "M4.3",
        "visual_plan_id": plan["visual_plan_id"],
        "render_plan_id": plan["render_plan_id"],
        "phase_count": len(plan["phases"]),
        "target_duration_seconds": plan["target_duration_seconds"],
        "final_status": plan["final_status"],
    })
    return out
