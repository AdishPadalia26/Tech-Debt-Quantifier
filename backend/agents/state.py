"""Shared state for LangGraph agents in Tech Debt Quantifier."""

from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """Shared state that flows between all agents in the pipeline."""

    github_url: str
    repo_id: str

    repo_path: Optional[str]
    clone_status: Optional[str]

    raw_analysis: Optional[dict]
    repo_profile: Optional[dict]
    findings: Optional[list]
    module_summaries: Optional[list]
    roadmap: Optional[dict]

    executive_summary: Optional[str]
    priority_actions: Optional[list]
    roi_analysis: Optional[dict]

    job_id: str
    status: str
    error: Optional[str]
    messages: Annotated[list, add_messages]
