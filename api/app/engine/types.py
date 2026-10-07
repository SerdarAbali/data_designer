from __future__ import annotations

from dataclasses import dataclass, field

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class FieldSpec:
    id: str
    data_type: str
    required: bool = False
    nullable: bool = True
    has_default: bool = False
    default_value: JsonValue = None


@dataclass(frozen=True, slots=True)
class EngineLimits:
    max_rows: int = 100
    max_nodes: int = 200
    max_edges: int = 500
    max_fields: int = 1_000
    max_graph_bytes: int = 262_144
    max_input_bytes: int = 65_536
    max_value_bytes: int = 65_536
    max_trace_bytes: int = 262_144
    max_output_bytes: int = 1_048_576
    max_execution_seconds: float = 2.0
    include_trace_values: bool = False


@dataclass(frozen=True, slots=True)
class EngineIssue:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True, slots=True)
class RowError:
    code: str
    row_id: str
    row_index: int
    node_id: str | None
    message: str
    recovered: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "rowId": self.row_id,
            "rowIndex": self.row_index,
            "nodeId": self.node_id,
            "message": self.message,
            "recovered": self.recovered,
        }


@dataclass(frozen=True, slots=True)
class TraceEntry:
    node_id: str
    node_type: str
    inputs: dict[str, JsonValue | str]
    outputs: dict[str, JsonValue | str]
    outcome: str
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "nodeId": self.node_id,
            "nodeType": self.node_type,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "outcome": self.outcome,
        }
        if self.error_code is not None:
            result["errorCode"] = self.error_code
        return result


@dataclass(frozen=True, slots=True)
class RowResult:
    row_id: str
    row_index: int
    outcome: str
    target_values: dict[str, JsonValue] = field(default_factory=dict)
    errors: tuple[RowError, ...] = ()
    trace: tuple[TraceEntry, ...] = ()
    trace_truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "rowId": self.row_id,
            "rowIndex": self.row_index,
            "outcome": self.outcome,
            "targetValues": self.target_values,
            "errors": [error.to_dict() for error in self.errors],
            "trace": [entry.to_dict() for entry in self.trace],
            "traceTruncated": self.trace_truncated,
        }


@dataclass(frozen=True, slots=True)
class SimulationResult:
    version: int
    summary: dict[str, int]
    rows: tuple[RowResult, ...]
    trace_truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "summary": self.summary,
            "rows": [row.to_dict() for row in self.rows],
            "traceTruncated": self.trace_truncated,
        }
