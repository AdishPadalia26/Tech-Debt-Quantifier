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
    import subprocess
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
        
        logger.info(f"Cloning {github_url} to {repo_path} (depth=100)")
        git_url = github_url if github_url.startswith("http") else f"https://github.com/{github_url}"
        
        subprocess.run(
            ["git", "clone", "--depth", "100", git_url, str(repo_path)],
            check=True,
            capture_output=True,
        )
        
        return {
            "repo_id": repo_id,
            "path": str(repo_path),
            "status": "cloned",
            "error": None,
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone repository: {e}")
        return {
            "status": "error",
            "error": str(e),
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


@mcp.tool()
def run_static_analysis(repo_id: str) -> dict:
    """
    Run static analysis on a cloned repository.
    
    Args:
        repo_id: Unique identifier for the repository
    
    Returns:
        Dictionary with analysis summary including complexity metrics
    """
    repo_path = REPOS_DIR / repo_id
    
    if not repo_path.exists():
        return {
            "status": "error",
            "error": f"Repository {repo_id} not found at {repo_path}",
        }
    
    try:
        from tools.static_analysis import StaticAnalyzer
        
        logger.info(f"Running static analysis on {repo_id}")
        analyzer = StaticAnalyzer()
        summary = analyzer.get_summary(str(repo_path))
        
        return {
            "status": "success",
            "repo_id": repo_id,
            "analysis": summary,
        }
    except Exception as e:
        logger.error(f"Static analysis failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@mcp.tool()
def get_git_hotspots(repo_id: str) -> dict:
    """
    Analyze git history to find code hotspots.
    
    Args:
        repo_id: Unique identifier for the repository
    
    Returns:
        Dictionary with hotspot files sorted by change frequency
    """
    repo_path = REPOS_DIR / repo_id
    
    if not repo_path.exists():
        return {
            "status": "error",
            "error": f"Repository {repo_id} not found at {repo_path}",
        }
    
    try:
        from tools.git_mining import GitMiner
        
        logger.info(f"Analyzing git hotspots for {repo_id}")
        miner = GitMiner()
        hotspots = miner.get_hotspots(str(repo_path))
        
        return {
            "status": "success",
            "repo_id": repo_id,
            "hotspots": hotspots,
            "count": len(hotspots),
        }
    except Exception as e:
        logger.error(f"Git hotspot analysis failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@mcp.tool()
def estimate_debt_cost(repo_id: str) -> dict:
    """
    Estimate total technical debt cost for a repository.
    
    Args:
        repo_id: Unique identifier for the repository
    
    Returns:
        Dictionary with comprehensive cost estimate and breakdown
    """
    repo_path = REPOS_DIR / repo_id
    
    if not repo_path.exists():
        return {
            "status": "error",
            "error": f"Repository {repo_id} not found at {repo_path}",
        }
    
    try:
        from tools.cost_estimator import CostEstimator
        
        logger.info(f"Estimating debt cost for {repo_id}")
        estimator = CostEstimator()
        estimate = estimator.estimate_total_cost(str(repo_path))
        
        return {
            "status": "success",
            "repo_id": repo_id,
            "estimate": estimate,
        }
    except Exception as e:
        logger.error(f"Cost estimation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


if __name__ == "__main__":
    mcp.run()
