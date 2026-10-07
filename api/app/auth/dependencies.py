import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AuthSession, Tenant, User


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    tenant_id: UUID
    email: str
    tenant_name: str


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def require_csrf(request: Request, auth_session: AuthSession) -> None:
    cookie_token = request.cookies.get("dd_csrf", "")
    header_token = request.headers.get("x-csrf-token", "")
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
        or not secrets.compare_digest(
            token_digest(cookie_token), auth_session.csrf_token_hash
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


def get_auth_session(
    request: Request,
    db: Session = Depends(get_session),  # noqa: B008
) -> AuthSession:
    token = request.cookies.get("dd_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_digest(token))
    )
    now = datetime.now(UTC)
    if auth_session is None or auth_session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return auth_session


def get_current_user(
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> AuthenticatedUser:
    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    target_tenant_id = auth_session.active_tenant_id or user.tenant_id
    tenant = db.scalar(
        select(Tenant).where(
            Tenant.id == target_tenant_id,
            Tenant.deleted_at.is_(None),
        )
    )
    if tenant is None and target_tenant_id != user.tenant_id:
        tenant = db.scalar(
            select(Tenant).where(
                Tenant.id == user.tenant_id,
                Tenant.deleted_at.is_(None),
            )
        )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return AuthenticatedUser(
        id=user.id,
        tenant_id=tenant.id,
        email=user.email,
        tenant_name=tenant.name,
    )
