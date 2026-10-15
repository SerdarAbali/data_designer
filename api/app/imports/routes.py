"""Guided architecture import endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.imports.schemas import (
    ImportBatchResponse,
    ImportCommitRequest,
    ImportPreviewRequest,
    ImportPreviewResponse,
)
from app.imports.service import (
    batch_response,
    commit_import,
    preview_import,
    undo_import_batch,
)
from app.models import AuthSession, ImportBatch, Workspace

router = APIRouter(prefix="/api/workspaces/{workspace_id}/imports", tags=["imports"])

DISCIPLINE_BY_IMPORT_TYPE = {
    "information_object": "information",
    "solution": "solution",
}
DISCIPLINE_LABELS = {
    "information_object": "Information Architecture",
    "solution": "Solution Architecture",
}


def _require_discipline(workspace: Workspace, import_type: str) -> None:
    required = DISCIPLINE_BY_IMPORT_TYPE.get(import_type)
    if required and required not in (workspace.disciplines or []):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{DISCIPLINE_LABELS[import_type]} is not enabled for this workspace. "
                "Enable it in Workspace Settings before importing."
            ),
        )


def _batch_or_404(db: Session, workspace: Workspace, batch_id: UUID) -> ImportBatch:
    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.tenant_id == workspace.tenant_id,
            ImportBatch.workspace_id == workspace.id,
        )
    )
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch not found")
    return batch


@router.post("/preview", response_model=ImportPreviewResponse)
def preview_import_endpoint(
    workspace_id: UUID,
    payload: ImportPreviewRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ImportPreviewResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_discipline(workspace, payload.import_type)
    return preview_import(db, workspace, payload)


@router.post(
    "/commit", response_model=ImportBatchResponse, status_code=status.HTTP_201_CREATED
)
def commit_import_endpoint(
    workspace_id: UUID,
    payload: ImportCommitRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_discipline(workspace, payload.import_type)
    batch = commit_import(db, workspace, payload)
    return batch_response(db, batch)


@router.get("", response_model=list[ImportBatchResponse])
def list_import_batches(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[dict]:
    workspace = get_accessible_workspace(db, user, workspace_id)
    batches = db.scalars(
        select(ImportBatch)
        .where(
            ImportBatch.tenant_id == workspace.tenant_id,
            ImportBatch.workspace_id == workspace.id,
        )
        .order_by(ImportBatch.imported_at.desc())
        .limit(50)
    )
    return [batch_response(db, batch, include_rows=False) for batch in batches]


@router.get("/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(
    workspace_id: UUID,
    batch_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict:
    workspace = get_accessible_workspace(db, user, workspace_id)
    return batch_response(db, _batch_or_404(db, workspace, batch_id))


@router.post("/{batch_id}/undo", response_model=ImportBatchResponse)
def undo_import_batch_endpoint(
    workspace_id: UUID,
    batch_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _batch_or_404(db, workspace, batch_id)
    batch, _removed = undo_import_batch(db, workspace, batch_id)
    return batch_response(db, batch)
