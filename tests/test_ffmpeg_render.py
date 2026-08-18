from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pipeline.ffmpeg_render import (
    build_audio_ffmpeg_command,
    build_master_record,
    build_mux_command,
    build_visual_ffmpeg_command,
    master_qa,
    validate_render_inputs,
    verify_artifact,
)


def h(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def bundle(tmp_path: Path) -> dict:
    music_bytes = b"music-bytes"
    visual_bytes = b"visual-bytes"
    music_path = tmp_path / "music.wav"
    visual_path = tmp_path / "visual.png"
    music_path.write_bytes(music_bytes)
    visual_path.write_bytes(visual_bytes)
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "mode": "live",
        "assets": [
            {
                "asset_id": "MUSIC-FLOW-000024", "asset_type": "music", "provider": "elevenlabs",
                "content_hash": h(music_bytes), "qa_status": "passed",
                "technical": {"artifact_path": str(music_path), "duration_seconds": 600},
            },
            {
                "asset_id": "VISUAL-FLOW-000024", "asset_type": "visual", "provider": "google_gemini",
                "content_hash": h(visual_bytes), "qa_status": "passed",
                "technical": {"artifact_path": str(visual_path), "width": 2752, "height": 1536, "aspect_ratio": "16:9"},
            },
        ],
        "qa": [{"asset_id": "MUSIC-FLOW-000024", "passed": True}, {"asset_id": "VISUAL-FLOW-000024", "passed": True}],
        "passed": True,
        "approval": {"decision": "approved", "approver": "human", "approved_at": "2026-08-18T12:00:00+08:00", "asset_bundle_hash": "placeholder"},
        "final_status": "APPROVED",
    }


def plan_set(tmp_path: Path):
    from pipeline.assembly import asset_bundle_fingerprint
    b = bundle(tmp_path)
    fingerprint = asset_bundle_fingerprint(b)
    b["approval"]["asset_bundle_hash"] = fingerprint
    # fingerprint excludes approval metadata, so remains stable.
    render = {
        "render_plan_id": "RENDER-FLOW-000024", "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024", "product": "flow_room",
        "assembly_mode": "production", "source_asset_mode": "live",
        "source_bundle_hash": fingerprint,
        "target": {"duration_minutes": 3, "aspect_ratio": "16:9", "status": "READY_FOR_RENDER"},
        "final_status": "READY_FOR_RENDER",
    }
    audio = {
        "audio_plan_id": "AUDIO-FLOW-000024", "render_plan_id": render["render_plan_id"], "video_id": render["video_id"],
        "topic_id": render["topic_id"], "product": "flow_room", "source_bundle_hash": fingerprint,
        "target_duration_seconds": 180.0,
        "music": {
            "source_asset_id": "MUSIC-FLOW-000024", "source_content_hash": b["assets"][0]["content_hash"],
            "segments": [
                {"sequence": 1, "section_id": "M1", "source_start_seconds": 0.0, "source_end_seconds": 100.0, "timeline_start_seconds": 0.0, "timeline_end_seconds": 100.0, "crossfade_in_seconds": 0.0},
                {"sequence": 2, "section_id": "M2", "source_start_seconds": 100.0, "source_end_seconds": 200.0, "timeline_start_seconds": 96.0, "timeline_end_seconds": 196.0, "crossfade_in_seconds": 4.0},
            ],
        },
        "sfx_tracks": [],
        "mix": {"integrated_loudness_target_lufs": -16.0, "true_peak_ceiling_dbtp": -1.5, "sfx_gain_db": None},
        "final_status": "AUDIO_PLAN_READY",
    }
    visual = {
        "visual_plan_id": "VISPLAN-FLOW-000024", "render_plan_id": render["render_plan_id"], "video_id": render["video_id"],
        "topic_id": render["topic_id"], "product": "flow_room", "source_bundle_hash": fingerprint,
        "source_visual": {"asset_id": "VISUAL-FLOW-000024", "content_hash": b["assets"][1]["content_hash"]},
        "execution_profile": {"width": 1920, "height": 1080, "fps": 30, "max_pan_x_fraction": 0.014, "max_pan_y_fraction": 0.008},
        "target_duration_seconds": 180.0,
        "phases": [
            {"sequence": 1, "motif": "push_in", "timeline_start_seconds": 0.0, "timeline_end_seconds": 100.0, "crossfade_in_seconds": 0.0,
             "transform": {"scale_start": 1.0, "scale_end": 1.03, "pan_x_start": -0.004, "pan_x_end": 0.004, "pan_y_start": 0.002, "pan_y_end": -0.002}},
            {"sequence": 2, "motif": "drift_left", "timeline_start_seconds": 96.0, "timeline_end_seconds": 196.0, "crossfade_in_seconds": 4.0,
             "transform": {"scale_start": 1.02, "scale_end": 1.02, "pan_x_start": 0.014, "pan_x_end": -0.014, "pan_y_start": -0.004, "pan_y_end": 0.004}},
        ],
        "final_status": "VISUAL_PLAN_READY",
    }
    return b, render, audio, visual


def test_render_input_lineage_is_bound_to_exact_bundle(tmp_path):
    b, render, audio, visual = plan_set(tmp_path)
    validate_render_inputs(render, audio, visual, b)
    audio["source_bundle_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="audio plan source bundle hash mismatch"):
        validate_render_inputs(render, audio, visual, b)


def test_verify_artifact_hashes_actual_bytes(tmp_path):
    b, _, _, _ = plan_set(tmp_path)
    assert verify_artifact(b["assets"][0]).name == "music.wav"
    Path(b["assets"][0]["technical"]["artifact_path"]).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        verify_artifact(b["assets"][0])


def test_audio_command_compiles_segments_crossfade_and_loudness(tmp_path):
    b, _, audio, visual = plan_set(tmp_path)
    paths = {asset["asset_id"]: Path(asset["technical"]["artifact_path"]) for asset in b["assets"]}
    command = build_audio_ffmpeg_command(audio, paths, tmp_path / "audio.m4a")
    text = " ".join(command)
    assert command[0] == "ffmpeg"
    assert "acrossfade=d=4" in text
    assert "loudnorm=I=-16:TP=-1.5" in text
    assert "-c:a aac" in text
    assert text.endswith("audio.m4a")


def test_visual_command_compiles_zoompan_xfade_and_1080p(tmp_path):
    b, _, _, visual = plan_set(tmp_path)
    paths = {asset["asset_id"]: Path(asset["technical"]["artifact_path"]) for asset in b["assets"]}
    command = build_visual_ffmpeg_command(visual, paths, tmp_path / "visual.mp4")
    text = " ".join(command)
    assert command[0] == "ffmpeg"
    assert "zoompan=" in text
    assert "xfade=transition=fade:duration=4:offset=96" in text
    assert "s=1920x1080" in text
    assert "-c:v libx264" in text
    assert "-pix_fmt yuv420p" in text


def test_mux_command_stream_copies_preencoded_tracks(tmp_path):
    command = build_mux_command(tmp_path / "v.mp4", tmp_path / "a.m4a", tmp_path / "master.mp4")
    text = " ".join(command)
    assert "-c:v copy" in text
    assert "-c:a copy" in text
    assert "-shortest" in command


def test_master_qa_accepts_expected_ffprobe_shape(tmp_path):
    master = tmp_path / "master.mp4"
    master.write_bytes(b"rendered-master")
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
        ],
        "format": {"duration": "180.25"},
    }
    qa = master_qa(master, probe, target_seconds=180.0)
    assert qa["passed"] is True
    assert all(qa["checks"].values())


def test_master_qa_rejects_wrong_codec_or_duration(tmp_path):
    master = tmp_path / "master.mp4"
    master.write_bytes(b"rendered-master")
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "vp9", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "175.0"},
    }
    qa = master_qa(master, probe, target_seconds=180.0)
    assert qa["passed"] is False
    assert qa["checks"]["h264_video"] is False
    assert qa["checks"]["duration_match"] is False


def test_master_record_hashes_actual_output(tmp_path):
    _, render, audio, visual = plan_set(tmp_path)
    master = tmp_path / "master.mp4"
    payload = b"rendered-master"
    master.write_bytes(payload)
    qa = {
        "passed": True, "checks": {}, "duration_seconds": 180.0, "fps": 30.0,
        "video_codec": "h264", "audio_codec": "aac", "width": 1920, "height": 1080,
    }
    record = build_master_record(render, audio, visual, master, qa)
    assert record["content_hash"] == h(payload)
    assert record["final_status"] == "MASTER_QA_PASSED"


def test_production_render_rejects_fixture_provider(tmp_path):
    b, render, audio, visual = plan_set(tmp_path)
    b["assets"][0]["provider"] = "jeha_fixture"
    from pipeline.assembly import asset_bundle_fingerprint
    fingerprint = asset_bundle_fingerprint(b)
    render["source_bundle_hash"] = fingerprint
    audio["source_bundle_hash"] = fingerprint
    visual["source_bundle_hash"] = fingerprint
    with pytest.raises(ValueError, match="fixture providers"):
        validate_render_inputs(render, audio, visual, b)
