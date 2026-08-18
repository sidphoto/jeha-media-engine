from __future__ import annotations

import argparse

from pipeline.ffmpeg_render import run_render_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render and QA a JEHA M4.4 production video master with FFmpeg"
    )
    parser.add_argument("render_plan")
    parser.add_argument("audio_plan")
    parser.add_argument("visual_plan")
    parser.add_argument("approved_asset_bundle")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = run_render_pipeline(
        args.render_plan,
        args.audio_plan,
        args.visual_plan,
        args.approved_asset_bundle,
        args.run_id,
    )
    print(out)


if __name__ == "__main__":
    main()
