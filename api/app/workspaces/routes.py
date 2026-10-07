from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.models import AuthSession, Tenant, User
from app.workspaces.schemas import (
    WorkspaceCreate,
    WorkspaceFork,
    WorkspaceResponse,
)
from app.workspaces.service import (
    export_workspace_bundle,
    fork_workspace,
    get_workspace_counts,
    import_workspace_bundle,
    seed_demo_data_for_tenant,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _user_can_access_workspace(db: Session, user: AuthenticatedUser, tenant_id: UUID) -> Tenant:
    tenant = db.scalar(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None),
            or_(
                Tenant.owner_id == user.id,
                Tenant.id == user.tenant_id,
            ),
        )
    )
    if tenant is None:
        # Check if user's root tenant
        db_user = db.get(User, user.id)
        if db_user and db_user.tenant_id == tenant_id:
            tenant = db.scalar(
                select(Tenant).where(
                    Tenant.id == tenant_id,
                    Tenant.deleted_at.is_(None),
                )
            )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    return tenant


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[WorkspaceResponse]:
    db_user = db.get(User, user.id)
    root_tenant_id = db_user.tenant_id if db_user else user.tenant_id

    tenants = list(
        db.scalars(
            select(Tenant).where(
                Tenant.deleted_at.is_(None),
                or_(
                    Tenant.owner_id == user.id,
                    Tenant.id == root_tenant_id,
                ),
            ).order_by(Tenant.created_at.asc())
        )
    )

    results: list[WorkspaceResponse] = []
    for t in tenants:
        s_count, c_count, sc_count = get_workspace_counts(db, t.id)
        results.append(
            WorkspaceResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                created_at=t.created_at,
                is_active=(t.id == user.tenant_id),
                systems_count=s_count,
                contracts_count=c_count,
                scenarios_count=sc_count,
            )
        )
    return results


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceResponse:
    require_csrf(request, auth_session)

    # Check unique name for active tenants
    existing = db.scalar(
        select(Tenant).where(
            Tenant.name == payload.name.strip(),
            Tenant.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A workspace named '{payload.name}' already exists",
        )

    new_tenant = Tenant(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        owner_id=user.id,
    )
    db.add(new_tenant)
    db.flush()

    if payload.seed_demo_data:
        seed_demo_data_for_tenant(db, new_tenant.id)

    # Switch session to new workspace
    auth_session.active_tenant_id = new_tenant.id
    db.commit()
    db.refresh(new_tenant)

    s_count, c_count, sc_count = get_workspace_counts(db, new_tenant.id)
    return WorkspaceResponse(
        id=new_tenant.id,
        name=new_tenant.name,
        description=new_tenant.description,
        created_at=new_tenant.created_at,
        is_active=True,
        systems_count=s_count,
        contracts_count=c_count,
        scenarios_count=sc_count,
    )


@router.post("/{workspace_id}/switch", response_model=WorkspaceResponse)
def switch_workspace(
    workspace_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceResponse:
    require_csrf(request, auth_session)
    tenant = _user_can_access_workspace(db, user, workspace_id)
    auth_session.active_tenant_id = tenant.id
    db.commit()

    s_count, c_count, sc_count = get_workspace_counts(db, tenant.id)
    return WorkspaceResponse(
        id=tenant.id,
        name=tenant.name,
        description=tenant.description,
        created_at=tenant.created_at,
        is_active=True,
        systems_count=s_count,
        contracts_count=c_count,
        scenarios_count=sc_count,
    )


@router.post("/{workspace_id}/fork", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def fork_workspace_endpoint(
    workspace_id: UUID,
    payload: WorkspaceFork,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceResponse:
    require_csrf(request, auth_session)
    source_tenant = _user_can_access_workspace(db, user, workspace_id)

    fork_name = payload.name.strip()
    existing = db.scalar(
        select(Tenant).where(
            Tenant.name == fork_name,
            Tenant.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A workspace named '{fork_name}' already exists",
        )

    new_tenant = Tenant(
        name=fork_name,
        description=payload.description.strip() if payload.description else f"Fork of {source_tenant.name}",
        owner_id=user.id,
    )
    db.add(new_tenant)
    db.flush()

    fork_workspace(db, source_tenant.id, new_tenant)

    # Switch session to new fork
    auth_session.active_tenant_id = new_tenant.id
    db.commit()
    db.refresh(new_tenant)

    s_count, c_count, sc_count = get_workspace_counts(db, new_tenant.id)
    return WorkspaceResponse(
        id=new_tenant.id,
        name=new_tenant.name,
        description=new_tenant.description,
        created_at=new_tenant.created_at,
        is_active=True,
        systems_count=s_count,
        contracts_count=c_count,
        scenarios_count=sc_count,
    )


@router.get("/{workspace_id}/export")
def export_workspace_endpoint(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict:
    tenant = _user_can_access_workspace(db, user, workspace_id)
    return export_workspace_bundle(db, tenant.id)


@router.post("/import", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def import_workspace_endpoint(
    payload: dict,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceResponse:
    require_csrf(request, auth_session)
    if payload.get("format") != "data-designer-workspace":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workspace format (expected 'data-designer-workspace')",
        )

    ws_info = payload.get("workspace", {})
    base_name = ws_info.get("name", "Imported Workspace").strip()
    import_name = base_name
    counter = 1
    while db.scalar(select(Tenant).where(Tenant.name == import_name, Tenant.deleted_at.is_(None))):
        counter += 1
        import_name = f"{base_name} ({counter})"

    new_tenant = Tenant(
        name=import_name,
        description=ws_info.get("description"),
        owner_id=user.id,
    )
    db.add(new_tenant)
    db.flush()

    import_workspace_bundle(db, new_tenant, payload)

    auth_session.active_tenant_id = new_tenant.id
    db.commit()
    db.refresh(new_tenant)

    s_count, c_count, sc_count = get_workspace_counts(db, new_tenant.id)
    return WorkspaceResponse(
        id=new_tenant.id,
        name=new_tenant.name,
        description=new_tenant.description,
        created_at=new_tenant.created_at,
        is_active=True,
        systems_count=s_count,
        contracts_count=c_count,
        scenarios_count=sc_count,
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    tenant = _user_can_access_workspace(db, user, workspace_id)

    db_user = db.get(User, user.id)
    root_tenant_id = db_user.tenant_id if db_user else user.tenant_id

    # Count other active workspaces
    other_workspaces = list(
        db.scalars(
            select(Tenant).where(
                Tenant.id != workspace_id,
                Tenant.deleted_at.is_(None),
                or_(
                    Tenant.owner_id == user.id,
                    Tenant.id == root_tenant_id,
                ),
            )
        )
    )
    if not other_workspaces:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your only workspace",
        )

    tenant.deleted_at = datetime.now(UTC)

    # If active, switch to first other workspace
    if auth_session.active_tenant_id == workspace_id or user.tenant_id == workspace_id:
        auth_session.active_tenant_id = other_workspaces[0].id

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

