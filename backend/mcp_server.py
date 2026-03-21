"""MCP (Model Context Protocol) Server for Tech Debt Quantifier."""

import logging
import os
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("tech-debt-server")

REPOS_DIR = Path("/tmp/repos")


@mcp.tool()
def clone_repo(github_url: str, repo_id: str) -> dict:
    """
    Clone a GitHub repository to local storage.
    
    Args:
        github_url: The full GitHub repository URL
        repo_id: Unique identifier for the repository
    
    Returns:
        Dictionary with clone status and path information
    """
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    repo_path = REPOS_DIR / repo_id
    
    try:
        if repo_path.exists():
            logger.info(f"Repository already exists at {repo_path}")
            return {
                "repo_id": repo_id,
                "path": str(repo_path),
                "status": "already_exists",
                "error": None,
            }
        
        logger.info(f"Cloning {github_url} to {repo_path}")
        git_url = github_url if github_url.startswith("http") else f"https://github.com/{github_url}"
        shutil.copytree(git_url, repo_path)
        
        return {
            "repo_id": repo_id,
            "path": str(repo_path),
            "status": "cloned",
            "error": None,
        }
    except Exception as e:
        logger.error(f"Failed to clone repository: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@mcp.tool()
def list_cloned_repos() -> dict:
    """
    List all cloned repositories in local storage.
    
    Returns:
        Dictionary containing list of cloned repository IDs
    """
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    
    repos = [d.name for d in REPOS_DIR.iterdir() if d.is_dir()]
    
    logger.info(f"Found {len(repos)} cloned repositories")
    
    return {
        "repos": repos,
        "count": len(repos),
    }


if __name__ == "__main__":
    mcp.run()
