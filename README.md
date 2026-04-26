# Tech Debt Quantifier

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Most engineering teams know they have technical debt. Few know what it *costs* them. Tech Debt Quantifier clones any GitHub repository, runs multi-layer static analysis and git history mining across eight debt categories, and produces a dollar-denominated cost estimate — broken down by category, file, severity, and remediation sprint — so engineering managers can make the business case for paying it down. Unlike SonarQube or CodeClimate, this tool anchors every finding to a dollar figure using role-calibrated hourly rates ($55/hr junior, $84/hr mid, $128/hr senior), a churn multiplier derived from actual git history, and an optional Ollama LLM layer that refines estimates and generates a plain-English executive summary a non-engineer can act on.

![Tech Debt Quantifier Dashboard](https://placehold.co/1200x600?text=Tech+Debt+Quantifier+Dashboard+Screenshot)

---

## How It Works (Architecture Overview)

Paste a public GitHub URL into the frontend. The Next.js UI POSTs to `/analyze`, which enqueues a background job. Three sequential agents handle the work: `CrawlerAgent` clones the repository, `AnalyzerAgent` runs eight parallel debt scanners (static complexity, git churn, architecture, duplication, reliability, performance, dead code, and dependency analysis) while a `RepoProfiler` detects the tech stack, team size, and AI-generated files to derive risk multipliers. `CostEstimator` assembles findings into dollar figures. Finally, `ReporterAgent` calls `ReportWriterAgent` — backed by `LocalLLMService` — to produce an executive summary, top-3 priority actions, and an ROI analysis. The frontend polls `/status/{job_id}` every two seconds and renders a live progress bar; results arrive at `/results/{job_id}`. Completed scans persist to SQLite (default) or PostgreSQL via SQLAlchemy ORM, enabling scan history, trend charts, and cross-scan comparisons.

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface                           │
│              Next.js 14  ·  TypeScript  ·  Tailwind             │
│  AnalyzeForm  ·  ProgressBar  ·  DebtScoreCard  ·  RoadmapBoard │
└───────────────────────────┬─────────────────────────────────────┘
                            │ POST /analyze
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (v0.2.0)                      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ CrawlerAgent │  │AnalyzerAgent │  │    ReporterAgent     │  │
│  │  (GitPython) │─▶│  (8 scanners)│─▶│  (ReportWriterAgent) │  │
│  │  Clone repo  │  │  + profiler  │  │  Executive summary   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                           │                       │             │
│          ┌────────────────┼───────────────────────┘             │
│          ▼                ▼                                     │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                   CostEstimator                        │    │
│  │  effort_hours × hourly_rate × business_impact_weight   │    │
│  │           × confidence  =  cost_usd per finding        │    │
│  │                                                        │    │
│  │  RepoProfiler  ·  BenchmarkAgent  ·  OwnershipAnalyzer │    │
│  └────────────────────────────────────────────────────────┘    │
│                           │                                     │
│          ┌────────────────┼──────────────────┐                  │
│          ▼                ▼                  ▼                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐      │
│  │    Slack     │  │    Jira      │  │  PDF Generator   │      │
│  │  Notifier    │  │   Client     │  │   (ReportLab)    │      │
│  └──────────────┘  └──────────────┘  └──────────────────┘      │
│                                                                 │
│  SQLite (dev)  /  PostgreSQL (prod)  ·  SQLAlchemy ORM          │
│  Scan · DebtItem · Finding · ModuleSummary · RoadmapItem        │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │   Local Ollama (optional)   │
              │   qwen3.5:latest (default)  │
              │   LangChain ChatOllama      │
              │   Timeout: 20s per invoke   │
              └─────────────────────────────┘
```

---

## The Cost Model

### The Formula

Every finding is individually priced. The core calculation in `tools/scoring.py`:

```
cost_usd = effort_hours × hourly_rate × business_impact_weight × confidence
```

| Factor | How it is determined |
|---|---|
| `effort_hours` | Per-category baseline from `COMPLEXITY_REMEDIATION_MINUTES` or `BANDIT_REMEDIATION_HOURS` in `constants.py`, scaled by severity |
| `hourly_rate` | Role assigned per category (see table below), with live market lookup via `RateIntelligenceAgent` |
| `business_impact_weight` | `low=0.9`, `medium=1.0`, `high=1.2`, `critical=1.5` — derived from severity + churn |
| `confidence` | `static_analysis=0.70`, `git_history=0.80`, `security_scan=0.80`, `dependency=0.85`, `fallback=0.45` |

Confidence is clamped to `[0.25, 1.0]` so no finding ever costs zero from a low-confidence source.

#### Churn Multiplier (git history)

Files that change more often carry disproportionate maintenance risk. The churn multiplier table in `constants.py`:

| Commits in history | Churn multiplier |
|---|---|
| 0–2 | 1.0× |
| 3–5 | 1.3× |
| 6–10 | 1.7× |
| 11–19 | 2.2× |
| 20+ | 3.0× |

#### Complexity Thresholds

Cyclomatic complexity bands drive severity classification:

| Band | Complexity range | Sonar equivalent | Remediation minutes |
|---|---|---|---|
| low | 1–5 | MINOR | 15 min |
| medium | 6–10 | MAJOR | 45 min |
| high | 11–15 | CRITICAL | 90 min |
| critical | 16+ | BLOCKER | 180 min |

#### Hourly Rates by Category

Rates are role-calibrated, not flat. The `DEBT_TYPE_TO_ROLE` mapping assigns a seniority tier per debt type, and `HOURLY_RATES` defines the USD values:

| Debt category | Role | Hourly rate |
|---|---|---|
| architecture | senior | $128.37 |
| security | senior | $128.37 |
| code_quality | mid | $84.55 |
| dependency | mid | $84.55 |
| test_debt | junior | $55.10 |
| documentation | junior | $55.10 |

These are default values. `RateIntelligenceAgent` can replace them at runtime with live market data when available; the system falls back to these constants when confidence is `"low"`.

---

### Debt Categories

Eight scanners run in parallel. Each finding records `file_path`, `category`, `severity`, `effort_hours`, `cost_usd`, and `confidence`.

| Category | What it detects | Tool(s) | Role |
|---|---|---|---|
| `code_quality` | Cyclomatic complexity per function (radon CC + lizard), git hotspots | radon, lizard, PyDriller | mid |
| `architecture` | Files > 400 LOC, modules with import fan-out > 10 | AST analysis | senior |
| `security` | Bandit findings at HIGH/MEDIUM/LOW severity | bandit | senior |
| `dependency` | Outdated or vulnerable packages, missing lock files | CVE data, pip/npm metadata | mid |
| `test_debt` | Missing test coverage, test files below coverage threshold | AST pattern matching | junior |
| `documentation` | Public functions and classes missing docstrings | AST analysis | junior |
| `performance` | Nested loops, synchronous I/O in async context, N+1 patterns | AST + regex | mid |
| `duplication` | Copy-pasted code blocks above a line threshold | Token-based comparison | mid |

A `SecurityCostAgent` applies an additional risk-weighted cost model for `security` findings that accounts for CVE severity and exploit availability.

---

### Debt Score (0–10)

The repo-level debt score normalizes total cost against the CISQ industry benchmark of **$310.00 per function**:

```
debt_score = min(10, (total_cost_usd / function_count) / 310.00 × 10)
```

A score of 5.0 means the repo's average cost per function equals the CISQ industry average. The sanity check flags estimates more than 150% above average.

---

### Hybrid LLM Mode

When `LLM_PROVIDER=ollama` is set, `LocalLLMService` sends prompts to the configured Ollama endpoint. The LLM layer handles two tasks:

1. **Executive summary**: a 3-sentence plain-English scan overview with specific numbers.
2. **Priority actions**: a JSON array of up to 3 actionable items with `rank`, `title`, `file_or_module`, `why`, `estimated_hours`, `estimated_cost`, `saves_per_month`, and `sprint`.

If the LLM times out (default 20 seconds per call, set by `LOCAL_LLM_TIMEOUT_SECONDS`) or returns unparseable output, `ReportWriterAgent` falls back to deterministic templates that produce equivalent output without any LLM call. The formula-based cost numbers are never touched by the LLM — only the natural-language narrative is LLM-generated.

**ROI analysis** is always deterministic:
```
annual_savings = total_cost × 0.40
payback_months = (total_cost / annual_savings) × 12
3_year_roi_pct = ((annual_savings × 3 - total_cost) / total_cost) × 100
```

---

## Tech Stack

### Backend

| Technology | Version | Why |
|---|---|---|
| FastAPI | 0.104+ | Async-native request handling; `BackgroundTasks` lets the `/analyze` endpoint return immediately while the analysis runs in the background — impossible in Flask without Celery. Auto-generated OpenAPI docs at `/docs` come free. |
| SQLAlchemy | 2.x | Supports both SQLite (zero-config dev) and PostgreSQL (production) through a single `DATABASE_URL` swap, with no code changes. The ORM maps directly to `Scan`, `DebtItem`, `Finding`, `ModuleSummary`, and `RoadmapItem` tables. |
| Alembic | latest | Schema migration management. Run `alembic upgrade head` to apply migrations without dropping data. |
| GitPython / PyDriller | latest | PyDriller wraps GitPython with commit-level iteration. It exposes per-file change counts, authors, and timestamps without shelling out to `git log` and parsing text output — which breaks on repos with non-ASCII commit messages. |
| radon | latest | Computes cyclomatic complexity (CC) per function via Python AST traversal. Returns structured `ComplexityVisitor` objects rather than text, so complexity thresholds are applied in Python, not grep. |
| lizard | latest | Language-agnostic complexity analysis for TypeScript, Go, Java, C++ and others. Runs when radon cannot parse the file (non-Python repos). |
| bandit | latest | AST-based Python security scanning. Produces structured JSON output with severity and confidence levels that map directly to `BANDIT_REMEDIATION_HOURS` constants. |
| LangChain | latest | Provides a consistent `.ainvoke()` async interface across Ollama, OpenAI, and HuggingFace backends. Swapping `LLM_PROVIDER` changes the backend without touching `LocalLLMService` or `ReportWriterAgent`. |
| Ollama | local | Runs LLMs entirely on-device. No API keys, no per-token billing, no data leaving the machine — important for teams scanning private repos. The default model `qwen3.5:latest` runs on a CPU-only machine (4 GB RAM minimum). |
| ReportLab + Pillow | latest | Generates PDF reports server-side via `reports/pdf_generator.py` without a headless browser. Plotly renders charts to PNG in-memory; Pillow embeds them in the PDF. |
| python-jose | latest | JWT encoding/decoding for GitHub OAuth sessions. `JWT_SECRET` is configurable; defaults to `"dev-secret"` which is only safe for local use. |
| slack-sdk | latest | Official Slack SDK. Used by `SlackNotifier` to build Block Kit message payloads — header, key metrics section, cost breakdown, priority actions, ROI, and a "Download PDF" button. |
| jira | latest | Python Jira REST client. `JiraClient` auto-discovers issue types via `createmeta` so it works on both Jira Cloud and Jira Server without hardcoding `"Task"` or `"Story"`. |

### Frontend

| Technology | Version | Why |
|---|---|---|
| Next.js 14 | App Router | Server components reduce JavaScript bundle size. The App Router's `layout.tsx` wraps all pages in a consistent shell with the sidebar and auth header — one file, zero prop drilling. |
| TypeScript | 5.x | `frontend/src/types/index.ts` defines the full API contract: `DebtReport`, `StructuredFinding`, `PriorityAction`, `ROIAnalysis`, `RepoChangeRollup`, and 20+ other interfaces. TypeScript catches shape mismatches between the API response and the UI at compile time. |
| Tailwind CSS | 3.4 | Utility-first CSS avoids the naming overhead of BEM or CSS modules for a dashboard with many small, one-off layout cells. `tailwind-merge` handles class conflict resolution. |
| shadcn/ui + Radix UI | latest | Accessible, unstyled component primitives (dialogs, tabs, tooltips, collapsibles, scroll areas) that match Tailwind's design constraints without shipping an opinionated component library theme. |
| Recharts | 3.x | React-native charting for `DebtTrendChart`, `CostBreakdownChart`, and `ActiveDebtChart`. Recharts uses SVG and React state, so charts re-render reactively when scan data updates — no D3 imperative DOM mutations needed. |
| Tremor | 3.x | Pre-built dashboard-grade cards and progress bars. Used by `ProgressBar` and `DebtScoreCard` for the scan progress UI. |
| motion (Framer Motion) | 12.x | CSS transitions alone do not handle layout animations (elements entering or leaving the DOM). Framer Motion's `AnimatePresence` handles the fade-in of result cards without writing keyframe CSS. |
| Lucide React | latest | Icon set consistent with shadcn/ui. |
| Axios | 1.x | Promise-based HTTP client used by the frontend's API layer. Handles request cancellation (important for the 2-second polling loop), response interceptors, and base URL configuration via `NEXT_PUBLIC_API_URL`. |

---

## Project Structure

```
├── backend/
│   ├── main.py                      # FastAPI app (v0.2.0), core routes: /analyze, /status, /results, /health, /jobs
│   ├── config.py                    # Env var loading for Slack, Jira, GitHub OAuth, JWT
│   ├── constants.py                 # Single source of truth for all numeric constants (thresholds, rates, multipliers)
│   ├── requirements.txt             # Python dependencies
│   ├── mcp_server.py                # MCP (Model Context Protocol) server, REPOS_DIR definition
│   ├── alembic.ini                  # Alembic migrations config
│   │
│   ├── agents/
│   │   ├── orchestrator.py          # TechDebtOrchestrator — top-level coordinator
│   │   ├── crawler.py               # CrawlerAgent — clones repository via GitPython
│   │   ├── analyzer.py              # AnalyzerAgent — runs all 8 debt scanners
│   │   ├── reporter.py              # ReporterAgent — calls ReportWriterAgent, persists scan
│   │   ├── llm_factory.py           # get_llm() factory: routes to Ollama/OpenAI/HuggingFace
│   │   └── state.py                 # Typed pipeline state shared between agents
│   │
│   ├── api/
│   │   ├── deps.py                  # FastAPI dependencies: get_current_user, get_github_access_token
│   │   └── routes/
│   │       ├── auth.py              # GitHub OAuth: /auth/github, /auth/github/callback, /auth/me
│   │       ├── github.py            # GitHub repo import: /github/repos, /github/orgs
│   │       ├── integrations.py      # /integrations/status, /report/{id}/slack, /report/{id}/jira
│   │       ├── portfolio.py         # /portfolio — multi-repo dashboard aggregates
│   │       ├── repositories.py      # /repositories — list, history, trends, changes, findings
│   │       ├── reports.py           # /report/{id}/pdf — PDF download
│   │       └── scans.py             # /scans/{id} — scan detail, findings, modules, roadmap
│   │
│   ├── database/
│   │   ├── models.py                # SQLAlchemy models: User, Repository, Scan, DebtItem, Finding, ModuleSummary, RoadmapItem, FindingSuppression, FindingFeedback
│   │   ├── connection.py            # DB engine (SQLite or PostgreSQL), SessionLocal, Base
│   │   ├── crud.py                  # save_scan() and related persistence helpers
│   │   ├── init_db.py               # Table creation script
│   │   └── migrate.py               # Migration helpers
│   │
│   ├── tools/
│   │   ├── cost_estimator.py        # Orchestrates 8 analyzers, builds debt_items list and cost_by_category
│   │   ├── scoring.py               # calculate_cost(), aggregate_repo_score(), build_finding_payload()
│   │   ├── static_analysis.py       # radon + lizard complexity, bandit security scan
│   │   ├── git_mining.py            # PyDriller hotspot and churn analysis
│   │   ├── architecture_analysis.py # LOC threshold (400) and import fan-out (10) checks
│   │   ├── dead_code_analysis.py    # Unused function and import detection
│   │   ├── dependency_analysis.py   # Outdated/vulnerable dependency scanning
│   │   ├── duplication_analysis.py  # Copy-paste block detection
│   │   ├── performance_analysis.py  # Nested loops, sync I/O in async context
│   │   ├── reliability_analysis.py  # Bare except, broad exception catching
│   │   └── test_debt_analysis.py    # Missing test coverage detection
│   │
│   ├── intelligence/
│   │   ├── report_writer_agent.py   # LLM-backed executive summary, priority actions, ROI analysis
│   │   ├── local_llm_service.py     # LocalLLMService: invoke_text(), invoke_json() with 20s timeout
│   │   ├── repo_profiler.py         # Tech stack detection, team size, bus factor, AI code detection
│   │   ├── rate_agent.py            # RateIntelligenceAgent: live market rate lookup with fallback
│   │   ├── benchmark_agent.py       # BenchmarkAgent: CISQ cost-per-function benchmarks
│   │   ├── security_cost_agent.py   # SecurityCostAgent: risk-weighted CVE cost model
│   │   ├── ownership_analyzer.py    # OwnershipAnalyzer: bus factor, top contributor share
│   │   ├── architecture_review_agent.py  # Architecture review insights
│   │   ├── hybrid_metrics_agent.py  # Blended static + LLM metrics
│   │   ├── semantic_triage_agent.py # LLM-based finding triage and action hints
│   │   └── test_gap_agent.py        # Test coverage gap analysis
│   │
│   ├── integrations/
│   │   ├── slack_notifier.py        # SlackNotifier: Block Kit message builder (header, metrics, breakdown, ROI, PDF button)
│   │   ├── jira_client.py           # JiraClient: creates Epic + Task per debt item with priority, labels, description
│   │   └── github_client.py         # GitHub API client for repo import and OAuth
│   │
│   ├── services/
│   │   └── report_service.py        # get_result_payload(), ensure_complete_result(), build_pdf_response()
│   │
│   ├── reports/
│   │   └── pdf_generator.py         # TechDebtPDFGenerator: ReportLab + Plotly PDF generation
│   │
│   ├── data/
│   │   └── vulnerability_fetcher.py # CVE/vulnerability data fetcher for dependency analysis
│   │
│   └── core/
│       └── cache_manager.py         # Disk-based cache (diskcache) for rate and benchmark data
│
└── frontend/
    ├── package.json                 # Next.js 14, React 18, TypeScript, Tailwind, Recharts, Tremor, shadcn
    ├── next.config.mjs              # Next.js config
    ├── tailwind.config.ts           # Tailwind config
    └── src/
        ├── app/
        │   ├── layout.tsx           # Root layout with app-shell, sidebar, auth header
        │   ├── page.tsx             # Main scanner UI: URL input, polling, results dashboard
        │   ├── portfolio/           # Multi-repo portfolio view
        │   ├── repositories/        # Per-repo scan history, trends, and findings
        │   ├── scans/               # Individual scan detail pages
        │   ├── auth/                # GitHub OAuth callback handling
        │   └── import/              # GitHub repo import flow
        ├── components/
        │   ├── AnalyzeForm.tsx           # GitHub URL input and submit button
        │   ├── ProgressBar.tsx           # Live scan progress with phase labels
        │   ├── DebtScoreCard.tsx         # Debt score 0–10 with color coding
        │   ├── PriorityActions.tsx       # Top-3 priority items with cost and sprint
        │   ├── CostBreakdownChart.tsx    # Category cost breakdown (Recharts)
        │   ├── DebtTrendChart.tsx        # Cost trend over scans (Recharts)
        │   ├── ActiveDebtChart.tsx       # Active vs resolved findings over time
        │   ├── ModuleRiskList.tsx        # Module-level risk table
        │   ├── RoadmapBoard.tsx          # Sprint-bucketed remediation roadmap
        │   ├── RepositoryInsightsPanel.tsx # Ownership, bus factor, team stats
        │   ├── RepoProfile.tsx           # Tech stack and multiplier display
        │   ├── ScanComparisonPanel.tsx   # Delta view between two scans
        │   ├── UnresolvedFindingsList.tsx # Filterable findings table with suppression
        │   ├── HeaderAuth.tsx            # GitHub OAuth header with user avatar
        │   ├── app-shell.tsx             # Main layout shell
        │   └── app-sidebar.tsx           # Navigation sidebar
        └── types/
            └── index.ts             # All TypeScript interfaces: DebtReport, StructuredFinding, PriorityAction, ROIAnalysis, RepoChangeRollup, RichRepoTrend, ScanRoadmapResponse, and 25+ others
```

---

## Getting Started

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Type union syntax (`X | Y`) used throughout requires 3.10+; 3.11 is recommended for `tomllib` and improved error messages |
| Node.js | 18+ | Required for Next.js 14 App Router |
| Git | any | Required by PyDriller and GitPython for repo cloning and history mining |
| Ollama | latest | Optional. Install from [ollama.ai](https://ollama.ai) for LLM-enhanced summaries |

### Local Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/AdishPadalia26/Tech-Debt-Quantifier.git
cd Tech-Debt-Quantifier

# 2. Set up Python virtual environment
cd backend
python -m venv .venv

# Activate — choose your OS:
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows PowerShell
.venv\Scripts\activate.bat       # Windows CMD

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment
# Copy the example file — SQLite works out of the box with no changes
cp .env.example .env

# 5. Start the backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Interactive API docs: http://localhost:8000/docs

# 6. In a new terminal — set up frontend
cd ../frontend
npm install

# 7. Start the frontend
npm run dev
# Open http://localhost:3000
```

The frontend's dev server reads `NEXT_PUBLIC_API_URL` from `.env.local`. The default value points to `http://localhost:8000`, which matches the backend started in step 5.

If you want LLM-enhanced summaries:

```bash
# Install Ollama from https://ollama.ai, then:
ollama pull qwen3.5:latest

# In backend/.env, set:
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3.5:latest
```

### Running Your First Scan

1. Open [http://localhost:3000](http://localhost:3000)
2. Paste any public GitHub URL, for example `https://github.com/pallets/flask`
3. Click **Analyze**
4. The progress bar moves through six phases: Cloning → Scanning files → Analyzing code patterns → Estimating costs → Generating report → Finalizing
5. Review the debt score, cost breakdown by category, priority actions, and ROI estimate

Typical scan time: 2–5 minutes for a medium-sized repo (< 50K LOC). The analysis caps at 200 files and 50 commits per run for performance.

---

## Configuration Reference

All configuration is read from environment variables via `python-dotenv`. The backend looks for `backend/.env`.

| Variable | Default | Required | Description |
|---|---|---|---|
| `DATABASE_URL` | `sqlite:///./techdebt.db` | No | SQLAlchemy connection string. Swap to `postgresql://user:pass@host:5432/db` for production without code changes. |
| `LLM_PROVIDER` | *(not set)* | No | Set to `ollama` to enable LLM-enhanced summaries. Any other value disables the LLM layer; the deterministic fallback runs instead. |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | For LLM | Ollama OpenAI-compatible API endpoint. |
| `OLLAMA_MODEL` | `qwen3.5:latest` | For LLM | Ollama model name. Also tried: `qwen2.5:3b` for lower RAM usage. |
| `OLLAMA_API_KEY` | `ollama` | For LLM | Passed as the API key to the OpenAI-compatible Ollama endpoint. |
| `LOCAL_LLM_TIMEOUT_SECONDS` | `20` | No | Per-LLM-call timeout. Increase for slower hardware; decrease to make the fallback trigger sooner. |
| `HF_TOKEN` | *(not set)* | For HF | HuggingFace API token for `langchain-huggingface` backend. |
| `HF_MODEL_ID` | `Qwen/Qwen2.5-7B-Instruct` | For HF | HuggingFace model ID. |
| `HF_FALLBACK_MODEL` | `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | For HF | Fallback HuggingFace model when primary is unavailable. |
| `OPENAI_API_KEY` | *(not set)* | For OpenAI | Used when `LLM_PROVIDER=openai`. |
| `ENGINEER_HOURLY_RATE` | `85` | No | Flat override for hourly rate. When set, overrides the role-calibrated defaults ($55/$84/$128). |
| `SLACK_BOT_TOKEN` | *(not set)* | For Slack | `xoxb-` prefixed token from Slack app OAuth configuration. |
| `SLACK_DEFAULT_CHANNEL` | `#tech-debt` | No | Default channel for Slack notifications. |
| `JIRA_SERVER` | *(not set)* | For Jira | Atlassian instance URL, e.g. `https://yourcompany.atlassian.net`. |
| `JIRA_EMAIL` | *(not set)* | For Jira | Email address associated with the Jira API token. |
| `JIRA_API_TOKEN` | *(not set)* | For Jira | Jira API token from Atlassian Account Settings. |
| `JIRA_PROJECT_KEY` | `TD` | No | Key of the Jira project where Epic and Task issues are created. |
| `GITHUB_CLIENT_ID` | *(not set)* | For OAuth | GitHub OAuth App client ID. Required for GitHub login. |
| `GITHUB_CLIENT_SECRET` | *(not set)* | For OAuth | GitHub OAuth App client secret. |
| `GITHUB_OAUTH_CALLBACK_URL` | *(not set)* | For OAuth | Callback URL registered in the GitHub OAuth App, e.g. `http://localhost:8000/auth/github/callback`. |
| `JWT_SECRET` | `dev-secret` | **Yes (prod)** | Secret for signing JWT session tokens. Set to a random 256-bit value in production. |
| `JWT_ALG` | `HS256` | No | JWT signing algorithm. |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | No | CORS origin allowlist for the frontend. Set to your production domain. |
| `ANALYSIS_CLONE_TIMEOUT_SECONDS` | `180` | No | Timeout for git clone operations. Increase for large repositories on slow networks. |
| `REPORT_TIMEOUT_SECONDS` | `180` | No | Timeout for the LLM report generation phase. |

---

## API Reference

### Core

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Start a new analysis job |
| `GET` | `/status/{job_id}` | Poll lightweight job status |
| `GET` | `/results/{job_id}` | Get full analysis result |
| `GET` | `/jobs` | List active in-memory jobs |
| `GET` | `/` | Compact health check |
| `GET` | `/health` | Detailed health with Ollama and DB status |

#### `POST /analyze`

Request body:
```json
{
  "github_url": "https://github.com/owner/repo",
  "repo_id": "owner/repo"
}
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Analysis started. Poll GET /results/{job_id} for updates."
}
```

#### `GET /status/{job_id}`

```json
{
  "job_id": "550e8400-...",
  "status": "processing",
  "progress": 40,
  "phase": "Analyzing code patterns"
}
```

Status values: `queued` → `processing` → `complete` | `error`

#### `GET /results/{job_id}`

Returns the full normalized result when complete:
```json
{
  "job_id": "...",
  "status": "complete",
  "scan_id": "...",
  "debt_score": 4.7,
  "total_cost_usd": 14820.50,
  "total_remediation_hours": 174.5,
  "total_remediation_sprints": 2.2,
  "cost_by_category": {
    "code_quality": { "cost_usd": 6200.0, "hours": 73.2, "item_count": 18 },
    "security": { "cost_usd": 4100.0, "hours": 32.0, "item_count": 5 }
  },
  "executive_summary": "...",
  "priority_actions": [...],
  "roi_analysis": {
    "total_fix_cost": 14820.50,
    "annual_maintenance_savings": 5928.20,
    "payback_months": 30,
    "3_year_roi_pct": 20,
    "recommended_budget": 3705.13,
    "recommendation": "Prioritize the top hotspots this quarter..."
  },
  "sanity_check": {
    "your_cost_per_function": 285.0,
    "industry_avg": 310.0,
    "variance_pct": -8.06,
    "is_reasonable": true,
    "assessment": "Slightly below industry average - reasonable condition"
  },
  "repo_profile": { ... },
  "data_sources_used": ["benchmarks:live", "hourly_rates:fallback"]
}
```

### Reports & Exports

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/report/{job_id}/pdf` | Download PDF report (ReportLab-generated) |
| `POST` | `/report/{job_id}/slack` | Send summary to Slack (optional `?channel=#channel`) |
| `POST` | `/report/{job_id}/jira` | Create Jira Epic + tickets (optional `?max_tickets=10&min_severity=medium`) |

#### `POST /report/{job_id}/jira` response

```json
{
  "ok": true,
  "epic_key": "TD-42",
  "epic_url": "https://yourcompany.atlassian.net/browse/TD-42",
  "created": [
    {
      "key": "TD-43",
      "url": "https://yourcompany.atlassian.net/browse/TD-43",
      "file": "src/core/processor.py",
      "cost": 1820.0,
      "summary": "[Code Quality] src/core/processor.py - process_batch ($1,820)"
    }
  ],
  "failed": [],
  "total_created": 5,
  "total_failed": 0
}
```

### Integrations

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/integrations/status` | Check Slack and Jira configuration |

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/github` | Initiate GitHub OAuth flow |
| `GET` | `/auth/github/callback` | Handle GitHub OAuth callback |
| `GET` | `/auth/me` | Return current authenticated user |

### Repositories & Scans (persisted history)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/repositories` | List tracked repositories |
| `GET` | `/repositories/{github_url}/history` | Full scan history for a repo |
| `GET` | `/repositories/{github_url}/trend` | Cost trend data for charts |
| `GET` | `/repositories/{github_url}/findings` | Unresolved findings across all scans |
| `GET` | `/scans/{scan_id}` | Single scan detail |
| `GET` | `/scans/{scan_id}/findings` | Paginated findings for a scan |
| `GET` | `/scans/{scan_id}/modules` | Module-level summary |
| `GET` | `/scans/{scan_id}/roadmap` | Sprint-bucketed remediation roadmap |
| `GET` | `/portfolio` | Aggregate stats across all repos |

---

## Integrations

### Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App → From Scratch**
3. Navigate to **OAuth & Permissions → Bot Token Scopes**
4. Add the `chat:write` scope
5. Click **Install to Workspace** and authorize
6. Copy the **Bot User OAuth Token** (starts with `xoxb-`)
7. Set `SLACK_BOT_TOKEN=xoxb-your-token` in `backend/.env`
8. Invite the bot to your target channel: `/invite @your-bot-name`
9. Optionally set `SLACK_DEFAULT_CHANNEL=#your-channel`

The Slack message is built with Block Kit and contains:
- **Header**: repo name
- **Context**: repo URL and analysis timestamp
- **Key metrics section**: debt score (color-coded 🟢/🟡/🔴), total cost, remediation hours, and sprints needed
- **Executive summary**: first 300 characters of the LLM or fallback summary
- **Cost breakdown**: top 3 categories by dollar value
- **Priority actions**: top 3 items with title, cost, and hours
- **ROI block**: fix cost, annual savings, and payback period
- **Action button**: "📄 Download PDF" linking to `/report/{job_id}/pdf`

### Jira

1. Log in to your Atlassian account
2. Go to **Account Settings → Security → API tokens → Create API token**
3. Copy the token value — it is shown only once
4. Set the following in `backend/.env`:
   ```
   JIRA_SERVER=https://yourcompany.atlassian.net
   JIRA_EMAIL=your-email@company.com
   JIRA_API_TOKEN=your-api-token
   JIRA_PROJECT_KEY=TD
   ```
5. Verify the connection: `GET /integrations/status`

When `POST /report/{job_id}/jira` is called:

1. `JiraClient` fetches `createmeta` to discover which issue types your project supports (avoids hardcoding "Task" or "Epic" which may not exist in all Jira configurations).
2. One **Epic** is created with the repo name, total cost, debt score, and executive summary.
3. Up to `max_tickets` (default 10) **Task** issues are created for findings at or above `min_severity` (default `medium`), sorted by `cost_usd` descending.

Each Task includes:
- **Summary**: `[Category] file/path - function ($cost)`
- **Priority**: mapped from severity (critical → Highest, high → High, medium → Medium, low → Low)
- **Labels**: category-specific (`tech-debt-code`, `tech-debt-security`, etc.) plus `tech-debt` and `automated`
- **Description**: file path, function, severity, base cost, final cost, remediation hours, risk multiplier, complexity score, cost drivers, and link back to the repo

---

## Optional: Hybrid LLM Estimation

By default the system runs in **formula-only mode** — deterministic, fast, and requires no external services. Setting `LLM_PROVIDER=ollama` activates the LLM layer.

### What changes with Ollama enabled

Formula-only mode already calculates all costs. With Ollama:
- The **executive summary** is LLM-generated (3 sentences, specific numbers, plain English) rather than a template string.
- **Priority actions** are LLM-ranked from the top findings rather than just sorted by cost.
- The **action hints** in each priority item reflect the LLM's interpretation of why the finding matters in context.

Cost numbers are never touched by the LLM. The dollar values come from the formula layer regardless of LLM availability.

### Installing Ollama and pulling a model

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the default model (2.3 GB)
ollama pull qwen3.5:latest

# Alternatively, a smaller model (1.9 GB) for constrained hardware
ollama pull qwen2.5:3b
```

`qwen3.5` is recommended because it follows JSON-format instructions reliably, fits in 4 GB of RAM on CPU, and handles the structured `priority_actions` prompt (which asks for a JSON array with 8 specific fields) without hallucinating extra fields. `qwen2.5:3b` is faster but occasionally deviates from the requested schema, triggering the fallback more often.

### Performance

Each scan makes at most two LLM calls: one for the executive summary (text) and one for priority actions (JSON). With `LOCAL_LLM_TIMEOUT_SECONDS=20`, the maximum LLM wait is 40 seconds on top of the analysis time. On a 2020 MacBook Pro M1, `qwen3.5` takes approximately 8–12 seconds per call.

### Confidence and fallback

`LocalLLMService.invoke_json()` extracts the first valid JSON object or array from the model output using a brace-depth scanner, tolerating markdown code fences and preamble text. If extraction fails, or if the model times out, `ReportWriterAgent` produces an equivalent result from the formula layer. The fallback is always active — there is no configuration needed and no error surfaced to the user when it triggers.

---

## Running Tests

```bash
# Backend unit tests
cd backend
python -m pytest tests/ -v

# Run individual test files
python -m pytest tests/test_cost_estimator.py -v
python -m pytest tests/test_api.py -v

# Frontend type checking (catches API shape mismatches)
cd frontend
npm run build

# Frontend linting
npm run lint
```

The backend test directory is at `backend/tests/`. Additional integration test scripts at the root of `backend/` (`test_analysis.py`, `test_pipeline.py`, `test_product_layers.py`) can be run directly with `python test_pipeline.py` against a live backend instance.

---

## Roadmap

```
- [x] Multi-category static analysis (8 debt categories)
- [x] Git history mining and churn detection (PyDriller)
- [x] Role-calibrated dollar-cost estimation engine
- [x] Hybrid LLM + formula cost model (Ollama + deterministic fallback)
- [x] PDF report generation (ReportLab + Plotly)
- [x] Slack integration (Block Kit message builder)
- [x] Jira integration (Epic + Task creation with auto-discovered issue types)
- [x] Scan history and per-repo trend charts
- [x] AI-generated code detection and premium multiplier
- [x] Ownership analysis (bus factor, top contributor share)
- [x] Scan comparison (delta view between two runs)
- [x] Module-level risk breakdown and roadmap board
- [x] GitHub OAuth login
- [x] Portfolio view (multi-repo aggregates)
- [ ] Finding suppression workflow (mark false positives)
- [ ] Custom hourly rate per team or role
- [ ] VS Code extension
- [ ] CI/CD integration (GitHub Actions, GitLab CI, Bitbucket Pipelines)
- [ ] PostgreSQL + production deployment guide (Docker Compose)
- [ ] Webhook notifications on new scan completion
- [ ] SARIF export for GitHub Code Scanning integration
- [ ] Custom debt category rules (user-defined regex/AST patterns)
```

---

## Contributing

```bash
# Fork the repository, then:
git checkout -b feature/your-feature-name

# Run tests before committing
cd backend && python -m pytest tests/ -v
cd ../frontend && npm run lint && npm run build

# Commit with Conventional Commits format:
git commit -m "feat(cost-model): add TypeScript complexity analysis via lizard"
git commit -m "fix(slack): truncate executive summary to 300 chars before block render"
git commit -m "chore(deps): bump fastapi to 0.115"

# Push and open a pull request against main
git push origin feature/your-feature-name
```

**Branch naming**: `feature/`, `fix/`, `chore/`, `docs/`

**Python style**: `black` for formatting, `ruff` for linting, type hints required on all function signatures.

**TypeScript style**: Prettier for formatting, `next lint` must pass.

**Adding a new debt category**: implement the analyzer class in `backend/tools/`, register it in `CostEstimator.estimate_total_cost()`, add the category to `_categorize_costs()`, and add the corresponding `CATEGORY_TO_LABEL` entry in `jira_client.py`.

---

## License

MIT License — see [LICENSE](LICENSE) file.
