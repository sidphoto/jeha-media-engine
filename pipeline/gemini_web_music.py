"""Gemini web Music browser-handoff provider for JEHA M3.

The browser step is deliberately outside repository code. This module creates a
deterministic handoff, then attaches a user-supplied downloaded MP3 only after
the browser workflow and commercial-use acknowledgement have completed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pipeline.assets import make_asset_id
from pipeline.providers import AssetRequest, sequence_from_topic_id

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PREFERENCE = "3.7 Flash"
DEFAULT_PROVIDER_VERSION = "Gemini web Music via browser handoff"
MUSIC_TERMS_URL = "https://support.google.com/gemini/answer/16901237?co=GENIE.Platform%3DDesktop&hl=en"


def build_music_prompt(request: AssetRequest) -> str:
    """Build the exact prompt that the browser operator must submit."""
    product_name = request.product.replace("_", " ").title()
    return (
        f"Create music: an original instrumental ambient track for {product_name}.\n"
        f"Creative brief: {request.music_brief}.\n"
        "Calm, polished, loop-friendly background music for long-form video, focus, reading, or sleep.\n"
        "No vocals, no lyrics, no spoken words.\n"
        f"Slow 68 BPM, suitable for a {request.duration_minutes}-minute program. Generate the audio track."
    )


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _prompt_hash(request: AssetRequest, prompt: str, model_preference: str) -> str:
    return _canonical_hash(
        {
            "topic_id": request.topic_id,
            "production_spec_ref": request.production_spec_ref,
            "product": request.product,
            "prompt": prompt,
            "model_preference": model_preference,
            "output_format": "mp3",
        }
    )


def build_music_handoff(
    request: AssetRequest,
    *,
    model_preference: str | None = None,
) -> dict:
    """Create a deterministic, browser-only music handoff without remote calls."""
    preference = (
        model_preference
        or os.getenv("JEHA_GEMINI_WEB_MUSIC_MODEL_PREFERENCE", DEFAULT_MODEL_PREFERENCE)
    ).strip()
    if not preference:
        raise ValueError("Gemini web music model preference must not be empty")
    prompt = build_music_prompt(request)
    return {
        "topic_id": request.topic_id,
        "production_spec_ref": request.production_spec_ref,
        "product": request.product,
        "provider": "gemini_web",
        "execution_mode": "browser_handoff",
        "preferred_model": preference,
        "model_selection_policy": (
            "Select the preferred model if visible; record the exact live label; "
            "verify that Music is available; fall back only to a capable visible mode."
        ),
        "prompt": prompt,
        "prompt_hash": _prompt_hash(request, prompt, preference),
        "output_format": "mp3",
        "download_selection": "audio_only_mp3",
        "remote_execution_allowed": False,
        "requested_program_minutes": request.duration_minutes,
        "final_status": "AWAITING_GEMINI_WEB_MUSIC_GENERATION",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _probe_audio(path: Path) -> dict:
    """Read local MP3 metadata through ffprobe without invoking a shell."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name:stream=codec_name,sample_rate,channels",
            "-of",
            "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown ffprobe error"
        raise RuntimeError(f"Gemini web music MP3 verification failed: {detail}")
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values.setdefault(key, value)
    try:
        duration = float(values["duration"])
        sample_rate = int(values["sample_rate"])
        channels = int(values["channels"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Gemini web music MP3 metadata is incomplete") from exc
    if duration <= 0 or sample_rate <= 0 or channels <= 0:
        raise RuntimeError("Gemini web music MP3 metadata must contain positive values")
    if values.get("codec_name") != "mp3" or values.get("format_name") != "mp3":
        raise RuntimeError("Gemini web music artifact must be an MP3 stream")
    return {
        "duration_seconds": duration,
        "format": "mp3",
        "sample_rate": sample_rate,
        "channels": channels,
    }


class GeminiWebMusicProvider:
    """Attach a verified Gemini web MP3 after an external browser handoff."""

    def __init__(
        self,
        *,
        artifact_path: str | Path | None = None,
        model_label: str | None = None,
        commercial_use_ack: bool | None = None,
        handoff_path: str | Path | None = None,
        output_dir: str | Path = ROOT / "data/generated_assets/music",
        probe: Callable[[Path], dict] = _probe_audio,
    ) -> None:
        configured_artifact = artifact_path or os.getenv("JEHA_GEMINI_WEB_MUSIC_ARTIFACT")
        self.artifact_path = Path(configured_artifact).expanduser() if configured_artifact else None
        self.model_label = (model_label or os.getenv("JEHA_GEMINI_WEB_MUSIC_MODEL", "")).strip()
        if commercial_use_ack is None:
            commercial_use_ack = os.getenv("JEHA_GEMINI_WEB_MUSIC_COMMERCIAL_USE_ACK", "").lower() in {
                "1",
                "true",
                "yes",
            }
        self.commercial_use_ack = commercial_use_ack
        configured_handoff = handoff_path or os.getenv("JEHA_GEMINI_WEB_MUSIC_HANDOFF")
        self.handoff_path = Path(configured_handoff).expanduser() if configured_handoff else None
        self.output_dir = Path(output_dir)
        self.probe = probe

    def build_handoff(self, request: AssetRequest) -> dict:
        return build_music_handoff(request)

    def _load_handoff(self, request: AssetRequest) -> dict | None:
        if self.handoff_path is None:
            return None
        try:
            handoff = json.loads(self.handoff_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Gemini web music handoff could not be loaded: {exc}") from exc
        if handoff.get("provider") != "gemini_web":
            raise RuntimeError("Gemini web music handoff provider is invalid")
        if handoff.get("output_format") != "mp3" or handoff.get("download_selection") != "audio_only_mp3":
            raise RuntimeError("Gemini web music handoff must require an audio-only MP3 download")
        if handoff.get("remote_execution_allowed") is not False:
            raise RuntimeError("Gemini web music handoff cannot enable remote repository execution")
        expected = build_music_handoff(request, model_preference=handoff.get("preferred_model"))
        if handoff.get("prompt_hash") != expected["prompt_hash"] or handoff.get("prompt") != expected["prompt"]:
            raise RuntimeError("Gemini web music handoff prompt lineage is stale or mutated")
        if handoff.get("final_status") != "AWAITING_GEMINI_WEB_MUSIC_GENERATION":
            raise RuntimeError("Gemini web music handoff is not awaiting generation")
        return handoff

    def generate(self, request: AssetRequest) -> dict:
        if self.artifact_path is None:
            raise RuntimeError(
                "Gemini web music requires a browser-generated MP3. Run the "
                "gemini-web-music-generation handoff, then set "
                "JEHA_GEMINI_WEB_MUSIC_ARTIFACT to the downloaded file."
            )
        if not self.model_label:
            raise RuntimeError(
                "JEHA_GEMINI_WEB_MUSIC_MODEL must record the exact Gemini model/mode label "
                "shown in the live picker"
            )
        if not self.commercial_use_ack:
            raise RuntimeError(
                "JEHA_GEMINI_WEB_MUSIC_COMMERCIAL_USE_ACK=true is required after reviewing "
                "the applicable Gemini/Google terms"
            )

        handoff = self._load_handoff(request)
        prompt = handoff["prompt"] if handoff else build_music_prompt(request)
        source = self.artifact_path.resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise RuntimeError("Gemini web music artifact is missing or empty")

        sequence = sequence_from_topic_id(request.topic_id)
        asset_id = make_asset_id("music", request.product.replace("_room", ""), sequence)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = (self.output_dir / f"{asset_id}.mp3").resolve()
        source_hash = _sha256_file(source)
        if destination != source:
            if destination.exists():
                if _sha256_file(destination) != source_hash:
                    raise RuntimeError(f"Refusing to overwrite a different music artifact: {destination}")
            else:
                shutil.copy2(source, destination)
        technical = self.probe(destination)
        try:
            stored_artifact_path = destination.relative_to(ROOT).as_posix()
        except ValueError:
            stored_artifact_path = str(destination)
        technical.update(
            {
                "artifact_path": stored_artifact_path,
                "requested_program_minutes": request.duration_minutes,
                "source_artifact_name": source.name,
                "generation_mode": "browser_handoff",
                "prompt_hash": _prompt_hash(
                    request,
                    prompt,
                    handoff.get("preferred_model", DEFAULT_MODEL_PREFERENCE) if handoff else DEFAULT_MODEL_PREFERENCE,
                ),
            }
        )
        return {
            "asset_id": asset_id,
            "asset_type": "music",
            "topic_id": request.topic_id,
            "production_spec_ref": request.production_spec_ref,
            "provider": "gemini_web",
            "model": self.model_label,
            "provider_version": DEFAULT_PROVIDER_VERSION,
            "prompt_or_source": prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": _sha256_file(destination),
            "rights": {
                "commercial_use": True,
                "license": "GOOGLE_GEMINI_TERMS_ACKNOWLEDGED",
                "source_url": MUSIC_TERMS_URL,
            },
            "technical": technical,
            "qa_status": "pending",
        }
