"""Guided architecture import: matching, validation, commit, and undo.

The backend is authoritative for validation, matching, and decisions. Imported
records reuse the existing canonical models, so imported systems register as
shared architecture objects and imported solutions reference canonical systems
instead of creating copies.
"""

from __future__ import annotations

import difflib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.architecture.state_scope import (
    assert_contract_editable_for_tenant,
    locked_baseline_anchors_contract,
)
from app.imports.schemas import (
    MAX_METADATA_BYTES,
    ImportCommitRequest,
    ImportIssue,
    ImportMatchCandidate,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportRowPreview,
    ImportRowResult,
    ImportType,
    RowDecision,
)
from app.models import (
    ArchitectureObject,
    ArchitectureState,
    CatalogObject,
    CatalogSystem,
    ImportBatch,
    InformationObject,
    Integration,
    SolutionBoundary,
    SolutionMember,
    Workspace,
)
from app.models import (
    ImportRowResult as ImportRowResultModel,
)

SIMILARITY_THRESHOLD = 0.90
MULTI_VALUE_SEPARATOR = ";"
INTERACTION_TYPE_ALIASES = {
    "one_way": "ONE_WAY",
    "oneway": "ONE_WAY",
    "one way": "ONE_WAY",
    "push": "ONE_WAY",
    "request_response": "REQUEST_RESPONSE",
    "requestresponse": "REQUEST_RESPONSE",
    "request response": "REQUEST_RESPONSE",
    "sync": "REQUEST_RESPONSE",
    "synchronous": "REQUEST_RESPONSE",
    "async_callback": "ASYNC_CALLBACK",
    "asynccallback": "ASYNC_CALLBACK",
    "async callback": "ASYNC_CALLBACK",
    "async": "ASYNC_CALLBACK",
    "callback": "ASYNC_CALLBACK",
}
SYSTEM_METADATA_KEYS = ("owner", "business_domain", "lifecycle", "status", "technology")
KIND_BY_IMPORT_TYPE = {
    "system": "system",
    "information_object": "information_object",
    "integration": "integration",
    "solution": "solution_boundary",
}
KIND_LABELS = {
    "system": "system",
    "information_object": "information object",
    "integration": "contract",
    "solution_boundary": "solution",
}
COUNT_KEYS = ("created", "updated", "matched", "skipped", "blocked", "failed")


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    multiple: bool = False


FIELD_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "system": (
        FieldSpec("name", "Name", required=True, aliases=("system", "system name", "application")),
        FieldSpec("description", "Description", aliases=("purpose",)),
        FieldSpec("owner", "Owner", aliases=("system owner",)),
        FieldSpec("business_domain", "Business domain", aliases=("domain", "business area")),
        FieldSpec("lifecycle", "Lifecycle", aliases=("life cycle",)),
        FieldSpec("status", "Status"),
        FieldSpec("technology", "Technology", aliases=("platform", "tech")),
        FieldSpec("external_id", "External ID", aliases=("external id", "externalid", "source id")),
        FieldSpec("aliases", "Aliases", aliases=("alias", "alternative names"), multiple=True),
    ),
    "information_object": (
        FieldSpec("name", "Name", required=True, aliases=("information object", "object")),
        FieldSpec("description", "Description"),
        FieldSpec("owner", "Owner", required=True, aliases=("data owner",)),
        FieldSpec(
            "authoritative_system",
            "Authoritative system",
            required=True,
            aliases=("authoritative system name", "system of record"),
        ),
        FieldSpec(
            "classification", "Classification", aliases=("data classification", "sensitivity")
        ),
        FieldSpec("external_id", "External ID", aliases=("external id", "externalid")),
    ),
    "integration": (
        FieldSpec("name", "Name", required=True, aliases=("integration", "interface", "contract")),
        FieldSpec("description", "Description or purpose", aliases=("purpose",)),
        FieldSpec(
            "source_system", "Source system", required=True, aliases=("source", "from system")
        ),
        FieldSpec("target_system", "Target system", required=True, aliases=("target", "to system")),
        FieldSpec("source_object", "Source object", aliases=("source object name", "from object")),
        FieldSpec("target_object", "Target object", aliases=("target object name", "to object")),
        FieldSpec(
            "integration_type",
            "Integration type",
            aliases=("type", "interaction type", "pattern"),
        ),
        FieldSpec("owner", "Owner"),
        FieldSpec("lifecycle", "Lifecycle", aliases=("life cycle",)),
        FieldSpec("external_id", "External ID", aliases=("external id", "externalid")),
        FieldSpec(
            "contract_reference",
            "Existing contract reference",
            aliases=("contract", "existing contract", "contract name"),
        ),
    ),
    "solution": (
        FieldSpec("name", "Solution name", required=True, aliases=("solution",)),
        FieldSpec("description", "Description"),
        FieldSpec("owner", "Owner", aliases=("solution owner",)),
        FieldSpec("external_id", "External ID", aliases=("external id", "externalid")),
        FieldSpec(
            "included_systems",
            "Included systems",
            required=True,
            aliases=("systems", "member systems", "system membership", "includes"),
            multiple=True,
        ),
    ),
}


def normalize_name(value: str) -> str:
    """NFKC-normalize, trim, collapse whitespace, and casefold a display name."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _normalized_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts: list[str] = []
    for part in value.replace("\n", MULTI_VALUE_SEPARATOR).split(MULTI_VALUE_SEPARATOR):
        cleaned = part.strip()
        if cleaned:
            parts.append(cleaned)
    return parts


def _metadata_size(metadata: dict[str, Any]) -> int:
    return len(json.dumps(metadata, separators=(",", ":")).encode("utf-8"))


@dataclass
class KindIndex:
    kind: str
    by_external_id: dict[str, tuple[UUID, str]]
    by_name: dict[str, tuple[UUID, str]]
    by_alias: dict[str, tuple[UUID, str]]
    all_names: list[tuple[str, UUID, str]] = field(default_factory=list)


@dataclass
class PreparedRow:
    row_number: int
    values: dict[str, str]
    external_id: str | None
    name: str | None
    issues: list[ImportIssue] = field(default_factory=list)
    warnings: list[ImportIssue] = field(default_factory=list)
    matches: list[ImportMatchCandidate] = field(default_factory=list)
    suggested_decision: RowDecision = "create"
    resolved: dict[str, Any] = field(default_factory=dict)


def _active_systems(db: Session, tenant_id: UUID) -> list[CatalogSystem]:
    return list(
        db.scalars(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
    )


def build_index(db: Session, tenant_id: UUID, import_type: ImportType) -> KindIndex:
    """Index the canonical records an import row can match against."""

    index = KindIndex(
        kind=KIND_BY_IMPORT_TYPE[import_type],
        by_external_id={},
        by_name={},
        by_alias={},
    )

    def add(
        record_id: UUID,
        name: str,
        external_identifier: str | None,
        aliases: list[str] | None = None,
    ):
        index.by_name.setdefault(normalize_name(name), (record_id, name))
        index.all_names.append((normalize_name(name), record_id, name))
        if external_identifier:
            index.by_external_id.setdefault(_normalized_key(external_identifier), (record_id, name))
        for alias in aliases or []:
            index.by_alias.setdefault(normalize_name(alias), (record_id, name))

    if import_type == "system":
        for system in _active_systems(db, tenant_id):
            metadata = system.extra_metadata or {}
            raw_aliases = metadata.get("aliases")
            aliases = [str(alias) for alias in raw_aliases] if isinstance(raw_aliases, list) else []
            add(system.id, system.name, system.external_identifier, aliases)
    elif import_type == "information_object":
        rows = db.scalars(select(InformationObject).where(InformationObject.tenant_id == tenant_id))
        for row in rows:
            add(row.object_id, row.name, row.external_identifier)
    elif import_type == "integration":
        rows = db.scalars(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.deleted_at.is_(None),
            )
        )
        for row in rows:
            add(row.id, row.name, row.external_identifier)
    else:
        rows = db.scalars(select(SolutionBoundary).where(SolutionBoundary.tenant_id == tenant_id))
        for row in rows:
            add(row.object_id, row.name, row.external_identifier)
    return index


def resolve_system(index: KindIndex, token: str) -> tuple[UUID, str] | None:
    """Resolve a system reference by external ID, exact name, then alias."""

    key = _normalized_key(token)
    if key in index.by_external_id:
        return index.by_external_id[key]
    normalized = normalize_name(token)
    if normalized in index.by_name:
        return index.by_name[normalized]
    if normalized in index.by_alias:
        return index.by_alias[normalized]
    return None


def match_row(
    index: KindIndex,
    row_number: int,
    name: str | None,
    external_id: str | None,
) -> tuple[list[ImportMatchCandidate], list[ImportIssue]]:
    """Layered matching: external ID, exact name, alias, then similar-name suggestion."""

    if external_id:
        hit = index.by_external_id.get(_normalized_key(external_id))
        if hit:
            return [
                ImportMatchCandidate(id=hit[0], kind=index.kind, name=hit[1], method="external_id")
            ], []
    if not name:
        return [], []
    normalized = normalize_name(name)
    hit = index.by_name.get(normalized)
    if hit:
        return [
            ImportMatchCandidate(id=hit[0], kind=index.kind, name=hit[1], method="exact_name")
        ], []
    hit = index.by_alias.get(normalized)
    if hit:
        return [ImportMatchCandidate(id=hit[0], kind=index.kind, name=hit[1], method="alias")], []

    best: tuple[float, UUID, str] | None = None
    for candidate_normalized, candidate_id, candidate_name in index.all_names:
        ratio = difflib.SequenceMatcher(None, normalized, candidate_normalized).ratio()
        if ratio >= SIMILARITY_THRESHOLD and (best is None or ratio > best[0]):
            best = (ratio, candidate_id, candidate_name)
    if best is None:
        return [], []
    ratio, candidate_id, candidate_name = best
    candidate = ImportMatchCandidate(
        id=candidate_id,
        kind=index.kind,
        name=candidate_name,
        method="similar_name",
        score=round(ratio, 4),
    )
    warning = ImportIssue(
        row=row_number,
        column="name",
        message=(
            f"Similar existing {KIND_LABELS[index.kind]} '{candidate_name}' "
            "matched by name similarity only. Confirm before updating; "
            "nothing is merged automatically."
        ),
    )
    return [candidate], [warning]


def _first_issue(row: PreparedRow) -> ImportIssue | None:
    return row.issues[0] if row.issues else None


def _field_map(import_type: ImportType) -> dict[str, FieldSpec]:
    return {spec.key: spec for spec in FIELD_SPECS[import_type]}


def _validate_mapping(payload: ImportPreviewRequest) -> dict[str, FieldSpec]:
    specs = _field_map(payload.import_type)
    unknown = sorted(key for key in payload.column_mapping if key not in specs)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Unknown import field(s): "
                + ", ".join(unknown)
                + ". Allowed fields: "
                + ", ".join(specs)
            ),
        )
    missing_required = sorted(
        key for key, spec in specs.items() if spec.required and key not in payload.column_mapping
    )
    if missing_required:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Required field(s) are not mapped to a source column: "
                + ", ".join(missing_required)
            ),
        )
    header_lookup = {
        header.strip().casefold(): index for index, header in enumerate(payload.headers)
    }
    for key, header in payload.column_mapping.items():
        if header.strip().casefold() not in header_lookup:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Mapped column '{header}' for field '{key}' is not present in the file",
            )
    return specs


def _row_values(payload: ImportPreviewRequest, row: list[str]) -> dict[str, str]:
    header_lookup = {
        header.strip().casefold(): index for index, header in enumerate(payload.headers)
    }
    values: dict[str, str] = {}
    for key, header in payload.column_mapping.items():
        index = header_lookup.get(header.strip().casefold())
        cell = row[index] if index is not None and index < len(row) else ""
        values[key] = (cell or "").strip()
    return values


def _map_interaction_type(raw: str) -> str | None:
    normalized = normalize_name(raw)
    candidates = (
        normalized,
        normalized.replace("-", "_"),
        normalized.replace(" ", "_"),
        normalized.replace("-", " "),
    )
    for candidate in candidates:
        if candidate in INTERACTION_TYPE_ALIASES:
            return INTERACTION_TYPE_ALIASES[candidate]
    return None


def _prepare_system(db: Session, workspace: Workspace, row: PreparedRow) -> None:
    name = _clean(row.values.get("name"))
    if not name:
        row.issues.append(
            ImportIssue(row=row.row_number, column="name", message="Name is required")
        )
        return
    metadata: dict[str, Any] = {}
    for key in SYSTEM_METADATA_KEYS:
        value = _clean(row.values.get(key))
        if value:
            metadata[key] = value
    aliases = _parse_list(row.values.get("aliases"))
    if aliases:
        metadata["aliases"] = aliases
    if _metadata_size(metadata) > MAX_METADATA_BYTES:
        row.issues.append(
            ImportIssue(
                row=row.row_number, column="aliases", message="Imported metadata exceeds 16 KiB"
            )
        )
        return
    row.resolved["metadata"] = metadata
    row.resolved["description"] = _clean(row.values.get("description"))
    row.resolved["external_identifier"] = _clean(row.values.get("external_id"))


def _prepare_information_object(
    db: Session, workspace: Workspace, row: PreparedRow, system_index: KindIndex
) -> None:
    name = _clean(row.values.get("name"))
    owner = _clean(row.values.get("owner"))
    if not name:
        row.issues.append(
            ImportIssue(row=row.row_number, column="name", message="Name is required")
        )
    if not owner:
        row.issues.append(
            ImportIssue(row=row.row_number, column="owner", message="Owner is required")
        )
    authoritative = _clean(row.values.get("authoritative_system"))
    if not authoritative:
        row.issues.append(
            ImportIssue(
                row=row.row_number,
                column="authoritative_system",
                message="An authoritative system is required",
            )
        )
    else:
        resolved = resolve_system(system_index, authoritative)
        if resolved is None:
            row.issues.append(
                ImportIssue(
                    row=row.row_number,
                    column="authoritative_system",
                    message=(
                        f"Authoritative system '{authoritative}' "
                        "does not match a catalog system"
                    ),
                )
            )
        else:
            row.resolved["authoritative_system_id"] = resolved[0]
            row.resolved["authoritative_system_name"] = resolved[1]
    row.resolved["description"] = _clean(row.values.get("description"))
    row.resolved["owner"] = owner
    row.resolved["classification"] = _clean(row.values.get("classification"))
    row.resolved["external_identifier"] = _clean(row.values.get("external_id"))


def _system_objects(db: Session, tenant_id: UUID, system_id: UUID) -> list[CatalogObject]:
    return list(
        db.scalars(
            select(CatalogObject).where(
                CatalogObject.tenant_id == tenant_id,
                CatalogObject.system_id == system_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
    )


def _resolve_endpoint_object(
    db: Session,
    tenant_id: UUID,
    system_id: UUID,
    system_name: str,
    explicit_name: str | None,
    role: str,
) -> tuple[UUID | None, str | None]:
    """Resolve an integration endpoint object without creating catalog objects."""

    objects = _system_objects(db, tenant_id, system_id)
    if explicit_name:
        wanted = normalize_name(explicit_name)
        for obj in objects:
            if normalize_name(obj.name) == wanted or normalize_name(obj.label) == wanted:
                return obj.id, None
        return None, f"{role} object '{explicit_name}' does not exist in system '{system_name}'"
    if len(objects) == 1:
        return objects[0].id, None
    if not objects:
        return None, (
            f"{role} system '{system_name}' has no catalog object. "
            f"Add a {role.lower()} object column or create the object first"
        )
    return None, (
        f"{role} system '{system_name}' has {len(objects)} objects. "
        f"Provide a {role.lower()} object column to choose one"
    )


def _integration_baseline_issue(
    db: Session, workspace: Workspace, row: PreparedRow
) -> ImportIssue | None:
    """The row updates a Contract that a locked Current baseline protects."""
    target = row.matches[0] if row.matches else None
    if target is None or target.kind != "integration":
        return None
    if not locked_baseline_anchors_contract(db, workspace.tenant_id, target.id):
        return None
    return ImportIssue(
        row=row.row_number,
        column="name",
        message=(
            "This contract is part of the locked Current baseline, so an import "
            "cannot change it. Change it in a Candidate state instead."
        ),
    )


def _prepare_integration(
    db: Session,
    workspace: Workspace,
    row: PreparedRow,
    system_index: KindIndex,
    integration_index: KindIndex,
) -> None:
    name = _clean(row.values.get("name"))
    if not name:
        row.issues.append(
            ImportIssue(row=row.row_number, column="name", message="Name is required")
        )

    resolved_systems: dict[str, tuple[UUID, str]] = {}
    for key, label in (("source_system", "Source"), ("target_system", "Target")):
        token = _clean(row.values.get(key))
        if not token:
            row.issues.append(
                ImportIssue(row=row.row_number, column=key, message=f"{label} system is required")
            )
            continue
        resolved = resolve_system(system_index, token)
        if resolved is None:
            row.issues.append(
                ImportIssue(
                    row=row.row_number,
                    column=key,
                    message=f"{label} system '{token}' does not match a catalog system",
                )
            )
            continue
        resolved_systems[key] = resolved

    raw_type = _clean(row.values.get("integration_type"))
    if raw_type:
        mapped_type = _map_interaction_type(raw_type)
        if mapped_type is None:
            row.issues.append(
                ImportIssue(
                    row=row.row_number,
                    column="integration_type",
                    message=(
                        f"Integration type '{raw_type}' is not recognized. Use one of "
                        "ONE_WAY, REQUEST_RESPONSE, or ASYNC_CALLBACK"
                    ),
                )
            )
        else:
            row.resolved["interaction_type"] = mapped_type
    row.resolved.setdefault("interaction_type", "ONE_WAY")

    contract_reference = _clean(row.values.get("contract_reference"))
    if contract_reference:
        hit = integration_index.by_external_id.get(_normalized_key(contract_reference)) or (
            integration_index.by_name.get(normalize_name(contract_reference))
        )
        if hit is None:
            row.issues.append(
                ImportIssue(
                    row=row.row_number,
                    column="contract_reference",
                    message=f"Existing contract '{contract_reference}' was not found",
                )
            )
        else:
            row.resolved["contract_id"] = hit[0]
            row.resolved["contract_name"] = hit[1]
            if not row.matches:
                row.matches.append(
                    ImportMatchCandidate(
                        id=hit[0], kind="integration", name=hit[1], method="exact_name"
                    )
                )

    if "source_system" in resolved_systems:
        source_system_id, source_system_name = resolved_systems["source_system"]
        object_id, error = _resolve_endpoint_object(
            db,
            workspace.tenant_id,
            source_system_id,
            source_system_name,
            _clean(row.values.get("source_object")),
            "Source",
        )
        if error:
            row.issues.append(
                ImportIssue(row=row.row_number, column="source_system", message=error)
            )
        else:
            row.resolved["source_system_id"] = source_system_id
            row.resolved["source_object_id"] = object_id
    if "target_system" in resolved_systems:
        target_system_id, target_system_name = resolved_systems["target_system"]
        object_id, error = _resolve_endpoint_object(
            db,
            workspace.tenant_id,
            target_system_id,
            target_system_name,
            _clean(row.values.get("target_object")),
            "Target",
        )
        if error:
            row.issues.append(
                ImportIssue(row=row.row_number, column="target_system", message=error)
            )
        else:
            row.resolved["target_system_id"] = target_system_id
            row.resolved["target_object_id"] = object_id

    metadata: dict[str, Any] = {}
    for key in ("owner", "lifecycle"):
        value = _clean(row.values.get(key))
        if value:
            metadata[key] = value
    row.resolved["metadata"] = metadata
    row.resolved["description"] = _clean(row.values.get("description"))
    row.resolved["external_identifier"] = _clean(row.values.get("external_id"))


    baseline_issue = _integration_baseline_issue(db, workspace, row)
    if baseline_issue is not None:
        row.issues.append(baseline_issue)


def _prepare_solution(
    db: Session, workspace: Workspace, row: PreparedRow, system_index: KindIndex
) -> None:
    name = _clean(row.values.get("name"))
    if not name:
        row.issues.append(
            ImportIssue(row=row.row_number, column="name", message="Name is required")
        )
    tokens = _parse_list(row.values.get("included_systems"))
    if not tokens:
        row.issues.append(
            ImportIssue(
                row=row.row_number,
                column="included_systems",
                message="At least one included system is required",
            )
        )
    member_ids: list[UUID] = []
    unresolved: list[str] = []
    for token in tokens:
        resolved = resolve_system(system_index, token)
        if resolved is None:
            unresolved.append(token)
        elif resolved[0] not in member_ids:
            member_ids.append(resolved[0])
    if unresolved:
        row.issues.append(
            ImportIssue(
                row=row.row_number,
                column="included_systems",
                message=("Included system(s) do not match the catalog: " + ", ".join(unresolved)),
            )
        )
    row.resolved["member_system_ids"] = member_ids
    row.resolved["description"] = _clean(row.values.get("description"))
    row.resolved["owner"] = _clean(row.values.get("owner"))
    row.resolved["external_identifier"] = _clean(row.values.get("external_id"))


def prepare_rows(
    db: Session, workspace: Workspace, payload: ImportPreviewRequest
) -> list[PreparedRow]:
    """Validate and match every row without writing anything."""

    _validate_mapping(payload)
    index = build_index(db, workspace.tenant_id, payload.import_type)
    system_index = (
        index if payload.import_type == "system" else build_index(db, workspace.tenant_id, "system")
    )
    integration_index = (
        index
        if payload.import_type == "integration"
        else build_index(db, workspace.tenant_id, "integration")
    )

    prepared: list[PreparedRow] = []
    for offset, raw_row in enumerate(payload.rows):
        row_number = offset + 1
        values = _row_values(payload, raw_row)
        row = PreparedRow(
            row_number=row_number,
            values=values,
            external_id=_clean(values.get("external_id")),
            name=_clean(values.get("name")),
        )
        if not any(value for value in values.values()):
            prepared.append(row)
            continue
        row.matches, row.warnings = match_row(index, row_number, row.name, row.external_id)
        if payload.import_type == "system":
            _prepare_system(db, workspace, row)
        elif payload.import_type == "information_object":
            _prepare_information_object(db, workspace, row, system_index)
        elif payload.import_type == "integration":
            _prepare_integration(db, workspace, row, system_index, integration_index)
        else:
            _prepare_solution(db, workspace, row, system_index)
        if row.matches and row.matches[0].method != "similar_name":
            row.suggested_decision = "use_existing"
        prepared.append(row)
    return prepared


def _integrity_message(error: Exception) -> str:
    text = str(getattr(error, "orig", error)).lower()
    if "uq_systems_active_name" in text or "uq_integrations_active_name" in text:
        return "Another active record already uses this name"
    if "external_id" in text:
        return "Another active record already uses this external ID"
    if "uq_solution_members_pair" in text:
        return "This system is already a member of the solution"
    return "The change conflicts with an existing record"


def _create_record(
    db: Session, workspace: Workspace, import_type: ImportType, row: PreparedRow
) -> tuple[UUID, dict]:
    tenant_id = workspace.tenant_id
    if import_type == "system":
        system = CatalogSystem(
            tenant_id=tenant_id,
            name=row.name,
            description=row.resolved.get("description"),
            kind="application",
            external_identifier=row.resolved.get("external_identifier"),
            extra_metadata=dict(row.resolved.get("metadata") or {}),
        )
        db.add(system)
        db.flush()
        return system.id, _system_snapshot(system)
    if import_type == "information_object":
        object_id = uuid4()
        db.add(ArchitectureObject(id=object_id, tenant_id=tenant_id, kind="information_object"))
        db.add(
            InformationObject(
                object_id=object_id,
                tenant_id=tenant_id,
                name=row.name,
                description=row.resolved.get("description"),
                owner=row.resolved.get("owner") or "",
                authoritative_system_id=row.resolved["authoritative_system_id"],
                external_identifier=row.resolved.get("external_identifier"),
                classification=row.resolved.get("classification"),
            )
        )
        db.flush()
        return object_id, {
            "name": row.name,
            "description": row.resolved.get("description"),
            "owner": row.resolved.get("owner"),
            "authoritative_system_id": str(row.resolved["authoritative_system_id"]),
            "classification": row.resolved.get("classification"),
            "external_identifier": row.resolved.get("external_identifier"),
        }
    if import_type == "integration":
        integration = Integration(
            tenant_id=tenant_id,
            name=row.name,
            description=row.resolved.get("description"),
            source_system_id=row.resolved["source_system_id"],
            source_object_id=row.resolved["source_object_id"],
            target_system_id=row.resolved["target_system_id"],
            target_object_id=row.resolved["target_object_id"],
            interaction_type=row.resolved.get("interaction_type", "ONE_WAY"),
            external_identifier=row.resolved.get("external_identifier"),
            extra_metadata=dict(row.resolved.get("metadata") or {}),
        )
        db.add(integration)
        db.flush()
        return integration.id, _integration_snapshot(integration)
    object_id = uuid4()
    db.add(ArchitectureObject(id=object_id, tenant_id=tenant_id, kind="solution_boundary"))
    db.add(
        SolutionBoundary(
            object_id=object_id,
            tenant_id=tenant_id,
            name=row.name,
            description=row.resolved.get("description"),
            owner=row.resolved.get("owner"),
            external_identifier=row.resolved.get("external_identifier"),
        )
    )
    for system_id in row.resolved.get("member_system_ids") or []:
        db.add(
            SolutionMember(tenant_id=tenant_id, solution_object_id=object_id, system_id=system_id)
        )
    db.flush()
    return object_id, {
        "name": row.name,
        "description": row.resolved.get("description"),
        "owner": row.resolved.get("owner"),
        "external_identifier": row.resolved.get("external_identifier"),
        "member_system_ids": [str(item) for item in row.resolved.get("member_system_ids") or []],
    }


def _system_snapshot(system: CatalogSystem) -> dict:
    return {
        "name": system.name,
        "description": system.description,
        "external_identifier": system.external_identifier,
        "metadata": dict(system.extra_metadata or {}),
    }


def _integration_snapshot(integration: Integration) -> dict:
    return {
        "name": integration.name,
        "description": integration.description,
        "interaction_type": integration.interaction_type,
        "external_identifier": integration.external_identifier,
        "metadata": dict(integration.extra_metadata or {}),
    }


def _information_object_snapshot(record: InformationObject) -> dict:
    return {
        "name": record.name,
        "description": record.description,
        "owner": record.owner,
        "authoritative_system_id": str(record.authoritative_system_id),
        "classification": record.classification,
        "external_identifier": record.external_identifier,
    }


def _solution_members(db: Session, tenant_id: UUID, object_id: UUID) -> list[UUID]:
    return list(
        db.scalars(
            select(SolutionMember.system_id).where(
                SolutionMember.tenant_id == tenant_id,
                SolutionMember.solution_object_id == object_id,
            )
        )
    )


def _solution_snapshot(db: Session, boundary: SolutionBoundary) -> dict:
    return {
        "name": boundary.name,
        "description": boundary.description,
        "owner": boundary.owner,
        "external_identifier": boundary.external_identifier,
        "member_system_ids": [
            str(item) for item in _solution_members(db, boundary.tenant_id, boundary.object_id)
        ],
    }


def _set_field(
    before: dict, after: dict, obj: Any, attr: str, value: Any, key: str | None = None
) -> None:
    name = key or attr
    before[name] = _jsonable(getattr(obj, attr))
    setattr(obj, attr, value)
    after[name] = _jsonable(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _update_system(db: Session, target_id: UUID, row: PreparedRow, tenant_id: UUID):
    system = db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.id == target_id,
            CatalogSystem.tenant_id == tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    )
    if system is None:
        return None, None
    before: dict = {}
    after: dict = {}
    if row.name:
        _set_field(before, after, system, "name", row.name)
    if row.values.get("description"):
        _set_field(before, after, system, "description", row.resolved.get("description"))
    if row.values.get("external_id"):
        _set_field(
            before, after, system, "external_identifier", row.resolved.get("external_identifier")
        )
    metadata = dict(system.extra_metadata or {})
    updated = dict(metadata)
    changed = False
    for key in SYSTEM_METADATA_KEYS:
        if row.values.get(key):
            updated[key] = row.values[key]
            changed = True
    if row.values.get("aliases"):
        updated["aliases"] = _parse_list(row.values["aliases"])
        changed = True
    if changed:
        _set_field(before, after, system, "extra_metadata", updated, key="metadata")
    system.updated_at = datetime.now(UTC)
    return before, after


def _update_information_object(db: Session, target_id: UUID, row: PreparedRow, tenant_id: UUID):
    record = db.scalar(
        select(InformationObject).where(
            InformationObject.object_id == target_id,
            InformationObject.tenant_id == tenant_id,
        )
    )
    if record is None:
        return None, None
    before: dict = {}
    after: dict = {}
    if row.name:
        _set_field(before, after, record, "name", row.name)
    if row.values.get("description"):
        _set_field(before, after, record, "description", row.resolved.get("description"))
    if row.values.get("owner"):
        _set_field(before, after, record, "owner", row.resolved.get("owner"))
    if row.values.get("classification"):
        _set_field(before, after, record, "classification", row.resolved.get("classification"))
    if row.values.get("external_id"):
        _set_field(
            before, after, record, "external_identifier", row.resolved.get("external_identifier")
        )
    if row.values.get("authoritative_system"):
        _set_field(
            before,
            after,
            record,
            "authoritative_system_id",
            row.resolved["authoritative_system_id"],
        )
    return before, after


def _update_integration(db: Session, target_id: UUID, row: PreparedRow, tenant_id: UUID):
    integration = db.scalar(
        select(Integration).where(
            Integration.id == target_id,
            Integration.tenant_id == tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    if integration is None:
        return None, None
    assert_contract_editable_for_tenant(db, tenant_id, integration)
    before: dict = {}
    after: dict = {}
    if row.name:
        _set_field(before, after, integration, "name", row.name)
    if row.values.get("description"):
        _set_field(before, after, integration, "description", row.resolved.get("description"))
    if row.values.get("integration_type"):
        _set_field(
            before,
            after,
            integration,
            "interaction_type",
            row.resolved.get("interaction_type", "ONE_WAY"),
        )
    if row.values.get("external_id"):
        _set_field(
            before,
            after,
            integration,
            "external_identifier",
            row.resolved.get("external_identifier"),
        )
    metadata = dict(integration.extra_metadata or {})
    updated = dict(metadata)
    changed = False
    for key in ("owner", "lifecycle"):
        if row.values.get(key):
            updated[key] = row.values[key]
            changed = True
    if changed:
        _set_field(before, after, integration, "extra_metadata", updated, key="metadata")
    integration.updated_at = datetime.now(UTC)
    return before, after


def _update_solution(db: Session, target_id: UUID, row: PreparedRow, tenant_id: UUID):
    boundary = db.scalar(
        select(SolutionBoundary).where(
            SolutionBoundary.object_id == target_id,
            SolutionBoundary.tenant_id == tenant_id,
        )
    )
    if boundary is None:
        return None, None
    before: dict = {}
    after: dict = {}
    if row.name:
        _set_field(before, after, boundary, "name", row.name)
    if row.values.get("description"):
        _set_field(before, after, boundary, "description", row.resolved.get("description"))
    if row.values.get("owner"):
        _set_field(before, after, boundary, "owner", row.resolved.get("owner"))
    if row.values.get("external_id"):
        _set_field(
            before, after, boundary, "external_identifier", row.resolved.get("external_identifier")
        )
    if row.values.get("included_systems"):
        current = set(_solution_members(db, tenant_id, target_id))
        desired = set(row.resolved.get("member_system_ids") or [])
        if current != desired:
            before["member_system_ids"] = sorted(str(item) for item in current)
            for removed in current - desired:
                member = db.scalar(
                    select(SolutionMember).where(
                        SolutionMember.tenant_id == tenant_id,
                        SolutionMember.solution_object_id == target_id,
                        SolutionMember.system_id == removed,
                    )
                )
                if member is not None:
                    db.delete(member)
            for added in desired - current:
                db.add(
                    SolutionMember(
                        tenant_id=tenant_id,
                        solution_object_id=target_id,
                        system_id=added,
                    )
                )
            db.flush()
            after["member_system_ids"] = sorted(str(item) for item in desired)
    return before, after


def _update_record(
    db: Session, tenant_id: UUID, import_type: ImportType, target_id: UUID, row: PreparedRow
):
    if import_type == "system":
        return _update_system(db, target_id, row, tenant_id)
    if import_type == "information_object":
        return _update_information_object(db, target_id, row, tenant_id)
    if import_type == "integration":
        return _update_integration(db, target_id, row, tenant_id)
    return _update_solution(db, target_id, row, tenant_id)


def _apply_row(
    db: Session,
    workspace: Workspace,
    import_type: ImportType,
    row: PreparedRow,
    action: RowDecision,
    target_id: UUID | None,
) -> tuple[ImportRowResult, dict | None, dict | None]:
    kind = KIND_BY_IMPORT_TYPE[import_type]
    if action == "skip":
        return (
            ImportRowResult(
                row_number=row.row_number, status="skipped", target_kind=kind, message="Skipped."
            ),
            None,
            None,
        )
    if row.issues:
        issue = _first_issue(row)
        return (
            ImportRowResult(
                row_number=row.row_number,
                status="blocked",
                target_kind=kind,
                message=issue.message if issue else "This row is not valid.",
                issues=row.issues,
            ),
            None,
            None,
        )
    if action == "use_existing":
        chosen = target_id or (row.matches[0].id if row.matches else None)
        if chosen is None:
            return (
                ImportRowResult(
                    row_number=row.row_number,
                    status="failed",
                    target_kind=kind,
                    message="No existing record is selected for this row.",
                ),
                None,
                None,
            )
        return (
            ImportRowResult(
                row_number=row.row_number,
                status="matched",
                target_kind=kind,
                target_id=chosen,
                message="Using the existing record.",
            ),
            None,
            None,
        )
    try:
        with db.begin_nested():
            if action == "create":
                new_id, after = _create_record(db, workspace, import_type, row)
                return (
                    ImportRowResult(
                        row_number=row.row_number,
                        status="created",
                        target_kind=kind,
                        target_id=new_id,
                        message="Created.",
                    ),
                    None,
                    after,
                )
            chosen = target_id or (row.matches[0].id if row.matches else None)
            if chosen is None:
                return (
                    ImportRowResult(
                        row_number=row.row_number,
                        status="failed",
                        target_kind=kind,
                        message="Choose an existing record to update.",
                    ),
                    None,
                    None,
                )
            before, after = _update_record(db, workspace.tenant_id, import_type, chosen, row)
            if before is None:
                return (
                    ImportRowResult(
                        row_number=row.row_number,
                        status="failed",
                        target_kind=kind,
                        message="The selected record no longer exists.",
                    ),
                    None,
                    None,
                )
            return (
                ImportRowResult(
                    row_number=row.row_number,
                    status="updated",
                    target_kind=kind,
                    target_id=chosen,
                    message="Updated.",
                ),
                before,
                after,
            )
    except IntegrityError as error:
        return (
            ImportRowResult(
                row_number=row.row_number,
                status="failed",
                target_kind=kind,
                message=_integrity_message(error),
            ),
            None,
            None,
        )


def preview_import(
    db: Session, workspace: Workspace, payload: ImportPreviewRequest
) -> ImportPreviewResponse:
    prepared = prepare_rows(db, workspace, payload)
    counts: dict[str, int] = {}
    valid_rows = [row for row in prepared if not row.issues]
    if payload.import_type == "information_object":
        counts["authoritative_systems_resolved"] = sum(
            1 for row in valid_rows if "authoritative_system_id" in row.resolved
        )
    elif payload.import_type == "integration":
        counts["endpoints_resolved"] = sum(
            1
            for row in valid_rows
            if "source_object_id" in row.resolved and "target_object_id" in row.resolved
        )
    elif payload.import_type == "solution":
        counts["member_systems_resolved"] = sum(
            len(row.resolved.get("member_system_ids") or []) for row in valid_rows
        )
    elif payload.import_type == "system":
        counts["rows_matched"] = sum(1 for row in valid_rows if row.matches)
    return ImportPreviewResponse(
        import_type=payload.import_type,
        rows=[
            ImportRowPreview(
                row_number=row.row_number,
                external_id=row.external_id,
                name=row.name,
                values=row.values,
                issues=row.issues,
                warnings=row.warnings,
                matches=row.matches,
                suggested_decision=row.suggested_decision,
            )
            for row in prepared
        ],
        blocked_count=sum(1 for row in prepared if row.issues),
        resolved_reference_counts=counts,
    )


def commit_import(db: Session, workspace: Workspace, payload: ImportCommitRequest) -> ImportBatch:
    prepared = prepare_rows(db, workspace, payload)
    decisions = {decision.row_number: decision for decision in payload.decisions}
    unknown = sorted(set(decisions) - {row.row_number for row in prepared})
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown row number(s) in decisions: "
            + ", ".join(str(item) for item in unknown),
        )
    batch = ImportBatch(
        tenant_id=workspace.tenant_id,
        workspace_id=workspace.id,
        source_filename=payload.source_filename or "import",
        sheet_name=payload.sheet_name or "",
        import_type=payload.import_type,
        status="applied",
        counts={key: 0 for key in COUNT_KEYS},
        imported_at=datetime.now(UTC),
    )
    db.add(batch)
    db.flush()

    counts = {key: 0 for key in COUNT_KEYS}
    for row in prepared:
        decision = decisions.get(row.row_number)
        action: RowDecision = decision.decision if decision else row.suggested_decision
        target_id = decision.target_id if decision else None
        result, before, after = _apply_row(
            db, workspace, payload.import_type, row, action, target_id
        )
        if result.status in counts:
            counts[result.status] += 1
        db.add(
            ImportRowResultModel(
                tenant_id=workspace.tenant_id,
                batch_id=batch.id,
                row_number=row.row_number,
                external_id=row.external_id,
                action=action,
                target_kind=result.target_kind,
                target_id=result.target_id,
                status=result.status,
                message=result.message,
                before=before,
                after=after,
            )
        )
    batch.counts = counts
    db.commit()
    db.refresh(batch)
    return batch


def batch_response(db: Session, batch: ImportBatch, *, include_rows: bool = True) -> dict:
    rows: list[ImportRowResult] = []
    if include_rows:
        records = db.scalars(
            select(ImportRowResultModel)
            .where(ImportRowResultModel.batch_id == batch.id)
            .order_by(ImportRowResultModel.row_number)
        )
        rows = [
            ImportRowResult(
                row_number=record.row_number,
                external_id=record.external_id,
                status=record.status,
                target_kind=record.target_kind,
                target_id=record.target_id,
                message=record.message,
            )
            for record in records
        ]
    return {
        "id": batch.id,
        "workspace_id": batch.workspace_id,
        "source_filename": batch.source_filename,
        "sheet_name": batch.sheet_name,
        "import_type": batch.import_type,
        "status": batch.status,
        "counts": dict(batch.counts or {}),
        "rows": rows,
        "imported_at": batch.imported_at,
        "undone_at": batch.undone_at,
    }


def _purge_state_references(
    db: Session, workspace_id: UUID, object_ids: set[str], integration_ids: set[str]
) -> int:
    """Remove canvas placements of records that an undo is deleting."""

    if not object_ids and not integration_ids:
        return 0
    removed = 0
    states = list(
        db.scalars(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == workspace_id,
                ArchitectureState.deleted_at.is_(None),
            )
        )
    )
    for state in states:
        nodes = list(state.nodes or [])
        removed_occurrences = {
            str(node.get("occurrence_id"))
            for node in nodes
            if str(node.get("object_id")) in object_ids
        }
        kept_nodes = [node for node in nodes if str(node.get("object_id")) not in object_ids]
        removed += len(nodes) - len(kept_nodes)
        kept_relationships = []
        for relationship in state.relationships or []:
            source_id = str(relationship.get("source_id"))
            target_id = str(relationship.get("target_id"))
            integration_id = relationship.get("integration_id")
            if (
                source_id in removed_occurrences
                or target_id in removed_occurrences
                or (integration_id is not None and str(integration_id) in integration_ids)
            ):
                removed += 1
                continue
            kept_relationships.append(relationship)
        if len(kept_nodes) != len(nodes) or len(kept_relationships) != len(
            state.relationships or []
        ):
            state.nodes = kept_nodes
            state.relationships = kept_relationships
            state.updated_at = datetime.now(UTC)
    return removed


def _external_system_reference(db: Session, tenant_id: UUID, system_id: UUID) -> str | None:
    contract = db.scalar(
        select(Integration.name).where(
            Integration.tenant_id == tenant_id,
            Integration.deleted_at.is_(None),
            (Integration.source_system_id == system_id)
            | (Integration.target_system_id == system_id),
        )
    )
    if contract:
        return f"contract '{contract}'"
    information_object = db.scalar(
        select(InformationObject.name).where(
            InformationObject.tenant_id == tenant_id,
            InformationObject.authoritative_system_id == system_id,
        )
    )
    if information_object:
        return f"information object '{information_object}'"
    solution = db.scalar(
        select(SolutionBoundary.name)
        .join(
            SolutionMember,
            (SolutionMember.solution_object_id == SolutionBoundary.object_id)
            & (SolutionMember.tenant_id == SolutionBoundary.tenant_id),
        )
        .where(
            SolutionMember.tenant_id == tenant_id,
            SolutionMember.system_id == system_id,
        )
    )
    if solution:
        return f"solution '{solution}'"
    return None


def _snapshot_for(db: Session, tenant_id: UUID, kind: str | None, target_id: UUID) -> dict | None:
    if kind == "system":
        record = db.get(CatalogSystem, target_id)
        if record is None or record.tenant_id != tenant_id or record.deleted_at is not None:
            return None
        return _system_snapshot(record)
    if kind == "integration":
        record = db.get(Integration, target_id)
        if record is None or record.tenant_id != tenant_id or record.deleted_at is not None:
            return None
        return _integration_snapshot(record)
    if kind == "information_object":
        record = db.scalar(
            select(InformationObject).where(
                InformationObject.object_id == target_id,
                InformationObject.tenant_id == tenant_id,
            )
        )
        return _information_object_snapshot(record) if record else None
    if kind == "solution_boundary":
        record = db.scalar(
            select(SolutionBoundary).where(
                SolutionBoundary.object_id == target_id,
                SolutionBoundary.tenant_id == tenant_id,
            )
        )
        return _solution_snapshot(db, record) if record else None
    return None


def _restore_record(
    db: Session, tenant_id: UUID, kind: str | None, target_id: UUID, before: dict
) -> None:
    if kind == "system":
        record = db.get(CatalogSystem, target_id)
        if record is None:
            return
        for key in ("name", "description", "external_identifier"):
            if key in before:
                setattr(record, key, before[key])
        if "metadata" in before:
            record.extra_metadata = dict(before["metadata"] or {})
        record.updated_at = datetime.now(UTC)
        return
    if kind == "integration":
        record = db.get(Integration, target_id)
        if record is None:
            return
        for key in ("name", "description", "interaction_type", "external_identifier"):
            if key in before:
                setattr(record, key, before[key])
        if "metadata" in before:
            record.extra_metadata = dict(before["metadata"] or {})
        record.updated_at = datetime.now(UTC)
        return
    if kind == "information_object":
        record = db.scalar(
            select(InformationObject).where(
                InformationObject.object_id == target_id,
                InformationObject.tenant_id == tenant_id,
            )
        )
        if record is None:
            return
        for key in ("name", "description", "owner", "classification", "external_identifier"):
            if key in before:
                setattr(record, key, before[key])
        if "authoritative_system_id" in before and before["authoritative_system_id"]:
            record.authoritative_system_id = UUID(str(before["authoritative_system_id"]))
        return
    if kind == "solution_boundary":
        record = db.scalar(
            select(SolutionBoundary).where(
                SolutionBoundary.object_id == target_id,
                SolutionBoundary.tenant_id == tenant_id,
            )
        )
        if record is None:
            return
        for key in ("name", "description", "owner", "external_identifier"):
            if key in before:
                setattr(record, key, before[key])
        if "member_system_ids" in before:
            desired = {UUID(str(item)) for item in before["member_system_ids"] or []}
            current = set(_solution_members(db, tenant_id, target_id))
            for removed in current - desired:
                member = db.scalar(
                    select(SolutionMember).where(
                        SolutionMember.tenant_id == tenant_id,
                        SolutionMember.solution_object_id == target_id,
                        SolutionMember.system_id == removed,
                    )
                )
                if member is not None:
                    db.delete(member)
            for added in desired - current:
                db.add(
                    SolutionMember(
                        tenant_id=tenant_id,
                        solution_object_id=target_id,
                        system_id=added,
                    )
                )
            db.flush()


def _reverse_create(
    db: Session, workspace: Workspace, row: ImportRowResultModel
) -> tuple[bool, str | None]:
    tenant_id = workspace.tenant_id
    if row.target_id is None:
        return True, "Nothing to reverse."
    if row.target_kind == "system":
        reference = _external_system_reference(db, tenant_id, row.target_id)
        if reference:
            return False, f"Not undone: the imported system is still referenced by {reference}."
        system = db.get(CatalogSystem, row.target_id)
        if system is None or system.deleted_at is not None:
            return True, "The imported system was already removed."
        now = datetime.now(UTC)
        system.deleted_at = system.updated_at = now
        return True, None
    if row.target_kind == "integration":
        integration = db.get(Integration, row.target_id)
        if integration is None or integration.deleted_at is not None:
            return True, "The imported contract was already removed."
        now = datetime.now(UTC)
        integration.deleted_at = integration.updated_at = now
        integration.revision += 1
        return True, None
    registry = db.get(ArchitectureObject, row.target_id)
    if registry is None or registry.tenant_id != tenant_id:
        return True, "The imported object was already removed."
    db.delete(registry)
    db.flush()
    return True, None


def _reverse_update(
    db: Session, workspace: Workspace, row: ImportRowResultModel
) -> tuple[bool, str | None]:
    if row.target_id is None:
        return True, "Nothing to reverse."
    snapshot = _snapshot_for(db, workspace.tenant_id, row.target_kind, row.target_id)
    if snapshot is None:
        return True, "The updated record no longer exists."
    after = row.after or {}
    changed = [
        key for key, value in after.items() if _jsonable(snapshot.get(key)) != _jsonable(value)
    ]
    if changed:
        return False, (
            "Not undone: these fields changed after the import: " + ", ".join(sorted(changed))
        )
    _restore_record(db, workspace.tenant_id, row.target_kind, row.target_id, row.before or {})
    db.flush()
    return True, None


def undo_import_batch(db: Session, workspace: Workspace, batch_id: UUID) -> ImportBatch:
    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.tenant_id == workspace.tenant_id,
            ImportBatch.workspace_id == workspace.id,
        )
    )
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch not found")
    if batch.status == "undone":
        raise HTTPException(status.HTTP_409_CONFLICT, "This import batch has already been undone")

    rows = list(
        db.scalars(
            select(ImportRowResultModel)
            .where(ImportRowResultModel.batch_id == batch.id)
            .order_by(ImportRowResultModel.row_number.desc())
        )
    )
    created_ids: set[str] = set()
    integration_ids: set[str] = set()
    conflicts = 0
    for row in rows:
        # Rows already reversed keep their "undone" status; conflicted rows are retried so a
        # blocked undo can be completed once the blocking reference is gone.
        if row.status not in ("created", "updated", "conflict"):
            continue
        if row.action == "create":
            reversed_ok, message = _reverse_create(db, workspace, row)
            if reversed_ok and row.target_id is not None:
                if row.target_kind == "integration":
                    integration_ids.add(str(row.target_id))
                else:
                    created_ids.add(str(row.target_id))
        else:
            reversed_ok, message = _reverse_update(db, workspace, row)
        if reversed_ok:
            row.status = "undone"
            row.message = message or "Undone by the import batch undo."
        else:
            row.status = "conflict"
            row.message = message
            conflicts += 1

    removed = _purge_state_references(db, workspace.id, created_ids, integration_ids)
    batch.undone_at = datetime.now(UTC)
    batch.status = "undo_blocked" if conflicts else "undone"
    db.commit()
    db.refresh(batch)
    return batch, removed
