"""M2 YouTube market-evidence collector."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from pipeline.http_utils import request_json


def collect_fixture(topics: list[dict], collected_at: str = "2026-08-18T00:00:00+00:00") -> list[dict]:
    rows = []
    for ti, topic in enumerate(topics):
        for variant in range(2):
            age_days = 3 + ((ti * 5 + variant * 7) % 60)
            views = 12000 + ((ti * 17321 + variant * 8191) % 480000)
            channel_size = 20000 + ((ti * 29111 + variant * 5003) % 900000)
            rows.append({
                "id": f"yt-{ti:02d}-{variant}", "source": "youtube",
                "query": topic["title"], "canonical_key": topic["key"],
                "title": f"{topic['title']} | {'Extended' if variant else 'Ambient'}",
                "channel": f"fixture-channel-{ti % 7}", "published_at": f"2026-07-{(ti % 27)+1:02d}T00:00:00Z",
                "views": views, "channel_size": channel_size, "age_days": age_days,
                "keywords": topic["tags"], "collected_at": collected_at,
                "source_trace": {"mode": "fixture", "video_id": f"fixture-{ti:02d}-{variant}"},
            })
    return rows


def collect_live(queries: list[str], region: str = "TW", max_results: int = 10, cache_dir: Path | None = None) -> list[dict]:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YouTube live mode requires YOUTUBE_API_KEY")
    collected_at = datetime.now(timezone.utc).isoformat()
    out = []
    for query in queries:
        params = urlencode({"part": "snippet", "q": query, "type": "video", "maxResults": max_results, "regionCode": region, "key": key})
        search = request_json(f"https://www.googleapis.com/youtube/v3/search?{params}", cache_dir=cache_dir, cache_ttl_seconds=1800, retries=2)
        ids = [item["id"]["videoId"] for item in search.get("items", []) if item.get("id", {}).get("videoId")]
        stats = {}
        if ids:
            vparams = urlencode({"part": "statistics,snippet", "id": ",".join(ids), "key": key})
            details = request_json(f"https://www.googleapis.com/youtube/v3/videos?{vparams}", cache_dir=cache_dir, cache_ttl_seconds=1800, retries=2)
            for item in details.get("items", []):
                stats[item["id"]] = item
        for item in search.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            detail = stats.get(video_id, {})
            snippet = detail.get("snippet", item.get("snippet", {}))
            out.append({
                "id": f"yt-live-{video_id}", "source": "youtube", "query": query,
                "title": snippet.get("title", ""), "channel": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt"), "views": int(detail.get("statistics", {}).get("viewCount", 0)),
                "channel_size": None, "age_days": None, "keywords": [], "collected_at": collected_at,
                "source_trace": {"mode": "live", "video_id": video_id},
            })
    return out
