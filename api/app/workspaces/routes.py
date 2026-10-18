from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.architecture.state_scope import BASELINE_DRAFT, BASELINE_LOCKED
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.demo import PRESETS, generate_demo, reset_demo
from app.models import (
    ArchitectureState,
    AuthSession,
    Tenant,
    User,
    Workspace,
)
from app.workspaces.bundle import (
    BundleError,
    export_workspace_bundle,
    fork_workspace,
    import_workspace_bundle,
    validate_bundle,
)
from app.workspaces.schemas import (
    WorkspaceCreate,
    WorkspaceFork,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.workspaces.service import (
    get_workspace_counts,
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


def _ensure_workspace_entity(
    db: Session,
    tenant: Tenant,
    disciplines: list[str] | None = None,
) -> Workspace:
    ws = db.scalar(
        select(Workspace).where(
            Workspace.id == tenant.id,
            Workspace.deleted_at.is_(None),
        )
    )
    if ws is None:
        ws = Workspace(
            id=tenant.id,
            tenant_id=tenant.id,
            name=tenant.name,
            description=tenant.description,
            disciplines=(
                disciplines
                if disciplines is not None
                else ["enterprise", "information", "solution", "integration"]
            ),
        )
        db.add(ws)
        db.flush()
    elif disciplines is not None:
        ws.disciplines = disciplines
        db.flush()
    return ws


def _workspace_response(
    db: Session, tenant: Tenant, ws: Workspace, *, is_active: bool
) -> WorkspaceResponse:
    s_count, c_count, sc_count = get_workspace_counts(db, tenant.id)
    return WorkspaceResponse(
        id=tenant.id,
        name=tenant.name,
        description=tenant.description,
        disciplines=ws.disciplines,
        created_at=tenant.created_at,
        is_active=is_active,
        systems_count=s_count,
        contracts_count=c_count,
        scenarios_count=sc_count,
        demo_preset=ws.demo_preset,
        demo_version=ws.demo_version,
        demo_generated_at=ws.demo_generated_at,
    )


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
        ws = _ensure_workspace_entity(db, t)
        results.append(_workspace_response(db, t, ws, is_active=(t.id == user.tenant_id)))
    db.commit()
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

    disciplines = payload.disciplines
    if payload.demo_preset is not None:
        disciplines = list(PRESETS[payload.demo_preset])
    new_ws = _ensure_workspace_entity(db, new_tenant, disciplines=disciplines)

    if payload.seed_demo_data:
        seed_demo_data_for_tenant(db, new_tenant.id)
    if payload.demo_preset is not None:
        generate_demo(db, new_ws, payload.demo_preset)
        # A demo provides Current *content*, so its Current state is a captured
        # baseline and keeps the historical read-only protection. The baseline
        # choice applies to workspaces that start empty.
        _lock_provided_baseline(db, new_ws)
    elif payload.baseline == "candidate_starter":
        _create_candidate_starter(db, new_ws)
    # ``current_draft`` needs nothing here: Current is materialised on first read
    # by the existing initializer, which also captures the Catalog systems that
    # exist by then. It starts as a draft, so it opens editable.

    # Switch session to new workspace
    auth_session.active_tenant_id = new_tenant.id
    db.commit()
    db.refresh(new_tenant)
    db.refresh(new_ws)

    return _workspace_response(db, new_tenant, new_ws, is_active=True)


def _create_candidate_starter(db: Session, workspace: Workspace) -> None:
    """The Candidate-starter option: an editable Current draft plus a Candidate.

    Both states are created eagerly so the workspace opens with somewhere to
    design *and* somewhere to capture. Current is a draft, exactly like the
    Current-baseline option: it becomes read-only only when a human locks it, so
    a new manual workspace never starts with an empty locked baseline.
    """
    from app.architecture.routes import auto_initialize_current_state

    auto_initialize_current_state(db, workspace, baseline_status=BASELINE_DRAFT)
    now = datetime.now(UTC)
    db.add(
        ArchitectureState(
            workspace_id=workspace.id,
            name="Candidate Design",
            state_type="candidate",
            description="Editable Candidate design.",
            nodes=[],
            relationships=[],
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _lock_provided_baseline(db: Session, workspace: Workspace) -> None:
    """Mark a generated Current (demo content) as a captured, locked baseline."""
    current = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.state_type == "current",
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if current is None:
        return
    if current.baseline_status is None:
        current.baseline_status = BASELINE_LOCKED
    db.commit()


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceResponse:
    require_csrf(request, auth_session)
    tenant = _user_can_access_workspace(db, user, workspace_id)
    ws = _ensure_workspace_entity(db, tenant)

    if payload.name is not None and payload.name.strip():
        new_name = payload.name.strip()
        if new_name != ws.name:
            existing = db.scalar(
                select(Tenant).where(
                    Tenant.name == new_name,
                    Tenant.id != tenant.id,
                    Tenant.deleted_at.is_(None),
                )
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A workspace named '{new_name}' already exists",
                )
            tenant.name = new_name
            ws.name = new_name

    if payload.description is not None:
        tenant.description = payload.description.strip() if payload.description else None
        ws.description = tenant.description

    if payload.disciplines is not None:
        ws.disciplines = payload.disciplines

    ws.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(ws)
    db.refresh(tenant)

    return _workspace_response(db, tenant, ws, is_active=(tenant.id == user.tenant_id))


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
    ws = _ensure_workspace_entity(db, tenant)
    auth_session.active_tenant_id = tenant.id
    db.commit()

    return _workspace_response(db, tenant, ws, is_active=True)


@router.post("/{workspace_id}/demo/reset", response_model=WorkspaceResponse)
def reset_demo_endpoint(
    workspace_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceResponse:
    require_csrf(request, auth_session)
    tenant = _user_can_access_workspace(db, user, workspace_id)
    ws = _ensure_workspace_entity(db, tenant)
    if not ws.demo_preset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This workspace is not a demo workspace",
        )
    try:
        reset_demo(db, ws)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    db.commit()
    db.refresh(ws)
    return _workspace_response(db, tenant, ws, is_active=(tenant.id == user.tenant_id))


@router.post(
    "/{workspace_id}/fork",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
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
        description=(
            payload.description.strip()
            if payload.description
            else f"Fork of {source_tenant.name}"
        ),
        owner_id=user.id,
    )
    db.add(new_tenant)
    db.flush()

    # The source workspace is never written to: its disciplines travel in the
    # serialised bundle unless the caller overrides them.
    try:
        fork_ws = fork_workspace(
            db,
            source_tenant.id,
            new_tenant,
            disciplines=list(payload.disciplines) if payload.disciplines is not None else None,
            actor_user_id=user.id,
        )
    except BundleError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.as_detail(),
        ) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "fork_conflict",
                "message": "The source workspace could not be copied cleanly",
            },
        ) from error
    except Exception:
        db.rollback()
        raise

    # Switch session to new fork
    auth_session.active_tenant_id = new_tenant.id
    db.commit()
    db.refresh(new_tenant)
    db.refresh(fork_ws)

    return _workspace_response(db, new_tenant, fork_ws, is_active=True)


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

    # Validate the whole bundle before anything is written so a rejection is
    # actionable and leaves no partial workspace behind.
    problems = validate_bundle(payload)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_bundle",
                "message": problems[0]["message"],
                "problems": problems[:20],
                "problem_count": len(problems),
            },
        )

    ws_info = payload.get("workspace", {}) or {}
    base_name = (ws_info.get("name") or "Imported Workspace").strip() or "Imported Workspace"
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

    try:
        imported_ws = import_workspace_bundle(db, new_tenant, payload, actor_user_id=user.id)
    except BundleError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.as_detail(),
        ) from error
    except IntegrityError as error:
        # A last-resort guard: anything the validator could not see (a database
        # constraint) still rolls the whole import back and stays actionable.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "import_conflict",
                "message": "The bundle conflicts with an existing record",
            },
        ) from error
    except Exception:
        db.rollback()
        raise

    auth_session.active_tenant_id = new_tenant.id
    db.commit()
    db.refresh(new_tenant)
    db.refresh(imported_ws)

    return _workspace_response(db, new_tenant, imported_ws, is_active=True)


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

