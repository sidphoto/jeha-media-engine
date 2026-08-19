# JEHA Media Engine Architecture

## Purpose

JEHA Media Engine is the shared content-production system for JEHA companion-media products.

## Product lines

- Flow Room: focus, study, coding, Pomodoro
- Moon Room: sleep, calm, rain, night
- Cozy Room: cafe, reading, jazz, lifestyle
- Nature Room: rain, forest, ocean, environmental sound

## MVP pipeline

Research -> Topic Scoring -> Product Router -> Production Spec -> QA Gate -> Human Approval

## Phase 2

Add asset generation, FFmpeg rendering, YouTube private upload, scheduling, and analytics feedback.

### Browser-bound music generation

Gemini web Music is the default live music provider. The repository owns the
deterministic handoff prompt, lineage hash, local artifact verification, and
asset registration; an authenticated browser operator owns the Gemini UI
generation and MP3 download. The two boundaries are explicit:

```text
Production Spec
  -> music_handoff.json
  -> Gemini web browser generation
  -> verified local MP3
  -> MUSIC asset record
```

No browser cookies, session tokens, or private endpoints are persisted in the
repository. ElevenLabs is retained only as an explicit legacy fallback until a
separate removal decision is approved.

## Governance

Public publishing must remain behind Human Approval until the system has stable QA, copyright records, and originality controls.
