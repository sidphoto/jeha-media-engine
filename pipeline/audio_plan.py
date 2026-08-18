"""M4.2 deterministic long-form audio extension and mix planning."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import validate

from pipeline.assembly import asset_bundle_fingerprint

ROOT = Path(__file__).resolve().parents[1]

LOUDNESS_LUFS = {
    "flow_room": -16.0,
    "cozy_room": -16.0,
    "moon_room": -18.0,
    "nature_room": -18.0,
}
SFX_GAIN_DB = {
    "flow_room": -14.0,
    "cozy_room": -16.0,
    "moon_room": -12.0,
    "nature_room": -8.0,
}
TRUE_PEAK_DBTP = -1.5


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _validate_hash(value: object, asset_id: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"Audio asset {asset_id} requires a SHA-256 content hash")
    return value


def _split_sections(duration_seconds: float) -> list[dict]:
    """Split a master into deterministic musical sections suitable for non-adjacent cycling."""
    if duration_seconds < 180:
        count = 1
    else:
        count = min(4, max(2, int(duration_seconds // 120)))
    length = duration_seconds / count
    sections = []
    for index in range(count):
        start = round(index * length, 3)
        end = round(duration_seconds if index == count - 1 else (index + 1) * length, 3)
        sections.append({"section_id": f"M{index + 1}", "source_start_seconds": start, "source_end_seconds": end})
    return sections


def _music_schedule(asset: dict, target_seconds: float, seed: str) -> dict:
    duration = _positive_number(asset.get("technical", {}).get("duration_seconds"), "music duration_seconds")
    asset_id = asset.get("asset_id", "")
    content_hash = _validate_hash(asset.get("content_hash"), asset_id)

    if duration >= target_seconds:
        return {
            "strategy": "trim_only",
            "source_asset_id": asset_id,
            "source_content_hash": content_hash,
            "source_duration_seconds": duration,
            "crossfade_seconds": 0.0,
            "segments": [{
                "sequence": 1,
                "section_id": "M1",
                "source_start_seconds": 0.0,
                "source_end_seconds": round(target_seconds, 3),
                "timeline_start_seconds": 0.0,
                "timeline_end_seconds": round(target_seconds, 3),
                "crossfade_in_seconds": 0.0,
            }],
            "planned_coverage_seconds": round(target_seconds, 3),
            "output_trim_seconds": 0.0,
        }

    sections = _split_sections(duration)
    shortest = min(section["source_end_seconds"] - section["source_start_seconds"] for section in sections)
    crossfade = round(min(8.0, shortest / 4), 3)
    if crossfade <= 0 or crossfade >= shortest:
        raise ValueError("music crossfade must be shorter than every scheduled section")

    start_index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(sections)
    order = sections[start_index:] + sections[:start_index]
    segments: list[dict] = []
    timeline_end = 0.0
    cursor = 0
    while timeline_end < target_seconds:
        section = order[cursor % len(order)]
        section_duration = section["source_end_seconds"] - section["source_start_seconds"]
        timeline_start = 0.0 if not segments else timeline_end - crossfade
        timeline_end = timeline_start + section_duration
        segments.append({
            "sequence": len(segments) + 1,
            "section_id": section["section_id"],
            "source_start_seconds": section["source_start_seconds"],
            "source_end_seconds": section["source_end_seconds"],
            "timeline_start_seconds": round(timeline_start, 3),
            "timeline_end_seconds": round(timeline_end, 3),
            "crossfade_in_seconds": 0.0 if not segments else crossfade,
        })
        cursor += 1

    if len(sections) > 1:
        for previous, current in zip(segments, segments[1:]):
            if previous["section_id"] == current["section_id"]:
                raise RuntimeError("music schedule produced adjacent identical sections")

    return {
        "strategy": "section_cycle_crossfade",
        "source_asset_id": asset_id,
        "source_content_hash": content_hash,
        "source_duration_seconds": duration,
        "section_count": len(sections),
        "crossfade_seconds": crossfade,
        "segments": segments,
        "planned_coverage_seconds": round(timeline_end, 3),
        "output_trim_seconds": round(max(0.0, timeline_end - target_seconds), 3),
    }


def _sfx_schedule(asset: dict, target_seconds: float) -> dict:
    duration = _positive_number(asset.get("technical", {}).get("duration_seconds"), "sfx duration_seconds")
    asset_id = asset.get("asset_id", "")
    content_hash = _validate_hash(asset.get("content_hash"), asset_id)
    crossfade = round(min(5.5, duration / 5), 3)
    if crossfade <= 0 or crossfade >= duration:
        raise ValueError("sfx crossfade must be shorter than the source duration")

    digest = int(hashlib.sha256(content_hash.encode("utf-8")).hexdigest()[:8], 16)
    max_offset = max(0.0, duration - (crossfade * 2))
    offset = round((digest % 10000) / 10000 * min(max_offset, duration / 3), 3)

    segments: list[dict] = []
    timeline_end = 0.0
    source_start = offset
    while timeline_end < target_seconds:
        source_end = duration
        source_length = source_end - source_start
        if source_length <= crossfade:
            source_start = 0.0
            source_length = duration
        timeline_start = 0.0 if not segments else timeline_end - crossfade
        timeline_end = timeline_start + source_length
        segments.append({
            "sequence": len(segments) + 1,
            "source_start_seconds": round(source_start, 3),
            "source_end_seconds": round(source_end, 3),
            "timeline_start_seconds": round(timeline_start, 3),
            "timeline_end_seconds": round(timeline_end, 3),
            "crossfade_in_seconds": 0.0 if not segments else crossfade,
        })
        source_start = 0.0

    return {
        "source_asset_id": asset_id,
        "source_content_hash": content_hash,
        "source_duration_seconds": duration,
        "initial_source_offset_seconds": offset,
        "crossfade_seconds": crossfade,
        "segments": segments,
        "planned_coverage_seconds": round(timeline_end, 3),
        "output_trim_seconds": round(max(0.0, timeline_end - target_seconds), 3),
    }


def build_audio_plan(render_plan: dict, approved_bundle: dict) -> dict:
    if render_plan.get("final_status") != "READY_FOR_RENDER":
        raise ValueError("M4.2 requires an M4.1 READY_FOR_RENDER plan")
    if approved_bundle.get("final_status") != "APPROVED":
        raise ValueError("M4.2 requires the approved M3 asset bundle")
    current_hash = asset_bundle_fingerprint(approved_bundle)
    if render_plan.get("source_bundle_hash") != current_hash:
        raise ValueError("M4.2 source bundle no longer matches the approved render plan")

    product = render_plan.get("product")
    if product not in LOUDNESS_LUFS:
        raise ValueError("M4.2 requires a known JEHA product")
    target_minutes = render_plan.get("target", {}).get("duration_minutes")
    target_seconds = _positive_number(target_minutes, "target duration_minutes") * 60

    assets = approved_bundle.get("assets", [])
    music_assets = [asset for asset in assets if asset.get("asset_type") == "music"]
    if len(music_assets) != 1:
        raise ValueError("M4.2 requires exactly one primary MUSIC asset")
    sfx_assets = [asset for asset in assets if asset.get("asset_type") == "sfx"]

    music = _music_schedule(music_assets[0], target_seconds, render_plan.get("render_plan_id", ""))
    sfx_tracks = [_sfx_schedule(asset, target_seconds) for asset in sfx_assets]

    return {
        "audio_plan_id": render_plan["render_plan_id"].replace("RENDER-", "AUDIO-", 1),
        "render_plan_id": render_plan["render_plan_id"],
        "video_id": render_plan["video_id"],
        "topic_id": render_plan["topic_id"],
        "product": product,
        "source_bundle_hash": current_hash,
        "target_duration_seconds": round(target_seconds, 3),
        "music": music,
        "sfx_tracks": sfx_tracks,
        "mix": {
            "integrated_loudness_target_lufs": LOUDNESS_LUFS[product],
            "true_peak_ceiling_dbtp": TRUE_PEAK_DBTP,
            "sfx_gain_db": SFX_GAIN_DB[product] if sfx_tracks else None,
            "target_basis": "JEHA internal production target",
        },
        "provenance": {
            "claim": "arrangement/extension of approved source masters; not a new composition",
            "audio_asset_hashes": {
                asset["asset_id"]: asset["content_hash"]
                for asset in music_assets + sfx_assets
            },
        },
        "final_status": "AUDIO_PLAN_READY",
    }


def run_audio_plan_pipeline(
    render_plan_path: str | Path,
    approved_bundle_path: str | Path,
    run_id: str,
) -> Path:
    render_plan = json.loads(Path(render_plan_path).read_text(encoding="utf-8"))
    approved_bundle = json.loads(Path(approved_bundle_path).read_text(encoding="utf-8"))
    plan = build_audio_plan(render_plan, approved_bundle)
    schema = json.loads((ROOT / "schemas" / "audio_plan.schema.json").read_text(encoding="utf-8"))
    validate(plan, schema)

    out = ROOT / "data" / "audio_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "audio_plan.json", plan)
    _write(out / "run_summary.json", {
        "run_id": run_id,
        "pipeline_version": "M4.2",
        "audio_plan_id": plan["audio_plan_id"],
        "render_plan_id": plan["render_plan_id"],
        "target_duration_seconds": plan["target_duration_seconds"],
        "music_segment_count": len(plan["music"]["segments"]),
        "sfx_track_count": len(plan["sfx_tracks"]),
        "final_status": plan["final_status"],
    })
    return out
