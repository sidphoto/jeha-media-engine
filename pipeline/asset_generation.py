"""M3 asset generation orchestration and QA."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pipeline.assets import AssetRegistry
from pipeline.elevenlabs_music import ElevenLabsMusicProvider
from pipeline.gemini_visual import GeminiVisualProvider
from pipeline.providers import (
    AssetRequest,
    FixtureMusicProvider,
    FixtureSFXProvider,
    FixtureVisualProvider,
    UnconfiguredLiveProvider,
)
from pipeline.security import safe_run_dir
from pipeline.sfx_library import LocalSFXLibraryProvider
from pipeline.visual_candidates import build_candidate_handoffs
from pipeline.visual_qa import validate_visual_lineage

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def infer_sfx_type(spec: dict) -> str | None:
    tags = set(spec.get("metadata", {}).get("tags", []))
    for value in ("rain", "forest", "ocean", "fireplace", "white_noise"):
        if value in tags:
            return value
    return None


def build_request(spec: dict, production_spec_ref: str) -> AssetRequest:
    return AssetRequest(
        topic_id=spec["topic_id"],
        product=spec["product"],
        production_spec_ref=production_spec_ref,
        music_brief=spec["music"]["brief"],
        visual_brief=spec["visual"]["brief"],
        duration_minutes=spec["duration_minutes"],
        sfx_type=infer_sfx_type(spec),
    )


def _technical_metadata_valid(record: dict) -> bool:
    technical = record.get("technical")
    if not isinstance(technical, dict):
        return False
    asset_type = record.get("asset_type")
    if asset_type in {"music", "sfx"}:
        duration = technical.get("duration_seconds")
        sample_rate = technical.get("sample_rate")
        channels = technical.get("channels")
        channels_valid = channels is None or (
            isinstance(channels, int)
            and not isinstance(channels, bool)
            and channels > 0
        )
        return (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and duration > 0
            and isinstance(sample_rate, int)
            and not isinstance(sample_rate, bool)
            and sample_rate > 0
            and channels_valid
            and isinstance(technical.get("format"), str)
            and bool(technical["format"].strip())
        )
    if asset_type == "visual":
        width = technical.get("width")
        height = technical.get("height")
        return (
            isinstance(width, int)
            and not isinstance(width, bool)
            and width > 0
            and isinstance(height, int)
            and not isinstance(height, bool)
            and height > 0
            and technical.get("aspect_ratio") == "16:9"
            and isinstance(technical.get("format"), str)
            and bool(technical["format"].strip())
        )
    return False


def _qa_record(record: dict, *, live_mode: bool) -> dict:
    rights = record.get("rights", {})
    visual_lineage_issues = validate_visual_lineage(record) if record.get("asset_type") == "visual" else []
    checks = {
        "id_present": bool(record.get("asset_id")),
        "topic_lineage": bool(record.get("topic_id") and record.get("production_spec_ref")),
        "provider_trace": bool(record.get("provider") and record.get("model") and record.get("prompt_or_source")),
        "rights_present": bool(rights.get("license")),
        "commercial_use": rights.get("commercial_use") is True,
        "content_hash": str(record.get("content_hash", "")).startswith("sha256:"),
        "technical_metadata": _technical_metadata_valid(record),
        "visual_house_style_lineage": not visual_lineage_issues,
        "no_fixture_in_live": not (live_mode and record.get("provider") == "jeha_fixture"),
    }
    passed = all(checks.values())
    result = {"asset_id": record["asset_id"], "passed": passed, "checks": checks}
    if visual_lineage_issues:
        result["visual_lineage_issues"] = visual_lineage_issues
    return result


def _chatgpt_visual_handoffs(request: AssetRequest) -> list[dict]:
    """Create the canonical #54 ChatGPT-first browser handoffs for live visual generation."""
    return build_candidate_handoffs(
        topic_id=request.topic_id,
        production_spec_ref=request.production_spec_ref,
        product=request.product,
        scene=request.visual_brief,
        lighting="soft product-appropriate cinematic lighting with restrained contrast",
        mood="calm low-stimulation long-form companion ambience",
    )


def _live_providers(request: AssetRequest, selected: dict[str, object]) -> tuple[object, object | None, object, list[str]]:
    """Resolve live providers without making ChatGPT browser handoffs depend on Gemini credentials."""
    errors: list[str] = []
    pending: list[str] = []

    if "music" in selected:
        music_provider = selected["music"]
    else:
        music_provider = ElevenLabsMusicProvider()
        if not music_provider.api_key:
            errors.append("ELEVENLABS_API_KEY is required for live ElevenLabs Music generation")
        if not music_provider.commercial_use_ack:
            errors.append("ELEVENLABS_COMMERCIAL_USE_ACK=true is required after commercial-use review")

    if "visual" in selected:
        visual_provider: object | None = selected["visual"]
    elif os.getenv("JEHA_VISUAL_PROVIDER", "chatgpt").strip().lower() == "gemini":
        visual_provider = GeminiVisualProvider()
        if not visual_provider.api_key:
            errors.append("GEMINI_API_KEY is required when JEHA_VISUAL_PROVIDER=gemini")
        if not visual_provider.commercial_use_ack:
            errors.append("GEMINI_COMMERCIAL_USE_ACK=true is required when JEHA_VISUAL_PROVIDER=gemini")
    else:
        visual_provider = None
        pending.append("visual")

    if "sfx" in selected:
        sfx_provider = selected["sfx"]
    elif request.sfx_type:
        manifest = os.getenv("JEHA_SFX_MANIFEST")
        if manifest:
            sfx_provider = LocalSFXLibraryProvider(manifest_path=manifest)
        else:
            sfx_provider = UnconfiguredLiveProvider("sfx")
            pending.append("sfx")
    else:
        sfx_provider = UnconfiguredLiveProvider("sfx")

    if errors:
        raise RuntimeError("Live provider preflight failed: " + "; ".join(errors))
    return music_provider, visual_provider, sfx_provider, pending


def generate_asset_bundle(
    spec: dict,
    *,
    mode: str = "fixture",
    production_spec_ref: str = "production_spec.json",
    providers: dict[str, object] | None = None,
) -> dict:
    request = build_request(spec, production_spec_ref)
    visual_handoffs: list[dict] = []
    pending_dependencies: list[str] = []

    if mode == "fixture":
        if providers is not None:
            raise ValueError("providers may only be injected in live mode")
        music_provider = FixtureMusicProvider()
        visual_provider: object | None = FixtureVisualProvider()
        sfx_provider = FixtureSFXProvider()
    elif mode == "live":
        music_provider, visual_provider, sfx_provider, pending_dependencies = _live_providers(request, providers or {})
        if visual_provider is None:
            visual_handoffs = _chatgpt_visual_handoffs(request)
    else:
        raise ValueError("mode must be fixture or live")

    generated = [music_provider.generate(request)]
    if visual_provider is not None:
        generated.append(visual_provider.generate(request))
    if request.sfx_type and "sfx" not in pending_dependencies:
        sfx = sfx_provider.generate(request)
        if sfx:
            generated.append(sfx)

    registry = AssetRegistry()
    qa = []
    for record in generated:
        result = _qa_record(record, live_mode=(mode == "live"))
        record["qa_status"] = "passed" if result["passed"] else "failed"
        registry.register(record)
        qa.append(result)

    required = {"music", "visual"}
    present = {item["asset_type"] for item in registry.to_list()}
    qa_passed = all(item["passed"] for item in qa)
    bundle_passed = required.issubset(present) and qa_passed and not pending_dependencies

    if bundle_passed:
        final_status = "AWAITING_APPROVAL"
    elif qa_passed and visual_handoffs:
        final_status = "AWAITING_CHATGPT_VISUAL_GENERATION"
    else:
        final_status = "FAILED"

    return {
        "topic_id": spec["topic_id"],
        "mode": mode,
        "assets": registry.to_list(),
        "visual_handoffs": visual_handoffs,
        "pending_dependencies": pending_dependencies,
        "qa": qa,
        "passed": bundle_passed,
        "final_status": final_status,
    }


def run_asset_pipeline(production_spec_path: str | Path, run_id: str, mode: str = "fixture") -> Path:
    out = safe_run_dir(ROOT, "asset_runs", run_id)
    source = Path(production_spec_path)
    spec = json.loads(source.read_text(encoding="utf-8"))
    bundle = generate_asset_bundle(spec, mode=mode, production_spec_ref=str(source))
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "asset_bundle.json", bundle)
    _write(out / "assets.json", bundle["assets"])
    if bundle["visual_handoffs"]:
        _write(out / "visual_handoffs.json", bundle["visual_handoffs"])
    _write(out / "qa_report.json", {"topic_id": bundle["topic_id"], "checks": bundle["qa"], "passed": bundle["passed"]})
    _write(out / "run_summary.json", {"run_id": run_id, "pipeline_version": "M3", "mode": mode, "asset_count": len(bundle["assets"]), "qa_passed": bundle["passed"], "final_status": bundle["final_status"], "pending_dependencies": bundle["pending_dependencies"]})
    return out
