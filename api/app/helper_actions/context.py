"""Shared helper context: authenticated user, accessible workspace, and scope checks.

Every helper action resolves (and validates) its tenant, workspace, enabled
disciplines, architecture state, and canonical references here. Cross-workspace
and cross-tenant references are rejected, and proposal targets may never be the
read-only Current state.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.auth.dependencies import AuthenticatedUser
from app.models import (
    ArchitectureObject,
    ArchitectureState,
    CatalogField,
    CatalogSystem,
    Integration,
    Workspace,
)


@dataclass
class HelperContext:
    db: Session
    user: AuthenticatedUser
    workspace: Workspace

    @property
    def workspace_id(self) -> UUID:
        return self.workspace.id

    @property
    def tenant_id(self) -> UUID:
        return self.workspace.tenant_id

    @property
    def disciplines(self) -> list[str]:
        return list(self.workspace.disciplines or [])


def resolve_context(db: Session, user: AuthenticatedUser, workspace_id: UUID) -> HelperContext:
    """Resolve an accessible workspace, applying existing tenant access rules."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    return HelperContext(db=db, user=user, workspace=workspace)


def require_discipline(ctx: HelperContext, discipline: str | None) -> None:
    if discipline is None:
        return
    if discipline not in ctx.disciplines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )


def resolve_state(ctx: HelperContext, state_id: UUID) -> ArchitectureState:
    state = ctx.db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == ctx.workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture state not found",
        )
    return state


def require_proposal_state(ctx: HelperContext, state_id: UUID) -> ArchitectureState:
    state = resolve_state(ctx, state_id)
    if state.state_type == "current":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current architecture state is read-only and cannot be a proposal target",
        )
    return state


def resolve_architecture_object(ctx: HelperContext, object_id: UUID) -> ArchitectureObject:
    registry = ctx.db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == ctx.tenant_id,
        )
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )
    return registry


def resolve_catalog_system(ctx: HelperContext, system_id: UUID) -> CatalogSystem:
    system = ctx.db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.id == system_id,
            CatalogSystem.tenant_id == ctx.tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    )
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System not found")
    return system


def resolve_catalog_field(ctx: HelperContext, field_id: UUID) -> CatalogField:
    field = ctx.db.scalar(
        select(CatalogField).where(
            CatalogField.id == field_id,
            CatalogField.tenant_id == ctx.tenant_id,
            CatalogField.deleted_at.is_(None),
        )
    )
    if field is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog field not found")
    return field


def resolve_contract(ctx: HelperContext, contract_id: UUID) -> Integration:
    integration = ctx.db.scalar(
        select(Integration).where(
            Integration.id == contract_id,
            Integration.tenant_id == ctx.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return integration
