"""Strict request/response schemas for the helper-action layer.

All request models forbid unknown fields and are bounded. Responses are
structured envelopes with explicit truncation metadata so callers never receive
unrestricted graphs or full workspace dumps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.architecture.schemas import (
    EnterprisePrincipleType,
    EnterpriseProcessType,
    EnterpriseRoleType,
    InformationCardinality,
    SolutionInterfaceDirection,
    SolutionInterfaceKind,
    SolutionOperationKind,
)
from app.integrations.schemas import IntegrationSpecification

ReadHelperName = Literal[
    "get_workspace_context",
    "get_enabled_disciplines",
    "get_architecture_state",
    "search_canonical_objects",
    "get_object_details",
    "get_object_relationships",
    "get_object_usages",
    "trace_architecture_path",
    "compare_current_candidate",
    "list_catalog_systems",
    "inspect_catalog_schema",
    "list_integration_contracts",
    "inspect_contract",
    "inspect_mapping_coverage",
    "inspect_scenarios_and_conformance",
]

ProposalHelperName = Literal[
    "propose_fixture",
    "propose_strategy_chain",
    "propose_capability_support",
    "propose_process_support",
    "propose_enterprise_impact_resolution",
    "propose_information_entity",
    "propose_information_model",
    "propose_entity_relationship",
    "propose_attribute_realization",
    "propose_information_gap_resolution",
    "propose_solution_structure",
    "propose_solution_component",
    "propose_interface_connection",
    "propose_repository_usage",
    "propose_deployment_allocation",
    "propose_trust_boundary_membership",
    "propose_solution_interaction",
    "propose_direct_integration",
    "propose_event_driven_integration",
    "propose_runtime_mediated_integration",
    "propose_file_transfer_integration",
    "propose_contract",
    "propose_field_mappings",
    "propose_transformations",
    "propose_resilience_configuration",
    "propose_scenarios",
    "propose_conformance_tests",
    "propose_end_to_end_architecture",
]

TraceDirection = Literal["both", "outgoing", "incoming"]

Discipline = Literal["enterprise", "information", "solution", "integration"]


class ReadRequest(BaseModel):
    """Bounded read-helper invocation input."""

    model_config = ConfigDict(extra="forbid")

    state_id: UUID | None = None
    baseline_state_id: UUID | None = None
    object_id: UUID | None = None
    system_id: UUID | None = None
    contract_id: UUID | None = None
    query: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, max_length=60)
    direction: TraceDirection = "both"
    depth: int = Field(default=1, ge=1, le=4)
    limit: int = Field(default=25, ge=1, le=100)


class ReadEnvelope(BaseModel):
    helper: str
    workspace_id: UUID
    truncated: bool = False
    limit: int | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class FixtureOperation(BaseModel):
    """A harmless, non-executable proposed operation used to exercise lifecycle.

    ``domain_action`` is a closed set. No value here runs code, touches the ORM
    directly, or causes architecture-domain writes.
    """

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=80)
    domain_action: Literal["reuse_existing_object", "reference_object"]
    target_type: Literal["architecture_object", "catalog_system", "catalog_field", "contract"] = (
        "architecture_object"
    )
    target_id: UUID | None = None
    temporary_id: str | None = Field(default=None, max_length=80)
    before_value: dict[str, Any] | None = None
    proposed_value: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    explanation: str = Field(default="", max_length=2000)


class FixtureProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: UUID
    summary: str = Field(min_length=1, max_length=2000)
    requested_disciplines: list[Discipline] = Field(default_factory=list, max_length=4)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    unresolved_decisions: list[str] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=50)
    operations: list[FixtureOperation] = Field(default_factory=list, max_length=200)


class OperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operation_id: str
    ordinal: int
    domain_action: str
    target_type: str
    target_id: UUID | None = None
    temporary_id: str | None = None
    before_value: dict[str, Any] | None = None
    proposed_value: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    validation_status: str
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str | None = None
    applied_id: UUID | None = None
    apply_status: str = "pending"
    ownership: dict[str, Any] = Field(default_factory=dict)
    post_fingerprint: dict[str, Any] = Field(default_factory=dict)
    undo_status: str = "pending"
    undo_conflict: dict[str, Any] = Field(default_factory=dict)
    resolution_state: str = "active"


class ChangeSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    state_id: UUID | None = None
    state_type: str | None = None
    helper_name: str
    status: str
    summary: str | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[Any] = Field(default_factory=list)
    unresolved_decisions: list[Any] = Field(default_factory=list)
    unresolved_details: list[Any] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)
    reused_objects: list[Any] = Field(default_factory=list)
    proposed_objects: list[Any] = Field(default_factory=list)
    expected_traceability: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    proposal_hash: str | None = None
    proposed_by: UUID | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    approved_hash: str | None = None
    validated_at: datetime | None = None
    apply_summary: dict[str, Any] = Field(default_factory=dict)
    undo_summary: dict[str, Any] = Field(default_factory=dict)
    applied_at: datetime | None = None
    undone_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    operations: list[OperationResponse] = Field(default_factory=list)


class ApplyResponse(BaseModel):
    change_set: ChangeSetResponse
    status: str
    applied_operation_count: int = 0
    resolution_map: dict[str, str] = Field(default_factory=dict)
    applied_operations: list[dict[str, Any]] = Field(default_factory=list)
    contract_revisions: list[dict[str, Any]] = Field(default_factory=list)
    affected_objects: list[str] = Field(default_factory=list)
    affected_workbenches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    audit_event_ref: str | None = None


class UndoResponse(BaseModel):
    change_set: ChangeSetResponse
    status: str
    undone_operation_count: int = 0
    undone_operations: list[dict[str, Any]] = Field(default_factory=list)
    preserved_objects: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    audit_event_ref: str | None = None


class ChangeSetStatusResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    status: str
    proposal_hash: str | None = None
    current_hash: str | None = None
    validated_at: datetime | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    operation_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)


# --- Slice 2: domain proposal helpers ---------------------------------------
# One strict, closed request shape shared by the Enterprise, Information, and
# Solution proposal helpers. A helper is a named profile over this shape: the
# profile decides which canonical kinds and relationship types are allowed and
# which node kinds are required. No value here is executable and none of it is
# free-form: every field maps to an existing canonical domain concept.

CanonicalKind = Literal[
    "business_goal",
    "business_requirement",
    "business_capability",
    "business_process",
    "architecture_principle",
    "organization_role",
    "information_object",
    "information_attribute",
    "solution_boundary",
    "component",
    "interface",
    "interface_operation",
    "data_repository",
    "deployment_node",
    "trust_boundary",
    "catalog_system",
    "catalog_field",
]

RelationshipType = Literal[
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
    "references",
    "uses_repository",
    "deployed_on",
    "crosses",
    "connects_to",
    "contained_in",
]

DomainAction = Literal[
    "create_object",
    "include_object",
    "override_object",
    "create_link",
    "set_realization",
    "record_interaction",
]


class ProposalNode(BaseModel):
    """A canonical object proposal: reuse an existing record or propose a new one.

    Exactly one of ``existing_object_id`` / name-based reuse / creation happens,
    in that deterministic order, inside the builder. Children (attributes,
    interfaces, operations, components, repositories, deployments, trust
    boundaries) reference their parent through ``parent_key``.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    kind: CanonicalKind
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    existing_object_id: UUID | None = None
    parent_key: str | None = Field(default=None, max_length=80)
    system_id: UUID | None = None
    system_name: str | None = Field(default=None, max_length=160)
    system_key: str | None = Field(default=None, max_length=80)
    external_identifier: str | None = Field(default=None, max_length=255)
    owner: str | None = Field(default=None, max_length=160)
    steward: str | None = Field(default=None, max_length=160)
    outcome_metric: str | None = Field(default=None, max_length=500)
    horizon: str | None = Field(default=None, max_length=60)
    process_type: EnterpriseProcessType | None = None
    principle_type: EnterprisePrincipleType | None = None
    rationale: str | None = Field(default=None, max_length=2000)
    role_type: EnterpriseRoleType | None = None
    classification: str | None = Field(default=None, max_length=100)
    sensitivity: str | None = Field(default=None, max_length=40)
    data_type: str | None = Field(default=None, max_length=100)
    required: bool | None = None
    nullable: bool | None = None
    is_key: bool | None = None
    is_identifier: bool | None = None
    ordinal: int | None = Field(default=None, ge=0, le=100000)
    definition: str | None = Field(default=None, max_length=2000)
    direction: SolutionInterfaceDirection | None = None
    interface_kind: SolutionInterfaceKind | None = None
    protocol: str | None = Field(default=None, max_length=60)
    technology: str | None = Field(default=None, max_length=160)
    operation_kind: SolutionOperationKind | None = None
    responsibility: str | None = Field(default=None, max_length=2000)
    component_type: str | None = Field(default=None, max_length=60)
    repository_type: str | None = Field(default=None, max_length=40)
    environment: str | None = Field(default=None, max_length=40)
    hosting: str | None = Field(default=None, max_length=40)
    security_level: str | None = Field(default=None, max_length=40)
    position: dict[str, float] | None = None


class ProposalLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: RelationshipType
    source_key: str = Field(min_length=1, max_length=80)
    target_key: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=160)
    cardinality: InformationCardinality | None = None
    source_optional: bool | None = None
    target_optional: bool | None = None


class ProposalRealization(BaseModel):
    """Realize a logical attribute against an existing Catalog field.

    A field may be named explicitly by ID, or by (Catalog object name, field
    name). Anything ambiguous or missing stays unresolved; helpers never guess
    from name similarity and never create a Catalog field.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    catalog_field_id: UUID | None = None
    catalog_object_name: str | None = Field(default=None, max_length=160)
    field_name: str | None = Field(default=None, max_length=160)


class ProposalInteraction(BaseModel):
    """A proposed interaction that must be supported by modeled evidence."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    source_key: str = Field(min_length=1, max_length=80)
    target_key: str = Field(min_length=1, max_length=80)
    connection_key: str | None = Field(default=None, max_length=80)
    interface_key: str | None = Field(default=None, max_length=80)
    operation_key: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class DomainProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: UUID
    summary: str = Field(min_length=1, max_length=2000)
    nodes: list[ProposalNode] = Field(default_factory=list, max_length=200)
    links: list[ProposalLink] = Field(default_factory=list, max_length=300)
    realizations: list[ProposalRealization] = Field(default_factory=list, max_length=200)
    interactions: list[ProposalInteraction] = Field(default_factory=list, max_length=200)


# Named profiles. Each is structurally identical and strict; the helper name is
# the only selector and it maps to a closed domain profile in the builder.
class StrategyChainRequest(DomainProposalRequest):
    pass


class CapabilitySupportRequest(DomainProposalRequest):
    pass


class ProcessSupportRequest(DomainProposalRequest):
    pass


class EnterpriseImpactResolutionRequest(DomainProposalRequest):
    pass


class InformationEntityRequest(DomainProposalRequest):
    pass


class InformationModelRequest(DomainProposalRequest):
    pass


class EntityRelationshipRequest(DomainProposalRequest):
    pass


class AttributeRealizationRequest(DomainProposalRequest):
    pass


class InformationGapResolutionRequest(DomainProposalRequest):
    pass


class SolutionStructureRequest(DomainProposalRequest):
    pass


class SolutionComponentRequest(DomainProposalRequest):
    pass


class InterfaceConnectionRequest(DomainProposalRequest):
    pass


class RepositoryUsageRequest(DomainProposalRequest):
    pass


class DeploymentAllocationRequest(DomainProposalRequest):
    pass


class TrustBoundaryMembershipRequest(DomainProposalRequest):
    pass


class SolutionInteractionRequest(DomainProposalRequest):
    pass


# --- Slice 3: Integration / Contract / Mapping / Scenario proposals ----------
# One strict, closed request shape shared by the integration proposal helpers.
# A helper is a named profile over this shape. Everything maps to an existing
# domain concept; nothing here is executable and no arbitrary payloads or
# generic graph mutations are accepted.

IntegrationInteractionType = Literal["ONE_WAY", "REQUEST_RESPONSE", "ASYNC_CALLBACK"]
IntegrationPatternName = Literal[
    "point_to_point",
    "request_reply",
    "publish_subscribe",
    "event_streaming",
    "message_queue",
    "file_transfer",
    "batch",
    "api_gateway",
    "orchestration",
    "other",
]
IntegrationImplementationStatus = Literal["draft", "in_progress", "built", "verified"]
ProposalIntent = Literal["alternative", "proposed_replacement", "independent"]
ScenarioPhaseName = Literal["request", "success-response", "async-response", "error-response"]
ScenarioPreset = Literal[
    "happy_path",
    "validation_failure",
    "target_unavailable",
    "duplicate_request",
    "error_response",
    "event_delivery_failure",
    "file_transfer_failure",
]
ConformanceExpectationType = Literal[
    "mapping_coverage",
    "required_fields",
    "success_failure",
    "response_phase",
    "scenario_revision",
]
TransformationNodeType = Literal[
    "constant",
    "fx",
    "concat",
    "ifelse",
    "map",
    "coalesce",
    "lookup",
    "filter",
    "validate",
]
InterfaceOperationKindName = Literal["operation", "event", "command", "query"]

IntegrationDomainAction = Literal[
    "reuse_contract",
    "create_contract",
    "create_mapping",
    "create_transformation",
    "configure_resilience",
    "create_scenario",
    "define_conformance_expectation",
]


class IntegrationOperationRef(BaseModel):
    """A reference to an interface operation/command/query/event, resolved by ID or name."""

    model_config = ConfigDict(extra="forbid")

    operation_id: UUID | None = None
    interface_id: UUID | None = None
    name: str | None = Field(default=None, max_length=160)
    kind: InterfaceOperationKindName | None = None


class IntegrationPhaseIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_refs: list[IntegrationOperationRef] = Field(default_factory=list, max_length=50)
    routing: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)


class ContractProposal(BaseModel):
    """A proposed new draft Contract. Never applied in this slice."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(default="contract", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    purpose: str | None = Field(default=None, max_length=300)
    source_system_id: UUID
    source_object_id: UUID
    target_system_id: UUID
    target_object_id: UUID
    error_response_object_id: UUID | None = None
    interaction_type: IntegrationInteractionType
    pattern: IntegrationPatternName
    implementation_status: IntegrationImplementationStatus = "draft"
    producer_interface_id: UUID | None = None
    consumer_interface_id: UUID | None = None
    external_identifier: str | None = Field(default=None, max_length=255)
    request_phase: IntegrationPhaseIntent | None = None
    success_response_phase: IntegrationPhaseIntent | None = None
    error_response_phase: IntegrationPhaseIntent | None = None


class FieldMappingProposal(BaseModel):
    """A proposed field mapping inside a contract phase."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    phase: ScenarioPhaseName = "request"
    source_field_id: UUID | None = None
    source_object_id: UUID | None = None
    source_field_name: str | None = Field(default=None, max_length=160)
    source_external_identifier: str | None = Field(default=None, max_length=255)
    target_field_id: UUID | None = None
    target_object_id: UUID | None = None
    target_field_name: str | None = Field(default=None, max_length=160)
    target_external_identifier: str | None = Field(default=None, max_length=255)
    required: bool = True
    transformation_key: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)


class TransformationProposal(BaseModel):
    """A supported transformation node over real Catalog fields. Never executable code."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    phase: ScenarioPhaseName = "request"
    node_type: TransformationNodeType
    source_field_ids: list[UUID] = Field(default_factory=list, max_length=20)
    target_field_id: UUID
    config: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=1000)
    evidence: str | None = Field(default=None, max_length=1000)


class ScenarioProposal(BaseModel):
    """A proposed design-time scenario referencing the proposal's contract."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    scenario_type: ScenarioPreset
    description: str | None = Field(default=None, max_length=2000)
    phase: ScenarioPhaseName = "request"
    synthetic_values: dict[str, Any] = Field(default_factory=dict, max_length=100)
    expected_values: dict[str, Any] = Field(default_factory=dict, max_length=100)
    assertion_text: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)


class ConformanceProposal(BaseModel):
    """A proposed conformance expectation over the proposal's contract/scenario."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    expectation_type: ConformanceExpectationType
    phase: ScenarioPhaseName | None = None
    coverage_min: float | None = Field(default=None, ge=0.0, le=1.0)
    field_ids: list[UUID] = Field(default_factory=list, max_length=100)
    expected_success: bool | None = None
    expected_phase: ScenarioPhaseName | None = None
    scenario_key: str | None = Field(default=None, max_length=80)
    expected_revision: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=1000)


class IntegrationProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: UUID
    summary: str = Field(min_length=1, max_length=2000)
    contract_id: UUID | None = None
    contract: ContractProposal | None = None
    based_on_contract_id: UUID | None = None
    proposal_intent: ProposalIntent = "independent"
    runtime_mediated: bool = False
    runtime_system_id: UUID | None = None
    runtime_responsibility: str | None = Field(default=None, max_length=300)
    resilience: IntegrationSpecification | None = None
    mappings: list[FieldMappingProposal] = Field(default_factory=list, max_length=200)
    transformations: list[TransformationProposal] = Field(default_factory=list, max_length=100)
    scenarios: list[ScenarioProposal] = Field(default_factory=list, max_length=50)
    conformance: list[ConformanceProposal] = Field(default_factory=list, max_length=100)


class DirectIntegrationRequest(IntegrationProposalRequest):
    pass


class EventDrivenIntegrationRequest(IntegrationProposalRequest):
    pass


class RuntimeMediatedIntegrationRequest(IntegrationProposalRequest):
    pass


class FileTransferIntegrationRequest(IntegrationProposalRequest):
    pass


class ContractProposalRequest(IntegrationProposalRequest):
    pass


class FieldMappingsRequest(IntegrationProposalRequest):
    pass


class TransformationsRequest(IntegrationProposalRequest):
    pass


class ResilienceConfigurationRequest(IntegrationProposalRequest):
    pass


class ScenariosRequest(IntegrationProposalRequest):
    pass


class ConformanceTestsRequest(IntegrationProposalRequest):
    pass


# --- Slice 4: composite end-to-end orchestration ----------------------------
# A strict, bounded composite input. Each enabled discipline carries the same
# closed sub-shape its dedicated helper accepts; the orchestrator reuses those
# builders (and their validation) and merges the results into one dependency
# ordered change set. There is no natural-language planner: every field is
# bounded and typed.


class EndToEndEnterpriseSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ProposalNode] = Field(default_factory=list, max_length=200)
    links: list[ProposalLink] = Field(default_factory=list, max_length=300)


class EndToEndInformationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ProposalNode] = Field(default_factory=list, max_length=200)
    links: list[ProposalLink] = Field(default_factory=list, max_length=300)
    realizations: list[ProposalRealization] = Field(default_factory=list, max_length=200)


class EndToEndSolutionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ProposalNode] = Field(default_factory=list, max_length=200)
    links: list[ProposalLink] = Field(default_factory=list, max_length=300)
    interactions: list[ProposalInteraction] = Field(default_factory=list, max_length=200)


class EndToEndIntegrationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: UUID | None = None
    contract: ContractProposal | None = None
    based_on_contract_id: UUID | None = None
    proposal_intent: ProposalIntent = "independent"
    runtime_mediated: bool = False
    runtime_system_id: UUID | None = None
    runtime_responsibility: str | None = Field(default=None, max_length=300)
    resilience: IntegrationSpecification | None = None
    mappings: list[FieldMappingProposal] = Field(default_factory=list, max_length=200)
    transformations: list[TransformationProposal] = Field(default_factory=list, max_length=100)
    scenarios: list[ScenarioProposal] = Field(default_factory=list, max_length=50)
    conformance: list[ConformanceProposal] = Field(default_factory=list, max_length=100)


class EndToEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: UUID
    summary: str = Field(min_length=1, max_length=2000)
    business_intent: str | None = Field(default=None, max_length=2000)
    requested_disciplines: list[Discipline] = Field(default_factory=list, max_length=4)
    preferred_object_ids: list[UUID] = Field(default_factory=list, max_length=200)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    desired_outcomes: list[str] = Field(default_factory=list, max_length=50)
    enterprise: EndToEndEnterpriseSection | None = None
    information: EndToEndInformationSection | None = None
    solution: EndToEndSolutionSection | None = None
    integration: EndToEndIntegrationSection | None = None
