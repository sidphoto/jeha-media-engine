from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.video_registry import run_video_registry
from pipeline.security import load_json_validated, validate_run_id

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Register an M4.4 master for JEHA delivery approval")
    parser.add_argument("master_record")
    parser.add_argument("qa_report")
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    load_json_validated(
        args.master_record,
        ROOT / "schemas" / "video_master.schema.json",
        label="M4.5 video master",
    )
    out = run_video_registry(
        args.master_record,
        args.qa_report,
        args.run_id,
        generated_at=args.generated_at,
    )
    print(out)


if __name__ == "__main__":
    main()
