import ast
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.engine import (
    EngineError,
    EngineLimits,
    EngineValidationError,
    FieldSpec,
    run_graph,
)

SOURCE_ID = "11111111-1111-4111-8111-111111111111"
TARGET_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_NODE = "00000000-0000-4000-8000-000000000001"
TARGET_NODE = "00000000-0000-4000-8000-000000000002"
TRANSFORM_NODE = "00000000-0000-4000-8000-000000000003"


def node(node_type: str, node_id: str | None = None, config=None) -> dict:
    return {
        "id": node_id or str(uuid4()),
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def edge(
    source_node: str,
    source_port: str,
    target_node: str,
    target_port: str,
) -> dict:
    return {
        "id": str(uuid4()),
        "sourceNodeId": source_node,
        "sourcePortId": source_port,
        "targetNodeId": target_node,
        "targetPortId": target_port,
    }


def graph_with_one_transform(
    config: dict,
    *,
    source_type: str = "string",
    target_type: str = "string",
    target_required: bool = False,
) -> tuple[dict, list[FieldSpec], list[FieldSpec]]:
    source_field = FieldSpec(SOURCE_ID, source_type)
    target_field = FieldSpec(TARGET_ID, target_type, required=target_required)
    graph = {
        "version": 1,
        "nodes": [
            node("source", SOURCE_NODE),
            node("fx" if "function" in config else "concat", TRANSFORM_NODE, config),
            node("target", TARGET_NODE),
        ],
        "edges": [
            edge(SOURCE_NODE, f"field:{SOURCE_ID}", TRANSFORM_NODE, "input"),
            edge(TRANSFORM_NODE, "output", TARGET_NODE, f"field:{TARGET_ID}"),
        ],
    }
    return graph, [source_field], [target_field]


def test_basic_mapping_matches_golden_trace_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "engine" / "basic_mapping.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    result = run_graph(
        fixture["graph"],
        [FieldSpec(**fixture["sourceField"])],
        [FieldSpec(**fixture["targetField"])],
        fixture["rows"],
    )
    assert result.to_dict() == fixture["expected"]


@pytest.mark.parametrize(
    ("function", "value", "expected"),
    [
        ("trim", "  text \n", "text"),
        ("title", "first LAST", "First Last"),
        ("lower", "AbC", "abc"),
        ("upper", "AbC", "ABC"),
        ("toString", 42, "42"),
        ("toString", True, "true"),
        ("toString", {"key": "value"}, '{"key":"value"}'),
        ("toInt", " 42 ", 42),
        ("toNumber", "3.25", 3.25),
        ("toBoolean", "false", False),
        ("parseDate", "31/12/2025", "2025-12-31"),
        ("formatDate", "2025-12-31", "31/12/2025"),
    ],
)
def test_text_functions(function: str, value: object, expected: object) -> None:
    config = {"function": function}
    if function == "parseDate":
        config["inputFormat"] = "%d/%m/%Y"
    if function == "formatDate":
        config["outputFormat"] = "%d/%m/%Y"
    target_type = {
        "toInt": "integer",
        "toNumber": "number",
        "toBoolean": "boolean",
        "parseDate": "date",
        "formatDate": "string",
    }.get(function, "string")
    graph, source, target = graph_with_one_transform(config, target_type=target_type)
    result = run_graph(graph, source, target, [{"rowId": "1", "values": {SOURCE_ID: value}}])
    assert result.rows[0].target_values[TARGET_ID] == expected


def test_target_validation_coerces_obvious_scalar_values() -> None:
    target_id = str(uuid4())
    constant_id = str(uuid4())
    cases = [
        ("integer", "3", 3),
        ("number", "3.5", 3.5),
        ("boolean", "true", True),
        ("string", 3, "3"),
    ]
    for target_type, raw_value, expected in cases:
        graph = {
            "version": 1,
            "nodes": [
                node("source", SOURCE_NODE),
                node("constant", constant_id, {"value": raw_value}),
                node("target", TARGET_NODE),
            ],
            "edges": [edge(constant_id, "output", TARGET_NODE, f"field:{target_id}")],
        }
        result = run_graph(
            graph,
            [],
            [FieldSpec(target_id, target_type)],
            [{"values": {}}],
        )
        assert result.rows[0].target_values[target_id] == expected


@pytest.mark.parametrize(
    ("function", "value"),
    [
        ("toInt", "3.2"),
        ("toNumber", "NaN"),
        ("toBoolean", "yes"),
    ],
)
def test_scalar_converters_reject_ambiguous_values(function: str, value: object) -> None:
    graph, source, target = graph_with_one_transform({"function": function})
    result = run_graph(graph, source, target, [{"values": {SOURCE_ID: value}}])
    assert result.rows[0].outcome == "failed"
    assert result.rows[0].errors[0].code in {
        "invalid_number",
        "invalid_boolean",
    }


def test_date_requires_explicit_formats_and_uses_strict_parsing() -> None:
    graph, source, target = graph_with_one_transform(
        {"function": "date", "inputFormat": "%d/%m/%Y", "outputFormat": "%Y-%m-%d"},
        target_type="date",
    )
    result = run_graph(graph, source, target, [{"values": {SOURCE_ID: "31/12/2025"}}])
    assert result.rows[0].target_values[TARGET_ID] == "2025-12-31"

    invalid = run_graph(
        graph,
        source,
        target,
        [{"values": {SOURCE_ID: "2025-12-31"}}],
    )
    assert invalid.rows[0].outcome == "failed"
    assert invalid.rows[0].errors[0].code == "invalid_date"

    with pytest.raises(EngineValidationError):
        run_graph(
            {
                **graph,
                "nodes": [
                    {**item, "config": {"function": "date"}} if item["type"] == "fx" else item
                    for item in graph["nodes"]
                ],
            },
            source,
            target,
            [],
        )


def test_e164_requires_context_for_national_input() -> None:
    graph, source, target = graph_with_one_transform({"function": "e164"}, target_type="string")
    missing_context = run_graph(graph, source, target, [{"values": {SOURCE_ID: "4155552671"}}])
    assert missing_context.rows[0].outcome == "failed"
    assert missing_context.rows[0].errors[0].code == "country_context_required"

    graph["nodes"][1]["config"]["countryCallingCode"] = "1"
    normalized = run_graph(graph, source, target, [{"values": {SOURCE_ID: "(415) 555-2671"}}])
    assert normalized.rows[0].target_values[TARGET_ID] == "+14155552671"


def test_e164_rejects_invalid_and_non_ascii_phone_digits() -> None:
    graph, source, target = graph_with_one_transform(
        {"function": "e164", "countryCallingCode": "1"}
    )
    for value in ("1", "٤١٥٥٥٥٢٦٧١", "+0123456789"):
        result = run_graph(graph, source, target, [{"values": {SOURCE_ID: value}}])
        assert result.rows[0].outcome == "failed"
        assert result.rows[0].errors[0].code == "invalid_phone"


def test_constant_node_can_populate_target_field() -> None:
    constant_id = str(uuid4())
    graph = {
        "version": 1,
        "nodes": [
            node("source", SOURCE_NODE),
            node("constant", constant_id, {"value": "seed"}),
            node("target", TARGET_NODE),
        ],
        "edges": [edge(constant_id, "output", TARGET_NODE, f"field:{TARGET_ID}")],
    }
    result = run_graph(
        graph,
        [],
        [FieldSpec(TARGET_ID, "string", required=True)],
        [{"values": {}}],
    )
    assert result.rows[0].target_values == {TARGET_ID: "seed"}


def test_concat_and_ifelse_nodes_support_multiple_inputs() -> None:
    source_fields = [
        FieldSpec(SOURCE_ID, "string"),
        FieldSpec(TARGET_ID, "string"),
        FieldSpec("33333333-3333-4333-8333-333333333333", "boolean"),
    ]
    target_field = FieldSpec("44444444-4444-4444-8444-444444444444", "string")
    concat_id = str(uuid4())
    graph = {
        "version": 1,
        "nodes": [
            node("source", SOURCE_NODE),
            node("concat", concat_id, {"separator": " "}),
            node("target", TARGET_NODE),
        ],
        "edges": [
            edge(SOURCE_NODE, f"field:{SOURCE_ID}", concat_id, "input"),
            edge(SOURCE_NODE, f"field:{TARGET_ID}", concat_id, "input"),
            edge(concat_id, "output", TARGET_NODE, f"field:{target_field.id}"),
        ],
    }
    result = run_graph(
        graph,
        source_fields,
        [target_field],
        [{"values": {SOURCE_ID: "Ada", TARGET_ID: "Lovelace"}}],
    )
    assert result.rows[0].target_values[target_field.id] == "Ada Lovelace"

    ifelse_id = str(uuid4())
    ifelse_graph = {
        "version": 1,
        "nodes": [
            node("source", SOURCE_NODE),
            node("ifelse", ifelse_id),
            node("target", TARGET_NODE),
        ],
        "edges": [
            edge(SOURCE_NODE, "field:33333333-3333-4333-8333-333333333333", ifelse_id, "input"),
            edge(SOURCE_NODE, f"field:{SOURCE_ID}", ifelse_id, "input"),
            edge(SOURCE_NODE, f"field:{TARGET_ID}", ifelse_id, "input"),
            edge(ifelse_id, "output", TARGET_NODE, f"field:{target_field.id}"),
        ],
    }
    ifelse_result = run_graph(
        ifelse_graph,
        source_fields,
        [target_field],
        [
            {
                "values": {
                    "33333333-3333-4333-8333-333333333333": True,
                    SOURCE_ID: "yes",
                    TARGET_ID: "no",
                }
            }
        ],
    )
    assert ifelse_result.rows[0].target_values[target_field.id] == "yes"


@pytest.mark.parametrize(
    ("node_type", "config", "inputs", "expected"),
    [
        ("map", {"mapping": {"a": "mapped"}}, ["a"], "mapped"),
        ("map", {"mapping": {"42": "mapped"}}, [42], "mapped"),
        ("map", {"mapping": {"a": "mapped"}, "fallback": "other"}, ["b"], "other"),
        ("lookup", {"table": {"a": "found"}}, ["a"], "found"),
        ("lookup", {"table": {"a": "found"}, "fallback": "missing"}, ["b"], "missing"),
        ("coalesce", {}, [None, "first", "second"], "first"),
        ("concat", {"separator": ","}, ["a", None, "b"], "a,,b"),
    ],
)
def test_generic_mapping_nodes(node_type, config, inputs, expected) -> None:
    source_specs = [FieldSpec(str(uuid4()), "string") for _ in inputs]
    target_spec = FieldSpec(str(uuid4()), "string")
    source_id, target_id, operation_id = str(uuid4()), str(uuid4()), str(uuid4())
    nodes = [
        node("source", source_id),
        node(node_type, operation_id, config),
        node("target", target_id),
    ]
    edges = [edge(source_id, f"field:{field.id}", operation_id, "input") for field in source_specs]
    edges.append(edge(operation_id, "output", target_id, f"field:{target_spec.id}"))
    graph = {"version": 1, "nodes": nodes, "edges": edges}
    row = {"values": {field.id: value for field, value in zip(source_specs, inputs, strict=True)}}
    result = run_graph(graph, source_specs, [target_spec], [row])
    assert result.rows[0].target_values[target_spec.id] == expected


def test_validate_node_checks_required_type_bounds_and_allowlist() -> None:
    graph, source, target = graph_with_one_transform(
        {"rules": {"required": True, "type": "string", "allowedValues": ["ok"]}}
    )
    graph["nodes"][1]["type"] = "validate"
    valid = run_graph(graph, source, target, [{"values": {SOURCE_ID: "ok"}}])
    assert valid.rows[0].target_values[TARGET_ID] == "ok"
    invalid = run_graph(graph, source, target, [{"values": {SOURCE_ID: "no"}}])
    assert invalid.rows[0].outcome == "failed"
    assert invalid.rows[0].errors[0].code == "validation_failed"

    graph["nodes"][1]["config"]["rules"] = {"min": 2, "max": 5}
    graph["nodes"][1]["config"].pop("errorPolicy", None)
    numeric_source = [FieldSpec(SOURCE_ID, "number")]
    numeric_target = [FieldSpec(TARGET_ID, "number")]
    bounded = run_graph(
        graph,
        numeric_source,
        numeric_target,
        [{"values": {SOURCE_ID: 3}}],
    )
    assert bounded.rows[0].target_values[TARGET_ID] == 3
    below_minimum = run_graph(
        graph,
        numeric_source,
        numeric_target,
        [{"values": {SOURCE_ID: 1}}],
    )
    assert below_minimum.rows[0].errors[0].code == "validation_failed"


@pytest.mark.parametrize(
    ("policy", "expected_outcome", "expected_value"),
    [
        ("fail", "failed", None),
        ("skip", "skipped", None),
        ("default", "ok", "fallback"),
    ],
)
def test_error_policies_and_recovered_error(policy, expected_outcome, expected_value) -> None:
    config = {"function": "trim", "errorPolicy": policy}
    if policy == "default":
        config["defaultValue"] = "fallback"
    graph, source, target = graph_with_one_transform(config)
    result = run_graph(graph, source, target, [{"values": {SOURCE_ID: 10}}])
    row = result.rows[0]
    assert row.outcome == expected_outcome
    assert row.target_values.get(TARGET_ID) == expected_value
    assert bool(row.errors[0].recovered) is (policy == "default")
    assert result.summary[expected_outcome] == 1


def test_filter_excludes_row_without_execution_error() -> None:
    graph, source, target = graph_with_one_transform({})
    graph["nodes"][1]["type"] = "filter"
    filtered = run_graph(graph, source, target, [{"values": {SOURCE_ID: False}}])
    assert filtered.rows[0].outcome == "skipped"
    assert filtered.rows[0].errors == ()
    assert filtered.rows[0].trace[-1].outcome == "filtered"


def test_missing_null_required_default_and_target_types_are_distinct() -> None:
    graph, source, _ = graph_with_one_transform({"function": "trim"})
    target = [FieldSpec(TARGET_ID, "string", required=True, nullable=False)]
    missing = run_graph(graph, source, target, [{"values": {}}])
    explicit_null = run_graph(graph, source, target, [{"values": {SOURCE_ID: None}}])
    assert missing.rows[0].errors[0].code == "required_field_missing"
    assert explicit_null.rows[0].errors[0].code == "null_not_allowed"

    target = [
        FieldSpec(
            TARGET_ID,
            "string",
            required=True,
            has_default=True,
            default_value="default",
        )
    ]
    defaulted = run_graph(graph, source, target, [{"values": {}}])
    assert defaulted.rows[0].target_values[TARGET_ID] == "default"

    nullable_target = [FieldSpec(TARGET_ID, "string", nullable=False)]
    null_value = run_graph(graph, source, nullable_target, [{"values": {SOURCE_ID: None}}])
    assert null_value.rows[0].errors[0].code == "null_not_allowed"

    number_graph, number_source, number_target = graph_with_one_transform(
        {"function": "trim"}, target_type="number"
    )
    mismatch = run_graph(
        number_graph, number_source, number_target, [{"values": {SOURCE_ID: "text"}}]
    )
    assert mismatch.rows[0].errors[0].code == "target_type_mismatch"


def test_graph_version_direction_ownership_cycle_and_direct_type_validation() -> None:
    graph, source, target = graph_with_one_transform({"function": "trim"})
    with pytest.raises(EngineValidationError) as version_error:
        run_graph({**graph, "version": True}, source, target, [])
    assert version_error.value.issues[0].code == "unsupported_graph_version"

    direct = {
        "version": 1,
        "nodes": [node("source", SOURCE_NODE), node("target", TARGET_NODE)],
        "edges": [edge(SOURCE_NODE, f"field:{SOURCE_ID}", TARGET_NODE, f"field:{TARGET_ID}")],
    }
    with pytest.raises(EngineValidationError, match="validation"):
        run_graph(direct, source, [FieldSpec(TARGET_ID, "number")], [])

    second_transform = str(uuid4())
    cyclic = {
        "version": 1,
        "nodes": [
            node("source", SOURCE_NODE),
            node("fx", TRANSFORM_NODE, {"function": "trim"}),
            node("fx", second_transform, {"function": "lower"}),
            node("target", TARGET_NODE),
        ],
        "edges": [
            edge(SOURCE_NODE, f"field:{SOURCE_ID}", TRANSFORM_NODE, "input"),
            edge(TRANSFORM_NODE, "output", second_transform, "input"),
            edge(second_transform, "output", TARGET_NODE, f"field:{TARGET_ID}"),
            edge(second_transform, "output", TRANSFORM_NODE, "input"),
        ],
    }
    with pytest.raises(EngineValidationError) as cycle_error:
        run_graph(cyclic, source, target, [])
    assert any(issue.code == "graph_cycle" for issue in cycle_error.value.issues)


def test_graph_shape_field_count_and_datetime_validation_are_bounded() -> None:
    graph, source, target = graph_with_one_transform({"function": "trim"})
    with pytest.raises(EngineValidationError) as shape_error:
        run_graph({**graph, "unexpected": True}, source, target, [])
    assert any(issue.code == "invalid_graph_shape" for issue in shape_error.value.issues)

    with pytest.raises(EngineError) as field_limit:
        run_graph(graph, source, target, [], EngineLimits(max_fields=1))
    assert field_limit.value.code == "field_limit"

    datetime_graph, datetime_source, datetime_target = graph_with_one_transform(
        {"function": "trim"}, target_type="datetime"
    )
    date_only = run_graph(
        datetime_graph,
        datetime_source,
        datetime_target,
        [{"values": {SOURCE_ID: "2025-01-01"}}],
    )
    assert date_only.rows[0].errors[0].code == "target_type_mismatch"


def test_source_trace_ports_keep_graph_order() -> None:
    second_source_id = "33333333-3333-4333-8333-333333333333"
    third_source_id = "44444444-4444-4444-8444-444444444444"
    graph = {
        "version": 1,
        "nodes": [node("source", SOURCE_NODE), node("target", TARGET_NODE)],
        "edges": [
            edge(SOURCE_NODE, f"field:{second_source_id}", TARGET_NODE, f"field:{TARGET_ID}"),
            edge(SOURCE_NODE, f"field:{SOURCE_ID}", TARGET_NODE, f"field:{third_source_id}"),
        ],
    }
    result = run_graph(
        graph,
        [FieldSpec(SOURCE_ID, "string"), FieldSpec(second_source_id, "string")],
        [FieldSpec(TARGET_ID, "string"), FieldSpec(third_source_id, "string")],
        [{"values": {}}],
    )
    assert list(result.rows[0].trace[0].outputs) == [
        f"field:{second_source_id}",
        f"field:{SOURCE_ID}",
    ]


def test_limits_trace_redaction_and_determinism() -> None:
    graph, source, target = graph_with_one_transform({"function": "upper"})
    rows = [{"rowId": "1", "values": {SOURCE_ID: "ada"}}]
    first = run_graph(graph, source, target, rows)
    second = run_graph(graph, source, target, rows)
    assert first.to_dict() == second.to_dict()
    assert first.rows[0].trace[0].outputs[f"field:{SOURCE_ID}"] == "[redacted]"

    visible = run_graph(
        graph,
        source,
        target,
        rows,
        EngineLimits(include_trace_values=True),
    )
    assert visible.rows[0].trace[0].outputs[f"field:{SOURCE_ID}"] == "ada"

    truncated = run_graph(
        graph,
        source,
        target,
        rows,
        EngineLimits(max_trace_bytes=1),
    )
    assert truncated.trace_truncated
    assert truncated.rows[0].trace_truncated
    assert truncated.rows[0].trace == ()

    with pytest.raises(EngineError) as row_limit:
        run_graph(graph, source, target, rows * 2, EngineLimits(max_rows=1))
    assert row_limit.value.code == "row_limit"

    with pytest.raises(EngineError) as input_limit:
        run_graph(
            graph,
            source,
            target,
            [{"values": {SOURCE_ID: "x" * 100}}],
            EngineLimits(max_input_bytes=20),
        )
    assert input_limit.value.code == "input_size_limit"

    with pytest.raises(EngineError) as output_limit:
        run_graph(
            graph,
            source,
            target,
            rows,
            EngineLimits(max_output_bytes=10),
        )
    assert output_limit.value.code == "output_limit"

    with pytest.raises(EngineError) as time_limit:
        run_graph(
            graph,
            source,
            target,
            rows,
            EngineLimits(max_execution_seconds=1e-12),
        )
    assert time_limit.value.code == "execution_time_limit"


def test_duplicate_row_ids_and_strict_json_values_are_rejected() -> None:
    graph, source, target = graph_with_one_transform({"function": "trim"})
    with pytest.raises(EngineValidationError) as duplicate:
        run_graph(
            graph,
            source,
            target,
            [
                {"rowId": "duplicate", "values": {}},
                {"rowId": "duplicate", "values": {}},
            ],
        )
    assert duplicate.value.issues[0].code == "duplicate_row_id"

    with pytest.raises(EngineValidationError) as non_string_key:
        run_graph(
            graph,
            source,
            target,
            [{"values": {SOURCE_ID: {1: "not-json-object"}}}],
        )
    assert non_string_key.value.issues[0].code == "invalid_json_value"


def test_engine_has_no_web_database_or_filesystem_imports() -> None:
    engine_path = Path(__file__).parents[1] / "app" / "engine"
    forbidden = {"fastapi", "sqlalchemy", "psycopg", "starlette", "pathlib", "os"}
    for source_path in engine_path.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                imported = {alias.name.split(".")[0] for alias in item.names}
                assert not imported & forbidden, source_path
            elif isinstance(item, ast.ImportFrom) and item.module:
                assert item.module.split(".")[0] not in forbidden, source_path
