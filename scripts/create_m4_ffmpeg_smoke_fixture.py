from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from pipeline.assembly import asset_bundle_fingerprint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ci_ffmpeg_smoke"
TARGET_SECONDS = 3.0


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


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
            "-frames:v", "1", str(visual_path),
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
    bundle["approval"] = {
        "decision": "approved",
        "approver": "ci-synthetic-human-gate",
        "approved_at": "2026-08-18T00:00:00+00:00",
        "asset_bundle_hash": fingerprint,
    }

    render = {
        "render_plan_id": "RENDER-FLOW-999998",
        "video_id": "VIDEO-FLOW-999998",
        "topic_id": topic_id,
        "product": "flow_room",
        "assembly_mode": "production",
        "source_asset_mode": "live",
        "source_bundle_hash": fingerprint,
        "target": {"duration_minutes": TARGET_SECONDS / 60.0, "aspect_ratio": "16:9", "status": "READY_FOR_RENDER"},
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
            "source_asset_id": music_id,
            "source_content_hash": bundle["assets"][0]["content_hash"],
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
        },
        "sfx_tracks": [],
        "mix": {"integrated_loudness_target_lufs": -16.0, "true_peak_ceiling_dbtp": -1.5, "sfx_gain_db": None},
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
            "style_preset": "jeha_cinematic_dreamy_realism_v1",
        },
        "execution_profile": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
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
        "final_status": "VISUAL_PLAN_READY",
    }

    write("approved_bundle.json", bundle)
    write("render_plan.json", render)
    write("audio_plan.json", audio)
    write("visual_plan.json", visual)
    print(OUT)


if __name__ == "__main__":
    main()
