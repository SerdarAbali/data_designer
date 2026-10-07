import json
import math
from typing import Annotated
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

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str | None, Field(max_length=2000)]


def validate_non_null_updates(model: BaseModel, non_nullable: set[str]) -> None:
    invalid = [
        name
        for name in non_nullable
        if name in model.model_fields_set and getattr(model, name) is None
    ]
    if invalid:
        raise ValueError(f"These fields cannot be null: {', '.join(sorted(invalid))}")


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_is_bounded(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(json.dumps(value, separators=(",", ":")).encode("utf-8")) > 16_384:
            raise ValueError("Metadata must not exceed 16 KiB")
        return value


class CatalogResponse(CatalogInput):
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_metadata(cls, value):
        if hasattr(value, "extra_metadata"):
            return {
                **{
                    name: getattr(value, name)
                    for name in cls.model_fields
                    if name != "metadata"
                },
                "metadata": value.extra_metadata,
            }
        return value


class SystemCreate(CatalogInput):
    name: Name
    description: Description = None
    kind: ShortText = "application"
    icon: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=40)
    position: dict[str, float] | None = None
    binding_state: ShortText = "unbound"

    @field_validator("position")
    @classmethod
    def position_is_finite(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is not None and any(
            not math.isfinite(coordinate) for coordinate in value.values()
        ):
            raise ValueError("Position coordinates must be finite numbers")
        return value


class SystemUpdate(CatalogInput):
    name: Name | None = None
    description: Description = None
    kind: ShortText | None = None
    icon: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=40)
    position: dict[str, float] | None = None
    binding_state: ShortText | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "SystemUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        validate_non_null_updates(self, {"name", "kind", "binding_state"})
        return self

    @field_validator("position")
    @classmethod
    def position_is_finite(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is not None and any(
            not math.isfinite(coordinate) for coordinate in value.values()
        ):
            raise ValueError("Position coordinates must be finite numbers")
        return value


class SystemResponse(CatalogResponse):
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    kind: str
    icon: str | None
    color: str | None
    position: dict[str, float] | None
    binding_state: str
    created_at: str
    updated_at: str

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def timestamps_to_iso(cls, value):
        return value.isoformat()


class ObjectCreate(CatalogInput):
    name: Name
    label: Name | None = None
    description: Description = None
    external_identifier: str | None = Field(default=None, max_length=255)
    origin: ShortText = "manual"
    position: int | None = Field(default=None, ge=0)


class ObjectUpdate(CatalogInput):
    name: Name | None = None
    label: Name | None = None
    description: Description = None
    external_identifier: str | None = Field(default=None, max_length=255)
    origin: ShortText | None = None
    position: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def has_changes(self) -> "ObjectUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        validate_non_null_updates(self, {"name", "label", "origin", "position"})
        return self


class ObjectResponse(CatalogResponse):
    id: UUID
    tenant_id: UUID
    system_id: UUID
    name: str
    label: str
    description: str | None
    external_identifier: str | None
    origin: str
    position: int
    created_at: str
    updated_at: str

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def timestamps_to_iso(cls, value):
        return value.isoformat()


class FieldCreate(CatalogInput):
    name: Name
    label: Name | None = None
    description: Description = None
    data_type: ShortText
    required: bool = False
    nullable: bool = True
    default_value: JsonValue = None
    external_identifier: str | None = Field(default=None, max_length=255)
    position: int | None = Field(default=None, ge=0)
    origin: ShortText = "manual"


class FieldUpdate(CatalogInput):
    name: Name | None = None
    label: Name | None = None
    description: Description = None
    data_type: ShortText | None = None
    required: bool | None = None
    nullable: bool | None = None
    default_value: JsonValue = None
    external_identifier: str | None = Field(default=None, max_length=255)
    position: int | None = Field(default=None, ge=0)
    origin: ShortText | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "FieldUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        validate_non_null_updates(
            self,
            {"name", "label", "data_type", "required", "nullable", "position", "origin"},
        )
        return self


class FieldResponse(CatalogResponse):
    id: UUID
    tenant_id: UUID
    object_id: UUID
    name: str
    label: str
    description: str | None
    data_type: str
    required: bool
    nullable: bool
    default_value: JsonValue
    external_identifier: str | None
    position: int
    origin: str
    created_at: str
    updated_at: str

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def timestamps_to_iso(cls, value):
        return value.isoformat()
