# AGENTS.md - Tech Debt Quantifier

## Overview

Tech Debt Quantifier is an AI-powered platform that scans GitHub repositories, measures technical debt in dollar and time terms, categorizes it by type and severity, and generates executive-ready reports.

---

## Project Structure

```
tech-debt-quantifier/
├── backend/
│   ├── main.py              # FastAPI server entry point
│   ├── mcp_server.py        # MCP (Model Context Protocol) server
│   ├── agents/              # LangGraph AI agents
│   ├── tools/               # Static analysis and git mining tools
│   └── models/              # Pydantic schemas
├── frontend/                # Next.js 14 frontend (Sprint 3)
└── docker-compose.yml       # PostgreSQL + Redis services
```

---

## Build/Lint/Test Commands

### Backend Development

```bash
# Navigate to backend
cd tech-debt-quantifier/backend

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the API server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run a single test file
pytest tests/test_specific_file.py -v

# Run a single test function
pytest tests/test_specific_file.py::test_function_name -v

# Run tests with coverage
pytest --cov=. --cov-report=html

# Format code (after installing black)
black .

# Lint code (after installing ruff)
ruff check .

# Type checking (after installing mypy)
mypy .
```

### Docker Commands

```bash
# Start PostgreSQL and Redis
docker-compose up -d

# Check container status
docker-compose ps

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v
```

---

## Code Style Guidelines

### Python Conventions

- **Python Version**: 3.11+
- **Type Hints**: Required on all function parameters and return types
- **Pydantic**: Use v2 syntax (`model_config` instead of `class Config`)
- **Docstrings**: Required on all public functions and classes
- **Line Length**: 88 characters (Black default)

### Import Organization

```python
# Standard library
import logging
import os
from pathlib import Path

# Third-party packages
from fastapi import FastAPI
from pydantic import BaseModel, Field

# Local application
from models.schemas import AnalyzeRequest
from tools.static_analysis import analyze_complexity
```

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Modules | snake_case | `static_analysis.py` |
| Classes | PascalCase | `DebtReport` |
| Functions | snake_case | `analyze_complexity()` |
| Variables | snake_case | `repo_path` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| Type Aliases | PascalCase | `DebtItems` |

### Error Handling

```python
def function_with_error_handling(repo_path: str) -> dict:
    """Description of function.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Dictionary with status and optional error
        
    Raises:
        ValueError: When repo_path is invalid
    """
    try:
        result = risky_operation()
        return {"status": "success", "data": result}
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logging.exception("Unexpected error occurred")
        raise
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

def process_something(data: str) -> None:
    """Process the given data."""
    logger.info(f"Starting processing with data length: {len(data)}")
    # ... processing ...
    logger.info("Processing complete")
```

### FastAPI Best Practices

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Tech Debt Quantifier",
    description="API for technical debt analysis",
    version="0.1.0",
)

class RequestModel(BaseModel):
    field: str = Field(..., description="Description of field")

@app.post("/endpoint")
async def endpoint_handler(request: RequestModel) -> dict:
    """Endpoint description."""
    if not validate_input(request.field):
        raise HTTPException(status_code=400, detail="Invalid input")
    return {"status": "success"}
```

### Environment Variables

```python
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/default")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
```

---

## Architecture Notes

### Agent System (LangGraph)

The orchestration uses LangGraph state machines:
- **Crawler Agent**: Clones repositories via MCP
- **Analyzer Agent**: Runs static analysis
- **Orchestrator**: Coordinates all agents via LangGraph

### MCP (Model Context Protocol)

MCP tools provide standardized tool access:
- `clone_repo(github_url, repo_id)`: Clone GitHub repository
- `list_cloned_repos()`: List cached repositories

### Static Analysis Tools

- **radon**: Cyclomatic complexity analysis
- **lizard**: Code complexity metrics
- **pydriller**: Git history mining
- **bandit**: Security vulnerability scanning
- **semgrep**: Pattern matching analysis

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| POST | `/analyze` | Queue repository analysis |
| GET | `/results/{job_id}` | Get analysis results |

---

## Environment Variables

Required in `backend/.env`:

```env
DATABASE_URL=postgresql://admin:password@localhost:5432/techdebt
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=your-openai-key-here
GITHUB_TOKEN=your-github-token-here
ENGINEER_HOURLY_RATE=85
```
