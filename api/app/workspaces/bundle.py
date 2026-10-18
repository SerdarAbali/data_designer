"""Canonical workspace portability: export, import and fork.

A workspace bundle is a deterministic, tenant-neutral JSON snapshot of the
records that give a workspace its architecture meaning. Three operations share
this module on purpose:

* ``export_workspace_bundle`` serialises a workspace.
* ``import_workspace_bundle`` remaps and re-creates it in a fresh workspace.
* ``fork_workspace`` is literally an export imported into a new tenant.

Because fork reuses the same serializer and importer there is no second mapping
implementation that can drift, and fork inherits every guarantee the importer
gives (dependency-ordered insert, id remapping, validation, transactionality).

Two things a bundle deliberately never contains: credentials/secrets and
Assistant runtime records (conversations, messages, tool calls, model settings,
sessions). Evidence keeps only the metadata and external locator the evidence
model already stores; user references are kept only where the evidence model
requires them (``recorded_by``) and are substituted with the acting user when
they cannot be resolved in the destination database.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, select
from sqlalchemy.orm import Session

from app.architecture.vocabulary import (
    CONFIDENCES,
    ENVIRONMENT_SCOPES,
    EVIDENCE_CLASSIFICATIONS,
    EVIDENCE_SOURCE_TYPES,
    LIFECYCLE_STAGES,
    OPERATIONAL_STATUSES,
    VERIFICATION_STATUSES,
)
from app.models import (
    BASELINE_DRAFT,
    BASELINE_LOCKED,
    ArchitectureEvidence,
    ArchitectureInterface,
    ArchitectureObject,
    ArchitecturePrinciple,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
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
    IntegrationDependency,
    IntegrationFieldRef,
    IntegrationStateOverride,
    InterfaceOperation,
    OrganizationRole,
    Scenario,
    SolutionBoundary,
    SolutionComponent,
    SolutionIntegration,
    SolutionMember,
    Tenant,
    TrustBoundary,
    User,
    Workspace,
)

logger = logging.getLogger(__name__)

BUNDLE_FORMAT = "data-designer-workspace"
#: The version this module writes. Older versions stay importable.
BUNDLE_VERSION = 2
#: A stable, human-readable identifier for the written schema.
BUNDLE_SCHEMA = f"{BUNDLE_FORMAT}/v{BUNDLE_VERSION}"
#: The oldest structure still understood: the pre-Slice-8 layout.
LEGACY_VERSION = 1

DEFAULT_DISCIPLINES = ("enterprise", "information", "solution", "integration")
WORKSPACE_DISCIPLINES = frozenset(DEFAULT_DISCIPLINES)

#: The approved Solution-to-Solution vocabulary (shared with the landscape).
SOLUTION_RELATIONSHIP_TYPES: tuple[str, ...] = (
    "depends_on",
    "uses",
    "provides_to",
    "replaces",
    "transitions_to",
    "shares_information_with",
)

#: Contract facts that a Candidate/Target state may override.
FACT_FIELDS: tuple[str, ...] = ("lifecycle_stage", "operational_status", "environment_scope")

#: Legacy bundle keys accepted on read. ``sample_source_records`` was written by
#: the pre-Slice-8 exporter for a model field that never existed; the real
#: ``Integration`` field is ``sample_rows``. ``metadata`` was the legacy key for
#: the ``extra_metadata`` field.
LEGACY_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sample_rows": ("sample_source_records",),
    "extra_metadata": ("metadata",),
}

#: Columns never carried in a bundle payload.
NEVER_PAYLOAD = frozenset({"deleted_at", "tenant_id"})

#: The closed evidence target arc.
EVIDENCE_TARGET_COLUMNS: tuple[str, ...] = (
    "architecture_object_id",
    "architecture_relationship_id",
    "integration_id",
    "integration_dependency_id",
    "solution_member_id",
)

_FACT_COLUMN_VOCABULARY: dict[str, tuple[str, ...]] = {
    "lifecycle_stage": LIFECYCLE_STAGES,
    "operational_status": OPERATIONAL_STATUSES,
    "environment_scope": ENVIRONMENT_SCOPES,
}

_EVIDENCE_VOCABULARY: dict[str, tuple[str, ...]] = {
    "evidence_classification": EVIDENCE_CLASSIFICATIONS,
    "source_type": EVIDENCE_SOURCE_TYPES,
    "confidence": CONFIDENCES,
    "verification_status": VERIFICATION_STATUSES,
}

SOLUTION_KIND = "solution_boundary"
ASSOCIATION_ROLES = frozenset({"owned", "participating", "dependency"})

_MISSING = object()


@dataclass(frozen=True)
class Section:
    """One bundle table: a model, its id namespace and its reference columns."""

    key: str
    model: type
    namespace: str
    since: int = 2
    id_field: str = "id"
    tenant_field: str | None = "tenant_id"
    workspace_field: str | None = None
    #: ``(column, namespace)`` pairs whose value is an id in another namespace.
    refs: tuple[tuple[str, str], ...] = ()
    #: Columns holding a user id (special-cased on import).
    user_refs: tuple[str, ...] = ()
    #: Nullable user references. When the original user cannot be resolved the
    #: value is dropped rather than misattributed to the importing user.
    optional_user_refs: tuple[str, ...] = ()
    #: Ref columns applied in a second pass, because their target section is
    #: imported later (a mutually dependent pair of tables is broken this way).
    defer: tuple[str, ...] = ()
    #: ``(column, container)`` pairs: the JSON container a column must hold.
    expect: tuple[tuple[str, str], ...] = ()
    #: Natural keys the database enforces; duplicates are reported up front
    #: instead of surfacing as an opaque integrity error mid-import.
    unique: tuple[tuple[str, ...], ...] = ()
    #: JSON columns that embed ids and must be remapped on import.
    json_refs: tuple[str, ...] = ()
    #: Deterministic ordering; ``id_field`` is always appended as a tiebreaker.
    order: tuple[str, ...] = ()
    #: Additional namespaces this section's ids also belong to.
    also_namespaces: tuple[str, ...] = ()


# Dependency-ordered. A section may only reference sections that appear before
# it; this order is also the import insert order.
SECTIONS: tuple[Section, ...] = (
    Section(
        "states",
        ArchitectureState,
        "state",
        tenant_field=None,
        workspace_field="workspace_id",
        json_refs=("nodes", "relationships"),
        expect=(
            ("nodes", "list"),
            ("relationships", "list"),
        ),
        # The lock actor is optional provenance: it is preserved when the user
        # resolves, and dropped rather than invented when it does not.
        optional_user_refs=("baseline_locked_by",),
        order=("state_type", "name"),
    ),
    Section(
        "systems",
        CatalogSystem,
        "system",
        since=1,
        order=("name",),
        unique=(("name",), ("external_identifier",)),
        also_namespaces=("registry",),
    ),
    Section(
        "objects",
        CatalogObject,
        "object",
        since=1,
        refs=(("system_id", "system"),),
        order=("name",),
        unique=(("system_id", "name"),),
    ),
    Section(
        "fields",
        CatalogField,
        "field",
        since=1,
        refs=(("object_id", "object"),),
        order=("object_id", "position", "name"),
        unique=(("object_id", "name"),),
    ),
    Section(
        "architecture_objects",
        ArchitectureObject,
        "registry",
        refs=(
            ("system_id", "system"),
            ("catalog_object_id", "object"),
            ("catalog_field_id", "field"),
            ("integration_id", "integration"),
            ("scenario_id", "scenario"),
        ),
        # Contracts and scenarios are imported after the registry, so these two
        # references are patched in a second pass instead of the first insert.
        defer=("integration_id", "scenario_id"),
        order=("kind",),
        unique=(("system_id",),),
    ),
    Section(
        "business_goals",
        BusinessGoal,
        "registry",
        id_field="object_id",
        refs=(("created_in_state_id", "state"),),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "business_requirements",
        BusinessRequirement,
        "registry",
        id_field="object_id",
        order=("name",),
    ),
    Section(
        "business_capabilities",
        BusinessCapability,
        "registry",
        id_field="object_id",
        order=("name",),
    ),
    Section(
        "business_processes",
        BusinessProcess,
        "registry",
        id_field="object_id",
        refs=(("created_in_state_id", "state"),),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "architecture_principles",
        ArchitecturePrinciple,
        "registry",
        id_field="object_id",
        refs=(("created_in_state_id", "state"),),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "organization_roles",
        OrganizationRole,
        "registry",
        id_field="object_id",
        refs=(("created_in_state_id", "state"),),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "information_objects",
        InformationObject,
        "registry",
        id_field="object_id",
        refs=(("authoritative_system_id", "system"),),
        order=("name",),
        unique=(("external_identifier",),),
    ),
    Section(
        "information_attributes",
        InformationAttribute,
        "registry",
        id_field="object_id",
        refs=(("entity_object_id", "registry"), ("created_in_state_id", "state")),
        order=("entity_object_id", "ordinal", "name"),
        unique=(("entity_object_id", "name"),),
    ),
    Section(
        "solution_boundaries",
        SolutionBoundary,
        "registry",
        id_field="object_id",
        order=("name",),
        unique=(("external_identifier",),),
    ),
    Section(
        "solution_components",
        SolutionComponent,
        "registry",
        id_field="object_id",
        refs=(
            ("solution_object_id", "registry"),
            ("parent_component_object_id", "registry"),
            ("created_in_state_id", "state"),
        ),
        order=("name",),
    ),
    Section(
        "solution_interfaces",
        ArchitectureInterface,
        "registry",
        id_field="object_id",
        refs=(("component_object_id", "registry"), ("created_in_state_id", "state")),
        order=("name",),
    ),
    Section(
        "interface_operations",
        InterfaceOperation,
        "registry",
        id_field="object_id",
        refs=(
            ("interface_object_id", "registry"),
            ("request_object_id", "registry"),
            ("response_object_id", "registry"),
            ("created_in_state_id", "state"),
        ),
        order=("interface_object_id", "ordinal", "name"),
        unique=(("interface_object_id", "name"),),
    ),
    Section(
        "data_repositories",
        DataRepository,
        "registry",
        id_field="object_id",
        refs=(("solution_object_id", "registry"), ("created_in_state_id", "state")),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "deployment_nodes",
        DeploymentNode,
        "registry",
        id_field="object_id",
        refs=(("solution_object_id", "registry"), ("created_in_state_id", "state")),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "trust_boundaries",
        TrustBoundary,
        "registry",
        id_field="object_id",
        refs=(("solution_object_id", "registry"), ("created_in_state_id", "state")),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("name",),
    ),
    Section(
        "integrations",
        Integration,
        "integration",
        since=1,
        refs=(
            ("source_system_id", "system"),
            ("source_object_id", "object"),
            ("target_system_id", "system"),
            ("target_object_id", "object"),
            ("error_response_object_id", "object"),
            ("producer_interface_id", "registry"),
            ("consumer_interface_id", "registry"),
            ("mediator_system_id", "system"),
        ),
        json_refs=(
            "graph",
            "response_graph",
            "error_response_graph",
            "sample_rows",
            # Both documents can carry architecture ids: a specification may name
            # the field used as an idempotency key, and a trigger may reference a
            # watched field. Free-form extra_metadata is deliberately left alone,
            # matching the pre-Slice-8 behaviour.
            "specification",
            "trigger_config",
        ),
        expect=(
            ("graph", "object"),
            ("response_graph", "object"),
            ("error_response_graph", "object"),
            ("sample_rows", "list"),
            ("trigger_config", "object"),
            ("specification", "object"),
        ),
        order=("name",),
        unique=(("name",), ("external_identifier",)),
    ),
    Section(
        "integration_field_refs",
        IntegrationFieldRef,
        "field_ref",
        refs=(("integration_id", "integration"), ("object_id", "object"), ("field_id", "field")),
        order=("integration_id", "direction", "field_id"),
        unique=(("integration_id", "field_id", "direction"),),
    ),
    Section(
        "integration_dependencies",
        IntegrationDependency,
        "dependency",
        refs=(
            ("upstream_integration_id", "integration"),
            ("downstream_integration_id", "integration"),
        ),
        order=("upstream_integration_id", "downstream_integration_id"),
        unique=(("upstream_integration_id", "downstream_integration_id"),),
    ),
    Section(
        "integration_state_overrides",
        IntegrationStateOverride,
        "integration_override",
        refs=(("state_id", "state"), ("integration_id", "integration")),
        order=("state_id", "integration_id"),
        unique=(("state_id", "integration_id"),),
    ),
    Section(
        "solution_members",
        SolutionMember,
        "solution_member",
        refs=(
            ("solution_object_id", "registry"),
            ("system_id", "system"),
            ("created_in_state_id", "state"),
        ),
        order=("solution_object_id", "system_id"),
        unique=(("solution_object_id", "system_id"),),
    ),
    Section(
        "solution_integrations",
        SolutionIntegration,
        "solution_integration",
        refs=(
            ("solution_object_id", "registry"),
            ("integration_id", "integration"),
            ("created_in_state_id", "state"),
        ),
        order=("solution_object_id", "integration_id", "created_in_state_id"),
        unique=(("solution_object_id", "integration_id", "created_in_state_id"),),
    ),
    Section(
        "architecture_relationships",
        ArchitectureRelationship,
        "relationship",
        refs=(
            ("source_object_id", "registry"),
            ("target_object_id", "registry"),
            ("created_in_state_id", "state"),
        ),
        json_refs=("properties",),
        expect=(("properties", "object"),),
        order=("source_object_id", "relationship_type", "target_object_id"),
        unique=(("source_object_id", "target_object_id", "relationship_type"),),
    ),
    Section(
        "scenarios",
        Scenario,
        "scenario",
        since=1,
        refs=(("scope_integration_id", "integration"),),
        json_refs=("document",),
        expect=(("document", "object"),),
        order=("name",),
        unique=(("name",),),
    ),
    Section(
        "evidence",
        ArchitectureEvidence,
        "evidence",
        refs=(
            ("architecture_object_id", "registry"),
            ("architecture_relationship_id", "relationship"),
            ("integration_id", "integration"),
            ("integration_dependency_id", "dependency"),
            ("solution_member_id", "solution_member"),
            ("created_in_state_id", "state"),
        ),
        user_refs=("recorded_by",),
        order=("recorded_at", "source_title"),
    ),
    Section(
        "architecture_state_members",
        ArchitectureStateMember,
        "state_member",
        workspace_field="workspace_id",
        refs=(("state_id", "state"), ("object_id", "registry")),
        order=("state_id", "object_id"),
    ),
)

SECTION_BY_KEY: dict[str, Section] = {section.key: section for section in SECTIONS}



class BundleError(ValueError):
    """A stable, actionable bundle failure.

    ``code`` is the machine-readable contract; ``context`` carries the record
    coordinates an operator needs to fix the bundle.
    """

    def __init__(self, code: str, message: str, **context: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.context}


@dataclass
class ImportReport:
    """Non-fatal facts about an import worth surfacing to the caller."""

    source_version: int = LEGACY_VERSION
    user_substitutions: list[str] = field(default_factory=list)
    dropped_user_references: list[str] = field(default_factory=list)
    baseline_backfills: list[str] = field(default_factory=list)


# --- shared helpers -----------------------------------------------------------


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _remap_uuids_in_json(obj: Any, mapping: dict[str, str]) -> Any:
    """Replace embedded id strings. Used for state canvases and graph documents."""
    if not mapping:
        return deepcopy(obj)
    dumped = json.dumps(obj)
    for old_id, new_id in mapping.items():
        dumped = dumped.replace(old_id, new_id)
    return json.loads(dumped)


def _sort_key(value: Any) -> str:
    return "" if value is None else str(value)


def attribute_columns(model: type) -> dict[str, Any]:
    """Mapped *attribute* name -> Column.

    Attribute names, never database column names: ``extra_metadata`` is stored in
    a column called ``metadata``, and reading that name off an instance would
    return SQLAlchemy's own ``MetaData`` object.
    """
    return {prop.key: prop.columns[0] for prop in model.__mapper__.column_attrs}


def _payload_fields(section: Section) -> tuple[str, ...]:
    """Attributes copied verbatim: everything the model has, minus handled ones."""
    handled = {
        section.id_field,
        *(column for column, _namespace in section.refs),
        *section.user_refs,
        *section.json_refs,
        *NEVER_PAYLOAD,
    }
    if section.tenant_field:
        handled.add(section.tenant_field)
    if section.workspace_field:
        handled.add(section.workspace_field)
    return tuple(name for name in attribute_columns(section.model) if name not in handled)


def _ordered_rows(section: Section, rows: list[dict]) -> list[dict]:
    keys = (*section.order, section.id_field)
    return sorted(rows, key=lambda row: tuple(_sort_key(row.get(key)) for key in keys))


def _declares_schema(bundle: dict) -> bool:
    return bundle.get("schema") == BUNDLE_SCHEMA


def _version(bundle: dict) -> int:
    value = bundle.get("version", LEGACY_VERSION)
    if isinstance(value, bool) or not isinstance(value, int):
        return -1
    return value


def _active_sections(version: int) -> tuple[Section, ...]:
    if version >= BUNDLE_VERSION:
        return SECTIONS
    return tuple(section for section in SECTIONS if section.since <= version)


def _dict_rows(bundle: dict, key: str) -> list[dict]:
    rows = bundle.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


# --- export ------------------------------------------------------------------


def _export_section(
    db: Session, section: Section, tenant_id: UUID, workspace_id: UUID
) -> list[dict]:
    stmt = select(section.model)
    conditions = []
    if section.tenant_field:
        conditions.append(getattr(section.model, section.tenant_field) == tenant_id)
    if section.workspace_field:
        # Workspace-scoped rows (architecture states and their members) carry no
        # tenant column, so they are scoped by the workspace id instead.
        conditions.append(getattr(section.model, section.workspace_field) == workspace_id)
    if hasattr(section.model, "deleted_at"):
        conditions.append(section.model.deleted_at.is_(None))
    if conditions:
        stmt = stmt.where(*conditions)

    payload: list[dict] = []
    for row in db.scalars(stmt):
        record: dict[str, Any] = {}
        for name in _payload_fields(section):
            record[name] = _jsonable(getattr(row, name))
        for column, _namespace in section.refs:
            value = getattr(row, column)
            record[column] = None if value is None else str(value)
        for name in section.json_refs:
            record[name] = _jsonable(getattr(row, name))
        for name in section.user_refs:
            value = getattr(row, name)
            record[name] = None if value is None else str(value)
        record[section.id_field] = str(getattr(row, section.id_field))
        payload.append({key: record[key] for key in sorted(record)})
    return _ordered_rows(section, payload)


def export_workspace_bundle(db: Session, tenant_id: UUID) -> dict:
    """Serialise a workspace. Never mutates the source workspace."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise BundleError("workspace_not_found", "Workspace not found")

    workspace = db.scalar(
        select(Workspace).where(Workspace.tenant_id == tenant_id, Workspace.deleted_at.is_(None))
    )
    disciplines = list(workspace.disciplines) if workspace else list(DEFAULT_DISCIPLINES)
    # A workspace shares its id with its backing tenant (see _ensure_workspace_entity),
    # which is also the fallback when the workspace row has not been materialised.
    workspace_id = workspace.id if workspace is not None else tenant_id

    bundle: dict[str, Any] = {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "schema": BUNDLE_SCHEMA,
        "exported_at": datetime.now(UTC).isoformat(),
        "workspace": {
            "name": tenant.name,
            "description": tenant.description,
            "disciplines": disciplines,
        },
    }
    for section in SECTIONS:
        bundle[section.key] = _export_section(db, section, tenant_id, workspace_id)
    return bundle


# --- validation ---------------------------------------------------------------


def _problem(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **context}


def _registry_kinds(bundle: dict) -> dict[str, str]:
    """Registry id -> architecture-object kind, used to classify relationship ends."""
    kinds: dict[str, str] = {}
    for row in _dict_rows(bundle, "architecture_objects"):
        value = row.get("id")
        if isinstance(value, str):
            kinds[value] = str(row.get("kind"))
    for row in _dict_rows(bundle, "systems"):
        value = row.get("id")
        if isinstance(value, str):
            kinds.setdefault(value, "system")
    return kinds


def validate_bundle(bundle: Any) -> list[dict[str, Any]]:
    """Return every problem found, each with a stable code and record context.

    The validator is deliberately read-only and total: it reports *all* problems
    rather than the first, and never coerces an invalid value into a default.
    """
    problems: list[dict[str, Any]] = []
    if not isinstance(bundle, dict):
        return [_problem("invalid_bundle", "The bundle must be a JSON object")]

    if bundle.get("format") != BUNDLE_FORMAT:
        problems.append(
            _problem(
                "invalid_format",
                f"Expected format '{BUNDLE_FORMAT}'",
                value=bundle.get("format"),
            )
        )

    version = _version(bundle)
    if version < 1:
        problems.append(
            _problem("invalid_version", "The bundle version must be a positive integer")
        )
        return problems
    if version > BUNDLE_VERSION:
        problems.append(
            _problem(
                "unsupported_version",
                f"This application reads bundle versions up to {BUNDLE_VERSION}",
                value=version,
                supported=BUNDLE_VERSION,
            )
        )
        return problems

    workspace = bundle.get("workspace")
    if not isinstance(workspace, dict):
        problems.append(
            _problem("missing_section", "The bundle has no workspace metadata", section="workspace")
        )
    else:
        disciplines = workspace.get("disciplines")
        if disciplines is not None and (
            not isinstance(disciplines, list)
            or not all(isinstance(item, str) for item in disciplines)
        ):
            problems.append(
                _problem(
                    "invalid_disciplines",
                    "Workspace disciplines must be a list of strings",
                    section="workspace",
                )
            )
        elif isinstance(disciplines, list):
            unknown = sorted(set(disciplines) - WORKSPACE_DISCIPLINES)
            if unknown:
                problems.append(
                    _problem(
                        "invalid_disciplines",
                        "Unknown workspace discipline",
                        section="workspace",
                        values=unknown,
                    )
                )

    active = _active_sections(version)
    # A bundle written by this module declares the schema and must carry every
    # section (even empty ones). Anything else — a legacy v1 bundle, or a
    # hand-written one — is read leniently: an absent section means "absent or
    # unspecified", never corruption. A present section must always be a list.
    required = [section.key for section in active] if _declares_schema(bundle) else []
    for key in [*required, *(section.key for section in active if section.key not in required)]:
        rows = bundle.get(key)
        if rows is None:
            if key in required:
                problems.append(
                    _problem("missing_section", f"Bundle section '{key}' is required", section=key)
                )
        elif not isinstance(rows, list):
            problems.append(
                _problem("invalid_section", f"Bundle section '{key}' must be a list", section=key)
            )

    # Ids: presence, uniqueness (per section), and the namespace index used for
    # reference checks. Two sections may legitimately share a namespace: a typed
    # architecture object and its registry row have the same id.
    ids: dict[str, set[str]] = {}
    seen: dict[str, set[str]] = {}
    for section in active:
        rows = bundle.get(section.key)
        if not isinstance(rows, list):
            continue
        bucket = seen.setdefault(section.key, set())
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(
                    _problem(
                        "invalid_record",
                        f"Each '{section.key}' record must be an object",
                        section=section.key,
                        index=index,
                    )
                )
                continue
            value = row.get(section.id_field)
            if not isinstance(value, str) or not value:
                problems.append(
                    _problem(
                        "invalid_id",
                        f"'{section.key}' record has no {section.id_field}",
                        section=section.key,
                        index=index,
                    )
                )
                continue
            if value in bucket:
                problems.append(
                    _problem(
                        "duplicate_id",
                        f"Duplicate id in '{section.key}'",
                        section=section.key,
                        index=index,
                        value=value,
                    )
                )
                continue
            bucket.add(value)
            ids.setdefault(section.namespace, set()).add(value)
            for extra in section.also_namespaces:
                ids.setdefault(extra, set()).add(value)

    def resolves(namespace: str, value: Any) -> bool:
        return isinstance(value, str) and value in ids.get(namespace, set())

    kinds = _registry_kinds(bundle)

    for section in active:
        for index, row in enumerate(_dict_rows(bundle, section.key)):
            context = {
                "section": section.key,
                "index": index,
                section.id_field: row.get(section.id_field),
            }
            for column, namespace in section.refs:
                value = row.get(column)
                if value is None:
                    continue
                if not resolves(namespace, value):
                    problems.append(
                        _problem(
                            "broken_reference",
                            f"'{column}' does not resolve to a {namespace} record",
                            column=column,
                            value=value,
                            **context,
                        )
                    )
            for field_name, allowed in _FACT_COLUMN_VOCABULARY.items():
                if field_name not in row:
                    continue
                value = row.get(field_name)
                if value is not None and value not in allowed:
                    problems.append(
                        _problem(
                            "invalid_vocabulary",
                            f"'{field_name}' is not an approved value",
                            column=field_name,
                            value=value,
                            **context,
                        )
                    )
            if section.key == "states":
                baseline_status = row.get("baseline_status")
                if baseline_status is not None and baseline_status not in (
                    BASELINE_DRAFT,
                    BASELINE_LOCKED,
                ):
                    problems.append(
                        _problem(
                            "invalid_baseline_status",
                            "'baseline_status' is not an approved value",
                            column="baseline_status",
                            value=baseline_status,
                            **context,
                        )
                    )
            elif section.key == "integrations":
                problems.extend(_mediator_problems(row, context))
            elif section.key == "architecture_relationships":
                problems.extend(_relationship_problems(row, kinds, context))
            elif section.key == "solution_integrations":
                problems.extend(_association_problems(row, kinds, context))
            elif section.key == "evidence":
                problems.extend(_evidence_problems(row, context))
            problems.extend(_container_problems(section, row, context))

    problems.extend(_unique_problems(bundle, active))
    return problems


def _unique_problems(bundle: dict, active: tuple[Section, ...]) -> list[dict[str, Any]]:
    """Report records that would violate a natural key the database enforces."""
    problems: list[dict[str, Any]] = []
    for section in active:
        seen: dict[tuple[str, ...], int] = {}
        for index, row in enumerate(_dict_rows(bundle, section.key)):
            for key in section.unique:
                values = tuple(row.get(column) for column in key)
                # A NULL-free key only; an optional key is skipped when absent so
                # two records without an external identifier do not collide.
                if any(value is None for value in values):
                    continue
                if values in seen:
                    problems.append(
                        _problem(
                            "duplicate_record",
                            "'" + "', '".join(key) + "' must be unique",
                            section=section.key,
                            index=index,
                            columns=list(key),
                            value=list(values),
                            first_index=seen[values],
                        )
                    )
                    continue
                seen[values] = index
    return problems


def _container_problems(section: Section, row: dict, context: dict) -> list[dict[str, Any]]:
    """A JSON column must hold the container the format documents."""
    problems: list[dict[str, Any]] = []
    for column, container in section.expect:
        value = _read_field(row, column)
        if value is _MISSING:
            continue
        if container == "object" and not isinstance(value, dict):
            problems.append(
                _problem(
                    "invalid_field",
                    f"'{column}' must be a JSON object",
                    column=column,
                    value=type(value).__name__,
                    **context,
                )
            )
        elif container == "list" and not isinstance(value, list):
            problems.append(
                _problem(
                    "invalid_field",
                    f"'{column}' must be a JSON array",
                    column=column,
                    value=type(value).__name__,
                    **context,
                )
            )
    return problems


def _mediator_problems(row: dict, context: dict) -> list[dict[str, Any]]:
    mediator = row.get("mediator_system_id")
    if mediator is None:
        return []
    if mediator in (row.get("source_system_id"), row.get("target_system_id")):
        return [
            _problem(
                "mediator_is_endpoint",
                "A mediator cannot also be a business endpoint",
                column="mediator_system_id",
                value=mediator,
                **context,
            )
        ]
    return []


def _relationship_problems(row: dict, kinds: dict[str, str], context: dict) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    source = row.get("source_object_id")
    target = row.get("target_object_id")
    if isinstance(source, str) and source == target:
        problems.append(
            _problem(
                "self_relationship",
                "A relationship cannot connect an object to itself",
                **context,
            )
        )
    # Only Solution-to-Solution edges are constrained to the approved vocabulary;
    # enterprise/information edge types are not owned by this module.
    if kinds.get(str(source)) == SOLUTION_KIND and kinds.get(str(target)) == SOLUTION_KIND:
        relationship_type = row.get("relationship_type")
        if relationship_type not in SOLUTION_RELATIONSHIP_TYPES:
            problems.append(
                _problem(
                    "invalid_relationship_type",
                    "Unsupported Solution relationship type",
                    column="relationship_type",
                    value=relationship_type,
                    **context,
                )
            )
    return problems


def _association_problems(row: dict, kinds: dict[str, str], context: dict) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    role = row.get("role")
    if role not in ASSOCIATION_ROLES:
        problems.append(
            _problem(
                "invalid_role",
                "'role' is not an approved Solution association role",
                column="role",
                value=role,
                **context,
            )
        )
    solution_id = row.get("solution_object_id")
    if (
        isinstance(solution_id, str)
        and solution_id in kinds
        and kinds[solution_id] != SOLUTION_KIND
    ):
        problems.append(
            _problem(
                "not_a_solution_boundary",
                "A Solution association must point at a Solution Boundary",
                column="solution_object_id",
                value=solution_id,
                **context,
            )
        )
    return problems


def _evidence_problems(row: dict, context: dict) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    present = [column for column in EVIDENCE_TARGET_COLUMNS if row.get(column) is not None]
    if len(present) != 1:
        problems.append(
            _problem(
                "invalid_evidence_target",
                "Evidence must reference exactly one target",
                columns=present,
                **context,
            )
        )
    for field_name, allowed in _EVIDENCE_VOCABULARY.items():
        value = row.get(field_name)
        if value not in allowed:
            problems.append(
                _problem(
                    "invalid_vocabulary",
                    f"'{field_name}' is not an approved evidence value",
                    column=field_name,
                    value=value,
                    **context,
                )
            )
    return problems


# --- import -------------------------------------------------------------------


def _column_value(column: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as error:  # pragma: no cover - defensive
            raise BundleError(
                "invalid_timestamp", "A stored timestamp is not ISO-8601", value=value
            ) from error
    return value


def _read_field(row: dict, name: str) -> Any:
    if name in row:
        return row[name]
    for alias in LEGACY_FIELD_ALIASES.get(name, ()):
        if alias in row:
            return row[alias]
    return _MISSING


def build_id_maps(bundle: dict, version: int) -> dict[str, dict[str, UUID]]:
    """Assign every imported record a fresh id, per namespace."""
    maps: dict[str, dict[str, UUID]] = {}
    for section in _active_sections(version):
        bucket = maps.setdefault(section.namespace, {})
        for row in _dict_rows(bundle, section.key):
            value = row.get(section.id_field)
            if isinstance(value, str) and value and value not in bucket:
                bucket[value] = uuid4()
        for extra in section.also_namespaces:
            target = maps.setdefault(extra, {})
            for old_id, new_id in bucket.items():
                target.setdefault(old_id, new_id)
    return maps


def _flat_map(maps: dict[str, dict[str, UUID]]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for namespace in sorted(maps):
        for old_id, new_id in maps[namespace].items():
            existing = flat.get(old_id)
            if existing is not None and existing != str(new_id):
                raise BundleError(
                    "ambiguous_id", "One bundle id maps to two different records", value=old_id
                )
            flat[old_id] = str(new_id)
    return flat


def _resolve_user(
    db: Session, value: Any, actor_user_id: UUID | None, report: ImportReport
) -> UUID:
    candidate: UUID | None = None
    if isinstance(value, str):
        try:
            candidate = UUID(value)
        except ValueError:
            candidate = None
    if candidate is not None and db.scalar(select(User.id).where(User.id == candidate)) is not None:
        return candidate
    if actor_user_id is None:
        raise BundleError(
            "missing_evidence_provenance",
            "Evidence provenance cannot be resolved and no acting user was supplied",
            value=value,
        )
    if candidate is not None:
        report.user_substitutions.append(str(candidate))
    return actor_user_id


def _resolve_optional_user(
    db: Session, value: Any, report: ImportReport, *, section: str, column: str
) -> UUID | None:
    """Resolve nullable provenance, dropping it when the user is unavailable.

    The required evidence provenance substitutes the acting user because the
    column is NOT NULL. Lock metadata is different: claiming the importer locked
    someone else's baseline would be a false audit record, so it is cleared and
    the drop is reported.
    """
    if not value:
        return None
    try:
        candidate = UUID(str(value))
    except ValueError:
        report.dropped_user_references.append(f"{section}.{column}")
        return None
    if db.scalar(select(User.id).where(User.id == candidate)) is not None:
        return candidate
    report.dropped_user_references.append(f"{section}.{column}")
    return None


def _insert_section(
    db: Session,
    section: Section,
    rows: list[dict],
    *,
    tenant: Tenant,
    workspace: Workspace,
    maps: dict[str, dict[str, UUID]],
    flat: dict[str, str],
    actor_user_id: UUID | None,
    report: ImportReport,
) -> None:
    if not rows:
        return
    namespace = maps.get(section.namespace, {})
    columns = attribute_columns(section.model)
    payload_fields = _payload_fields(section)
    for row in _ordered_rows(section, rows):
        old_id = row.get(section.id_field)
        new_id = namespace.get(old_id)
        if new_id is None:
            continue
        instance = section.model()
        setattr(instance, section.id_field, new_id)
        if section.tenant_field:
            setattr(instance, section.tenant_field, tenant.id)
        if section.workspace_field:
            setattr(instance, section.workspace_field, workspace.id)
        for name in payload_fields:
            value = _read_field(row, name)
            if value is _MISSING:
                continue
            setattr(instance, name, _column_value(columns[name], value))
        for column, ref_namespace in section.refs:
            if column in section.defer:
                setattr(instance, column, None)
                continue
            value = row.get(column)
            if value is None:
                setattr(instance, column, None)
                continue
            target = maps.get(ref_namespace, {}).get(value)
            if target is None:
                raise BundleError(
                    "broken_reference",
                    f"'{column}' does not resolve to a {ref_namespace} record",
                    section=section.key,
                    column=column,
                    value=value,
                )
            setattr(instance, column, target)
        for name in section.json_refs:
            value = _read_field(row, name)
            if value is _MISSING:
                continue
            remapped = _remap_uuids_in_json(value, flat) if value is not None else None
            setattr(instance, name, remapped)
        for name in section.user_refs:
            setattr(instance, name, _resolve_user(db, row.get(name), actor_user_id, report))
        for name in section.optional_user_refs:
            setattr(
                instance,
                name,
                _resolve_optional_user(db, row.get(name), report, section=section.key, column=name),
            )
        db.add(instance)
    db.flush()


def _apply_deferred_refs(
    db: Session,
    bundle: dict,
    version: int,
    maps: dict[str, dict[str, UUID]],
) -> None:
    """Patch references whose target section is imported after their own."""
    for section in _active_sections(version):
        if not section.defer:
            continue
        namespace = maps.get(section.namespace, {})
        ref_namespaces = dict(section.refs)
        for row in _dict_rows(bundle, section.key):
            new_id = namespace.get(row.get(section.id_field))
            if new_id is None:
                continue
            instance = db.get(section.model, new_id)
            if instance is None:  # pragma: no cover - defensive
                continue
            for column in section.defer:
                value = row.get(column)
                if value is None:
                    continue
                target = maps.get(ref_namespaces[column], {}).get(value)
                if target is None:
                    raise BundleError(
                        "broken_reference",
                        f"'{column}' does not resolve to a "
                        f"{ref_namespaces[column]} record",
                        section=section.key,
                        column=column,
                        value=value,
                    )
                setattr(instance, column, target)
    db.flush()


def _backfill_baseline_status(
    db: Session,
    bundle: dict,
    version: int,
    maps: dict[str, dict[str, UUID]],
    report: ImportReport,
) -> None:
    """A bundled Current state without a baseline status imports as locked.

    Bundles written before the baseline lifecycle existed carry Current content
    that was read-only, so the safe reading of "no status" is ``locked``. An
    explicit status always wins, and Candidate/Target states are untouched.
    """
    section = SECTION_BY_KEY["states"]
    namespace = maps.get(section.namespace, {})
    for row in _dict_rows(bundle, section.key):
        if row.get("state_type") != "current":
            continue
        if row.get("baseline_status") in ("draft", "locked"):
            continue
        instance = db.get(ArchitectureState, namespace.get(row.get("id")))
        if instance is None:  # pragma: no cover - defensive
            continue
        instance.baseline_status = BASELINE_LOCKED
        report.baseline_backfills.append(str(instance.id))
    db.flush()


def import_workspace_bundle(
    db: Session,
    tenant: Tenant,
    bundle: dict,
    *,
    actor_user_id: UUID | None = None,
    report: ImportReport | None = None,
) -> Workspace:
    """Re-create a bundle inside ``tenant``. One transaction, all-or-nothing.

    The caller owns the transaction: the importer never commits, and any
    exception leaves the session dirty so the caller can roll the whole import
    back.
    """
    problems = validate_bundle(bundle)
    if problems:
        first = problems[0]
        raise BundleError(
            "invalid_bundle",
            first["message"],
            problems=problems[:20],
            problem_count=len(problems),
        )

    version = _version(bundle)
    active_report = report if report is not None else ImportReport()
    active_report.source_version = version

    workspace_info = bundle.get("workspace") or {}
    disciplines = workspace_info.get("disciplines") or list(DEFAULT_DISCIPLINES)
    workspace = Workspace(
        id=tenant.id,
        tenant_id=tenant.id,
        name=tenant.name,
        description=tenant.description,
        disciplines=list(disciplines),
    )
    db.add(workspace)
    db.flush()

    maps = build_id_maps(bundle, version)
    flat = _flat_map(maps)
    system_ids = maps.get("system", {})

    for section in _active_sections(version):
        rows = _dict_rows(bundle, section.key)
        if section.key == "architecture_objects":
            # CatalogSystem inserts create their own registry row; skipping the
            # exported copy avoids a duplicate and keeps the ids aligned.
            rows = [row for row in rows if row.get("id") not in system_ids]
        _insert_section(
            db,
            section,
            rows,
            tenant=tenant,
            workspace=workspace,
            maps=maps,
            flat=flat,
            actor_user_id=actor_user_id,
            report=active_report,
        )

    _apply_deferred_refs(db, bundle, version, maps)
    _backfill_baseline_status(db, bundle, version, maps, active_report)

    if active_report.user_substitutions:
        logger.warning(
            "Workspace import substituted %d unresolvable evidence provenance user(s): %s",
            len(active_report.user_substitutions),
            ", ".join(sorted(set(active_report.user_substitutions))),
        )
    return workspace


# --- fork ---------------------------------------------------------------------


def fork_workspace(
    db: Session,
    source_tenant_id: UUID,
    new_tenant: Tenant,
    *,
    disciplines: list[str] | None = None,
    actor_user_id: UUID | None = None,
    report: ImportReport | None = None,
) -> Workspace:
    """Deep-copy a workspace. Implemented as export + import, by construction."""
    bundle = export_workspace_bundle(db, source_tenant_id)
    if disciplines is not None:
        bundle["workspace"]["disciplines"] = list(disciplines)
    return import_workspace_bundle(
        db, new_tenant, bundle, actor_user_id=actor_user_id, report=report
    )
