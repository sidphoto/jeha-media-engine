from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.ffmpeg_render import run_render_pipeline
from pipeline.security import load_json_validated, validate_run_id

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Render and QA a JEHA M4.4 video master")
    parser.add_argument("render_plan")
    parser.add_argument("audio_plan")
    parser.add_argument("visual_plan")
    parser.add_argument("approved_bundle")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    args = parser.parse_args()
    load_json_validated(args.render_plan, ROOT / "schemas" / "render_plan.schema.json", label="M4.4 render plan")
    load_json_validated(args.audio_plan, ROOT / "schemas" / "audio_plan.schema.json", label="M4.4 audio plan")
    load_json_validated(args.visual_plan, ROOT / "schemas" / "visual_motion_plan.schema.json", label="M4.4 visual plan")
    out = run_render_pipeline(
        args.render_plan,
        args.audio_plan,
        args.visual_plan,
        args.approved_bundle,
        args.run_id,
    )
    print(out)


if __name__ == "__main__":
    main()
