"""M4.4 FFmpeg render adapter and ffprobe master QA.

The renderer consumes already-approved M4 plans. It never downloads assets and never
publishes output. Production execution verifies every source file against the hash stored
in the approved M3 Asset Registry before starting FFmpeg.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from jsonschema import validate

from pipeline.assembly import asset_bundle_fingerprint
from pipeline.security import safe_run_dir

ROOT = Path(__file__).resolve().parents[1]
DURATION_TOLERANCE_SECONDS = 1.0


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _asset_map(bundle: dict) -> dict[str, dict]:
    assets = bundle.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Approved M3 bundle assets must be a list")
    result: dict[str, dict] = {}
    for asset in assets:
        asset_id = asset.get("asset_id")
        if not asset_id or asset_id in result:
            raise ValueError("Approved M3 bundle requires unique non-empty asset IDs")
        result[asset_id] = asset
    return result


def validate_render_inputs(render_plan: dict, audio_plan: dict, visual_plan: dict, bundle: dict) -> None:
    """Verify that all plans refer to the same exact approved bundle and output identity."""
    if render_plan.get("final_status") != "READY_FOR_RENDER":
        raise ValueError("M4.4 requires an M4.1 READY_FOR_RENDER plan")
    if audio_plan.get("final_status") != "AUDIO_PLAN_READY":
        raise ValueError("M4.4 requires an M4.2 AUDIO_PLAN_READY plan")
    if visual_plan.get("final_status") != "VISUAL_PLAN_READY":
        raise ValueError("M4.4 requires an M4.3 VISUAL_PLAN_READY plan")
    if bundle.get("final_status") != "APPROVED":
        raise ValueError("M4.4 requires the approved M3 asset bundle")

    bundle_hash = asset_bundle_fingerprint(bundle)
    for name, value in (
        ("render", render_plan.get("source_bundle_hash")),
        ("audio", audio_plan.get("source_bundle_hash")),
        ("visual", visual_plan.get("source_bundle_hash")),
    ):
        if value != bundle_hash:
            raise ValueError(f"M4.4 {name} plan source bundle hash mismatch")

    for plan_name, plan in (("audio", audio_plan), ("visual", visual_plan)):
        if plan.get("render_plan_id") != render_plan.get("render_plan_id"):
            raise ValueError(f"M4.4 {plan_name} plan render_plan_id mismatch")
        if plan.get("video_id") != render_plan.get("video_id"):
            raise ValueError(f"M4.4 {plan_name} plan video_id mismatch")
        if plan.get("topic_id") != render_plan.get("topic_id"):
            raise ValueError(f"M4.4 {plan_name} plan topic_id mismatch")

    target_seconds = float(render_plan.get("target", {}).get("duration_minutes", 0)) * 60
    if target_seconds <= 0:
        raise ValueError("M4.4 requires a positive render target duration")
    if abs(float(audio_plan.get("target_duration_seconds", 0)) - target_seconds) > 0.001:
        raise ValueError("M4.4 audio target duration mismatch")
    if abs(float(visual_plan.get("target_duration_seconds", 0)) - target_seconds) > 0.001:
        raise ValueError("M4.4 visual target duration mismatch")

    if render_plan.get("assembly_mode") == "production":
        if bundle.get("mode") != "live":
            raise ValueError("M4.4 production rendering requires an M3 live bundle")
        if any(asset.get("provider") == "jeha_fixture" for asset in bundle.get("assets", [])):
            raise ValueError("M4.4 production rendering rejects fixture providers")


def verify_artifact(asset: dict) -> Path:
    """Resolve one local source and prove that its bytes match the approved registry hash."""
    asset_id = asset.get("asset_id", "<unknown>")
    path_value = asset.get("technical", {}).get("artifact_path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise RuntimeError(f"{asset_id} is missing technical.artifact_path")
    path = Path(path_value)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{asset_id} artifact is missing or empty: {path}")
    expected = asset.get("content_hash")
    actual = _sha256_file(path)
    if expected != actual:
        raise RuntimeError(f"{asset_id} artifact hash mismatch")
    return path


def _required_source_ids(audio_plan: dict, visual_plan: dict) -> list[str]:
    ids = [audio_plan["music"]["source_asset_id"], visual_plan["source_visual"]["asset_id"]]
    ids.extend(track["source_asset_id"] for track in audio_plan.get("sfx_tracks", []))
    return ids


def verify_required_artifacts(audio_plan: dict, visual_plan: dict, bundle: dict) -> dict[str, Path]:
    assets = _asset_map(bundle)
    paths: dict[str, Path] = {}
    for asset_id in _required_source_ids(audio_plan, visual_plan):
        asset = assets.get(asset_id)
        if asset is None:
            raise RuntimeError(f"Referenced asset is absent from approved bundle: {asset_id}")
        paths[asset_id] = verify_artifact(asset)
    return paths


def _fmt(value: float) -> str:
    text = f"{value:.6f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def build_audio_ffmpeg_command(audio_plan: dict, artifact_paths: dict[str, Path], output_path: Path) -> list[str]:
    """Compile M4.2 segment schedules into one FFmpeg audio render command."""
    music = audio_plan["music"]
    tracks = [music] + list(audio_plan.get("sfx_tracks", []))
    command = ["ffmpeg", "-y"]
    for track in tracks:
        command += ["-i", str(artifact_paths[track["source_asset_id"]])]

    filter_parts: list[str] = []
    rendered_labels: list[str] = []
    for input_index, track in enumerate(tracks):
        segments = track.get("segments", [])
        if not segments:
            raise ValueError("M4.4 audio track requires at least one segment")
        if len(segments) == 1:
            source_labels = [f"{input_index}:a"]
        else:
            source_labels = [f"a{input_index}s{i}" for i in range(len(segments))]
            split_labels = "".join(f"[{label}]" for label in source_labels)
            filter_parts.append(f"[{input_index}:a]asplit={len(segments)}{split_labels}")

        segment_labels: list[str] = []
        for i, segment in enumerate(segments):
            label = f"a{input_index}p{i}"
            start = _fmt(float(segment["source_start_seconds"]))
            end = _fmt(float(segment["source_end_seconds"]))
            filter_parts.append(
                f"[{source_labels[i]}]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[{label}]"
            )
            segment_labels.append(label)

        current = segment_labels[0]
        for i in range(1, len(segment_labels)):
            out = f"a{input_index}x{i}"
            crossfade_value = float(segments[i]["crossfade_in_seconds"])
            crossfade = _fmt(crossfade_value)
            if crossfade_value > 0:
                filter_parts.append(
                    f"[{current}][{segment_labels[i]}]acrossfade=d={crossfade}:c1=tri:c2=tri[{out}]"
                )
            else:
                filter_parts.append(f"[{current}][{segment_labels[i]}]concat=n=2:v=0:a=1[{out}]")
            current = out

        if input_index > 0:
            gain = audio_plan.get("mix", {}).get("sfx_gain_db")
            if gain is not None:
                out = f"a{input_index}gain"
                filter_parts.append(f"[{current}]volume={_fmt(float(gain))}dB[{out}]")
                current = out
        rendered_labels.append(current)

    if len(rendered_labels) > 1:
        mixed = "amixed"
        filter_parts.append(
            "".join(f"[{label}]" for label in rendered_labels)
            + f"amix=inputs={len(rendered_labels)}:normalize=0:duration=longest[{mixed}]"
        )
        audio_label = mixed
    else:
        audio_label = rendered_labels[0]

    target = _fmt(float(audio_plan["target_duration_seconds"]))
    loudness = _fmt(float(audio_plan["mix"]["integrated_loudness_target_lufs"]))
    peak = _fmt(float(audio_plan["mix"]["true_peak_ceiling_dbtp"]))
    filter_parts.append(
        f"[{audio_label}]atrim=duration={target},asetpts=PTS-STARTPTS,"
        f"loudnorm=I={loudness}:TP={peak}:LRA=11[aout]"
    )
    command += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[aout]",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return command


def _motion_expr(start: float, end: float, frames: int) -> str:
    if frames <= 1 or abs(end - start) < 1e-12:
        return _fmt(end)
    return f"{_fmt(start)}+({_fmt(end - start)})*on/{frames - 1}"


def build_visual_ffmpeg_command(visual_plan: dict, artifact_paths: dict[str, Path], output_path: Path) -> list[str]:
    """Compile M4.3 phases into one still-image motion/crossfade FFmpeg command."""
    source_id = visual_plan["source_visual"]["asset_id"]
    profile = visual_plan["execution_profile"]
    fps = int(profile["fps"])
    width = int(profile["width"])
    height = int(profile["height"])
    max_pan_x = float(profile["max_pan_x_fraction"])
    max_pan_y = float(profile["max_pan_y_fraction"])
    phases = visual_plan.get("phases", [])
    if not phases:
        raise ValueError("M4.4 visual plan requires at least one phase")

    command = ["ffmpeg", "-y", "-loop", "1", "-i", str(artifact_paths[source_id])]
    filters: list[str] = []
    if len(phases) == 1:
        source_labels = ["0:v"]
    else:
        source_labels = [f"vsrc{i}" for i in range(len(phases))]
        split_labels = "".join(f"[{label}]" for label in source_labels)
        filters.append(f"[0:v]split={len(phases)}{split_labels}")

    phase_labels: list[str] = []
    for i, phase in enumerate(phases):
        transform = phase["transform"]
        duration = float(phase["timeline_end_seconds"]) - float(phase["timeline_start_seconds"])
        if duration <= 0:
            raise ValueError("M4.4 visual phase duration must be positive")
        frames = max(1, round(duration * fps))
        z = _motion_expr(float(transform["scale_start"]), float(transform["scale_end"]), frames)
        nx0 = float(transform["pan_x_start"]) / max_pan_x if max_pan_x else 0.0
        nx1 = float(transform["pan_x_end"]) / max_pan_x if max_pan_x else 0.0
        ny0 = float(transform["pan_y_start"]) / max_pan_y if max_pan_y else 0.0
        ny1 = float(transform["pan_y_end"]) / max_pan_y if max_pan_y else 0.0
        nx = _motion_expr(nx0, nx1, frames)
        ny = _motion_expr(ny0, ny1, frames)
        x = f"(iw-iw/zoom)/2*(1+({nx}))"
        y = f"(ih-ih/zoom)/2*(1+({ny}))"
        label = f"vp{i}"
        filters.append(
            f"[{source_labels[i]}]scale={width}:{height},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
            f"setsar=1[{label}]"
        )
        phase_labels.append(label)

    current = phase_labels[0]
    for i in range(1, len(phase_labels)):
        out = f"vx{i}"
        duration = _fmt(float(phases[i]["crossfade_in_seconds"]))
        offset = _fmt(float(phases[i]["timeline_start_seconds"]))
        filters.append(
            f"[{current}][{phase_labels[i]}]xfade=transition=fade:duration={duration}:offset={offset}[{out}]"
        )
        current = out

    target = _fmt(float(visual_plan["target_duration_seconds"]))
    filters.append(f"[{current}]trim=duration={target},setpts=PTS-STARTPTS,format=yuv420p[vout]")
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-an",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return command


def build_mux_command(video_path: Path, audio_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        "-shortest",
        str(output_path),
    ]


def probe_master(path: Path, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    command = [
        "ffprobe", "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json", str(path),
    ]
    result = runner(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _fps_value(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        denominator = float(right)
        return float(left) / denominator if denominator else None
    return float(value)


def master_qa(path: Path, probe: dict, *, target_seconds: float) -> dict:
    checks: dict[str, bool] = {}
    checks["file_present"] = path.is_file() and path.stat().st_size > 0
    streams = probe.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video = videos[0] if videos else {}
    audio = audios[0] if audios else {}
    checks["h264_video"] = video.get("codec_name") == "h264"
    checks["aac_audio"] = audio.get("codec_name") == "aac"
    checks["resolution_1080p"] = video.get("width") == 1920 and video.get("height") == 1080
    fps = _fps_value(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    checks["fps_30"] = fps is not None and abs(fps - 30.0) <= 0.05
    raw_duration = probe.get("format", {}).get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        duration = 0.0
    checks["duration_match"] = duration > 0 and abs(duration - target_seconds) <= DURATION_TOLERANCE_SECONDS
    passed = all(checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "duration_seconds": duration,
        "fps": fps,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
    }


def build_master_record(
    render_plan: dict,
    audio_plan: dict,
    visual_plan: dict,
    output_path: Path,
    qa: dict,
) -> dict:
    if not qa.get("passed"):
        raise RuntimeError("Rendered master failed M4.4 QA")
    return {
        "video_id": render_plan["video_id"],
        "render_plan_id": render_plan["render_plan_id"],
        "audio_plan_id": audio_plan["audio_plan_id"],
        "visual_plan_id": visual_plan["visual_plan_id"],
        "topic_id": render_plan["topic_id"],
        "product": render_plan["product"],
        "source_bundle_hash": render_plan["source_bundle_hash"],
        "artifact_path": str(output_path),
        "content_hash": _sha256_file(output_path),
        "technical": {
            "container": "mp4",
            "video_codec": qa["video_codec"],
            "audio_codec": qa["audio_codec"],
            "width": qa["width"],
            "height": qa["height"],
            "fps": qa["fps"],
            "duration_seconds": qa["duration_seconds"],
        },
        "qa": qa,
        "final_status": "MASTER_QA_PASSED",
    }


def run_render_pipeline(
    render_plan_path: str | Path,
    audio_plan_path: str | Path,
    visual_plan_path: str | Path,
    approved_bundle_path: str | Path,
    run_id: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    """Execute production FFmpeg rendering. This path requires real approved artifacts."""
    out = safe_run_dir(ROOT, "video_runs", run_id)
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("M4.4 requires ffmpeg and ffprobe on PATH")

    render_plan = json.loads(Path(render_plan_path).read_text(encoding="utf-8"))
    audio_plan = json.loads(Path(audio_plan_path).read_text(encoding="utf-8"))
    visual_plan = json.loads(Path(visual_plan_path).read_text(encoding="utf-8"))
    bundle = json.loads(Path(approved_bundle_path).read_text(encoding="utf-8"))
    validate_render_inputs(render_plan, audio_plan, visual_plan, bundle)
    if render_plan.get("assembly_mode") != "production":
        raise RuntimeError("M4.4 execution only accepts production render plans; dry-run plans are planning-only")
    paths = verify_required_artifacts(audio_plan, visual_plan, bundle)

    out.mkdir(parents=True, exist_ok=False)
    audio_path = out / "audio.m4a"
    visual_path = out / "visual.mp4"
    master_path = out / f"{render_plan['video_id']}.mp4"

    commands = {
        "audio": build_audio_ffmpeg_command(audio_plan, paths, audio_path),
        "visual": build_visual_ffmpeg_command(visual_plan, paths, visual_path),
        "mux": build_mux_command(visual_path, audio_path, master_path),
    }
    _write(out / "render_commands.json", commands)
    for command in (commands["audio"], commands["visual"], commands["mux"]):
        runner(command, check=True)

    probe = probe_master(master_path, runner=runner)
    qa = master_qa(master_path, probe, target_seconds=float(audio_plan["target_duration_seconds"]))
    record = build_master_record(render_plan, audio_plan, visual_plan, master_path, qa)
    schema = json.loads((ROOT / "schemas" / "video_master.schema.json").read_text(encoding="utf-8"))
    validate(record, schema)
    _write(out / "master_record.json", record)
    _write(out / "qa_report.json", qa)
    _write(out / "run_summary.json", {
        "run_id": run_id,
        "pipeline_version": "M4.4",
        "video_id": record["video_id"],
        "master_hash": record["content_hash"],
        "qa_passed": qa["passed"],
        "final_status": record["final_status"],
    })
    return out
