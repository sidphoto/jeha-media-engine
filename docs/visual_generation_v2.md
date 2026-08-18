# JEHA Visual Generation v2

## Production policy

JEHA uses ChatGPT image generation as the primary visual generator. JEHA owns prompt construction, candidate intent, QA, and asset lineage. Paid image APIs are optional fallbacks and are not required for the default visual path.

## Flow

`Production Spec -> Prompt Builder -> 3 browser handoffs -> ChatGPT image generation -> Visual QA -> selected VISUAL asset -> Asset Registry -> M4`

## Candidate policy

Exactly three candidates are created for every topic:

1. `primary` — canonical scene and product composition.
2. `alt_a` — composition exploration only.
3. `alt_b` — atmosphere exploration only.

The system must not create three unrelated concepts.

## House style

Parent style: `jeha_cinematic_dreamy_realism_v2`.

Product presets:

- Flow Room: `jeha_flow_focus_v2`
- Moon Room: `jeha_moon_sleep_v2`
- Cozy Room: `jeha_cozy_warm_v2`
- Nature Room: `jeha_nature_atmospheric_v2`

Reference roles from the first accepted test set:

- Nature Room: house-style reference.
- Flow Room: YouTube functional composition reference.
- Moon Room: product reference; prefer understated sleep cues over spectacle.
- Cozy Room: product reference; readable text and pseudo-text are hard failures.

## Browser execution boundary

The repository creates deterministic handoffs but does not persist ChatGPT login credentials, browser cookies, session tokens, or secrets. A browser-capable operator/agent may execute each handoff externally, save the returned image, compute the artifact SHA-256, and attach that result back to the handoff record.

`remote_execution_allowed=false` means repository code itself does not silently trigger external image generation. This preserves an explicit execution boundary while the browser workflow is being stabilized.

## QA

Weighted score:

- House style: 20
- Product fit: 15
- Long-view comfort: 15
- Composition: 10
- Thumbnail legibility: 10
- Light/color: 10
- AI artifact control: 10
- Motion potential: 5
- Series scalability: 5

Gate:

- `>=85`: PASS
- `80-84`: CONDITIONAL
- `<80`: FAIL

Hard-fail examples include pseudo-text, watermark/logo, major structural artifacts, unknown rights, non-16:9 master, Production Spec mismatch, or missing prompt lineage.

## M4 handoff

Only a QA-passed selected visual becomes a production VISUAL asset. M4 remains responsible for low-stimulation motion, effects, and video assembly; M3 v2 generates the visual master rather than pre-rendering video motion.
