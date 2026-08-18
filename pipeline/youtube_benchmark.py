"""YouTube benchmark intelligence for JEHA companion-content patterns.

Benchmarking extracts repeatable market patterns rather than copying competitor assets.
Fixture mode is deterministic and network-free; live mode uses the YouTube Data API when
`YOUTUBE_API_KEY` is configured.
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from pipeline.http_utils import request_json

PRODUCT_QUERIES = {
    "flow_room": "study focus pomodoro lofi ambience",
    "moon_room": "sleep rain night ambience relaxation",
    "cozy_room": "cozy cafe jazz fireplace reading ambience",
    "nature_room": "nature sounds rain forest ocean ambience",
}

TITLE_TERMS = (
    "study", "focus", "pomodoro", "lofi", "coding",
    "sleep", "rain", "night", "moon", "calm",
    "cozy", "cafe", "jazz", "fireplace", "reading",
    "nature", "forest", "ocean", "stream", "sounds",
)

SCENE_CUES = {
    "flow_room": ["rainy desk", "coding room", "study workspace"],
    "moon_room": ["moonlit cabin", "rainy bedroom", "dark night landscape"],
    "cozy_room": ["reading corner", "warm cafe", "fireplace room"],
    "nature_room": ["misty forest", "ocean coast", "forest stream"],
}

AUDIO_CUES = {
    "flow_room": ["instrumental", "soft rhythm", "rain optional"],
    "moon_room": ["slow ambient", "rain", "low stimulation"],
    "cozy_room": ["soft jazz", "piano", "fireplace optional"],
    "nature_room": ["environmental sound", "rain", "ocean or forest"],
}


def _duration_seconds(value: str | None) -> int | None:
    """Parse the H/M/S subset of ISO-8601 durations returned by YouTube."""
    if not value:
        return None
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _duration_bucket(duration_minutes: float | int | None) -> str:
    if duration_minutes is None:
        return "unknown"
    if duration_minutes < 60:
        return "under_1h"
    if duration_minutes < 240:
        return "1h_to_4h"
    if duration_minutes < 480:
        return "4h_to_8h"
    return "8h_plus"


def _title_terms(title: str) -> list[str]:
    lower = title.lower()
    return [term for term in TITLE_TERMS if term in lower]


def collect_fixture(collected_at: str = "2026-08-18T00:00:00+00:00") -> list[dict]:
    """Create deterministic synthetic benchmark examples for all four JEHA products."""
    templates = {
        "flow_room": [
            ("Deep Focus Study Ambience with Rain", 180, 2_400_000, 500),
            ("Pomodoro Focus Session for Study", 120, 1_300_000, 300),
            ("Lofi Coding Focus Ambience", 240, 1_800_000, 420),
        ],
        "moon_room": [
            ("Sleep Rain Night Ambience", 480, 5_500_000, 700),
            ("Calm Night Sleep Music", 720, 7_800_000, 900),
            ("Moon Rain Sleep Ambience", 600, 4_200_000, 600),
        ],
        "cozy_room": [
            ("Cozy Cafe Jazz Reading Ambience", 180, 2_700_000, 450),
            ("Fireplace Jazz Cozy Evening", 240, 2_100_000, 400),
            ("Warm Reading Cafe Ambience", 360, 1_900_000, 360),
        ],
        "nature_room": [
            ("Forest Rain Nature Sounds", 480, 6_100_000, 800),
            ("Ocean Sounds for Relaxation", 600, 5_800_000, 750),
            ("Misty Forest Stream Sounds", 720, 4_900_000, 680),
        ],
    }
    rows = []
    for product, examples in templates.items():
        for index, (title, duration_minutes, views, age_days) in enumerate(examples):
            rows.append({
                "id": f"benchmark-{product}-{index}",
                "product": product,
                "title": title,
                "channel": f"fixture-benchmark-{index}",
                "video_id": f"fixture-{product}-{index}",
                "published_at": None,
                "views": views,
                "age_days": age_days,
                "views_per_day": round(views / max(age_days, 1), 2),
                "duration_minutes": duration_minutes,
                "duration_bucket": _duration_bucket(duration_minutes),
                "title_terms": _title_terms(title),
                "collected_at": collected_at,
                "source_trace": {"mode": "fixture", "synthetic": True},
            })
    return rows


def collect_live(
    *,
    region: str = "TW",
    max_results: int = 10,
    cache_dir: Path | None = None,
    now: datetime | None = None,
) -> list[dict]:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YouTube benchmark live mode requires YOUTUBE_API_KEY")
    now = now or datetime.now(timezone.utc)
    collected_at = now.isoformat()
    rows: list[dict] = []

    for product, query in PRODUCT_QUERIES.items():
        params = urlencode({
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "maxResults": max_results,
            "regionCode": region,
            "key": key,
        })
        search = request_json(
            f"https://www.googleapis.com/youtube/v3/search?{params}",
            cache_dir=cache_dir,
            cache_ttl_seconds=1800,
            retries=2,
        )
        ids = [
            item.get("id", {}).get("videoId")
            for item in search.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not ids:
            continue
        details_params = urlencode({
            "part": "statistics,snippet,contentDetails",
            "id": ",".join(ids),
            "key": key,
        })
        details = request_json(
            f"https://www.googleapis.com/youtube/v3/videos?{details_params}",
            cache_dir=cache_dir,
            cache_ttl_seconds=1800,
            retries=2,
        )
        for item in details.get("items", []):
            snippet = item.get("snippet", {})
            published_at = snippet.get("publishedAt")
            age_days = None
            if published_at:
                try:
                    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    age_days = max((now - published).days, 0)
                except ValueError:
                    age_days = None
            raw_views = item.get("statistics", {}).get("viewCount")
            views = int(raw_views) if raw_views is not None else None
            seconds = _duration_seconds(item.get("contentDetails", {}).get("duration"))
            duration_minutes = round(seconds / 60, 2) if seconds is not None else None
            rows.append({
                "id": f"benchmark-live-{item.get('id')}",
                "product": product,
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "video_id": item.get("id"),
                "published_at": published_at,
                "views": views,
                "age_days": age_days,
                "views_per_day": round(views / max(age_days or 1, 1), 2) if views is not None else None,
                "duration_minutes": duration_minutes,
                "duration_bucket": _duration_bucket(duration_minutes),
                "title_terms": _title_terms(snippet.get("title", "")),
                "collected_at": collected_at,
                "source_trace": {"mode": "live", "video_id": item.get("id")},
            })
    return rows


def build_pattern_intelligence(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        product = row.get("product")
        if product in PRODUCT_QUERIES:
            grouped[product].append(row)

    patterns: dict[str, dict] = {}
    for product in PRODUCT_QUERIES:
        product_rows = grouped.get(product, [])
        if not product_rows:
            patterns[product] = {
                "sample_count": 0,
                "preferred_duration_bucket": "unknown",
                "median_views_per_day": None,
                "title_terms": [],
                "scene_cues": SCENE_CUES[product],
                "audio_cues": AUDIO_CUES[product],
            }
            continue

        bucket_score: Counter[str] = Counter()
        term_score: Counter[str] = Counter()
        vpd_values = []
        for row in product_rows:
            vpd = row.get("views_per_day")
            weight = max(float(vpd or 0), 1.0)
            bucket_score[row.get("duration_bucket", "unknown")] += weight
            for term in row.get("title_terms", []):
                term_score[term] += weight
            if vpd is not None:
                vpd_values.append(float(vpd))
        vpd_values.sort()
        median = None
        if vpd_values:
            mid = len(vpd_values) // 2
            median = vpd_values[mid] if len(vpd_values) % 2 else (vpd_values[mid - 1] + vpd_values[mid]) / 2

        patterns[product] = {
            "sample_count": len(product_rows),
            "preferred_duration_bucket": bucket_score.most_common(1)[0][0],
            "median_views_per_day": round(median, 2) if median is not None else None,
            "title_terms": [term for term, _ in term_score.most_common(5)],
            "scene_cues": SCENE_CUES[product],
            "audio_cues": AUDIO_CUES[product],
        }
    return patterns


def advisory_for_product(patterns: dict[str, dict], product: str) -> dict:
    pattern = patterns.get(product)
    if not pattern:
        raise ValueError(f"Unknown or missing benchmark product: {product}")
    return {
        "source": "youtube_benchmark",
        "advisory_only": True,
        "product": product,
        **pattern,
        "guardrail": "Use market patterns as evidence; do not copy competitor titles, thumbnails, audio, or branding.",
    }
