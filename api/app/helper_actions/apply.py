"""Transactional apply and conflict-safe undo for approved change sets (Slice 4).

This is the only module that writes architecture-domain data for the helper
layer. It is deliberately narrow:

* dispatch is a closed registry keyed by ``domain_action``; unknown actions fail
  closed (no generic executor, dynamic import, SQL, JSON patch, or ORM payload);
* it reuses the existing canonical models and validation helpers and calls no
  committing HTTP route handler;
* it writes only Candidate/Target memberships, overrides, rows, relationships,
  new draft Contracts, mappings, transformations, and scenarios;
* reused canonical objects, reused Contracts, and the Catalog are read-only;
* no dry-run, simulation, scenario evaluation, or conformance test is executed;
* every operation records ownership + a post-apply fingerprint so undo can
  remove only change-set-owned rows and refuse unsafe destructive steps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.architecture.information import ER_EDGE_TYPE, REALIZES_EDGE_TYPE
from app.architecture.solution import (
    CONNECTS_TO,
    CONTAINED_IN,
    CROSSES,
    DEPLOYED_ON,
    USES_REPOSITORY,
)
from app.architecture.state_scope import get_state
from app.helper_actions import matching
from app.helper_actions.context import HelperContext
from app.integrations.graph import (
    GraphDocument,
    GraphValidationError,
)
from app.integrations.routes import graph_references
from app.models import (
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
    DataRepository,
    DeploymentNode,
    HelperChangeOperation,
    HelperChangeSet,
    InformationAttribute,
    InformationObject,
    Integration,
    IntegrationFieldRef,
    InterfaceOperation,
    OrganizationRole,
    Scenario,
    SolutionBoundary,
    SolutionComponent,
    TrustBoundary,
)
from app.scenarios.routes import document_json, validate_for_save
from app.scenarios.schemas import ScenarioDocument

# --- closed vocabularies -----------------------------------------------------

KIND_MODEL: dict[str, Any] = {
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

CANVAS_KINDS = frozenset(
    {
        "business_goal",
        "business_requirement",
        "business_capability",
        "business_process",
        "architecture_principle",
        "organization_role",
        "information_object",
        "solution_boundary",
        "component",
    }
)
CHILD_KINDS = frozenset(
    {
        "information_attribute",
        "interface",
        "interface_operation",
        "data_repository",
        "deployment_node",
        "trust_boundary",
    }
)
DISCIPLINE_KINDS = frozenset(CANVAS_KINDS | CHILD_KINDS)
CATALOG_KINDS = frozenset({"catalog_system", "catalog_field"})

ENTERPRISE_KINDS = frozenset(
    {
        "business_goal",
        "business_requirement",
        "business_capability",
        "business_process",
        "architecture_principle",
        "organization_role",
    }
)
ENTERPRISE_RELATIONSHIPS = frozenset(
    {
        "drives",
        "needs",
        "has_process",
        "supports",
        "satisfies",
        "governed_by",
        "owned_by",
        "depends_on",
        "impacts",
        "affects",
    }
)
SOLUTION_RELATIONSHIPS = frozenset(
    {USES_REPOSITORY, DEPLOYED_ON, CROSSES, CONNECTS_TO, CONTAINED_IN}
)

# Every action the dispatcher understands. Anything else fails closed.
KNOWN_ACTIONS = frozenset(
    {
        "create_object",
        "include_object",
        "override_object",
        "create_link",
        "set_realization",
        "record_interaction",
        "reuse_contract",
        "create_contract",
        "create_mapping",
        "create_transformation",
        "configure_resilience",
        "create_scenario",
        "define_conformance_expectation",
    }
)

INTERACTION_RELATIONSHIP = "interacts_with"

_PHASE_DIRECTIONS = {
    "request": ("source", "target"),
    "success-response": ("response_source", "response_target"),
    "async-response": ("response_source", "response_target"),
    "error-response": ("error_response_source", "error_response_target"),
}


def _as_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message, **extra},
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list | tuple)):
        return [_json_value(item) for item in value]
    return value


# --- domain writer -----------------------------------------------------------


class DomainWriter:
    """Writes approved operations into Candidate/Target state using existing models.

    Every method flushes but never commits; the caller owns the transaction.
    """

    def __init__(self, ctx: HelperContext, state: ArchitectureState) -> None:
        self.ctx = ctx
        self.db = ctx.db
        self.state = state
        self.resolved: dict[str, str] = {}

    # -- lookups --------------------------------------------------------------

    def _registry(self, object_id: UUID) -> ArchitectureObject | None:
        return self.db.scalar(
            select(ArchitectureObject).where(
                ArchitectureObject.id == object_id,
                ArchitectureObject.tenant_id == self.ctx.tenant_id,
            )
        )

    def _typed(self, kind: str, object_id: UUID):
        model = KIND_MODEL.get(kind)
        if model is None:
            return None
        return self.db.scalar(
            select(model).where(
                model.object_id == object_id,
                model.tenant_id == self.ctx.tenant_id,
            )
        )

    def _node(self, object_id: UUID) -> dict | None:
        for node in self.state.nodes:
            if str(node.get("object_id")) == str(object_id):
                return node
        return None

    def _member(self, object_id: UUID) -> ArchitectureStateMember | None:
        return self.db.scalar(
            select(ArchitectureStateMember).where(
                ArchitectureStateMember.state_id == self.state.id,
                ArchitectureStateMember.object_id == object_id,
            )
        )

    def _ensure_node(self, object_id: UUID, discipline: str | None) -> dict:
        existing = self._node(object_id)
        if existing is not None:
            return {"occurrence_id": str(existing.get("occurrence_id")), "created": False}
        occurrence_id = f"occ-{uuid4()}"
        nodes = list(self.state.nodes)
        nodes.append(
            {
                "occurrence_id": occurrence_id,
                "object_id": str(object_id),
                "position": {"x": 0.0, "y": 0.0},
                "discipline": discipline,
                "parent_occurrence_id": None,
                "width": None,
                "height": None,
                "display_metadata": {},
                "candidate_overrides": {},
            }
        )
        self.state.nodes = nodes
        self.state.updated_at = datetime.now(UTC)
        return {"occurrence_id": occurrence_id, "created": True}

    def _remove_node(self, object_id: UUID) -> None:
        self.state.nodes = [
            node for node in self.state.nodes if str(node.get("object_id")) != str(object_id)
        ]
        self.state.updated_at = datetime.now(UTC)

    def _ensure_member(
        self, object_id: UUID, membership: str = "included"
    ) -> tuple[ArchitectureStateMember, bool]:
        member = self._member(object_id)
        if member is not None:
            return member, False
        member = ArchitectureStateMember(
            id=uuid4(),
            tenant_id=self.ctx.tenant_id,
            workspace_id=self.ctx.workspace_id,
            state_id=self.state.id,
            object_id=object_id,
            membership=membership,
        )
        self.db.add(member)
        return member, True

    # -- create_object --------------------------------------------------------

    def create_object(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        kind = pv.get("kind")
        if kind not in KIND_MODEL:
            raise _conflict("unsupported_kind", f"Cannot create kind {kind!r}")
        parent_ref = pv.get("parent_ref")
        parent_id = None
        if parent_ref:
            parent_id = _as_uuid(self.resolved.get(parent_ref)) or _as_uuid(parent_ref)
        if parent_ref and parent_id is None:
            raise _conflict("missing_parent", "A created object's parent did not resolve")
        object_id = uuid4()
        registry = ArchitectureObject(id=object_id, tenant_id=self.ctx.tenant_id, kind=kind)
        self.db.add(registry)
        self.db.flush()

        values: dict[str, Any] = {
            "object_id": object_id,
            "tenant_id": self.ctx.tenant_id,
            "name": str(pv.get("name", "")).strip(),
        }
        if "description" in pv and pv.get("description") is not None:
            values["description"] = str(pv["description"]).strip()
        model = KIND_MODEL[kind]
        model_fields = set(model.__table__.columns.keys())

        def maybe(field: str, source: str | None = None) -> None:
            source = source or field
            if source in pv and pv.get(source) is not None and field in model_fields:
                values[field] = pv.get(source)

        for field in (
            "owner",
            "steward",
            "outcome_metric",
            "horizon",
            "process_type",
            "principle_type",
            "rationale",
            "role_type",
            "classification",
            "sensitivity",
            "data_type",
            "required",
            "nullable",
            "is_key",
            "is_identifier",
            "ordinal",
            "definition",
            "direction",
            "interface_kind",
            "protocol",
            "technology",
            "operation_kind",
            "responsibility",
            "component_type",
            "repository_type",
            "environment",
            "hosting",
            "security_level",
        ):
            maybe(field)
        # Parent wiring.
        if kind == "component":
            if "solution_object_id" in model_fields:
                values["solution_object_id"] = parent_id
        elif kind == "interface":
            values["component_object_id"] = parent_id
        elif kind == "interface_operation":
            values["interface_object_id"] = parent_id
        elif kind in {"data_repository", "deployment_node", "trust_boundary"}:
            values["solution_object_id"] = parent_id
        elif kind == "information_attribute":
            values["entity_object_id"] = parent_id
        elif kind == "information_object":
            values["authoritative_system_id"] = _as_uuid(pv.get("system_ref"))
        if kind == "information_attribute" and not pv.get("data_type"):
            values["data_type"] = "string"
        if "created_in_state_id" in model_fields and kind in (
            "business_goal",
            "business_process",
            "architecture_principle",
            "organization_role",
            "information_attribute",
            "component",
            "interface",
            "interface_operation",
            "data_repository",
            "deployment_node",
            "trust_boundary",
        ):
            values["created_in_state_id"] = self.state.id

        row = model(**values)
        self.db.add(row)
        self.db.flush()

        node_info: dict[str, Any] = {"created": False, "occurrence_id": None}
        member_info: dict[str, Any] = {"created": False, "member_id": None}
        if kind in CANVAS_KINDS:
            discipline = (
                "enterprise"
                if kind in ENTERPRISE_KINDS
                else "information"
                if kind == "information_object"
                else "solution"
            )
            node_info = self._ensure_node(object_id, discipline)
        elif kind in CHILD_KINDS:
            member, created = self._ensure_member(object_id)
            member_info = {"created": created, "member_id": str(member.id)}
        self.db.flush()

        temp = op.temporary_id
        if temp:
            self.resolved[temp] = str(object_id)
        ownership = {
            "role": "created",
            "kind": kind,
            "object_id": str(object_id),
            "row_id": str(object_id),
            "state_id": str(self.state.id),
            "node": node_info,
            "member": member_info,
            "reused": False,
        }
        fingerprint = {
            "object_id": str(object_id),
            "name": values.get("name"),
            "description": values.get("description"),
            "kind": kind,
            "node_occurrence_id": node_info.get("occurrence_id"),
            "member_id": member_info.get("member_id"),
        }
        return {
            "applied_id": object_id,
            "ownership": ownership,
            "post_fingerprint": fingerprint,
            "result": {"kind": kind, "object_id": str(object_id)},
        }

    # -- include_object -------------------------------------------------------

    def include_object(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        kind = pv.get("kind") or op.target_type
        object_id = op.target_id
        if object_id is None:
            raise _conflict("missing_target", "include_object needs a target")
        if kind == "catalog_system":
            node_info = self._ensure_node(object_id, None)
            ownership = {
                "role": "included",
                "kind": kind,
                "object_id": str(object_id),
                "state_id": str(self.state.id),
                "node": node_info,
                "member": {"created": False, "member_id": None},
                "reused": True,
            }
            return {
                "applied_id": object_id,
                "ownership": ownership,
                "post_fingerprint": {"object_id": str(object_id), "kind": kind},
                "result": {"kind": kind, "object_id": str(object_id)},
            }
        if kind in CHILD_KINDS:
            member, created = self._ensure_member(object_id)
            ownership = {
                "role": "included",
                "kind": kind,
                "object_id": str(object_id),
                "state_id": str(self.state.id),
                "member": {"created": created, "member_id": str(member.id)},
                "reused": True,
            }
        else:
            node_info = self._ensure_node(
                object_id,
                "enterprise"
                if kind in ENTERPRISE_KINDS
                else "information"
                if kind == "information_object"
                else "solution"
                if kind in CANVAS_KINDS
                else None,
            )
            ownership = {
                "role": "included",
                "kind": kind,
                "object_id": str(object_id),
                "state_id": str(self.state.id),
                "node": node_info,
                "reused": True,
            }
        return {
            "applied_id": object_id,
            "ownership": ownership,
            "post_fingerprint": {"object_id": str(object_id), "kind": kind},
            "result": {"kind": kind, "object_id": str(object_id)},
        }

    # -- override_object ------------------------------------------------------

    def override_object(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        kind = pv.get("kind") or op.target_type
        object_id = op.target_id
        changes = dict(pv.get("changes") or {})
        if object_id is None or not changes:
            raise _conflict("nothing_to_override", "override_object had no scalar changes")
        before = dict(op.before_value or {})
        # Immediate before-value check: the canonical row must still match.
        row = self._typed(kind, object_id)
        if row is not None:
            for field, expected in before.items():
                if getattr(row, field, None) != expected:
                    raise _conflict(
                        "before_value_conflict",
                        f"{kind}.{field} changed since the proposal was created",
                        field=field,
                    )
        if kind in ENTERPRISE_KINDS:
            node = self._node(object_id)
            if node is None:
                raise _conflict("unknown_target", "The object is not in the target state")
            prior = dict(node.get("candidate_overrides") or {})
            updated = list(self.state.nodes)
            for index, item in enumerate(updated):
                if str(item.get("object_id")) == str(object_id):
                    merged = dict(item.get("candidate_overrides") or {})
                    merged.update(changes)
                    replacement = dict(item)
                    replacement["candidate_overrides"] = merged
                    updated[index] = replacement
            self.state.nodes = updated
            self.state.updated_at = datetime.now(UTC)
            storage = "node"
            member_id = None
        else:
            member = self._member(object_id)
            if member is None:
                member, _ = self._ensure_member(object_id)
            prior = dict(member.property_overrides or {})
            merged = dict(prior)
            merged.update(changes)
            member.membership = "included"
            member.property_overrides = merged
            storage = "member"
            member_id = str(member.id)
        self.db.flush()
        ownership = {
            "role": "overridden",
            "kind": kind,
            "object_id": str(object_id),
            "state_id": str(self.state.id),
            "storage": storage,
            "member_id": member_id,
            "applied": _json_value(changes),
            "prior": {key: prior.get(key) for key in changes},
            "prior_present": {key: key in prior for key in changes},
            "reused": True,
        }
        return {
            "applied_id": object_id,
            "ownership": ownership,
            "post_fingerprint": {"object_id": str(object_id), "changes": _json_value(changes)},
            "result": {"kind": kind, "object_id": str(object_id), "changes": list(changes)},
        }

    # -- create_link ----------------------------------------------------------

    def create_link(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        if pv.get("unresolved"):
            raise _conflict("unresolved_operation", "An unresolved operation cannot be applied")
        relationship = pv.get("relationship_type")
        source_id = _as_uuid(self.resolved.get(pv.get("source_ref"), pv.get("source_ref")))
        target_id = _as_uuid(self.resolved.get(pv.get("target_ref"), pv.get("target_ref")))
        if source_id is None or target_id is None:
            raise _conflict("unresolved_endpoint", "A link endpoint did not resolve")
        if source_id == target_id:
            raise _conflict("self_link", "A link must connect two different objects")
        source = self._registry(source_id)
        target = self._registry(target_id)
        if source is None or target is None:
            raise _conflict("unknown_target", "A link endpoint is not an architecture object")
        self._check_link_rule(relationship, source.kind, target.kind)
        properties: dict[str, Any] = {}
        for field in ("name", "cardinality", "source_optional", "target_optional"):
            if pv.get(field) is not None:
                properties[field] = pv[field]
        relationship_id = uuid4()
        self.db.add(
            ArchitectureRelationship(
                id=relationship_id,
                tenant_id=self.ctx.tenant_id,
                source_object_id=source_id,
                target_object_id=target_id,
                relationship_type=relationship,
                properties=properties,
                created_in_state_id=self.state.id,
            )
        )
        self.db.flush()
        ownership = {
            "role": "linked",
            "kind": "relationship",
            "relationship_id": str(relationship_id),
            "relationship_type": relationship,
            "source_object_id": str(source_id),
            "target_object_id": str(target_id),
            "state_id": str(self.state.id),
            "properties": _json_value(properties),
            "reused": False,
        }
        return {
            "applied_id": relationship_id,
            "ownership": ownership,
            "post_fingerprint": {
                "relationship_id": str(relationship_id),
                "properties": _json_value(properties),
            },
            "result": {
                "relationship_type": relationship,
                "source_object_id": str(source_id),
                "target_object_id": str(target_id),
            },
        }

    def _check_link_rule(self, relationship: str, source_kind: str, target_kind: str) -> None:
        if relationship == ER_EDGE_TYPE:
            if source_kind != "information_object" or target_kind != "information_object":
                raise _conflict("link_rule", "'references' connects two information entities")
            return
        if relationship in SOLUTION_RELATIONSHIPS:
            if relationship == CONNECTS_TO:
                return
            if relationship == USES_REPOSITORY and target_kind != "data_repository":
                raise _conflict("link_rule", "uses_repository targets a repository")
            if relationship == DEPLOYED_ON and target_kind != "deployment_node":
                raise _conflict("link_rule", "deployed_on targets a deployment node")
            if relationship in {CROSSES, CONTAINED_IN} and target_kind != "trust_boundary":
                raise _conflict("link_rule", f"{relationship} targets a trust boundary")
            return
        if relationship in ENTERPRISE_RELATIONSHIPS:
            return
        raise _conflict("unknown_relationship", f"Unknown relationship {relationship!r}")

    # -- set_realization ------------------------------------------------------

    def set_realization(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        if pv.get("unresolved") or not pv.get("resolved"):
            raise _conflict("unresolved_operation", "An unresolved realization cannot be applied")
        attribute_id = _as_uuid(self.resolved.get(pv.get("attribute_ref"), pv.get("attribute_ref")))
        field_id = _as_uuid(pv.get("catalog_field_id"))
        if attribute_id is None or field_id is None:
            raise _conflict("unresolved_endpoint", "A realization reference did not resolve")
        field = self.db.scalar(
            select(CatalogField).where(
                CatalogField.id == field_id,
                CatalogField.tenant_id == self.ctx.tenant_id,
                CatalogField.deleted_at.is_(None),
            )
        )
        if field is None:
            raise _conflict("unknown_target", "The Catalog field is not active")
        field_ref = self.db.scalar(
            select(ArchitectureObject).where(
                ArchitectureObject.tenant_id == self.ctx.tenant_id,
                ArchitectureObject.kind == "catalog_field_ref",
                ArchitectureObject.catalog_field_id == field.id,
            )
        )
        field_ref_created = False
        if field_ref is None:
            field_ref = ArchitectureObject(
                id=uuid4(),
                tenant_id=self.ctx.tenant_id,
                kind="catalog_field_ref",
                catalog_field_id=field.id,
            )
            self.db.add(field_ref)
            self.db.flush()
            field_ref_created = True
        relationship_id = uuid4()
        self.db.add(
            ArchitectureRelationship(
                id=relationship_id,
                tenant_id=self.ctx.tenant_id,
                source_object_id=attribute_id,
                target_object_id=field_ref.id,
                relationship_type=REALIZES_EDGE_TYPE,
                properties={"catalog_object_id": str(field.object_id)},
                created_in_state_id=self.state.id,
            )
        )
        self.db.flush()
        ownership = {
            "role": "realized",
            "kind": "realization",
            "relationship_id": str(relationship_id),
            "attribute_object_id": str(attribute_id),
            "field_ref_id": str(field_ref.id),
            "field_ref_created": field_ref_created,
            "catalog_field_id": str(field.id),
            "state_id": str(self.state.id),
            "reused": False,
        }
        return {
            "applied_id": relationship_id,
            "ownership": ownership,
            "post_fingerprint": {"relationship_id": str(relationship_id)},
            "result": {"attribute_object_id": str(attribute_id), "catalog_field_id": str(field.id)},
        }

    # -- record_interaction ---------------------------------------------------

    def record_interaction(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        if pv.get("unresolved"):
            raise _conflict("unresolved_operation", "An interaction without evidence cannot apply")
        source_id = _as_uuid(self.resolved.get(pv.get("source_ref"), pv.get("source_ref")))
        target_id = _as_uuid(self.resolved.get(pv.get("target_ref"), pv.get("target_ref")))
        if source_id is None or target_id is None:
            raise _conflict("unresolved_endpoint", "An interaction endpoint did not resolve")
        if source_id == target_id:
            raise _conflict("self_interaction", "An interaction must connect two systems")
        properties = {
            "evidence_refs": list(pv.get("evidence_refs") or []),
            "description": pv.get("description"),
        }
        relationship_id = uuid4()
        self.db.add(
            ArchitectureRelationship(
                id=relationship_id,
                tenant_id=self.ctx.tenant_id,
                source_object_id=source_id,
                target_object_id=target_id,
                relationship_type=INTERACTION_RELATIONSHIP,
                properties=properties,
                created_in_state_id=self.state.id,
            )
        )
        self.db.flush()
        ownership = {
            "role": "linked",
            "kind": "interaction",
            "relationship_id": str(relationship_id),
            "relationship_type": INTERACTION_RELATIONSHIP,
            "source_object_id": str(source_id),
            "target_object_id": str(target_id),
            "state_id": str(self.state.id),
            "properties": _json_value(properties),
            "reused": False,
        }
        return {
            "applied_id": relationship_id,
            "ownership": ownership,
            "post_fingerprint": {
                "relationship_id": str(relationship_id),
                "properties": _json_value(properties),
            },
            "result": {
                "source_object_id": str(source_id),
                "target_object_id": str(target_id),
            },
        }

    # -- integration ----------------------------------------------------------

    def _contract(self, ref: Any) -> Integration | None:
        contract_id = _as_uuid(self.resolved.get(ref, ref))
        if contract_id is None:
            return None
        return self.db.scalar(
            select(Integration).where(
                Integration.id == contract_id,
                Integration.tenant_id == self.ctx.tenant_id,
                Integration.deleted_at.is_(None),
            )
        )

    def reuse_contract(self, op: HelperChangeOperation) -> dict[str, Any]:
        contract = self._contract(op.target_id)
        if contract is None:
            raise _conflict("unknown_target", "The reused Contract is not active")
        ownership = {
            "role": "reused",
            "kind": "contract",
            "contract_id": str(contract.id),
            "revision": contract.revision,
            "reused": True,
        }
        return {
            "applied_id": contract.id,
            "ownership": ownership,
            "post_fingerprint": {"contract_id": str(contract.id), "revision": contract.revision},
            "result": {"contract_id": str(contract.id), "revision": contract.revision},
        }

    def create_contract(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        specification = pv.get("specification") or {}
        contract = Integration(
            tenant_id=self.ctx.tenant_id,
            source_system_id=_as_uuid(pv.get("source_system_id")),
            source_object_id=_as_uuid(pv.get("source_object_id")),
            target_system_id=_as_uuid(pv.get("target_system_id")),
            target_object_id=_as_uuid(pv.get("target_object_id")),
            name=str(pv.get("name", "")).strip(),
            description=pv.get("description"),
            trigger_config={},
            graph={"version": 1, "nodes": [], "edges": []},
            response_graph={"version": 1, "nodes": [], "edges": []},
            error_response_graph={"version": 1, "nodes": [], "edges": []},
            error_response_object_id=_as_uuid(pv.get("error_response_object_id")),
            interaction_type=pv.get("interaction_type") or "ONE_WAY",
            pattern=pv.get("pattern"),
            implementation_status=pv.get("implementation_status") or "draft",
            producer_interface_id=_as_uuid(pv.get("producer_interface_id")),
            consumer_interface_id=_as_uuid(pv.get("consumer_interface_id")),
            specification=specification,
            sample_rows=[],
            revision=1,
        )
        self.db.add(contract)
        self.db.flush()
        temp = op.temporary_id
        if temp:
            self.resolved[temp] = str(contract.id)
        ownership = {
            "role": "created",
            "kind": "contract",
            "contract_id": str(contract.id),
            "revision": 1,
            "based_on_contract_id": pv.get("based_on_contract_id"),
            "proposal_intent": pv.get("proposal_intent"),
            "reused": False,
        }
        return {
            "applied_id": contract.id,
            "ownership": ownership,
            "post_fingerprint": {"contract_id": str(contract.id), "revision": 1},
            "result": {"contract_id": str(contract.id), "revision": 1},
        }

    def create_mapping(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        if pv.get("unresolved") or not pv.get("resolved"):
            raise _conflict("unresolved_operation", "An unresolved mapping cannot be applied")
        if pv.get("contract_ref") not in self.resolved:
            raise _conflict(
                "reused_contract_mutation", "Mappings may only target a new draft Contract"
            )
        contract = self._contract(pv.get("contract_ref"))
        if contract is None:
            raise _conflict("unknown_target", "The mapping Contract did not resolve")
        phase = pv.get("phase") or "request"
        source_direction, target_direction = _PHASE_DIRECTIONS.get(phase, ("source", "target"))
        created: list[str] = []
        pairs = (
            (str(pv.get("source_object_id")), pv.get("source_field_id"), source_direction),
            (str(pv.get("target_object_id")), pv.get("target_field_id"), target_direction),
        )
        for object_id, field_id, direction in pairs:
            obj = _as_uuid(object_id)
            field = _as_uuid(field_id)
            if obj is None or field is None:
                raise _conflict("unresolved_endpoint", "The mapping field did not resolve")
            existing = self.db.scalar(
                select(IntegrationFieldRef).where(
                    IntegrationFieldRef.integration_id == contract.id,
                    IntegrationFieldRef.tenant_id == self.ctx.tenant_id,
                    IntegrationFieldRef.field_id == field,
                    IntegrationFieldRef.direction == direction,
                )
            )
            if existing is not None:
                continue
            ref_id = uuid4()
            self.db.add(
                IntegrationFieldRef(
                    id=ref_id,
                    tenant_id=self.ctx.tenant_id,
                    integration_id=contract.id,
                    object_id=obj,
                    field_id=field,
                    direction=direction,
                )
            )
            created.append(str(ref_id))
        self.db.flush()
        ownership = {
            "role": "configured",
            "kind": "mapping",
            "contract_id": str(contract.id),
            "phase": phase,
            "field_ref_ids": created,
            "reused": bool(contract.revision and False),
        }
        return {
            "applied_id": contract.id,
            "ownership": ownership,
            "post_fingerprint": {
                "contract_id": str(contract.id),
                "field_ref_ids": sorted(created),
            },
            "result": {
                "contract_id": str(contract.id),
                "phase": phase,
                "field_refs_created": len(created),
            },
        }

    def _phase_graph_name(self, phase: str) -> str:
        if phase == "request":
            return "graph"
        if phase in {"success-response", "async-response"}:
            return "response_graph"
        return "error_response_graph"

    def _phase_graph_references(self, contract: Integration, phase: str, graph: dict):
        if phase == "request":
            return graph_references(
                self.db,
                self.ctx.tenant_id,
                contract.source_object_id,
                contract.target_object_id,
                GraphDocument.model_validate(graph),
                response=False,
            )
        if phase == "error-response":
            if contract.error_response_object_id is None:
                raise _conflict("missing_error_schema", "The error-response phase has no schema")
            return graph_references(
                self.db,
                self.ctx.tenant_id,
                contract.source_object_id,
                contract.error_response_object_id,
                GraphDocument.model_validate(graph),
                response=True,
                response_phase="error_response",
            )
        return graph_references(
            self.db,
            self.ctx.tenant_id,
            contract.source_object_id,
            contract.target_object_id,
            GraphDocument.model_validate(graph),
            response=True,
            response_phase="response",
        )

    def _phase_sender_receiver(self, contract: Integration, phase: str) -> tuple[UUID, UUID]:
        if phase == "request":
            return contract.source_object_id, contract.target_object_id
        if phase == "error-response":
            if contract.error_response_object_id is None:
                raise _conflict("missing_error_schema", "The error-response phase has no schema")
            return contract.error_response_object_id, contract.source_object_id
        return contract.target_object_id, contract.source_object_id

    def create_transformation(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        if pv.get("contract_ref") not in self.resolved:
            raise _conflict(
                "reused_contract_mutation",
                "Transformations may only target a new draft Contract",
            )
        contract = self._contract(pv.get("contract_ref"))
        if contract is None:
            raise _conflict("unknown_target", "The transformation Contract did not resolve")
        phase = pv.get("phase") or "request"
        node_type = pv.get("node_type")
        config = dict(pv.get("config") or {})
        source_field_ids = [_as_uuid(item) for item in (pv.get("source_field_ids") or [])]
        target_field_id = _as_uuid(pv.get("target_field_id"))
        sender_object, receiver_object = self._phase_sender_receiver(contract, phase)
        sender_fields = {field.id for field in matching.list_active_fields(self.ctx, sender_object)}
        receiver_fields = {
            field.id for field in matching.list_active_fields(self.ctx, receiver_object)
        }
        for field_id in source_field_ids:
            if field_id is None or field_id not in sender_fields:
                raise _conflict(
                    "unknown_target", "A transformation source field is not a sender field"
                )
        if target_field_id is None or target_field_id not in receiver_fields:
            raise _conflict(
                "unknown_target", "The transformation target field is not a receiver field"
            )

        graph_name = self._phase_graph_name(phase)
        graph = dict(getattr(contract, graph_name) or {"version": 1, "nodes": [], "edges": []})
        nodes = list(graph.get("nodes") or [])
        edges = list(graph.get("edges") or [])
        source_node_id = _find_endpoint_node(nodes, "source")
        if source_node_id is None:
            source_node_id = str(uuid4())
            nodes.append({"id": source_node_id, "type": "source", "position": {"x": 0.0, "y": 0.0}})
        target_node_id = _find_endpoint_node(nodes, "target")
        if target_node_id is None:
            target_node_id = str(uuid4())
            nodes.append(
                {"id": target_node_id, "type": "target", "position": {"x": 400.0, "y": 0.0}}
            )
        transform_node_id = str(uuid4())
        nodes.append(
            {
                "id": transform_node_id,
                "type": node_type,
                "position": {"x": 200.0, "y": 0.0},
                "config": config,
            }
        )
        for field_id in source_field_ids:
            edges.append(
                {
                    "id": str(uuid4()),
                    "sourceNodeId": source_node_id,
                    "sourcePortId": f"field:{field_id}",
                    "targetNodeId": transform_node_id,
                    "targetPortId": "input",
                }
            )
        edges.append(
            {
                "id": str(uuid4()),
                "sourceNodeId": transform_node_id,
                "sourcePortId": "output",
                "targetNodeId": target_node_id,
                "targetPortId": f"field:{target_field_id}",
            }
        )
        candidate_graph = {"version": 1, "nodes": nodes, "edges": edges}
        try:
            self._phase_graph_references(contract, phase, candidate_graph)
        except GraphValidationError as error:
            raise _conflict(
                "invalid_transformation",
                "The transformation graph is invalid",
                issues=[issue.model_dump() for issue in error.issues][:10],
            ) from error
        setattr(contract, graph_name, candidate_graph)
        self.db.flush()
        ownership = {
            "role": "configured",
            "kind": "transformation",
            "contract_id": str(contract.id),
            "phase": phase,
            "node_ids": [transform_node_id, source_node_id, target_node_id],
            "reversed_with_contract": True,
            "reused": False,
        }
        return {
            "applied_id": contract.id,
            "ownership": ownership,
            "post_fingerprint": {"contract_id": str(contract.id), "phase": phase},
            "result": {
                "contract_id": str(contract.id),
                "phase": phase,
                "node_id": transform_node_id,
            },
        }

    def configure_resilience(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        ref = pv.get("contract_ref")
        # A reused Contract is read-only: only a change-set-owned draft may be configured.
        if _as_uuid(ref) is not None:
            raise _conflict("reused_contract_mutation", "A reused Contract cannot be reconfigured")
        contract = self._contract(ref)
        if contract is None:
            raise _conflict("unknown_target", "The resilience Contract did not resolve")
        if ref not in self.resolved:
            raise _conflict("reused_contract_mutation", "A reused Contract cannot be reconfigured")
        contract.specification = dict(pv.get("specification") or {})
        self.db.flush()
        ownership = {
            "role": "configured",
            "kind": "resilience",
            "contract_id": str(contract.id),
            "reused": False,
        }
        return {
            "applied_id": contract.id,
            "ownership": ownership,
            "post_fingerprint": {"contract_id": str(contract.id)},
            "result": {"contract_id": str(contract.id)},
        }

    def create_scenario(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        ref = pv.get("contract_ref")
        contract = self._contract(ref)
        if contract is None:
            raise _conflict("unknown_target", "The scenario Contract did not resolve")
        placeholder = str(pv.get("contract_uuid") or "")
        real = str(contract.id)
        document = _replace_reference(pv.get("document") or {}, placeholder, real)
        try:
            parsed = ScenarioDocument.model_validate(document)
        except Exception as error:  # noqa: BLE001 - convert to a structured conflict
            raise _conflict("invalid_scenario", "The scenario document is invalid") from error
        document = document_json(parsed)
        try:
            validate_for_save(self.db, self.ctx.tenant_id, parsed, contract.id)
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, dict) else {"message": error.detail}
            raise _conflict(
                "invalid_scenario_reference",
                str(detail.get("message", "The scenario references are invalid")),
            ) from error
        scenario = Scenario(
            tenant_id=self.ctx.tenant_id,
            scope_integration_id=contract.id,
            name=str(pv.get("name", "")).strip(),
            category=pv.get("category") or "happy_path",
            description=pv.get("scenario_type"),
            document=document,
            revision=1,
        )
        self.db.add(scenario)
        try:
            self.db.flush()
        except IntegrityError as error:
            raise _conflict(
                "duplicate_scenario", "An active scenario with this name already exists"
            ) from error
        temp = op.temporary_id
        if temp:
            self.resolved[temp] = str(scenario.id)
        ownership = {
            "role": "created",
            "kind": "scenario",
            "scenario_id": str(scenario.id),
            "contract_id": str(contract.id),
            "revision": 1,
            "reused": False,
        }
        return {
            "applied_id": scenario.id,
            "ownership": ownership,
            "post_fingerprint": {"scenario_id": str(scenario.id), "revision": 1},
            "result": {"scenario_id": str(scenario.id), "contract_id": str(contract.id)},
        }

    def define_conformance_expectation(self, op: HelperChangeOperation) -> dict[str, Any]:
        pv = op.proposed_value or {}
        contract = self._contract(pv.get("contract_ref"))
        if contract is None:
            raise _conflict("unknown_target", "The conformance Contract did not resolve")
        scenario_id = None
        if pv.get("scenario_ref"):
            scenario_id = self.resolved.get(pv["scenario_ref"], pv["scenario_ref"])
        ownership = {
            "role": "defined",
            "kind": "conformance",
            "contract_id": str(contract.id),
            "scenario_id": str(scenario_id) if scenario_id else None,
            "expectation_type": pv.get("expectation_type"),
            "definition_only": True,
            "reused": False,
        }
        return {
            "applied_id": contract.id,
            "ownership": ownership,
            "post_fingerprint": {"contract_id": str(contract.id)},
            "result": {
                "contract_id": str(contract.id),
                "expectation_type": pv.get("expectation_type"),
            },
        }


def _find_endpoint_node(nodes: list[dict], node_type: str) -> str | None:
    for node in nodes:
        if node.get("type") == node_type:
            return str(node.get("id"))
    return None


def _replace_reference(value: Any, old: str, new: str) -> Any:
    if not old:
        return value
    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, dict):
        return {key: _replace_reference(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_reference(item, old, new) for item in value]
    return value


# --- ordering ----------------------------------------------------------------


def topological_order(
    operations: list[HelperChangeOperation],
) -> list[HelperChangeOperation]:
    by_id = {op.operation_id: op for op in operations}
    ordered: list[HelperChangeOperation] = []
    state: dict[str, int] = {}

    def visit(op: HelperChangeOperation) -> None:
        marker = state.get(op.operation_id, 0)
        if marker == 2:
            return
        if marker == 1:
            raise _conflict("dependency_cycle", "The operation graph contains a cycle")
        state[op.operation_id] = 1
        for dep in op.depends_on or []:
            parent = by_id.get(dep)
            if parent is not None:
                visit(parent)
        state[op.operation_id] = 2
        ordered.append(op)

    for op in sorted(operations, key=lambda item: (item.ordinal, item.operation_id)):
        visit(op)
    return ordered


# --- apply -------------------------------------------------------------------


def apply_change_set(ctx: HelperContext, change_set: HelperChangeSet) -> dict[str, Any]:
    from app.helper_actions import service

    operations = service.load_operations(ctx.db, change_set.id)
    service.add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="apply_requested",
        change_set_id=change_set.id,
        state_id=change_set.state_id,
        summary={"status": change_set.status, "operation_count": len(operations)},
    )
    ctx.db.commit()

    def fail(code: str, message: str, **extra: Any) -> None:
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="apply_precondition_failed",
            change_set_id=change_set.id,
            state_id=change_set.state_id,
            summary={"code": code, "message": message},
        )
        ctx.db.commit()
        raise _conflict(code, message, **extra)

    if change_set.status == "applied":
        fail("already_applied", "The change set has already been applied")
    if change_set.status == "undone":
        fail("already_undone", "The change set has been undone and cannot be re-applied")
    if change_set.status != "approved":
        fail("not_approved", "Only an approved change set can be applied")
    if not change_set.approved_hash or change_set.approved_hash != change_set.proposal_hash:
        fail("approval_hash_mismatch", "The approval does not match the proposal hash")

    # Revalidate the complete proposal against current context.
    try:
        service.validate_change_set(ctx, change_set)
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {"message": error.detail}
        fail(str(detail.get("code", "stale")), str(detail.get("message", "Proposal is stale")))
    if change_set.status != "validated":
        fail("validation_failed", "The proposal failed revalidation")
    summary = change_set.validation_summary or {}
    if not summary.get("ready_for_approval", True):
        fail(
            "unresolved_decisions",
            "Required unresolved decisions remain; resolve them before applying",
            unresolved_decisions=summary.get("unresolved_decisions", []),
        )
    operations = service.load_operations(ctx.db, change_set.id)
    if service.compute_proposal_hash(change_set, operations) != change_set.approved_hash:
        fail("proposal_stale", "The proposal changed after approval")

    # Static precondition checks.
    state = None
    if change_set.state_id is not None:
        state = get_state(ctx.db, ctx.workspace, change_set.state_id)
    if state is None or state.state_type == "current":
        fail("current_target", "A helper apply cannot target the Current state")
    for op in operations:
        if op.domain_action not in KNOWN_ACTIONS:
            fail("unknown_operation", f"Unknown operation type {op.domain_action!r}")
        if (
            op.domain_action == "create_object"
            and (op.proposed_value or {}).get("kind") in CATALOG_KINDS
        ):
            fail("catalog_creation", "Helpers never create Catalog records")
    try:
        ordered = topological_order(operations)
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        fail(
            str(detail.get("code", "dependency_cycle")),
            "The operation graph is invalid",
        )

    # Before-value and reused-reference checks.
    for op in operations:
        if op.domain_action == "override_object":
            kind = (op.proposed_value or {}).get("kind") or op.target_type
            row = _typed_row(ctx, kind, op.target_id)
            if row is None:
                fail("unknown_target", "An override target is not active")
            for field, expected in (op.before_value or {}).items():
                if getattr(row, field, None) != expected:
                    fail(
                        "before_value_conflict",
                        f"{kind}.{field} changed since the proposal was created",
                        field=field,
                    )
        if op.domain_action == "reuse_contract" and op.target_id is not None:
            contract = ctx.db.scalar(
                select(Integration).where(
                    Integration.id == op.target_id,
                    Integration.tenant_id == ctx.tenant_id,
                    Integration.deleted_at.is_(None),
                )
            )
            if contract is None:
                fail("unknown_target", "A reused Contract is no longer active")

    wb = DomainWriter(ctx, state)
    service.add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="apply_started",
        change_set_id=change_set.id,
        state_id=state.id,
        summary={"operation_count": len(ordered), "state_type": state.state_type},
    )
    ctx.db.commit()

    applied: list[dict[str, Any]] = []
    contract_revisions: list[dict[str, Any]] = []
    try:
        for op in ordered:
            handler = _DISPATCH.get(op.domain_action)
            if handler is None:
                raise _conflict("unknown_operation", f"Unknown operation {op.domain_action!r}")
            result = handler(wb, op)
            op.applied_id = result["applied_id"]
            op.apply_status = "applied"
            op.ownership = result["ownership"]
            op.post_fingerprint = result["post_fingerprint"]
            op.undo_status = "pending"
            applied.append(
                {
                    "operation_id": op.operation_id,
                    "domain_action": op.domain_action,
                    "applied_id": str(result["applied_id"]),
                    "role": result["ownership"].get("role"),
                    "result": result["result"],
                }
            )
            if result["ownership"].get("kind") == "contract":
                contract_revisions.append(
                    {
                        "contract_id": str(result["applied_id"]),
                        "revision": result["ownership"].get("revision", 1),
                        "role": result["ownership"].get("role"),
                    }
                )
            service.add_audit(
                ctx.db,
                tenant_id=ctx.tenant_id,
                workspace_id=ctx.workspace_id,
                user_id=ctx.user.id,
                event_type="operation_applied",
                change_set_id=change_set.id,
                state_id=state.id,
                summary={
                    "operation_id": op.operation_id,
                    "domain_action": op.domain_action,
                },
            )
        resolution = {temp: real for temp, real in wb.resolved.items()}
        affected_objects = sorted(
            {str(op.applied_id) for op in operations if op.applied_id is not None}
        )
        affected_workbenches = _affected_workbenches(operations)
        change_set.apply_summary = {
            "applied_operation_count": len(applied),
            "resolution_map": resolution,
            "contract_revisions": contract_revisions,
            "affected_objects": affected_objects,
            "affected_workbenches": affected_workbenches,
            "applied_at": datetime.now(UTC).isoformat(),
        }
        change_set.status = "applied"
        change_set.applied_at = datetime.now(UTC)
        change_set.updated_at = datetime.now(UTC)
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="apply_completed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={
                "applied_operation_count": len(applied),
                "state_type": state.state_type,
                "affected_workbenches": affected_workbenches,
            },
            affected_contract_ids=[item["contract_id"] for item in contract_revisions],
        )
        ctx.db.commit()
    except HTTPException as error:
        ctx.db.rollback()
        detail = error.detail if isinstance(error.detail, dict) else {"message": error.detail}
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="apply_rolled_back",
            change_set_id=change_set.id,
            state_id=change_set.state_id,
            summary={
                "code": str(detail.get("code", "operation_failed")),
                "message": str(detail.get("message", "An operation failed")),
            },
        )
        ctx.db.commit()
        raise
    except Exception:
        ctx.db.rollback()
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="apply_rolled_back",
            change_set_id=change_set.id,
            state_id=change_set.state_id,
            summary={"code": "operation_failed"},
        )
        ctx.db.commit()
        raise

    ctx.db.refresh(change_set)
    latest = service.load_operations(ctx.db, change_set.id)
    applied_by_id = {item["operation_id"]: item for item in applied}
    return {
        "status": "applied",
        "applied_operation_count": len(applied),
        "resolution_map": change_set.apply_summary.get("resolution_map", {}),
        "applied_operations": [
            {**applied_by_id[op.operation_id], "apply_status": op.apply_status}
            for op in latest
            if op.operation_id in applied_by_id
        ],
        "contract_revisions": contract_revisions,
        "affected_objects": sorted(
            {str(op.applied_id) for op in latest if op.applied_id is not None}
        ),
        "affected_workbenches": _affected_workbenches(latest),
        "warnings": list(change_set.warnings or []),
        "conflicts": [],
        "audit_event_ref": str(change_set.id),
    }


def _typed_row(ctx: HelperContext, kind: str, object_id: UUID | None):
    if object_id is None:
        return None
    model = KIND_MODEL.get(kind)
    if model is None:
        return None
    return ctx.db.scalar(
        select(model).where(model.object_id == object_id, model.tenant_id == ctx.tenant_id)
    )


def _affected_workbenches(operations: list[HelperChangeOperation]) -> list[str]:
    workbenches: set[str] = set()
    for op in operations:
        kind = (op.proposed_value or {}).get("kind") or op.target_type
        if kind in ENTERPRISE_KINDS:
            workbenches.add("enterprise")
        elif kind in {"information_object", "information_attribute", "realization"}:
            workbenches.add("information")
        elif kind in {
            "solution_boundary",
            "component",
            "interface",
            "interface_operation",
            "data_repository",
            "deployment_node",
            "trust_boundary",
            "interaction",
            "relationship",
        }:
            workbenches.add("solution")
        if op.domain_action in {
            "reuse_contract",
            "create_contract",
            "create_mapping",
            "create_transformation",
            "configure_resilience",
            "create_scenario",
            "define_conformance_expectation",
        }:
            workbenches.add("integration")
    return sorted(workbenches)


# The closed dispatch table. Every entry is an explicit method; there is no
# fallback executor for unknown actions.
_DISPATCH = {
    "create_object": DomainWriter.create_object,
    "include_object": DomainWriter.include_object,
    "override_object": DomainWriter.override_object,
    "create_link": DomainWriter.create_link,
    "set_realization": DomainWriter.set_realization,
    "record_interaction": DomainWriter.record_interaction,
    "reuse_contract": DomainWriter.reuse_contract,
    "create_contract": DomainWriter.create_contract,
    "create_mapping": DomainWriter.create_mapping,
    "create_transformation": DomainWriter.create_transformation,
    "configure_resilience": DomainWriter.configure_resilience,
    "create_scenario": DomainWriter.create_scenario,
    "define_conformance_expectation": DomainWriter.define_conformance_expectation,
}


# --- undo --------------------------------------------------------------------


def _owned_sets(
    operations: list[HelperChangeOperation],
) -> tuple[set[str], set[str], set[str], set[str]]:
    object_ids: set[str] = set()
    relationship_ids: set[str] = set()
    contract_ids: set[str] = set()
    scenario_ids: set[str] = set()
    for op in operations:
        ownership = op.ownership or {}
        role = ownership.get("role")
        kind = ownership.get("kind")
        if kind == "contract" and role == "created":
            contract_ids.add(str(ownership.get("contract_id")))
        if kind == "scenario":
            scenario_ids.add(str(ownership.get("scenario_id")))
        if role == "created" and kind in DISCIPLINE_KINDS:
            object_ids.add(str(ownership.get("object_id")))
        if ownership.get("relationship_id"):
            relationship_ids.add(str(ownership["relationship_id"]))
    return object_ids, relationship_ids, contract_ids, scenario_ids


def _external_object_reference(
    ctx: HelperContext,
    object_id: UUID,
    owned_objects: set[str],
    owned_relationships: set[str],
) -> str | None:
    # An external relationship touching the object.
    rows = list(
        ctx.db.scalars(
            select(ArchitectureRelationship.id).where(
                ArchitectureRelationship.tenant_id == ctx.tenant_id,
                or_(
                    ArchitectureRelationship.source_object_id == object_id,
                    ArchitectureRelationship.target_object_id == object_id,
                ),
            )
        )
    )
    for relationship_id in rows:
        if str(relationship_id) not in owned_relationships:
            return "relationship"
    # An external child object pointing at it.
    child_checks = (
        (ArchitectureInterface, "component_object_id"),
        (InterfaceOperation, "interface_object_id"),
    )
    for model, column in child_checks:
        for child_id in ctx.db.scalars(
            select(model.object_id).where(
                model.tenant_id == ctx.tenant_id,
                getattr(model, column) == object_id,
            )
        ):
            if str(child_id) not in owned_objects:
                return "child"
    return None


def _build_undo_plan(
    ctx: HelperContext,
    change_set: HelperChangeSet,
    ordered: list[HelperChangeOperation],
) -> list[dict[str, Any]]:
    operations = ordered
    owned_objects, owned_relationships, owned_contracts, owned_scenarios = _owned_sets(operations)
    plan: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for op in reversed(ordered):
        ownership = op.ownership or {}
        role = ownership.get("role")
        kind = ownership.get("kind")
        step = {"operation_id": op.operation_id, "role": role, "kind": kind, "action": "skip"}
        if role == "created" and kind in DISCIPLINE_KINDS:
            object_id = _as_uuid(ownership.get("object_id"))
            row = _typed_row(ctx, kind, object_id)
            if row is None:
                step["action"] = "skip"
            elif getattr(row, "name", None) != op.post_fingerprint.get("name"):
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "object_modified",
                        "message": f"{kind} was changed after apply",
                    }
                )
            elif _membership_changed(ctx, change_set, ownership):
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "membership_modified",
                        "message": f"{kind} state membership or occurrence changed after apply",
                    }
                )
            else:
                external = _external_object_reference(
                    ctx, object_id, owned_objects, owned_relationships
                )
                if external is not None:
                    conflicts.append(
                        {
                            "operation_id": op.operation_id,
                            "code": "external_reference",
                            "message": f"{kind} is referenced outside this change set",
                        }
                    )
                else:
                    step["action"] = "delete_object"
        elif role == "overridden":
            step["action"] = "restore_override"
            current = _current_override_value(ctx, change_set, ownership)
            if current != ownership.get("applied"):
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "override_modified",
                        "message": "The overridden value changed after apply",
                    }
                )
        elif role == "linked":
            relationship_id = _as_uuid(ownership.get("relationship_id"))
            edge = ctx.db.get(ArchitectureRelationship, relationship_id)
            if edge is None:
                step["action"] = "skip"
            elif _json_value(dict(edge.properties or {})) != ownership.get("properties"):
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "relationship_modified",
                        "message": "The relationship changed after apply",
                    }
                )
            else:
                step["action"] = "delete_relationship"
        elif role == "realized":
            relationship_id = _as_uuid(ownership.get("relationship_id"))
            edge = ctx.db.get(ArchitectureRelationship, relationship_id)
            step["action"] = "delete_relationship" if edge is not None else "skip"
        elif role == "included":
            step["action"] = "uninclude"
        elif role == "configured" and kind == "mapping":
            missing = False
            for ref_id in ownership.get("field_ref_ids") or []:
                if ctx.db.get(IntegrationFieldRef, _as_uuid(ref_id)) is None:
                    missing = True
            if missing:
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "mapping_modified",
                        "message": "The applied mapping graph changed after apply",
                    }
                )
            else:
                step["action"] = "noop"
        elif role == "created" and kind == "contract":
            contract_id = _as_uuid(ownership.get("contract_id"))
            contract = ctx.db.get(Integration, contract_id)
            if contract is None:
                step["action"] = "skip"
            elif contract.revision != op.post_fingerprint.get("revision", contract.revision):
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "contract_modified",
                        "message": "The created Contract was changed after apply",
                    }
                )
            else:
                external = _external_contract_reference(ctx, contract_id, owned_scenarios)
                if external is not None:
                    conflicts.append(
                        {
                            "operation_id": op.operation_id,
                            "code": "external_reference",
                            "message": "A scenario outside this change set references the Contract",
                        }
                    )
                else:
                    step["action"] = "delete_contract"
        elif role == "created" and kind == "scenario":
            scenario_id = _as_uuid(ownership.get("scenario_id"))
            scenario = ctx.db.get(Scenario, scenario_id)
            if scenario is None:
                step["action"] = "skip"
            elif scenario.revision != op.post_fingerprint.get("revision", scenario.revision):
                conflicts.append(
                    {
                        "operation_id": op.operation_id,
                        "code": "scenario_modified",
                        "message": "The created scenario was changed after apply",
                    }
                )
            else:
                step["action"] = "delete_scenario"
        plan.append(step)
    if conflicts:
        raise UndoConflict(conflicts)
    return plan


def _membership_changed(
    ctx: HelperContext, change_set: HelperChangeSet, ownership: dict[str, Any]
) -> bool:
    object_id = _as_uuid(ownership.get("object_id"))
    node = ownership.get("node") or {}
    member = ownership.get("member") or {}
    if node.get("created"):
        state = get_state(ctx.db, ctx.workspace, change_set.state_id)
        for item in state.nodes:
            if str(item.get("object_id")) == str(object_id):
                return str(item.get("occurrence_id")) != str(node.get("occurrence_id"))
        return True
    if member.get("created"):
        row = ctx.db.get(ArchitectureStateMember, _as_uuid(member.get("member_id")))
        return row is None or str(row.object_id) != str(object_id)
    return False


def _external_contract_reference(
    ctx: HelperContext, contract_id: UUID, owned_scenarios: set[str]
) -> str | None:
    from app.scenarios.routes import references_contract

    candidates = list(
        ctx.db.scalars(
            select(Scenario).where(
                Scenario.tenant_id == ctx.tenant_id,
                Scenario.deleted_at.is_(None),
            )
        )
    )
    for scenario in candidates:
        if str(scenario.id) in owned_scenarios:
            continue
        if references_contract(scenario, contract_id):
            return str(scenario.id)
    return None


class UndoConflict(Exception):
    def __init__(self, conflicts: list[dict[str, Any]]) -> None:
        self.conflicts = conflicts
        super().__init__("undo conflict")


def _current_override_value(
    ctx: HelperContext, change_set: HelperChangeSet, ownership: dict[str, Any]
) -> dict[str, Any]:
    applied = ownership.get("applied") or {}
    object_id = _as_uuid(ownership.get("object_id"))
    if ownership.get("storage") == "node":
        state = get_state(ctx.db, ctx.workspace, change_set.state_id)
        for node in state.nodes:
            if str(node.get("object_id")) == str(object_id):
                overrides = node.get("candidate_overrides") or {}
                return {key: overrides.get(key) for key in applied}
        return {}
    member = ctx.db.scalar(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == change_set.state_id,
            ArchitectureStateMember.object_id == object_id,
        )
    )
    overrides = dict(member.property_overrides or {}) if member is not None else {}
    return {key: overrides.get(key) for key in applied}


def _execute_undo_step(
    wb: DomainWriter, ctx: HelperContext, change_set: HelperChangeSet, op: HelperChangeOperation
) -> None:
    ownership = op.ownership or {}
    role = ownership.get("role")
    kind = ownership.get("kind")
    if role == "created" and kind in DISCIPLINE_KINDS:
        object_id = _as_uuid(ownership.get("object_id"))
        _delete_created_object(ctx, wb.state, kind, object_id)
    elif role == "overridden":
        _restore_override(ctx, change_set, ownership)
    elif role == "included":
        _uninclude(ctx, wb.state, ownership)
    elif role in {"linked", "realized"} and ownership.get("relationship_id"):
        edge = ctx.db.get(ArchitectureRelationship, _as_uuid(ownership["relationship_id"]))
        if edge is not None:
            ctx.db.delete(edge)
        if role == "realized" and ownership.get("field_ref_created"):
            field_ref_id = _as_uuid(ownership.get("field_ref_id"))
            still_used = ctx.db.scalar(
                select(ArchitectureRelationship.id).where(
                    ArchitectureRelationship.tenant_id == ctx.tenant_id,
                    ArchitectureRelationship.target_object_id == field_ref_id,
                )
            )
            registry = ctx.db.get(ArchitectureObject, field_ref_id)
            if still_used is None and registry is not None:
                ctx.db.delete(registry)
    elif kind == "contract" and role == "created":
        contract = ctx.db.get(Integration, _as_uuid(ownership.get("contract_id")))
        if contract is not None:
            ctx.db.delete(contract)
    elif kind == "scenario":
        scenario = ctx.db.get(Scenario, _as_uuid(ownership.get("scenario_id")))
        if scenario is not None:
            ctx.db.delete(scenario)
    ctx.db.flush()


def _delete_created_object(
    ctx: HelperContext, state: ArchitectureState, kind: str, object_id: UUID
) -> None:
    model = KIND_MODEL.get(kind)
    if model is not None:
        row = ctx.db.scalar(
            select(model).where(model.object_id == object_id, model.tenant_id == ctx.tenant_id)
        )
        if row is not None:
            ctx.db.delete(row)
            ctx.db.flush()
    member = ctx.db.scalar(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == state.id,
            ArchitectureStateMember.object_id == object_id,
        )
    )
    if member is not None:
        ctx.db.delete(member)
    registry = ctx.db.get(ArchitectureObject, object_id)
    if registry is not None:
        ctx.db.delete(registry)
    state.nodes = [node for node in state.nodes if str(node.get("object_id")) != str(object_id)]
    state.updated_at = datetime.now(UTC)
    ctx.db.flush()


def _uninclude(ctx: HelperContext, state: ArchitectureState, ownership: dict[str, Any]) -> None:
    object_id = _as_uuid(ownership.get("object_id"))
    node = ownership.get("node") or {}
    member = ownership.get("member") or {}
    if node.get("created"):
        state.nodes = [item for item in state.nodes if str(item.get("object_id")) != str(object_id)]
        state.updated_at = datetime.now(UTC)
    if member.get("created"):
        row = ctx.db.get(ArchitectureStateMember, _as_uuid(member.get("member_id")))
        if row is not None:
            ctx.db.delete(row)
    ctx.db.flush()


def _restore_override(
    ctx: HelperContext, change_set: HelperChangeSet, ownership: dict[str, Any]
) -> None:
    applied = ownership.get("applied") or {}
    prior = ownership.get("prior") or {}
    prior_present = ownership.get("prior_present") or {}
    object_id = _as_uuid(ownership.get("object_id"))
    if ownership.get("storage") == "node":
        state = get_state(ctx.db, ctx.workspace, change_set.state_id)
        updated = list(state.nodes)
        for index, node in enumerate(updated):
            if str(node.get("object_id")) != str(object_id):
                continue
            overrides = dict(node.get("candidate_overrides") or {})
            for key in applied:
                if prior_present.get(key):
                    overrides[key] = prior.get(key)
                else:
                    overrides.pop(key, None)
            replacement = dict(node)
            replacement["candidate_overrides"] = overrides
            updated[index] = replacement
        state.nodes = updated
        state.updated_at = datetime.now(UTC)
        return
    member = ctx.db.scalar(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == change_set.state_id,
            ArchitectureStateMember.object_id == object_id,
        )
    )
    if member is None:
        return
    overrides = dict(member.property_overrides or {})
    for key in applied:
        if prior_present.get(key):
            overrides[key] = prior.get(key)
        else:
            overrides.pop(key, None)
    member.property_overrides = overrides


def undo_change_set(ctx: HelperContext, change_set: HelperChangeSet) -> dict[str, Any]:
    from app.helper_actions import service

    service.add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="undo_requested",
        change_set_id=change_set.id,
        state_id=change_set.state_id,
        summary={"status": change_set.status},
    )
    ctx.db.commit()

    def fail(code: str, message: str, conflicts: list[dict[str, Any]] | None = None) -> None:
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="undo_conflict",
            change_set_id=change_set.id,
            state_id=change_set.state_id,
            summary={"code": code, "message": message, "conflicts": conflicts or []},
        )
        ctx.db.commit()
        raise _conflict(code, message, conflicts=conflicts or [])

    if change_set.status == "undone":
        fail("not_applied", "The change set has already been undone")
    if change_set.status != "applied":
        fail("not_applied", "Only an applied change set can be undone")
    if service.sync_staleness(ctx, change_set):
        fail("proposal_stale", "The proposal changed after apply; undo was refused")

    operations = service.load_operations(ctx.db, change_set.id)
    ordered = topological_order(operations)
    state = get_state(ctx.db, ctx.workspace, change_set.state_id)
    try:
        plan = _build_undo_plan(ctx, change_set, ordered)
    except UndoConflict as conflict:
        fail(
            "undo_conflict",
            "Undo would overwrite a later change or external reference",
            conflict.conflicts,
        )

    wb = DomainWriter(ctx, state)
    undone: list[dict[str, Any]] = []
    by_id = {op.operation_id: op for op in operations}
    try:
        for step in plan:
            op = by_id[step["operation_id"]]
            if step["action"] == "skip":
                op.undo_status = "noop"
            else:
                _execute_undo_step(wb, ctx, change_set, op)
                op.undo_status = "undone"
            op.undo_conflict = {}
            undone.append(
                {
                    "operation_id": op.operation_id,
                    "domain_action": op.domain_action,
                    "action": step["action"],
                }
            )
            if step["action"] != "skip":
                service.add_audit(
                    ctx.db,
                    tenant_id=ctx.tenant_id,
                    workspace_id=ctx.workspace_id,
                    user_id=ctx.user.id,
                    event_type="operation_undone",
                    change_set_id=change_set.id,
                    state_id=state.id,
                    summary={"operation_id": op.operation_id, "action": step["action"]},
                )
        change_set.undo_summary = {
            "undone_operation_count": len([item for item in undone if item["action"] != "skip"]),
            "undone_at": datetime.now(UTC).isoformat(),
        }
        change_set.status = "undone"
        change_set.undone_at = datetime.now(UTC)
        change_set.updated_at = datetime.now(UTC)
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="undo_completed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"undone_operation_count": change_set.undo_summary["undone_operation_count"]},
        )
        ctx.db.commit()
    except HTTPException as error:
        ctx.db.rollback()
        detail = error.detail if isinstance(error.detail, dict) else {"message": error.detail}
        service.add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="undo_conflict",
            change_set_id=change_set.id,
            state_id=change_set.state_id,
            summary={
                "code": str(detail.get("code", "undo_failed")),
                "message": str(detail.get("message", "Undo failed")),
            },
        )
        ctx.db.commit()
        raise

    ctx.db.refresh(change_set)
    preserved = [
        ownership.get("object_id") or ownership.get("contract_id")
        for op in operations
        for ownership in [op.ownership or {}]
        if ownership.get("reused")
    ]
    return {
        "status": "undone",
        "undone_operation_count": change_set.undo_summary.get("undone_operation_count", 0),
        "undone_operations": undone,
        "preserved_objects": sorted({item for item in preserved if item}),
        "warnings": [],
        "conflicts": [],
        "audit_event_ref": str(change_set.id),
    }
