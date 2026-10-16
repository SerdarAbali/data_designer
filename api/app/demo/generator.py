"""Scope-aware deterministic demo workspace generator.

One generator, discipline modules, three presets. Generation is deterministic
(ids come from :mod:`app.demo.context`) and idempotent: the previously recorded
assets are purged before a demo is rebuilt, so re-running never duplicates
content and reset only ever removes generated demo assets.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete

from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    Scenario,
    Workspace,
)

from .catalog import SYSTEMS, build_catalog
from .context import DEMO_ORIGIN, DEMO_VERSION, DemoContext
from .enterprise import build_enterprise
from .information import build_information
from .integration import build_integration
from .scenarios import build_scenarios
from .solution import build_solution

# Preset -> discipline set. Only these three presets are supported.
PRESETS: dict[str, tuple[str, ...]] = {
    "full": ("enterprise", "information", "solution", "integration"),
    "solution_integration": ("solution", "integration"),
    "integration_only": ("integration",),
}

PRESET_LABELS = {
    "full": "Full Architecture",
    "solution_integration": "Solution + Integration",
    "integration_only": "Integration Only",
}

# Purge order respects foreign keys (children before parents).
_PURGE_ORDER: list[tuple[str, object, str]] = [
    ("scenario", Scenario, "tenant_id"),
    ("integration", Integration, "tenant_id"),
    ("relationship", ArchitectureRelationship, "tenant_id"),
    ("architecture_object", ArchitectureObject, "tenant_id"),
    ("catalog_field", CatalogField, "tenant_id"),
    ("catalog_object", CatalogObject, "tenant_id"),
    ("catalog_system", CatalogSystem, "tenant_id"),
    ("state", ArchitectureState, "workspace_id"),
]

_SYSTEM_POSITIONS = {
    "crm": {"x": 80, "y": 80},
    "billing": {"x": 460, "y": 80},
    "integration_runtime": {"x": 840, "y": 80},
}


def resolve_preset(preset: str | None) -> tuple[str, ...]:
    if preset is None or preset not in PRESETS:
        raise ValueError(f"Unknown demo preset: {preset!r}")
    return PRESETS[preset]


def purge_demo(db, workspace: Workspace) -> None:
    """Delete only the assets recorded by a previous demo generation."""
    assets = workspace.demo_assets or {}
    for kind, model, scope in _PURGE_ORDER:
        raw = assets.get(kind) or []
        ids: list[UUID] = []
        for value in raw:
            try:
                ids.append(UUID(str(value)))
            except ValueError:
                continue
        if not ids:
            continue
        query = delete(model).where(model.id.in_(ids))
        if scope == "tenant_id":
            query = query.where(model.tenant_id == workspace.tenant_id)
        else:
            query = query.where(model.workspace_id == workspace.id)
        db.execute(query)
    workspace.demo_assets = {}
    db.flush()


def _seed_states(db, ctx: DemoContext) -> tuple[ArchitectureState, ArchitectureState]:
    current = ArchitectureState(
        id=ctx.id("state.current"),
        workspace_id=ctx.workspace_id,
        name="Current State",
        state_type="current",
        description="Current customer onboarding (synthetic demo).",
        nodes=[],
        relationships=[],
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    candidate = ArchitectureState(
        id=ctx.id("state.candidate"),
        workspace_id=ctx.workspace_id,
        name="Candidate Design",
        state_type="candidate",
        description="Improved customer onboarding (synthetic demo).",
        nodes=[],
        relationships=[],
        created_at=ctx.now,
        updated_at=ctx.now,
    )
    db.add_all([current, candidate])
    ctx.record("state", current.id)
    ctx.record("state", candidate.id)
    db.flush()
    return current, candidate


def _seed_system_nodes(ctx: DemoContext) -> None:
    for key in SYSTEMS:
        position = _SYSTEM_POSITIONS.get(key, {"x": 80, "y": 80})
        ctx.add_node("current", f"system.{key}.cur", ctx.id(f"system.{key}"), position)
        ctx.add_node("candidate", f"system.{key}.cand", ctx.id(f"system.{key}"), position)


def _build_trace(db, ctx: DemoContext) -> None:
    """Cross-discipline edges connecting strategy to execution."""
    if ctx.has("enterprise") and ctx.has("solution"):
        db.add(
            ctx.relationship(
                "trace.process.solution",
                ctx.id("ent.process"),
                ctx.id("solution.onboarding"),
                "supports",
            )
        )
    if ctx.has("solution") and ctx.has("information"):
        db.add(
            ctx.relationship(
                "trace.interface.entity",
                ctx.id("iface.onboarding_api"),
                ctx.id("info.customer"),
                "references",
            )
        )
    if ctx.has("information"):
        for spec in ("customer_id", "first_name", "last_name", "email", "status", "consent"):
            db.add(
                ctx.relationship(
                    f"trace.entity.{spec}",
                    ctx.id("info.customer"),
                    ctx.id(f"info.customer.{spec}"),
                    "has_attribute",
                )
            )
    if ctx.has("enterprise") and ctx.has("information"):
        db.add(
            ctx.relationship(
                "trace.process.entity", ctx.id("ent.process"), ctx.id("info.customer"), "affects"
            )
        )
    db.flush()


def generate_demo(db, workspace: Workspace, preset: str) -> None:
    """Deterministically (re)generate a demo workspace for a preset."""
    disciplines = resolve_preset(preset)
    purge_demo(db, workspace)

    workspace.disciplines = list(disciplines)
    ctx = DemoContext(
        tenant_id=workspace.tenant_id,
        workspace_id=workspace.id,
        preset=preset,
        disciplines=set(disciplines),
        db=db,
    )
    workspace.demo_preset = preset
    workspace.demo_version = DEMO_VERSION

    current_state, candidate_state = _seed_states(db, ctx)
    build_catalog(db, ctx)
    _seed_system_nodes(ctx)

    if ctx.has("enterprise"):
        build_enterprise(db, ctx)
    if ctx.has("information"):
        build_information(db, ctx)
    if ctx.has("solution"):
        build_solution(db, ctx)
    if ctx.has("integration"):
        build_integration(db, ctx)
    _build_trace(db, ctx)
    if ctx.has("integration"):
        build_scenarios(db, ctx)

    db.flush()
    current_state.nodes = list(ctx.current_nodes)
    current_state.relationships = list(ctx.current_relationships)
    candidate_state.nodes = list(ctx.candidate_nodes)
    candidate_state.relationships = list(ctx.candidate_relationships)
    current_state.updated_at = ctx.now
    candidate_state.updated_at = ctx.now

    workspace.demo_generated_at = ctx.now
    workspace.demo_assets = {kind: values for kind, values in ctx.assets.items()}
    workspace.updated_at = datetime.now(UTC)
    db.flush()


def reset_demo(db, workspace: Workspace) -> None:
    """Remove generated demo content and regenerate the stored preset."""
    if not workspace.demo_preset:
        raise ValueError("This workspace is not a demo workspace")
    generate_demo(db, workspace, workspace.demo_preset)


def demo_status(workspace: Workspace) -> dict:
    generated = workspace.demo_generated_at
    return {
        "is_demo": bool(workspace.demo_preset),
        "preset": workspace.demo_preset,
        "version": workspace.demo_version,
        "origin": DEMO_ORIGIN,
        "generated_at": generated.isoformat() if generated else None,
    }
