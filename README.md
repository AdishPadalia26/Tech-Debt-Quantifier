# Tech Debt Quantifier

Analyzes GitHub repositories for technical debt and estimates the
real dollar cost of fixing it. Scans code quality, security,
documentation, test coverage, and dependency health.

## Features

- Static analysis across 6 debt categories
- Git history mining for churn and hotspot detection
- Hybrid LLM + formula cost estimation (optional, via local Ollama)
- Executive PDF reports
- Slack and Jira integrations
- ROI and payback period calculations

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.ai) (optional, for hybrid estimation)

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:3000

## Optional: Hybrid LLM Estimation

For more accurate cost estimates, run Ollama locally:

```bash
ollama pull qwen2.5:3b
```

Then set in backend/.env:
```
HYBRID_ESTIMATION_ENABLED=true
OLLAMA_MODEL=qwen2.5:3b
```

## Integrations

See backend/.env.example for Slack, Jira, and GitHub OAuth configuration.

## Running Tests

```bash
cd backend && python -m pytest tests/ -v
cd frontend && npm run build
```

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, LangChain, GitPython
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **LLM**: Ollama (local), qwen2.5 / qwen3
- **DB**: SQLite (dev), PostgreSQL (prod)