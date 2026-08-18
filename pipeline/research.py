"""Deterministic local candidate generation for M1."""

from __future__ import annotations

from copy import deepcopy


SEED_CANDIDATES = [
    ("deep-focus-coding-rain", "Deep Focus Coding with Soft Rain", ["focus", "coding", "rain", "deep_work"], [92, 82, 86, 91, 90, 94, 78, 72]),
    ("night-rain-sleep", "Night Rain for Deep Sleep", ["sleep", "rain", "night", "calm"], [95, 80, 90, 88, 96, 93, 82, 70]),
    ("cozy-cafe-reading", "Cozy Café Reading Session", ["cafe", "reading", "cozy", "weekend"], [86, 76, 84, 89, 82, 92, 76, 74]),
    ("forest-white-noise", "Forest White Noise for Rest", ["forest", "white_noise", "relaxation"], [84, 72, 81, 83, 91, 90, 88, 78]),
    ("pomodoro-lofi", "Pomodoro Focus Room", ["pomodoro", "focus", "study"], [89, 79, 88, 90, 87, 95, 84, 68]),
    ("moon-calm-piano", "Moonlit Calm Piano for Sleep", ["sleep", "calm", "night"], [83, 75, 80, 84, 90, 91, 74, 82]),
    ("ocean-ambience", "Slow Ocean Ambience", ["ocean", "relaxation"], [81, 73, 79, 82, 92, 89, 90, 76]),
    ("weekend-jazz-cafe", "Weekend Jazz Café", ["jazz", "cafe", "weekend", "cozy"], [85, 77, 82, 88, 80, 90, 70, 73]),
    ("study-library", "Quiet Library Study Room", ["study", "focus", "reading"], [82, 71, 83, 86, 85, 94, 89, 80]),
    ("fireplace-night", "Fireplace Night Ambience", ["fireplace", "night", "cozy"], [80, 69, 78, 84, 91, 88, 86, 81]),
    ("rain-window-reading", "Rainy Window Reading Room", ["rain", "reading", "cozy"], [87, 78, 85, 89, 88, 93, 80, 71]),
    ("deep-work-minimal", "Minimal Deep Work Soundscape", ["deep_work", "focus", "coding"], [88, 74, 86, 87, 89, 96, 92, 77]),
    ("brown-noise-sleep", "Brown Noise Sleep Room", ["sleep", "white_noise", "calm"], [90, 83, 87, 85, 95, 89, 94, 67]),
    ("morning-cafe-focus", "Morning Café Focus", ["cafe", "focus", "cozy"], [79, 70, 77, 85, 78, 91, 81, 84]),
    ("forest-rain", "Forest Rain Ambience", ["forest", "rain", "relaxation"], [91, 81, 89, 86, 94, 92, 91, 69]),
    ("coding-night", "Late Night Coding Room", ["coding", "night", "focus"], [84, 79, 82, 88, 86, 95, 85, 75]),
    ("ocean-sleep", "Ocean Waves for Sleep", ["ocean", "sleep", "calm"], [88, 74, 86, 87, 95, 90, 90, 72]),
    ("soft-jazz-reading", "Soft Jazz Reading Lounge", ["jazz", "reading", "cozy"], [80, 68, 79, 86, 79, 91, 72, 83]),
    ("rain-pomodoro", "Rainy Pomodoro Study", ["rain", "pomodoro", "study", "focus"], [90, 82, 88, 91, 90, 96, 86, 66]),
    ("quiet-fireplace", "Quiet Fireplace for Relaxation", ["fireplace", "relaxation", "cozy"], [78, 67, 76, 81, 88, 87, 89, 85]),
]

SIGNAL_NAMES = [
    "search_demand",
    "recent_growth",
    "historical_performance",
    "returning_viewer_potential",
    "long_session_potential",
    "brand_fit",
    "production_cost",
    "competition",
]


def generate_candidates() -> list[dict]:
    """Return exactly 20 reproducible candidates with normalized 0-100 signals."""
    candidates = []
    for index, (slug, title, tags, values) in enumerate(SEED_CANDIDATES, start=1):
        candidates.append(
            {
                "id": f"topic-{index:02d}-{slug}",
                "title": title,
                "tags": list(tags),
                "signals": dict(zip(SIGNAL_NAMES, values, strict=True)),
                "source_trace": {
                    "type": "curated_seed",
                    "reference": f"m1-seed:{slug}",
                },
                "status": "candidate",
            }
        )
    if len(candidates) != 20:
        raise RuntimeError("M1 requires exactly 20 candidates")
    return deepcopy(candidates)
