from __future__ import annotations

import argparse

from pipeline.visual_motion import run_visual_motion_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build JEHA M4.3 low-stimulation long-form visual motion plan"
    )
    parser.add_argument("render_plan")
    parser.add_argument("approved_asset_bundle")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = run_visual_motion_pipeline(
        args.render_plan,
        args.approved_asset_bundle,
        args.run_id,
    )
    print(out)


if __name__ == "__main__":
    main()
