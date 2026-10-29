# Cost Accuracy & Scan Performance Plan

> **Status:** Proposed · **Date:** 2026-10-29 · **Scope:** cost model, validation, scan pipeline
> **Constraint:** only public GitHub data (code, git history, GitHub API) is available — no customer time logs.

---

## TL;DR

- **The numbers are not verified today.** Every existing check tests internal plausibility; none compares an
  estimate to something that actually happened. Several inputs are also wrong (details in §2).
- **The LLM estimator has been silently off.** Every call returns `404 model_not_found` for
  `llama-3.3-70b-versatile` and falls back to a fixed lookup table — 0 of 8,383 items were LLM-estimated in
  the latest fastapi scan.
- **Scans are slow for one avoidable reason.** The fastapi scan took **663.6 s**; **588 s (89%)** was an
  AI-generated-code heuristic re-reading every commit's diff from a blobless clone. The real analysis took ~35 s.
- **With GitHub data alone we can:** fix the math, make results reproducible, calibrate effort from real historical
  fixes, measure "interest" per repo, and backtest whether debt predicts real bugs.
  **We cannot** claim dollar accuracy against a customer's real spend until a design partner shares time data.
- **Performance target:** p50 scan **< 90 s**, p95 **< 3 min** for a ~1–2k-file repo; repeat scan of the same
  commit **< 2 s**. All calibration/backtesting runs **offline**, never inside a user's scan.

---

## 1. How numbers are "verified" today

| Mechanism | Where | What it actually proves |
|---|---|---|
| Sanity check vs. "CISQ" benchmark | `tools/cost_estimator.py:108` | Only that cost/function isn't > 2.5× the benchmark. "Below average is always reasonable" — under-estimation can never be flagged |
| Debt score (0–10, log scale) | `tools/scoring.py:73` | Anchored to the **same** benchmark — circular with the sanity check |
| Confidence labels per finding | `tools/scoring.py:28` | How an estimate was produced, not whether it's correct |
| Per-item breakdown | `_apply_formula` | Traceability of the arithmetic |
| Data-source tracking (live/fallback) | `_track_data_source` | Provenance of inputs, not their correctness |
| Clamps (0.05–200 h, confidence ≥ 0.25) | `llm_estimator.py`, `scoring.py` | Absence of absurd single values |
| Unit tests | `tests/test_cost_estimator.py` | Shape only (`0 ≤ score ≤ 10`, keys exist); one is a tautology (`x is False or x is True`) |

---

## 2. Verified problems

All evidence below was taken from the stored scans in `backend/techdebt.db`, the cache in
`backend/data/cache/`, and scan logs.

### 2.1 Accuracy

| # | Problem | Evidence | Severity |
|---|---|---|---|
| A0 | **LLM estimation never runs** — model 404 is swallowed, everything silently uses the lookup table | Log: `Error code: 404 … model 'llama-3.3-70b-versatile' does not exist … Falling back to formula defaults.` LLM-estimated items: 0/8,383 (Oct 29), 243/6,489 (Jul), 39/6,489 (Jun) | Critical |
| A1 | **Headline ≠ sum of categories** — total is multiplied by a repo-wide factor; categories mostly aren't | fastapi: Apr 06 total $84,650 vs categories $32,671 (2.59×); Jun 15 $518,888 vs $602,450 (0.86×) | Critical |
| A2 | **Benchmark is a misparsed vendor-blog number** — fallback regex takes *any* `$50–$50,000` figure on a page mentioning "function" | Cache: `cost_per_function_usd: 607.0`, source `CISQ-adjacent via perforce.com/blog/pdx/cost-of-software-defects`. Code also has `310` (constants) and `433` (fallback); UI text says `$1,083/fn` | Critical |
| A3 | **Wrong BLS series** — `CES0500000003` is avg hourly earnings of *all private employees*, not software developers; blend weights re-normalize by which sites answered that day | `rates_cache.json`: mid = $37.81 (BLS), blended rate used ≈ $134/hr; Levels.fyi uses total comp incl. equity | High |
| A4 | **Double counting** — severity applied twice (table 0.5–2.0× and formula 0.84–1.32×); repo risk applied per item *and* to the total | `_fallback_estimates` + `_apply_formula`; `repo_risk = combined/3` per item, then `total × combined` | High |
| A5 | **Global multiplier is three hand-picked step functions** (repo age × bus factor × team size) | Swung 3.0 → 2.4 → 0.86 between versions, moving totals ~3.5× | High |
| A6 | **Scope mismatch** — complexity runs on a random 200-file sample (comment says "stratified", it's a shuffle) with no extrapolation; docs/architecture/duplication/git run on the full repo; cost/function mixes both | fastapi: "Sampling 200 files out of 1223". April scans: `functions_analyzed = 4` → score 10.0, uncaught by tests | High |
| A7 | **Non-debt counted as debt** — `tests/`, `docs_src/` tutorials; a 12-min-per-function "baseline" charges clean code | fastapi top findings dominated by `docs_src/…/tutorial*.py`; `tests` module $113K | Medium |
| A8 | **Confidence lowers cost** — `cost × confidence` makes uncertain debt *cheaper* instead of widening the range | `scoring.calculate_cost` | Medium |
| A9 | **Security breach path is dead** — CVSS hard-coded to 7.0/5.0, breach value only applies at ≥ 9.0; report still cites IBM/Verizon DBIR | `cost_estimator.py:747`, `security_cost_agent.py:219` | Medium |
| A10 | **ROI contradicts recommendations** — top fix: $584 cost, $7/mo savings, 80-month payback, −55% 3-yr ROI | Scan `eeeff1ca…` | Medium |
| A11 | **AI-code premium is a heuristic multiplier** (1.5× cost) based on signals like "single large commit", "generic names" | `repo_profiler.detect_ai_generated_code`, `cost_estimator.py:637` | Medium |
| A12 | **No reproducibility** — same repo: $85K → $1.12M → $1.18M → $519K → $710K → $568K; no model version to separate code change from model change. The identical Apr 20 pair was a cache hit, not a re-run | `scans` table | High |
| A13 | **Churn uses only the last 50 commits** on a 500-commit shallow clone | `git_mining.py:41`, `GIT_CLONE_DEPTH=500` | Medium |

### 2.2 Performance (measured, fastapi scan, 663.6 s total)

| Stage | Time | Note |
|---|---|---|
| Clone (shallow 500, blobless) | 37 s | |
| **Step 0 profiling** | **588 s** | 0.5 s team metadata + **~587 s AI-detection diff walk** (`repo_profiler.py:480`, pydriller, `num_workers=1`, every commit's `modified_files` on a blobless clone ⇒ on-demand blob fetches) |
| Static analysis | ~1 s | **Runs twice** (Step 1 and again inside GitMiner) |
| Other analyzers (arch, dup, reliability, perf, dead code) | ~13 s | |
| Security scan | ~6 s | Includes live web searches (DDG/Google/Yandex for "IBM breach report") **inside the scan** |
| Docs, tests, deps | ~3 s | |
| LLM pass | 11 s | Fails fast with 404 (A0) — will become the bottleneck once fixed unless bounded |
| Report | 3 s | |

Related read-path issues: `GET /scan/{id}` returns **10.9 MB** (includes `raw_result`, and in 25/53 scans a
**GitHub access token**); repository endpoints parse ~10 MB `raw_result` JSON per scan (2–11 s each).

---

## 3. What is achievable with GitHub data only

| Capability | No data needed | GitHub data sufficient | Needs customer data |
|---|---|---|---|
| Correct math, reconciliation, no double counting | ✅ | | |
| Reproducibility (golden set, determinism, model versioning, invariants) | ✅ | | |
| Public, cited rates & a defensible benchmark method | ✅ | | |
| Effort calibration (hours per finding type, P10/P50/P90) | | ✅ proxy | exact |
| "Interest" (ongoing cost) per repo | | ✅ | |
| Backtest: does debt predict future bugs? | | ✅ | |
| Corpus percentile benchmark | | ✅ | |
| Real CVSS / CWE for security | | ✅ (OSV, bandit) | |
| "Within ±X% of what you actually spent" | | | ❌ time logs |
| Customer's real loaded rate | | | input field |
| Production incidents / revenue impact | | | ❌ |

Honest positioning until a design partner shares data: **"calibrated on public evidence"**, not "accurate for
your company".

---

## 4. Target model (what "correct" looks like)

Three figures, never summed together, each with a **P10 / P50 / P90** range:

| Line | Meaning | Formula |
|---|---|---|
| **Principal** | One-time remediation cost | Σ calibrated hours(finding type, severity, size) × loaded rate |
| **Interest** | Yearly cost of *not* fixing | Σ files: extra hours per change (fitted per repo) × changes/yr × rate |
| **Risk exposure** | Expected loss (security), separate | Frequency × magnitude (FAIR-style), shown on its own |

Rules:
1. Each multiplier is applied **once**, at **one** level, and is shown in a waterfall (base → churn → severity → total).
2. Confidence widens the interval; it never changes the point estimate.
3. Numerator and denominator always cover the same scope.
4. `sum(categories) == total` and `Σ(hours × rate) == cost` hold exactly (enforced by tests).
5. Benchmarks are percentiles against our own corpus and a SQALE-style debt ratio
   (remediation cost ÷ estimated development cost) with A–E grades — never a scraped number.

---

## 5. Fix plan

Each phase lists tasks, acceptance criteria, and its compute cost. Online = inside a user's scan;
offline = batch job.

### Phase 0 — Stop silent failures and the 10-minute scan (1–2 days)

| Task | Files | Acceptance |
|---|---|---|
| Make the LLM model configurable; startup health check; **fail loudly** (scan metadata + log ERROR + UI badge) when estimation falls back for > 10% of items | `agents/llm_factory.py`, `tools/llm_estimator.py`, `tools/cost_estimator.py` | Scan report shows "LLM estimated: N / M"; a 404 surfaces as an error, not silence |
| **Remove the per-commit AI-detection diff walk** (or replace with the single `git log` pass in Phase 2). Drop the 1.5× AI premium until it's validated | `intelligence/repo_profiler.py:466+`, `cost_estimator.py:637` | Step 0 < 5 s on fastapi |
| Run static analysis once and share results with GitMiner | `tools/git_mining.py`, `tools/cost_estimator.py` | "Analysis complete" logged once per scan |
| Remove live web scraping from the scan path (benchmarks, rates, breach data) — use versioned static tables (Phase 1) | `intelligence/benchmark_agent.py`, `rate_agent.py`, `security_cost_agent.py` | Zero outbound HTTP during a scan except clone + OSV |
| Stop persisting/returning `github_access_token`; slim `GET /scan/{id}` | `services/analysis_runner.py`, `api/routes/scans.py` | No token in DB or responses; detail payload < 500 KB |

**Compute impact:** fastapi 663 s → ~80 s (clone 37 s + analysis ~35 s + report).

### Phase 1 — Correct the math (3–5 days, online, no data needed)

| Task | Acceptance |
|---|---|
| Apply repo-level factors exactly once; remove the per-item `repo_risk` *or* the total multiplier | Property test: doubling one factor doubles only its own contribution |
| Remove severity double-count (keep it in one place) | Unit test on a fixed finding |
| `cost_by_category` includes every adjustment | Test: `abs(sum(categories) - total) < $1` for every golden repo |
| Same-scope density: scan all files, or stratified sample (by top-level dir × size bucket) **with extrapolation and CI** | Score unchanged ±0.1 when the sample seed changes |
| Exclude `tests/`, `docs/`, `examples/`, generated code from principal (report test debt separately) | fastapi top-20 findings contain no `docs_src/` tutorials |
| Drop the 12-min/function baseline (it's maintenance, not debt) | — |
| Confidence → interval width; remove `× confidence` from cost | Lower confidence never lowers P50 |
| Rates: BLS OES **15-1252 Software Developers** (≈ $130K median annual, May 2023 — verify latest) ÷ 2,080 h × loaded factor from BLS ECEC (~1.4×); store rate + citation per scan; **customer override field** | Same commit → same rate, regardless of network |
| Security: real CVSS from OSV, CWE/severity/confidence from bandit; risk on its own line or remove breach claims | No cited source that isn't used |
| Detect degenerate inputs (e.g. `functions_analyzed < files_scanned`) and fail the scan with a clear error | April-style `functions_analyzed = 4` impossible |

**Compute impact:** neutral (pure arithmetic).

### Phase 2 — Reproducibility & one fast history pass (1 week)

| Task | Acceptance |
|---|---|
| **Golden set:** 15–20 public repos pinned to SHAs (flask, fastapi, django, express, gin, spring-petclinic, …) with snapshot expected outputs | CI fails on unexplained deltas |
| Determinism: LLM temperature 0, cache by `hash(model, prompt, snippet)`, fixed sample seed | Same SHA scanned twice → identical output |
| `model_version` stored on every scan; changelog of deltas on the golden set per release | Trend charts can separate "code changed" from "model changed" |
| Invariant + property tests (Hypothesis): reconciliation, monotonicity, clean-file-adds-no-cost | Tests run < 30 s |
| **Single history pass:** full-history *blobless* clone + one `git log --no-renames --name-status --format=…` subprocess → churn, authors, ownership, bus factor, change dates for every file. Trees are present in a blobless clone, so this needs **no blob downloads** | History features for 10k commits in < 10 s; replaces pydriller per-commit walks and the 50-commit churn window |

**Compute impact:** clone slightly larger (full history, no blobs); history features drop from minutes to seconds.

### Phase 3 — Backtest the ranking (1 week, offline)

Most important validation possible without customer data.

1. For each golden repo, check out the tree at T = −12 months (and −6, −18); run the scanner on that snapshot.
2. Label files that received bug-fix commits in (T, now]: commits linked to `bug`-labeled issues via closing
   keywords (GitHub API), falling back to `fix|bug` commit messages.
3. Metrics: precision@10/20, recall@20, AUC. **Baselines:** lines of code, churn alone, random.
4. **Go/no-go:** if the debt ranking doesn't beat LOC, fix the model before calibrating dollars.

**Compute:** offline batch; ~1 scan per snapshot (~1 min each after Phase 0) × 20 repos × 3 snapshots ≈ 1 h.
GitHub API via GraphQL, cached per repo/date (5,000 req/h budget per token).

### Phase 4 — Calibrate effort from historical fixes (1–2 weeks, offline)

1. **Find fix events** (per-function metrics at commit pairs, not every commit):
   - complexity: function CCN ≥ 15 → ≤ 10 without deletion
   - documentation: docstring added to an undocumented function
   - test debt: test file appears for an untested module
   - duplication: duplicated block removed / extracted
   - dependency: bump to the OSV `fixed_version`
2. **Effort proxies** per event, combined robustly (median of normalized proxies):
   PR first-commit → merge time and review rounds (GitHub API); author **session clustering**
   (commits < 2 h apart + first-commit allowance); lines changed as a sanity bound.
3. **Fit** per (finding type × severity × size bucket): P10 / P50 / P90 hours. Ship as a versioned
   `calibration/effort_v{N}.json` loaded at scan time.
4. **State biases:** elapsed ≠ effort (review wait inflates, sessions deflate), OSS ≠ paid teams,
   survivorship (fixed debt may be easier).

**Compute:** offline only. Candidate commits are pre-filtered with the cheap `git log` pass; metrics are computed
only on the before/after versions of touched files (~O(fix events), not O(all commits)). Runtime at scan time: a
dictionary lookup.

### Phase 5 — Interest model (1 week, offline fit + cheap online apply)

1. Per file over the last 12–24 months: bug-fix commits per change, PR cycle time for PRs touching the file,
   rework (reverts, lines rewritten within 21 days), distinct authors.
2. Compare high- vs low-debt files **controlling for size** (regression or size-matched pairs).
3. `interest/yr = Σ extra_hours_per_change × changes_per_year × rate` → drives "saves per month" and ROI.
4. Use public research (e.g. Tornhill & Borg, *Code Red*, 2022 — reported markedly higher defect density and
   longer issue resolution in low-quality code) only as a **prior**, overridden by each repo's own fit.

**Compute:** the per-file features come from the Phase 2 single `git log` pass plus one cached GraphQL query for
PRs; the fit is a small regression (milliseconds). Online cost: < 5 s.

### Phase 6 — Corpus benchmark (1 week, offline)

Scan 200–300 popular public repos at pinned SHAs, bucketed by language × size. Publish percentiles and SQALE-style
debt-ratio grades (A–E). Refresh monthly. Online cost: percentile lookup.

---

## 6. Compute budget design

### Principles

1. **Online scan does only per-repo work.** Everything that learns from many repos (calibration, backtesting,
   corpus benchmarks) runs offline and ships as small versioned tables.
2. **No network calls in the scan path** except the clone and OSV (batched).
3. **One pass over git history**, using `git log --name-status` on a blobless clone — never per-commit diff
   objects.
4. **Cache by content:** full results by `(repo, HEAD sha, model_version)`; per-file analysis by **blob SHA**, so a
   re-scan only re-analyzes changed files.
5. **Bound the LLM:** estimate only the top-N findings by principal (e.g. 50), batched, cached by snippet hash,
   with a hard time box; everything else uses the calibrated tables.
6. **Store slim, serve slim:** findings in columns; `raw_result` moved to a separate table/blob, never sent to the
   browser.
7. **Run heavy work on a worker queue** (arq/RQ/Celery on existing Redis), not threads inside the API process.

### Targets

| Stage | Today (fastapi) | Target |
|---|---|---|
| Clone | 37 s | ≤ 40 s (full-history blobless) |
| Profiling / history features | 588 s | **≤ 10 s** |
| Static + other analyzers | ~25 s (static runs twice) | ≤ 20 s |
| Security + deps | ~9 s (incl. web search) | ≤ 5 s |
| LLM | 11 s (failing) | ≤ 20 s (top-N, cached) |
| Report + persist | 3 s | ≤ 3 s |
| **Total p50** | **663.6 s** | **< 90 s** |
| Same commit re-scan | full re-run | **< 2 s** (cache hit) |
| Incremental re-scan (few files changed) | full re-run | **< 20 s** |
| `GET /scan/{id}` | 5.4 s, 10.9 MB | < 300 ms, < 500 KB |
| Repository history endpoints | 2–11 s each | < 500 ms |

### Offline job budget

| Job | Frequency | Est. runtime |
|---|---|---|
| Golden-set regression | Every PR touching `tools/`, `intelligence/`, `constants.py` | ~20 min (pinned SHAs, cached clones) |
| Backtest | Per model release | ~1 h |
| Effort calibration | Monthly | 2–4 h |
| Corpus benchmark refresh | Monthly | 3–5 h |
| Rate / benchmark tables | Quarterly (manual, cited) | minutes |

---

## 7. Metrics to track

| Metric | Target |
|---|---|
| Reconciliation error (`sum(categories) − total`) | $0 on every scan |
| Determinism (same SHA, two runs) | 100% identical |
| Backtest lift vs. LOC baseline (precision@20) | > 1.3× |
| Calibration coverage (findings with a fitted distribution) | > 90% |
| LLM-estimated share of top-N | 100% (fallback alerts if < 90%) |
| Scan p50 / p95 | < 90 s / < 3 min |
| Golden-set unexplained delta per release | 0 |

---

## 8. Risks & limits

- **Proxy bias:** git/PR time is elapsed time, not effort; OSS teams differ from paid teams. Disclose on every
  report until customer data validates.
- **Bug labels are noisy** across repos; use closing keywords first, message heuristics second, and report label
  coverage per repo.
- **Small repos** have too little history for per-repo interest fits — fall back to corpus priors and widen ranges.
- **GitHub API limits** — GraphQL, caching, and one token per worker.
- **Breaking change for users:** totals will move (likely down: no baseline, no double counting, no docs/tests).
  Ship with `model_version`, a changelog, and an optional re-score of historical scans.

---

## 9. Appendix — reproducing the evidence

- **Totals vs. categories / multipliers per scan:** query `scans.raw_result` for `cost_by_category`,
  `combined_multiplier`, `items_estimated_by_llm` (fastapi rows, ordered by `created_at`).
- **Benchmark source:** `backend/data/cache/tech_debt_cache/cache.db`, key prefix `cisq_benchmarks:`.
- **Rates:** `backend/data/cache/rates_cache.json`.
- **LLM failure:** scan logs, `tools.llm_estimator - WARNING - Batch LLM estimation failed … 404`.
- **Scan timeline:** `[COST EST] Step …` log lines; gap between "Step 0" and "Step 0b" is the AI-detection walk.
- **Token exposure:** count scans whose `raw_result.github_access_token` is non-empty (25 / 53 at time of writing).
