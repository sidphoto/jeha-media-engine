from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.publish_contract import run_publish_plan
from pipeline.security import load_json_validated, validate_run_id

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an approval-bound JEHA M5 publish plan")
    parser.add_argument("delivery_package")
    parser.add_argument("approval")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    args = parser.parse_args()
    load_json_validated(
        args.delivery_package,
        ROOT / "schemas" / "delivery_package.schema.json",
        label="M5.1 delivery package",
    )
    out = run_publish_plan(args.delivery_package, args.approval, args.run_id)
    print(out)


if __name__ == "__main__":
    main()
