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


class ArchitectureObjectCreatedResponse(BaseModel):
    object: ArchitectureObjectResponse
    state: ArchitectureStateResponse
