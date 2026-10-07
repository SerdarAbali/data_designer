from __future__ import annotations

import heapq
import json
import math
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.engine.operations import (
    MISSING,
    OperationFailure,
    apply_target_field,
    execute_operation,
    is_finite_number,
    validate_json_value,
    validate_node_config,
)
from app.engine.types import (
    EngineIssue,
    EngineLimits,
    FieldSpec,
    JsonValue,
    RowError,
    RowResult,
    SimulationResult,
    TraceEntry,
)

NODE_TYPES = {
    "source",
    "target",
    "constant",
    "fx",
    "concat",
    "ifelse",
    "map",
    "coalesce",
    "lookup",
    "filter",
    "validate",
}
REDACTED = "[redacted]"


class EngineError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class EngineValidationError(EngineError):
    def __init__(self, issues: list[EngineIssue]) -> None:
        self.issues = issues
        super().__init__("invalid_graph", "Graph or engine input validation failed")


class EngineLimitError(EngineError):
    pass


@dataclass(frozen=True, slots=True)
class _Edge:
    id: str
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str


def run_graph(
    graph: Mapping[str, Any],
    source_fields: Sequence[FieldSpec],
    target_fields: Sequence[FieldSpec],
    rows: Sequence[Mapping[str, Any]],
    limits: EngineLimits | None = None,
) -> SimulationResult:
    """Run a version-1 graph against bounded sample rows without side effects."""
    limits = limits or EngineLimits()
    _validate_limits(limits)
    if len(rows) > limits.max_rows:
        raise EngineLimitError("row_limit", "Input exceeds the maximum row count")
    if len(source_fields) + len(target_fields) > limits.max_fields:
        raise EngineLimitError("field_limit", "Catalog fields exceed the maximum field count")
    source_by_id = _field_index(source_fields, "source", limits.max_fields)
    target_by_id = _field_index(target_fields, "target", limits.max_fields)
    nodes, order, incoming, outgoing = _validate_graph(
        graph, source_by_id, target_by_id, limits
    )
    normalized_rows = _validate_input_rows(rows, source_by_id, limits)

    row_results: list[RowResult] = []
    trace_bytes = 0
    output_value_bytes = 0
    any_trace_truncated = False
    deadline = time.monotonic() + limits.max_execution_seconds
    for row_index, row in enumerate(normalized_rows):
        row_result, trace_bytes, output_value_bytes = _run_row(
            row,
            row_index,
            nodes,
            order,
            incoming,
            outgoing,
            source_by_id,
            target_by_id,
            trace_bytes,
            output_value_bytes,
            limits,
            deadline,
        )
        _check_deadline(deadline)
        row_results.append(row_result)
        any_trace_truncated = any_trace_truncated or row_result.trace_truncated

    outcomes = [row.outcome for row in row_results]
    summary = {
        "total": len(row_results),
        "ok": outcomes.count("ok"),
        "skipped": outcomes.count("skipped"),
        "failed": outcomes.count("failed"),
    }
    result = SimulationResult(
        version=1,
        summary=summary,
        rows=tuple(row_results),
        trace_truncated=any_trace_truncated,
    )
    try:
        serialized = json.dumps(
            result.to_dict(), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise EngineError("invalid_output", "Engine output is not valid JSON") from error
    if len(serialized) > limits.max_output_bytes:
        raise EngineLimitError("output_limit", "Simulation output exceeds the configured limit")
    return result


def _validate_limits(limits: EngineLimits) -> None:
    positive_limits = (
        "max_rows",
        "max_nodes",
        "max_edges",
        "max_fields",
        "max_graph_bytes",
        "max_input_bytes",
        "max_value_bytes",
        "max_output_bytes",
    )
    if (
        any(
            isinstance(getattr(limits, name), bool)
            or not isinstance(getattr(limits, name), int)
            or getattr(limits, name) < 1
            for name in positive_limits
        )
        or isinstance(limits.max_trace_bytes, bool)
        or not isinstance(limits.max_trace_bytes, int)
        or limits.max_trace_bytes < 0
        or isinstance(limits.max_execution_seconds, bool)
        or not isinstance(limits.max_execution_seconds, int | float)
        or not math.isfinite(limits.max_execution_seconds)
        or limits.max_execution_seconds <= 0
        or not isinstance(limits.include_trace_values, bool)
    ):
        raise ValueError("Engine limits must be positive, except max_trace_bytes may be zero")


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise EngineLimitError("execution_time_limit", "Simulation exceeded its time budget")


def _field_index(
    fields: Sequence[FieldSpec], direction: str, max_fields: int
) -> dict[str, FieldSpec]:
    if len(fields) > max_fields:
        raise EngineLimitError("field_limit", f"{direction} fields exceed the maximum field count")
    indexed: dict[str, FieldSpec] = {}
    issues: list[EngineIssue] = []
    for index, field_spec in enumerate(fields):
        try:
            field_id = str(UUID(field_spec.id))
        except (ValueError, TypeError, AttributeError):
            issues.append(
                EngineIssue(
                    "invalid_field_id",
                    f"{direction}Fields[{index}].id",
                    "Field IDs must be UUIDs",
                )
            )
            continue
        if field_id in indexed:
            issues.append(
                EngineIssue(
                    "duplicate_field_id",
                    f"{direction}Fields[{index}].id",
                    "Field IDs must be unique",
                )
            )
        else:
            if not isinstance(field_spec.data_type, str) or not field_spec.data_type.strip():
                issues.append(
                    EngineIssue(
                        "invalid_data_type",
                        f"{direction}Fields[{index}].data_type",
                        "data_type must be a non-empty string",
                    )
                )
            if not isinstance(field_spec.required, bool) or not isinstance(
                field_spec.nullable, bool
            ):
                issues.append(
                    EngineIssue(
                        "invalid_field_constraints",
                        f"{direction}Fields[{index}]",
                        "required and nullable must be boolean",
                    )
                )
            if field_spec.has_default:
                try:
                    validate_json_value(field_spec.default_value, max_bytes=65_536)
                except OperationFailure as error:
                    issues.append(
                        EngineIssue(
                            error.code,
                            f"{direction}Fields[{index}].default_value",
                            error.message,
                        )
                    )
            indexed[field_id] = field_spec
    if issues:
        raise EngineValidationError(issues)
    return indexed


def _validate_graph(
    graph: Mapping[str, Any],
    source_fields: dict[str, FieldSpec],
    target_fields: dict[str, FieldSpec],
    limits: EngineLimits,
):
    issues: list[EngineIssue] = []
    if not isinstance(graph, Mapping):
        raise EngineValidationError(
            [EngineIssue("invalid_graph", "graph", "Graph must be an object")]
        )
    required_graph_keys = {"version", "nodes", "edges"}
    if set(graph) - required_graph_keys or required_graph_keys - set(graph):
        issues.append(
            EngineIssue(
                "invalid_graph_shape",
                "graph",
                "Graph must contain exactly version, nodes, and edges",
            )
        )
    version = graph.get("version")
    if type(version) is not int or version != 1:
        issues.append(
            EngineIssue("unsupported_graph_version", "version", "Only graph version 1 is supported")
        )
    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    if not isinstance(raw_nodes, list):
        issues.append(EngineIssue("invalid_nodes", "nodes", "Nodes must be an array"))
        raw_nodes = []
    if not isinstance(raw_edges, list):
        issues.append(EngineIssue("invalid_edges", "edges", "Edges must be an array"))
        raw_edges = []
    if len(raw_nodes) > limits.max_nodes:
        raise EngineLimitError("node_limit", "Graph exceeds the maximum node count")
    if len(raw_edges) > limits.max_edges:
        raise EngineLimitError("edge_limit", "Graph exceeds the maximum edge count")
    try:
        validate_json_value(graph, max_bytes=limits.max_graph_bytes)
    except OperationFailure as error:
        if error.code == "value_size_limit":
            raise EngineLimitError(
                "graph_size_limit", "Graph exceeds the configured size limit"
            ) from error
        raise EngineValidationError(
            [EngineIssue("invalid_graph", "graph", error.message)]
        ) from error

    nodes: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    for index, raw_node in enumerate(raw_nodes):
        path = f"nodes[{index}]"
        if not isinstance(raw_node, Mapping):
            issues.append(EngineIssue("invalid_node", path, "Node must be an object"))
            continue
        if set(raw_node) - {"id", "type", "position", "config"}:
            issues.append(
                EngineIssue(
                    "invalid_node_shape",
                    path,
                    "Node contains unsupported properties",
                )
            )
            continue
        node_id = _canonical_id(raw_node.get("id"), f"{path}.id", issues)
        node_type = raw_node.get("type")
        config = raw_node.get("config", {})
        if not isinstance(node_type, str) or node_type not in NODE_TYPES:
            issues.append(
                EngineIssue("unsupported_node_type", f"{path}.type", "Node type is not supported")
            )
            continue
        if node_id is None:
            continue
        if node_id in nodes:
            issues.append(EngineIssue("duplicate_node_id", f"{path}.id", "Node IDs must be unique"))
            continue
        if not isinstance(config, Mapping):
            issues.append(
                EngineIssue(
                    "invalid_node_config", f"{path}.config", "Node config must be an object"
                )
            )
            continue
        position = raw_node.get("position")
        if (
            not isinstance(position, Mapping)
            or set(position) != {"x", "y"}
            or any(
                isinstance(coordinate, bool) or not is_finite_number(coordinate)
                for coordinate in position.values()
            )
        ):
            issues.append(
                EngineIssue(
                    "invalid_position",
                    f"{path}.position",
                    "Node position must contain finite numeric x and y coordinates",
                )
            )
            continue
        normalized = {
            "id": node_id,
            "type": node_type,
            "position": raw_node.get("position", {}),
            "config": dict(config),
        }
        try:
            validate_json_value(config, max_bytes=8_192)
        except OperationFailure as error:
            issues.append(EngineIssue(error.code, f"{path}.config", error.message))
            continue
        try:
            validate_node_config(normalized, path)
        except OperationFailure as error:
            issues.append(EngineIssue(error.code, f"{path}.config", error.message))
            continue
        nodes[node_id] = normalized
        node_order.append(node_id)

    endpoint_nodes: dict[str, list[str]] = {"source": [], "target": []}
    for node_id, node in nodes.items():
        if node["type"] in endpoint_nodes:
            endpoint_nodes[node["type"]].append(node_id)
    for node_type in ("source", "target"):
        if len(endpoint_nodes[node_type]) != 1:
            issues.append(
                EngineIssue(
                    "invalid_endpoint_count",
                    "nodes",
                    f"Executable graphs require exactly one {node_type} node",
                )
            )

    edges: list[_Edge] = []
    edge_ids: set[str] = set()
    assigned_target_fields: set[str] = set()
    for index, raw_edge in enumerate(raw_edges):
        path = f"edges[{index}]"
        if not isinstance(raw_edge, Mapping):
            issues.append(EngineIssue("invalid_edge", path, "Edge must be an object"))
            continue
        if set(raw_edge) - {
            "id",
            "sourceNodeId",
            "sourcePortId",
            "targetNodeId",
            "targetPortId",
        }:
            issues.append(
                EngineIssue(
                    "invalid_edge_shape",
                    path,
                    "Edge contains unsupported properties",
                )
            )
            continue
        edge_id = _canonical_id(raw_edge.get("id"), f"{path}.id", issues)
        source_node_id = _canonical_id(raw_edge.get("sourceNodeId"), f"{path}.sourceNodeId", issues)
        target_node_id = _canonical_id(raw_edge.get("targetNodeId"), f"{path}.targetNodeId", issues)
        source_port_id = raw_edge.get("sourcePortId")
        target_port_id = raw_edge.get("targetPortId")
        if not isinstance(source_port_id, str) or not isinstance(target_port_id, str):
            issues.append(EngineIssue("invalid_port", path, "Edge ports must be strings"))
            continue
        if (
            not source_port_id
            or len(source_port_id) > 100
            or not target_port_id
            or len(target_port_id) > 100
        ):
            issues.append(
                EngineIssue("invalid_port", path, "Edge ports must be 1-100 characters")
            )
            continue
        if (
            edge_id is None
            or source_node_id is None
            or target_node_id is None
            or source_node_id not in nodes
            or target_node_id not in nodes
        ):
            issues.append(
                EngineIssue(
                    "unknown_edge_node",
                    path,
                    "Edge IDs must refer to nodes in the graph",
                )
            )
            continue
        if edge_id in edge_ids:
            issues.append(EngineIssue("duplicate_edge_id", f"{path}.id", "Edge IDs must be unique"))
            continue
        edge_ids.add(edge_id)
        source_type = nodes[source_node_id]["type"]
        target_type = nodes[target_node_id]["type"]
        if source_type == "target" or target_type == "source":
            issues.append(EngineIssue("invalid_port_direction", path, "Edge direction is invalid"))
            continue
        if source_type == "source":
            source_field_id = _field_port(
                source_port_id, f"{path}.sourcePortId", source_fields, issues
            )
            if source_field_id is not None:
                source_port_id = f"field:{source_field_id}"
        elif source_type == "constant":
            source_field_id = None
            if source_port_id != "output":
                issues.append(
                    EngineIssue(
                        "invalid_source_port",
                        f"{path}.sourcePortId",
                        "Constant nodes use the output port",
                    )
                )
        else:
            source_field_id = None
            if source_port_id != "output":
                issues.append(
                    EngineIssue(
                        "invalid_source_port",
                        f"{path}.sourcePortId",
                        "Transformation nodes use the output port",
                    )
                )

        target_field_id: str | None = None
        if target_type == "target":
            target_field_id = _field_port(
                target_port_id, f"{path}.targetPortId", target_fields, issues
            )
            if target_field_id is not None:
                target_port_id = f"field:{target_field_id}"
                if target_field_id in assigned_target_fields:
                    issues.append(
                        EngineIssue(
                            "duplicate_target_mapping",
                            f"{path}.targetPortId",
                            "Target fields can be assigned by only one edge",
                        )
                    )
                assigned_target_fields.add(target_field_id)
        elif target_type == "constant":
            issues.append(
                EngineIssue(
                    "invalid_port_direction",
                    f"{path}.targetNodeId",
                    "Constant nodes do not accept input edges",
                )
            )
        elif target_port_id != "input":
            issues.append(
                EngineIssue(
                    "invalid_target_port",
                    f"{path}.targetPortId",
                    "Transformation nodes use the input port",
                )
            )

        if (
            source_type == "source"
            and target_type == "target"
            and source_field_id is not None
            and target_field_id is not None
            and source_fields[source_field_id].data_type.strip().casefold()
            != target_fields[target_field_id].data_type.strip().casefold()
        ):
            issues.append(
                EngineIssue(
                    "incompatible_field_types",
                    path,
                    "Direct field mappings require identical data_type values",
                )
            )
        edges.append(
            _Edge(
                edge_id,
                source_node_id,
                source_port_id,
                target_node_id,
                target_port_id,
            )
        )

    incoming: dict[str, list[_Edge]] = defaultdict(list)
    outgoing: dict[str, list[_Edge]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in nodes}
    for edge in edges:
        incoming[edge.target_node_id].append(edge)
        outgoing[edge.source_node_id].append(edge)
        indegree[edge.target_node_id] += 1

    order_index = {node_id: index for index, node_id in enumerate(node_order)}
    ready = [(order_index[node_id], node_id) for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    topological_order: list[str] = []
    while ready:
        _, node_id = heapq.heappop(ready)
        topological_order.append(node_id)
        for edge in outgoing[node_id]:
            indegree[edge.target_node_id] -= 1
            if indegree[edge.target_node_id] == 0:
                heapq.heappush(ready, (order_index[edge.target_node_id], edge.target_node_id))
    if len(topological_order) != len(nodes):
        issues.append(EngineIssue("graph_cycle", "edges", "Graph edges must be acyclic"))
    if issues:
        raise EngineValidationError(issues)

    _validate_static_arity(nodes, incoming, node_order)
    return nodes, topological_order, incoming, outgoing


def _canonical_id(value: object, path: str, issues: list[EngineIssue]) -> str | None:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        issues.append(EngineIssue("invalid_uuid", path, "ID must be a UUID"))
        return None


def _field_port(
    port_id: str,
    path: str,
    fields: dict[str, FieldSpec],
    issues: list[EngineIssue],
) -> str | None:
    if not port_id.startswith("field:"):
        issues.append(EngineIssue("invalid_field_port", path, "Field ports use field:<uuid>"))
        return None
    field_id = _canonical_id(port_id.removeprefix("field:"), path, issues)
    if field_id is not None and field_id not in fields:
        issues.append(
            EngineIssue("unknown_field", path, "Field is not part of the active endpoint object")
        )
        return None
    return field_id


def _validate_static_arity(nodes, incoming, node_order) -> None:
    issues: list[EngineIssue] = []
    for node_id in node_order:
        node_type = nodes[node_id]["type"]
        count = len(incoming[node_id])
        if node_type == "target" and count == 0:
            issues.append(
                EngineIssue(
                    "unmapped_target",
                    f"nodes.{node_id}",
                    "Target node requires a field mapping",
                )
            )
        elif node_type == "constant" and count:
            issues.append(
                EngineIssue(
                    "invalid_input_count",
                    f"nodes.{node_id}",
                    "Constant nodes do not accept inputs",
                )
            )
        elif node_type in {"fx", "map", "lookup", "filter", "validate", "ifelse"} and count not in (
            1 if node_type != "ifelse" else 3,
        ):
            expected = 3 if node_type == "ifelse" else 1
            issues.append(
                EngineIssue(
                    "invalid_input_count",
                    f"nodes.{node_id}",
                    f"{node_type} requires exactly {expected} input connection(s)",
                )
            )
        elif node_type == "coalesce" and count == 0:
            issues.append(
                EngineIssue(
                    "invalid_input_count",
                    f"nodes.{node_id}",
                    "coalesce requires at least one input connection",
                )
            )
        elif node_type == "concat" and count == 0:
            issues.append(
                EngineIssue(
                    "invalid_input_count",
                    f"nodes.{node_id}",
                    "concat requires at least one input connection",
                )
            )
    if issues:
        raise EngineValidationError(issues)


def _validate_input_rows(
    rows: Sequence[Mapping[str, Any]],
    source_fields: dict[str, FieldSpec],
    limits: EngineLimits,
) -> list[dict[str, Any]]:
    allowed_ids = set(source_fields)
    total_size = 0
    normalized_rows: list[dict[str, Any]] = []
    row_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EngineValidationError(
                [EngineIssue("invalid_row", f"rows[{index}]", "Row must be an object")]
            )
        values = row.get("values")
        if not isinstance(values, Mapping):
            raise EngineValidationError(
                [
                    EngineIssue(
                        "invalid_row",
                        f"rows[{index}].values",
                        "Row values must be an object",
                    )
                ]
            )
        raw_row_id = row.get("rowId", row.get("row_id", str(index)))
        if not isinstance(raw_row_id, str) or not raw_row_id or len(raw_row_id) > 100:
            raise EngineValidationError(
                [
                    EngineIssue(
                        "invalid_row_id",
                        f"rows[{index}].rowId",
                        "rowId must be a non-empty string of at most 100 characters",
                    )
                ]
            )
        if raw_row_id in row_ids:
            raise EngineValidationError(
                [
                    EngineIssue(
                        "duplicate_row_id",
                        f"rows[{index}].rowId",
                        "rowId values must be unique within a simulation",
                    )
                ]
            )
        row_ids.add(raw_row_id)
        try:
            normalized_row = {"rowId": raw_row_id, "values": values}
            validate_json_value(normalized_row, max_bytes=limits.max_input_bytes)
            row_size = len(
                json.dumps(normalized_row, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
        except OperationFailure as error:
            if error.code == "value_size_limit":
                raise EngineLimitError(
                    "input_size_limit", f"Row {index} exceeds the input size limit"
                ) from error
            raise EngineValidationError(
                [
                    EngineIssue(
                        error.code,
                        f"rows[{index}].values",
                        error.message,
                    )
                ]
            ) from error
        except (TypeError, ValueError, RecursionError) as error:
            raise EngineValidationError(
                [
                    EngineIssue(
                        "invalid_row_value",
                        f"rows[{index}].values",
                        "Row values must contain finite JSON values",
                    )
                ]
            ) from error
        if row_size > limits.max_input_bytes:
            raise EngineLimitError("input_size_limit", f"Row {index} exceeds the input size limit")
        total_size += row_size
        if total_size > limits.max_input_bytes:
            raise EngineLimitError(
                "input_size_limit", "Input rows exceed the configured serialized size limit"
            )
        normalized_ids = set()
        normalized_values: dict[str, Any] = {}
        for raw_id in values:
            try:
                field_id = str(UUID(str(raw_id)))
            except (ValueError, TypeError, AttributeError):
                raise EngineValidationError(
                    [
                        EngineIssue(
                            "invalid_sample_field_id",
                            f"rows[{index}].values",
                            "Row keys must be source field UUIDs",
                        )
                    ]
                ) from None
            if field_id in normalized_ids:
                raise EngineValidationError(
                    [
                        EngineIssue(
                            "duplicate_sample_field",
                            f"rows[{index}].values",
                            "Row cannot contain duplicate field UUIDs",
                        )
                    ]
                )
            normalized_ids.add(field_id)
            if field_id not in allowed_ids:
                raise EngineValidationError(
                    [
                        EngineIssue(
                            "unknown_source_field",
                            f"rows[{index}].values",
                            "Row values may only reference source fields",
                        )
                    ]
                )
            try:
                validate_json_value(values[raw_id], max_bytes=limits.max_value_bytes)
            except OperationFailure as error:
                raise EngineValidationError(
                    [
                        EngineIssue(
                            error.code,
                            f"rows[{index}].values.{raw_id}",
                            error.message,
                        )
                    ]
                ) from error
            normalized_values[field_id] = values[raw_id]
        normalized_rows.append(
            {
                "rowId": raw_row_id,
                "values": normalized_values,
            }
        )
    return normalized_rows


def _run_row(
    row: Mapping[str, Any],
    row_index: int,
    nodes: dict[str, dict[str, Any]],
    order: list[str],
    incoming: dict[str, list[_Edge]],
    outgoing: dict[str, list[_Edge]],
    source_fields: dict[str, FieldSpec],
    target_fields: dict[str, FieldSpec],
    trace_bytes: int,
    output_value_bytes: int,
    limits: EngineLimits,
    deadline: float,
) -> tuple[RowResult, int, int]:
    row_id = str(row.get("rowId", row.get("row_id", row_index)))
    input_values = row["values"]
    results: dict[tuple[str, str], object] = {}
    trace: list[TraceEntry] = []
    errors: list[RowError] = []
    target_values: dict[str, JsonValue] = {}
    outcome = "ok"
    trace_truncated = False

    for node_id in order:
        _check_deadline(deadline)
        node = nodes[node_id]
        node_type = node["type"]
        node_edges = incoming[node_id]
        inputs: list[object] = []
        trace_inputs: dict[str, JsonValue | str] = {}
        if node_type == "source":
            emitted_fields = list(
                dict.fromkeys(
                    edge.source_port_id.removeprefix("field:")
                    for edge in outgoing[node_id]
                    if edge.source_port_id.startswith("field:")
                )
            )
            for field_id in emitted_fields:
                value = input_values.get(field_id, MISSING)
                if value is not MISSING:
                    validate_json_value(value, max_bytes=limits.max_value_bytes)
                results[(node_id, f"field:{field_id}")] = value
            trace_outputs = {
                f"field:{field_id}": _trace_value(
                    input_values.get(field_id, MISSING), limits.include_trace_values
                )
                for field_id in emitted_fields
            }
        elif node_type == "target":
            target_trace: dict[str, JsonValue | str] = {}
            mapped_fields: set[str] = set()
            for edge in node_edges:
                field_id = edge.target_port_id.removeprefix("field:")
                mapped_fields.add(field_id)
                value = results[(edge.source_node_id, edge.source_port_id)]
                target_trace[edge.target_port_id] = _trace_value(value, limits.include_trace_values)
                try:
                    output_value = apply_target_field(value, target_fields[field_id])
                    if output_value is not MISSING:
                        validate_json_value(output_value, max_bytes=limits.max_value_bytes)
                        target_values[field_id] = output_value
                        output_value_bytes = _account_output_value(
                            output_value_bytes, output_value, limits
                        )
                except OperationFailure as error:
                    errors.append(
                        RowError(
                            error.code,
                            row_id,
                            row_index,
                            node_id,
                            error.message,
                        )
                    )
                    outcome = "failed"
                    break
            if outcome != "failed":
                for field_id, field_spec in target_fields.items():
                    if field_id in mapped_fields:
                        continue
                    try:
                        output_value = apply_target_field(MISSING, field_spec)
                        if output_value is not MISSING:
                            validate_json_value(output_value, max_bytes=limits.max_value_bytes)
                            target_values[field_id] = output_value
                            output_value_bytes = _account_output_value(
                                output_value_bytes, output_value, limits
                            )
                    except OperationFailure as error:
                        errors.append(
                            RowError(
                                error.code,
                                row_id,
                                row_index,
                                node_id,
                                error.message,
                            )
                        )
                        outcome = "failed"
                        break
            trace_inputs = target_trace
            trace_outputs = {
                f"field:{field_id}": _trace_value(value, limits.include_trace_values)
                for field_id, value in target_values.items()
            }
        elif node_type == "constant":
            value = node["config"]["value"]
            try:
                validate_json_value(value, max_bytes=limits.max_value_bytes)
            except OperationFailure as error:
                errors.append(RowError(error.code, row_id, row_index, node_id, error.message))
                outcome = "failed"
                break
            results[(node_id, "output")] = value
            trace_outputs = {"output": _trace_value(value, limits.include_trace_values)}
        else:
            for edge in node_edges:
                value = results[(edge.source_node_id, edge.source_port_id)]
                inputs.append(value)
                port_name = edge.target_port_id
                occurrence = sum(
                    key == port_name or key.startswith(f"{port_name}#") for key in trace_inputs
                )
                trace_key = port_name if occurrence == 0 else f"{port_name}#{occurrence + 1}"
                trace_inputs[trace_key] = _trace_value(value, limits.include_trace_values)
            try:
                value = execute_operation(node_type, node["config"], inputs)
                if node_type == "filter" and value is False:
                    results[(node_id, "output")] = value
                    trace_outputs = {"output": _trace_value(value, limits.include_trace_values)}
                    trace_outcome = "filtered"
                else:
                    validate_json_value(
                        value if value is not MISSING else None,
                        max_bytes=limits.max_value_bytes,
                    )
                    results[(node_id, "output")] = value
                    trace_outputs = {"output": _trace_value(value, limits.include_trace_values)}
                    trace_outcome = "ok"
            except OperationFailure as error:
                policy = node["config"].get("errorPolicy", "fail")
                if policy == "default":
                    value = node["config"]["defaultValue"]
                    validate_json_value(value, max_bytes=limits.max_value_bytes)
                    results[(node_id, "output")] = value
                    trace_outputs = {"output": _trace_value(value, limits.include_trace_values)}
                    trace_outcome = (
                        "filtered" if node_type == "filter" and value is False else "recovered"
                    )
                    errors.append(
                        RowError(
                            error.code,
                            row_id,
                            row_index,
                            node_id,
                            error.message,
                            recovered=True,
                        )
                    )
                    trace_error_code = error.code
                else:
                    outcome = "skipped" if policy == "skip" else "failed"
                    errors.append(RowError(error.code, row_id, row_index, node_id, error.message))
                    trace_outputs = {}
                    trace_outcome = outcome
                    trace_error_code = error.code
                    entry = TraceEntry(
                        node_id,
                        node_type,
                        trace_inputs,
                        trace_outputs,
                        trace_outcome,
                        trace_error_code,
                    )
                    trace_bytes, was_truncated = _append_trace(trace, entry, trace_bytes, limits)
                    trace_truncated = trace_truncated or was_truncated
                    break
            else:
                trace_error_code = None

            entry = TraceEntry(
                node_id,
                node_type,
                trace_inputs,
                trace_outputs,
                trace_outcome,
                trace_error_code,
            )
            trace_bytes, was_truncated = _append_trace(trace, entry, trace_bytes, limits)
            trace_truncated = trace_truncated or was_truncated
            if trace_outcome == "filtered":
                outcome = "skipped"
                break
            continue

        trace_outcome = "failed" if outcome == "failed" else "ok"
        entry = TraceEntry(
            node_id,
            node_type,
            trace_inputs,
            trace_outputs,
            trace_outcome,
            errors[-1].code if outcome == "failed" and errors else None,
        )
        trace_bytes, was_truncated = _append_trace(trace, entry, trace_bytes, limits)
        trace_truncated = trace_truncated or was_truncated
        if outcome == "failed":
            break

    result = RowResult(
        row_id=row_id,
        row_index=row_index,
        outcome=outcome,
        target_values=target_values,
        errors=tuple(errors),
        trace=tuple(trace),
        trace_truncated=trace_truncated,
    )
    return result, trace_bytes, output_value_bytes


def _account_output_value(current_bytes: int, value: JsonValue, limits: EngineLimits) -> int:
    value_bytes = len(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    total = current_bytes + value_bytes
    if total > limits.max_output_bytes:
        raise EngineLimitError("output_limit", "Simulation output exceeds the configured limit")
    return total


def _trace_value(value: object, include_values: bool) -> JsonValue | str:
    if not include_values or value is MISSING:
        return REDACTED
    return value


def _append_trace(
    trace: list[TraceEntry],
    entry: TraceEntry,
    current_bytes: int,
    limits: EngineLimits,
) -> tuple[int, bool]:
    entry_size = len(
        json.dumps(
            entry.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if current_bytes + entry_size > limits.max_trace_bytes:
        return current_bytes, True
    trace.append(entry)
    return current_bytes + entry_size, False
