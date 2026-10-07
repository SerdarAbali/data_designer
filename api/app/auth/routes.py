import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
    token_digest,
)
from app.auth.rate_limit import login_rate_limiter
from app.auth.schemas import LoginRequest, UserResponse
from app.auth.security import hash_password, verify_password
from app.config import settings
from app.db import get_session
from app.models import AuthSession, User

router = APIRouter(prefix="/api/auth", tags=["authentication"])
dummy_password_hash = hash_password("invalid-login-placeholder")


def set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    max_age = settings.session_ttl_hours * 60 * 60
    response.set_cookie(
        "dd_session",
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "dd_csrf",
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        "dd_session",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        "dd_csrf",
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.get("/csrf")
def issue_login_csrf(response: Response) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.set_cookie(
        "dd_csrf",
        token,
        max_age=600,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"csrf_token": token}


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),  # noqa: B008
) -> dict[str, str]:
    csrf_cookie = request.cookies.get("dd_csrf", "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")

    client_host = request.client.host if request.client else "unknown"
    retry_after = login_rate_limiter.consume(client_host)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.email == payload.email))
    password_hash = user.password_hash if user is not None else dummy_password_hash
    password_valid = verify_password(password_hash, payload.password)
    if user is None or not user.is_active or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(session_token),
        csrf_token_hash=token_digest(csrf_token),
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(auth_session)
    db.commit()
    set_auth_cookies(response, session_token, csrf_token)
    login_rate_limiter.clear(client_host)
    return {"status": "authenticated"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    auth_session.revoked_at = datetime.now(UTC)
    db.commit()
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
def current_user(
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        tenant_name=user.tenant_name,
    )
