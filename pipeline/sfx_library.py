"""Local licensed SFX library adapter for JEHA M3.

The library never downloads arbitrary audio. Every production entry must point to a
local file and carry explicit source/license/commercial-use metadata before it can be
registered as an SFX asset.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.assets import make_asset_id
from pipeline.providers import AssetRequest, sequence_from_topic_id

SUPPORTED_SFX = {"rain", "forest", "ocean", "fireplace", "white_noise"}


class LocalSFXLibraryProvider:
    def __init__(self, *, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path)

    def _load_manifest(self) -> list[dict]:
        if not self.manifest_path.exists():
            raise RuntimeError(f"SFX manifest not found: {self.manifest_path}")
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        entries = payload.get("assets") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise RuntimeError("SFX manifest must contain an assets list")
        return entries

    @staticmethod
    def _validate_entry(entry: dict) -> None:
        required = (
            "sfx_type", "path", "source_url", "license", "commercial_use",
            "duration_seconds", "format", "sample_rate", "channels",
        )
        missing = [key for key in required if key not in entry]
        if missing:
            raise RuntimeError(f"SFX entry missing required metadata: {', '.join(missing)}")
        if entry["sfx_type"] not in SUPPORTED_SFX:
            raise RuntimeError(f"Unsupported SFX type: {entry['sfx_type']}")
        if entry["commercial_use"] is not True:
            raise RuntimeError("SFX entry is not cleared for commercial use")
        if not str(entry["license"]).strip() or not str(entry["source_url"]).strip():
            raise RuntimeError("SFX entry requires explicit license and source_url")
        for key in ("duration_seconds", "sample_rate", "channels"):
            value = entry[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise RuntimeError(f"SFX entry has invalid {key}")
        if not str(entry["format"]).strip():
            raise RuntimeError("SFX entry requires format")

    def generate(self, request: AssetRequest) -> dict | None:
        if not request.sfx_type:
            return None
        if request.sfx_type not in SUPPORTED_SFX:
            raise RuntimeError(f"Unsupported requested SFX type: {request.sfx_type}")

        candidates = []
        for entry in self._load_manifest():
            self._validate_entry(entry)
            if entry["sfx_type"] == request.sfx_type:
                candidates.append(entry)
        if not candidates:
            raise RuntimeError(f"No licensed local SFX found for type: {request.sfx_type}")

        # Stable deterministic selection prevents runs from silently changing source assets.
        entry = sorted(candidates, key=lambda item: (item.get("priority", 100), item["path"]))[0]
        path = Path(entry["path"]).expanduser()
        if not path.is_absolute():
            path = (self.manifest_path.parent / path).resolve()
        if not path.is_file():
            raise RuntimeError(f"Licensed SFX file not found: {path}")

        data = path.read_bytes()
        if not data:
            raise RuntimeError(f"Licensed SFX file is empty: {path}")

        asset_id = make_asset_id(
            "sfx",
            request.sfx_type,
            sequence_from_topic_id(request.topic_id),
        )
        return {
            "asset_id": asset_id,
            "asset_type": "sfx",
            "topic_id": request.topic_id,
            "production_spec_ref": request.production_spec_ref,
            "provider": "jeha_local_sfx_library",
            "model": "licensed-file-v1",
            "provider_version": "1",
            "prompt_or_source": entry["source_url"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
            "rights": {
                "commercial_use": True,
                "license": entry["license"],
                "source_url": entry["source_url"],
            },
            "technical": {
                "duration_seconds": entry["duration_seconds"],
                "format": entry["format"],
                "sample_rate": int(entry["sample_rate"]),
                "channels": int(entry["channels"]),
                "artifact_path": str(path),
                "library_entry_id": entry.get("id"),
            },
            "qa_status": "pending",
        }
