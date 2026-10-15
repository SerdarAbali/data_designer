"""Schemas for the guided architecture import experience."""

import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ImportType = Literal["system", "information_object", "integration", "solution"]
RowDecision = Literal["create", "update", "use_existing", "skip"]
MatchMethod = Literal["external_id", "exact_name", "alias", "similar_name", "none"]
RowStatus = Literal[
    "created",
    "updated",
    "matched",
    "skipped",
    "blocked",
    "failed",
    "undone",
    "conflict",
]
BatchStatus = Literal["applied", "undone", "undo_blocked"]

MAX_ROWS = 500
MAX_HEADERS = 64
MAX_CELL_CHARS = 2000
MAX_HEADER_CHARS = 200
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024

ImportCell = Annotated[str, Field(max_length=MAX_CELL_CHARS)]
ImportHeader = Annotated[str, Field(max_length=MAX_HEADER_CHARS)]


class ImportPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_type: ImportType
    headers: list[ImportHeader] = Field(default_factory=list, max_length=MAX_HEADERS)
    rows: list[list[ImportCell]] = Field(default_factory=list, max_length=MAX_ROWS)
    column_mapping: dict[str, str] = Field(default_factory=dict)
    source_filename: str = Field(default="", max_length=255)
    sheet_name: str = Field(default="", max_length=120)

    @field_validator("rows")
    @classmethod
    def rows_are_bounded(cls, value: list[list[str]]) -> list[list[str]]:
        for row in value:
            if len(row) > MAX_HEADERS:
                raise ValueError(f"Each row must not exceed {MAX_HEADERS} cells")
        if len(json.dumps(value).encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("The parsed rows exceed the 2 MiB import limit")
        return value

    @field_validator("column_mapping")
    @classmethod
    def mapping_is_bounded(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > MAX_HEADERS:
            raise ValueError(f"The column mapping must not exceed {MAX_HEADERS} fields")
        for key, header in value.items():
            if not isinstance(header, str) or not header.strip():
                raise ValueError(f"Column mapping for '{key}' must be a non-empty header name")
        return value


class ImportMatchCandidate(BaseModel):
    id: UUID
    kind: str
    name: str
    method: MatchMethod
    score: float | None = None


class ImportIssue(BaseModel):
    row: int
    column: str
    message: str


class ImportRowPreview(BaseModel):
    row_number: int
    external_id: str | None = None
    name: str | None = None
    values: dict[str, str] = Field(default_factory=dict)
    issues: list[ImportIssue] = Field(default_factory=list)
    warnings: list[ImportIssue] = Field(default_factory=list)
    matches: list[ImportMatchCandidate] = Field(default_factory=list)
    suggested_decision: RowDecision = "create"


class ImportPreviewResponse(BaseModel):
    import_type: ImportType
    rows: list[ImportRowPreview] = Field(default_factory=list)
    blocked_count: int = 0
    resolved_reference_counts: dict[str, int] = Field(default_factory=dict)


class ImportRowDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=1)
    decision: RowDecision
    target_id: UUID | None = None


class ImportCommitRequest(ImportPreviewRequest):
    decisions: list[ImportRowDecision] = Field(default_factory=list, max_length=MAX_ROWS)


class ImportRowResult(BaseModel):
    row_number: int
    external_id: str | None = None
    status: RowStatus
    target_kind: str | None = None
    target_id: UUID | None = None
    message: str | None = None
    issues: list[ImportIssue] = Field(default_factory=list)


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_filename: str
    sheet_name: str
    import_type: str
    status: str
    counts: dict[str, int]
    rows: list[ImportRowResult] = Field(default_factory=list)
    imported_at: datetime
    undone_at: datetime | None = None
