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

## MVP v1

第一版先驗證：

`20 candidates -> score -> Top 5 -> product route -> Top 1 production spec -> QA checklist -> AWAITING_APPROVAL`

目前不直接自動公開影片；發布前保留 Human Gate。

## Products

- **Flow Room** — Focus / Study / Coding / Pomodoro
- **Moon Room** — Sleep / Calm / Rain / Night
- **Cozy Room** — Café / Reading / Lifestyle
- **Nature Room** — Rain / Forest / Ocean / Environmental sounds

## Pipeline

```text
Research
  -> Topic Scoring
  -> Product Router
  -> Production Planner
  -> QA Gate
  -> Human Approval
  -> Publisher (v2)
  -> Analytics (v2)
  -> Research
```

## Run M1 locally

Python 3.11+ is recommended.

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/run_daily_pipeline.py
```

For a reproducible run with a known output path:

```bash
python3 scripts/run_daily_pipeline.py --run-id m1-demo
```

Sample output path:

```text
data/runs/m1-demo/
├── candidates.json
├── top5.json
├── production_spec.json
├── qa_report.json
└── run_summary.json
```

A successful M1 run ends with:

```json
{
  "final_status": "AWAITING_APPROVAL"
}
```

Run tests with:

```bash
pytest -q
```

## M1 boundaries

M1 is planning/selection only. It does not call external trend APIs, generate music or images, render media with FFmpeg, upload to YouTube, or publish publicly.

## Project principle

- AI 可以自動研究、規劃與生產。
- 品質、原創性與版權狀態必須通過 Gate。
- MVP 階段 Public publishing 必須由人批准。
- 每一份素材都應有可追蹤 Asset ID 與來源紀錄。
