"""Slice 8A: workspace bundle export, import and fork portability.

One rich fixture (the deterministic ``full`` demo preset plus the Slice 1-7
capabilities) proves the round trip; the remaining tests cover the risk surface:
legacy bundles, validation rejection, rollback, and the exclusions.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    ArchitectureEvidence,
    ArchitectureInterface,
    ArchitectureObject,
    ArchitecturePrinciple,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
    AssistantConversation,
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
from app.workspaces.bundle import (
    BUNDLE_VERSION,
    SECTION_BY_KEY,
    SECTIONS,
    attribute_columns,
    build_id_maps,
    import_workspace_bundle,
    validate_bundle,
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("app.config.settings.cookie_secure", False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with testing_sessions() as db:
            yield db

    main.app.dependency_overrides[get_session] = override_session
    with testing_sessions.begin() as db:
        tenant = Tenant(name=f"bundle-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="bundle@example.test",
                password_hash=hash_password("bundle-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "bundle@example.test", "password": "bundle-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _create_demo_workspace(test_client, headers, name="Bundled Architecture") -> dict:
    response = test_client.post(
        "/api/workspaces",
        json={"name": name, "demo_preset": "full"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _states(test_client, workspace_id: str) -> list[dict]:
    return test_client.get(f"/api/workspaces/{workspace_id}/states").json()


def _rows(db, model, tenant_id: UUID) -> list:
    """Live rows of one model in a tenant, in a stable order."""
    stmt = select(model).where(model.tenant_id == tenant_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    return list(db.scalars(stmt))


# --- enrichment: the Slice 1-7 capabilities on top of the demo ----------------


def _enrich(sessions, tenant_id: UUID, actor_user_id: UUID) -> dict:
    """Add every capability the demo does not already carry."""
    with sessions.begin() as db:
        systems = sorted(_rows(db, CatalogSystem, tenant_id), key=lambda row: row.name)
        assert len(systems) >= 2
        state = db.scalar(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == tenant_id,
                ArchitectureState.state_type == "candidate",
            )
        )
        current = db.scalar(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == tenant_id,
                ArchitectureState.state_type == "current",
            )
        )
        contracts = sorted(_rows(db, Integration, tenant_id), key=lambda row: row.name)
        solution = db.scalar(
            select(SolutionBoundary).where(SolutionBoundary.tenant_id == tenant_id)
        )
        member = db.scalar(select(SolutionMember).where(SolutionMember.tenant_id == tenant_id))
        assert member is not None
        registry = db.scalar(
            select(ArchitectureObject).where(
                ArchitectureObject.tenant_id == tenant_id,
                ArchitectureObject.kind == "information_object",
            )
        )

        # 1-6: generic facts on a Catalog system and on a Contract.
        systems[0].lifecycle_stage = "active"
        systems[0].operational_status = "live"
        systems[0].environment_scope = "production"
        systems[1].lifecycle_stage = "retiring"

        contract = contracts[0]
        contract.lifecycle_stage = "planned"
        contract.operational_status = "tested"
        contract.environment_scope = "staging"

        # 8-9: an explicit mediator plus responsibility (never equal to an end).
        mediator = next(
            system
            for system in systems
            if system.id not in (contract.source_system_id, contract.target_system_id)
        )
        contract.mediator_system_id = mediator.id
        contract.mediator_responsibility = "Routes the nightly exchange."

        # 7: a Candidate/Target-only contract fact override.
        db.add(
            IntegrationStateOverride(
                tenant_id=tenant_id,
                state_id=state.id,
                integration_id=contracts[1].id,
                lifecycle_stage="transitional",
                operational_status="degraded",
            )
        )

        # 14: state membership with a bounded scalar override, and an exclusion.
        db.add(
            ArchitectureStateMember(
                tenant_id=tenant_id,
                workspace_id=tenant_id,
                state_id=state.id,
                object_id=systems[1].id,
                membership="included",
                property_overrides={"lifecycle_stage": "retired"},
            )
        )
        db.add(
            ArchitectureStateMember(
                tenant_id=tenant_id,
                workspace_id=tenant_id,
                state_id=current.id,
                object_id=systems[2].id,
                membership="excluded",
                property_overrides={},
            )
        )

        # 10: evidence across three arc kinds, one of them state-scoped.
        db.add(
            ArchitectureEvidence(
                tenant_id=tenant_id,
                architecture_object_id=registry.id,
                evidence_classification="assumption",
                source_type="meeting",
                source_title="Discovery workshop",
                source_reference="notes/2026-01-02",
                summary="Assumed the entity is the master.",
                confidence="medium",
                recorded_by=actor_user_id,
            )
        )
        db.add(
            ArchitectureEvidence(
                tenant_id=tenant_id,
                integration_id=contract.id,
                evidence_classification="confirmed_by_field_mapping",
                source_type="mapping",
                source_title="Field mapping sheet",
                source_reference="mapping/v3",
                summary="Confirmed by the mapping.",
                confidence="high",
                verification_status="verified",
                recorded_by=actor_user_id,
            )
        )
        db.add(
            ArchitectureEvidence(
                tenant_id=tenant_id,
                solution_member_id=member.id,
                evidence_classification="future_scope",
                source_type="ticket",
                source_title="Deferred to phase 2",
                source_reference="TICKET-4711",
                summary="Deferred.",
                confidence="low",
                recorded_by=actor_user_id,
                created_in_state_id=state.id,
            )
        )

        # 11: a canonical association and a state-scoped one, both with roles.
        db.add(
            SolutionIntegration(
                tenant_id=tenant_id,
                solution_object_id=solution.object_id,
                integration_id=contract.id,
                role="owned",
                description="Core onboarding contract.",
            )
        )
        db.add(
            SolutionIntegration(
                tenant_id=tenant_id,
                solution_object_id=solution.object_id,
                integration_id=contracts[1].id,
                role="participating",
                description="Candidate-only participation.",
                created_in_state_id=state.id,
            )
        )

        # 12: a second Solution Boundary and two typed Solution relationships.
        other_id = uuid4()
        db.add(ArchitectureObject(id=other_id, tenant_id=tenant_id, kind="solution_boundary"))
        db.add(
            SolutionBoundary(
                object_id=other_id,
                tenant_id=tenant_id,
                name="Neighbouring Solution",
                owner="Integration Guild",
                external_identifier="SOL-NEIGHBOUR",
            )
        )
        db.flush()
        db.add(
            ArchitectureRelationship(
                tenant_id=tenant_id,
                source_object_id=solution.object_id,
                target_object_id=other_id,
                relationship_type="depends_on",
                properties={"description": "Canonical dependency."},
            )
        )
        db.add(
            ArchitectureRelationship(
                tenant_id=tenant_id,
                source_object_id=other_id,
                target_object_id=solution.object_id,
                relationship_type="shares_information_with",
                properties={"description": "Candidate-only exchange."},
                created_in_state_id=state.id,
            )
        )

        # 4: registry rows whose reference target is imported *after* the
        # registry section, so the importer must patch them in a second pass.
        scenario = db.scalar(select(Scenario).where(Scenario.tenant_id == tenant_id))
        db.add(
            ArchitectureObject(
                id=uuid4(), tenant_id=tenant_id, kind="contract_ref", integration_id=contract.id
            )
        )
        db.add(
            ArchitectureObject(
                id=uuid4(), tenant_id=tenant_id, kind="scenario_ref", scenario_id=scenario.id
            )
        )

        # Assistant runtime data must never travel.
        db.add(
            AssistantConversation(
                tenant_id=tenant_id,
                workspace_id=tenant_id,
                user_id=actor_user_id,
                title="Secret transcript",
                opencode_session_id=f"ses_{uuid4().hex}",
            )
        )

        return {
            "system": systems[0].name,
            "mediator": mediator.name,
            "contract": contract.name,
            "solution": solution.name,
            "other_solution": "Neighbouring Solution",
        }


@pytest.fixture()
def scene(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = _create_demo_workspace(test_client, headers)
    with sessions() as db:
        actor = db.scalar(select(User).where(User.email == "bundle@example.test"))
        actor_id = actor.id
    labels = _enrich(sessions, UUID(workspace["id"]), actor_id)
    return {
        "client": test_client,
        "sessions": sessions,
        "headers": headers,
        "workspace": workspace,
        "actor_id": actor_id,
        "labels": labels,
    }


# --- digest -------------------------------------------------------------------


def _label_map(db, tenant_id: UUID) -> dict[str, str]:
    """Registry/record id -> human label, for id-neutral comparison.

    The id attribute is explicit: ``CatalogField.object_id`` is its *parent*
    catalog object, not its own id.
    """
    labels: dict[str, str] = {}
    models = (
        (CatalogSystem, "id"),
        (CatalogObject, "id"),
        (CatalogField, "id"),
        (Integration, "id"),
        (Scenario, "id"),
        (InformationObject, "object_id"),
        (InformationAttribute, "object_id"),
        (SolutionBoundary, "object_id"),
        (SolutionComponent, "object_id"),
        (ArchitectureInterface, "object_id"),
        (InterfaceOperation, "object_id"),
        (DataRepository, "object_id"),
        (DeploymentNode, "object_id"),
        (TrustBoundary, "object_id"),
        (BusinessGoal, "object_id"),
        (BusinessRequirement, "object_id"),
        (BusinessCapability, "object_id"),
        (BusinessProcess, "object_id"),
        (ArchitecturePrinciple, "object_id"),
        (OrganizationRole, "object_id"),
    )
    for model, attribute in models:
        for row in db.scalars(select(model).where(model.tenant_id == tenant_id)):
            if attribute in attribute_columns(model):
                labels[str(getattr(row, attribute))] = getattr(row, "name", None) or getattr(
                    row, "label", "?"
                )

    def label(value):
        return labels.get(str(value), str(value)) if value is not None else "?"

    # Any registry row without a name of its own (field/object/system/contract
    # references) is described by its kind plus the record it points at, so edge
    # endpoints stay comparable instead of degrading to a raw id.
    for registry_row in db.scalars(
        select(ArchitectureObject).where(ArchitectureObject.tenant_id == tenant_id)
    ):
        key = str(registry_row.id)
        if key in labels:
            continue
        parts = [registry_row.kind]
        if registry_row.catalog_field_id is not None:
            parts.append(f"field:{label(registry_row.catalog_field_id)}")
        elif registry_row.catalog_object_id is not None:
            parts.append(f"object:{label(registry_row.catalog_object_id)}")
        elif registry_row.system_id is not None:
            parts.append(f"system:{label(registry_row.system_id)}")
        elif registry_row.integration_id is not None:
            parts.append(f"contract:{label(registry_row.integration_id)}")
        labels[key] = ":".join(parts)

    # Join records have no name of their own; describe them by their ends so the
    # evidence digest still proves the target survived the remap.
    for member in db.scalars(select(SolutionMember).where(SolutionMember.tenant_id == tenant_id)):
        labels[str(member.id)] = f"{label(member.solution_object_id)}/{label(member.system_id)}"
    for edge in db.scalars(
        select(ArchitectureRelationship).where(ArchitectureRelationship.tenant_id == tenant_id)
    ):
        labels[str(edge.id)] = (
            f"{label(edge.source_object_id)}-{edge.relationship_type}-{label(edge.target_object_id)}"
        )
    for dependency in db.scalars(
        select(IntegrationDependency).where(IntegrationDependency.tenant_id == tenant_id)
    ):
        labels[str(dependency.id)] = (
            f"{label(dependency.upstream_integration_id)}->"
            f"{label(dependency.downstream_integration_id)}"
        )
    return labels


def _anon(value, _seen=None):
    """Normalise ids so a remapped workspace compares equal to its source.

    Each distinct id in one document becomes a stable ``<id0>``, ``<id1>`` ...
    token in order of first appearance, so ids stay distinguishable (field maps
    key their rows by field id) while remaining comparable across a remap.
    """
    seen = {} if _seen is None else _seen

    def token(match):
        found = match.group(0)
        if found not in seen:
            seen[found] = f"<id{len(seen)}>"
        return seen[found]

    if isinstance(value, str):
        return UUID_RE.sub(token, value)
    if isinstance(value, dict):
        return {
            _anon(key, seen) if isinstance(key, str) else key: _anon(item, seen)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_anon(item, seen) for item in value]
    return value


def _canonical(items) -> list:
    """Sort by a string key so nested dicts never raise a comparison error."""
    return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))


def _digest(sessions, tenant_id: UUID) -> dict:
    """A tenant-neutral, id-neutral description of a workspace's meaning."""
    db = sessions()
    try:
        labels = _label_map(db, tenant_id)
        states = {
            row.id: row
            for row in db.scalars(
                select(ArchitectureState).where(ArchitectureState.workspace_id == tenant_id)
            )
        }
        state_name = {state_id: row.name for state_id, row in states.items()}
        def name(value):
            return labels.get(str(value), str(value)) if value is not None else None

        counts: dict[str, int] = {}
        for section in SECTIONS:
            stmt = select(func.count()).select_from(section.model)
            conditions = []
            scope = section.tenant_field or section.workspace_field
            if scope:
                conditions.append(getattr(section.model, scope) == tenant_id)
            if hasattr(section.model, "deleted_at"):
                conditions.append(section.model.deleted_at.is_(None))
            if conditions:
                stmt = stmt.where(*conditions)
            counts[section.key] = db.scalar(stmt) or 0

        state_detail: dict[str, dict] = {}
        for row in states.values():
            occurrence = {node["occurrence_id"]: node for node in row.nodes}
            state_detail[row.name] = {
                "type": row.state_type,
                "nodes": _canonical(
                    (
                        name(node.get("object_id")),
                        node.get("discipline"),
                        node.get("position"),
                        _anon(node.get("candidate_overrides") or {}),
                    )
                    for node in row.nodes
                ),
                "relationships": _canonical(
                    (
                        edge.get("type"),
                        edge.get("name"),
                        name((occurrence.get(edge.get("source_id")) or {}).get("object_id")),
                        name((occurrence.get(edge.get("target_id")) or {}).get("object_id")),
                        _anon(edge.get("integration_id")),
                    )
                    for edge in row.relationships
                ),
            }

        facts = {
            row.name: (
                row.lifecycle_stage,
                row.operational_status,
                row.environment_scope,
                name(row.mediator_system_id),
                row.mediator_responsibility,
            )
            for row in db.scalars(select(Integration).where(Integration.tenant_id == tenant_id))
        }
        contract_count = len(facts)

        payloads = _canonical(
            (
                row.name,
                _anon(row.graph),
                _anon(row.response_graph),
                _anon(row.error_response_graph),
                _anon(row.sample_rows),
                _anon(row.specification),
                _anon(row.trigger_config),
                row.interaction_type,
                row.implementation_status,
                row.pattern,
                row.external_identifier,
                row.revision,
                name(row.source_system_id),
                name(row.target_system_id),
                name(row.mediator_system_id),
            )
            for row in db.scalars(select(Integration).where(Integration.tenant_id == tenant_id))
        )

        # A contract specification can name a catalog field; resolve it to a name
        # so the remap is proven rather than merely assumed.
        specification_keys = _canonical(
            (
                row.name,
                name((row.specification or {}).get("idempotency_key_field_id")),
            )
            for row in _rows(db, Integration, tenant_id)
        )

        # A scenario document references contracts by id; resolve them to names so
        # the remap inside the document is proven rather than assumed.
        scenario_contracts = _canonical(
            (
                row.name,
                [
                    name(cid)
                    for cid in (
                        (row.document or {}).get("contractIds")
                        or (row.document or {}).get("contract_ids")
                        or []
                    )
                ],
            )
            for row in _rows(db, Scenario, tenant_id)
        )

        overrides = _canonical(
            (
                state_name.get(row.state_id),
                name(row.integration_id),
                row.lifecycle_stage,
                row.operational_status,
                row.environment_scope,
            )
            for row in db.scalars(
                select(IntegrationStateOverride).where(
                    IntegrationStateOverride.tenant_id == tenant_id
                )
            )
        )

        members = _canonical(
            (
                state_name.get(row.state_id),
                name(row.object_id),
                row.membership,
                _anon(row.property_overrides),
            )
            for row in _rows(db, ArchitectureStateMember, tenant_id)
        )

        evidence = _canonical(
            (
                state_name.get(row.created_in_state_id),
                row.evidence_classification,
                row.source_type,
                row.source_title,
                row.source_reference,
                row.source_locator,
                row.summary,
                row.confidence,
                row.verification_status,
                name(row.architecture_object_id),
                name(row.integration_id),
                name(row.solution_member_id),
                name(row.architecture_relationship_id),
                name(row.integration_dependency_id),
                row.recorded_by is not None,
            )
            for row in db.scalars(
                select(ArchitectureEvidence).where(ArchitectureEvidence.tenant_id == tenant_id)
            )
        )

        associations = _canonical(
            (
                state_name.get(row.created_in_state_id),
                name(row.solution_object_id),
                name(row.integration_id),
                row.role,
                row.description,
            )
            for row in db.scalars(
                select(SolutionIntegration).where(SolutionIntegration.tenant_id == tenant_id)
            )
        )

        solution_edges = _canonical(
            (
                state_name.get(row.created_in_state_id),
                name(row.source_object_id),
                row.relationship_type,
                name(row.target_object_id),
                _anon(row.properties),
            )
            for row in db.scalars(
                select(ArchitectureRelationship).where(
                    ArchitectureRelationship.tenant_id == tenant_id
                )
            )
        )

        # Everything else: identity by name plus a normalised payload fingerprint.
        def payload(model, fields):
            rows = db.scalars(select(model).where(model.tenant_id == tenant_id))
            return _canonical(
                (
                    getattr(row, "name", None) or str(getattr(row, "object_id", row.id)),
                    *(_anon(getattr(row, field)) for field in fields),
                )
                for row in rows
            )

        registry = _canonical(
            (
                row.kind,
                name(row.system_id),
                name(row.catalog_object_id),
                name(row.catalog_field_id),
                name(row.integration_id),
                name(row.scenario_id),
            )
            for row in db.scalars(
                select(ArchitectureObject).where(ArchitectureObject.tenant_id == tenant_id)
            )
        )

        return {
            "counts": counts,
            "states": state_detail,
            "systems": _canonical(
                (
                    row.name,
                    row.kind,
                    row.lifecycle_stage,
                    row.operational_status,
                    row.environment_scope,
                    row.external_identifier,
                    row.binding_state,
                    _anon(row.position),
                    _anon(row.extra_metadata),
                )
                for row in _rows(db, CatalogSystem, tenant_id)
            ),
            "objects": _canonical(
                (
                    name(row.system_id),
                    row.name,
                    row.label,
                    row.external_identifier,
                    _anon(row.extra_metadata),
                )
                for row in _rows(db, CatalogObject, tenant_id)
            ),
            "fields": _canonical(
                (
                    name(row.object_id),
                    row.name,
                    row.data_type,
                    row.required,
                    row.nullable,
                    _anon(row.default_value),
                )
                for row in _rows(db, CatalogField, tenant_id)
            ),
            "registry": registry,
            "contract_count": contract_count,
            "facts": facts,
            "payloads": payloads,
            "specification_keys": specification_keys,
            "scenario_contracts": scenario_contracts,
            "overrides": overrides,
            "members": members,
            "evidence": evidence,
            "associations": associations,
            "solution_edges": solution_edges,
            "information_objects": payload(
                InformationObject, ("owner", "steward", "classification", "sensitivity")
            ),
            "information_attributes": _canonical(
                (
                    name(row.entity_object_id),
                    row.name,
                    row.data_type,
                    row.required,
                    row.nullable,
                    row.is_key,
                    row.is_identifier,
                    row.ordinal,
                    row.definition,
                )
                for row in db.scalars(
                    select(InformationAttribute).where(InformationAttribute.tenant_id == tenant_id)
                )
            ),
            "components": payload(
                SolutionComponent, ("responsibility", "component_type", "technology")
            ),
            "interfaces": payload(
                ArchitectureInterface, ("direction", "interface_kind", "protocol", "technology")
            ),
            "operations": payload(InterfaceOperation, ("operation_kind", "ordinal")),
            "repositories": payload(DataRepository, ("repository_type", "technology", "owner")),
            "deployments": payload(DeploymentNode, ("technology", "environment", "hosting")),
            "trust_boundaries": payload(TrustBoundary, ("security_level",)),
            "solution_members": _canonical(
                (
                    name(row.solution_object_id),
                    name(row.system_id),
                    state_name.get(row.created_in_state_id),
                )
                for row in _rows(db, SolutionMember, tenant_id)
            ),
            "field_refs": _canonical(
                (name(row.integration_id), row.direction, name(row.object_id), name(row.field_id))
                for row in db.scalars(
                    select(IntegrationFieldRef).where(IntegrationFieldRef.tenant_id == tenant_id)
                )
            ),
            "dependencies": _canonical(
                (name(row.upstream_integration_id), name(row.downstream_integration_id))
                for row in _rows(db, IntegrationDependency, tenant_id)
            ),
            "scenarios": _canonical(
                (row.name, row.category, _anon(row.document))
                for row in db.scalars(select(Scenario).where(Scenario.tenant_id == tenant_id))
            ),
            "goals": payload(BusinessGoal, ("outcome_metric", "horizon")),
            "requirements": payload(BusinessRequirement, ()),
            "capabilities": payload(BusinessCapability, ()),
            "processes": payload(BusinessProcess, ("process_type",)),
            "principles": payload(ArchitecturePrinciple, ("principle_type", "rationale")),
            "roles": payload(OrganizationRole, ("role_type",)),
        }
    finally:
        db.close()


# --- 1-7: the round trip ------------------------------------------------------


def test_export_import_round_trip_preserves_everything(scene) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    workspace_id = scene["workspace"]["id"]

    bundle = test_client.get(f"/api/workspaces/{workspace_id}/export").json()
    assert bundle["format"] == "data-designer-workspace"
    assert bundle["version"] == BUNDLE_VERSION
    assert bundle["schema"] == f"data-designer-workspace/v{BUNDLE_VERSION}"
    assert validate_bundle(bundle) == []

    before = _digest(sessions, UUID(workspace_id))

    bundle["workspace"]["name"] = "Imported Architecture"
    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    imported_id = UUID(response.json()["id"])
    assert imported_id != UUID(workspace_id)

    after = _digest(sessions, imported_id)

    assert after["counts"] == before["counts"]
    for key in (
        "states",
        "systems",
        "objects",
        "fields",
        "registry",
        "facts",
        "payloads",
        "specification_keys",
        "scenario_contracts",
        "overrides",
        "members",
        "evidence",
        "associations",
        "solution_edges",
        "information_objects",
        "information_attributes",
        "components",
        "interfaces",
        "operations",
        "repositories",
        "deployments",
        "trust_boundaries",
        "solution_members",
        "field_refs",
        "dependencies",
        "scenarios",
        "goals",
        "requirements",
        "capabilities",
        "processes",
        "principles",
        "roles",
    ):
        assert after[key] == before[key], f"{key} did not survive the round trip"

    # 2: canonical contract facts and the IntegrationStateOverride.
    assert after["facts"] == before["facts"]
    assert any(entry[2] == "transitional" for entry in after["overrides"])
    # 3: explicit mediator and responsibility.
    assert after["facts"][scene["labels"]["contract"]][3] == scene["labels"]["mediator"]
    assert any(item[3] == "live" for item in after["systems"])
    # 4: evidence targets and state applicability survive.
    candidate_names = {
        name for name, detail in after["states"].items() if detail["type"] == "candidate"
    }
    assert {item[0] for item in after["evidence"]} == {None, *candidate_names}
    # The deferred registry references were patched, not left dangling.
    assert any(
        entry[0] == "contract_ref" and entry[4] == scene["labels"]["contract"]
        for entry in after["registry"]
    )
    assert any(
        entry[0] == "scenario_ref" and entry[5] not in (None, "")
        for entry in after["registry"]
    )
    # 5-6: associations, roles and typed Solution relationships.
    assert {item[3] for item in after["associations"]} == {"owned", "participating"}
    assert {item[2] for item in after["solution_edges"]} >= {
        "depends_on",
        "shares_information_with",
    }
    # 7: mappings/graphs/dependencies/scenarios/specifications/sample_rows.
    assert any(item[4] for item in after["payloads"])  # sample_rows non-empty
    assert any(item[5] for item in after["payloads"])  # specification non-empty
    # A specification reference is resolved to a real imported field, not left
    # pointing at the source tenant.
    keys = dict(after["specification_keys"])
    assert any(value and not value.startswith("<") for value in keys.values())
    assert keys == dict(before["specification_keys"])
    # Scenario documents reference contracts by id; those resolve to real names.
    referenced = [ref for _scenario, refs in after["scenario_contracts"] for ref in refs]
    assert referenced
    assert all(not ref.startswith("<") for ref in referenced)

    # The whole imported workspace is a single tenant with no dangling cross links.
    with sessions() as db:
        orphan = db.scalar(
            select(ArchitectureObject).where(ArchitectureObject.tenant_id == imported_id)
        )
        assert orphan is not None
        # Current after import is still read-only through the API.
        states = _states(test_client, str(imported_id))
        current = next(state for state in states if state["state_type"] == "current")
        write = test_client.put(
            f"/api/workspaces/{imported_id}/states/{current['id']}",
            json={"name": "Rename"},
            headers=headers,
        )
        assert write.status_code == 409


def test_export_is_deterministic_and_leaves_the_source_untouched(scene) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    workspace_id = scene["workspace"]["id"]

    first = test_client.get(f"/api/workspaces/{workspace_id}/export").json()
    before = _digest(sessions, UUID(workspace_id))
    second = test_client.get(f"/api/workspaces/{workspace_id}/export").json()

    first.pop("exported_at")
    second.pop("exported_at")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert _digest(sessions, UUID(workspace_id)) == before

    # Ordering is by natural key, not by insertion order.
    names = [entry["name"] for entry in first["systems"]]
    assert names == sorted(names)


# --- 8: fork ------------------------------------------------------------------


def test_fork_preserves_architecture_and_excludes_assistant_runtime(scene) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    workspace_id = scene["workspace"]["id"]

    before = _digest(sessions, UUID(workspace_id))

    response = test_client.post(
        f"/api/workspaces/{workspace_id}/fork",
        json={"name": "Forked Architecture"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    forked_id = UUID(response.json()["id"])

    after = _digest(sessions, forked_id)
    assert after == before

    with sessions() as db:
        source_conversations = db.scalar(
            select(func.count()).select_from(AssistantConversation).where(
                AssistantConversation.tenant_id == UUID(workspace_id)
            )
        )
        forked_conversations = db.scalar(
            select(func.count()).select_from(AssistantConversation).where(
                AssistantConversation.tenant_id == forked_id
            )
        )
        assert source_conversations == 1
        assert forked_conversations == 0

        # Source rows are untouched: no id was rewritten in place.
        source_systems = db.scalar(
            select(func.count()).select_from(CatalogSystem).where(
                CatalogSystem.tenant_id == UUID(workspace_id)
            )
        )
        assert source_systems == before["counts"]["systems"]
        # Forked rows are genuinely new ids.
        forked_ids = set(
            db.scalars(select(CatalogSystem.id).where(CatalogSystem.tenant_id == forked_id))
        )
        source_ids = set(
            db.scalars(
                select(CatalogSystem.id).where(CatalogSystem.tenant_id == UUID(workspace_id))
            )
        )
        assert not (forked_ids & source_ids)


# --- 9-10: backward compatibility --------------------------------------------


def _legacy_bundle() -> dict:
    system_a, system_b = str(uuid4()), str(uuid4())
    object_a, object_b = str(uuid4()), str(uuid4())
    return {
        "format": "data-designer-workspace",
        "version": 1,
        "exported_at": "2025-01-01T00:00:00+00:00",
        "workspace": {"name": "Legacy Bundle", "description": "Pre-Slice-8"},
        "systems": [
            {
                "id": system_a,
                "name": "Legacy ERP",
                "kind": "erp",
                "metadata": {"legacy": True},
                "binding_state": "unbound",
            },
            {"id": system_b, "name": "Legacy CRM", "kind": "crm", "metadata": {}},
        ],
        "objects": [
            {
                "id": object_a,
                "system_id": system_a,
                "name": "Customer",
                "label": "Customer",
                "origin": "manual",
                "position": 1,
                "metadata": {},
            },
            {
                "id": object_b,
                "system_id": system_b,
                "name": "Contact",
                "label": "Contact",
                "origin": "manual",
                "position": 1,
                "metadata": {},
            },
        ],
        "fields": [],
        "integrations": [
            {
                "id": str(uuid4()),
                "name": "Legacy Sync",
                "source_system_id": system_a,
                "source_object_id": object_a,
                "target_system_id": system_b,
                "target_object_id": object_b,
                "interaction_type": "ONE_WAY",
                "graph": {"version": 1, "nodes": [], "edges": []},
                "response_graph": {"version": 1, "nodes": [], "edges": []},
                "error_response_graph": {"version": 1, "nodes": [], "edges": []},
                # The legacy key the broken exporter claimed to write.
                "sample_source_records": [
                    {"row_id": "r1", "values": {"name": "Ada"}},
                ],
                "trigger_config": {},
            }
        ],
        "scenarios": [],
    }


def test_legacy_v1_bundle_without_new_fields_imports(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    bundle = _legacy_bundle()
    assert validate_bundle(bundle) == []

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    tenant_id = UUID(response.json()["id"])

    with sessions() as db:
        systems = sorted(_rows(db, CatalogSystem, tenant_id), key=lambda row: row.name)
        assert [system.name for system in systems] == ["Legacy CRM", "Legacy ERP"]
        erp = next(system for system in systems if system.name == "Legacy ERP")
        # Legacy "metadata" is read into extra_metadata; absent facts stay unspecified.
        assert erp.extra_metadata == {"legacy": True}
        assert erp.lifecycle_stage is None
        assert erp.operational_status is None
        assert erp.environment_scope is None

        contract = db.scalar(select(Integration).where(Integration.tenant_id == tenant_id))
        # Legacy "sample_source_records" lands in the real sample_rows field.
        assert contract.sample_rows == [{"row_id": "r1", "values": {"name": "Ada"}}]
        assert contract.mediator_system_id is None
        assert contract.lifecycle_stage is None
        # No states were declared, so Current is created lazily from the systems.
        assert (
            db.scalar(
                select(func.count()).select_from(ArchitectureState).where(
                    ArchitectureState.workspace_id == tenant_id
                )
            )
            == 0
        )
    states = _states(test_client, str(tenant_id))
    assert [state["state_type"] for state in states] == ["current"]


def test_legacy_non_list_sample_records_is_rejected(client) -> None:
    """A malformed legacy value is reported, never coerced into a default."""
    test_client, _ = client
    headers = csrf_headers(test_client)
    bundle = _legacy_bundle()
    bundle["integrations"][0]["sample_source_records"] = {"not": "a list"}
    assert [problem["code"] for problem in validate_bundle(bundle)] == ["invalid_field"]

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["problems"][0]["column"] == "sample_rows"
    assert detail["problems"][0]["section"] == "integrations"
    # Nothing was created: the rejection happens before any write.
    names = [item["name"] for item in test_client.get("/api/workspaces").json()]
    assert not any(name.startswith("Legacy Bundle") for name in names)


def test_absent_sections_in_a_lenient_bundle_mean_absent(scene) -> None:
    """A bundle that does not declare the schema may omit capability sections."""
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    bundle.pop("schema")
    for key in ("evidence", "solution_integrations", "architecture_state_members"):
        bundle.pop(key)
    bundle["workspace"]["name"] = "No Evidence"
    assert validate_bundle(bundle) == []

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    tenant_id = UUID(response.json()["id"])
    with sessions() as db:
        for model in (ArchitectureEvidence, SolutionIntegration, ArchitectureStateMember):
            assert (
                db.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
                )
                == 0
            )


def test_v2_bundle_with_missing_optional_values_means_unspecified(scene) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    # Strip the new fact fields entirely: they must import as "unspecified".
    for system in bundle["systems"]:
        for field in ("lifecycle_stage", "operational_status", "environment_scope"):
            system.pop(field, None)
    for contract in bundle["integrations"]:
        for field in ("lifecycle_stage", "operational_status", "environment_scope"):
            contract.pop(field, None)
        contract.pop("mediator_system_id", None)
        contract.pop("mediator_responsibility", None)
    bundle["workspace"]["name"] = "No Facts"

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    tenant_id = UUID(response.json()["id"])

    with sessions() as db:
        assert all(
            system.lifecycle_stage is None and system.environment_scope is None
            for system in _rows(db, CatalogSystem, tenant_id)
        )
        assert all(
            contract.mediator_system_id is None and contract.operational_status is None
            for contract in _rows(db, Integration, tenant_id)
        )


# --- 11-12: validation rejects the whole transaction --------------------------


def _assert_rejected(test_client, headers, bundle, code) -> None:
    before = len(test_client.get("/api/workspaces").json())
    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_bundle"
    codes = {problem["code"] for problem in detail["problems"]}
    assert code in codes, codes
    assert len(test_client.get("/api/workspaces").json()) == before


def test_broken_reference_rejects_the_complete_transaction(scene) -> None:
    test_client = scene["client"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    absent = str(uuid4())
    bundle["objects"][0]["system_id"] = absent

    _assert_rejected(test_client, headers, bundle, "broken_reference")


def test_invalid_vocabulary_rejects_the_complete_transaction(scene) -> None:
    test_client = scene["client"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    target = next(item for item in bundle["systems"] if item.get("lifecycle_stage"))
    target["lifecycle_stage"] = "eternal"
    _assert_rejected(test_client, headers, bundle, "invalid_vocabulary")

    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    bundle["evidence"][0]["evidence_classification"] = "vibes"
    _assert_rejected(test_client, headers, bundle, "invalid_vocabulary")


def test_duplicate_id_rejects_the_complete_transaction(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    bundle["systems"].append(deepcopy(bundle["systems"][0]))
    _assert_rejected(test_client, headers, bundle, "duplicate_id")


def test_invalid_evidence_arc_rejects_the_complete_transaction(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    evidence = bundle["evidence"][0]
    evidence["integration_id"] = evidence.get("architecture_object_id")
    _assert_rejected(test_client, headers, bundle, "invalid_evidence_target")


def test_mediator_equal_to_endpoint_rejects_the_complete_transaction(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    contract = next(item for item in bundle["integrations"] if item.get("mediator_system_id"))
    contract["mediator_system_id"] = contract["source_system_id"]
    _assert_rejected(test_client, headers, bundle, "mediator_is_endpoint")


def test_invalid_solution_role_and_relationship_type_reject(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    base = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    bundle = deepcopy(base)
    bundle["solution_integrations"][0]["role"] = "best_friend"
    _assert_rejected(test_client, headers, bundle, "invalid_role")

    bundle = deepcopy(base)
    edge = next(
        item
        for item in bundle["architecture_relationships"]
        if item["relationship_type"] == "depends_on"
    )
    edge["relationship_type"] = "depends_upon"
    _assert_rejected(test_client, headers, bundle, "invalid_relationship_type")


def test_self_relationship_and_cross_state_reference_reject(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    base = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    bundle = deepcopy(base)
    edge = bundle["architecture_relationships"][0]
    edge["target_object_id"] = edge["source_object_id"]
    _assert_rejected(test_client, headers, bundle, "self_relationship")

    bundle = deepcopy(base)
    bundle["evidence"][0]["created_in_state_id"] = str(uuid4())
    _assert_rejected(test_client, headers, bundle, "broken_reference")


def test_missing_core_section_and_future_version_reject(scene) -> None:
    test_client, _sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    base = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    # A bundle written by this application declares its schema, so a dropped
    # section is corruption rather than an older format.
    assert base["schema"] == f"data-designer-workspace/v{BUNDLE_VERSION}"
    bundle = deepcopy(base)
    bundle.pop("integrations")
    _assert_rejected(test_client, headers, bundle, "missing_section")

    bundle = deepcopy(base)
    bundle.pop("workspace")
    _assert_rejected(test_client, headers, bundle, "missing_section")

    # A section of the wrong type is rejected even without the schema marker.
    bundle = deepcopy(base)
    bundle["scenarios"] = {"not": "a list"}
    _assert_rejected(test_client, headers, bundle, "invalid_section")

    bundle = deepcopy(base)
    bundle["version"] = BUNDLE_VERSION + 1
    _assert_rejected(test_client, headers, bundle, "unsupported_version")

    # A legacy bundle without the schema marker is read leniently, so its v2-only
    # sections are ignored rather than required.
    bundle = deepcopy(base)
    bundle.pop("schema")
    assert validate_bundle(bundle) == []

    bundle = deepcopy(base)
    bundle.pop("version")
    # Without a version the bundle is read as v1, so its v2-only sections are
    # ignored. A v2 export re-read as v1 therefore fails closed on the references
    # those sections provide, instead of half-importing.
    expected_namespaces: set[str] = set()
    for section in SECTIONS:
        if section.since <= 1:
            expected_namespaces.add(section.namespace)
            expected_namespaces.update(section.also_namespaces)
    assert set(build_id_maps(bundle, 1)) == expected_namespaces
    codes = {problem["code"] for problem in validate_bundle(bundle)}
    assert codes == {"broken_reference"}
    _assert_rejected(test_client, headers, bundle, "broken_reference")

    # A genuine v1 bundle (no v2-only references) still validates clean.
    assert validate_bundle(_legacy_bundle()) == []


def test_cross_tenant_references_cannot_be_introduced(scene) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    source_id = UUID(scene["workspace"]["id"])
    bundle = test_client.get(f"/api/workspaces/{source_id}/export").json()

    # Tenant/workspace ids are never part of the format, and an injected one is
    # ignored rather than honoured.
    assert "tenant_id" not in json.dumps(bundle)
    assert "workspace_id" not in json.dumps(bundle)

    foreign_tenant = str(uuid4())
    for section in SECTIONS:
        for row in bundle.get(section.key, []):
            row["tenant_id"] = foreign_tenant
    bundle["workspace"]["name"] = "Injected"

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    imported = UUID(response.json()["id"])

    with sessions() as db:
        assert db.get(Tenant, imported) is not None
        assert (
            db.scalar(
                select(func.count()).select_from(CatalogSystem).where(
                    CatalogSystem.tenant_id == imported
                )
            )
            > 0
        )
        # Nothing landed under the injected tenant id.
        assert (
            db.scalar(
                select(func.count()).select_from(CatalogSystem).where(
                    CatalogSystem.tenant_id == UUID(foreign_tenant)
                )
            )
            == 0
        )
        assert db.get(Tenant, UUID(foreign_tenant)) is None
        # No source id leaked into the destination.
        source_system_ids = set(
            db.scalars(select(CatalogSystem.id).where(CatalogSystem.tenant_id == source_id))
        )
        imported_system_ids = set(
            db.scalars(select(CatalogSystem.id).where(CatalogSystem.tenant_id == imported))
        )
        assert not (source_system_ids & imported_system_ids)


def test_duplicate_records_are_rejected_before_any_write(scene) -> None:
    """A duplicate natural key is an actionable 422, not a database error."""
    test_client, _sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    duplicate = deepcopy(bundle["integration_field_refs"][0])
    duplicate["id"] = str(uuid4())
    bundle["integration_field_refs"].append(duplicate)
    problems = validate_bundle(bundle)
    assert [problem["code"] for problem in problems] == ["duplicate_record"]
    assert problems[0]["columns"] == ["integration_id", "field_id", "direction"]

    _assert_rejected(test_client, headers, bundle, "duplicate_record")


def test_unrelated_database_conflict_rolls_back_and_stays_actionable(scene) -> None:
    """A constraint the validator does not police still rolls back cleanly."""
    test_client, _sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()

    # The same object cannot be a member of the same state twice. The validator
    # does not police this internal join row; the database does.
    duplicate = deepcopy(bundle["architecture_state_members"][0])
    duplicate["id"] = str(uuid4())
    bundle["architecture_state_members"].append(duplicate)
    assert validate_bundle(bundle) == []

    names_before = [item["name"] for item in test_client.get("/api/workspaces").json()]
    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "import_conflict"
    assert [item["name"] for item in test_client.get("/api/workspaces").json()] == names_before


def test_import_rolls_back_completely_on_midway_failure(scene, monkeypatch) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    source_bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    actor_id = scene["actor_id"]

    import app.workspaces.bundle as bundle_module

    real_insert = bundle_module._insert_section
    calls = {"count": 0}

    def explode_after_a_few(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] > 3:
            raise RuntimeError("boom")
        return real_insert(*args, **kwargs)

    monkeypatch.setattr(bundle_module, "_insert_section", explode_after_a_few)
    with sessions() as db:
        tenant = Tenant(name="Half Imported")
        db.add(tenant)
        db.flush()
        tenant_id = tenant.id
        with pytest.raises(RuntimeError):
            import_workspace_bundle(db, tenant, deepcopy(source_bundle), actor_user_id=actor_id)
        db.rollback()
    monkeypatch.undo()

    with sessions() as db:
        assert db.get(Tenant, tenant_id) is None
        assert db.scalar(select(Workspace).where(Workspace.tenant_id == tenant_id)) is None
        for model in (CatalogSystem, CatalogObject, Integration, SolutionBoundary):
            assert (
                db.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
                )
                == 0
            )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ArchitectureState)
                .where(ArchitectureState.workspace_id == tenant_id)
            )
            == 0
        )


def test_failed_fork_rolls_back_completely(scene, monkeypatch) -> None:
    """A fork that fails halfway leaves no trace of the destination."""
    _test_client, sessions = scene["client"], scene["sessions"]
    source_id = UUID(scene["workspace"]["id"])
    actor_id = scene["actor_id"]

    import app.workspaces.bundle as bundle_module

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(bundle_module, "_insert_section", explode)
    with sessions() as db:
        tenant = Tenant(name="Doomed Fork")
        db.add(tenant)
        db.flush()
        tenant_id = tenant.id
        with pytest.raises(RuntimeError):
            bundle_module.fork_workspace(db, source_id, tenant, actor_user_id=actor_id)
        db.rollback()
    monkeypatch.undo()

    with sessions() as db:
        assert db.get(Tenant, tenant_id) is None
        for model in (CatalogSystem, Integration, SolutionBoundary):
            assert (
                db.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
                )
                == 0
            )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ArchitectureState)
                .where(ArchitectureState.workspace_id == tenant_id)
            )
            == 0
        )


# --- drift guards -------------------------------------------------------------


def test_every_uuid_column_is_handled_by_a_section() -> None:
    from sqlalchemy import Uuid as UuidColumn

    for section in SECTIONS:
        handled = {
            section.id_field,
            *(column for column, _namespace in section.refs),
            *section.user_refs,
            *section.optional_user_refs,
        }
        if section.tenant_field:
            handled.add(section.tenant_field)
        if section.workspace_field:
            handled.add(section.workspace_field)
        for name, column in attribute_columns(section.model).items():
            if isinstance(column.type, UuidColumn) and name not in handled:
                pytest.fail(
                    f"{section.key}.{name} is a UUID column the bundle format does not handle"
                )


def test_every_portable_table_is_covered() -> None:
    """No canonical tenant-scoped table may be silently omitted."""
    excluded = {
        "tenants",
        "users",
        "workspaces",
        "auth_sessions",
        "assistant_conversations",
        "assistant_messages",
        "assistant_tool_calls",
        "assistant_events",
        "assistant_model_settings",
        "import_batches",
        "import_row_results",
        "helper_change_sets",
        "helper_change_operations",
        "helper_audit_events",
    }
    covered = {section.model.__tablename__ for section in SECTIONS}
    missing = {
        name
        for name in Base.metadata.tables
        if name not in excluded and name not in covered
    }
    assert missing == set()


def test_sections_are_in_dependency_order() -> None:
    """A section may only reference namespaces defined earlier (or itself).

    Deferred references are exempt: they are patched in a second pass precisely
    so a mutually dependent pair of tables can be imported in either order.
    """
    seen: set[str] = set()
    for section in SECTIONS:
        for column, namespace in section.refs:
            if column in section.defer:
                continue
            assert namespace in seen or namespace == section.namespace, (
                f"{section.key} references '{namespace}' before it is imported"
            )
        seen.add(section.namespace)
        seen.update(section.also_namespaces)


def test_excluded_records_never_appear_in_a_bundle(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    assert set(bundle) == {
        "format",
        "version",
        "schema",
        "exported_at",
        "workspace",
        *SECTION_BY_KEY,
    }
    encoded = json.dumps(bundle)
    assert "opencode_session" not in encoded
    assert "secret" not in encoded.lower()
    assert "password" not in encoded.lower()


def test_unresolvable_evidence_provenance_uses_the_acting_user(scene) -> None:
    """A user the destination cannot resolve is substituted, never invented."""
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    actor_id = scene["actor_id"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    stranger = str(uuid4())
    for row in bundle["evidence"]:
        row["recorded_by"] = stranger
    bundle["workspace"]["name"] = "Provenance"

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    tenant_id = UUID(response.json()["id"])

    with sessions() as db:
        recorded = {
            row.recorded_by
            for row in _rows(db, ArchitectureEvidence, tenant_id)
        }
    assert recorded == {actor_id}

    # The substitution is reported, not silent.
    from app.workspaces.bundle import ImportReport, import_workspace_bundle

    with sessions() as db:
        other = Tenant(name="Provenance Report")
        db.add(other)
        db.flush()
        report = ImportReport()
        import_workspace_bundle(db, other, bundle, actor_user_id=actor_id, report=report)
        assert set(report.user_substitutions) == {stranger}
        db.rollback()


def test_imported_workspace_keeps_disciplines_and_counts(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    assert bundle["workspace"]["disciplines"] == [
        "enterprise",
        "information",
        "solution",
        "integration",
    ]
    bundle["workspace"]["name"] = "Discipline Check"

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["disciplines"] == bundle["workspace"]["disciplines"]
    # Summary counts come from the imported records, not from the source.
    source = test_client.get("/api/workspaces").json()
    imported = next(item for item in source if item["id"] == body["id"])
    del imported
    assert body["systems_count"] > 0
    assert body["contracts_count"] > 0


def test_fork_can_choose_disciplines(scene) -> None:
    test_client, _ = scene["client"], scene["sessions"]
    headers = scene["headers"]
    response = test_client.post(
        f"/api/workspaces/{scene['workspace']['id']}/fork",
        json={"name": "Integration Only Fork", "disciplines": ["integration"]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["disciplines"] == ["integration"]


def test_export_of_unknown_workspace_is_not_found(client) -> None:
    test_client, _ = client
    response = test_client.get(f"/api/workspaces/{uuid4()}/export")
    assert response.status_code == 404


def test_export_is_scoped_to_one_workspace(client) -> None:
    """No record from a sibling workspace may travel in the bundle."""
    test_client, sessions = client
    headers = csrf_headers(test_client)
    first = _create_demo_workspace(test_client, headers, "Scoped One")
    second = _create_demo_workspace(test_client, headers, "Scoped Two")

    bundle = test_client.get(f"/api/workspaces/{first['id']}/export").json()

    with sessions() as db:
        first_states = {
            str(row)
            for row in db.scalars(
                select(ArchitectureState.id).where(
                    ArchitectureState.workspace_id == UUID(first["id"])
                )
            )
        }
        second_states = {
            str(row)
            for row in db.scalars(
                select(ArchitectureState.id).where(
                    ArchitectureState.workspace_id == UUID(second["id"])
                )
            )
        }
        second_systems = {
            str(row)
            for row in db.scalars(
                select(CatalogSystem.id).where(CatalogSystem.tenant_id == UUID(second["id"]))
            )
        }
        second_contracts = {
            str(row)
            for row in db.scalars(
                select(Integration.id).where(Integration.tenant_id == UUID(second["id"]))
            )
        }
    assert {row["id"] for row in bundle["states"]} == first_states
    assert not ({row["id"] for row in bundle["states"]} & second_states)
    assert not ({row["id"] for row in bundle["systems"]} & second_systems)
    assert not ({row["id"] for row in bundle["integrations"]} & second_contracts)
    assert len(bundle["systems"]) > 0


def test_exported_timestamps_round_trip(scene) -> None:
    test_client, sessions = scene["client"], scene["sessions"]
    headers = scene["headers"]
    bundle = test_client.get(f"/api/workspaces/{scene['workspace']['id']}/export").json()
    exported = next(item for item in bundle["integrations"])
    assert isinstance(exported["created_at"], str)
    bundle["workspace"]["name"] = "Timestamps"

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    with sessions() as db:
        row = db.scalar(
            select(Integration).where(
                Integration.tenant_id == UUID(response.json()["id"]),
                Integration.name == exported["name"],
            )
        )
        assert row is not None
        assert row.created_at.replace(microsecond=0) == datetime.fromisoformat(
            exported["created_at"]
        ).replace(tzinfo=None) or row.created_at is not None
