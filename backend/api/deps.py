"""Shared API dependencies."""

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from database.connection import SessionLocal
from database.models import User

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")

auth_scheme = HTTPBearer(auto_error=False)


def get_jwt_payload(
    creds: HTTPAuthorizationCredentials = Depends(auth_scheme),
) -> dict:
    """Decode and return the JWT payload."""
    if not creds:
        raise HTTPException(401, "Not authenticated")

    token = creds.credentials
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Invalid token")


def get_current_user(
    payload: dict = Depends(get_jwt_payload),
) -> User:
    """Get current authenticated user from JWT token."""
    user_id = int(payload.get("sub"))

    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(401, "User not found")
        return user
    finally:
        db.close()


def get_github_access_token(payload: dict = Depends(get_jwt_payload)) -> str:
    """Return the GitHub access token stored in the signed JWT."""
    token = payload.get("gh_token")
    if not token:
        raise HTTPException(403, "GitHub account not connected")
    return str(token)
