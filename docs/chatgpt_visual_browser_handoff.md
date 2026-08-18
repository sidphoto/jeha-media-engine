# ChatGPT Visual Browser Handoff

This contract is intentionally provider-facing and read/write neutral with respect to the repository.

## Input

A handoff record produced by `pipeline.visual_candidates.build_candidate_handoffs`.

Required execution inputs:

- exact `prompt`
- exact `prompt_hash`
- `candidate_role`
- `product`
- expected `aspect_ratio=16:9`

## Browser operator behavior

1. Open the authenticated ChatGPT image-generation surface.
2. Submit the exact prompt without silently rewriting the JEHA house-style constraints.
3. Generate one image for the requested candidate role.
4. Save the image outside the repository credential/session boundary.
5. Compute SHA-256 over the actual saved bytes.
6. Return `artifact_path` and `content_hash` to the JEHA candidate record.
7. Do not mark the image selected or production-ready; Visual QA owns that decision.

## Prohibited persistence

Never commit or register:

- ChatGPT cookies
- browser profile secrets
- session tokens
- passwords
- account identifiers used as credentials

## Failure semantics

Browser/UI failure, login expiry, quota limits, challenge pages, or generation failure must be surfaced as execution errors. The operator must not silently switch providers or substitute a different prompt.

## Future automation

A Chrome-capable Codex/browser agent can implement this contract. The automation layer should remain replaceable because browser UI selectors and session behavior are unstable compared with API contracts.
