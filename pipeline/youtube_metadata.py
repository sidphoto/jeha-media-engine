"""M5.2 deterministic YouTube metadata and SEO package builder."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import validate

from pipeline.security import safe_run_dir

ROOT = Path(__file__).resolve().parents[1]
TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_ACCOUNTED_CHARS = 500

PRODUCT_LABELS = {
    "flow_room": "Flow Room",
    "moon_room": "Moon Room",
    "cozy_room": "Cozy Room",
    "nature_room": "Nature Room",
}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clean_text(value: str) -> str:
    return " ".join(value.replace("<", "").replace(">", "").split())


def _tag_accounted_length(tags: list[str]) -> int:
    total = 0
    for index, tag in enumerate(tags):
        if index:
            total += 1  # comma separator
        total += len(tag)
        if " " in tag:
            total += 2  # API accounting treats space-containing tags as quoted
    return total


def _fit_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = _clean_text(str(raw)).strip("#, ")
        key = tag.casefold()
        if not tag or key in seen:
            continue
        candidate = result + [tag]
        if _tag_accounted_length(candidate) > TAGS_MAX_ACCOUNTED_CHARS:
            continue
        result.append(tag)
        seen.add(key)
    return result


def _validate_lineage(publish_plan: dict, production_spec: dict) -> None:
    if publish_plan.get("final_status") != "PUBLISH_PLAN_READY":
        raise ValueError("M5.2 requires PUBLISH_PLAN_READY")
    if publish_plan.get("mode") != "dry_run":
        raise ValueError("M5.2 metadata generation is planning-only")
    if publish_plan.get("topic_id") != production_spec.get("topic_id"):
        raise ValueError("M5.2 topic lineage mismatch")
    if publish_plan.get("product") != production_spec.get("product"):
        raise ValueError("M5.2 product lineage mismatch")
    intent = publish_plan.get("publish_intent", {})
    if intent.get("visibility") != "private_first" or intent.get("public_release_allowed") is not False:
        raise ValueError("M5.2 requires private-first release control")


def build_metadata_package(
    publish_plan: dict,
    production_spec: dict,
    *,
    default_language: str = "en",
    category_id: str = "10",
    contains_synthetic_media: bool = True,
) -> dict:
    _validate_lineage(publish_plan, production_spec)
    metadata = production_spec.get("metadata", {})
    working_title = _clean_text(str(metadata.get("working_title", "Companion ambience")))
    product = production_spec["product"]
    product_label = PRODUCT_LABELS[product]
    purpose = _clean_text(str(metadata.get("purpose", "calm companion media")))
    duration = production_spec.get("duration_minutes")

    title = _clean_text(f"{working_title} | {product_label}")[:TITLE_MAX_CHARS].rstrip()
    if not title:
        raise ValueError("M5.2 generated an empty title")

    duration_text = f"{duration} minutes" if isinstance(duration, int) and duration > 0 else "long-form"
    description = (
        f"{working_title}\n\n"
        f"A {duration_text} JEHA Media companion experience for {purpose}. "
        f"Designed for low-stimulation listening and viewing.\n\n"
        "This video uses original/authorized source assets and AI-assisted visual production under JEHA Media's traceable asset workflow."
    )
    description = description.replace("<", "").replace(">", "")
    if len(description.encode("utf-8")) > DESCRIPTION_MAX_BYTES:
        raise ValueError("M5.2 generated description exceeds YouTube byte limit")

    tags = _fit_tags(
        [
            product_label,
            working_title,
            purpose,
            "JEHA Media",
            "ambient",
            "relaxing",
            "focus music" if product == "flow_room" else "calm ambience",
            *metadata.get("tags", []),
        ]
    )
    if _tag_accounted_length(tags) > TAGS_MAX_ACCOUNTED_CHARS:
        raise ValueError("M5.2 generated tags exceed YouTube accounting limit")

    package = {
        "metadata_package_id": "META-" + publish_plan["video_id"].removeprefix("VIDEO-"),
        "publish_plan_id": publish_plan["publish_plan_id"],
        "delivery_package_id": publish_plan["delivery_package_id"],
        "video_id": publish_plan["video_id"],
        "topic_id": publish_plan["topic_id"],
        "product": product,
        "source_package_hash": publish_plan["source_package_hash"],
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(category_id),
            "defaultLanguage": default_language,
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(contains_synthetic_media),
        },
        "constraints": {
            "title_chars": len(title),
            "description_utf8_bytes": len(description.encode("utf-8")),
            "tags_accounted_chars": _tag_accounted_length(tags),
        },
        "release_control": {
            "visibility_intent": "private_first",
            "public_release_allowed": False,
        },
        "final_status": "METADATA_READY",
    }
    return package


def run_metadata_pipeline(
    publish_plan_path: str | Path,
    production_spec_path: str | Path,
    run_id: str,
    *,
    default_language: str = "en",
    category_id: str = "10",
) -> Path:
    out = safe_run_dir(ROOT, "metadata_runs", run_id)
    publish_plan = json.loads(Path(publish_plan_path).read_text(encoding="utf-8"))
    production_spec = json.loads(Path(production_spec_path).read_text(encoding="utf-8"))
    package = build_metadata_package(
        publish_plan,
        production_spec,
        default_language=default_language,
        category_id=category_id,
    )
    schema = json.loads((ROOT / "schemas" / "youtube_metadata.schema.json").read_text(encoding="utf-8"))
    validate(package, schema)

    out.mkdir(parents=True, exist_ok=False)
    _write(out / "youtube_metadata.json", package)
    _write(
        out / "run_summary.json",
        {
            "run_id": run_id,
            "pipeline_version": "M5.2",
            "metadata_package_id": package["metadata_package_id"],
            "video_id": package["video_id"],
            "final_status": package["final_status"],
        },
    )
    return out
