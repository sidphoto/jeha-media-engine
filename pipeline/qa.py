"""M1 QA checklist for production planning outputs."""

from __future__ import annotations


def build_qa_report(production_spec: dict, originality_minimum: float) -> dict:
    metadata = production_spec.get("metadata", {})
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
            "passed": bool(metadata.get("product_name")) and metadata.get("candidate_score", 0) > 0,
            "evidence": {
                "product_name": metadata.get("product_name"),
                "candidate_score": metadata.get("candidate_score"),
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
