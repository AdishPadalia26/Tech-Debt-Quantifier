"""Pydantic models for Tech Debt Quantifier API."""

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request model for repository analysis."""

    github_url: str = Field(..., description="GitHub repository URL to analyze")
    repo_id: str = Field(..., description="Unique identifier for the repository")


class AnalyzeResponse(BaseModel):
    """Response model for analysis submission."""

    job_id: str = Field(..., description="Unique job identifier for tracking")
    status: str = Field(..., description="Current status of the analysis job")
    message: str = Field(..., description="Human-readable status message")


class DebtItem(BaseModel):
    """Model representing a single technical debt item."""

    file: str = Field(..., description="File path where debt was found")
    category: str = Field(..., description="Category of technical debt")
    severity: str = Field(..., description="Severity level: low, medium, high, critical")
    complexity: int = Field(..., ge=0, description="Cyclomatic complexity score")
    remediation_hours: float = Field(..., ge=0, description="Estimated hours to fix")
    cost_usd: float = Field(..., ge=0, description="Estimated cost in USD")


class DebtReport(BaseModel):
    """Complete technical debt report for a repository."""

    repo_id: str = Field(..., description="Repository identifier")
    total_cost_usd: float = Field(..., ge=0, description="Total estimated cost in USD")
    debt_score: float = Field(..., ge=0, description="Overall debt score (0-100)")
    items: list[DebtItem] = Field(default_factory=list, description="List of debt items found")
