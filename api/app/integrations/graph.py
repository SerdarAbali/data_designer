import json
import math
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from app.engine.operations import OperationFailure, validate_node_config

NodeType = Literal[
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
]


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: NodeType
    position: dict[str, float]
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("position")
    @classmethod
    def finite_coordinates(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != {"x", "y"} or any(
            not math.isfinite(coordinate) for coordinate in value.values()
        ):
            raise ValueError("Position must contain finite x and y coordinates")
        return value

    @field_validator("config")
    @classmethod
    def bounded_config(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(json.dumps(value, separators=(",", ":")).encode("utf-8")) > 8192:
            raise ValueError("Node configuration must not exceed 8 KiB")
        return value


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    id: UUID
    source_node_id: UUID = Field(alias="sourceNodeId")
    source_port_id: Annotated[str, Field(min_length=1, max_length=100)] = Field(
        alias="sourcePortId"
    )
    target_node_id: UUID = Field(alias="targetNodeId")
    target_port_id: Annotated[str, Field(min_length=1, max_length=100)] = Field(
        alias="targetPortId"
    )


class GraphDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    nodes: list[GraphNode] = Field(max_length=200)
    edges: list[GraphEdge] = Field(max_length=500)

    @field_validator("version", mode="before")
    @classmethod
    def version_is_integer_one(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Graph version must be the integer 1")
        return value

    @field_validator("nodes", "edges")
    @classmethod
    def unique_ids(cls, values):
        ids = [item.id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs must be unique within the graph")
        return values

    @field_validator("edges")
    @classmethod
    def no_self_edges(cls, values: list[GraphEdge]) -> list[GraphEdge]:
        if any(edge.source_node_id == edge.target_node_id for edge in values):
            raise ValueError("An edge cannot connect a node to itself")
        return values

    @model_validator(mode="after")
    def bounded_document(self) -> "GraphDocument":
        if len(self.model_dump_json().encode("utf-8")) > 262_144:
            raise ValueError("Graph document must not exceed 256 KiB")
        return self


class GraphIssue(BaseModel):
    code: str
    path: str
    message: str


class GraphValidationError(Exception):
    def __init__(self, issues: list[GraphIssue]) -> None:
        self.issues = issues
        super().__init__("Graph validation failed")


def field_port_id(port_id: str) -> UUID | None:
    if not port_id.startswith("field:"):
        return None
    try:
        return UUID(port_id.removeprefix("field:"))
    except ValueError:
        return None


def validate_graph(
    graph: GraphDocument,
    source_field_types: dict[UUID, str],
    target_field_types: dict[UUID, str],
) -> set[tuple[UUID, str]]:
    graph.bounded_document()
    nodes = {node.id: node for node in graph.nodes}
    issues: list[GraphIssue] = []
    node_types = [node.type for node in graph.nodes]
    for node_type in ("source", "target"):
        if node_types.count(node_type) > 1:
            issues.append(
                GraphIssue(
                    code="duplicate_endpoint_node",
                    path="nodes",
                    message=f"A graph may contain at most one {node_type} node",
                )
            )

    for index, node in enumerate(graph.nodes):
        if node.type in {"source", "target"} and node.config:
            issues.append(
                GraphIssue(
                    code="invalid_endpoint_config",
                    path=f"nodes[{index}].config",
                    message="Source and target nodes do not accept configuration",
                )
            )
        try:
            validate_node_config(
                {"type": node.type, "config": node.config},
                f"nodes[{index}]",
            )
        except OperationFailure as error:
            issues.append(
                GraphIssue(
                    code=error.code,
                    path=f"nodes[{index}].config",
                    message=error.message,
                )
            )

    references: set[tuple[UUID, str]] = set()
    assigned_targets: set[UUID] = set()
    adjacency: dict[UUID, set[UUID]] = {node_id: set() for node_id in nodes}

    for index, edge in enumerate(graph.edges):
        path = f"edges[{index}]"
        source = nodes.get(edge.source_node_id)
        target = nodes.get(edge.target_node_id)
        source_field_id: UUID | None = None
        target_field_id: UUID | None = None
        if source is None or target is None:
            issues.append(
                GraphIssue(
                    code="unknown_edge_node",
                    path=path,
                    message="Both edge endpoints must reference graph nodes",
                )
            )
            continue

        if source.type == "target":
            issues.append(
                GraphIssue(
                    code="invalid_port_direction",
                    path=f"{path}.sourceNodeId",
                    message="A target node cannot produce an edge",
                )
            )
        if target.type == "source":
            issues.append(
                GraphIssue(
                    code="invalid_port_direction",
                    path=f"{path}.targetNodeId",
                    message="A source node cannot receive an edge",
                )
            )

        if source.type == "source":
            field_id = field_port_id(edge.source_port_id)
            if field_id is None:
                issues.append(
                    GraphIssue(
                        code="invalid_source_port",
                        path=f"{path}.sourcePortId",
                        message="Source ports must use field:<uuid>",
                    )
                )
            elif field_id not in source_field_types:
                issues.append(
                    GraphIssue(
                        code="unknown_source_field",
                        path=f"{path}.sourcePortId",
                        message=(
                            "The source field is missing, archived, or outside the source object"
                        ),
                    )
                )
            else:
                source_field_id = field_id
                references.add((field_id, "source"))
        elif edge.source_port_id != "output":
            issues.append(
                GraphIssue(
                    code="unknown_source_port",
                    path=f"{path}.sourcePortId",
                    message="Transformation output ports use the output port",
                )
            )

        if target.type == "target":
            field_id = field_port_id(edge.target_port_id)
            if field_id is None:
                issues.append(
                    GraphIssue(
                        code="invalid_target_port",
                        path=f"{path}.targetPortId",
                        message="Target ports must use field:<uuid>",
                    )
                )
            elif field_id not in target_field_types:
                issues.append(
                    GraphIssue(
                        code="unknown_target_field",
                        path=f"{path}.targetPortId",
                        message=(
                            "The target field is missing, archived, or outside the target object"
                        ),
                    )
                )
            else:
                target_field_id = field_id
                if field_id in assigned_targets:
                    issues.append(
                        GraphIssue(
                            code="duplicate_target_mapping",
                            path=f"{path}.targetPortId",
                            message="A target field can be assigned by only one edge",
                        )
                    )
                assigned_targets.add(field_id)
                references.add((field_id, "target"))
        elif target.type == "constant":
            issues.append(
                GraphIssue(
                    code="invalid_port_direction",
                    path=f"{path}.targetNodeId",
                    message="A constant node does not accept input edges",
                )
            )
        elif edge.target_port_id != "input":
            issues.append(
                GraphIssue(
                    code="unknown_target_port",
                    path=f"{path}.targetPortId",
                    message="Transformation input ports use the input port",
                )
            )

        if (
            source.type == "source"
            and target.type == "target"
            and source_field_id is not None
            and target_field_id is not None
            and source_field_types[source_field_id].strip().casefold()
            != target_field_types[target_field_id].strip().casefold()
        ):
            issues.append(
                GraphIssue(
                    code="incompatible_field_types",
                    path=path,
                    message=(
                        "Direct field mappings require identical data_type values; "
                        "connect a transformation node for conversion"
                    ),
                )
            )

        adjacency[edge.source_node_id].add(edge.target_node_id)

    visiting: set[UUID] = set()
    visited: set[UUID] = set()

    def visit(node_id: UUID) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(child) for child in adjacency[node_id]):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(visit(node_id) for node_id in adjacency if node_id not in visited):
        issues.append(
            GraphIssue(code="graph_cycle", path="edges", message="Graph edges must be acyclic")
        )

    if issues:
        raise GraphValidationError(issues)
    return references
