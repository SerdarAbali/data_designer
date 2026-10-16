"""Deterministic proposal builders for the Slice 2 domain helpers.

These builders translate a strict, closed request into a list of typed
operations. They only *read* canonical records (to decide reuse) and never
create or modify architecture-domain data: the sole output is a list of
:class:`BuiltOperation` values that the change-set service persists as helper
lifecycle rows.

Every helper is a named profile over one request shape. A profile fixes:

* the enabled discipline it belongs to,
* which canonical kinds it may create or include, and
* which relationship types it may propose.

Matching order is fixed (see :mod:`app.helper_actions.matching`): explicit
canonical ID, then exact external identifier, then exact normalized name within
tenant + kind + parent scope, then a new object is proposed or the decision is
left unresolved. Name similarity never causes automatic reuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.architecture.enterprise import LINK_RULES as ENTERPRISE_LINK_RULES
from app.architecture.solution import (
    CONNECTS_TO,
    CONTAINED_IN,
    CROSSES,
    DEPLOYED_ON,
    USES_REPOSITORY,
)
from app.architecture.state_scope import present_in_current
from app.helper_actions import matching
from app.helper_actions.context import HelperContext
from app.helper_actions.schemas import (
    AttributeRealizationRequest,
    CapabilitySupportRequest,
    DeploymentAllocationRequest,
    DomainProposalRequest,
    EnterpriseImpactResolutionRequest,
    EntityRelationshipRequest,
    InformationEntityRequest,
    InformationGapResolutionRequest,
    InformationModelRequest,
    InterfaceConnectionRequest,
    ProcessSupportRequest,
    RepositoryUsageRequest,
    SolutionComponentRequest,
    SolutionInteractionRequest,
    SolutionStructureRequest,
    StrategyChainRequest,
    TrustBoundaryMembershipRequest,
)

# --- closed vocabularies -----------------------------------------------------

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
INFORMATION_KINDS = frozenset({"information_object", "information_attribute"})
SOLUTION_KINDS = frozenset(
    {
        "solution_boundary",
        "component",
        "interface",
        "interface_operation",
        "data_repository",
        "deployment_node",
        "trust_boundary",
    }
)
CROSS_KINDS = frozenset({"catalog_system", "catalog_field"})
ALL_KINDS = ENTERPRISE_KINDS | INFORMATION_KINDS | SOLUTION_KINDS | CROSS_KINDS

ENTERPRISE_RELS = frozenset(ENTERPRISE_LINK_RULES)
INFORMATION_RELS = frozenset({"references"})
SOLUTION_RELS = frozenset({USES_REPOSITORY, DEPLOYED_ON, CROSSES, CONNECTS_TO, CONTAINED_IN})
ALL_RELS = ENTERPRISE_RELS | INFORMATION_RELS | SOLUTION_RELS

KIND_DISCIPLINE = {kind: "enterprise" for kind in ENTERPRISE_KINDS}
KIND_DISCIPLINE.update({kind: "information" for kind in INFORMATION_KINDS})
KIND_DISCIPLINE.update({kind: "solution" for kind in SOLUTION_KINDS})

# The registry stores Catalog systems with kind ``system``; the request calls
# them ``catalog_system``. Translate when checking domain link rules.
REGISTRY_KIND = {"catalog_system": "system"}

REQUIRED_PARENT_KINDS = frozenset(
    {
        "information_attribute",
        "interface",
        "interface_operation",
        "data_repository",
        "deployment_node",
        "trust_boundary",
    }
)

SCALAR_FIELDS = (
    "description",
    "external_identifier",
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
)


def registry_kind(kind: str) -> str:
    return REGISTRY_KIND.get(kind, kind)


@dataclass(frozen=True)
class Profile:
    discipline: str
    kinds: frozenset[str]
    relationships: frozenset[str]
    required: tuple[tuple[str, ...], ...] = ()


ENTERPRISE_PROFILE_KINDS = ENTERPRISE_KINDS | CROSS_KINDS
INFORMATION_PROFILE_KINDS = INFORMATION_KINDS | CROSS_KINDS
SOLUTION_PROFILE_KINDS = SOLUTION_KINDS | CROSS_KINDS

PROFILES: dict[str, Profile] = {
    "propose_strategy_chain": Profile(
        "enterprise",
        ENTERPRISE_PROFILE_KINDS,
        ENTERPRISE_RELS,
        (
            ("business_goal",),
            ("business_requirement",),
            ("business_capability",),
            ("business_process",),
        ),
    ),
    "propose_capability_support": Profile(
        "enterprise",
        ENTERPRISE_PROFILE_KINDS,
        frozenset({"supports", "satisfies"}),
        (("business_capability",),),
    ),
    "propose_process_support": Profile(
        "enterprise",
        ENTERPRISE_PROFILE_KINDS,
        frozenset({"has_process", "supports"}),
        (("business_process",),),
    ),
    "propose_enterprise_impact_resolution": Profile(
        "enterprise",
        ENTERPRISE_PROFILE_KINDS,
        frozenset({"impacts", "affects", "depends_on"}),
    ),
    "propose_information_entity": Profile(
        "information",
        INFORMATION_PROFILE_KINDS,
        INFORMATION_RELS,
        (("information_object",),),
    ),
    "propose_information_model": Profile(
        "information",
        INFORMATION_PROFILE_KINDS,
        INFORMATION_RELS,
        (("information_object",),),
    ),
    "propose_entity_relationship": Profile(
        "information",
        INFORMATION_PROFILE_KINDS,
        INFORMATION_RELS,
        (("information_object",),),
    ),
    "propose_attribute_realization": Profile(
        "information", INFORMATION_PROFILE_KINDS, INFORMATION_RELS
    ),
    "propose_information_gap_resolution": Profile(
        "information", INFORMATION_PROFILE_KINDS, INFORMATION_RELS
    ),
    "propose_solution_structure": Profile(
        "solution",
        SOLUTION_PROFILE_KINDS,
        SOLUTION_RELS,
        (("solution_boundary",),),
    ),
    "propose_solution_component": Profile("solution", SOLUTION_PROFILE_KINDS, SOLUTION_RELS),
    "propose_interface_connection": Profile(
        "solution", SOLUTION_PROFILE_KINDS, frozenset({CONNECTS_TO})
    ),
    "propose_repository_usage": Profile(
        "solution", SOLUTION_PROFILE_KINDS, frozenset({USES_REPOSITORY})
    ),
    "propose_deployment_allocation": Profile(
        "solution", SOLUTION_PROFILE_KINDS, frozenset({DEPLOYED_ON})
    ),
    "propose_trust_boundary_membership": Profile(
        "solution", SOLUTION_PROFILE_KINDS, frozenset({CONTAINED_IN, CROSSES})
    ),
    "propose_solution_interaction": Profile("solution", SOLUTION_PROFILE_KINDS, SOLUTION_RELS),
}

REQUEST_MODELS = {
    "propose_strategy_chain": StrategyChainRequest,
    "propose_capability_support": CapabilitySupportRequest,
    "propose_process_support": ProcessSupportRequest,
    "propose_enterprise_impact_resolution": EnterpriseImpactResolutionRequest,
    "propose_information_entity": InformationEntityRequest,
    "propose_information_model": InformationModelRequest,
    "propose_entity_relationship": EntityRelationshipRequest,
    "propose_attribute_realization": AttributeRealizationRequest,
    "propose_information_gap_resolution": InformationGapResolutionRequest,
    "propose_solution_structure": SolutionStructureRequest,
    "propose_solution_component": SolutionComponentRequest,
    "propose_interface_connection": InterfaceConnectionRequest,
    "propose_repository_usage": RepositoryUsageRequest,
    "propose_deployment_allocation": DeploymentAllocationRequest,
    "propose_trust_boundary_membership": TrustBoundaryMembershipRequest,
    "propose_solution_interaction": SolutionInteractionRequest,
}


@dataclass
class BuiltOperation:
    operation_id: str
    domain_action: str
    target_type: str
    target_id: UUID | None = None
    temporary_id: str | None = None
    before_value: dict[str, Any] | None = None
    proposed_value: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class BuiltProposal:
    helper_name: str
    state_id: UUID
    summary: str
    operations: list[BuiltOperation] = field(default_factory=list)
    reused_objects: list[dict[str, Any]] = field(default_factory=list)
    proposed_objects: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unresolved_decisions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _reject(code: str, **context: Any) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, **context},
    )


class _Builder:
    def __init__(
        self, ctx: HelperContext, helper_name: str, req: DomainProposalRequest, profile: Profile
    ) -> None:
        self.ctx = ctx
        self.helper_name = helper_name
        self.req = req
        self.profile = profile
        self.ops: list[BuiltOperation] = []
        self._seq = 0
        self._temps: set[str] = set()
        self.key_ref: dict[str, str] = {}
        self.key_kind: dict[str, str] = {}
        self.key_op: dict[str, str] = {}
        self.key_canonical: dict[str, UUID] = {}
        self.reused: dict[str, dict[str, Any]] = {}
        self.proposed: dict[str, dict[str, Any]] = {}
        self.assumptions: list[str] = []
        self.unresolved: list[str] = []
        self.warnings: list[str] = []

    # -- primitives -----------------------------------------------------------

    def _emit(
        self,
        domain_action: str,
        target_type: str,
        *,
        target_id: UUID | None = None,
        temporary_id: str | None = None,
        proposed_value: dict[str, Any] | None = None,
        before_value: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        explanation: str = "",
    ) -> BuiltOperation:
        self._seq += 1
        op = BuiltOperation(
            operation_id=f"op-{self._seq}",
            domain_action=domain_action,
            target_type=target_type,
            target_id=target_id,
            temporary_id=temporary_id,
            before_value=before_value,
            proposed_value=proposed_value or {},
            depends_on=list(dict.fromkeys(depends_on or [])),
            explanation=explanation,
        )
        self.ops.append(op)
        return op

    def _temp(self, kind: str, name: str) -> str:
        base = f"tmp:{kind}:{matching.slug(name)}"
        candidate = base
        suffix = 2
        while candidate in self._temps:
            candidate = f"{base}-{suffix}"
            suffix += 1
        self._temps.add(candidate)
        return candidate

    def _unresolved(self, decision: str) -> None:
        if decision not in self.unresolved:
            self.unresolved.append(decision)

    def _scalars(self, node) -> dict[str, Any]:
        dumped = node.model_dump(exclude_unset=True)
        return {k: v for k, v in dumped.items() if k in SCALAR_FIELDS and v is not None}

    # -- node ordering --------------------------------------------------------

    def _ordered_nodes(self):
        nodes = {n.key: n for n in self.req.nodes}
        order: list[Any] = []
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(key: str) -> None:
            if key in done:
                return
            if key in visiting:
                _reject("node_reference_cycle", key=key)
            node = nodes[key]
            visiting.add(key)
            if node.parent_key:
                if node.parent_key not in nodes:
                    _reject("unknown_parent_key", key=node.parent_key)
                visit(node.parent_key)
            visiting.discard(key)
            done.add(key)
            order.append(node)

        for node in self.req.nodes:
            visit(node.key)
        return order

    # -- reuse / create -------------------------------------------------------

    def _resolve_system_ref(self, node) -> UUID | None:
        if node.system_key is not None:
            ref = self.key_canonical.get(node.system_key)
            if ref is None:
                _reject("unknown_system_key", key=node.system_key)
            return ref
        if node.system_id is not None:
            system = matching.find_catalog_system(self.ctx, node.system_id)
            if system is None:
                _reject("unknown_reference", object_id=str(node.system_id))
            return system.id
        if node.system_name is not None:
            system = matching.find_catalog_system(self.ctx, name=node.system_name)
            if system is None:
                self._unresolved(
                    f"Catalog system '{node.system_name}' was not found; "
                    "helpers cannot create Catalog records"
                )
                return None
            return system.id
        return None

    def _reuse(self, node, object_id: UUID, kind: str, name: str, row: Any = None) -> None:
        scalars = self._scalars(node)
        if scalars and present_in_current(self.ctx.db, self.ctx.workspace, object_id):
            before = {key: getattr(row, key, None) for key in scalars} if row is not None else {}
            self._emit(
                "override_object",
                kind,
                target_id=object_id,
                proposed_value={"kind": kind, "changes": scalars},
                before_value=before,
                explanation=f"Override {kind} '{name}' with a bounded Candidate scalar change",
            )
        else:
            self._emit(
                "include_object",
                kind,
                target_id=object_id,
                proposed_value={"kind": kind, "name": name},
                explanation=f"Reuse existing {kind} '{name}' as a state membership",
            )
        self.key_ref[node.key] = str(object_id)
        self.key_kind[node.key] = kind
        self.key_canonical[node.key] = object_id
        self.reused[str(object_id)] = {
            "target_type": kind,
            "target_id": str(object_id),
            "name": name,
        }

    def _create(self, node, parent_ref: str | None) -> None:
        if node.kind in REQUIRED_PARENT_KINDS and parent_ref is None:
            _reject("missing_parent", kind=node.kind, key=node.key)
        temp = self._temp(node.kind, node.name)
        values: dict[str, Any] = {"kind": node.kind, "name": node.name}
        values.update(self._scalars(node))
        depends_on: list[str] = []
        if parent_ref is not None:
            values["parent_ref"] = parent_ref
            parent_op = self.key_op.get(node.parent_key)
            if parent_op is not None:
                depends_on.append(parent_op)
        system_ref = self._resolve_system_ref(node)
        if system_ref is not None:
            values["system_ref"] = str(system_ref)
        op = self._emit(
            "create_object",
            node.kind,
            temporary_id=temp,
            proposed_value=values,
            depends_on=depends_on,
            explanation=f"Propose new {node.kind} '{node.name}'",
        )
        self.key_ref[node.key] = temp
        self.key_kind[node.key] = node.kind
        self.key_op[node.key] = op.operation_id
        self.proposed[temp] = {
            "temporary_id": temp,
            "target_type": node.kind,
            "name": node.name,
        }

    def _process_node(self, node) -> None:
        if node.kind not in self.profile.kinds:
            _reject("kind_not_allowed", kind=node.kind, helper=self.helper_name)
        parent_ref: str | None = None
        parent_canonical: UUID | None = None
        if node.parent_key:
            parent_ref = self.key_ref.get(node.parent_key)
            parent_canonical = self.key_canonical.get(node.parent_key)
            if parent_ref is None:
                _reject("unknown_parent_key", key=node.parent_key)

        if node.kind == "catalog_system":
            system = matching.find_catalog_system(
                self.ctx, node.system_id or node.existing_object_id, node.name
            )
            if system is None:
                self._unresolved(
                    f"Catalog system '{node.name}' was not found; "
                    "helpers cannot create Catalog records"
                )
                return
            self._reuse(node, system.id, "catalog_system", system.name)
            return

        if node.kind == "catalog_field":
            field = (
                matching.find_catalog_field_by_id(self.ctx, node.existing_object_id)
                if node.existing_object_id is not None
                else None
            )
            if field is None:
                self._unresolved(
                    f"Catalog field '{node.name}' was not found; "
                    "helpers cannot create Catalog records"
                )
                return
            self._reuse(node, field.id, "catalog_field", node.name)
            return

        if node.existing_object_id is not None:
            registry = matching.find_registry(self.ctx, node.existing_object_id, {node.kind})
            if registry is None:
                _reject("unknown_reference", object_id=str(node.existing_object_id))
            row = matching.find_typed_row(self.ctx, node.kind, registry.id)
            name = getattr(row, "name", node.name) if row is not None else node.name
            self._reuse(node, registry.id, node.kind, name, row=row)
            return

        if node.external_identifier:
            match = matching.find_by_external_id(self.ctx, node.kind, node.external_identifier)
            if match is not None:
                self._reuse(node, match.object_id, node.kind, match.name, row=match)
                return

        if parent_ref is None or parent_canonical is not None:
            match = matching.find_canonical_by_name(
                self.ctx, node.kind, node.name, parent_canonical
            )
            if match is not None:
                self._reuse(node, match.object_id, node.kind, match.name, row=match)
                return

        self._create(node, parent_ref)

    # -- links, realizations, interactions -----------------------------------

    def _process_link(self, link) -> None:
        if link.relationship_type not in self.profile.relationships:
            _reject(
                "relationship_not_allowed",
                relationship_type=link.relationship_type,
                helper=self.helper_name,
            )
        if link.source_key not in self.key_ref or link.target_key not in self.key_ref:
            _reject(
                "unknown_link_endpoint",
                source_key=link.source_key,
                target_key=link.target_key,
            )
        deps = [
            self.key_op[key]
            for key in (link.source_key, link.target_key)
            if key in self.key_op
        ]
        proposed: dict[str, Any] = {
            "relationship_type": link.relationship_type,
            "source_ref": self.key_ref[link.source_key],
            "target_ref": self.key_ref[link.target_key],
        }
        for name in ("name", "cardinality", "source_optional", "target_optional"):
            value = getattr(link, name)
            if value is not None:
                proposed[name] = value
        self._emit(
            "create_link",
            "relationship",
            proposed_value=proposed,
            depends_on=deps,
            explanation=(
                f"Propose '{link.relationship_type}' link "
                f"from '{link.source_key}' to '{link.target_key}'"
            ),
        )

    def _process_realization(self, real) -> None:
        if real.key not in self.key_ref:
            _reject("unknown_realization_key", key=real.key)
        if self.key_kind[real.key] != "information_attribute":
            _reject("realization_requires_attribute", key=real.key)
        deps = [self.key_op[real.key]] if real.key in self.key_op else []
        proposed: dict[str, Any] = {"attribute_ref": self.key_ref[real.key]}
        reason: str | None = None
        if real.catalog_field_id is not None:
            field = matching.find_catalog_field_by_id(self.ctx, real.catalog_field_id)
            if field is None:
                _reject("unknown_reference", object_id=str(real.catalog_field_id))
            proposed["catalog_field_id"] = str(field.id)
            proposed["catalog_object_id"] = str(field.object_id)
            proposed["resolved"] = True
        elif real.catalog_object_name and real.field_name:
            field, ambiguous, candidates = matching.match_catalog_field(
                self.ctx, real.catalog_object_name, real.field_name
            )
            if field is not None:
                proposed["catalog_field_id"] = str(field.id)
                proposed["catalog_object_id"] = str(field.object_id)
                proposed["resolved"] = True
            else:
                if ambiguous:
                    reason = (
                        "Multiple Catalog fields matched "
                        f"'{real.catalog_object_name}.{real.field_name}'; "
                        "the choice is a human decision"
                    )
                else:
                    reason = (
                        "No active Catalog field matched "
                        f"'{real.catalog_object_name}.{real.field_name}'"
                    )
                suggestions = matching.suggest_catalog_fields(self.ctx, real.field_name)
                candidates = sorted(set(candidates + suggestions))[:10]
                proposed.update({"unresolved": True, "reason": reason, "candidates": candidates})
        else:
            reason = f"No Catalog field or (object, field) name supplied for '{real.key}'"
            proposed.update({"unresolved": True, "reason": reason, "candidates": []})
        self._emit(
            "set_realization",
            "realization",
            proposed_value=proposed,
            depends_on=deps,
            explanation=f"Realize attribute '{real.key}' against an existing Catalog field",
        )
        if reason is not None:
            self._unresolved(reason)

    def _process_interaction(self, interaction) -> None:
        for key in (interaction.source_key, interaction.target_key):
            if key not in self.key_ref:
                _reject("unknown_interaction_endpoint", key=key)
        evidence_keys = [
            key
            for key in (
                interaction.connection_key,
                interaction.interface_key,
                interaction.operation_key,
            )
            if key is not None
        ]
        for key in evidence_keys:
            if key not in self.key_ref:
                _reject("unknown_interaction_evidence", key=key)
        deps = [
            self.key_op[key]
            for key in (interaction.source_key, interaction.target_key, *evidence_keys)
            if key in self.key_op
        ]
        proposed: dict[str, Any] = {
            "source_ref": self.key_ref[interaction.source_key],
            "target_ref": self.key_ref[interaction.target_key],
            "evidence_refs": [self.key_ref[key] for key in evidence_keys],
        }
        if interaction.description:
            proposed["description"] = interaction.description
        if not evidence_keys:
            reason = (
                f"Interaction '{interaction.key}' has no modeled or proposed "
                "interface, operation, or connection evidence"
            )
            proposed.update({"unresolved": True, "reason": reason, "candidates": []})
            self._unresolved(reason)
        self._emit(
            "record_interaction",
            "interaction",
            proposed_value=proposed,
            depends_on=deps,
            explanation=f"Propose interaction '{interaction.key}'",
        )

    # -- entry point ----------------------------------------------------------

    def build(self, profile: Profile) -> BuiltProposal:
        keys = [node.key for node in self.req.nodes]
        if len(keys) != len(set(keys)):
            _reject("duplicate_node_key")
        for node in self._ordered_nodes():
            self._process_node(node)
        for link in self.req.links:
            self._process_link(link)
        for real in self.req.realizations:
            self._process_realization(real)
        for interaction in self.req.interactions:
            self._process_interaction(interaction)
        for group in profile.required:
            if not any(node.kind in group for node in self.req.nodes):
                self._unresolved(
                    f"No {'/'.join(group)} node was supplied for {self.helper_name}; "
                    "the missing strategy relationship is not fabricated"
                )
        return BuiltProposal(
            helper_name=self.helper_name,
            state_id=self.req.state_id,
            summary=self.req.summary,
            operations=self.ops,
            reused_objects=[self.reused[key] for key in sorted(self.reused)],
            proposed_objects=sorted(
                self.proposed.values(), key=lambda item: item["temporary_id"]
            ),
            assumptions=self.assumptions,
            unresolved_decisions=self.unresolved,
            warnings=self.warnings,
            input_summary={
                "node_count": len(self.req.nodes),
                "link_count": len(self.req.links),
                "realization_count": len(self.req.realizations),
                "interaction_count": len(self.req.interactions),
                "operation_count": len(self.ops),
                "reused_count": len(self.reused),
                "proposed_count": len(self.proposed),
                "unresolved_count": len(self.unresolved),
                "requested_disciplines": [profile.discipline],
            },
        )


def build_domain_proposal(
    ctx: HelperContext, helper_name: str, req: DomainProposalRequest
) -> BuiltProposal:
    profile = PROFILES[helper_name]
    return _Builder(ctx, helper_name, req, profile).build(profile)
