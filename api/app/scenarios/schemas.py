"""Design-time scenario schemas.

The scenario document stores only references (contract/system/object/field UUIDs) plus
scenario-owned sample values. It never embeds or alters contract definitions.
"""

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

from app.integrations.schemas import Name, validate_json_size

ScenarioCategory = Literal["happy_path", "alternative", "error"]
ScenarioPhase = Literal["request", "success-response", "error-response", "async-response"]
Ident = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
]
ShortText = Annotated[str, Field(max_length=300)]

MAX_STEPS = 200
MAX_DEPTH = 4
DOCUMENT_LIMIT = 262_144
FieldValues = dict[str, JsonValue]

_aliases = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


def normalize_field_values(value: FieldValues, label: str) -> FieldValues:
    if len(value) > 200:
        raise ValueError(f"{label} cannot contain more than 200 fields")
    normalized: FieldValues = {}
    for key, item in value.items():
        try:
            field_id = str(UUID(key))
        except ValueError as error:
            raise ValueError(f"{label} keys must be field UUIDs") from error
        if field_id in normalized:
            raise ValueError(f"{label} cannot repeat a field UUID")
        normalized[field_id] = item
    return normalized


class ScenarioParticipant(BaseModel):
    model_config = _aliases

    id: Ident
    kind: Literal["system", "actor"]
    system_id: UUID | None = Field(default=None, alias="systemId")
    label: Annotated[str | None, Field(max_length=160)] = None

    @model_validator(mode="after")
    def kind_matches_reference(self) -> "ScenarioParticipant":
        if self.kind == "system" and self.system_id is None:
            raise ValueError("A system participant requires systemId")
        if self.kind == "actor":
            if self.system_id is not None:
                raise ValueError("An actor participant cannot reference a system")
            if not (self.label or "").strip():
                raise ValueError("An actor participant requires a label")
        return self


class ScenarioStateEntry(BaseModel):
    model_config = _aliases

    id: Ident
    participant_id: Ident = Field(alias="participantId")
    object_id: UUID = Field(alias="objectId")
    values: FieldValues = Field(default_factory=dict)
    note: Annotated[str | None, Field(max_length=2000)] = None

    @field_validator("values")
    @classmethod
    def field_keys(cls, value: FieldValues) -> FieldValues:
        return normalize_field_values(value, "State values")


class ScenarioStep(BaseModel):
    model_config = _aliases

    id: Ident
    kind: Literal["contract", "self", "actor"]
    contract_id: UUID | None = Field(default=None, alias="contractId")
    phase: ScenarioPhase | None = None
    from_participant_id: Ident | None = Field(default=None, alias="fromParticipantId")
    to_participant_id: Ident | None = Field(default=None, alias="toParticipantId")
    label: ShortText | None = None
    sample_values: FieldValues = Field(default_factory=dict, alias="sampleValues")
    expected_values: FieldValues = Field(default_factory=dict, alias="expectedValues")
    notes: Annotated[str | None, Field(max_length=4000)] = None

    @field_validator("sample_values")
    @classmethod
    def sample_keys(cls, value: FieldValues) -> FieldValues:
        return normalize_field_values(value, "Sample values")

    @field_validator("expected_values")
    @classmethod
    def expected_keys(cls, value: FieldValues) -> FieldValues:
        return normalize_field_values(value, "Expected values")

    @model_validator(mode="after")
    def kind_shape(self) -> "ScenarioStep":
        if self.kind == "contract":
            if self.contract_id is None or self.phase is None:
                raise ValueError("A contract step requires contractId and phase")
            if self.from_participant_id or self.to_participant_id:
                raise ValueError("Contract step participants are derived from the contract")
            return self
        if self.contract_id is not None or self.phase is not None:
            raise ValueError("Only contract steps may reference a contract or phase")
        if self.sample_values or self.expected_values:
            raise ValueError("Only contract steps may carry sample or expected values")
        if not (self.label or "").strip():
            raise ValueError("Self and actor steps require a label")
        if self.from_participant_id is None:
            raise ValueError("Self and actor steps require fromParticipantId")
        if self.kind == "self":
            if self.to_participant_id not in (None, self.from_participant_id):
                raise ValueError("A self step must start and end on the same participant")
            self.to_participant_id = self.from_participant_id
        elif self.to_participant_id is None:
            raise ValueError("An actor step requires toParticipantId")
        return self


class ScenarioOperand(BaseModel):
    model_config = _aliases

    guard: ShortText = ""
    items: list["ScenarioItem"] = Field(default_factory=list, max_length=MAX_STEPS)


class ScenarioFragment(BaseModel):
    model_config = _aliases

    id: Ident
    kind: Literal["alt", "opt", "loop"]
    operands: list[ScenarioOperand] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def operand_count(self) -> "ScenarioFragment":
        if self.kind == "alt" and len(self.operands) < 2:
            raise ValueError("An alt block requires at least two operands")
        if self.kind != "alt" and len(self.operands) != 1:
            raise ValueError(f"A {self.kind} block has exactly one operand")
        return self


ScenarioItem = Annotated[ScenarioStep | ScenarioFragment, Field(discriminator="kind")]
ScenarioOperand.model_rebuild()


class ScenarioAssertion(BaseModel):
    model_config = _aliases

    id: Ident
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    step_id: Ident | None = Field(default=None, alias="stepId")
    field_id: UUID | None = Field(default=None, alias="fieldId")
    expected: JsonValue = None

    @model_validator(mode="after")
    def field_needs_step(self) -> "ScenarioAssertion":
        if self.field_id is not None and self.step_id is None:
            raise ValueError("A field assertion requires stepId")
        return self


def iter_items(items: list, depth: int = 1):
    """Yield (item, depth) for every step and fragment in document order."""
    for item in items:
        yield item, depth
        if isinstance(item, ScenarioFragment):
            for operand in item.operands:
                yield from iter_items(operand.items, depth + 1)


class ScenarioDocument(BaseModel):
    model_config = _aliases

    version: Literal[1]
    preconditions: Annotated[str, Field(max_length=4000)] = ""
    trigger: Annotated[str, Field(max_length=2000)] = ""
    participants: list[ScenarioParticipant] = Field(default_factory=list, max_length=30)
    contract_ids: list[UUID] = Field(default_factory=list, alias="contractIds", max_length=50)
    before_state: list[ScenarioStateEntry] = Field(
        default_factory=list, alias="beforeState", max_length=100
    )
    after_state: list[ScenarioStateEntry] = Field(
        default_factory=list, alias="afterState", max_length=100
    )
    items: list[ScenarioItem] = Field(default_factory=list, max_length=MAX_STEPS)
    assertions: list[ScenarioAssertion] = Field(default_factory=list, max_length=200)
    notes: Annotated[str, Field(max_length=8000)] = ""

    def steps(self) -> list[ScenarioStep]:
        return [item for item, _ in iter_items(self.items) if isinstance(item, ScenarioStep)]

    @model_validator(mode="after")
    def consistent_document(self) -> "ScenarioDocument":
        def unique(ids: list[str], label: str) -> None:
            if len(set(ids)) != len(ids):
                raise ValueError(f"{label} IDs must be unique")

        participant_ids = [item.id for item in self.participants]
        unique(participant_ids, "Participant")
        unique([str(item) for item in self.contract_ids], "Participating contract")
        unique(
            [item.id for item in self.before_state] + [item.id for item in self.after_state],
            "State entry",
        )
        unique([item.id for item in self.assertions], "Assertion")

        item_ids: list[str] = []
        step_count = 0
        for item, depth in iter_items(self.items):
            if depth > MAX_DEPTH:
                raise ValueError(f"Blocks cannot be nested more than {MAX_DEPTH - 1} deep")
            item_ids.append(item.id)
            if isinstance(item, ScenarioStep):
                step_count += 1
                for ref in (item.from_participant_id, item.to_participant_id):
                    if ref is not None and ref not in participant_ids:
                        raise ValueError(f"Step {item.id} references unknown participant {ref}")
        if step_count > MAX_STEPS:
            raise ValueError(f"A scenario cannot contain more than {MAX_STEPS} steps")
        unique(item_ids, "Step and block")

        system_participants = {
            item.id for item in self.participants if item.kind == "system"
        }
        for entry in self.before_state + self.after_state:
            if entry.participant_id not in system_participants:
                raise ValueError("State entries must belong to a system participant")

        contract_steps = {item.id for item in self.steps() if item.kind == "contract"}
        for assertion in self.assertions:
            if assertion.step_id is not None and assertion.step_id not in item_ids:
                raise ValueError(f"Assertion {assertion.id} references an unknown step")
            if assertion.field_id is not None and assertion.step_id not in contract_steps:
                raise ValueError("Field assertions must reference a contract step")

        validate_json_size(
            self.model_dump(mode="json", by_alias=True), "Scenario document", DOCUMENT_LIMIT
        )
        return self


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_integration_id: UUID | None = None
    name: Name
    category: ScenarioCategory = "happy_path"
    description: Annotated[str | None, Field(max_length=2000)] = None
    document: ScenarioDocument


class ScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: Annotated[int, Field(ge=1)]
    name: Name
    category: ScenarioCategory
    description: Annotated[str | None, Field(max_length=2000)] = None
    document: ScenarioDocument


class ScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope_integration_id: UUID | None
    name: str
    category: ScenarioCategory
    description: str | None
    document: dict[str, JsonValue]
    revision: int
    created_at: str
    updated_at: str

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def timestamps_to_iso(cls, value):
        return value.isoformat()


class ScenarioEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_integration_id: UUID | None = None
    document: ScenarioDocument


class MissingReference(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    kind: Literal["contract", "phase", "system", "object", "field"]
    id: str
    message: str
    step_id: str | None = Field(default=None, serialization_alias="stepId")


class StepMismatch(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    field_id: str = Field(serialization_alias="fieldId")
    expected: JsonValue
    actual: JsonValue
    present: bool


class StepEvaluation(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    step_id: str = Field(serialization_alias="stepId")
    contract_id: str | None = Field(serialization_alias="contractId")
    phase: ScenarioPhase | None
    outcome: Literal[
        "ok", "mismatch", "failed", "skipped", "missing_reference", "not_evaluated"
    ]
    target_values: dict[str, JsonValue] = Field(
        default_factory=dict, serialization_alias="targetValues"
    )
    errors: list[dict[str, JsonValue]] = Field(default_factory=list)
    mismatches: list[StepMismatch] = Field(default_factory=list)


class AssertionEvaluation(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    assertion_id: str = Field(serialization_alias="assertionId")
    status: Literal["passed", "failed", "manual", "not_evaluated"]
    message: str


class ScenarioEvaluateResponse(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    steps: list[StepEvaluation]
    assertions: list[AssertionEvaluation]
    missing_references: list[MissingReference] = Field(
        serialization_alias="missingReferences"
    )
    summary: dict[str, int]
