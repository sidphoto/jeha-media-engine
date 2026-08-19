from __future__ import annotations

import pytest

from pipeline.youtube_upload import run_upload_pipeline


def test_upload_pipeline_rejects_path_traversal_run_id_before_input_or_upload_work():
    """M5.3 must reject an unsafe run id before reading inputs or invoking an uploader.

    Missing input paths are intentional: if run-id validation is not the first boundary,
    this test fails with an input-loading error instead of the expected run-id error.
    """
    with pytest.raises(ValueError, match="run_id"):
        run_upload_pipeline(
            "missing-publish-plan.json",
            "missing-metadata.json",
            "../escape",
            mode="live",
        )
