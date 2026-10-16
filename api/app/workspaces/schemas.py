from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

DEFAULT_DISCIPLINES = ["enterprise", "information", "solution", "integration"]

Discipline = Literal["enterprise", "information", "solution", "integration"]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


Disciplines = Annotated[list[Discipline], Field(min_length=1), AfterValidator(_dedupe)]


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    disciplines: list[str] = Field(default_factory=lambda: list(DEFAULT_DISCIPLINES))
    created_at: datetime
    is_active: bool = False
    systems_count: int = 0
    contracts_count: int = 0
    scenarios_count: int = 0
    demo_preset: str | None = None
    demo_version: str | None = None
    demo_generated_at: datetime | None = None


DemoPreset = Literal["full", "solution_integration", "integration_only"]


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    disciplines: Disciplines = Field(default_factory=lambda: list(DEFAULT_DISCIPLINES))
    seed_demo_data: bool = False
    demo_preset: DemoPreset | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    disciplines: Disciplines | None = None


class WorkspaceFork(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    disciplines: Disciplines | None = None
