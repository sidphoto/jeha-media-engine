from __future__ import annotations

import argparse

from pipeline.publish_contract import run_publish_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an approval-bound JEHA M5 publish plan")
    parser.add_argument("delivery_package")
    parser.add_argument("approval")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = run_publish_plan(args.delivery_package, args.approval, args.run_id)
    print(out)


if __name__ == "__main__":
    main()
