#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from pipeline.intelligence import run_intelligence_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("m2-%Y%m%dT%H%M%SZ"))
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    args = parser.parse_args()
    print(run_intelligence_pipeline(args.run_id, args.mode))


if __name__ == "__main__":
    main()
