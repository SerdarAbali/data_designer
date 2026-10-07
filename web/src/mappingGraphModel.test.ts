import { describe, expect, it } from "vitest";
import {
  deriveMappingChains,
  fieldIdFromPort,
  transformationLabel,
  transformationSummary,
  type MappingGraphDocument,
  type MappingGraphEdge,
  type MappingGraphField,
  type MappingGraphNode,
} from "./mappingGraphModel";

const SOURCE_ID = "source-node";
const TARGET_ID = "target-node";
const SENDER_ID = "11111111-1111-4111-8111-111111111111";
const SECOND_SENDER_ID = "22222222-2222-4222-8222-222222222222";
const RECEIVER_ID = "33333333-3333-4333-8333-333333333333";

function node(
  id: string,
  type: string,
  config: Record<string, unknown> = {},
): MappingGraphNode {
  return { id, type, config };
}

function edge(
  id: string,
  sourceNodeId: string,
  sourcePortId: string,
  targetNodeId: string,
  targetPortId: string,
): MappingGraphEdge {
  return { id, sourceNodeId, sourcePortId, targetNodeId, targetPortId };
}

function field(id: string, data_type = "string"): MappingGraphField {
  return { id, data_type, required: true, nullable: false };
}

function graph(nodes: MappingGraphNode[], edges: MappingGraphEdge[]): MappingGraphDocument {
  return { nodes, edges };
}

function derive(
  document: MappingGraphDocument,
  senderFields: MappingGraphField[] = [field(SENDER_ID)],
  receiverFields: MappingGraphField[] = [field(RECEIVER_ID)],
) {
  return deriveMappingChains({ graph: document, senderFields, receiverFields });
}

describe("persisted mapping graph interpretation", () => {
  it("derives a direct sender field to receiver field mapping", () => {
    const [chain] = derive(graph(
      [node(SOURCE_ID, "source"), node(TARGET_ID, "target")],
      [edge("direct", SOURCE_ID, `field:${SENDER_ID}`, TARGET_ID, `field:${RECEIVER_ID}`)],
    ));

    expect(chain?.inputs.map((item) => item.senderFieldId)).toEqual([SENDER_ID]);
    expect(chain?.receiverFieldId).toBe(RECEIVER_ID);
    expect(chain?.transformations).toEqual([]);
    expect(chain?.validation?.status).toBe("Valid");
  });

  it("derives one transformation between the sender and receiver", () => {
    const [chain] = derive(graph(
      [node(SOURCE_ID, "source"), node("cast", "fx", { function: "toInt" }), node(TARGET_ID, "target")],
      [
        edge("in", SOURCE_ID, `field:${SENDER_ID}`, "cast", "input"),
        edge("out", "cast", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ), [field(SENDER_ID, "string")], [field(RECEIVER_ID, "integer")]);

    expect(chain?.transformations.map((item) => item.label)).toEqual(["Convert to integer"]);
    expect(chain?.inputs[0]?.transformationNodeIds).toEqual(["cast"]);
    expect(chain?.validation?.status).toBe("Valid");
  });

  it("preserves multiple transformation steps in execution order", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("first", "fx", { function: "toNumber" }),
        node("second", "fx", { function: "toInteger" }),
        node(TARGET_ID, "target"),
      ],
      [
        edge("e1", SOURCE_ID, `field:${SENDER_ID}`, "first", "input"),
        edge("e2", "first", "output", "second", "input"),
        edge("e3", "second", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ));

    expect(chain?.transformations.map((item) => item.nodeId)).toEqual(["first", "second"]);
    expect(chain?.validation?.steps.map((step) => step.label)).toEqual([
      "Convert to number",
      "Convert to integer",
    ]);
  });

  it("emits separate receiver chains when one sender branches", () => {
    const secondReceiver = "44444444-4444-4444-8444-444444444444";
    const chains = derive(graph(
      [node(SOURCE_ID, "source"), node(TARGET_ID, "target")],
      [
        edge("branch-a", SOURCE_ID, `field:${SENDER_ID}`, TARGET_ID, `field:${RECEIVER_ID}`),
        edge("branch-b", SOURCE_ID, `field:${SENDER_ID}`, TARGET_ID, `field:${secondReceiver}`),
      ],
    ), [field(SENDER_ID)], [field(RECEIVER_ID), field(secondReceiver)]);

    expect(chains.map((chain) => chain.receiverFieldId)).toEqual([RECEIVER_ID, secondReceiver]);
    expect(chains.map((chain) => chain.inputs[0]?.senderFieldId)).toEqual([SENDER_ID, SENDER_ID]);
  });

  it("represents fan-in as one receiver chain with every input and edge", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("concat", "concat", { separator: " " }),
        node(TARGET_ID, "target"),
      ],
      [
        edge("in-a", SOURCE_ID, `field:${SENDER_ID}`, "concat", "input"),
        edge("in-b", SOURCE_ID, `field:${SECOND_SENDER_ID}`, "concat", "input"),
        edge("out", "concat", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ), [field(SENDER_ID), field(SECOND_SENDER_ID)], [field(RECEIVER_ID)]);

    expect(chain?.inputs).toHaveLength(2);
    expect(chain?.receiverFieldId).toBe(RECEIVER_ID);
    expect(chain?.inputs.map((item) => item.senderFieldId)).toEqual([SENDER_ID, SECOND_SENDER_ID]);
    expect(chain?.edgeIds).toEqual(["in-a", "out", "in-b"]);
    expect(chain?.validation).toBeNull();
    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "multiple_inputs_need_review",
      severity: "Warning",
      message: "Transformation has multiple inputs and needs visual review.",
    }));
  });

  it("retains every fan-in sender rather than selecting a primary input", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("concat", "concat"),
        node(TARGET_ID, "target"),
      ],
      [
        edge("input-a", SOURCE_ID, `field:${SENDER_ID}`, "concat", "input"),
        edge("input-b", SOURCE_ID, `field:${SECOND_SENDER_ID}`, "concat", "input"),
        edge("result", "concat", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ), [field(SENDER_ID), field(SECOND_SENDER_ID)], [field(RECEIVER_ID)]);

    expect(chain?.inputs.map((item) => item.edgeIds)).toEqual([["input-a", "result"], ["input-b", "result"]]);
  });

  it("reports a missing sender schema field while retaining its explicit ID", () => {
    const [chain] = derive(graph(
      [node(SOURCE_ID, "source"), node(TARGET_ID, "target")],
      [edge("direct", SOURCE_ID, `field:${SENDER_ID}`, TARGET_ID, `field:${RECEIVER_ID}`)],
    ), [], [field(RECEIVER_ID)]);

    expect(chain?.inputs[0]?.senderFieldId).toBe(SENDER_ID);
    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "missing_source_field",
      severity: "Error",
      senderFieldIds: [SENDER_ID],
    }));
  });

  it("reports a missing receiver schema field while retaining its explicit ID", () => {
    const [chain] = derive(graph(
      [node(SOURCE_ID, "source"), node(TARGET_ID, "target")],
      [edge("direct", SOURCE_ID, `field:${SENDER_ID}`, TARGET_ID, `field:${RECEIVER_ID}`)],
    ), [field(SENDER_ID)], []);

    expect(chain?.receiverFieldId).toBe(RECEIVER_ID);
    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "missing_receiver_field",
      receiverFieldIds: [RECEIVER_ID],
    }));
  });

  it("reports a missing transformation node without inventing a sender", () => {
    const [chain] = derive(graph(
      [node(TARGET_ID, "target")],
      [edge("out", "deleted-transform", "output", TARGET_ID, `field:${RECEIVER_ID}`)],
    ));

    expect(chain?.inputs[0]?.senderFieldId).toBeNull();
    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "missing_transformation_node",
      nodeIds: ["deleted-transform"],
      edgeIds: ["out"],
    }));
  });

  it("reports invalid transformation input ports", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("cast", "fx"),
        node(TARGET_ID, "target"),
      ],
      [
        edge("in", SOURCE_ID, `field:${SENDER_ID}`, "cast", "secondary-input"),
        edge("out", "cast", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ));

    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "invalid_transformation_input_port",
      message: "Transformation input handle is invalid.",
      edgeIds: expect.arrayContaining(["in", "out"]),
    }));
  });

  it("reports invalid transformation output ports", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("cast", "fx"),
        node(TARGET_ID, "target"),
      ],
      [
        edge("in", SOURCE_ID, `field:${SENDER_ID}`, "cast", "input"),
        edge("out", "cast", "unknown-output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ));

    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "invalid_transformation_output_port",
      message: "Transformation output handle is invalid.",
    }));
  });

  it("detects cycles and returns involved graph IDs", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("first", "fx"),
        node("second", "fx"),
        node(TARGET_ID, "target"),
      ],
      [
        edge("source-in", SOURCE_ID, `field:${SENDER_ID}`, "first", "input"),
        edge("cycle-a", "first", "output", "second", "input"),
        edge("cycle-b", "second", "output", "first", "input"),
        edge("receiver", "second", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ));

    expect(chain?.issues).toContainEqual(expect.objectContaining({
      code: "cycle",
      nodeIds: expect.arrayContaining(["first", "second"]),
    }));
  });

  it("returns disconnected transformations as explicit incomplete chains", () => {
    const chains = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node(TARGET_ID, "target"),
        node("orphan", "fx"),
      ],
      [edge("orphan-input", SOURCE_ID, `field:${SENDER_ID}`, "orphan", "input")],
    ));
    const orphan = chains.find((chain) => chain.issues.some(
      (item) => item.code === "disconnected_transformation",
    ));

    expect(orphan?.inputs.map((item) => item.senderFieldId)).toEqual([SENDER_ID]);
    expect(orphan?.issues[0]?.nodeIds).toContain("orphan");
    expect(orphan?.issues[0]?.edgeIds).toContain("orphan-input");
    expect(orphan?.transformations.map((item) => item.nodeId)).toContain("orphan");
  });

  it("extracts exact field IDs from field ports", () => {
    expect(fieldIdFromPort(`field:${SENDER_ID}`)).toBe(SENDER_ID);
    expect(fieldIdFromPort("field:")).toBeNull();
    expect(fieldIdFromPort("input")).toBeNull();
  });

  it("keeps similar field metadata distinct by explicit field ID", () => {
    const firstId = "55555555-5555-4555-8555-555555555555";
    const secondId = "66666666-6666-4666-8666-666666666666";
    const graphFor = (fieldId: string) => graph(
      [node(SOURCE_ID, "source"), node(TARGET_ID, "target")],
      [edge("direct", SOURCE_ID, `field:${fieldId}`, TARGET_ID, `field:${RECEIVER_ID}`)],
    );

    const sameLabelFields = [
      { ...field(firstId), name: "record_id", label: "Record ID" },
      { ...field(secondId), name: "record_id", label: "Record ID" },
    ];
    const firstChain = derive(graphFor(firstId), [sameLabelFields[0]!], [field(RECEIVER_ID)])[0];
    const secondChain = derive(graphFor(secondId), [sameLabelFields[1]!], [field(RECEIVER_ID)])[0];

    expect(firstChain?.inputs[0]?.senderFieldId).toBe(firstId);
    expect(secondChain?.inputs[0]?.senderFieldId).toBe(secondId);
    expect(firstChain?.inputs[0]?.senderFieldId).not.toBe(secondChain?.inputs[0]?.senderFieldId);
  });

  it("uses friendly function labels without changing operation identifiers", () => {
    const config = { function: "toInt" };
    const originalConfig = structuredClone(config);

    expect(transformationLabel("fx", config)).toBe("Convert to integer");
    expect(transformationLabel("fx", { function: "toInteger" })).toBe("Convert to integer");
    expect(transformationLabel("fx", { function: "toString" })).toBe("Convert to text");
    expect(transformationLabel("fx", { function: "customOp" })).toBe("customOp");
    expect(transformationSummary([])).toBe("Direct");
    expect(config).toEqual(originalConfig);
  });

  it("exposes type-validation steps in chain order", () => {
    const [chain] = derive(graph(
      [
        node(SOURCE_ID, "source"),
        node("number", "fx", { function: "toNumber" }),
        node("integer", "fx", { function: "toInteger" }),
        node(TARGET_ID, "target"),
      ],
      [
        edge("e1", SOURCE_ID, `field:${SENDER_ID}`, "number", "input"),
        edge("e2", "number", "output", "integer", "input"),
        edge("e3", "integer", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    ), [field(SENDER_ID, "string")], [field(RECEIVER_ID, "integer")]);

    expect(chain?.validation?.steps.map((step) => step.label)).toEqual([
      "Convert to number",
      "Convert to integer",
    ]);
    expect(chain?.validation?.steps.map((step) => [step.input, step.output])).toEqual([
      ["string", "number"],
      ["number", "integer"],
    ]);
  });

  it("does not mutate graph documents or field metadata", () => {
    const inputGraph = graph(
      [
        node(SOURCE_ID, "source"),
        node("cast", "fx", { function: "toInt", options: { strict: true } }),
        node(TARGET_ID, "target"),
      ],
      [
        edge("in", SOURCE_ID, `field:${SENDER_ID}`, "cast", "input"),
        edge("out", "cast", "output", TARGET_ID, `field:${RECEIVER_ID}`),
      ],
    );
    const senderFields = [field(SENDER_ID)];
    const receiverFields = [field(RECEIVER_ID, "integer")];
    const before = structuredClone({ inputGraph, senderFields, receiverFields });

    const [chain] = deriveMappingChains({ graph: inputGraph, senderFields, receiverFields });

    expect({ inputGraph, senderFields, receiverFields }).toEqual(before);
    expect(chain?.transformations[0]?.config).toEqual(inputGraph.nodes[1]?.config);
    expect(chain?.transformations[0]?.config).not.toBe(inputGraph.nodes[1]?.config);
  });

  it("returns an explicit issue for a missing receiver node", () => {
    const chains = derive(graph(
      [node(SOURCE_ID, "source")],
      [edge("dangling", SOURCE_ID, `field:${SENDER_ID}`, "deleted-target", `field:${RECEIVER_ID}`)],
    ));

    expect(chains).toContainEqual(expect.objectContaining({
      receiverFieldId: RECEIVER_ID,
      receiverEdgeId: null,
      inputs: expect.arrayContaining([
        expect.objectContaining({ senderFieldId: SENDER_ID }),
      ]),
      issues: expect.arrayContaining([
        expect.objectContaining({ code: "missing_graph_node" }),
      ]),
    }));
  });
});
