from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path
from urllib.request import Request

import pytest

from pipeline.asset_generation import run_asset_pipeline
from pipeline.assembly import run_assembly_pipeline
from pipeline.audio_plan import run_audio_plan_pipeline
from pipeline.ffmpeg_render import run_render_pipeline
from pipeline.google_trends import collect_live
from pipeline.http_utils import request_json
from pipeline.publish_contract import run_publish_plan
from pipeline.release_controls import run_release_configuration
from pipeline.security import load_json_validated, safe_run_dir, validate_https_host, validate_run_id
from pipeline.video_registry import run_video_registry
from pipeline.visual_motion import run_visual_motion_pipeline
from pipeline.youtube_metadata import run_metadata_pipeline
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


# Every M1-M5 pipeline entrypoint that persists a run under data/<category>/<run_id> must
# reject a path-traversal run_id before it touches disk, not only when invoked through the
# argparse CLI wrappers in scripts/. Each callable below is exercised with nonexistent input
# paths: if run_id validation ran anywhere but first, these would fail with FileNotFoundError
# instead of the expected ValueError.
_MALICIOUS_RUN_ID = "../escape"
_PIPELINE_ENTRYPOINTS = [
    (run_asset_pipeline, ("missing-production-spec.json",)),
    (run_assembly_pipeline, ("missing-bundle.json", "missing-spec.json", "missing-approval.json")),
    (run_audio_plan_pipeline, ("missing-render-plan.json", "missing-bundle.json")),
    (run_render_pipeline, ("missing-render.json", "missing-audio.json", "missing-visual.json", "missing-bundle.json")),
    (run_publish_plan, ("missing-package.json", "missing-approval.json")),
    (run_release_configuration, ("missing-upload-record.json", "missing-metadata.json")),
    (run_visual_motion_pipeline, ("missing-render-plan.json", "missing-bundle.json")),
    (run_video_registry, ("missing-master-record.json", "missing-qa-report.json")),
    (run_metadata_pipeline, ("missing-publish-plan.json", "missing-production-spec.json")),
]


@pytest.mark.parametrize("func, positional_args", _PIPELINE_ENTRYPOINTS)
def test_pipeline_entrypoints_reject_path_traversal_run_id_before_touching_disk(func, positional_args):
    with pytest.raises(ValueError, match="run_id"):
        func(*positional_args, _MALICIOUS_RUN_ID)


class _CaptureHandler(http.server.BaseHTTPRequestHandler):
    """Records the last request it received; used as the redirect target below."""

    captured: dict = {}

    def do_GET(self):  # noqa: N802 - stdlib handler naming
        _CaptureHandler.captured["authorization"] = self.headers.get("Authorization")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"received": True}).encode())

    def log_message(self, *args):  # silence default stderr logging
        pass


def _make_redirect_handler(target_port: int):
    class _RedirectHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target_port}/steal")
            self.end_headers()

        def log_message(self, *args):
            pass

    return _RedirectHandler


@pytest.fixture
def local_redirect_chain():
    """Spins up an attacker capture server plus a server that 302-redirects to it."""
    _CaptureHandler.captured = {}
    attacker = http.server.HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    threading.Thread(target=attacker.serve_forever, daemon=True).start()

    redirector = http.server.HTTPServer(("127.0.0.1", 0), _make_redirect_handler(attacker.server_address[1]))
    threading.Thread(target=redirector.serve_forever, daemon=True).start()

    try:
        yield redirector.server_address[1], _CaptureHandler.captured
    finally:
        attacker.shutdown()
        redirector.shutdown()


def test_request_json_refuses_redirect_instead_of_forwarding_credentials(local_redirect_chain):
    """Regression test for the urllib default behavior of resending Authorization headers
    across a cross-host redirect. A validated, allowlisted endpoint (e.g. GOOGLE_TRENDS_API_URL)
    could still exfiltrate a Bearer token via a 3xx response naming an arbitrary host; this
    must fail closed instead of silently following it."""
    redirector_port, captured = local_redirect_chain
    req = Request(
        f"http://127.0.0.1:{redirector_port}/start",
        headers={"Authorization": "Bearer do-not-exfiltrate"},
    )
    with pytest.raises(RuntimeError, match="redirect"):
        request_json(req, retries=0)
    assert captured.get("authorization") is None
