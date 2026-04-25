"""Authentication routes."""

from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from api.deps import JWT_ALG, JWT_SECRET, get_current_user
from database.connection import SessionLocal
from database.models import User

router = APIRouter(tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"


def _auth_settings() -> dict[str, str]:
    """Read GitHub OAuth settings from the current environment."""
    return {
        "client_id": os.getenv("GITHUB_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET", "").strip(),
        "callback_url": os.getenv("GITHUB_OAUTH_CALLBACK_URL", "").strip(),
        "frontend_origin": os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:3000").strip(),
    }


def _frontend_origin_from_request(request: Request | None = None) -> str:
    """Return the canonical frontend origin for auth redirects."""
    configured = _auth_settings()["frontend_origin"].rstrip("/")
    if configured:
        return configured

    if not request:
        return "http://127.0.0.1:3000"

    referer = request.headers.get("referer", "").strip()
    origin = request.headers.get("origin", "").strip()
    candidate = (referer or origin).rstrip("/")
    if candidate.startswith(("http://127.0.0.1:", "http://localhost:")):
        parts = candidate.split("/", 3)
        return parts[0] + "//" + parts[2]
    return "http://127.0.0.1:3000"


def _callback_url_from_request(request: Request | None = None) -> str:
    """Choose a callback URL that matches the active local development hostname."""
    configured = _auth_settings()["callback_url"].strip()
    if not request or not configured:
        return configured

    if "localhost" not in configured and "127.0.0.1" not in configured:
        return configured

    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/auth/github/callback"


def _build_oauth_state(frontend_origin: str) -> str:
    """Create a signed state token so callback redirects return to the right app."""
    payload = {
        "frontend_origin": frontend_origin.rstrip("/"),
        "nonce": secrets.token_urlsafe(16),
        "kind": "github_oauth_state",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_oauth_state(state: str | None) -> str | None:
    """Decode a signed OAuth state token and extract the frontend origin."""
    if not state:
        return None

    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        return None

    if payload.get("kind") != "github_oauth_state":
        return None

    frontend_origin = str(payload.get("frontend_origin") or "").rstrip("/")
    if frontend_origin.startswith(("http://127.0.0.1:", "http://localhost:")):
        return frontend_origin
    return None


@router.get("/auth/github/login")
async def github_login(request: Request) -> RedirectResponse:
    """Redirect to GitHub OAuth authorization page."""
    settings = _auth_settings()
    frontend_origin = _frontend_origin_from_request(request)
    callback_url = _callback_url_from_request(request)
    if not settings["client_id"] or not callback_url:
        raise HTTPException(500, "GitHub OAuth not configured")

    params = {
        "client_id": settings["client_id"],
        "redirect_uri": callback_url,
        "scope": "read:user user:email repo read:org",
        "allow_signup": "true",
        "state": _build_oauth_state(frontend_origin),
    }
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/auth/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle GitHub OAuth callback and redirect to the frontend."""
    frontend_origin = _decode_oauth_state(state) or _frontend_origin_from_request(request)
    if error:
        return RedirectResponse(f"{frontend_origin}/auth/callback?error={error}")
    if not code:
        return RedirectResponse(f"{frontend_origin}/auth/callback?error=missing_code")
    settings = _auth_settings()
    callback_url = _callback_url_from_request(request)
    if (
        not settings["client_id"]
        or not settings["client_secret"]
        or not callback_url
    ):
        return RedirectResponse(
            f"{frontend_origin}/auth/callback?error=github_oauth_not_configured"
        )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_resp = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings["client_id"],
                    "client_secret": settings["client_secret"],
                    "code": code,
                    "redirect_uri": callback_url,
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
        redirect_url = f"{frontend_origin}/auth/callback#token={jwt_token}"
        return RedirectResponse(redirect_url)
    except HTTPException as exc:
        return RedirectResponse(
            f"{frontend_origin}/auth/callback?error={str(exc.detail)}"
        )
    except Exception:
        return RedirectResponse(
            f"{frontend_origin}/auth/callback?error=github_auth_failed"
        )


def _serialize_user(user: User) -> dict[str, str | int | None]:
    """Return a stable user profile payload for frontend auth flows."""
    return {
        "id": user.id,
        "login": user.login,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "html_url": user.html_url,
    }


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict[str, str | int | None]:
    """Get current user info."""
    return _serialize_user(user)


@router.get("/auth/me")
async def get_auth_me(user: User = Depends(get_current_user)) -> dict[str, str | int | None]:
    """Alias for current user info used by the GitHub auth frontend flow."""
    return _serialize_user(user)
