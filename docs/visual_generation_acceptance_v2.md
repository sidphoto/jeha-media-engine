# JEHA Visual v2 Acceptance Checklist

Aegis L2:
- exactly three deterministic candidates
- candidate roles are primary / alt_a / alt_b
- product preset mapping is correct
- all prompts include 16:9 and negative guidance
- browser handoff performs no remote call from repository code
- prompt hash is stable and bound to topic/spec/product/role/style/prompt
- generated result requires actual artifact path and SHA-256
- Visual QA hard-fails pseudo-text and other critical defects

Sentinel L3:
- no secret/session persistence path
- no silent provider fallback
- no unrelated three-image randomization
- no stale prompt lineage after artifact attachment
- no NaN/Infinity score bypass
- existing M3/M4 lineage remains compatible

Orion:
- safe to merge without requiring Gemini billing
- M4 still consumes only QA-approved final visual assets
