"""MCP (Model Context Protocol) Server for Tech Debt Quantifier."""

import base64
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("tech-debt-server")

REPOS_DIR = Path("/tmp/repos")


def _repo_storage_root() -> Path:
    """Return a writable repository cache location for the current platform."""
    configured = os.getenv("TDQ_REPO_CACHE_DIR")
    if configured:
        return Path(configured)

    workspace_cache = Path(__file__).resolve().parent / ".cache" / "tech-debt-repos"
    try:
        workspace_cache.mkdir(parents=True, exist_ok=True)
        return workspace_cache
    except OSError:
        pass

    tmp_root = os.getenv("TMPDIR") or os.getenv("TEMP") or os.getenv("TMP")
    if tmp_root:
        return Path(tmp_root) / "tech-debt-repos"
    return REPOS_DIR


REPOS_DIR = _repo_storage_root()
DEFAULT_CLONE_TIMEOUT_SECONDS = int(os.getenv("GIT_CLONE_TIMEOUT_SECONDS", "120"))


def _safe_repo_dirname(repo_id: str) -> str:
    """Convert logical repo ids like owner/repo into a filesystem-safe folder name."""
    return repo_id.replace("\\", "__").replace("/", "__").replace(":", "_")


def _has_working_tree_files(repo_path: Path) -> bool:
    """Return True when the repository has checked-out files beyond `.git`."""
    try:
        return any(child.name != ".git" for child in repo_path.iterdir())
    except OSError:
        return False


def _is_valid_cached_repo(repo_path: Path) -> bool:
    """Return True when a cached repository is a real git checkout for this path."""
    git_dir = repo_path / ".git"
    if not repo_path.exists() or not git_dir.exists():
        return False

    try:
        top_level = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
            timeout=10,
            capture_output=True,
            text=True,
        )
        if top_level.returncode != 0:
            return False

        resolved_repo_path = repo_path.resolve()
        resolved_top_level = Path(top_level.stdout.strip()).resolve()
        if resolved_repo_path != resolved_top_level:
            logger.warning(
                "Cached repo path %s resolves to git root %s; treating as invalid",
                resolved_repo_path,
                resolved_top_level,
            )
            return False

        inside = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
            timeout=10,
            capture_output=True,
            text=True,
        )
        if inside.returncode != 0 or inside.stdout.strip().lower() != "true":
            return False

        if not _has_working_tree_files(repo_path):
            logger.warning(
                "Cached repo at %s has no checked-out working tree files",
                repo_path,
            )
            return False
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Failed validating cached repo at %s: %s", repo_path, exc)
        return False


def _force_remove_repo_path(repo_path: Path) -> None:
    """Remove a repository path reliably on Windows, including hidden `.git` remnants."""
    if not repo_path.exists():
        return

    try:
        subprocess.run(
            [
                "cmd",
                "/c",
                f'attrib -h -s -r "{repo_path}\\*" /s /d',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass

    last_error: Exception | None = None
    for _ in range(3):
        try:
            shutil.rmtree(repo_path, ignore_errors=False)
            return
        except FileNotFoundError:
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)

    if repo_path.exists():
        raise OSError(f"Failed to remove stale repository path {repo_path}: {last_error}")


def _best_effort_remove_repo_path(repo_path: Path, context: str) -> None:
    """Try to remove a path, but only warn if Windows still has files locked."""
    try:
        _force_remove_repo_path(repo_path)
    except OSError as exc:
        logger.warning("Best-effort cleanup failed for %s at %s: %s", context, repo_path, exc)


def _run_clone_attempt(
    git_url: str,
    target_path: Path,
    timeout_seconds: int,
    extra_args: list[str] | None = None,
    git_config_args: list[str] | None = None,
) -> dict[str, Any]:
    """Run one git clone attempt and capture either the process result or timeout."""
    command = [
        "git",
        *(git_config_args or []),
        "clone",
        "--depth=1",
        "--single-branch",
        *(extra_args or []),
        git_url,
        str(target_path),
    ]
    started_at = time.time()

    try:
        result = subprocess.run(
            command,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )
        return {
            "ok": result.returncode == 0,
            "timed_out": False,
            "elapsed_seconds": time.time() - started_at,
            "stderr": (result.stderr or "").strip(),
            "stdout": (result.stdout or "").strip(),
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "timed_out": True,
            "elapsed_seconds": time.time() - started_at,
            "stderr": ((exc.stderr or "") if isinstance(exc.stderr, str) else "").strip(),
            "stdout": ((exc.stdout or "") if isinstance(exc.stdout, str) else "").strip(),
            "command": command,
        }


@mcp.tool()
def clone_repo(github_url: str, repo_id: str, access_token: str | None = None) -> dict:
    """
    Clone a GitHub repository to local storage.
    
    Args:
        github_url: The full GitHub repository URL
        repo_id: Unique identifier for the repository
        access_token: Optional GitHub OAuth token for private repository access
    
    Returns:
        Dictionary with clone status and path information
    """
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    repo_dirname = _safe_repo_dirname(repo_id)
    repo_path = REPOS_DIR / repo_dirname
    
    try:
        repo_path.parent.mkdir(parents=True, exist_ok=True)

        if repo_path.exists():
            if _is_valid_cached_repo(repo_path):
                logger.info("Repository already exists at %s", repo_path)
                return {
                    "repo_id": repo_id,
                    "path": str(repo_path),
                    "status": "already_exists",
                    "error": None,
                }

            logger.warning(
                "Removing invalid existing repository path before re-clone: %s",
                repo_path,
            )
            try:
                _force_remove_repo_path(repo_path)
            except OSError as exc:
                fallback_repo_path = REPOS_DIR / f"{repo_dirname}__fresh_{int(time.time())}"
                logger.warning(
                    "Could not remove stale repo path %s (%s); using fallback clone path %s",
                    repo_path,
                    exc,
                    fallback_repo_path,
                )
                repo_path = fallback_repo_path
        
        clone_timeout_seconds = int(
            os.getenv("GIT_CLONE_TIMEOUT_SECONDS", str(DEFAULT_CLONE_TIMEOUT_SECONDS))
        )
        retry_timeout_seconds = max(clone_timeout_seconds * 2, clone_timeout_seconds + 60)
        logger.info(
            "Cloning %s to %s with shallow clone (timeout=%ss)",
            github_url,
            repo_path,
            clone_timeout_seconds,
        )
        git_url = github_url if github_url.startswith("http") else f"https://github.com/{github_url}"
        git_config_args: list[str] = []
        if access_token:
            auth_value = base64.b64encode(
                f"x-access-token:{access_token}".encode("utf-8")
            ).decode("ascii")
            git_config_args = [
                "-c",
                f"http.extraheader=AUTHORIZATION: basic {auth_value}",
            ]

        attempt_specs = [
            {
                "timeout_seconds": clone_timeout_seconds,
                "extra_args": ["--filter=blob:none"],
                "label": "partial shallow clone",
            },
            {
                "timeout_seconds": retry_timeout_seconds,
                "extra_args": [],
                "label": "fallback shallow clone",
            },
        ]

        clone_result: dict[str, Any] | None = None
        last_error = "git clone failed"
        for attempt_index, attempt_spec in enumerate(attempt_specs, start=1):
            temp_repo_path = repo_path.with_name(
                f"{repo_path.name}__clone_tmp_{uuid.uuid4().hex[:8]}"
            )
            logger.info(
                "Clone attempt %s/%s for %s using %s (timeout=%ss)",
                attempt_index,
                len(attempt_specs),
                git_url,
                attempt_spec["label"],
                attempt_spec["timeout_seconds"],
            )
            clone_result = _run_clone_attempt(
                git_url=git_url,
                target_path=temp_repo_path,
                timeout_seconds=int(attempt_spec["timeout_seconds"]),
                extra_args=list(attempt_spec["extra_args"]),
                git_config_args=git_config_args,
            )
            if clone_result["ok"]:
                break

            last_error = (
                clone_result["stderr"]
                or clone_result["stdout"]
                or (
                    f"Git clone timed out after {attempt_spec['timeout_seconds']}s"
                    if clone_result["timed_out"]
                    else "git clone failed"
                )
            )
            if clone_result["timed_out"]:
                logger.warning(
                    "Clone attempt %s for %s timed out after %.1fs",
                    attempt_index,
                    git_url,
                    clone_result["elapsed_seconds"],
                )
            else:
                logger.error(
                    "Clone attempt %s for %s failed: %s",
                    attempt_index,
                    git_url,
                    last_error,
                )
            _best_effort_remove_repo_path(temp_repo_path, f"clone attempt {attempt_index}")

        if not clone_result or not clone_result["ok"]:
            return {
                "status": "error",
                "error": last_error,
            }

        if repo_path.exists():
            try:
                _force_remove_repo_path(repo_path)
            except OSError as exc:
                fallback_repo_path = REPOS_DIR / f"{repo_dirname}__fresh_{int(time.time())}"
                logger.warning(
                    "Could not replace existing repo path %s (%s); keeping fresh clone at %s",
                    repo_path,
                    exc,
                    fallback_repo_path,
                )
                repo_path = fallback_repo_path
        temp_repo_path.replace(repo_path)

        if not _is_valid_cached_repo(repo_path):
            logger.error(
                "Clone command completed but repository validation failed at %s",
                repo_path,
            )
            _best_effort_remove_repo_path(repo_path, "invalid repository clone")
            return {
                "status": "error",
                "error": "Repository clone completed without a valid working tree",
            }
        
        return {
            "repo_id": repo_id,
            "path": str(repo_path),
            "status": "cloned",
            "error": None,
        }
    except subprocess.TimeoutExpired:
        logger.error(
            "Git clone timed out after %ss: %s",
            DEFAULT_CLONE_TIMEOUT_SECONDS,
            github_url,
        )
        if "temp_repo_path" in locals():
            _best_effort_remove_repo_path(temp_repo_path, "timed out temporary clone")
        return {
            "status": "error",
            "error": f"Git clone timed out after {DEFAULT_CLONE_TIMEOUT_SECONDS}s",
        }
    except Exception as e:
        logger.error(f"Failed to clone repository: {e}")
        if "temp_repo_path" in locals():
            _best_effort_remove_repo_path(temp_repo_path, "exception temporary clone")
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
    repo_path = REPOS_DIR / _safe_repo_dirname(repo_id)
    
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
    repo_path = REPOS_DIR / _safe_repo_dirname(repo_id)
    
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
def estimate_debt_cost(repo_id: str, github_url: str = None) -> dict:
    """
    Estimate total technical debt cost for a repository.
    
    Uses the intelligence layer for dynamic data:
    - Repo profiling for tech stack detection
    - Market rate intelligence from multiple sources
    - Risk-weighted security costs
    
    Args:
        repo_id: Unique identifier for the repository
        github_url: Optional GitHub URL for additional context
    
    Returns:
        Dictionary with comprehensive cost estimate and breakdown
    """
    repo_path = REPOS_DIR / _safe_repo_dirname(repo_id)
    
    if not repo_path.exists():
        return {
            "status": "error",
            "error": f"Repository {repo_id} not found at {repo_path}",
        }
    
    try:
        from tools.cost_estimator import CostEstimator
        
        logger.info(f"Estimating debt cost for {repo_id}")
        estimator = CostEstimator()
        estimate = estimator.estimate_total_cost(str(repo_path), github_url)
        
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
