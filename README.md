# JEHA Media Engine

家河（JEHA）旗下陪伴型媒體產品的自動化內容引擎。

## 目標

建立一條可重複執行、可驗收、可逐步自動化的內容生產線：

1. 研究市場與候選題材
2. 為候選題材評分
3. 分流至 Flow Room / Moon Room / Cozy Room / Nature Room
4. 產生 Production Spec
5. 執行 QA / Originality Gate
6. 等待 Human Approval
7. 後續串接音樂、視覺、FFmpeg 與 YouTube 發布
8. 將 Analytics 回饋下一輪選題

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

## Tests

```bash
pytest -q
```

CI verifies both M1 and M2 fixture smoke paths and requires the final status to remain:

```json
{"final_status": "AWAITING_APPROVAL"}
```

## Current boundaries

M1/M2 do not generate music or images, render media with FFmpeg, upload to YouTube, publish publicly, or implement the M6 analytics feedback loop.

## Project principle

- AI 可以自動研究、規劃與生產。
- 品質、原創性與版權狀態必須通過 Gate。
- MVP 階段 Public publishing 必須由人批准。
- 每一份素材都應有可追蹤 Asset ID 與來源紀錄。
