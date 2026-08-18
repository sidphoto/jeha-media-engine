from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.security import load_json_validated, validate_run_id
from pipeline.youtube_metadata import run_metadata_pipeline

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build JEHA M5.2 YouTube metadata package")
    parser.add_argument("publish_plan")
    parser.add_argument("production_spec")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    parser.add_argument("--language", default="en")
    parser.add_argument("--category-id", default="10")
    args = parser.parse_args()
    load_json_validated(
        args.publish_plan,
        ROOT / "schemas" / "publish_plan.schema.json",
        label="M5.2 publish plan",
    )
    load_json_validated(
        args.production_spec,
        ROOT / "schemas" / "production_spec.schema.json",
        label="M5.2 production spec",
    )
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
