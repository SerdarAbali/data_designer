from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

StateType = Literal["current", "candidate", "target"]
ArchitectureDiscipline = Literal["enterprise", "information", "solution", "integration"]
ArchitectureObjectKind = Literal[
    "business_requirement",
    "business_capability",
    "information_object",
    "solution_boundary",
    "component",
    "interface",
]


class ArchitectureStateNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    occurrence_id: str
    object_id: UUID
    position: dict[str, float]
    discipline: ArchitectureDiscipline | None = None
    parent_occurrence_id: str | None = None
    width: float | None = None
    height: float | None = None
    display_metadata: dict[str, Any] = Field(default_factory=dict)
    candidate_overrides: dict[str, Any] = Field(default_factory=dict)


class ArchitectureStateRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    target_id: str
    type: str = "Uses"
    name: str | None = None
    integration_id: UUID | None = None
    candidate_overrides: dict[str, Any] = Field(default_factory=dict)
    display_metadata: dict[str, Any] = Field(default_factory=dict)


class ArchitectureStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    state_type: str
    description: str | None = None
    nodes: list[ArchitectureStateNode] = Field(default_factory=list)
    relationships: list[ArchitectureStateRelationship] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ArchitectureStateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    state_type: StateType = "current"
    description: str | None = Field(default=None, max_length=2000)
    nodes: list[ArchitectureStateNode] = Field(default_factory=list)
    relationships: list[ArchitectureStateRelationship] = Field(default_factory=list)


class ArchitectureStateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    nodes: list[ArchitectureStateNode] | None = None
    relationships: list[ArchitectureStateRelationship] | None = None


class DuplicateStateRequest(BaseModel):
    target_name: str = Field(min_length=1, max_length=160)
    target_state_type: Literal["candidate", "target"] = "candidate"
    description: str | None = Field(default=None, max_length=2000)


class ArchitectureObjectCreate(BaseModel):
    kind: ArchitectureObjectKind
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    authoritative_system_id: UUID | None = None
    related_system_id: UUID | None = None
    position: dict[str, float]


class ArchitectureObjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    authoritative_system_id: UUID | None = None


class ArchitectureObjectResponse(BaseModel):
    id: UUID
    kind: ArchitectureObjectKind
    name: str
    description: str | None = None
    owner: str | None = None
    authoritative_system_id: UUID | None = None
    external_identifier: str | None = None
    classification: str | None = None


class ArchitectureObjectCreatedResponse(BaseModel):
    object: ArchitectureObjectResponse
    state: ArchitectureStateResponse


class IncludeObjectsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_ids: list[UUID] = Field(default_factory=list, max_length=500)
    architecture_object_ids: list[UUID] = Field(default_factory=list, max_length=500)
    integration_ids: list[UUID] = Field(default_factory=list, max_length=500)
    visualize_solution_membership: bool = True


class IncludeObjectsSkipped(BaseModel):
    kind: str
    id: UUID
    name: str | None = None
    message: str


class IncludeObjectsResponse(BaseModel):
    state: ArchitectureStateResponse
    added_occurrences: int
    added_relationships: int
    skipped: list[IncludeObjectsSkipped] = Field(default_factory=list)


InformationCardinality = Literal["one_to_one", "one_to_many", "many_to_many"]


class InformationRealization(BaseModel):
    catalog_object_id: UUID | None = None
    catalog_field_id: UUID | None = None
    catalog_object_name: str | None = None
    catalog_field_name: str | None = None


class InformationAttributeResponse(BaseModel):
    object_id: UUID
    entity_object_id: UUID
    name: str
    data_type: str
    required: bool
    nullable: bool
    is_key: bool
    is_identifier: bool
    ordinal: int
    definition: str | None = None
    created_in_state_id: UUID | None = None
    realization: InformationRealization | None = None


class InformationEntityResponse(BaseModel):
    object_id: UUID
    occurrence_id: str
    name: str
    description: str | None = None
    owner: str | None = None
    steward: str | None = None
    authoritative_system_id: UUID | None = None
    authoritative_system_name: str | None = None
    classification: str | None = None
    sensitivity: str | None = None
    external_identifier: str | None = None
    position: dict[str, float]
    attributes: list[InformationAttributeResponse] = Field(default_factory=list)


class InformationRelationshipResponse(BaseModel):
    id: UUID
    source_object_id: UUID
    target_object_id: UUID
    name: str | None = None
    cardinality: InformationCardinality
    source_optional: bool
    target_optional: bool
    # Optional manual connector endpoints; absent means automatic routing.
    source_handle: str | None = None
    target_handle: str | None = None


class InformationModelResponse(BaseModel):
    state_id: UUID
    state_type: StateType
    editable: bool
    entities: list[InformationEntityResponse]
    relationships: list[InformationRelationshipResponse]


class InformationEntityCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    steward: str | None = Field(default=None, max_length=160)
    authoritative_system_id: UUID | None = None
    classification: str | None = Field(default=None, max_length=100)
    sensitivity: str | None = Field(default=None, max_length=40)
    position: dict[str, float]


class InformationEntityUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    steward: str | None = Field(default=None, max_length=160)
    authoritative_system_id: UUID | None = None
    classification: str | None = Field(default=None, max_length=100)
    sensitivity: str | None = Field(default=None, max_length=40)


class InformationEntityCreatedResponse(BaseModel):
    entity: InformationEntityResponse
    state: ArchitectureStateResponse


class InformationAttributeCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    data_type: str = Field(default="string", max_length=100)
    required: bool = False
    nullable: bool = True
    is_key: bool = False
    is_identifier: bool = False
    ordinal: int = 0
    definition: str | None = Field(default=None, max_length=2000)


class InformationAttributeUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    data_type: str | None = Field(default=None, max_length=100)
    required: bool | None = None
    nullable: bool | None = None
    is_key: bool | None = None
    is_identifier: bool | None = None
    ordinal: int | None = None
    definition: str | None = Field(default=None, max_length=2000)


class InformationRealizationRequest(BaseModel):
    state_id: UUID
    catalog_field_id: UUID | None = None
    catalog_object_id: UUID | None = None


class InformationRelationshipCreate(BaseModel):
    state_id: UUID
    source_object_id: UUID
    target_object_id: UUID
    name: str | None = Field(default=None, max_length=160)
    cardinality: InformationCardinality = "one_to_many"
    source_optional: bool = False
    target_optional: bool = True
    source_handle: str | None = Field(default=None, max_length=32)
    target_handle: str | None = Field(default=None, max_length=32)


class InformationRelationshipUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    cardinality: InformationCardinality | None = None
    source_optional: bool | None = None
    target_optional: bool | None = None
    # Reconnection may reassign the endpoints; None (unset) leaves them as-is.
    source_object_id: UUID | None = None
    target_object_id: UUID | None = None
    source_handle: str | None = Field(default=None, max_length=32)
    target_handle: str | None = Field(default=None, max_length=32)


# --- Information Architecture completion projections -------------------------
# Additive, read-only projections derived from the existing information model,
# catalog rows, integration contracts and state scoping. No new source of truth.

InformationRealizationStatus = Literal["realized", "partial", "unmapped", "invalid"]
InformationChangeType = Literal["added", "removed", "changed", "reused"]


class InformationConcept(BaseModel):
    object_id: UUID
    name: str
    description: str | None = None
    owner: str | None = None


class InformationConceptRelationship(BaseModel):
    id: UUID
    source_object_id: UUID
    target_object_id: UUID
    name: str | None = None
    cardinality: InformationCardinality


class InformationConceptualResponse(BaseModel):
    state_id: UUID
    concepts: list[InformationConcept]
    relationships: list[InformationConceptRelationship]


class InformationContractRef(BaseModel):
    id: UUID
    name: str
    direction: str


class InformationPhysicalMapping(BaseModel):
    entity_object_id: UUID
    entity_name: str
    attribute_object_id: UUID
    attribute_name: str
    data_type: str
    required: bool
    status: InformationRealizationStatus
    system_id: UUID | None = None
    system_name: str | None = None
    catalog_object_id: UUID | None = None
    catalog_object_name: str | None = None
    catalog_field_id: UUID | None = None
    catalog_field_name: str | None = None
    contracts: list[InformationContractRef] = Field(default_factory=list)


class InformationPhysicalResponse(BaseModel):
    state_id: UUID
    mappings: list[InformationPhysicalMapping]
    summary: dict[str, int]


class InformationOwnershipEntry(BaseModel):
    object_id: UUID
    name: str
    owner: str | None = None
    steward: str | None = None
    authoritative_system_id: UUID | None = None
    authoritative_system_name: str | None = None
    authoritative_in_state: bool = False
    classification: str | None = None
    sensitivity: str | None = None
    realization_count: int = 0
    systems: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class InformationOwnershipResponse(BaseModel):
    state_id: UUID
    entries: list[InformationOwnershipEntry]


class InformationLineageNode(BaseModel):
    id: str
    kind: str
    name: str
    detail: str | None = None
    system_name: str | None = None
    catalog_field_id: UUID | None = None
    contract_id: UUID | None = None


class InformationLineageEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str


class InformationLineageResponse(BaseModel):
    state_id: UUID
    nodes: list[InformationLineageNode]
    edges: list[InformationLineageEdge]
    gaps: list[str]


class InformationImpactChange(BaseModel):
    object_type: str
    object_id: UUID
    name: str
    entity_object_id: UUID | None = None
    entity_name: str | None = None
    change: InformationChangeType
    changed_fields: list[str] = Field(default_factory=list)
    reason: str | None = None


class InformationImpactResponse(BaseModel):
    state_id: UUID
    baseline_state_id: UUID | None = None
    supported: bool
    changes: list[InformationImpactChange]
    unresolved: list[str]
    summary: dict[str, int]


SolutionInterfaceDirection = Literal["provided", "required"]
SolutionOperationKind = Literal["operation", "event", "command", "query"]
SolutionInterfaceKind = Literal["sync", "async"]
SOLUTION_COMPONENT_TYPES = (
    "application",
    "service",
    "data",
    "ui",
    "integration",
    "infrastructure",
)


class SolutionOperationResponse(BaseModel):
    object_id: UUID
    interface_object_id: UUID
    name: str
    description: str | None = None
    operation_kind: SolutionOperationKind
    request_object_id: UUID | None = None
    response_object_id: UUID | None = None
    ordinal: int
    created_in_state_id: UUID | None = None


class SolutionInterfaceResponse(BaseModel):
    object_id: UUID
    component_object_id: UUID | None = None
    name: str
    description: str | None = None
    direction: SolutionInterfaceDirection
    interface_kind: SolutionInterfaceKind | None = None
    protocol: str | None = None
    technology: str | None = None
    created_in_state_id: UUID | None = None
    operations: list[SolutionOperationResponse] = Field(default_factory=list)


class SolutionComponentResponse(BaseModel):
    object_id: UUID
    occurrence_id: str
    solution_object_id: UUID | None = None
    parent_component_object_id: UUID | None = None
    name: str
    description: str | None = None
    responsibility: str | None = None
    component_type: str | None = None
    technology: str | None = None
    position: dict[str, float]
    created_in_state_id: UUID | None = None
    interfaces: list[SolutionInterfaceResponse] = Field(default_factory=list)


class SolutionRepositoryResponse(BaseModel):
    object_id: UUID
    solution_object_id: UUID | None = None
    name: str
    description: str | None = None
    owner: str | None = None
    repository_type: str | None = None
    technology: str | None = None
    created_in_state_id: UUID | None = None


class SolutionDeploymentResponse(BaseModel):
    object_id: UUID
    solution_object_id: UUID | None = None
    name: str
    description: str | None = None
    technology: str | None = None
    environment: str | None = None
    hosting: str | None = None
    created_in_state_id: UUID | None = None


class SolutionTrustBoundaryResponse(BaseModel):
    object_id: UUID
    solution_object_id: UUID | None = None
    name: str
    description: str | None = None
    security_level: str | None = None
    created_in_state_id: UUID | None = None


class SolutionMemberResponse(BaseModel):
    system_id: UUID
    name: str
    kind: str


class SolutionContextResponse(BaseModel):
    solution_object_id: UUID
    occurrence_id: str
    name: str
    description: str | None = None
    owner: str | None = None
    position: dict[str, float]
    members: list[SolutionMemberResponse] = Field(default_factory=list)
    external_systems: list[SolutionMemberResponse] = Field(default_factory=list)


class SolutionLinkResponse(BaseModel):
    id: UUID
    source_object_id: UUID
    target_object_id: UUID
    relationship_type: str


class SolutionSummary(BaseModel):
    object_id: UUID
    occurrence_id: str
    name: str
    description: str | None = None
    component_count: int
    member_count: int


class SolutionDesignResponse(BaseModel):
    state_id: UUID
    state_type: StateType
    editable: bool
    solution: SolutionContextResponse
    components: list[SolutionComponentResponse] = Field(default_factory=list)
    repositories: list[SolutionRepositoryResponse] = Field(default_factory=list)
    deployment_nodes: list[SolutionDeploymentResponse] = Field(default_factory=list)
    trust_boundaries: list[SolutionTrustBoundaryResponse] = Field(default_factory=list)
    links: list[SolutionLinkResponse] = Field(default_factory=list)


class SolutionCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 80.0, "y": 80.0})


class SolutionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)


class SolutionMemberCreate(BaseModel):
    state_id: UUID
    system_id: UUID
    position: dict[str, float] | None = None


class SolutionComponentCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    responsibility: str | None = Field(default=None, max_length=2000)
    component_type: str | None = Field(default=None, max_length=60)
    technology: str | None = Field(default=None, max_length=160)
    parent_component_object_id: UUID | None = None
    position: dict[str, float]


class SolutionComponentUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    responsibility: str | None = Field(default=None, max_length=2000)
    component_type: str | None = Field(default=None, max_length=60)
    technology: str | None = Field(default=None, max_length=160)


class SolutionInterfaceCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    direction: SolutionInterfaceDirection = "provided"
    interface_kind: SolutionInterfaceKind | None = None
    protocol: str | None = Field(default=None, max_length=60)
    technology: str | None = Field(default=None, max_length=160)


class SolutionInterfaceUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    direction: SolutionInterfaceDirection | None = None
    interface_kind: SolutionInterfaceKind | None = None
    protocol: str | None = Field(default=None, max_length=60)
    technology: str | None = Field(default=None, max_length=160)


class SolutionOperationCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    operation_kind: SolutionOperationKind = "operation"
    request_object_id: UUID | None = None
    response_object_id: UUID | None = None
    ordinal: int = 0


class SolutionOperationUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    operation_kind: SolutionOperationKind | None = None
    request_object_id: UUID | None = None
    response_object_id: UUID | None = None
    ordinal: int | None = None


class SolutionRepositoryCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=160)
    repository_type: str | None = Field(default=None, max_length=40)
    technology: str | None = Field(default=None, max_length=160)


class SolutionRepositoryUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=160)
    repository_type: str | None = Field(default=None, max_length=40)
    technology: str | None = Field(default=None, max_length=160)


class SolutionDeploymentCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    technology: str | None = Field(default=None, max_length=160)
    environment: str | None = Field(default=None, max_length=40)
    hosting: str | None = Field(default=None, max_length=40)


class SolutionDeploymentUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    technology: str | None = Field(default=None, max_length=160)
    environment: str | None = Field(default=None, max_length=40)
    hosting: str | None = Field(default=None, max_length=40)


class SolutionTrustBoundaryCreate(BaseModel):
    state_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    security_level: str | None = Field(default=None, max_length=40)


class SolutionTrustBoundaryUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    security_level: str | None = Field(default=None, max_length=40)


class SolutionLinkRequest(BaseModel):
    state_id: UUID
    target_object_id: UUID | None = None


EnterpriseObjectType = Literal["goal", "requirement", "capability", "process", "principle", "role"]
EnterpriseProcessType = Literal["process", "value_stream"]
EnterprisePrincipleType = Literal["principle", "constraint", "quality", "risk"]
EnterpriseRoleType = Literal["organization", "role"]
ImpactChangeType = Literal["added", "removed", "changed", "reused"]


class EnterpriseObjectResponse(BaseModel):
    object_id: UUID
    kind: EnterpriseObjectType
    name: str
    description: str | None = None
    owner: str | None = None
    outcome_metric: str | None = None
    horizon: str | None = None
    process_type: str | None = None
    principle_type: str | None = None
    rationale: str | None = None
    role_type: str | None = None
    created_in_state_id: UUID | None = None


class EnterpriseApplicationResponse(BaseModel):
    object_id: UUID
    name: str
    kind: str
    description: str | None = None


class EnterpriseLinkResponse(BaseModel):
    id: UUID
    source_object_id: UUID
    target_object_id: UUID
    relationship_type: str


class EnterpriseModelResponse(BaseModel):
    state_id: UUID
    state_type: StateType
    editable: bool
    goals: list[EnterpriseObjectResponse] = Field(default_factory=list)
    requirements: list[EnterpriseObjectResponse] = Field(default_factory=list)
    capabilities: list[EnterpriseObjectResponse] = Field(default_factory=list)
    processes: list[EnterpriseObjectResponse] = Field(default_factory=list)
    principles: list[EnterpriseObjectResponse] = Field(default_factory=list)
    roles: list[EnterpriseObjectResponse] = Field(default_factory=list)
    applications: list[EnterpriseApplicationResponse] = Field(default_factory=list)
    links: list[EnterpriseLinkResponse] = Field(default_factory=list)


class EnterpriseObjectCreate(BaseModel):
    state_id: UUID
    kind: EnterpriseObjectType
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    outcome_metric: str | None = Field(default=None, max_length=500)
    horizon: str | None = Field(default=None, max_length=60)
    process_type: EnterpriseProcessType | None = None
    principle_type: EnterprisePrincipleType | None = None
    rationale: str | None = Field(default=None, max_length=2000)
    role_type: EnterpriseRoleType | None = None
    position: dict[str, float] | None = None


class EnterpriseObjectUpdate(BaseModel):
    state_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=160)
    outcome_metric: str | None = Field(default=None, max_length=500)
    horizon: str | None = Field(default=None, max_length=60)
    process_type: EnterpriseProcessType | None = None
    principle_type: EnterprisePrincipleType | None = None
    rationale: str | None = Field(default=None, max_length=2000)
    role_type: EnterpriseRoleType | None = None


class EnterpriseLinkCreate(BaseModel):
    state_id: UUID
    relationship_type: str = Field(min_length=1, max_length=60)
    source_object_id: UUID
    target_object_id: UUID


class CapabilityMapEntry(BaseModel):
    capability: EnterpriseObjectResponse
    processes: list[EnterpriseObjectResponse] = Field(default_factory=list)
    applications: list[EnterpriseApplicationResponse] = Field(default_factory=list)
    principles: list[EnterpriseObjectResponse] = Field(default_factory=list)
    owner_role: EnterpriseObjectResponse | None = None


class CapabilityMapResponse(BaseModel):
    state_id: UUID
    capabilities: list[CapabilityMapEntry] = Field(default_factory=list)


class ProcessImpactEntry(BaseModel):
    process: EnterpriseObjectResponse
    capabilities: list[EnterpriseObjectResponse] = Field(default_factory=list)
    applications: list[EnterpriseApplicationResponse] = Field(default_factory=list)
    requirements: list[EnterpriseObjectResponse] = Field(default_factory=list)
    governed_by: list[EnterpriseObjectResponse] = Field(default_factory=list)
    impacted: bool = False


class ProcessImpactResponse(BaseModel):
    state_id: UUID
    processes: list[ProcessImpactEntry] = Field(default_factory=list)


class ApplicationSupportEntry(BaseModel):
    application: EnterpriseApplicationResponse
    capabilities: list[EnterpriseObjectResponse] = Field(default_factory=list)
    processes: list[EnterpriseObjectResponse] = Field(default_factory=list)
    requirements: list[EnterpriseObjectResponse] = Field(default_factory=list)


class ApplicationSupportResponse(BaseModel):
    state_id: UUID
    applications: list[ApplicationSupportEntry] = Field(default_factory=list)


class StrategyTraceStep(BaseModel):
    requirement: EnterpriseObjectResponse
    capabilities: list[EnterpriseObjectResponse] = Field(default_factory=list)
    processes: list[EnterpriseObjectResponse] = Field(default_factory=list)
    applications: list[EnterpriseApplicationResponse] = Field(default_factory=list)


class StrategyTraceChain(BaseModel):
    goal: EnterpriseObjectResponse
    steps: list[StrategyTraceStep] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class StrategyTraceResponse(BaseModel):
    state_id: UUID
    chains: list[StrategyTraceChain] = Field(default_factory=list)
    unlinked_requirements: list[EnterpriseObjectResponse] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ImpactChange(BaseModel):
    object_id: UUID
    kind: str
    name: str
    change: ImpactChangeType
    changed_fields: list[str] = Field(default_factory=list)


class EnterpriseImpactResponse(BaseModel):
    state_id: UUID
    baseline_state_id: UUID | None = None
    changes: list[ImpactChange] = Field(default_factory=list)
    affected_applications: list[EnterpriseApplicationResponse] = Field(default_factory=list)
    affected_capabilities: list[EnterpriseObjectResponse] = Field(default_factory=list)
    affected_processes: list[EnterpriseObjectResponse] = Field(default_factory=list)
    unresolved_dependencies: list[str] = Field(default_factory=list)
    unresolved_constraints: list[str] = Field(default_factory=list)
    risks: list[EnterpriseObjectResponse] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


# --- Cross-discipline traceability (Slice 5) -----------------------------------

TraceDirection = Literal["both", "outgoing", "incoming"]
TraceStateMembership = Literal["current", "candidate", "target", "none"]


class TraceObjectRef(BaseModel):
    id: UUID
    kind: str
    name: str
    description: str | None = None
    discipline: str | None = None
    state_membership: TraceStateMembership = "none"
    external: bool = False


class TraceEdge(BaseModel):
    id: str
    source_object_id: UUID
    target_object_id: UUID
    relationship_type: str
    derived: bool = False


class TraceNeighbor(BaseModel):
    relationship_type: str
    direction: Literal["outgoing", "incoming"]
    derived: bool
    object: TraceObjectRef


class TraceUsageGroup(BaseModel):
    label: str
    objects: list[TraceObjectRef] = Field(default_factory=list)


class ObjectTraceResponse(BaseModel):
    state_id: UUID
    object: TraceObjectRef
    disciplines: list[str] = Field(default_factory=list)
    outgoing: list[TraceNeighbor] = Field(default_factory=list)
    incoming: list[TraceNeighbor] = Field(default_factory=list)
    groups: list[TraceUsageGroup] = Field(default_factory=list)
    physical_refs: list[TraceObjectRef] = Field(default_factory=list)
    tests: list[TraceObjectRef] = Field(default_factory=list)
    principles: list[TraceObjectRef] = Field(default_factory=list)


class ArchitectureGraphResponse(BaseModel):
    state_id: UUID
    nodes: list[TraceObjectRef] = Field(default_factory=list)
    edges: list[TraceEdge] = Field(default_factory=list)


class TraceResponse(BaseModel):
    state_id: UUID
    direction: TraceDirection
    max_depth: int
    root: TraceObjectRef
    nodes: list[TraceObjectRef] = Field(default_factory=list)
    edges: list[TraceEdge] = Field(default_factory=list)
    depths: dict[str, int] = Field(default_factory=dict)
