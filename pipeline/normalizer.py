"""M2 deterministic topic normalization and evidence lineage."""
from __future__ import annotations

import re

NORMALIZATION_VERSION = "m2-normalizer-v1"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def normalize_topics(catalog: list[dict], evidence: list[dict]) -> list[dict]:
    """Resolve raw evidence to stable canonical identities using versioned rules."""
    by_key = {
        topic["key"]: {**topic, "normalization_version": NORMALIZATION_VERSION, "evidence_ids": [], "variants": []}
        for topic in catalog
    }
    topic_tokens = {key: _tokens(item["title"] + " " + " ".join(item.get("tags", []))) for key, item in by_key.items()}
    for row in evidence:
        key = row.get("canonical_key")
        if key not in by_key:
            text = " ".join(str(row.get(field, "")) for field in ("query", "keyword", "title"))
            tokens = _tokens(text)
            ranked = sorted(
                ((len(tokens & wanted), candidate) for candidate, wanted in topic_tokens.items()),
                key=lambda x: (-x[0], x[1]),
            )
            key = ranked[0][1] if ranked and ranked[0][0] > 0 else None
        if key:
            by_key[key]["evidence_ids"].append(row["id"])
            variant = row.get("title") or row.get("keyword") or row.get("query")
            if variant and variant not in by_key[key]["variants"]:
                by_key[key]["variants"].append(variant)
    return [by_key[key] for key in sorted(by_key)]
