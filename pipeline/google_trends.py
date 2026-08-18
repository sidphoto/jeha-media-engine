"""M2 Google Trends collector with deterministic fixture and opt-in alpha API adapter."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request

from pipeline.http_utils import request_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_fixture(seeds: list[str], windows: list[str], collected_at: str = "2026-08-18T00:00:00+00:00") -> list[dict]:
    evidence = []
    for si, keyword in enumerate(seeds):
        for wi, window in enumerate(windows):
            raw = 45 + ((si * 13 + wi * 11) % 51)
            growth = round((((si + 1) * (wi + 2)) % 19 - 5) / 100, 3)
            evidence.append({
                "id": f"gt-{si:02d}-{wi:02d}", "source": "google_trends", "keyword": keyword,
                "window": window, "raw_value": raw, "growth_rate": growth,
                "collected_at": collected_at, "source_trace": {"mode": "fixture", "seed_index": si},
            })
    return evidence


def collect_live(seeds: list[str], windows: list[str], cache_dir: Path | None = None) -> list[dict]:
    """Call a Google Trends API alpha endpoint supplied to approved testers.

    Google currently limits the official Trends API to alpha testers. Deployment provides
    its approved endpoint/token through environment variables; no credential is committed.
    """
    endpoint = os.getenv("GOOGLE_TRENDS_API_URL")
    token = os.getenv("GOOGLE_TRENDS_API_TOKEN")
    if not endpoint or not token:
        raise RuntimeError("Google Trends live mode requires GOOGLE_TRENDS_API_URL and GOOGLE_TRENDS_API_TOKEN")
    payload = json.dumps({"keywords": seeds, "windows": windows}).encode()
    req = Request(endpoint, data=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    data = request_json(req, cache_dir=cache_dir, cache_ttl_seconds=3600, retries=2)
    out = []
    collected_at = _now()
    for index, item in enumerate(data.get("observations", [])):
        out.append({
            "id": f"gt-live-{index:04d}", "source": "google_trends", "keyword": item["keyword"],
            "window": item["window"], "raw_value": item["raw_value"],
            "growth_rate": item.get("growth_rate"), "collected_at": collected_at,
            "source_trace": {"mode": "live", "endpoint": endpoint},
        })
    return out
