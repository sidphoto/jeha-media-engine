from __future__ import annotations

import argparse

from pipeline.assembly import run_assembly_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a JEHA M4 render plan from an externally approved M3 asset bundle"
    )
    parser.add_argument("asset_bundle")
    parser.add_argument("production_spec")
    parser.add_argument("approval")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = run_assembly_pipeline(
        args.asset_bundle,
        args.production_spec,
        args.approval,
        args.run_id,
    )
    print(out)


if __name__ == "__main__":
    main()
