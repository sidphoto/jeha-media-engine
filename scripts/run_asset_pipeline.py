from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.asset_generation import run_asset_pipeline
from pipeline.security import load_json_validated, validate_run_id

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JEHA M3 asset generation pipeline")
    parser.add_argument("production_spec")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    args = parser.parse_args()
    load_json_validated(
        args.production_spec,
        ROOT / "schemas" / "production_spec.schema.json",
        label="M3 production spec",
    )
    out = run_asset_pipeline(args.production_spec, args.run_id, args.mode)
    print(out)


if __name__ == "__main__":
    main()
