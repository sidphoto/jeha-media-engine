from __future__ import annotations

import argparse

from pipeline.youtube_upload import run_upload_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JEHA M5.3 private-first YouTube upload adapter")
    parser.add_argument("publish_plan")
    parser.add_argument("metadata")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    args = parser.parse_args()
    out = run_upload_pipeline(args.publish_plan, args.metadata, args.run_id, mode=args.mode)
    print(out)


if __name__ == "__main__":
    main()
