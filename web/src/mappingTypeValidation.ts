export type NormalizedType =
  | "string"
  | "integer"
  | "number"
  | "boolean"
  | "date"
  | "datetime"
  | "object"
  | "array"
  | "null"
  | "unknown";

export type ValidationSeverity = "Valid" | "Warning" | "Error";

export type TypeValidationStep = {
  label: string;
  input: NormalizedType;
  output: NormalizedType;
  status: ValidationSeverity;
  issue: string;
  lossy: boolean;
};

export type TypeValidationResult = {
  status: ValidationSeverity;
  issue: string;
  outputType: NormalizedType;
  steps: TypeValidationStep[];
  lossy: boolean;
};

export type TransformationForValidation = {
  nodeType: string;
  label: string;
  config: Record<string, unknown>;
};

function severityRank(severity: ValidationSeverity): number {
  if (severity === "Error") return 3;
  if (severity === "Warning") return 2;
  return 1;
}

function worseSeverity(left: ValidationSeverity, right: ValidationSeverity): ValidationSeverity {
  return severityRank(left) >= severityRank(right) ? left : right;
}

function normalizeFunctionName(value: unknown): string {
  return typeof value === "string"
    ? value.trim().toLowerCase().replace(/[_\-\s]+/g, "")
    : "";
}

function normalizeAlias(value: string): NormalizedType {
  const raw = value.trim().toLowerCase();
  if (!raw) return "unknown";
  if (["string", "text", "varchar", "char"].includes(raw)) return "string";
  if (["int", "integer", "long", "short"].includes(raw)) return "integer";
  if (["number", "float", "double", "decimal", "numeric"].includes(raw)) return "number";
  if (["bool", "boolean"].includes(raw)) return "boolean";
  if (["date"].includes(raw)) return "date";
  if (["datetime", "timestamp", "timestamptz"].includes(raw)) return "datetime";
  if (["object", "json", "jsonobject"].includes(raw)) return "object";
  if (["array", "list"].includes(raw)) return "array";
  if (["null", "nil"].includes(raw)) return "null";
  return "unknown";
}

export function normalizeSchemaType(value: string | null | undefined): NormalizedType {
  if (!value) return "unknown";
  return normalizeAlias(value);
}

function normalizeValueType(value: unknown): NormalizedType {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "string") return "string";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
  if (typeof value === "object") return "object";
  return "unknown";
}

export function directTypeCompatibility(input: {
  produced: NormalizedType;
  expected: NormalizedType;
  receiverNullable: boolean;
}): { status: ValidationSeverity; issue: string } {
  const { produced, expected, receiverNullable } = input;
  if (produced === "null") {
    return receiverNullable
      ? { status: "Valid", issue: "" }
      : { status: "Error", issue: "Receiver does not allow null values." };
  }
  if (produced === "unknown") {
    return { status: "Error", issue: `Expected ${expected}, but produced type is unknown.` };
  }
  if (expected === "unknown") {
    return { status: "Error", issue: "Receiver field type is unknown." };
  }
  if (produced === expected) return { status: "Valid", issue: "" };
  if (produced === "integer" && expected === "number") return { status: "Valid", issue: "" };
  if (produced === "date" && expected === "datetime") return { status: "Valid", issue: "" };
  if ((produced === "object" || produced === "array" || expected === "object" || expected === "array")
    && produced !== expected) {
    return { status: "Error", issue: `Expected ${expected}, but produced ${produced}.` };
  }
  return { status: "Error", issue: `Expected ${expected}, but produced ${produced}.` };
}

function transformationStep(node: TransformationForValidation, inputType: NormalizedType): TypeValidationStep {
  if (node.nodeType === "constant") {
    const output = normalizeValueType(node.config.value);
    return {
      label: node.label,
      input: inputType,
      output,
      status: output === "unknown" ? "Error" : "Valid",
      issue: output === "unknown" ? "Constant output type is unknown." : "",
      lossy: false,
    };
  }

  if (node.nodeType === "fx") {
    const fxName = normalizeFunctionName(node.config.function);
    if (fxName === "tostring") {
      return { label: node.label, input: inputType, output: "string", status: "Valid", issue: "", lossy: false };
    }
    if (fxName === "tointeger" || fxName === "toint") {
      if (!["string", "integer", "number"].includes(inputType)) {
        return {
          label: node.label,
          input: inputType,
          output: "integer",
          status: "Error",
          issue: `toInteger cannot accept ${inputType}.`,
          lossy: false,
        };
      }
      return {
        label: node.label,
        input: inputType,
        output: "integer",
        status: inputType === "number" ? "Warning" : "Valid",
        issue: inputType === "number" ? "toInteger may discard decimal values." : "",
        lossy: inputType === "number",
      };
    }
    if (fxName === "tonumber") {
      if (!["string", "integer", "number"].includes(inputType)) {
        return {
          label: node.label,
          input: inputType,
          output: "number",
          status: "Error",
          issue: `toNumber cannot accept ${inputType}.`,
          lossy: false,
        };
      }
      return {
        label: node.label,
        input: inputType,
        output: "number",
        status: inputType === "string" ? "Warning" : "Valid",
        issue: inputType === "string" ? "toNumber depends on parseable numeric text." : "",
        lossy: false,
      };
    }
    if (fxName === "toboolean") {
      if (!["string", "integer", "number", "boolean"].includes(inputType)) {
        return {
          label: node.label,
          input: inputType,
          output: "boolean",
          status: "Error",
          issue: `toBoolean cannot accept ${inputType}.`,
          lossy: false,
        };
      }
      return {
        label: node.label,
        input: inputType,
        output: "boolean",
        status: inputType === "boolean" ? "Valid" : "Warning",
        issue: inputType === "boolean" ? "" : "toBoolean depends on coercion rules.",
        lossy: inputType !== "boolean",
      };
    }
    if (fxName === "parsedate") {
      if (inputType !== "string") {
        return {
          label: node.label,
          input: inputType,
          output: "datetime",
          status: "Error",
          issue: `parseDate expects string input, received ${inputType}.`,
          lossy: false,
        };
      }
      return { label: node.label, input: inputType, output: "datetime", status: "Valid", issue: "", lossy: false };
    }
    if (fxName === "formatdate") {
      if (!["date", "datetime"].includes(inputType)) {
        return {
          label: node.label,
          input: inputType,
          output: "string",
          status: "Error",
          issue: `formatDate expects date or datetime input, received ${inputType}.`,
          lossy: false,
        };
      }
      return { label: node.label, input: inputType, output: "string", status: "Valid", issue: "", lossy: false };
    }
    return {
      label: node.label,
      input: inputType,
      output: "unknown",
      status: "Error",
      issue: `Transformation “${String(node.config.function ?? node.label)}” has no known output type.`,
      lossy: false,
    };
  }

  if (node.nodeType === "concat") {
    return {
      label: node.label,
      input: inputType,
      output: "string",
      status: inputType === "string" ? "Valid" : "Warning",
      issue: inputType === "string" ? "" : "Concatenate converts non-string values to string.",
      lossy: inputType !== "string",
    };
  }

  if (node.nodeType === "ifelse") {
    return {
      label: node.label,
      input: inputType,
      output: "unknown",
      status: "Warning",
      issue: "If / else output type cannot be inferred from single-path metadata.",
      lossy: false,
    };
  }

  if (node.nodeType === "map") {
    return {
      label: node.label,
      input: inputType,
      output: "unknown",
      status: "Warning",
      issue: "Map output type depends on mapping table values.",
      lossy: false,
    };
  }

  if (node.nodeType === "coalesce") {
    return { label: node.label, input: inputType, output: inputType, status: "Valid", issue: "", lossy: false };
  }

  if (node.nodeType === "lookup") {
    return {
      label: node.label,
      input: inputType,
      output: "unknown",
      status: "Warning",
      issue: "Lookup output type depends on lookup table configuration.",
      lossy: false,
    };
  }

  if (node.nodeType === "filter") {
    if (inputType !== "boolean") {
      return {
        label: node.label,
        input: inputType,
        output: "unknown",
        status: "Error",
        issue: `Filter expects boolean input, received ${inputType}.`,
        lossy: false,
      };
    }
    return {
      label: node.label,
      input: inputType,
      output: "unknown",
      status: "Warning",
      issue: "Filter controls row emission and does not provide a concrete value type.",
      lossy: false,
    };
  }

  if (node.nodeType === "validate") {
    return { label: node.label, input: inputType, output: inputType, status: "Valid", issue: "", lossy: false };
  }

  return {
    label: node.label,
    input: inputType,
    output: "unknown",
    status: "Error",
    issue: `Transformation type “${node.nodeType}” is not in the type registry.`,
    lossy: false,
  };
}

export function validateTypeChain(input: {
  senderType: string | null | undefined;
  transformations: TransformationForValidation[];
  receiverType: string | null | undefined;
  receiverNullable: boolean;
}): TypeValidationResult {
  const receiverType = normalizeSchemaType(input.receiverType);
  let currentType = normalizeSchemaType(input.senderType);
  const steps: TypeValidationStep[] = [];
  let status: ValidationSeverity = "Valid";
  let issue = "";
  let lossy = false;

  for (const transform of input.transformations) {
    const step = transformationStep(transform, currentType);
    steps.push(step);
    currentType = step.output;
    lossy = lossy || step.lossy;
    status = worseSeverity(status, step.status);
    if (!issue && step.issue) issue = step.issue;
    if (step.status === "Error") {
      return { status: "Error", issue, outputType: currentType, steps, lossy };
    }
  }

  const compatibility = directTypeCompatibility({
    produced: currentType,
    expected: receiverType,
    receiverNullable: input.receiverNullable,
  });
  status = worseSeverity(status, compatibility.status);
  if (!issue && compatibility.issue) issue = compatibility.issue;

  return {
    status,
    issue,
    outputType: currentType,
    steps,
    lossy,
  };
}

