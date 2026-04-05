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
    complexity: int | None = Field(
        default=None, ge=0, description="Cyclomatic complexity score"
    )
    remediation_hours: float = Field(..., ge=0, description="Estimated hours to fix")
    cost_usd: float = Field(..., ge=0, description="Estimated cost in USD")
    confidence: float | None = Field(
        default=None, ge=0, le=1, description="Confidence in the finding"
    )
    business_impact: str | None = Field(
        default=None, description="Likely business impact classification"
    )
    type: str | None = Field(default=None, description="Specific debt item type")


class FindingEvidence(BaseModel):
    """Evidence supporting a debt finding."""

    source: str = Field(..., description="Tool or stage that produced the evidence")
    summary: str = Field(..., description="Human-readable evidence summary")


class DebtFinding(BaseModel):
    """Extended finding model for structured product output."""

    id: str | None = Field(default=None, description="Optional finding identifier")
    file_path: str = Field(..., description="File path where debt was found")
    category: str = Field(..., description="Debt category")
    subcategory: str | None = Field(default=None, description="Optional debt subtype")
    severity: str = Field(..., description="Severity level")
    business_impact: str = Field(..., description="Business impact level")
    effort_hours: float = Field(..., ge=0, description="Estimated remediation effort")
    cost_usd: float = Field(..., ge=0, description="Estimated remediation cost")
    confidence: float = Field(..., ge=0, le=1, description="Finding confidence")
    evidence: list[FindingEvidence] = Field(
        default_factory=list, description="Evidence supporting the finding"
    )
    owner_count: int | None = Field(
        default=None, description="Number of contributors seen for the file"
    )
    top_contributor_share: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Share of file changes from the top contributor",
    )
    ownership_risk: str | None = Field(
        default=None, description="Ownership concentration risk classification"
    )


class FindingSuppressionRequest(BaseModel):
    """Request model for suppressing a finding."""

    reason: str = Field(..., min_length=3, description="Why this finding is suppressed")


class FindingFeedbackRequest(BaseModel):
    """Request model for attaching feedback to a finding."""

    feedback_type: str = Field(
        ...,
        description="Feedback classification such as true_positive, false_positive, accepted_risk",
    )
    severity_override: str | None = Field(
        default=None,
        description="Optional human override for finding severity",
    )
    notes: str | None = Field(default=None, description="Optional reviewer notes")


class DebtReport(BaseModel):
    """Complete technical debt report for a repository."""

    repo_id: str = Field(..., description="Repository identifier")
    total_cost_usd: float = Field(..., ge=0, description="Total estimated cost in USD")
    debt_score: float = Field(..., ge=0, description="Overall debt score (0-100)")
    items: list[DebtItem] = Field(default_factory=list, description="List of debt items found")
    findings: list[DebtFinding] = Field(
        default_factory=list, description="Structured findings for richer product flows"
    )


class GitHubOwnerSummary(BaseModel):
    """GitHub repository owner summary."""

    login: str = Field(..., description="Owner or organization login")
    avatar_url: str | None = Field(default=None, description="Owner avatar URL")


class GitHubRepoSummary(BaseModel):
    """Normalized GitHub repository info for import flows."""

    id: int = Field(..., description="GitHub repository id")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="owner/repo identifier")
    private: bool = Field(..., description="Whether the repository is private")
    html_url: str = Field(..., description="Repository web URL")
    clone_url: str = Field(..., description="Repository clone URL")
    default_branch: str | None = Field(default=None, description="Default branch")
    description: str | None = Field(default=None, description="Repository description")
    language: str | None = Field(default=None, description="Primary language")
    updated_at: str | None = Field(default=None, description="Last updated timestamp")
    owner: GitHubOwnerSummary = Field(..., description="Repository owner")


class GitHubOrgSummary(BaseModel):
    """GitHub organization info for repo import flows."""

    login: str = Field(..., description="Organization login")
    id: int = Field(..., description="Organization id")
    avatar_url: str | None = Field(default=None, description="Organization avatar")
    description: str | None = Field(default=None, description="Organization description")


class GitHubRepoImportRequest(BaseModel):
    """Request model for importing a GitHub repository into the workspace."""

    github_url: str = Field(..., description="GitHub URL for the repository")


class GitHubRepoImportResponse(BaseModel):
    """Response model for imported repositories."""

    repository_id: str = Field(..., description="Tracked repository id")
    github_url: str = Field(..., description="Normalized GitHub URL")
    repo_name: str = Field(..., description="Repository name")
    repo_owner: str = Field(..., description="Repository owner")
    imported: bool = Field(..., description="Whether the repository is now tracked")
