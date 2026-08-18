from __future__ import annotations

from pathlib import Path

from pipeline.google_trends import collect_fixture as collect_trends_fixture
from pipeline.intelligence import collect_evidence, load_intelligence_config, run_intelligence_pipeline
from pipeline.normalizer import normalize_topics
from pipeline.signal_engineering import build_candidates

ROOT = Path(__file__).resolve().parents[1]


def test_google_trends_fixture_is_traceable_and_deterministic():
    config = load_intelligence_config()
    first = collect_trends_fixture(config["seeds"], config["trends_windows"])
    second = collect_trends_fixture(config["seeds"], config["trends_windows"])
    assert first == second
    assert len(first) == 24
    assert {row["window"] for row in first} == {"7d", "30d", "90d"}
    assert all(row["source"] == "google_trends" and row["source_trace"] for row in first)


def test_m2_normalization_and_signal_contract():
    config = load_intelligence_config()
    evidence, errors = collect_evidence(config, "fixture")
    assert errors == []
    assert len(evidence) >= 50
    canonical = normalize_topics(config["canonical_topics"], evidence)
    assert len(canonical) == 20
    assert len({item["key"] for item in canonical}) == 20
    candidates = build_candidates(canonical, evidence)
    assert len(candidates) == 20
    for candidate in candidates:
        assert set(candidate["signals"]) == {
            "search_demand", "recent_growth", "historical_performance",
            "returning_viewer_potential", "long_session_potential", "brand_fit",
            "production_cost", "competition",
        }
        assert all(0 <= value <= 100 for value in candidate["signals"].values())
        assert candidate["signal_provenance"]["historical_performance"]["status"] == "unavailable"


def test_normalizer_deduplicates_variants_to_canonical_identity():
    catalog = [{"key": "rainy_coding", "title": "Rainy Coding Music", "tags": ["coding", "rain"], "product_hint": "flow_room"}]
    evidence = [
        {"id": "a", "source": "youtube", "title": "Coding Music Rain"},
        {"id": "b", "source": "youtube", "title": "Rain Sounds for Coding"},
    ]
    result = normalize_topics(catalog, evidence)
    assert len(result) == 1
    assert result[0]["key"] == "rainy_coding"
    assert result[0]["evidence_ids"] == ["a", "b"]


def test_full_m2_fixture_pipeline_reuses_m1_and_stops_at_human_gate(tmp_path, monkeypatch):
    import pipeline.intelligence as intelligence
    monkeypatch.setattr(intelligence, "ROOT", tmp_path)
    # Recreate required config/schema inputs by pointing those reads at repository through wrapped loaders.
    monkeypatch.setattr(intelligence, "load_intelligence_config", lambda path=None: load_intelligence_config(ROOT / "config" / "intelligence.yaml"))
    from pipeline.score import load_scoring_config as real_score
    from pipeline.router import load_products as real_products
    monkeypatch.setattr(intelligence, "load_scoring_config", lambda path: real_score(ROOT / "config" / "scoring.yaml"))
    monkeypatch.setattr(intelligence, "load_products", lambda path: real_products(ROOT / "config" / "products.yaml"))
    # schema validation paths still use ROOT, so copy minimal files.
    (tmp_path / "schemas").mkdir()
    for name in ("production_spec.schema.json", "qa_report.schema.json"):
        (tmp_path / "schemas" / name).write_text((ROOT / "schemas" / name).read_text())
    out = run_intelligence_pipeline("m2-test", "fixture")
    import json
    summary = json.loads((out / "run_summary.json").read_text())
    top5 = json.loads((out / "top5.json").read_text())
    assert summary["raw_evidence_count"] >= 50
    assert summary["candidate_count"] == 20
    assert summary["shortlist_count"] == 5
    assert summary["final_status"] == "AWAITING_APPROVAL"
    assert len(top5) == 5
    assert all(item["source_trace"]["type"] == "m2_market_evidence" for item in top5)
