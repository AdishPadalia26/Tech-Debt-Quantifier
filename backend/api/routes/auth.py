"""Authentication routes."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import jwt

from api.deps import JWT_ALG, JWT_SECRET, get_current_user
from database.connection import SessionLocal
from database.models import User

router = APIRouter(tags=["auth"])

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_CALLBACK_URL = os.getenv("GITHUB_OAUTH_CALLBACK_URL", "")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"


@router.get("/auth/github/login")
async def github_login() -> RedirectResponse:
    """Redirect to GitHub OAuth authorization page."""
    if not GITHUB_CLIENT_ID or not GITHUB_OAUTH_CALLBACK_URL:
        raise HTTPException(500, "GitHub OAuth not configured")

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_OAUTH_CALLBACK_URL,
        "scope": "read:user user:email repo read:org",
        "allow_signup": "true",
    }
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/auth/github/callback")
async def github_callback(code: str | None = None) -> RedirectResponse:
    """Handle GitHub OAuth callback and redirect to the frontend."""
    if not code:
        raise HTTPException(400, "Missing code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_OAUTH_CALLBACK_URL,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, "Failed to get access token")

        user_resp = await client.get(
            GITHUB_API_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        user_resp.raise_for_status()
        gh = user_resp.json()

    db = SessionLocal()
    try:
        github_id = str(gh.get("id"))
        if not github_id:
            raise HTTPException(400, "Invalid GitHub user")

        user = db.query(User).filter(User.github_id == github_id).first()
        if not user:
            user = User(
                github_id=github_id,
                login=gh.get("login"),
                name=gh.get("name"),
                avatar_url=gh.get("avatar_url"),
                html_url=gh.get("html_url"),
                email=gh.get("email"),
            )
            db.add(user)
        else:
            user.login = gh.get("login")
            user.name = gh.get("name")
            user.avatar_url = gh.get("avatar_url")
            user.html_url = gh.get("html_url")
            user.email = gh.get("email")

        db.commit()
        db.refresh(user)
    finally:
        db.close()

    token_payload = {
        "sub": str(user.id),
        "login": user.login,
        "gh_token": access_token,
    }
    jwt_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALG)
    redirect_url = f"{FRONTEND_ORIGIN}/auth/callback#token={jwt_token}"
    return RedirectResponse(redirect_url)


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict[str, str | int | None]:
    """Get current user info."""
    return {
        "id": user.id,
        "login": user.login,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "html_url": user.html_url,
    }
