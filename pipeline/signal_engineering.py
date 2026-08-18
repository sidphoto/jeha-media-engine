"""Convert M2 evidence into M1-compatible 0-100 candidate signals."""
from __future__ import annotations


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def build_candidates(canonical_topics: list[dict], evidence: list[dict], model_version: str = "m2-v1") -> list[dict]:
    by_id = {row["id"]: row for row in evidence}
    candidates = []
    for index, topic in enumerate(canonical_topics, start=1):
        rows = [by_id[eid] for eid in topic.get("evidence_ids", []) if eid in by_id]
        if not rows:
            raise RuntimeError(f"Canonical topic {topic['key']} has no market evidence")
        trends = [row for row in rows if row.get("source") == "google_trends"]
        youtube = [row for row in rows if row.get("source") == "youtube"]

        trend_values = [float(row["raw_value"]) for row in trends if isinstance(row.get("raw_value"), (int, float)) and not isinstance(row.get("raw_value"), bool)]
        growth_values = [float(row["growth_rate"]) for row in trends if isinstance(row.get("growth_rate"), (int, float)) and not isinstance(row.get("growth_rate"), bool)]
        views = [float(row["views"]) for row in youtube if isinstance(row.get("views"), (int, float)) and not isinstance(row.get("views"), bool)]

        youtube_velocity = sum(min(100.0, (v / 250000.0) * 100.0) for v in views) / len(views) if views else None
        if trend_values and youtube_velocity is not None:
            search_demand = _clamp((sum(trend_values) / len(trend_values)) * 0.65 + youtube_velocity * 0.35)
        elif trend_values:
            search_demand = _clamp(sum(trend_values) / len(trend_values))
        elif youtube_velocity is not None:
            search_demand = _clamp(youtube_velocity)
        else:
            search_demand = 0.0
        recent_growth = _clamp(50 + (sum(growth_values) / len(growth_values)) * 200) if growth_values else 0.0

        tags = set(topic.get("tags", []))
        long_session = 92 if tags & {"sleep", "rain", "white_noise", "ocean", "forest"} else 84
        returning = 90 if tags & {"coding", "study", "sleep", "focus"} else 82
        brand_fit = 96 if topic.get("product_hint") in {"flow_room", "moon_room"} else 90
        production_cost = 25 if tags & {"rain", "white_noise"} else 35
        competition = _clamp(35 + min(45, len(youtube) * 8) + max(0, search_demand - 70) * 0.25)

        product_code = topic.get("product_hint", "unknown").split("_")[0].upper()
        signals = {
            "search_demand": search_demand,
            "recent_growth": recent_growth,
            "historical_performance": 0,
            "returning_viewer_potential": returning,
            "long_session_potential": long_session,
            "brand_fit": brand_fit,
            "production_cost": production_cost,
            "competition": competition,
        }
        candidates.append({
            "id": f"TOPIC-{product_code}-{index:06d}",
            "title": topic["title"],
            "tags": topic.get("tags", []),
            "signals": signals,
            "signal_model_version": model_version,
            "signal_provenance": {
                "search_demand": {"evidence_ids": [row["id"] for row in trends + youtube], "policy": "trends_plus_youtube_or_available_source"},
                "recent_growth": {"evidence_ids": [row["id"] for row in trends], "status": "observed" if growth_values else "unavailable_zero"},
                "historical_performance": {"status": "unavailable", "policy": "zero_unavailable"},
                "returning_viewer_potential": {"rule": "intent prior", "tags": sorted(tags)},
                "long_session_potential": {"rule": "long-session intent prior", "tags": sorted(tags)},
                "brand_fit": {"rule": "JEHA product-fit prior", "product_hint": topic.get("product_hint")},
                "production_cost": {"rule": "M2 v1 production-complexity prior", "tags": sorted(tags)},
                "competition": {"evidence_ids": [row["id"] for row in youtube], "rule": "content-density plus demand"},
            },
            "source_trace": {"type": "m2_market_evidence", "evidence_ids": topic.get("evidence_ids", [])},
            "canonical_key": topic["key"],
            "status": "candidate",
        })
    return candidates
