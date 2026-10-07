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


class SampleRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    row_id: Annotated[str, Field(min_length=1, max_length=100)] = Field(alias="rowId")
    values: dict[str, JsonValue]


def validate_json_size(value, label: str, limit: int) -> None:
    if len(json.dumps(value, separators=(",", ":")).encode("utf-8")) > limit:
        raise ValueError(f"{label} must not exceed {limit // 1024} KiB")


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
