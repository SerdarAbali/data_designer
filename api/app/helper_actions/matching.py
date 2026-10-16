"""Deterministic canonical matching for Slice 2 proposal helpers.

Matching order (fixed, no fuzzy auto-reuse):

1. Explicit canonical ID supplied by the caller.
2. Exact external identifier, where the canonical type supports one.
3. Exact normalized name within the correct tenant and canonical type
   (and parent scope for child records).
4. Parent-child match for attributes, interfaces, and operations.
5. Otherwise the caller proposes a new object, or the record is left unresolved.

Name similarity is only ever reported as a *suggestion*; it never causes a
record to be reused automatically. Catalog records are always read-only here:
these functions never create or modify them.
"""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app.helper_actions.context import HelperContext
from app.models import (
    ArchitectureInterface,
    ArchitectureObject,
    ArchitecturePrinciple,
    BusinessCapability,
    BusinessGoal,
    BusinessProcess,
    BusinessRequirement,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    DataRepository,
    DeploymentNode,
    InformationAttribute,
    InformationObject,
    Integration,
    IntegrationFieldRef,
    InterfaceOperation,
    OrganizationRole,
    SolutionBoundary,
    SolutionComponent,
    TrustBoundary,
)

_WORD_RE = re.compile(r"[^a-z0-9]+")

# Canonical kind -> typed model (read/matching only; never written here).
KIND_TABLE = {
    "business_goal": BusinessGoal,
    "business_requirement": BusinessRequirement,
    "business_capability": BusinessCapability,
    "business_process": BusinessProcess,
    "architecture_principle": ArchitecturePrinciple,
    "organization_role": OrganizationRole,
    "information_object": InformationObject,
    "information_attribute": InformationAttribute,
    "solution_boundary": SolutionBoundary,
    "component": SolutionComponent,
    "interface": ArchitectureInterface,
    "interface_operation": InterfaceOperation,
    "data_repository": DataRepository,
    "deployment_node": DeploymentNode,
    "trust_boundary": TrustBoundary,
}

# Canonical kind -> column holding the parent canonical ID, when applicable.
KIND_PARENT_COLUMN = {
    "information_attribute": "entity_object_id",
    "interface": "component_object_id",
    "interface_operation": "interface_object_id",
    "component": "solution_object_id",
    "data_repository": "solution_object_id",
    "deployment_node": "solution_object_id",
    "trust_boundary": "solution_object_id",
}

# Canonical kind -> column searched for an exact external identifier.
EXTERNAL_ID_COLUMNS = {
    "information_object": "external_identifier",
    "solution_boundary": "external_identifier",
}


def normalize_name(value: str) -> str:
    return _WORD_RE.sub("-", value.strip().lower()).strip("-")


def slug(value: str) -> str:
    return normalize_name(value) or "item"


def _name_of(row) -> str:
    return getattr(row, "name", "") or ""


def find_registry(ctx: HelperContext, object_id: UUID, kinds: set[str] | None = None):
    registry = ctx.db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == ctx.tenant_id,
        )
    )
    if registry is None:
        return None
    if kinds is not None and registry.kind not in kinds:
        return None
    return registry


def find_typed_row(ctx: HelperContext, kind: str, object_id: UUID):
    model = KIND_TABLE.get(kind)
    if model is None:
        return None
    return ctx.db.scalar(
        select(model).where(
            model.object_id == object_id,
            model.tenant_id == ctx.tenant_id,
        )
    )


def find_canonical_by_name(
    ctx: HelperContext,
    kind: str,
    name: str,
    parent_object_id: UUID | None = None,
):
    """Exact normalised-name match within tenant + kind (+ parent scope)."""
    model = KIND_TABLE.get(kind)
    if model is None:
        return None
    parent_column = KIND_PARENT_COLUMN.get(kind)
    if parent_column is not None and parent_object_id is None:
        return None
    target = normalize_name(name)
    conditions = [model.tenant_id == ctx.tenant_id]
    if parent_column is not None:
        conditions.append(getattr(model, parent_column) == parent_object_id)
    rows = list(
        ctx.db.scalars(select(model).where(*conditions).order_by(model.name, model.object_id))
    )
    for row in rows:
        if normalize_name(_name_of(row)) == target:
            return row
    return None


def find_by_external_id(ctx: HelperContext, kind: str, external_id: str):
    column = EXTERNAL_ID_COLUMNS.get(kind)
    model = KIND_TABLE.get(kind)
    if column is None or model is None:
        return None
    return ctx.db.scalar(
        select(model).where(
            model.tenant_id == ctx.tenant_id,
            getattr(model, column) == external_id,
        )
    )


def find_catalog_system(
    ctx: HelperContext, system_id: UUID | None = None, name: str | None = None
) -> CatalogSystem | None:
    if system_id is not None:
        return ctx.db.scalar(
            select(CatalogSystem).where(
                CatalogSystem.id == system_id,
                CatalogSystem.tenant_id == ctx.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
    if name is None:
        return None
    target = normalize_name(name)
    rows = list(
        ctx.db.scalars(
            select(CatalogSystem)
            .where(
                CatalogSystem.tenant_id == ctx.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
            .order_by(CatalogSystem.name, CatalogSystem.id)
        )
    )
    for row in rows:
        if normalize_name(row.name) == target:
            return row
    return None


def find_catalog_field_by_id(ctx: HelperContext, field_id: UUID) -> CatalogField | None:
    return ctx.db.scalar(
        select(CatalogField).where(
            CatalogField.id == field_id,
            CatalogField.tenant_id == ctx.tenant_id,
            CatalogField.deleted_at.is_(None),
        )
    )


def catalog_object_name(ctx: HelperContext, object_id: UUID) -> str | None:
    row = ctx.db.scalar(
        select(CatalogObject).where(
            CatalogObject.id == object_id,
            CatalogObject.tenant_id == ctx.tenant_id,
        )
    )
    return row.name if row is not None else None


def match_catalog_field(
    ctx: HelperContext,
    object_name: str | None,
    field_name: str | None,
) -> tuple[CatalogField | None, bool, list[str]]:
    """Resolve (Catalog object name, field name) to exactly one active field.

    Returns ``(field, ambiguous, candidates)``. ``ambiguous`` is True when more
    than one field matches; ``candidates`` are human-readable ``object.field``
    suggestions for unresolved decisions. Never guesses from partial similarity.
    """
    if not object_name or not field_name:
        return None, False, []
    target_object = normalize_name(object_name)
    target_field = normalize_name(field_name)
    matches: list[CatalogField] = []
    suggestions: list[str] = []
    objects = list(
        ctx.db.scalars(
            select(CatalogObject)
            .where(
                CatalogObject.tenant_id == ctx.tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
            .order_by(CatalogObject.name, CatalogObject.id)
        )
    )
    for obj in objects:
        object_matches = normalize_name(obj.name or "") == target_object
        fields = list(
            ctx.db.scalars(
                select(CatalogField)
                .where(
                    CatalogField.tenant_id == ctx.tenant_id,
                    CatalogField.object_id == obj.id,
                    CatalogField.deleted_at.is_(None),
                )
                .order_by(CatalogField.name, CatalogField.id)
            )
        )
        for field in fields:
            field_matches = normalize_name(field.name or "") == target_field
            if object_matches and field_matches:
                matches.append(field)
            elif object_matches or field_matches:
                suggestions.append(f"{obj.name}.{field.name}")
    if len(matches) == 1:
        return matches[0], False, []
    if len(matches) > 1:
        return None, True, sorted(f"{object_name}.{field_name}" for _ in matches)
    return None, False, sorted(set(suggestions))[:10]


def suggest_catalog_fields(ctx: HelperContext, name: str, limit: int = 5) -> list[str]:
    """Name-similarity suggestions only; never used for automatic reuse."""
    target = normalize_name(name)
    if not target:
        return []
    objects = {
        obj.id: obj.name
        for obj in ctx.db.scalars(
            select(CatalogObject).where(
                CatalogObject.tenant_id == ctx.tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
    }
    suggestions: list[str] = []
    fields = list(
        ctx.db.scalars(
            select(CatalogField)
            .where(
                CatalogField.tenant_id == ctx.tenant_id,
                CatalogField.deleted_at.is_(None),
            )
            .order_by(CatalogField.name, CatalogField.id)
        )
    )
    for field in fields:
        field_name = normalize_name(field.name or "")
        if target and (target in field_name or field_name in target):
            suggestions.append(f"{objects.get(field.object_id, '?')}.{field.name}")
    return sorted(set(suggestions))[:limit]


# --- Slice 3: integration/contract/mapping matching --------------------------
# Canonical contracts are ``Integrations``; reused contracts are read-only here.
# Every function only *reads* canonical records.

# Temp-id target types owned by the Slice 3 builder (never registry kinds).
SLICE3_TEMP_KINDS = frozenset(
    {"contract", "mapping", "transformation", "resilience", "scenario", "conformance"}
)

# A system is an integration runtime only when modelled data proves it: an
# explicit runtime catalog kind, or a name that names a runtime. Callers must
# reference the runtime explicitly; helpers never auto-discover one by name.
RUNTIME_SYSTEM_KINDS = {"integration_runtime", "integration_runtime_platform", "esb", "runtime"}


def is_runtime_system(system: CatalogSystem | None) -> bool:
    if system is None:
        return False
    if (system.kind or "").strip().lower() in RUNTIME_SYSTEM_KINDS:
        return True
    return "runtime" in (system.name or "").strip().lower()


def normalize_purpose(value: str | None) -> str:
    return normalize_name(value or "")


def placeholder_uuid(value: str) -> UUID:
    """Deterministic placeholder UUID for a proposal-local temporary ID.

    Scenarios reference proposed contracts by temporary ID; the existing scenario
    document model needs a UUID, so the builder maps the temp ID to a stable
    placeholder that apply (a later slice) replaces with the real contract ID.
    """
    return uuid5(NAMESPACE_URL, f"helper-actions:{value}")


def find_contract(ctx: HelperContext, contract_id: UUID):
    return ctx.db.scalar(
        select(Integration).where(
            Integration.id == contract_id,
            Integration.tenant_id == ctx.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )


def list_contracts(ctx: HelperContext):
    return list(
        ctx.db.scalars(
            select(Integration)
            .where(
                Integration.tenant_id == ctx.tenant_id,
                Integration.deleted_at.is_(None),
            )
            .order_by(Integration.name, Integration.id)
        )
    )


def find_contract_by_external_id(ctx: HelperContext, external_id: str):
    return ctx.db.scalar(
        select(Integration).where(
            Integration.tenant_id == ctx.tenant_id,
            Integration.deleted_at.is_(None),
            Integration.external_identifier == external_id,
        )
    )


def list_field_refs(ctx: HelperContext, contract_id: UUID):
    return list(
        ctx.db.scalars(
            select(IntegrationFieldRef).where(
                IntegrationFieldRef.tenant_id == ctx.tenant_id,
                IntegrationFieldRef.integration_id == contract_id,
            )
        )
    )


def find_catalog_object(ctx: HelperContext, object_id: UUID) -> CatalogObject | None:
    return ctx.db.scalar(
        select(CatalogObject).where(
            CatalogObject.id == object_id,
            CatalogObject.tenant_id == ctx.tenant_id,
            CatalogObject.deleted_at.is_(None),
        )
    )


def list_active_fields(ctx: HelperContext, object_id: UUID) -> list[CatalogField]:
    if object_id is None:
        return []
    return list(
        ctx.db.scalars(
            select(CatalogField)
            .where(
                CatalogField.tenant_id == ctx.tenant_id,
                CatalogField.object_id == object_id,
                CatalogField.deleted_at.is_(None),
            )
            .order_by(CatalogField.name, CatalogField.id)
        )
    )


def find_catalog_field_by_external_id(ctx: HelperContext, external_id: str) -> CatalogField | None:
    return ctx.db.scalar(
        select(CatalogField).where(
            CatalogField.tenant_id == ctx.tenant_id,
            CatalogField.deleted_at.is_(None),
            CatalogField.external_identifier == external_id,
        )
    )


def match_catalog_field_in_object(
    ctx: HelperContext, object_id: UUID, name: str
) -> tuple[CatalogField | None, bool]:
    """Exact normalized field-name match within one object. Returns (field, ambiguous)."""
    target = normalize_name(name)
    matches = [
        field
        for field in list_active_fields(ctx, object_id)
        if normalize_name(field.name or "") == target
    ]
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def find_interface(ctx: HelperContext, interface_id: UUID) -> ArchitectureInterface | None:
    return ctx.db.scalar(
        select(ArchitectureInterface).where(
            ArchitectureInterface.object_id == interface_id,
            ArchitectureInterface.tenant_id == ctx.tenant_id,
        )
    )


def list_interfaces(ctx: HelperContext) -> list[ArchitectureInterface]:
    return list(
        ctx.db.scalars(
            select(ArchitectureInterface).where(
                ArchitectureInterface.tenant_id == ctx.tenant_id,
            )
        )
    )


def find_interface_operation(ctx: HelperContext, operation_id: UUID) -> InterfaceOperation | None:
    return ctx.db.scalar(
        select(InterfaceOperation).where(
            InterfaceOperation.object_id == operation_id,
            InterfaceOperation.tenant_id == ctx.tenant_id,
        )
    )


def match_interface_operation_in_interface(
    ctx: HelperContext, interface_id: UUID, name: str
) -> tuple[InterfaceOperation | None, bool]:
    target = normalize_name(name)
    rows = list(
        ctx.db.scalars(
            select(InterfaceOperation).where(
                InterfaceOperation.tenant_id == ctx.tenant_id,
                InterfaceOperation.interface_object_id == interface_id,
            )
        )
    )
    matches = [row for row in rows if normalize_name(row.name or "") == target]
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def match_interface_operation_by_name(
    ctx: HelperContext, name: str
) -> tuple[InterfaceOperation | None, bool]:
    target = normalize_name(name)
    rows = list(
        ctx.db.scalars(
            select(InterfaceOperation)
            .where(InterfaceOperation.tenant_id == ctx.tenant_id)
            .order_by(InterfaceOperation.name, InterfaceOperation.object_id)
        )
    )
    matches = [row for row in rows if normalize_name(row.name or "") == target]
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1
