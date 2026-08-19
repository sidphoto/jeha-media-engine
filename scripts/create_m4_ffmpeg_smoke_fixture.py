from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import validate

from pipeline.assembly import asset_bundle_fingerprint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ci_ffmpeg_smoke"
# Cross-stage smoke inputs must obey the real M4 schemas. The M4.1 contract expresses
# target duration in whole minutes, so use the minimum valid production target rather
# than bypassing boundary validation with a fractional synthetic value.
TARGET_MINUTES = 1
TARGET_SECONDS = float(TARGET_MINUTES * 60)


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def validate_schema(value: dict, schema_name: str) -> None:
    schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    validate(value, schema)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    music_path = OUT / "music.wav"
    visual_path = OUT / "visual.png"

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={TARGET_SECONDS}",
            "-ar", "48000", "-ac", "2", str(music_path),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x203040:s=1920x1080:d=1",
            "-frames:v", "1", "-update", "1", str(visual_path),
        ],
        check=True,
    )

    topic_id = "TOPIC-FLOW-999998"
    music_id = "MUSIC-FLOW-999998"
    visual_id = "VISUAL-FLOW-999998"
    bundle = {
        "topic_id": topic_id,
        "mode": "live",
        "assets": [
            {
                "asset_id": music_id,
                "asset_type": "music",
                "provider": "ci_synthetic",
                "model": "lavfi-sine",
                "provider_version": "ci",
                "prompt_or_source": "CI synthetic sine wave",
                "content_hash": sha256(music_path),
                "qa_status": "passed",
                "production_spec_ref": "ci-smoke-spec.json",
                "technical": {
                    "artifact_path": str(music_path),
                    "duration_seconds": TARGET_SECONDS,
                    "format": "wav",
                    "sample_rate": 48000,
                    "channels": 2,
                },
                "rights": {"commercial_use": True, "license": "CI_SYNTHETIC"},
            },
            {
                "asset_id": visual_id,
                "asset_type": "visual",
                "provider": "ci_synthetic",
                "model": "lavfi-color",
                "provider_version": "ci",
                "prompt_or_source": "CI synthetic solid color",
                "content_hash": sha256(visual_path),
                "qa_status": "passed",
                "production_spec_ref": "ci-smoke-spec.json",
                "technical": {
                    "artifact_path": str(visual_path),
                    "width": 1920,
                    "height": 1080,
                    "aspect_ratio": "16:9",
                    "format": "png",
                    "style_preset": "jeha_cinematic_dreamy_realism_v1",
                    "reference_lineage": [],
                },
                "rights": {"commercial_use": True, "license": "CI_SYNTHETIC"},
            },
        ],
        "qa": [
            {"asset_id": music_id, "passed": True},
            {"asset_id": visual_id, "passed": True},
        ],
        "passed": True,
        "final_status": "APPROVED",
    }
    fingerprint = asset_bundle_fingerprint(bundle)
    approval = {
        "decision": "approved",
        "approver": "ci-synthetic-human-gate",
        "approved_at": "2026-08-18T00:00:00+00:00",
        "asset_bundle_hash": fingerprint,
    }
    bundle["approval"] = approval

    render = {
        "render_plan_id": "RENDER-FLOW-999998",
        "video_id": "VIDEO-FLOW-999998",
        "topic_id": topic_id,
        "product": "flow_room",
        "assembly_mode": "production",
        "source_asset_mode": "live",
        "source_bundle_hash": fingerprint,
        "approval": approval,
        "lineage": {
            "production_spec_ref": "ci-smoke-spec.json",
            "asset_ids": [music_id, visual_id],
            "music_id": music_id,
            "visual_id": visual_id,
            "sfx_ids": [],
        },
        "target": {"duration_minutes": TARGET_MINUTES, "aspect_ratio": "16:9", "status": "READY_FOR_RENDER"},
        "final_status": "READY_FOR_RENDER",
    }
    audio = {
        "audio_plan_id": "AUDIO-FLOW-999998",
        "render_plan_id": render["render_plan_id"],
        "video_id": render["video_id"],
        "topic_id": topic_id,
        "product": "flow_room",
        "source_bundle_hash": fingerprint,
        "target_duration_seconds": TARGET_SECONDS,
        "music": {
            "strategy": "trim_only",
            "source_asset_id": music_id,
            "source_content_hash": bundle["assets"][0]["content_hash"],
            "source_duration_seconds": TARGET_SECONDS,
            "crossfade_seconds": 0.0,
            "segments": [
                {
                    "sequence": 1,
                    "section_id": "M1",
                    "source_start_seconds": 0.0,
                    "source_end_seconds": TARGET_SECONDS,
                    "timeline_start_seconds": 0.0,
                    "timeline_end_seconds": TARGET_SECONDS,
                    "crossfade_in_seconds": 0.0,
                }
            ],
            "planned_coverage_seconds": TARGET_SECONDS,
            "output_trim_seconds": 0.0,
        },
        "sfx_tracks": [],
        "mix": {
            "integrated_loudness_target_lufs": -16.0,
            "true_peak_ceiling_dbtp": -1.5,
            "sfx_gain_db": None,
            "target_basis": "JEHA internal production target",
        },
        "provenance": {
            "claim": "CI synthetic source hashes verified against the approved M3 bundle",
            "audio_asset_hashes": {music_id: bundle["assets"][0]["content_hash"]},
        },
        "final_status": "AUDIO_PLAN_READY",
    }
    visual = {
        "visual_plan_id": "VISPLAN-FLOW-999998",
        "render_plan_id": render["render_plan_id"],
        "video_id": render["video_id"],
        "topic_id": topic_id,
        "product": "flow_room",
        "source_bundle_hash": fingerprint,
        "source_visual": {
            "asset_id": visual_id,
            "content_hash": bundle["assets"][1]["content_hash"],
            "width": 1920,
            "height": 1080,
            "aspect_ratio": "16:9",
            "style_preset": "jeha_cinematic_dreamy_realism_v1",
        },
        "execution_profile": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "motion_class": "low_stimulation_ken_burns",
            "phase_seconds": TARGET_SECONDS,
            "crossfade_seconds": 1.0,
            "max_scale": 1.035,
            "max_pan_x_fraction": 0.014,
            "max_pan_y_fraction": 0.008,
        },
        "target_duration_seconds": TARGET_SECONDS,
        "phases": [
            {
                "sequence": 1,
                "motif": "push_in",
                "timeline_start_seconds": 0.0,
                "timeline_end_seconds": TARGET_SECONDS,
                "crossfade_in_seconds": 0.0,
                "transform": {
                    "scale_start": 1.0,
                    "scale_end": 1.01,
                    "pan_x_start": 0.0,
                    "pan_x_end": 0.003,
                    "pan_y_start": 0.0,
                    "pan_y_end": -0.002,
                },
            }
        ],
        "planned_coverage_seconds": TARGET_SECONDS,
        "output_trim_seconds": 0.0,
        "final_status": "VISUAL_PLAN_READY",
    }

    # Assert the smoke fixture itself obeys the same cross-stage contracts enforced by
    # production entrypoints. This prevents CI from normalizing invalid synthetic shapes.
    validate_schema(render, "render_plan.schema.json")
    validate_schema(audio, "audio_plan.schema.json")
    validate_schema(visual, "visual_motion_plan.schema.json")

    write("approved_bundle.json", bundle)
    write("render_plan.json", render)
    write("audio_plan.json", audio)
    write("visual_plan.json", visual)
    print(OUT)


if __name__ == "__main__":
    main()
