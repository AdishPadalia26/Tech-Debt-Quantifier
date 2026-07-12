# Hybrid LLM-Formula Cost Estimation Engine

Redesign the cost estimation pipeline so the local Ollama (qwen3.5) model provides **realistic effort estimates** (hours, severity scores, risk scores) per debt item, and a deterministic formula layer applies multipliers and computes final dollar costs.

## User Review Required

> [!IMPORTANT]
> **Architectural Decision — Where to place the LLM estimation call.**
> The current `CostEstimator.estimate_total_cost()` is a monolithic 400-line function. The user's spec calls for calling the LLM per debt item after all analyzers have run. My proposal is to:
> 1. Create `LLMEstimator` as a standalone module
> 2. Add `_estimate_single_item()` and `_estimate_all_items()` as **standalone functions** in `cost_estimator.py` (not class methods) since `CostEstimator` currently has no instance state related to the LLM
> 3. Wire the call at the end of `estimate_total_cost()` after all debt items are collected but **before** final totals are computed
> This lets us re-estimate all items at once with LLM hours, then recompute totals using those hybrid-adjusted costs.

> [!WARNING]
> **The `CostEstimator` class has no `self.ollama_client` or `self.model_name`.**
> Unlike the user's spec which assumes `self.ollama_client` exists, the current class is stateless. I'll need to instantiate the Ollama client inside the estimator using the existing `llm_factory` pattern (env-based `OLLAMA_MODEL` and `OLLAMA_BASE_URL`), or initialize `LLMEstimator` with a fresh `ollama.Client`.

> [!IMPORTANT]
> **Ollama Python SDK vs OpenAI-compat API.**
> The existing codebase uses Ollama through the **OpenAI-compatible `/v1`** endpoint via `langchain_openai.ChatOpenAI`. The user's spec uses `ollama.Client.chat()` directly. I will use the `ollama` Python package directly (`import ollama`) for `LLMEstimator` since it's lighter weight for this use case and avoids langchain overhead. **This requires `pip install ollama` — please confirm this is acceptable**, or I can use the existing OpenAI-compat approach.

## Open Questions

1. **Ollama package**: The codebase currently does NOT have `ollama` as a direct dependency (it uses the OpenAI-compat wrapper via LangChain). Should I:
   - **(A)** Add `ollama` package as a new dependency (cleaner API for direct chat calls) — **recommended**
   - **(B)** Use `openai.OpenAI(base_url=...).chat.completions.create()` to avoid a new dep
   - **(C)** Use the existing `LocalLLMService` wrapper (async, adds langchain overhead)

2. **Performance tradeoff**: For a repo with 50-100 debt items, LLM estimation at ~2-5s per item × 25 items per batch (4 workers) = ~30-120 seconds added to scan time. The user's spec caps at 4 parallel workers. Is this acceptable, or should we add a config toggle (`HYBRID_ESTIMATION_ENABLED=true/false`)?

---

## Proposed Changes

### New Module: LLM Estimator

#### [NEW] [llm_estimator.py](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/backend/tools/llm_estimator.py)

Standalone module with `LLMEstimator` class as specified in the user's prompt. Key points:
- Uses Ollama client with `temperature=0.2`
- Prompt asks for structured JSON: `realistic_hours`, `severity_score` (1-10), `business_risk_score` (1-10), `fix_complexity_score` (1-10), `confidence`, `primary_risk`, `fix_summary`, `cost_rationale`
- Parses response with regex-based JSON extraction
- Clamps all numeric values to sane ranges
- Falls back to formula-based estimates if LLM fails
- Uses existing `OLLAMA_MODEL` and `OLLAMA_BASE_URL` env vars

---

### Backend: Cost Estimator Integration

#### [MODIFY] [cost_estimator.py](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/backend/tools/cost_estimator.py)

1. **Add `LLMEstimator` initialization** — Create an Ollama client using env vars and instantiate `LLMEstimator` in the `__init__` method
2. **Add `_estimate_single_item()` method** — Hybrid estimation per the user's spec:
   - Call `LLMEstimator.estimate_debt_item()` for each debt item
   - Use `realistic_hours` as the base effort
   - Apply churn, severity, and repo multipliers
   - Build cost factors and cost explanation
3. **Add `_estimate_all_items()` method** — ThreadPoolExecutor-based parallel estimation with `max_workers=4`
4. **Add `_estimate_single_item_with_timeout()` method** — 30s per-item timeout wrapper
5. **Wire into `estimate_total_cost()`** — After all debt items are collected (line ~453), call `_estimate_all_items()` to re-estimate all items, then recompute totals using hybrid costs
6. **Add `estimation_method` flag** to the return dict:
   - `estimation_method`: `"hybrid_llm_formula"`
   - `llm_model`: model name from env
   - `items_estimated_by_llm` / `items_estimated_by_formula` counts
7. **Preserve existing API shape** — All existing fields remain; new fields are additive only

**Churn data access**: The existing code computes churn via `GitMiner().get_hotspots()`. I'll build a `{file_path: change_count}` dict from the `risky_files` data (which already contains `change_count`) and pass it to the estimation functions.

---

### Backend: Normalize new fields

#### [MODIFY] [main.py](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/backend/main.py)

Update `normalize_analysis_result()` to pass through the new debt item fields:
- `estimation_confidence`
- `primary_risk`
- `fix_summary`
- `cost_factors`
- `cost_explanation`
- `severity_score`
- `business_risk_score`
- `fix_complexity_score`

Also pass through `estimation_method`, `llm_model`, `items_estimated_by_llm`, `items_estimated_by_formula` at the top-level.

---

### Frontend: Types Update

#### [MODIFY] [index.ts](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/frontend/src/types/index.ts)

Add to `PriorityAction` interface:
- `estimation_confidence?: string`
- `primary_risk?: string`
- `fix_summary?: string`
- `top_cost_drivers?: string[]`
- `cost_explanation?: string`
- `base_cost_usd?: number`
- `combined_multiplier?: number`

Add to `ActionItem` local type in `page.tsx`:
- `estimation_confidence?: string`
- `fix_summary?: string`

---

### Frontend: ActionCard Confidence Badge & Fix Summary

#### [MODIFY] [page.tsx](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/frontend/src/app/page.tsx)

1. **ActionCard component** (line ~261): Add after the severity badge:
   - Confidence badge (green/yellow/gray) with text
   - Fix summary subtitle from LLM
   
2. **KpiCard for "Total Debt Cost"** (line ~1075): Add "How we estimate" tooltip icon next to the label, showing the estimation methodology explanation on hover.

3. **Update `ActionItem` type** (line ~134): Add `estimation_confidence` and `fix_summary` fields.

---

### Frontend: PriorityActions component (scan detail page)

#### [MODIFY] [PriorityActions.tsx](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/frontend/src/components/PriorityActions.tsx)

Add confidence badge and fix summary to the scan detail page's priority action cards.

---

### Backend: Report Writer — Priority Action Builder

#### [MODIFY] [report_writer_agent.py](file:///d:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/backend/intelligence/report_writer_agent.py)

Update `priority_actions()` and `_fallback_priorities()` to pass through hybrid estimation fields from findings to the priority action output:
- `estimation_confidence`
- `primary_risk`
- `fix_summary`
- `cost_explanation`
- `top_cost_drivers`
- `base_cost_usd`
- `combined_multiplier`

---

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `backend/tools/llm_estimator.py` | NEW | LLM-based effort estimator |
| `backend/tools/cost_estimator.py` | MODIFY | Add hybrid estimation pipeline |
| `backend/main.py` | MODIFY | Normalize new fields in API response |
| `backend/intelligence/report_writer_agent.py` | MODIFY | Pass through hybrid fields to priority actions |
| `frontend/src/types/index.ts` | MODIFY | Add new type fields |
| `frontend/src/app/page.tsx` | MODIFY | Confidence badge, fix summary, estimation tooltip |
| `frontend/src/components/PriorityActions.tsx` | MODIFY | Confidence badge + fix summary on scan page |

---

## Verification Plan

### Automated Tests
1. Run `python -c "from tools.llm_estimator import LLMEstimator; print('OK')"` to verify import
2. Run `python -c "from tools.cost_estimator import CostEstimator; print('OK')"` to verify integration
3. Run existing tests: `pytest tests/ -v` to ensure no regressions
4. Run `npm run build` in frontend to verify TypeScript compilation

### Manual Verification
1. Start backend (`uvicorn main:app --reload`)
2. Start frontend (`npm run dev`)
3. Run a scan against a small repo
4. Verify debt items have `cost_explanation` and `estimation_confidence` fields
5. Verify priority action cards show confidence badges and fix summaries
6. Verify the "How we estimate" tooltip appears on the Total Debt Cost KPI
7. Stop Ollama → run scan → verify fallback works (all items show `estimation_confidence: "low"`)
