"""M2 daily intelligence orchestration feeding the existing M1 pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import validate

from pipeline.google_trends import collect_fixture as collect_trends_fixture, collect_live as collect_trends_live
from pipeline.youtube_intelligence import collect_fixture as collect_youtube_fixture, collect_live as collect_youtube_live
from pipeline.youtube_benchmark import (
    advisory_for_product,
    build_pattern_intelligence,
    collect_fixture as collect_benchmark_fixture,
    collect_live as collect_benchmark_live,
)
from pipeline.normalizer import normalize_topics
from pipeline.signal_engineering import build_candidates
from pipeline.score import load_scoring_config, rank_candidates
from pipeline.router import load_products, route_top_candidates
from pipeline.planner import build_production_spec
from pipeline.qa import build_qa_report

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_intelligence_config(path: str | Path = ROOT / "config" / "intelligence.yaml") -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if config.get("candidate_count") != 20:
        raise ValueError("M2 contract requires candidate_count=20")
    if len(config.get("canonical_topics", [])) != 20:
        raise ValueError("M2 canonical catalog must contain exactly 20 topics")
    return config


def collect_evidence(config: dict, mode: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    evidence: list[dict] = []
    cache_dir = ROOT / "data" / "cache" / "m2"
    if mode == "fixture":
        evidence += collect_trends_fixture(config["seeds"], config["trends_windows"])
        evidence += collect_youtube_fixture(config["canonical_topics"])
    elif mode == "live":
        try:
            evidence += collect_trends_live(config["seeds"], config["trends_windows"], cache_dir=cache_dir / "trends")
        except Exception as exc:  # source isolation is intentional
            errors.append({"source": "google_trends", "error": str(exc)})
        try:
            evidence += collect_youtube_live(
                [item["title"] for item in config["canonical_topics"]],
                region=config.get("region", "TW"),
                cache_dir=cache_dir / "youtube",
            )
        except Exception as exc:  # source isolation is intentional
            errors.append({"source": "youtube", "error": str(exc)})
    else:
        raise ValueError("mode must be fixture or live")

    schema = json.loads((ROOT / "schemas" / "market_evidence.schema.json").read_text())
    for row in evidence:
        validate(row, schema)
    if len(evidence) < int(config.get("raw_topic_minimum", 50)):
        raise RuntimeError(f"Insufficient market evidence: {len(evidence)} observations; errors={errors}")
    return evidence, errors


def collect_benchmark(config: dict, mode: str) -> tuple[list[dict], dict[str, dict], list[dict]]:
    errors: list[dict] = []
    cache_dir = ROOT / "data" / "cache" / "m2" / "youtube_benchmark"
    if mode == "fixture":
        rows = collect_benchmark_fixture()
    elif mode == "live":
        try:
            rows = collect_benchmark_live(
                region=config.get("region", "TW"),
                cache_dir=cache_dir,
            )
        except Exception as exc:
            rows = []
            errors.append({"source": "youtube_benchmark", "error": str(exc)})
    else:
        raise ValueError("mode must be fixture or live")
    return rows, build_pattern_intelligence(rows), errors


def run_intelligence_pipeline(run_id: str, mode: str = "fixture") -> Path:
    config = load_intelligence_config()
    scoring = load_scoring_config(ROOT / "config" / "scoring.yaml")
    products = load_products(ROOT / "config" / "products.yaml")

    evidence, source_errors = collect_evidence(config, mode)
    benchmark_rows, benchmark_patterns, benchmark_errors = collect_benchmark(config, mode)
    source_errors += benchmark_errors
    canonical = normalize_topics(config["canonical_topics"], evidence)
    candidates = build_candidates(canonical, evidence, model_version=config.get("version", "m2-v1"))
    if len(candidates) != 20:
        raise RuntimeError(f"Expected exactly 20 M2 candidates, got {len(candidates)}")

    ranked = rank_candidates(candidates, scoring)
    top5 = route_top_candidates(ranked[: scoring["thresholds"]["shortlist_count"]], products)
    for item in top5:
        item["status"] = "shortlisted"
    top5[0]["status"] = "selected"

    production_spec = build_production_spec(top5[0], products)
    production_spec.setdefault("metadata", {})["youtube_benchmark"] = advisory_for_product(
        benchmark_patterns,
        top5[0]["product"],
    )
    qa_report = build_qa_report(production_spec, scoring["thresholds"]["originality_minimum"])
    validate(production_spec, json.loads((ROOT / "schemas" / "production_spec.schema.json").read_text()))
    validate(qa_report, json.loads((ROOT / "schemas" / "qa_report.schema.json").read_text()))

    out = ROOT / "data" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "raw_evidence.json", evidence)
    _write(out / "youtube_benchmark.json", benchmark_rows)
    _write(out / "benchmark_patterns.json", benchmark_patterns)
    _write(out / "canonical_topics.json", canonical)
    _write(out / "candidates.json", ranked)
    _write(out / "top5.json", top5)
    _write(out / "production_spec.json", production_spec)
    _write(out / "qa_report.json", qa_report)
    summary = {
        "run_id": run_id, "pipeline_version": "M2", "signal_model_version": config.get("version", "m2-v1"), "mode": mode,
        "raw_evidence_count": len(evidence), "candidate_count": len(ranked),
        "shortlist_count": len(top5), "selected_topic_id": top5[0]["id"],
        "selected_product": top5[0]["product"], "qa_passed": qa_report["passed"],
        "benchmark_sample_count": len(benchmark_rows),
        "benchmark_products": sum(1 for value in benchmark_patterns.values() if value["sample_count"] > 0),
        "source_errors": source_errors, "final_status": "AWAITING_APPROVAL",
    }
    _write(out / "run_summary.json", summary)
    return out
