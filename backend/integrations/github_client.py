"""Lightweight GitHub API client for OAuth-backed repo import."""

from __future__ import annotations

from typing import Any

import httpx


class GitHubClient:
    """Thin wrapper over the GitHub REST API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, access_token: str) -> None:
        """Initialize the client with an OAuth token."""
        self.access_token = access_token

    @property
    def headers(self) -> dict[str, str]:
        """Return common GitHub API headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_user_repos(self) -> list[dict[str, Any]]:
        """Return repositories visible to the authenticated user."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.BASE_URL}/user/repos",
                headers=self.headers,
                params={
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "updated",
                    "per_page": 100,
                },
            )
            response.raise_for_status()
            return self._normalize_repos(response.json())

    async def get_orgs(self) -> list[dict[str, Any]]:
        """Return organizations available to the authenticated user."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.BASE_URL}/user/orgs",
                headers=self.headers,
                params={"per_page": 100},
            )
            response.raise_for_status()
            return [
                {
                    "login": org.get("login"),
                    "id": org.get("id"),
                    "avatar_url": org.get("avatar_url"),
                    "description": org.get("description"),
                }
                for org in response.json()
            ]

    async def get_org_repos(self, org: str) -> list[dict[str, Any]]:
        """Return repositories for a single organization."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.BASE_URL}/orgs/{org}/repos",
                headers=self.headers,
                params={"sort": "updated", "per_page": 100},
            )
            response.raise_for_status()
            return self._normalize_repos(response.json())

    def _normalize_repos(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a stable, frontend-friendly repository shape."""
        normalized = []
        for repo in repos:
            owner = repo.get("owner") or {}
            normalized.append(
                {
                    "id": repo.get("id"),
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "private": bool(repo.get("private")),
                    "html_url": repo.get("html_url"),
                    "clone_url": repo.get("clone_url"),
                    "default_branch": repo.get("default_branch"),
                    "description": repo.get("description"),
                    "language": repo.get("language"),
                    "updated_at": repo.get("updated_at"),
                    "owner": {
                        "login": owner.get("login"),
                        "avatar_url": owner.get("avatar_url"),
                    },
                }
            )
        return normalized
