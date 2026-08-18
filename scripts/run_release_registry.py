from __future__ import annotations

import argparse

from pipeline.release_registry import run_release_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JEHA M5.5 approval-bound release registry")
    parser.add_argument("release_configuration")
    parser.add_argument("approval")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = run_release_registry(args.release_configuration, args.approval, args.run_id)
    print(out)


if __name__ == "__main__":
    main()
