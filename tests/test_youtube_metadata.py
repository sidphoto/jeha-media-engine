from __future__ import annotations

import copy

import pytest

from pipeline.youtube_metadata import (
    DESCRIPTION_MAX_BYTES,
    TAGS_MAX_ACCOUNTED_CHARS,
    TITLE_MAX_CHARS,
    _tag_accounted_length,
    build_metadata_package,
)


def publish_plan() -> dict:
    return {
        "publish_plan_id": "PUBLISH-FLOW-000024",
        "delivery_package_id": "DELIVERY-FLOW-000024",
        "video_id": "VIDEO-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "source_package_hash": "sha256:" + "1" * 64,
        "mode": "dry_run",
        "publish_intent": {
            "platform": "youtube",
            "visibility": "private_first",
            "upload_allowed": False,
            "public_release_allowed": False,
        },
        "final_status": "PUBLISH_PLAN_READY",
    }


def production_spec() -> dict:
    return {
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "duration_minutes": 180,
        "music": {"brief": "focus companion audio"},
        "visual": {"brief": "rainy coding room"},
        "metadata": {
            "working_title": "Rainy Coding Room for Deep Focus",
            "product_name": "Flow Room",
            "purpose": "calm productivity and coding focus",
            "tags": ["coding", "rain", "deep focus", "study music"],
        },
        "status": "approved",
    }


def test_metadata_package_is_deterministic_private_and_within_limits():
    first = build_metadata_package(publish_plan(), production_spec())
    second = build_metadata_package(publish_plan(), production_spec())
    assert first == second
    assert first["metadata_package_id"] == "META-FLOW-000024"
    assert first["status"]["privacyStatus"] == "private"
    assert first["status"]["containsSyntheticMedia"] is True
    assert first["release_control"]["public_release_allowed"] is False
    assert first["final_status"] == "METADATA_READY"
    assert len(first["snippet"]["title"]) <= TITLE_MAX_CHARS
    assert len(first["snippet"]["description"].encode("utf-8")) <= DESCRIPTION_MAX_BYTES
    assert _tag_accounted_length(first["snippet"]["tags"]) <= TAGS_MAX_ACCOUNTED_CHARS
    assert "<" not in first["snippet"]["title"] and ">" not in first["snippet"]["title"]
    assert "<" not in first["snippet"]["description"] and ">" not in first["snippet"]["description"]


def test_metadata_rejects_topic_and_product_lineage_mismatch():
    spec = production_spec()
    spec["topic_id"] = "TOPIC-FLOW-999999"
    with pytest.raises(ValueError, match="topic lineage"):
        build_metadata_package(publish_plan(), spec)

    spec = production_spec()
    spec["product"] = "moon_room"
    with pytest.raises(ValueError, match="product lineage"):
        build_metadata_package(publish_plan(), spec)


def test_long_working_title_is_safely_truncated_and_tags_are_bounded():
    spec = production_spec()
    spec["metadata"]["working_title"] = "A" * 300 + " <unsafe>"
    spec["metadata"]["tags"] = ["long tag " + str(i) + " " + "x" * 80 for i in range(30)]
    package = build_metadata_package(publish_plan(), spec)
    assert len(package["snippet"]["title"]) <= 100
    assert _tag_accounted_length(package["snippet"]["tags"]) <= 500


def test_non_private_or_public_release_intent_is_rejected():
    plan = copy.deepcopy(publish_plan())
    plan["publish_intent"]["visibility"] = "public"
    with pytest.raises(ValueError, match="private-first"):
        build_metadata_package(plan, production_spec())
