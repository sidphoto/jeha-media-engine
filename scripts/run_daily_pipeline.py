#!/usr/bin/env python3
"""Run the deterministic M1 topic-to-production-spec pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]

from pipeline.planner import build_production_spec
from pipeline.qa import build_qa_report
from pipeline.research import generate_candidates
from pipeline.router import load_products, route_top_candidates
from pipeline.score import load_scoring_config, rank_candidates


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_pipeline(run_id: str) -> Path:
    scoring = load_scoring_config(ROOT / "config" / "scoring.yaml")
    products = load_products(ROOT / "config" / "products.yaml")

    candidates = generate_candidates()
    ranked = rank_candidates(candidates, scoring)
    shortlist_count = scoring["thresholds"]["shortlist_count"]
    top5 = route_top_candidates(ranked[:shortlist_count], products)

    for item in top5:
        item["status"] = "shortlisted"
    top5[0]["status"] = "selected"

    production_spec = build_production_spec(top5[0], products)
    qa_report = build_qa_report(
        production_spec,
        originality_minimum=scoring["thresholds"]["originality_minimum"],
    )

    validate(
        instance=production_spec,
        schema=load_json(ROOT / "schemas" / "production_spec.schema.json"),
    )
    validate(
        instance=qa_report,
        schema=load_json(ROOT / "schemas" / "qa_report.schema.json"),
    )

    output_dir = ROOT / "data" / "runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    write_json(output_dir / "candidates.json", ranked)
    write_json(output_dir / "top5.json", top5)
    write_json(output_dir / "production_spec.json", production_spec)
    write_json(output_dir / "qa_report.json", qa_report)

    summary = {
        "run_id": run_id,
        "pipeline_version": "M1",
        "candidate_count": len(ranked),
        "shortlist_count": len(top5),
        "selected_topic_id": top5[0]["id"],
        "selected_product": top5[0]["product"],
        "qa_passed": qa_report["passed"],
        "final_status": "AWAITING_APPROVAL",
    }
    write_json(output_dir / "run_summary.json", summary)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        help="Output run id. Use a fixed value for reproducibility checks.",
    )
    args = parser.parse_args()
    output_dir = run_pipeline(args.run_id)
    print(output_dir.relative_to(ROOT))


if __name__ == "__main__":
    main()
