"""Application-owned assistant routes.

Slice B exposes exactly one route: a narrow, authenticated runtime status. There
is deliberately no generic OpenCode proxy here, and no route accepts an OpenCode
path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.assistant.probe import AssistantRuntimeStatus, get_assistant_status
from app.auth.dependencies import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/status")
def assistant_status(
    _user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    status: AssistantRuntimeStatus = Depends(get_assistant_status),  # noqa: B008
) -> dict[str, Any]:
    """Safe, redacted runtime status.

    Never returns the OpenCode password, authorization headers, provider keys,
    environment details, raw upstream payloads, or stack traces.
    """
    return status.public_snapshot()
