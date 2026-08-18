from __future__ import annotations

import argparse

from pipeline.youtube_metadata import run_metadata_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build JEHA M5.2 YouTube metadata package")
    parser.add_argument("publish_plan")
    parser.add_argument("production_spec")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--language", default="en")
    parser.add_argument("--category-id", default="10")
    args = parser.parse_args()
    out = run_metadata_pipeline(
        args.publish_plan,
        args.production_spec,
        args.run_id,
        default_language=args.language,
        category_id=args.category_id,
    )
    print(out)


if __name__ == "__main__":
    main()
