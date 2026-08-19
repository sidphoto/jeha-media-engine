# JEHA Media Engine

家河（JEHA）旗下陪伴型媒體產品的自動化內容引擎。

## 目標

建立一條可重複執行、可驗收、可逐步自動化的內容生產線：

1. 研究市場與候選題材
2. 為候選題材評分
3. 分流至 Flow Room / Moon Room / Cozy Room / Nature Room
4. 產生 Production Spec
5. 執行 QA / Originality Gate
6. 產生可追蹤的 Music / Visual / optional SFX asset bundle
7. 等待 Human Approval
8. 後續串接 FFmpeg 與 YouTube 發布
9. 將 Analytics 回饋下一輪選題

## Products

- **Flow Room** — Focus / Study / Coding / Pomodoro
- **Moon Room** — Sleep / Calm / Rain / Night
- **Cozy Room** — Café / Reading / Lifestyle
- **Nature Room** — Rain / Forest / Ocean / Environmental sounds

## M1 — deterministic planning pipeline

```text
20 candidates -> score -> Top 5 -> product route -> Top 1 Production Spec -> QA -> AWAITING_APPROVAL
```

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/run_daily_pipeline.py --run-id m1-demo
```

## M2 — Live Topic Intelligence

M2 replaces curated topic selection with traceable market evidence while reusing the M1 scorer/router/planner.

```text
Google Trends + YouTube evidence
  -> Raw Evidence
  -> Normalize / Dedup
  -> exactly 20 candidates
  -> M1 Scoring
  -> Top 5
  -> Production Spec
  -> QA
  -> AWAITING_APPROVAL
```

Deterministic fixture mode (CI-safe, no network):

```bash
python3 scripts/run_intelligence_pipeline.py --run-id m2-demo --mode fixture
```

Outputs include:

```text
data/runs/m2-demo/
├── raw_evidence.json
├── canonical_topics.json
├── candidates.json
├── top5.json
├── production_spec.json
├── qa_report.json
└── run_summary.json
```

Live mode:

```bash
export YOUTUBE_API_KEY="..."
# Google Trends official API remains limited-access alpha. Approved testers may also set:
export GOOGLE_TRENDS_API_URL="..."
export GOOGLE_TRENDS_API_TOKEN="..."
python3 scripts/run_intelligence_pipeline.py --run-id m2-live --mode live
```

Live sources are isolated: one source may fail and be reported in `source_errors`; the run only continues when enough traceable evidence remains. API responses use bounded retry/rate-limit handling and a local cache. Credentials are never written to repository files.

Missing JEHA historical performance is represented as numeric `0` only because the M1 scorer requires a number; provenance explicitly marks it `unavailable` / `zero_unavailable`, so the value is never presented as observed history.

## M3 — Asset Generation

M3 consumes a Production Spec and produces deterministic, traceable asset records for music, visuals, and optional environmental SFX.

```text
Production Spec
  -> Music / Visual / optional SFX providers
  -> Asset Registry
  -> Asset QA
  -> asset bundle
  -> AWAITING_APPROVAL
```

Fixture mode is deterministic and CI-safe:

```bash
python3 scripts/run_asset_pipeline.py data/runs/m2-demo/production_spec.json --run-id m3-demo --mode fixture
```

Outputs:

```text
data/asset_runs/m3-demo/
├── asset_bundle.json
├── assets.json
├── qa_report.json
└── run_summary.json
```

Asset records include TOPIC lineage, provider/model/version, prompt/source, SHA-256 content hash, rights/license metadata, technical metadata, and QA status. Fixture asset IDs derive their six-digit sequence from TOPIC lineage so separate topics do not collapse onto the same identity.

### Gemini Web Music live provider (default)

JEHA's default production music provider is now **Gemini web Music**. It is a
two-stage browser handoff, not a hidden API call from repository code:

```text
M3 live preflight
  -> music_handoff.json (deterministic prompt + prompt_hash)
  -> Gemini web browser skill
  -> audio-only MP3 download
  -> local file/hash/ffprobe verification
  -> M3 asset attach
```

The first stage creates the handoff and does not require a Gemini API key:

```bash
export JEHA_MUSIC_PROVIDER="gemini_web"
python3 scripts/run_asset_pipeline.py \
  data/runs/m2-demo/production_spec.json \
  --run-id m3-gemini-handoff \
  --mode live
```

The resulting `data/asset_runs/m3-gemini-handoff/music_handoff.json` is the
exact prompt input for the `gemini-web-music-generation` browser skill. After
the browser reports a completed audio-only MP3 download, attach it in a new
live run with the exact model label shown by the live picker:

```bash
export JEHA_MUSIC_PROVIDER="gemini_web"
export JEHA_GEMINI_WEB_MUSIC_ARTIFACT="/absolute/path/to/downloaded.mp3"
export JEHA_GEMINI_WEB_MUSIC_MODEL="3.7 Flash"
export JEHA_GEMINI_WEB_MUSIC_HANDOFF="data/asset_runs/m3-gemini-handoff/music_handoff.json"
export JEHA_GEMINI_WEB_MUSIC_COMMERCIAL_USE_ACK="true"
python3 scripts/run_asset_pipeline.py \
  data/runs/m2-demo/production_spec.json \
  --run-id m3-gemini-assets \
  --mode live
```

`JEHA_GEMINI_WEB_MUSIC_COMMERCIAL_USE_ACK=true` is a human gate: review the
applicable Google/Gemini terms for the intended use before allowing the asset
into the commercial registry. The provider copies the MP3 into the JEHA
generated-assets directory, hashes the actual bytes, records the exact live
model label, and refuses stale handoff prompts or conflicting overwrites.

ElevenLabs remains available only as an explicit legacy fallback by setting
`JEHA_MUSIC_PROVIDER=elevenlabs` and supplying its existing key/terms gate; it
is no longer the default path.

Visual and SFX live providers remain separately gated. Live mode never silently falls back to fixture generation.

## Tests

```bash
pytest -q
```

CI verifies M1, M2, and M3 fixture smoke paths plus network-free live-provider contracts and requires successful pipeline stages to remain:

```json
{"final_status": "AWAITING_APPROVAL"}
```

## Current boundaries

M3 fixture mode is deterministic and CI-safe. Gemini web Music requires an
authenticated browser operator and a locally verified MP3; repository code
does not persist browser cookies or session tokens. Visual/SFX production
integrations, FFmpeg rendering, YouTube upload/public publishing, and the M6
analytics feedback loop remain outside the current automated boundary.

## Project principle

- AI 可以自動研究、規劃與生產。
- 品質、原創性與版權狀態必須通過 Gate。
- MVP 階段 Public publishing 必須由人批准。
- 每一份素材都應有可追蹤 Asset ID 與來源紀錄。
