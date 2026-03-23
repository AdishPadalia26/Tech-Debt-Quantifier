"""Crawler agent for Tech Debt Quantifier."""

from agents.state import AgentState


class CrawlerAgent:
    """Agent that clones a GitHub repo using the MCP clone_repo tool."""

    async def run(self, state: AgentState) -> AgentState:
        """Clone the repo and update state."""
        from mcp_server import clone_repo

        github_url = state["github_url"]
        repo_id = state["repo_id"]

        result = clone_repo(github_url, repo_id)

        if result["status"] in ["cloned", "already_exists"]:
            state["repo_path"] = result["path"]
            state["clone_status"] = "success"
            state["status"] = "cloning_complete"
        else:
            state["clone_status"] = "failed"
            state["error"] = result.get("error", "Unknown clone error")
            state["status"] = "failed"

        return state
