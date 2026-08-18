"""M3 asset identity, registry, provenance, and fixture records."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]

PREFIX = {"music": "MUSIC", "visual": "VISUAL", "sfx": "SFX"}


def content_hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def make_asset_id(asset_type: str, namespace: str, sequence: int) -> str:
    if asset_type not in PREFIX:
        raise ValueError(f"Unsupported asset_type: {asset_type}")
    clean = namespace.upper().replace("-", "_")
    if not clean or sequence < 1:
        raise ValueError("namespace must be non-empty and sequence must be >= 1")
    return f"{PREFIX[asset_type]}-{clean}-{sequence:06d}"


@dataclass
class AssetRegistry:
    records: dict[str, dict] = field(default_factory=dict)

    def register(self, record: dict) -> dict:
        schema = json.loads((ROOT / "schemas" / "asset.schema.json").read_text(encoding="utf-8"))
        validate(record, schema)
        asset_id = record["asset_id"]
        if asset_id in self.records:
            raise ValueError(f"Duplicate asset_id: {asset_id}")
        if not record["rights"]["commercial_use"]:
            raise ValueError(f"Asset is not cleared for commercial use: {asset_id}")
        self.records[asset_id] = record
        return record

    def by_topic(self, topic_id: str) -> list[dict]:
        return [self.records[key] for key in sorted(self.records) if self.records[key]["topic_id"] == topic_id]

    def to_list(self) -> list[dict]:
        return [self.records[key] for key in sorted(self.records)]


def build_fixture_asset(
    *, asset_type: str, namespace: str, sequence: int, topic_id: str,
    prompt_or_source: str, technical: dict, production_spec_ref: str | None = None,
) -> dict:
    """Create deterministic metadata-only fixture asset for CI/contract testing."""
    asset_id = make_asset_id(asset_type, namespace, sequence)
    seed_payload = json.dumps({
        "asset_id": asset_id, "topic_id": topic_id, "prompt_or_source": prompt_or_source,
        "technical": technical,
    }, sort_keys=True).encode()
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "topic_id": topic_id,
        "production_spec_ref": production_spec_ref,
        "provider": "jeha_fixture",
        "model": "fixture-v1",
        "provider_version": "1",
        "prompt_or_source": prompt_or_source,
        "created_at": "2026-08-18T00:00:00+00:00",
        "content_hash": content_hash(seed_payload),
        "rights": {"commercial_use": True, "license": "JEHA_TEST_FIXTURE_ONLY", "source_url": None},
        "technical": technical,
        "qa_status": "pending",
    }
