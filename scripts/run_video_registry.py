from __future__ import annotations

import argparse

from pipeline.video_registry import run_video_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Register an M4.4 master for JEHA delivery approval")
    parser.add_argument("master_record")
    parser.add_argument("qa_report")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    out = run_video_registry(
        args.master_record,
        args.qa_report,
        args.run_id,
        generated_at=args.generated_at,
    )
    print(out)


if __name__ == "__main__":
    main()
