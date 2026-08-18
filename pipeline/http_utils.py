"""Small standard-library HTTP helper for M2 live collectors."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(
    request: Request | str,
    *,
    cache_dir: Path | None = None,
    cache_ttl_seconds: int = 3600,
    retries: int = 2,
) -> dict:
    """Fetch JSON with optional file cache and bounded 429/5xx retry handling."""
    req = request if isinstance(request, Request) else Request(request)
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        body = req.data or b""
        cache_key = hashlib.sha256((req.full_url + "\n").encode() + body).hexdigest()
        cache_path = cache_dir / f"{cache_key}.json"
        if cache_path.exists() and time.time() - cache_path.stat().st_mtime <= cache_ttl_seconds:
            return json.loads(cache_path.read_text(encoding="utf-8"))

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=30) as response:  # noqa: S310 - callers provide trusted API endpoints
                data = json.loads(response.read().decode())
            if cache_path is not None:
                cache_path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 4)
            time.sleep(delay)
    assert last_error is not None
    raise last_error
