from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pipeline.video_registry import build_delivery_package, delivery_package_fingerprint, verify_master_record


def h(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def master_record(tmp_path: Path) -> tuple[dict, dict]:
    payload = b"final-master-bytes"
    master = tmp_path / "VIDEO-FLOW-000024.mp4"
    master.write_bytes(payload)
    qa = {
        "passed": True,
        "checks": {"file_present": True},
        "duration_seconds": 180.0,
        "fps": 30.0,
        "video_codec": "h264",
        "audio_codec": "aac",
        "width": 1920,
        "height": 1080,
    }
    record = {
        "video_id": "VIDEO-FLOW-000024",
        "render_plan_id": "RENDER-FLOW-000024",
        "audio_plan_id": "AUDIO-FLOW-000024",
        "visual_plan_id": "VISPLAN-FLOW-000024",
        "topic_id": "TOPIC-FLOW-000024",
        "product": "flow_room",
        "source_bundle_hash": "sha256:" + "1" * 64,
        "artifact_path": str(master),
        "content_hash": h(payload),
        "technical": {
            "container": "mp4",
            "video_codec": "h264",
            "audio_codec": "aac",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "duration_seconds": 180.0,
        },
        "qa": qa,
        "final_status": "MASTER_QA_PASSED",
    }
    return record, qa


def test_delivery_package_preserves_lineage_and_stops_at_human_gate(tmp_path):
    record, qa = master_record(tmp_path)
    first = build_delivery_package(record, qa, generated_at="2026-08-18T12:00:00+08:00")
    second = build_delivery_package(record, qa, generated_at="2026-08-18T12:00:00+08:00")
    assert first == second
    assert first["delivery_package_id"] == "DELIVERY-FLOW-000024"
    assert first["video_id"] == "VIDEO-FLOW-000024"
    assert first["lineage"]["render_plan_id"] == "RENDER-FLOW-000024"
    assert first["lineage"]["audio_plan_id"] == "AUDIO-FLOW-000024"
    assert first["lineage"]["visual_plan_id"] == "VISPLAN-FLOW-000024"
    assert first["master"]["content_hash"] == record["content_hash"]
    assert first["delivery_state"] == "prepared_not_delivered"
    assert first["final_status"] == "AWAITING_DELIVERY_APPROVAL"
    assert first["package_hash"] == delivery_package_fingerprint(first)


def test_registry_rejects_tampered_master_bytes(tmp_path):
    record, qa = master_record(tmp_path)
    Path(record["artifact_path"]).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        verify_master_record(record, qa)


def test_registry_rejects_nonpassed_master_or_mismatched_qa(tmp_path):
    record, qa = master_record(tmp_path)
    record["final_status"] = "FAILED"
    with pytest.raises(ValueError, match="MASTER_QA_PASSED"):
        verify_master_record(record, qa)

    record, qa = master_record(tmp_path)
    external = dict(qa)
    external["duration_seconds"] = 999
    with pytest.raises(ValueError, match="does not match"):
        verify_master_record(record, external)
