"""M1 QA checklist for production planning outputs."""

from __future__ import annotations

import math


def build_qa_report(production_spec: dict, originality_minimum: float) -> dict:
    metadata = production_spec.get("metadata", {})
    brand_fit = metadata.get("brand_fit")
    brand_fit_passed = (
        isinstance(brand_fit, (int, float))
        and not isinstance(brand_fit, bool)
        and math.isfinite(brand_fit)
        and 0 < brand_fit <= 100
    )
    checks = [
        {
            "id": "originality",
            "label": "Originality target meets minimum",
            "passed": production_spec.get("originality_target", 0) >= originality_minimum,
            "evidence": {
                "target": production_spec.get("originality_target"),
                "minimum": originality_minimum,
            },
        },
        {
            "id": "metadata_completeness",
            "label": "Required planning metadata is present",
            "passed": all(metadata.get(key) for key in ("working_title", "product_name", "purpose", "tags")),
            "evidence": {"required": ["working_title", "product_name", "purpose", "tags"]},
        },
        {
            "id": "brand_fit",
            "label": "Candidate has a positive JEHA brand-fit signal",
            "passed": brand_fit_passed,
            "evidence": {
                "brand_fit": brand_fit,
                "valid_range": "(0, 100]",
            },
        },
        {
            "id": "source_traceability",
            "label": "Candidate source is traceable",
            "passed": bool(metadata.get("source_trace", {}).get("reference")),
            "evidence": metadata.get("source_trace", {}),
        },
    ]
    return {
        "topic_id": production_spec["topic_id"],
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "status": "complete",
    }
