"""Shared API dependencies."""

import os
from typing import Any

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt

from database.connection import SessionLocal
from database.models import User

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")


def _extract_token(request: Request) -> str | None:
    """Cookie-first, Authorization-header fallback for API clients."""
    token = request.cookies.get("tdq_token")
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _decode(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        return None


def get_jwt_payload(request: Request) -> dict:
    """Decode and return the JWT payload."""
    payload = _decode(_extract_token(request))
    if payload is None:
        raise HTTPException(401, "Not authenticated")
    return payload


def get_jwt_payload_optional(request: Request) -> dict[str, Any] | None:
    """Decode and return the JWT payload when present, else allow anonymous access."""
    return _decode(_extract_token(request))


def get_current_user(
    payload: dict = Depends(get_jwt_payload),
) -> User:
    """Get current authenticated user from JWT token."""
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(401, "Invalid token: missing sub")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(401, "Invalid token: bad sub")

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(401, "User not found")
        return user
    finally:
        db.close()


def get_current_user_optional(
    payload: dict | None = Depends(get_jwt_payload_optional),
) -> User | None:
    """Return the authenticated user when present, else allow anonymous access."""
    if not payload:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None

    db = SessionLocal()
    try:
        return db.get(User, uid)
    finally:
        db.close()


def get_github_access_token(payload: dict = Depends(get_jwt_payload)) -> str:
    """Return the GitHub access token stored in the signed JWT."""
    token = payload.get("gh_token")
    if not token:
        raise HTTPException(403, "GitHub account not connected")
    return str(token)


def get_github_access_token_optional(
    payload: dict[str, Any] | None = Depends(get_jwt_payload_optional),
) -> str | None:
    """Return the GitHub access token when the caller is authenticated."""
    if not payload:
        return None

    token = payload.get("gh_token")
    return str(token) if token else None
