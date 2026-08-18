"""Shared security helpers for JEHA pipeline boundaries.

These helpers deliberately fail closed before credentials are attached, untrusted run IDs
are turned into filesystem paths, or cross-stage JSON enters deeper pipeline logic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import ValidationError, validate

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def validate_run_id(run_id: str) -> str:
    """Return a canonical safe run id or reject path-like/ambiguous values."""
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            "run_id must be 1-128 characters using only letters, digits, '_' or '-', "
            "and must start with a letter or digit"
        )
    return run_id


def safe_run_dir(root: Path, category: str, run_id: str) -> Path:
    """Build a run output directory that is guaranteed to stay below data/<category>."""
    safe_id = validate_run_id(run_id)
    base = (root / "data" / category).resolve()
    out = (base / safe_id).resolve()
    if out.parent != base:
        raise ValueError("run_id resolved outside the configured run directory")
    return out


def validate_https_host(
    url: str,
    *,
    exact_hosts: set[str] | frozenset[str] = frozenset(),
    allowed_suffixes: tuple[str, ...] = (),
    label: str = "endpoint",
) -> str:
    """Validate an HTTPS URL against a credential-safe hostname allowlist.

    Userinfo and non-443 ports are rejected so a Bearer token cannot be redirected to an
    unexpected authority. Suffix entries must include the leading dot, e.g. '.googleapis.com'.
    """
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError(f"{label} URL is required")
    parsed = urlparse(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme.lower() != "https" or not host:
        raise RuntimeError(f"{label} URL must use HTTPS and include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError(f"{label} URL must not contain userinfo")
    if parsed.port not in {None, 443}:
        raise RuntimeError(f"{label} URL must use the default HTTPS port")

    normalized_exact = {item.rstrip(".").lower() for item in exact_hosts}
    suffix_match = any(host.endswith(suffix.lower()) and host != suffix.lstrip(".").lower() for suffix in allowed_suffixes)
    if host not in normalized_exact and not suffix_match:
        raise RuntimeError(f"{label} host is not allowlisted: {host}")
    return url


def load_json_validated(path: str | Path, schema_path: str | Path, *, label: str) -> dict:
    """Load a cross-stage JSON object and reject malformed/schema-invalid data immediately."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} could not be loaded as JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")

    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        validate(payload, schema)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} schema could not be loaded: {exc}") from exc
    except ValidationError as exc:
        path_text = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ValueError(f"{label} schema validation failed at {path_text}: {exc.message}") from exc
    return payload
