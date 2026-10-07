from __future__ import annotations

import json
import math
from datetime import date, datetime

MISSING = object()


class OperationFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


NODE_CONFIG_KEYS: dict[str, set[str]] = {
    "source": set(),
    "target": set(),
    "constant": {"value"},
    "fx": {
        "function",
        "errorPolicy",
        "defaultValue",
        "inputFormat",
        "outputFormat",
        "countryCallingCode",
    },
    "concat": {"separator", "errorPolicy", "defaultValue"},
    "ifelse": {"errorPolicy", "defaultValue"},
    "map": {"mapping", "fallback", "defaultValue", "errorPolicy"},
    "coalesce": {"errorPolicy", "defaultValue"},
    "lookup": {"table", "fallback", "defaultValue", "errorPolicy"},
    "filter": {"errorPolicy", "defaultValue"},
    "validate": {"rules", "errorPolicy", "defaultValue"},
}
ERROR_POLICIES = {"fail", "skip", "default"}
FX_FUNCTIONS = {
    "trim",
    "title",
    "lower",
    "upper",
    "e164",
    "date",
    "toInt",
    "toNumber",
    "toString",
    "toBoolean",
    "parseDate",
    "formatDate",
}


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return isinstance(value, int) or math.isfinite(value)


def validate_node_config(node: dict, path: str) -> None:
    node_type = node["type"]
    config = node.get("config", {})
    if not isinstance(config, dict):
        raise OperationFailure("invalid_node_config", f"{path}.config must be an object")
    unknown_keys = set(config) - NODE_CONFIG_KEYS[node_type]
    if unknown_keys:
        raise OperationFailure(
            "invalid_node_config",
            f"{path}.config contains unsupported keys: {', '.join(sorted(unknown_keys))}",
        )

    if node_type in {"source", "target"}:
        if config:
            raise OperationFailure(
                "invalid_node_config", f"{path}.config is not supported for {node_type} nodes"
            )
        return
    if node_type == "constant":
        if "value" not in config:
            raise OperationFailure("invalid_node_config", f"{path}.config.value is required")
        return

    policy = config.get("errorPolicy", "fail")
    if not isinstance(policy, str) or policy not in ERROR_POLICIES:
        raise OperationFailure(
            "invalid_error_policy",
            f"{path}.config.errorPolicy must be fail, skip, or default",
        )
    if policy == "default" and "defaultValue" not in config:
        raise OperationFailure(
            "invalid_node_config",
            f"{path}.config.defaultValue is required when errorPolicy is default",
        )
    if policy != "default" and "defaultValue" in config:
        raise OperationFailure(
            "invalid_node_config",
            f"{path}.config.defaultValue requires errorPolicy default",
        )

    if node_type == "fx":
        function = config.get("function")
        if not isinstance(function, str) or function not in FX_FUNCTIONS:
            raise OperationFailure(
                "unsupported_function", f"{path}.config.function is not supported"
            )
        if function == "date" and (
            not isinstance(config.get("inputFormat"), str)
            or not isinstance(config.get("outputFormat"), str)
        ):
            raise OperationFailure(
                "invalid_node_config",
                f"{path} date nodes require inputFormat and outputFormat",
            )
        if function == "parseDate" and not isinstance(config.get("inputFormat"), str):
            raise OperationFailure(
                "invalid_node_config", f"{path} parseDate nodes require inputFormat"
            )
        if function == "formatDate" and not isinstance(config.get("outputFormat"), str):
            raise OperationFailure(
                "invalid_node_config", f"{path} formatDate nodes require outputFormat"
            )
        if "countryCallingCode" in config:
            calling_code = config["countryCallingCode"]
            if (
                not isinstance(calling_code, str)
                or not calling_code.isdigit()
                or not 1 <= len(calling_code) <= 3
                or calling_code.startswith("0")
            ):
                raise OperationFailure(
                    "invalid_node_config",
                    f"{path}.config.countryCallingCode must be 1-3 digits without a leading zero",
                )
    elif node_type == "concat":
        if not isinstance(config.get("separator", ""), str):
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.separator must be a string"
            )
    elif node_type == "map":
        if not isinstance(config.get("mapping"), dict):
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.mapping must be an object"
            )
    elif node_type == "lookup":
        if not isinstance(config.get("table"), dict):
            raise OperationFailure("invalid_node_config", f"{path}.config.table must be an object")
    elif node_type == "validate":
        rules = config.get("rules")
        if not isinstance(rules, dict) or not rules:
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.rules must be a non-empty object"
            )
        allowed_rules = {"required", "type", "min", "max", "allowedValues"}
        if set(rules) - allowed_rules:
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.rules contains an unsupported rule"
            )
        if "required" in rules and not isinstance(rules["required"], bool):
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.rules.required must be boolean"
            )
        if "type" in rules and not isinstance(rules["type"], str):
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.rules.type must be a string"
            )
        for key in ("min", "max"):
            if key in rules and (not is_finite_number(rules[key])):
                raise OperationFailure(
                    "invalid_node_config", f"{path}.config.rules.{key} must be finite numeric"
                )
        if "allowedValues" in rules and not isinstance(rules["allowedValues"], list):
            raise OperationFailure(
                "invalid_node_config",
                f"{path}.config.rules.allowedValues must be an array",
            )
        if "min" in rules and "max" in rules and rules["min"] > rules["max"]:
            raise OperationFailure(
                "invalid_node_config", f"{path}.config.rules.min cannot exceed max"
            )


def validate_json_value(value: object, *, max_bytes: int) -> None:
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > 64:
            raise OperationFailure("value_depth_limit", "A value exceeds the nesting depth limit")
        if current is None or isinstance(current, str | bool | int):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise OperationFailure("invalid_json_value", "Values must be finite JSON values")
            continue
        if isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
            continue
        if isinstance(current, dict) and all(isinstance(key, str) for key in current):
            pending.extend((item, depth + 1) for item in current.values())
            continue
        raise OperationFailure("invalid_json_value", "Values must be finite JSON values")
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise OperationFailure("invalid_json_value", "Values must be finite JSON values") from error
    if len(serialized) > max_bytes:
        raise OperationFailure("value_size_limit", "A value exceeds the configured size limit")


def matches_data_type(value: object, data_type: str) -> bool:
    normalized = data_type.strip().casefold()
    if normalized in {"string", "text"}:
        return isinstance(value, str)
    if normalized in {"number", "float", "decimal"}:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            or (isinstance(value, float) and math.isfinite(value))
        )
    if normalized in {"integer", "int"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized in {"boolean", "bool"}:
        return isinstance(value, bool)
    if normalized == "date":
        if not isinstance(value, str):
            return False
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if normalized == "datetime":
        if not isinstance(value, str) or "T" not in value:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    if normalized in {"object", "json"}:
        return isinstance(value, dict)
    if normalized == "array":
        return isinstance(value, list)
    return False


def execute_operation(node_type: str, config: dict, inputs: list[object]) -> object:
    if node_type == "fx":
        return execute_fx(config, only_input(inputs, "fx"))
    if node_type == "concat":
        if not inputs:
            raise OperationFailure("missing_input", "concat requires at least one input")
        if any(
            value is not MISSING and value is not None and not isinstance(value, str)
            for value in inputs
        ):
            raise OperationFailure("type_mismatch", "concat inputs must be strings or null")
        separator = config.get("separator", "")
        return separator.join(
            "" if value is MISSING or value is None else value for value in inputs
        )
    if node_type == "ifelse":
        require_input_count(inputs, 3, "ifelse")
        condition, if_true, if_false = inputs
        if not isinstance(condition, bool):
            raise OperationFailure("type_mismatch", "ifelse condition must be boolean")
        return if_true if condition else if_false
    if node_type == "map":
        value = only_input(inputs, "map")
        if value is MISSING or value is None:
            return value
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, int | float):
            value = str(value)
        elif not isinstance(value, str):
            raise OperationFailure("type_mismatch", "map input must be a string or scalar number")
        mapping = config["mapping"]
        if value in mapping:
            return mapping[value]
        return config.get("fallback", value)
    if node_type == "coalesce":
        if not inputs:
            raise OperationFailure("missing_input", "coalesce requires at least one input")
        return next((value for value in inputs if value is not MISSING and value is not None), None)
    if node_type == "lookup":
        value = only_input(inputs, "lookup")
        if value is MISSING or value is None:
            return value
        if not isinstance(value, str):
            raise OperationFailure("type_mismatch", "lookup input must be a string")
        table = config["table"]
        if value in table:
            return table[value]
        if "fallback" in config:
            return config["fallback"]
        raise OperationFailure("lookup_miss", "lookup table has no matching key")
    if node_type == "filter":
        value = only_input(inputs, "filter")
        if not isinstance(value, bool):
            raise OperationFailure("type_mismatch", "filter input must be boolean")
        return value
    if node_type == "validate":
        value = only_input(inputs, "validate")
        validate_value(value, config["rules"])
        return value
    raise OperationFailure("unsupported_node", f"Node type {node_type} is not executable")


def only_input(inputs: list[object], node_type: str) -> object:
    require_input_count(inputs, 1, node_type)
    return inputs[0]


def require_input_count(inputs: list[object], expected: int, node_type: str) -> None:
    if len(inputs) != expected:
        raise OperationFailure(
            "invalid_input_count",
            f"{node_type} requires exactly {expected} input connection(s)",
        )


def execute_fx(config: dict, value: object) -> object:
    if value is MISSING or value is None:
        return value
    function = config["function"]
    if function == "toInt":
        if isinstance(value, bool):
            raise OperationFailure(
                "type_mismatch", "toInt input must be a numeric string or number"
            )
        try:
            if isinstance(value, int):
                return value
            if isinstance(value, float) and math.isfinite(value) and value.is_integer():
                return int(value)
            if isinstance(value, str) and value.strip() and value.strip().lstrip("+-").isdigit():
                return int(value.strip())
        except (ValueError, OverflowError):
            pass
        raise OperationFailure("invalid_number", "Value cannot be converted to an integer")
    if function == "toNumber":
        if isinstance(value, bool):
            raise OperationFailure(
                "type_mismatch", "toNumber input must be a numeric string or number"
            )
        if isinstance(value, int):
            return value
        try:
            number = float(value.strip()) if isinstance(value, str) and value.strip() else value
        except ValueError as error:
            raise OperationFailure(
                "invalid_number", "Value cannot be converted to a number"
            ) from error
        if (
            isinstance(number, int | float)
            and not isinstance(number, bool)
            and math.isfinite(number)
        ):
            return number
        raise OperationFailure("invalid_number", "Value cannot be converted to a finite number")
    if function == "toBoolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, int | float) and not isinstance(value, bool) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "1"}:
                return True
            if normalized in {"false", "0"}:
                return False
        raise OperationFailure("invalid_boolean", "Value must be true, false, 1, or 0")
    if function == "toString":
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            if isinstance(value, float) and not math.isfinite(value):
                raise OperationFailure(
                    "type_mismatch", "toString input must be a finite JSON value"
                )
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)
        if isinstance(value, dict | list):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        raise OperationFailure("type_mismatch", "toString input is not a supported JSON value")
    if function == "formatDate":
        if not isinstance(value, str):
            raise OperationFailure(
                "type_mismatch",
                "formatDate input must be an ISO date or datetime string",
            )
        try:
            try:
                parsed_date = date.fromisoformat(value)
                parsed = datetime.combine(parsed_date, datetime.min.time())
            except ValueError:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                raise OperationFailure(
                    "timezone_not_supported",
                    "Date transformation does not convert timezone-aware values",
                )
            return parsed.strftime(config["outputFormat"])
        except ValueError as error:
            raise OperationFailure(
                "invalid_date", "Value must be a valid ISO date or datetime"
            ) from error
    if function == "parseDate":
        if not isinstance(value, str):
            raise OperationFailure("type_mismatch", "parseDate input must be a string")
        try:
            parsed = datetime.strptime(value, config["inputFormat"])
        except ValueError as error:
            raise OperationFailure("invalid_date", "Value does not match inputFormat") from error
        if parsed.strftime(config["inputFormat"]) != value:
            raise OperationFailure("invalid_date", "Value is not an exact inputFormat match")
        if parsed.tzinfo is not None:
            raise OperationFailure(
                "timezone_not_supported",
                "Date transformation does not convert timezone-aware values",
            )
        if any(token in config["inputFormat"] for token in ("%H", "%I", "%M", "%S", "%f")):
            return parsed.isoformat()
        return parsed.date().isoformat()
    if not isinstance(value, str):
        raise OperationFailure("type_mismatch", "fx input must be a string or null")
    if function == "trim":
        return value.strip()
    if function == "lower":
        return value.lower()
    if function == "upper":
        return value.upper()
    if function == "title":
        return value.title()
    if function == "date":
        input_format, output_format = config["inputFormat"], config["outputFormat"]
        try:
            parsed = datetime.strptime(value, input_format)
        except ValueError as error:
            raise OperationFailure("invalid_date", "Value does not match inputFormat") from error
        if parsed.strftime(input_format) != value:
            raise OperationFailure("invalid_date", "Value is not an exact inputFormat match")
        if parsed.tzinfo is not None:
            raise OperationFailure(
                "timezone_not_supported",
                "Date transformation does not convert timezone-aware values",
            )
        return parsed.strftime(output_format)
    if function == "e164":
        return normalize_e164(value, config.get("countryCallingCode"))
    raise OperationFailure("unsupported_function", f"Function {function} is not supported")


def normalize_e164(value: str, calling_code: str | None) -> str:
    compact = "".join(character for character in value if character not in " ()-.\t")
    if not compact or any(not (character.isdigit() or character == "+") for character in compact):
        raise OperationFailure("invalid_phone", "Phone number contains unsupported characters")
    if compact.startswith("+"):
        digits = compact[1:]
    else:
        if calling_code is None:
            raise OperationFailure(
                "country_context_required",
                "A countryCallingCode is required for numbers without an international prefix",
            )
        digits = calling_code + compact
    if (
        not digits
        or any(character < "0" or character > "9" for character in digits)
        or not 8 <= len(digits) <= 15
        or digits.startswith("0")
    ):
        raise OperationFailure("invalid_phone", "Number cannot be represented in E.164 format")
    return f"+{digits}"


def validate_value(value: object, rules: dict) -> None:
    if value is MISSING or value is None:
        if rules.get("required", False):
            raise OperationFailure("validation_failed", "A required value is missing or null")
        return
    expected_type = rules.get("type")
    if expected_type is not None and not matches_data_type(value, expected_type):
        raise OperationFailure("validation_failed", f"Value must have type {expected_type}")
    if "allowedValues" in rules and value not in rules["allowedValues"]:
        raise OperationFailure("validation_failed", "Value is not in allowedValues")
    if "min" in rules or "max" in rules:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise OperationFailure("validation_failed", "min and max rules require a number")
        if "min" in rules and value < rules["min"]:
            raise OperationFailure("validation_failed", "Value is below min")
        if "max" in rules and value > rules["max"]:
            raise OperationFailure("validation_failed", "Value is above max")


def apply_target_field(value: object, field_spec) -> object:
    if value is MISSING:
        if field_spec.has_default:
            value = field_spec.default_value
        elif field_spec.required:
            raise OperationFailure("required_field_missing", "Required target field has no value")
        else:
            return MISSING
    if value is None:
        if not field_spec.nullable:
            raise OperationFailure("null_not_allowed", "Target field does not allow null")
        return None
    if not matches_data_type(value, field_spec.data_type):
        value = coerce_target_scalar(value, field_spec.data_type)
    if not matches_data_type(value, field_spec.data_type):
        raise OperationFailure(
            "target_type_mismatch",
            f"Value is incompatible with target data_type {field_spec.data_type}",
        )
    return value


def coerce_target_scalar(value: object, data_type: str) -> object:
    normalized = data_type.strip().casefold()
    if normalized in {"string", "text"}:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float) and not isinstance(value, bool):
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)
        return value
    if normalized in {"integer", "int"}:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(value.strip())
            except ValueError:
                return value
    elif normalized in {"number", "float", "decimal"}:
        if isinstance(value, bool) or isinstance(value, int | float):
            return value
        if isinstance(value, str) and value.strip():
            try:
                converted = float(value.strip())
                if math.isfinite(converted):
                    return int(converted) if converted.is_integer() else converted
            except ValueError:
                return value
    elif normalized in {"boolean", "bool"}:
        if isinstance(value, int | float) and not isinstance(value, bool) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized_value = value.strip().casefold()
            if normalized_value in {"true", "1"}:
                return True
            if normalized_value in {"false", "0"}:
                return False
    return value
