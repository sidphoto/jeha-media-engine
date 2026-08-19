# Gemini Web Music Handoff

JEHA's live music default is `gemini_web`. This contract keeps browser
automation outside repository code while preserving deterministic lineage.

## Stage A — Prepare

Run M3 live with no `JEHA_GEMINI_WEB_MUSIC_ARTIFACT`. The provider writes:

```text
data/asset_runs/<run-id>/music_handoff.json
```

The handoff contains the exact prompt, `prompt_hash`, preferred model
(`3.7 Flash` by default), output format (`mp3`), and the required audio-only
download selection. Its status is
`AWAITING_GEMINI_WEB_MUSIC_GENERATION`.

## Stage B — Browser execution

Use the `gemini-web-music-generation` skill with the handoff's exact prompt.
The operator must:

1. Select `3.7 Flash` when it is visible, or record the exact capable fallback
   mode shown in the live picker.
2. Verify that the selected mode exposes Music; capability takes precedence
   over an unavailable model label.
3. Generate the track and verify a player with a non-zero duration.
4. Choose audio-only MP3, confirm Chrome reports the download as complete, and
   retain the absolute local artifact path.

The operator must not edit the prompt, switch providers silently, or persist
browser cookies, session tokens, or credentials.

## Stage C — Attach

Set the following for a new live M3 run:

```bash
export JEHA_MUSIC_PROVIDER="gemini_web"
export JEHA_GEMINI_WEB_MUSIC_ARTIFACT="/absolute/path/to/downloaded.mp3"
export JEHA_GEMINI_WEB_MUSIC_MODEL="<exact live picker label>"
export JEHA_GEMINI_WEB_MUSIC_HANDOFF="data/asset_runs/<handoff-run>/music_handoff.json"
export JEHA_GEMINI_WEB_MUSIC_COMMERCIAL_USE_ACK="true"
```

The attach provider checks the handoff lineage, reads MP3 metadata with
`ffprobe`, copies (never moves) the file into
`data/generated_assets/music/`, computes SHA-256, and records the actual
model label. It refuses missing terms acknowledgement, stale prompts, invalid
MP3 metadata, and conflicting artifact overwrites.

`JEHA_GEMINI_WEB_MUSIC_COMMERCIAL_USE_ACK=true` is a human gate, not a claim
that every Gemini output is automatically cleared for commercial use. Review
the applicable Google/Gemini terms before setting it.
