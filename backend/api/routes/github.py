"""GitHub import routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from api.deps import get_current_user, get_github_access_token
from database.connection import DB_AVAILABLE, SessionLocal
from database.crud import get_or_create_repository
from database.models import User
from integrations.github_client import GitHubClient
from models.schemas import GitHubRepoImportRequest

router = APIRouter(tags=["github"])


@router.get("/github/repos")
async def get_github_repos(
    user: User = Depends(get_current_user),
    access_token: str = Depends(get_github_access_token),
):
    """List repositories visible to the authenticated GitHub user."""
    client = GitHubClient(access_token)
    try:
        repos = await client.get_user_repos()
    except HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Failed to load GitHub repositories")
    return {"repositories": repos, "total": len(repos)}


@router.get("/github/orgs")
async def get_github_orgs(
    user: User = Depends(get_current_user),
    access_token: str = Depends(get_github_access_token),
):
    """List organizations visible to the authenticated GitHub user."""
    client = GitHubClient(access_token)
    try:
        orgs = await client.get_orgs()
    except HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Failed to load GitHub organizations")
    return {"organizations": orgs, "total": len(orgs)}


@router.get("/github/orgs/{org}/repos")
async def get_github_org_repos(
    org: str,
    user: User = Depends(get_current_user),
    access_token: str = Depends(get_github_access_token),
):
    """List repositories for a selected GitHub organization."""
    client = GitHubClient(access_token)
    try:
        repos = await client.get_org_repos(org)
    except HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Failed to load organization repositories")
    return {"organization": org, "repositories": repos, "total": len(repos)}


@router.post("/github/import")
async def import_github_repo(
    request: GitHubRepoImportRequest,
    user: User = Depends(get_current_user),
):
    """Import a GitHub repository into tracked repositories."""
    if not DB_AVAILABLE:
        raise HTTPException(503, "Database not available.")

    db = SessionLocal()
    try:
        repo = get_or_create_repository(db, request.github_url, user_id=user.id)
        return {
            "repository_id": repo.id,
            "github_url": repo.github_url,
            "repo_name": repo.repo_name,
            "repo_owner": repo.repo_owner,
            "imported": True,
        }
    finally:
        db.close()
