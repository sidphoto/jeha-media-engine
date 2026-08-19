from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.security import load_json_validated, validate_run_id
from pipeline.visual_motion import run_visual_motion_pipeline

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build JEHA M4.3 low-stimulation long-form visual motion plan"
    )
    parser.add_argument("render_plan")
    parser.add_argument("approved_asset_bundle")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    args = parser.parse_args()
    load_json_validated(
        args.render_plan,
        ROOT / "schemas" / "render_plan.schema.json",
        label="M4.3 render plan",
    )
    out = run_visual_motion_pipeline(
        args.render_plan,
        args.approved_asset_bundle,
        args.run_id,
    )
    print(out)


if __name__ == "__main__":
    main()
