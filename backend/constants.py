"""Constants for Tech Debt Quantifier.

This file is the single source of truth for ALL magic numbers.
Never hardcode numbers elsewhere — always import from here.
"""

from typing import Final

COMPLEXITY_THRESHOLDS: Final[dict[str, tuple[int, int]]] = {
    "low": (1, 5),
    "medium": (6, 10),
    "high": (11, 15),
    "critical": (16, 9999),
}

CHURN_MULTIPLIERS: Final[list[tuple[int, float]]] = [
    (0, 1.0),
    (3, 1.3),
    (6, 1.7),
    (11, 2.2),
    (20, 3.0),
]

HOURLY_RATES: Final[dict[str, float]] = {
    "junior": 55.10,
    "mid": 84.55,
    "senior": 128.37,
}

DEBT_TYPE_TO_ROLE: Final[dict[str, str]] = {
    "architecture": "senior",
    "security": "senior",
    "code_quality": "mid",
    "dependency": "mid",
    "test_debt": "junior",
    "documentation": "junior",
}

CISQ_COST_PER_FUNCTION: Final[float] = 550.0

SONAR_SEVERITY_MINUTES: Final[dict[str, int]] = {
    "BLOCKER": 120,
    "CRITICAL": 60,
    "MAJOR": 30,
    "MINOR": 10,
    "INFO": 5,
}

SKIP_DIRS: Final[set[str]] = {
    "venv",
    "node_modules",
    ".git",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "__generated__",
    "vendor",
    ".tox",
    "eggs",
    ".eggs",
    ".venv",
    "env",
    ".env",
}

SKIP_FILE_PATTERNS: Final[list[str]] = [
    "*.min.js",
    "*.bundle.js",
    "*_pb2.py",
    "*.lock",
    "*.sum",
    "*.map",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
]

MAX_WORKERS: Final[int] = 4

API_TIMEOUT_SECONDS: Final[int] = 10

CACHE_STALE_HOURS: Final[int] = 24

SONAR_CACHE_STALE_DAYS: Final[int] = 7

VULNERABILITY_REMEDIATION_HOURS: Final[dict[str, float]] = {
    "CRITICAL": 12.0,
    "HIGH": 6.0,
    "MEDIUM": 3.0,
    "LOW": 1.0,
    "UNKNOWN": 2.0,
}

BANDIT_REMEDIATION_HOURS: Final[dict[str, float]] = {
    "HIGH": 8.0,
    "MEDIUM": 4.0,
    "LOW": 1.0,
}

COMPLEXITY_TO_SONAR_SEVERITY: Final[dict[str, str]] = {
    "low": "MINOR",
    "medium": "MAJOR",
    "high": "CRITICAL",
    "critical": "BLOCKER",
}

HOURS_PER_SPRINT: Final[float] = 80.0

DEBT_SCORE_MAX: Final[float] = 10.0

SANITY_CHECK_VARIANCE_THRESHOLD: Final[float] = 60.0

COMPLEXITY_REMEDIATION_MINUTES: Final[dict[str, float]] = {
    "low": 15.0,
    "medium": 45.0,
    "high": 90.0,
    "critical": 180.0,
}

FUNCTION_BASELINE_MINUTES: Final[float] = 10.0

MAINTENANCE_OVERHEAD_MULTIPLIER: Final[float] = 10.0
