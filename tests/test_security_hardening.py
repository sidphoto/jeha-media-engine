from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.google_trends import collect_live
from pipeline.security import load_json_validated, safe_run_dir, validate_https_host, validate_run_id
from pipeline.youtube_upload import YouTubeResumableTransport


def test_run_id_rejects_path_traversal_and_separators(tmp_path: Path):
    for value in ("../escape", "..", ".", "a/b", r"a\\b", "/tmp/x", " space"):
        with pytest.raises(ValueError, match="run_id"):
            validate_run_id(value)
        with pytest.raises(ValueError, match="run_id"):
            safe_run_dir(tmp_path, "runs", value)


def test_run_id_accepts_expected_ci_and_timestamp_style_ids(tmp_path: Path):
    assert validate_run_id("ci-m4-audio") == "ci-m4-audio"
    assert validate_run_id("run_20260818_2200") == "run_20260818_2200"
    out = safe_run_dir(tmp_path, "runs", "ci-m4-audio")
    assert out.parent == (tmp_path / "data" / "runs").resolve()


def test_https_host_allowlist_rejects_credential_exfiltration_targets():
    assert validate_https_host(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        exact_hosts={"www.googleapis.com"},
        label="YouTube",
    )
    for url in (
        "http://www.googleapis.com/upload/youtube/v3/videos",
        "https://evil.example/upload",
        "https://www.googleapis.com.evil.example/upload",
        "https://user@www.googleapis.com/upload",
        "https://www.googleapis.com:444/upload",
    ):
        with pytest.raises(RuntimeError):
            validate_https_host(url, exact_hosts={"www.googleapis.com"}, label="YouTube")


def test_youtube_transport_rejects_non_google_resumable_location():
    transport = YouTubeResumableTransport()
    with pytest.raises(RuntimeError, match="not allowlisted"):
        transport._connection("https://attacker.example/resumable?upload_id=secret")
    with pytest.raises(RuntimeError, match="not allowlisted"):
        transport._connection("https://www.googleapis.com.attacker.example/resumable")


def test_google_trends_rejects_untrusted_endpoint_before_http(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GOOGLE_TRENDS_API_URL", "https://attacker.example/collect")
    monkeypatch.setenv("GOOGLE_TRENDS_API_TOKEN", "do-not-exfiltrate")
    with pytest.raises(RuntimeError, match="not allowlisted"):
        collect_live(["focus music"], ["7d"], cache_dir=tmp_path)


def test_schema_boundary_reports_explicit_validation_error(tmp_path: Path):
    payload = tmp_path / "payload.json"
    schema = tmp_path / "schema.json"
    payload.write_text(json.dumps({"status": "wrong"}), encoding="utf-8")
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"const": "READY"}},
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema validation failed"):
        load_json_validated(payload, schema, label="cross-stage fixture")
