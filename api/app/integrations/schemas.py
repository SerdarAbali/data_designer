import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.integrations.graph import GraphDocument

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
ArchitectureStatus = Literal["draft", "attention", "healthy"]
InteractionType = Literal["ONE_WAY", "REQUEST_RESPONSE", "ASYNC_CALLBACK"]
IntegrationPattern = Literal[
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
ImplementationStatus = Literal["draft", "in_progress", "built", "verified"]
AuthType = Literal["none", "api_key", "basic", "oauth2", "jwt", "mtls", "saml", "custom"]
BackoffStrategy = Literal["none", "linear", "exponential"]
OrchestrationRole = Literal["orchestration", "choreography", "participant", "none"]
ShortNote = Annotated[str, Field(max_length=2000)]


class SampleRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    row_id: Annotated[str, Field(min_length=1, max_length=100)] = Field(alias="rowId")
    values: dict[str, JsonValue]


def validate_json_size(value, label: str, limit: int) -> None:
    if len(json.dumps(value, separators=(",", ":")).encode("utf-8")) > limit:
        raise ValueError(f"{label} must not exceed {limit // 1024} KiB")


class RetrySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: Annotated[int, Field(ge=0, le=10)] = 0
    backoff: BackoffStrategy = "none"


class SecuritySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_type: AuthType = "none"
    notes: ShortNote = ""


class IntegrationSpecification(BaseModel):
    """Bounded, additive integration resilience/security/routing properties.

    The specification never carries child objects; it stores only scalar or list metadata
    about how the contract behaves. It is not a graph, mapping, schema, or test engine.
    """

    model_config = ConfigDict(extra="forbid")

    retry: RetrySpec = Field(default_factory=RetrySpec)
    timeout_ms: Annotated[int | None, Field(default=None, ge=0, le=600_000)] = None
    idempotent: bool = False
    idempotency_key_field_id: UUID | None = None
    security: SecuritySpec = Field(default_factory=SecuritySpec)
    routing: ShortNote = ""
    orchestration_role: OrchestrationRole = "none"
    error_handling: ShortNote = ""

    @model_validator(mode="after")
    def bounded(self) -> "IntegrationSpecification":
        if not self.idempotent and self.idempotency_key_field_id is not None:
            raise ValueError("An idempotency key requires idempotent to be true")
        validate_json_size(self.model_dump(mode="json"), "Integration specification", 8192)
        return self


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system_id: UUID
    source_object_id: UUID
    target_system_id: UUID
    target_object_id: UUID
    name: Name
    description: Annotated[str | None, Field(max_length=2000)] = None
    trigger_config: dict[str, JsonValue] = Field(default_factory=dict)
    graph: GraphDocument = Field(
        default_factory=lambda: GraphDocument(version=1, nodes=[], edges=[])
    )
    response_graph: GraphDocument = Field(
        default_factory=lambda: GraphDocument(version=1, nodes=[], edges=[])
    )
    error_response_graph: GraphDocument = Field(
        default_factory=lambda: GraphDocument(version=1, nodes=[], edges=[])
    )
    error_response_object_id: UUID | None = None
    interaction_type: InteractionType = "ONE_WAY"
    pattern: IntegrationPattern | None = None
    implementation_status: ImplementationStatus = "draft"
    producer_interface_id: UUID | None = None
    consumer_interface_id: UUID | None = None
    specification: IntegrationSpecification = Field(default_factory=IntegrationSpecification)
    sample_rows: list[SampleRow] = Field(default_factory=list, max_length=100)

    @field_validator("trigger_config")
    @classmethod
    def trigger_config_is_bounded(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        validate_json_size(value, "Trigger configuration", 8192)
        return value

    @model_validator(mode="after")
    def samples_are_bounded(self) -> "IntegrationCreate":
        if self.error_response_object_id is None and (
            self.error_response_graph.nodes or self.error_response_graph.edges
        ):
            raise ValueError("An error response schema is required for its graph")
        if len({row.row_id for row in self.sample_rows}) != len(self.sample_rows):
            raise ValueError("Sample row IDs must be unique")
        validate_json_size([row.model_dump() for row in self.sample_rows], "Sample rows", 65_536)
        return self


class IntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: Annotated[int, Field(ge=1)]
    name: Name | None = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    trigger_config: dict[str, JsonValue] | None = None
    pattern: IntegrationPattern | None = None
    implementation_status: ImplementationStatus | None = None
    producer_interface_id: UUID | None = None
    consumer_interface_id: UUID | None = None
    specification: IntegrationSpecification | None = None
    sample_rows: list[SampleRow] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_update(self) -> "IntegrationUpdate":
        changes = self.model_fields_set - {"expected_revision"}
        if not changes:
            raise ValueError("At least one integration field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be null")
        if "trigger_config" in self.model_fields_set and self.trigger_config is None:
            raise ValueError("Trigger configuration cannot be null")
        if "implementation_status" in self.model_fields_set and self.implementation_status is None:
            raise ValueError("Implementation status cannot be null")
        if "specification" in self.model_fields_set and self.specification is None:
            raise ValueError("Specification cannot be null")
        if "sample_rows" in self.model_fields_set and self.sample_rows is None:
            raise ValueError("Sample rows cannot be null")
        if self.trigger_config is not None:
            validate_json_size(self.trigger_config, "Trigger configuration", 8192)
        if self.sample_rows is not None:
            if len({row.row_id for row in self.sample_rows}) != len(self.sample_rows):
                raise ValueError("Sample row IDs must be unique")
            validate_json_size(
                [row.model_dump() for row in self.sample_rows], "Sample rows", 65_536
            )
        return self


class GraphUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: Annotated[int, Field(ge=1)]
    graph: GraphDocument
    response_graph: GraphDocument | None = None
    error_response_graph: GraphDocument | None = None
    error_response_object_id: UUID | None = None
    interaction_type: InteractionType | None = None
    name: Name | None = None
    pattern: IntegrationPattern | None = None
    implementation_status: ImplementationStatus | None = None
    producer_interface_id: UUID | None = None
    consumer_interface_id: UUID | None = None
    specification: IntegrationSpecification | None = None
    sample_rows: list[SampleRow] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_optional_updates(self) -> "GraphUpdate":
        if self.name is None and "name" in self.model_fields_set:
            raise ValueError("Name cannot be null")
        if self.response_graph is None and "response_graph" in self.model_fields_set:
            raise ValueError("Response graph cannot be null")
        if self.error_response_graph is None and "error_response_graph" in self.model_fields_set:
            raise ValueError("Error response graph cannot be null")
        if self.interaction_type is None and "interaction_type" in self.model_fields_set:
            raise ValueError("Interaction type cannot be null")
        if self.sample_rows is not None:
            if len({row.row_id for row in self.sample_rows}) != len(self.sample_rows):
                raise ValueError("Sample row IDs must be unique")
            validate_json_size(
                [row.model_dump() for row in self.sample_rows],
                "Sample rows",
                65_536,
            )
        return self


class SimulationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    include_trace_values: bool = Field(default=False, alias="includeTraceValues")


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    expected_revision: Annotated[int | None, Field(default=None, ge=1)]
    graph: GraphDocument | None = None
    response_graph: GraphDocument | None = None
    rows: list[SampleRow] | None = Field(default=None, max_length=100)
    response_payload: list[SampleRow] | None = Field(default=None, max_length=100)
    options: SimulationOptions = Field(default_factory=SimulationOptions)

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case_revision(cls, value):
        if isinstance(value, dict):
            normalized = dict(value)
            for camel, snake in (
                ("expectedRevision", "expected_revision"),
                ("responseGraph", "response_graph"),
                ("responsePayload", "response_payload"),
            ):
                if camel in normalized:
                    if snake in normalized:
                        raise ValueError(f"Provide only one {snake} property")
                    normalized[snake] = normalized.pop(camel)
            return normalized
        return value

    @model_validator(mode="after")
    def validate_rows(self) -> "SimulationRequest":
        if self.rows is not None:
            if len({row.row_id for row in self.rows}) != len(self.rows):
                raise ValueError("Simulation row IDs must be unique")
            validate_json_size(
                [row.model_dump(by_alias=True) for row in self.rows],
                "Simulation rows",
                65_536,
            )
        if self.response_payload is not None:
            if len({row.row_id for row in self.response_payload}) != len(self.response_payload):
                raise ValueError("Response payload row IDs must be unique")
            validate_json_size(
                [row.model_dump(by_alias=True) for row in self.response_payload],
                "Response payload",
                65_536,
            )
        return self


class SimulationErrorResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    code: str
    row_id: str = Field(alias="rowId")
    row_index: int = Field(alias="rowIndex")
    node_id: UUID | None = Field(alias="nodeId")
    message: str
    recovered: bool


class SimulationTraceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    node_id: UUID = Field(alias="nodeId")
    node_type: str = Field(alias="nodeType")
    inputs: dict[str, JsonValue]
    outputs: dict[str, JsonValue]
    outcome: str
    error_code: str | None = Field(default=None, alias="errorCode")


class SimulationRowResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    row_id: str = Field(alias="rowId")
    row_index: int = Field(alias="rowIndex")
    outcome: str
    target_values: dict[str, JsonValue] = Field(alias="targetValues")
    errors: list[SimulationErrorResponse]
    trace: list[SimulationTraceResponse]
    trace_truncated: bool = Field(alias="traceTruncated")


class SimulationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    integration_id: UUID = Field(alias="integrationId")
    version: int
    revision: int
    summary: dict[str, int]
    rows: list[SimulationRowResponse]
    trace_truncated: bool = Field(alias="traceTruncated")
    request_outcomes: list[SimulationRowResponse] = Field(alias="requestOutcomes")
    response_outcomes: list[SimulationRowResponse] = Field(alias="responseOutcomes")
    response_summary: dict[str, int] = Field(alias="responseSummary")
    response_trace_truncated: bool = Field(alias="responseTraceTruncated")


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    source_system_id: UUID
    source_object_id: UUID
    target_system_id: UUID
    target_object_id: UUID
    name: str
    description: str | None
    trigger_config: dict[str, JsonValue]
    graph: GraphDocument
    response_graph: GraphDocument
    error_response_graph: GraphDocument = Field(
        default_factory=lambda: GraphDocument(version=1, nodes=[], edges=[])
    )
    error_response_object_id: UUID | None = None
    interaction_type: InteractionType
    pattern: IntegrationPattern | None = None
    implementation_status: ImplementationStatus = "draft"
    producer_interface_id: UUID | None = None
    consumer_interface_id: UUID | None = None
    specification: IntegrationSpecification = Field(default_factory=IntegrationSpecification)
    sample_rows: list[SampleRow]
    revision: int
    created_at: str
    updated_at: str
    deleted_at: str | None

    @field_validator("created_at", "updated_at", "deleted_at", mode="before")
    @classmethod
    def timestamps_to_iso(cls, value):
        return value.isoformat() if value is not None else None


class DependencyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    downstream_integration_id: UUID


class DependencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    upstream_integration_id: UUID
    downstream_integration_id: UUID
    created_at: str

    @field_validator("created_at", mode="before")
    @classmethod
    def timestamp_to_iso(cls, value):
        return value.isoformat()


class ArchitectureIntegrationRef(BaseModel):
    id: UUID
    name: str
    status: ArchitectureStatus


class ArchitectureConflictField(BaseModel):
    object_id: UUID
    object_label: str
    field_id: UUID
    field_label: str


class ArchitectureIntegrationResponse(BaseModel):
    id: UUID
    name: str
    status: ArchitectureStatus
    reasons: list[str]
    target_mapping_count: int
    conflict_fields: list[ArchitectureConflictField]
    upstream: list[ArchitectureIntegrationRef]


class ArchitectureFieldConflictResponse(ArchitectureConflictField):
    integrations: list[ArchitectureIntegrationRef]


class ArchitectureAnalysisResponse(BaseModel):
    integrations: list[ArchitectureIntegrationResponse]
    conflicts: list[ArchitectureFieldConflictResponse]


# --- Integration Designer (Slice 4) ---------------------------------------------
# Read-only projections over the existing contract/mapping/scenario/test engine.
# These schemas never introduce a second contract, schema, mapping, or test model.

InterfaceDirection = Literal["provided", "required"]
OperationKind = Literal["operation", "event", "command", "query"]
ContractStatus = Literal["draft", "in_progress", "built", "verified", "attention"]
ScenarioConformanceStatus = Literal["passing", "failing", "not_run", "outdated"]
FlowPhaseName = Literal["request", "success-response", "async-response", "error-response"]
FlowNodeRole = Literal["validation", "routing", "transformation", "constant"]
ChannelKind = Literal["api", "event", "file"]


class IntegrationOperationSummary(BaseModel):
    object_id: UUID
    name: str
    operation_kind: str
    description: str | None = None


class IntegrationInterfaceRef(BaseModel):
    object_id: UUID
    name: str
    direction: str | None = None
    interface_kind: str | None = None
    protocol: str | None = None
    technology: str | None = None


class IntegrationInterfaceSummary(IntegrationInterfaceRef):
    description: str | None = None
    component_object_id: UUID | None = None
    component_name: str | None = None
    operations: list[IntegrationOperationSummary] = Field(default_factory=list)
    contract_ids: list[UUID] = Field(default_factory=list)


class IntegrationEndpointRef(BaseModel):
    system_id: UUID
    system_name: str
    object_id: UUID
    object_name: str
    system_kind: str | None = None
    is_runtime: bool = False


class IntegrationContractSummary(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    interaction_type: InteractionType
    pattern: str | None = None
    implementation_status: str = "draft"
    revision: int
    updated_at: str | None = None
    status: ContractStatus = "draft"
    source: IntegrationEndpointRef
    target: IntegrationEndpointRef
    producer_interface: IntegrationInterfaceRef | None = None
    consumer_interface: IntegrationInterfaceRef | None = None
    has_request_graph: bool = False
    has_response_graph: bool = False
    has_error_graph: bool = False
    specification: dict[str, JsonValue] = Field(default_factory=dict)
    idempotency_key_field_name: str | None = None
    target_fields_mapped: int = 0
    target_fields_total: int = 0
    scenario_count: int = 0


class IntegrationLandscapeResponse(BaseModel):
    state_id: UUID
    state_type: str
    editable: bool
    contracts: list[IntegrationContractSummary] = Field(default_factory=list)
    interfaces: list[IntegrationInterfaceSummary] = Field(default_factory=list)


class IntegrationFlowTransformation(BaseModel):
    node_id: UUID
    type: str
    label: str
    role: FlowNodeRole = "transformation"
    position: dict[str, float] | None = None


class IntegrationFlowPhase(BaseModel):
    phase: FlowPhaseName
    configured: bool = False
    node_count: int = 0
    transformation_count: int = 0
    transformations: list[IntegrationFlowTransformation] = Field(default_factory=list)
    source_field_count: int = 0
    target_field_count: int = 0
    mapped_target_count: int = 0
    target_fields: list[str] = Field(default_factory=list)
    unmapped_required_fields: list[str] = Field(default_factory=list)


class IntegrationMessageFlowResponse(BaseModel):
    contract: IntegrationContractSummary
    routing: str = ""
    trigger_config: dict[str, JsonValue] = Field(default_factory=dict)
    channel_kind: ChannelKind | None = None
    channel_label: str | None = None
    phases: list[IntegrationFlowPhase] = Field(default_factory=list)


class IntegrationContractDetail(BaseModel):
    contract: IntegrationContractSummary
    source_interface: IntegrationInterfaceSummary | None = None
    target_interface: IntegrationInterfaceSummary | None = None
    phases: list[IntegrationFlowPhase] = Field(default_factory=list)


class IntegrationCoverage(BaseModel):
    mapped: int = 0
    total: int = 0
    ratio: float = 0.0


class IntegrationScenarioStatus(BaseModel):
    id: UUID
    name: str
    category: str
    revision: int
    updated_at: str | None = None
    status: ScenarioConformanceStatus = "not_run"
    step_count: int = 0
    message: str = ""


class IntegrationConformanceResponse(BaseModel):
    contract_id: UUID
    contract_name: str
    revision: int
    updated_at: str | None = None
    request_coverage: IntegrationCoverage = Field(default_factory=IntegrationCoverage)
    response_coverage: IntegrationCoverage = Field(default_factory=IntegrationCoverage)
    error_coverage: IntegrationCoverage = Field(default_factory=IntegrationCoverage)
    scenarios: list[IntegrationScenarioStatus] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class IntegrationSequenceParticipant(BaseModel):
    id: str
    label: str
    kind: str
    system_id: UUID | None = None
    system_name: str | None = None
    is_runtime: bool = False


class IntegrationSequenceInteraction(BaseModel):
    id: str
    kind: str
    phase: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    label: str
    contract_step: bool = False


class IntegrationScenarioSequence(BaseModel):
    id: UUID
    name: str
    category: str
    status: ScenarioConformanceStatus = "not_run"
    revision: int
    outdated: bool = False
    step_count: int = 0
    participants: list[IntegrationSequenceParticipant] = Field(default_factory=list)
    interactions: list[IntegrationSequenceInteraction] = Field(default_factory=list)


class IntegrationSequenceResponse(BaseModel):
    contract_id: UUID
    contract_name: str
    revision: int
    scenarios: list[IntegrationScenarioSequence] = Field(default_factory=list)
