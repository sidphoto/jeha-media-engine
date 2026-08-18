from __future__ import annotations

import argparse

from pipeline.audio_plan import run_audio_plan_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build JEHA M4.2 long-form audio extension and mix plan"
    )
    parser.add_argument("render_plan")
    parser.add_argument("approved_asset_bundle")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = run_audio_plan_pipeline(
        args.render_plan,
        args.approved_asset_bundle,
        args.run_id,
    )
    print(out)


if __name__ == "__main__":
    main()
