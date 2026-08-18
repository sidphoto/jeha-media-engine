from __future__ import annotations

import argparse

from pipeline.release_controls import run_release_configuration


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JEHA M5.4 release configuration planning")
    parser.add_argument("upload_record")
    parser.add_argument("metadata")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-visibility", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--publish-at")
    parser.add_argument("--thumbnail")
    args = parser.parse_args()
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
