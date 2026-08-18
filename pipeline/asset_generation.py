"""M3 asset generation orchestration and QA."""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.assets import AssetRegistry
from pipeline.providers import (
    AssetRequest,
    FixtureMusicProvider,
    FixtureSFXProvider,
    FixtureVisualProvider,
    UnconfiguredLiveProvider,
)

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
        return (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and duration > 0
            and isinstance(sample_rate, int)
            and not isinstance(sample_rate, bool)
            and sample_rate > 0
            and isinstance(channels, int)
            and not isinstance(channels, bool)
            and channels > 0
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
    checks = {
        "id_present": bool(record.get("asset_id")),
        "topic_lineage": bool(record.get("topic_id") and record.get("production_spec_ref")),
        "provider_trace": bool(record.get("provider") and record.get("model") and record.get("prompt_or_source")),
        "rights_present": bool(rights.get("license")),
        "commercial_use": rights.get("commercial_use") is True,
        "content_hash": str(record.get("content_hash", "")).startswith("sha256:"),
        "technical_metadata": _technical_metadata_valid(record),
        "no_fixture_in_live": not (live_mode and record.get("provider") == "jeha_fixture"),
    }
    passed = all(checks.values())
    return {"asset_id": record["asset_id"], "passed": passed, "checks": checks}


def generate_asset_bundle(
    spec: dict,
    *,
    mode: str = "fixture",
    production_spec_ref: str = "production_spec.json",
    providers: dict[str, object] | None = None,
) -> dict:
    request = build_request(spec, production_spec_ref)
    if mode == "fixture":
        if providers is not None:
            raise ValueError("providers may only be injected in live mode")
        music_provider = FixtureMusicProvider()
        visual_provider = FixtureVisualProvider()
        sfx_provider = FixtureSFXProvider()
    elif mode == "live":
        selected = providers or {}
        music_provider = selected.get("music", UnconfiguredLiveProvider("music"))
        visual_provider = selected.get("visual", UnconfiguredLiveProvider("visual"))
        sfx_provider = selected.get("sfx", UnconfiguredLiveProvider("sfx"))
    else:
        raise ValueError("mode must be fixture or live")

    generated = [music_provider.generate(request), visual_provider.generate(request)]
    sfx = sfx_provider.generate(request)
    if sfx:
        generated.append(sfx)

    registry = AssetRegistry()
    qa = []
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for record in generated:
        asset_id = record.get("asset_id")
        if asset_id in seen_ids:
            duplicate_ids.add(asset_id)
        seen_ids.add(asset_id)
        result = _qa_record(record, live_mode=(mode == "live"))
        if asset_id in duplicate_ids:
            result["checks"]["id_unique"] = False
            result["passed"] = False
        else:
            result["checks"]["id_unique"] = True
        record["qa_status"] = "passed" if result["passed"] else "failed"
        registry.register(record)
        qa.append(result)

    required = {"music", "visual"}
    present = {item["asset_type"] for item in registry.to_list()}
    bundle_passed = required.issubset(present) and all(item["passed"] for item in qa)
    return {
        "topic_id": spec["topic_id"],
        "mode": mode,
        "assets": registry.to_list(),
        "qa": qa,
        "passed": bundle_passed,
        "final_status": "AWAITING_APPROVAL" if bundle_passed else "FAILED",
    }


def run_asset_pipeline(production_spec_path: str | Path, run_id: str, mode: str = "fixture") -> Path:
    source = Path(production_spec_path)
    spec = json.loads(source.read_text(encoding="utf-8"))
    bundle = generate_asset_bundle(spec, mode=mode, production_spec_ref=str(source))
    out = ROOT / "data" / "asset_runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "asset_bundle.json", bundle)
    _write(out / "assets.json", bundle["assets"])
    _write(out / "qa_report.json", {"topic_id": bundle["topic_id"], "checks": bundle["qa"], "passed": bundle["passed"]})
    _write(out / "run_summary.json", {"run_id": run_id, "pipeline_version": "M3", "mode": mode, "asset_count": len(bundle["assets"]), "qa_passed": bundle["passed"], "final_status": bundle["final_status"]})
    return out
