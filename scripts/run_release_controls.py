from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.release_controls import run_release_configuration
from pipeline.security import load_json_validated, validate_run_id

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JEHA M5.4 release configuration planning")
    parser.add_argument("upload_record")
    parser.add_argument("metadata")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    parser.add_argument("--target-visibility", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--publish-at")
    parser.add_argument("--thumbnail")
    args = parser.parse_args()
    load_json_validated(
        args.upload_record,
        ROOT / "schemas" / "youtube_upload_record.schema.json",
        label="M5.4 upload record",
    )
    load_json_validated(
        args.metadata,
        ROOT / "schemas" / "youtube_metadata.schema.json",
        label="M5.4 YouTube metadata",
    )
    out = run_release_configuration(
        args.upload_record,
        args.metadata,
        args.run_id,
        target_visibility=args.target_visibility,
        publish_at=args.publish_at,
        thumbnail_path=args.thumbnail,
    )
    print(out)


if __name__ == "__main__":
    main()
