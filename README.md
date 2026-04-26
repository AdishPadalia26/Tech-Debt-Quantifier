# Tech Debt Quantifier

![FastAPI](https://img.shields.io/badge/FastAPI-backend-0f172a?logo=fastapi) ![Next.js 14](https://img.shields.io/badge/Next.js-14.2.35-000000?logo=nextdotjs) ![TypeScript](https://img.shields.io/badge/TypeScript-frontend-3178c6?logo=typescript) ![Ollama](https://img.shields.io/badge/Ollama-optional%20local%20LLM-111827) ![SQLite/PostgreSQL](https://img.shields.io/badge/DB-SQLite%20%7C%20PostgreSQL-1f2937) ![Slack](https://img.shields.io/badge/Slack-supported-4a154b?logo=slack) ![Jira](https://img.shields.io/badge/Jira-supported-0052cc?logo=jira)

Most engineering teams know they have technical debt. Few can show what it costs, where it concentrates, or which fixes pay back fastest. Tech Debt Quantifier clones a GitHub repository, runs static analysis, git-history mining, ownership analysis, and optional local-LLM calibration, then turns the result into a score, a dollar estimate, a remediation-hours forecast, a module-level roadmap, and exportable Slack, Jira, and PDF outputs.

> Screenshot placeholder: add a current dashboard capture here.

## 2. How It Works

A scan starts with a GitHub URL in the Next.js frontend. The browser sends `POST /analyze`, the FastAPI backend creates a background job, clones the repository into a local cache, runs the analyzer stack, computes a cost model, and then hands the structured output to the reporter agent for executive summary, priorities, ROI, and optional local-LLM insights. Results are normalized into a stable payload for polling, persisted into SQLAlchemy models for trend and portfolio views, and can then be exported to PDF, Slack, or Jira.

```text
+--------------------------------------------------------------------------+
|                              User Interface                               |
|                Next.js 14 - TypeScript - Tailwind - shadcn               |
+----------------------------------+---------------------------------------+
                                   |
                                   | POST /analyze
                                   v
+--------------------------------------------------------------------------+
|                             FastAPI Backend                               |
|                                                                          |
|  +--------------+   +----------------+   +-----------------------------+ |
|  | CrawlerAgent |   | AnalyzerAgent  |   | ReporterAgent               | |
|  | clone_repo   |-->| CostEstimator  |-->| semantic triage             | |
|  | Git cache    |   | StaticAnalyzer |   | architecture review         | |
|  +--------------+   | GitMiner       |   | test-gap review             | |
|         |           | RepoProfiler   |   | hybrid metrics calibration  | |
|         |           +-------+--------+   | executive summary           | |
|         |                   |            | priorities and ROI          | |
|         |                   v            +-----------------------------+ |
|         |      +------------------------------------------------------+ |
|         |      |                    Cost Estimator                    | |
|         |      | base hours x severity x churn x repo risk x rate    | |
|         |      | + baseline maintenance cost x combined multiplier    | |
|         |      +------------------------------------------------------+ |
|         |                   |                                            |
|         v                   v                                            |
|  +--------------+   +----------------+   +-----------------------------+ |
|  | SQLAlchemy   |   | PDF Generator  |   | SlackNotifier / JiraClient  | |
|  | Scan history |   | ReportLab      |   | report export and ticketing | |
|  | Findings     |   +----------------+   +-----------------------------+ |
|  | Modules      |                                                        |
|  | Roadmap      |                                                        |
|  +--------------+                                                        |
+----------------------------------+---------------------------------------+
                                   |
                                   v
                    +-----------------------------------------+
                    | Local Ollama or alternate LLM provider  |
                    | qwen3.5:latest by default               |
                    | optional hybrid estimation              |
                    +-----------------------------------------+
```

## 3. The Cost Model

### 3a. The Formula

The estimator uses two layers:

1. a per-item effort and cost model
2. a repository-level overhead and baseline adjustment

```text
Per-item Estimated Cost
= base_hours x severity_multiplier x churn_multiplier x repo_risk_multiplier x hourly_rate

Repository Total
= (sum(item_costs) + baseline_function_cost) x combined_repo_multiplier
```

In hybrid mode, `base_hours` comes from `LLMEstimator.realistic_hours`. In formula-only fallback mode, `base_hours` comes from hardcoded category defaults in [llm_estimator.py](/D:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/backend/tools/llm_estimator.py).

The main hardcoded multipliers in the current code are:

| Factor | Value | Source |
|--------|-------|--------|
| Hybrid churn multiplier | 1.0 at 0 changes | `CostEstimator._apply_formula()` |
| Hybrid churn multiplier | 1.1 at 1-4 changes | `CostEstimator._apply_formula()` |
| Hybrid churn multiplier | 1.3 at 5-9 changes | `CostEstimator._apply_formula()` |
| Hybrid churn multiplier | 1.8 at 10-19 changes | `CostEstimator._apply_formula()` |
| Hybrid churn multiplier | 2.5 at 20+ changes | `CostEstimator._apply_formula()` |
| Git hotspot churn multiplier | 1.0 at 0-2 changes | `constants.CHURN_MULTIPLIERS` |
| Git hotspot churn multiplier | 1.3 at 3-5 changes | `constants.CHURN_MULTIPLIERS` |
| Git hotspot churn multiplier | 1.7 at 6-10 changes | `constants.CHURN_MULTIPLIERS` |
| Git hotspot churn multiplier | 2.2 at 11-19 changes | `constants.CHURN_MULTIPLIERS` |
| Git hotspot churn multiplier | 3.0 at 20+ changes | `constants.CHURN_MULTIPLIERS` |
| Severity multiplier | `1 + (severity_score - 5) * 0.08`, clamped to `0.7x`-`2.0x` | `CostEstimator._apply_formula()` |
| Repo risk multiplier | `combined_multiplier / 3`, clamped to `1.0x`-`2.0x` | `CostEstimator._apply_formula()` |
| Repo age multiplier | `1.4x` over 10 years | `RepoProfiler.calculate_multipliers()` |
| Repo age multiplier | `1.3x` over 5.5 years | `RepoProfiler.calculate_multipliers()` |
| Repo age multiplier | `1.1x` over 2.7 years | `RepoProfiler.calculate_multipliers()` |
| Repo age multiplier | `0.8x` under 180 days | `RepoProfiler.calculate_multipliers()` |
| Bus factor multiplier | `2.0x` when bus factor = 1 | `RepoProfiler.calculate_multipliers()` |
| Bus factor multiplier | `1.5x` when bus factor = 2 | `RepoProfiler.calculate_multipliers()` |
| Bus factor multiplier | `1.2x` when bus factor = 3-4 | `RepoProfiler.calculate_multipliers()` |
| Team size multiplier | `1.5x` for solo repos | `RepoProfiler.calculate_multipliers()` |
| Team size multiplier | `1.2x` for 2-3 engineers | `RepoProfiler.calculate_multipliers()` |
| Team size multiplier | `1.0x` for 4-10 engineers | `RepoProfiler.calculate_multipliers()` |
| Team size multiplier | `0.9x` for 11+ engineers | `RepoProfiler.calculate_multipliers()` |
| Baseline function cost | 12 minutes per function | `constants.FUNCTION_BASELINE_MINUTES` |
| Sprint conversion | 80 hours per sprint | `constants.HOURS_PER_SPRINT` |
| Maintenance overhead fallback | `6.0x` | `constants.MAINTENANCE_OVERHEAD_MULTIPLIER` |

Two more weights affect cost even before the final repository multiplier:

| Factor | Value | Source |
|--------|-------|--------|
| Business impact weight - low | `0.9x` | `constants.BUSINESS_IMPACT_WEIGHTS` |
| Business impact weight - medium | `1.0x` | `constants.BUSINESS_IMPACT_WEIGHTS` |
| Business impact weight - high | `1.2x` | `constants.BUSINESS_IMPACT_WEIGHTS` |
| Business impact weight - critical | `1.5x` | `constants.BUSINESS_IMPACT_WEIGHTS` |
| Confidence floor | `0.25x` minimum | `tools.scoring.calculate_cost()` |

### 3b. Debt Categories

The scanner currently emits these debt categories and effort defaults:

| Category | What it looks for | Base remediation effort |
|----------|-------------------|-------------------------|
| `code_quality` | complexity hotspots, duplicate logic, unreachable code, unused private helpers | 10 min, 30 min, 60 min, or 120 min for complexity severities; 1.5 h to 8.0 h for duplication; 0.5 h unreachable code; 0.75 h unused helper |
| `security` | Python security findings from Bandit plus dependency vulnerabilities from OSV.dev | 1.5 h low, 4 h medium, 8 h high for Bandit; 1 h low, 3 h medium, 6 h high, 12 h critical for dependency vulns |
| `documentation` | missing docstrings from static function analysis | 10 min |
| `architecture` | oversized modules, high fanout, cyclic imports | 8 h oversized module, 5 h fanout hotspot, 10 h cycle |
| `test_debt` | source files without matching tests and high-churn hotspots without tests | 2 h source file without tests, 4 h hotspot without tests |
| `dependency` | loose version constraints and dependency hygiene issues | 0.75 h medium, 1.5 h high |
| `reliability` | bare `except`, broad exception handling, silent handlers, mutable defaults | 1.25 h to 2.0 h depending on smell |
| `performance` | nested loops, expression accumulation in loops, repeated append patterns | 1.0 h to 1.5 h depending on smell |

### 3c. Hybrid LLM Mode

Hybrid mode is optional and local-first. The formula layer still owns the final cost math, but the local model can improve the realism of effort estimates and top-level reporting:

- `LLMEstimator` asks the local model for realistic remediation hours, complexity, risk, and confidence for each debt item.
- `ReporterAgent` and [report_writer_agent.py](/D:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/backend/intelligence/report_writer_agent.py) ask the configured model for semantic triage, architecture review, test-gap review, executive summary, and priority actions.
- `hybrid_metrics_agent.py` applies bounded calibration to top-level metrics instead of replacing them outright.

`rate_confidence` in the output is deterministic metadata from the rate and benchmark pipeline. LLM confidence on individual debt items is stored separately and is then folded into final cost calculations through the shared scoring helpers.

## 4. Tech Stack

### Backend

| Technology | Version | Why |
|------------|---------|-----|
| FastAPI | `0.116.1` | Background-job APIs, typed request models, and automatic OpenAPI docs fit the scan-and-poll workflow better than a lighter sync framework |
| Uvicorn | `0.35.0` | Fast local ASGI serving with straightforward reload behavior during analyzer development |
| SQLAlchemy | `2.0.43` | Repository history, scan findings, roadmap buckets, and auth users all need relational persistence without tying the code to one database vendor |
| Pydantic | `2.11.7` | Request and response shapes stay explicit across scan results, GitHub auth, and report export payloads |
| GitPython | `3.1.45` | Local repo validation and clone management stay inside Python instead of shelling out for every repo operation |
| PyDriller | `2.9` | Churn, hotspots, author ownership, and repository history analysis are core to the debt model |
| Radon | `6.0.1` | Complexity analysis provides one of the main debt signals without needing a heavyweight language server |
| Lizard | `1.18.0` | Function-level complexity and size metrics complement Radon and make hotspot ranking more stable |
| Bandit | `1.8.6` | Security findings are integrated into the same cost model as maintainability debt |
| ReportLab | `4.4.4` | The PDF report needs custom layout control, dark theming, and multi-section tables instead of HTML-to-PDF shortcuts |
| LangChain | `0.3.27` | Reporter-side prompt composition and provider abstraction are already wired through the intelligence agents |
| Ollama | local endpoint | Local execution keeps repo analysis and executive summaries inside the team network and avoids per-scan API spend |
| SQLite / PostgreSQL | SQLAlchemy URL driven | SQLite keeps local setup light; PostgreSQL is already supported through the same ORM models for shared environments |

### Frontend

| Technology | Version | Why |
|------------|---------|-----|
| Next.js | `14.2.35` | App Router gives route-based dashboards, scan detail pages, and callback flows without building client-side routing from scratch |
| React | `18` | The analyzer dashboard, polling UI, and portfolio views rely on client state and streaming-friendly rendering |
| TypeScript | `5` | Scan payloads are large and nested, so strict contracts reduce UI breakage when backend shapes evolve |
| Tailwind CSS | `3.4.17` | Dense dashboards, tables, and cards move faster with utility classes than with a custom CSS architecture |
| shadcn/Radix primitives | various | Sidebar, tabs, drawers, and tooltips reuse accessible building blocks instead of custom one-off widgets |
| Recharts | `3.8.0` | Portfolio and ROI charts need explicit control over dark-mode contrast and tooltip behavior |
| Tremor | `3.18.7` | KPI cards and chart wrappers cover a good chunk of the dashboard without writing another metric-card layer |
| Geist | `1.7.0` | The current UI intentionally leans into a Vercel-style product presentation |
| Axios | `1.13.6` | Shared auth-aware API access and interceptors stay centralized instead of scattering fetch boilerplate |
| Motion | `12.38.0` | Count-up KPIs and staggered cards use one lightweight animation system instead of ad hoc transitions |

## 5. Project Structure

```text
tech-debt-quantifier/
|-- backend/
|   |-- main.py                         # FastAPI app, background job runner, health endpoints, and in-memory polling state
|   |-- constants.py                    # Central numeric defaults: churn bands, complexity thresholds, baseline minutes, sprint hours
|   |-- config.py                       # Environment-variable defaults for Slack, Jira, and GitHub OAuth
|   |-- mcp_server.py                   # Clone, cache, and local analysis tools exposed through FastMCP
|   |-- report_generator.py             # Stable import shim for PDF generation
|   |-- requirements.txt                # Backend dependency manifest
|   |-- api/
|   |   |-- deps.py                     # JWT auth dependencies and GitHub token extraction
|   |   `-- routes/
|   |       |-- auth.py                 # GitHub OAuth login, callback, and current-user endpoints
|   |       |-- github.py               # GitHub repo/org listing and repo import endpoints
|   |       |-- integrations.py         # Slack delivery, Jira ticket creation, and Jira connection test
|   |       |-- portfolio.py            # Authenticated portfolio summary, trends, and delete endpoints
|   |       |-- repositories.py         # Repository history, summary, triage, changes, unresolved, and active-trend routes
|   |       |-- reports.py              # PDF download endpoint
|   |       `-- scans.py                # Scan detail, findings, modules, roadmap, compare, suppress, and feedback routes
|   |-- agents/
|   |   |-- orchestrator.py             # Agent orchestration entrypoint
|   |   |-- crawler.py                  # Clone step that fills `repo_path`
|   |   |-- analyzer.py                 # Cost-estimator step
|   |   |-- reporter.py                 # Executive summary, ROI, and bounded local-LLM reporting step
|   |   |-- state.py                    # Shared agent-state typing
|   |   `-- llm_factory.py              # LLM provider switch for Ollama, Hugging Face, and OpenAI
|   |-- database/
|   |   |-- connection.py               # Engine, SessionLocal, and SQLite/PostgreSQL selection
|   |   |-- crud.py                     # Scan persistence and repository history queries
|   |   `-- models.py                   # SQLAlchemy models for users, repositories, scans, findings, modules, roadmap, suppression, feedback
|   |-- data/
|   |   |-- sonarqube_rules.py          # SonarCloud remediation-time fetcher with cache fallback
|   |   |-- vulnerability_fetcher.py    # OSV.dev dependency vulnerability lookup
|   |   `-- rate_fetcher.py             # External rate-data fetch helpers
|   |-- intelligence/
|   |   |-- repo_profiler.py            # Tech stack, team, bus factor, repo age, AI-code suspicion, and repo multipliers
|   |   |-- rate_agent.py               # Market-rate blending across external sources
|   |   |-- benchmark_agent.py          # CISQ-style benchmark retrieval
|   |   |-- ownership_analyzer.py       # Ownership concentration and hotspot contributor analysis
|   |   |-- security_cost_agent.py      # Security-cost weighting helpers
|   |   |-- local_llm_service.py        # Timeout-bounded text/JSON calls to the configured local model
|   |   |-- semantic_triage_agent.py    # LLM-assisted triage summaries for findings
|   |   |-- architecture_review_agent.py# LLM-assisted architecture review
|   |   |-- test_gap_agent.py           # LLM-assisted test-gap review
|   |   |-- hybrid_metrics_agent.py     # Bounded calibration for top-level metrics
|   |   `-- report_writer_agent.py      # Executive summary, priorities, and deterministic ROI writer
|   |-- integrations/
|   |   |-- github_client.py            # GitHub API wrapper for repo/org import flows
|   |   |-- slack_notifier.py           # Slack Block Kit analysis message builder
|   |   `-- jira_client.py              # Jira metadata discovery, epic creation, and ticket export
|   |-- reports/
|   |   `-- pdf_generator.py            # Dark-theme multi-section PDF report layout
|   |-- services/
|   |   |-- finding_aggregator.py       # Structured findings, module summaries, and roadmap buckets
|   |   |-- portfolio_service.py        # Portfolio rollups for tracked repositories
|   |   `-- report_service.py           # Shared result lookup and PDF response helpers
|   |-- tools/
|   |   |-- static_analysis.py          # Radon/Lizard complexity, Bandit scan, and docstring detection
|   |   |-- git_mining.py               # PyDriller hotspot mining and churn-based cost pressure
|   |   |-- cost_estimator.py           # Main formula engine, analyzer orchestration, and hybrid estimation pass
|   |   |-- llm_estimator.py            # Per-item LLM prompt, parser, and fallback effort defaults
|   |   |-- architecture_analysis.py    # Oversized modules, fanout, and cyclic dependency checks
|   |   |-- duplication_analysis.py     # Duplicate Python function-body detection
|   |   |-- dependency_analysis.py      # Loose-version dependency hygiene checks
|   |   |-- reliability_analysis.py     # Bare excepts, silent handlers, and mutable-default detection
|   |   |-- performance_analysis.py     # Loop-based performance smell detection
|   |   |-- dead_code_analysis.py       # Unreachable code and unused private helper detection
|   |   |-- test_debt_analysis.py       # Missing-test heuristics for source files and hotspots
|   |   `-- scoring.py                  # Shared confidence, business impact, and cost helpers
|   `-- tests/
|       |-- test_api.py                 # FastAPI endpoint tests
|       |-- test_cost_estimator.py      # Cost-model tests
|       `-- test_llm_estimator.py       # LLM fallback and parser tests
`-- frontend/
    |-- package.json                    # Frontend dependencies and scripts
    |-- next.config.mjs                 # Next.js configuration
    |-- scripts/dev-server.cjs          # Local dev server wrapper
    `-- src/
        |-- app/
        |   |-- layout.tsx              # Root layout, dark theme, and app shell wiring
        |   |-- globals.css             # Theme tokens and base styling
        |   |-- page.tsx                # Main analyzer dashboard, progress polling, charts, exports, and result tabs
        |   |-- auth/callback/page.tsx  # GitHub OAuth callback token capture
        |   |-- import/page.tsx         # GitHub repo import UI
        |   |-- portfolio/page.tsx      # Portfolio table and selected-repository insights
        |   |-- repositories/[...repo]/page.tsx # Repository detail view
        |   |-- scans/[scanId]/page.tsx # Scan detail view
        |   `-- debug/[jobId]/page.tsx  # Job-level debug page
        |-- components/
        |   |-- AnalyzeForm.tsx         # URL input plus signed-in GitHub repo picker
        |   |-- ProgressBar.tsx         # Polling and progress-phase UI
        |   |-- HeaderAuth.tsx          # GitHub sign-in state in the app header
        |   |-- ActiveDebtChart.tsx     # Active unresolved debt trend chart
        |   |-- RepositoryInsightsPanel.tsx # Repository rollup card surface
        |   |-- UnresolvedFindingsList.tsx  # Unresolved findings list
        |   |-- ScanComparisonPanel.tsx # Scan comparison delta panel
        |   |-- ModuleRiskList.tsx      # Scan module risk list
        |   |-- error-boundary.tsx      # Runtime guard around result panels
        |   `-- ui/*                    # Shared design-system primitives
        |-- hooks/
        |   `-- useRepositoryInsights.ts# Shared repository detail and portfolio insight fetching
        |-- lib/
        |   |-- api.ts                  # Typed API client, auth token helpers, and polling logic
        |   |-- routes.ts               # Frontend route helpers
        |   `-- utils.ts                # Classname utility helpers
        `-- types/
            `-- index.ts                # TypeScript contracts for scans, findings, trends, GitHub import, and auth
```

## 6. Getting Started

### Prerequisites

- Python 3.11+ - the backend uses modern typing syntax and the team guide targets 3.11+
- Node.js 18+ - required by Next.js 14
- Git - repository clone and history analysis depend on it directly
- Ollama (optional) - required only if you want local hybrid estimation and local-LLM reporting; install from [ollama.ai](https://ollama.ai)

### Local Development Setup

1. Clone the repository and move into it.

```bash
git clone https://github.com/yourusername/tech-debt-quantifier.git
cd tech-debt-quantifier
```

2. Create a virtual environment for the backend.

```bash
cd backend
python -m venv .venv
```

3. Activate the virtual environment.

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
.venv\Scripts\activate.bat
```

4. Install backend dependencies.

```bash
pip install -r requirements.txt
```

5. Create a backend environment file.

```bash
copy .env.example .env
```

If `.env.example` does not exist in your branch yet, create `.env` manually with at least:

```env
DATABASE_URL=sqlite:///./techdebt.db
FRONTEND_ORIGIN=http://127.0.0.1:3000
JWT_SECRET=change-me
JWT_ALG=HS256
```

6. Start the backend API.

```bash
uvicorn main:app --reload --port 8000
```

OpenAPI docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

7. In a new terminal, install frontend dependencies.

```bash
cd ../frontend
npm install
```

8. Create a frontend environment file.

```bash
copy .env.local.example .env.local
```

If `.env.local.example` does not exist in your branch yet, create `.env.local` manually with:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

9. Start the frontend.

```bash
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

### Running Your First Scan

1. Open [http://127.0.0.1:3000](http://127.0.0.1:3000)
2. Paste any public GitHub URL such as `https://github.com/pallets/flask`
3. Click `Analyze`
4. Wait for the poller to move through clone, scan, estimate, and report phases
5. Review the debt score, category costs, roadmap buckets, and priority actions

## 7. Configuration Reference

The codebase reads environment variables from route modules, config helpers, analyzer services, and the local-LLM layer. The table below focuses on variables that are actively used in the current code.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | `sqlite:///./techdebt.db` | No | SQLAlchemy connection string; SQLite works locally, PostgreSQL works through the same models |
| `FRONTEND_ORIGIN` | `http://localhost:3000` in some code paths, but local setup is safest on `http://127.0.0.1:3000` | No | Frontend redirect target for OAuth callback and CORS |
| `JWT_SECRET` | `super-secret-dev-key-12345` in local defaults | No for local, yes for shared envs | JWT signing secret for app auth |
| `JWT_ALG` | `HS256` | No | JWT signing algorithm |
| `GITHUB_CLIENT_ID` | empty | For GitHub OAuth | GitHub OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | empty | For GitHub OAuth | GitHub OAuth app client secret |
| `GITHUB_OAUTH_CALLBACK_URL` | empty unless set | For GitHub OAuth | GitHub callback URL, typically `http://127.0.0.1:8000/auth/github/callback` |
| `GITHUB_TOKEN` | empty | Optional | Fallback token for backend GitHub API access outside user OAuth |
| `TDQ_REPO_CACHE_DIR` | backend-local `.cache/tech-debt-repos` | No | Clone cache directory for analyzed repos |
| `GIT_CLONE_TIMEOUT_SECONDS` | `120` | No | Git clone subprocess timeout |
| `ANALYSIS_CLONE_TIMEOUT_SECONDS` | `180` | No | Outer pipeline timeout for the clone phase |
| `REPORT_TIMEOUT_SECONDS` | `180` | No | Timeout for report generation phase |
| `LOCAL_LLM_TIMEOUT_SECONDS` | `20` | No | Timeout for local model text and JSON calls |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | No | Base URL for Ollama-compatible chat calls |
| `OLLAMA_MODEL` | `qwen3.5:latest` | No | Default local model for reporting and hybrid estimation |
| `OLLAMA_API_KEY` | `ollama` | No | Placeholder auth value for OpenAI-compatible Ollama clients |
| `LLM_PROVIDER` | `huggingface_api` in `llm_factory.py`; local flows separately call Ollama services | No | Reporter-side provider switch for Ollama, Hugging Face, or OpenAI |
| `HF_TOKEN` | empty | For Hugging Face hosted inference | Token for remote Hugging Face provider path |
| `HF_MODEL_ID` | provider default | Optional | Model ID for Hugging Face-backed reporting |
| `OPENAI_API_KEY` | empty | For OpenAI provider path | API key for the OpenAI provider option in the reporter factory |
| `HYBRID_ESTIMATION_ENABLED` | `true` | No | Enables LLM-assisted per-item estimate refinement |
| `ENGINEER_HOURLY_RATE` | `85` if no richer rate data resolves | No | Baseline hourly rate when market-rate fetchers do not override it |
| `SLACK_BOT_TOKEN` | empty | For Slack | Bot token used by the Slack notifier |
| `SLACK_DEFAULT_CHANNEL` | empty | For Slack | Default channel for analysis export |
| `JIRA_SERVER` | empty | For Jira | Jira base URL such as `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | empty | For Jira | Jira account email |
| `JIRA_API_TOKEN` | empty | For Jira | Jira API token |
| `JIRA_PROJECT_KEY` | `TD` | No | Jira project key for epic and ticket creation |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` in frontend helpers; local setup is safest on `http://127.0.0.1:8000` | No | Base URL used by the frontend API client |

## 8. API Reference

### Core scan flow

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Root health/status payload |
| `GET` | `/health` | Health check with version |
| `POST` | `/analyze` | Queue a new scan |
| `GET` | `/status/{job_id}` | Poll scan progress |
| `GET` | `/results/{job_id}` | Fetch the normalized result payload |
| `GET` | `/jobs` | Inspect active in-memory jobs |
| `GET` | `/debug/results/{job_id}` | Debug view of result state |
| `GET` | `/debug/raw/{job_id}` | Raw persisted result lookup |
| `GET` | `/debug/scans` | Debug list of scans |

`POST /analyze` request body:

```json
{
  "github_url": "https://github.com/pallets/flask",
  "repo_id": "optional-repo-id"
}
```

Typical `GET /status/{job_id}` response:

```json
{
  "job_id": "uuid",
  "status": "processing",
  "progress": 40,
  "phase": "Analyzing code patterns",
  "error": null
}
```

Typical `GET /results/{job_id}` response shape:

```json
{
  "job_id": "uuid",
  "github_url": "https://github.com/pallets/flask",
  "raw_analysis": {
    "debt_score": 3.29,
    "total_cost_usd": 118383.43,
    "total_remediation_hours": 909.85,
    "total_remediation_sprints": 11.37,
    "debt_items": [],
    "cost_by_category": {},
    "executive_summary": ""
  },
  "priority_actions": [],
  "roi_analysis": {},
  "repo_profile": {},
  "data_sources": {}
}
```

### Auth and GitHub import

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/github/login` | Start GitHub OAuth |
| `GET` | `/auth/github/callback` | OAuth callback that issues JWT and redirects to the frontend |
| `GET` | `/me` | Current user profile |
| `GET` | `/auth/me` | Current user profile alias |
| `GET` | `/github/repos` | List personal GitHub repos for the signed-in user |
| `GET` | `/github/orgs` | List GitHub orgs for the signed-in user |
| `GET` | `/github/orgs/{org}/repos` | List repos for a specific GitHub org |
| `POST` | `/github/import` | Import a GitHub repo into app persistence |

`POST /github/import` request body:

```json
{
  "full_name": "pallets/flask",
  "html_url": "https://github.com/pallets/flask",
  "private": false,
  "default_branch": "main"
}
```

### Portfolio and repository history

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/portfolio` | Current user's repository portfolio |
| `GET` | `/portfolio/summary` | Aggregated portfolio summary |
| `GET` | `/portfolio/trends` | Portfolio trend points |
| `DELETE` | `/portfolio/{repo_id:path}` | Delete a tracked repository |
| `GET` | `/history/{repo_url:path}` | Scan history for one repository |
| `GET` | `/history/{repo_url:path}/rich` | Rich scan history with more metadata |
| `GET` | `/repositories` | Repository listing from persistence |
| `GET` | `/repositories/{repo_url:path}/summary` | Summary rollup for one repository |
| `GET` | `/repositories/{repo_url:path}/triage` | Triage rollup for one repository |
| `GET` | `/repositories/{repo_url:path}/unresolved` | Unresolved findings for one repository |
| `GET` | `/repositories/{repo_url:path}/changes` | Finding delta/change view for one repository |
| `GET` | `/repositories/{repo_url:path}/active-trend` | Active debt trend for one repository |

### Scan detail surfaces

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/scan/{scan_id}` | Full scan record |
| `GET` | `/scan/{scan_id}/summary` | Summary payload for one scan |
| `GET` | `/scan/{scan_id}/findings` | Findings list for one scan |
| `GET` | `/scan/{scan_id}/modules` | Module summaries for one scan |
| `GET` | `/scan/{scan_id}/roadmap` | Roadmap buckets for one scan |
| `GET` | `/scan/compare` | Compare two scans |
| `POST` | `/scan/{scan_id}/findings/{finding_id}/suppress` | Suppress one finding |
| `POST` | `/scan/{scan_id}/findings/{finding_id}/feedback` | Submit user feedback on one finding |

`POST /scan/{scan_id}/findings/{finding_id}/feedback` request body:

```json
{
  "rating": "accurate",
  "comment": "This is useful"
}
```

### Reports and exports

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/report/{job_id}/pdf` | Download the generated PDF report |
| `POST` | `/report/{job_id}/slack` | Send the report to Slack |
| `POST` | `/report/{job_id}/jira` | Create Jira tickets from debt items |
| `GET` | `/integrations/status` | Check Slack and Jira configuration status |
| `GET` | `/jira/test` | Test Jira credentials without creating tickets |

`POST /report/{job_id}/slack` request body:

```json
{
  "channel": "#eng-alerts"
}
```

`POST /report/{job_id}/jira` query parameters:

```text
max_tickets=10
min_severity=medium
```

## 9. Integrations

### Slack

Setup:

1. Open [api.slack.com/apps](https://api.slack.com/apps)
2. Create a new app from scratch
3. Under OAuth & Permissions, add the `chat:write` bot scope
4. Install the app to the workspace
5. Copy the Bot User OAuth Token into `SLACK_BOT_TOKEN`
6. Set `SLACK_DEFAULT_CHANNEL` if you want a default destination
7. Invite the bot to the destination channel with `/invite @bot-name`

The Slack export uses Block Kit. The notifier builds a header, key metrics, category cost breakdown, priority actions, and quick links back to the scan or repository context.

### Jira

Setup:

1. Create an API token in Atlassian account security settings
2. Set `JIRA_SERVER` to your Jira base URL
3. Set `JIRA_EMAIL` to the Jira account email
4. Set `JIRA_API_TOKEN` to the generated token
5. Set `JIRA_PROJECT_KEY` to the destination project
6. Call `/jira/test` before the first export

The Jira export path creates:

- one Epic when the project supports it
- up to `max_tickets` issues sorted by cost descending
- severity-based Jira priorities
- category-based labels
- wiki-format descriptions with file, category, severity, cost, hours, and cost drivers

## 10. Optional: Hybrid LLM Estimation

Hybrid estimation changes the output in two places:

1. `LLMEstimator` asks the local model for more realistic remediation hours per debt item
2. the reporter-side agents generate semantic triage, architecture commentary, test-gap review, executive summary, and bounded metric calibration

To enable the local Ollama path:

```bash
ollama pull qwen3.5:latest
ollama serve
```

Recommended local configuration:

```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3.5:latest
HYBRID_ESTIMATION_ENABLED=true
```

Other provider paths already exist in code:

- Hugging Face hosted inference via `HF_TOKEN`
- Hugging Face local model loading via `LLM_PROVIDER=huggingface_local`
- OpenAI via `LLM_PROVIDER=openai`

Tradeoff:

- formula-only mode is faster and fully local to the analyzer stack
- hybrid mode adds one local-model pass per debt item plus the reporting passes
- the code limits local text and JSON model calls to 20 seconds by default

Fallback behavior:

- if Ollama is unreachable, `CostEstimator` logs a warning and falls back to formula-only estimation
- if one item times out, the estimator falls back for that item
- if the reporter-side local model times out, the scan still completes with deterministic summaries and ROI

## 11. Running Tests

Backend tests:

```bash
cd backend
python -m pytest tests/ -v
```

Frontend production build:

```bash
cd frontend
npm run build
```

Frontend lint:

```bash
cd frontend
npm run lint
```

A healthy run ends with output like:

```text
backend/tests/test_api.py::test_health PASSED
backend/tests/test_cost_estimator.py::test_estimate_total_cost PASSED
backend/tests/test_llm_estimator.py::test_fallback_estimates PASSED
============================= passed =============================

No ESLint warnings or errors
```

## 12. Roadmap

- [x] Multi-category static analysis
- [x] Git history mining and churn detection
- [x] Dollar-denominated cost estimation
- [x] Hybrid LLM + formula estimation
- [x] PDF report generation
- [x] Slack integration
- [x] Jira integration
- [x] Scan history and portfolio view
- [x] GitHub OAuth login and repo import
- [ ] Queue-backed execution with Redis/Celery instead of in-process background tasks
- [ ] Stronger non-Python analysis coverage across the newer analyzer categories
- [ ] Production deployment defaults beyond the current local-first setup
- [ ] Deeper workspace and authorization controls beyond per-user scan scoping

## 13. Contributing

Use the standard fork and pull-request flow:

1. Fork the repository
2. Create a feature branch from `main`
3. Implement the change
4. Run backend tests, frontend build, and frontend lint
5. Open a pull request with a clear description and screenshots when UI changes are involved

Suggested branch prefixes:

- `feature/`
- `fix/`
- `chore/`

Suggested commit format:

```text
feat: add repository-level roadmap export
fix: guard ActiveDebtChart against empty points
chore: refresh README configuration table
```

Python code in this repo follows the existing Black-style 88-character format and typed-function conventions from [AGENTS.md](/D:/Documents/Desktop/Tech-Debt/tech-debt-quantifier/AGENTS.md). Frontend work should continue to pass `npm run build` and `npm run lint` before review.

## 14. License

```text
MIT License - see LICENSE file
```
