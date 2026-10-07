import { describe, expect, it } from "vitest";
import {
  directTypeCompatibility,
  normalizeSchemaType,
  validateTypeChain,
} from "./mappingTypeValidation";

describe("type normalization", () => {
  it("normalizes supported aliases", () => {
    expect(normalizeSchemaType("text")).toBe("string");
    expect(normalizeSchemaType("integer")).toBe("integer");
    expect(normalizeSchemaType("decimal")).toBe("number");
    expect(normalizeSchemaType("bool")).toBe("boolean");
    expect(normalizeSchemaType("timestamp")).toBe("datetime");
  });
});

describe("direct compatibility", () => {
  it("string -> string direct = Valid", () => {
    expect(directTypeCompatibility({
      produced: "string",
      expected: "string",
      receiverNullable: false,
    }).status).toBe("Valid");
  });

  it("integer -> number direct = Valid", () => {
    expect(directTypeCompatibility({
      produced: "integer",
      expected: "number",
      receiverNullable: false,
    }).status).toBe("Valid");
  });

  it("string -> integer direct = Error", () => {
    const result = directTypeCompatibility({
      produced: "string",
      expected: "integer",
      receiverNullable: false,
    });
    expect(result.status).toBe("Error");
    expect(result.issue).toContain("Expected integer");
  });

  it("nullable compatibility is respected", () => {
    expect(directTypeCompatibility({
      produced: "null",
      expected: "string",
      receiverNullable: true,
    }).status).toBe("Valid");
    expect(directTypeCompatibility({
      produced: "null",
      expected: "string",
      receiverNullable: false,
    }).status).toBe("Error");
  });
});

describe("type propagation through transformation chains", () => {
  it("string -> toString -> integer = Error", () => {
    const result = validateTypeChain({
      senderType: "string",
      transformations: [{ nodeType: "fx", label: "toString", config: { function: "toString" } }],
      receiverType: "integer",
      receiverNullable: false,
    });
    expect(result.status).toBe("Error");
    expect(result.issue).toContain("Expected integer");
  });

  it("integer -> toString -> string = Valid", () => {
    const result = validateTypeChain({
      senderType: "integer",
      transformations: [{ nodeType: "fx", label: "toString", config: { function: "toString" } }],
      receiverType: "string",
      receiverNullable: false,
    });
    expect(result.status).toBe("Valid");
  });

  it("string -> toInteger -> integer = Valid", () => {
    const result = validateTypeChain({
      senderType: "string",
      transformations: [{ nodeType: "fx", label: "toInteger", config: { function: "toInteger" } }],
      receiverType: "integer",
      receiverNullable: false,
    });
    expect(result.status).toBe("Valid");
  });

  it("number -> toInteger -> integer = Warning", () => {
    const result = validateTypeChain({
      senderType: "number",
      transformations: [{ nodeType: "fx", label: "toInteger", config: { function: "toInteger" } }],
      receiverType: "integer",
      receiverNullable: false,
    });
    expect(result.status).toBe("Warning");
    expect(result.issue).toContain("discard decimal");
  });

  it("incompatible transformation input = Error", () => {
    const result = validateTypeChain({
      senderType: "object",
      transformations: [{ nodeType: "fx", label: "parseDate", config: { function: "parseDate" } }],
      receiverType: "datetime",
      receiverNullable: false,
    });
    expect(result.status).toBe("Error");
    expect(result.issue).toContain("expects string input");
  });

  it("unknown function output = Error", () => {
    const result = validateTypeChain({
      senderType: "string",
      transformations: [{ nodeType: "fx", label: "mystery", config: { function: "mystery" } }],
      receiverType: "string",
      receiverNullable: false,
    });
    expect(result.status).toBe("Error");
    expect(result.issue).toContain("no known output type");
  });

  it("multi-step type propagation preserves order", () => {
    const result = validateTypeChain({
      senderType: "string",
      transformations: [
        { nodeType: "fx", label: "toNumber", config: { function: "toNumber" } },
        { nodeType: "fx", label: "toInteger", config: { function: "toInteger" } },
      ],
      receiverType: "integer",
      receiverNullable: false,
    });
    expect(result.steps.map((step) => step.label)).toEqual(["toNumber", "toInteger"]);
    expect(result.outputType).toBe("integer");
  });
});

