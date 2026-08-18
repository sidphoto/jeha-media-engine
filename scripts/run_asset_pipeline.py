from __future__ import annotations

import argparse

from pipeline.asset_generation import run_asset_pipeline
from pipeline.security import validate_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JEHA M3 asset generation pipeline")
    parser.add_argument("production_spec")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    args = parser.parse_args()
    out = run_asset_pipeline(args.production_spec, args.run_id, args.mode)
    print(out)


if __name__ == "__main__":
    main()
