import { describe, expect, it } from "vitest";
import {
  computePhaseGraphsForSave,
  deriveMappingMatrixRows,
  dirtyStateForWorkbenchViewSwitch,
  applyWorkbenchLayout,
  filterMappingMatrixRows,
  graphFromFlow,
  normalizeUuidForApi,
  pruneSelectionForActiveFlow,
  resolveMatrixRowSelection,
  sanitizeCanvasFlowForPhase,
  transformationPositionBetweenHandles,
  validatePhaseConnection,
  type FlowEdge,
  type FlowNode,
} from "./IntegrationWorkspace";
import { edgeAnimationClassName, mapperEdgePath } from "./components/mapper/MapperEdge";

function node(id: string, type: FlowNode["type"] = "fx"): FlowNode {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: { label: id, config: {} },
  } as FlowNode;
}

function edge(id: string, source: string, target: string): FlowEdge {
  return {
    id,
    source,
    target,
    sourceHandle: "output",
    targetHandle: "input",
  } as FlowEdge;
}

type MatrixInput = Parameters<typeof deriveMappingMatrixRows>[0];
type MatrixField = MatrixInput["senderFields"][number];

function matrixField(
  id: string,
  label: string,
  dataType = "string",
  options?: { required?: boolean; nullable?: boolean; name?: string },
): MatrixField {
  return {
    id,
    object_id: "obj",
    name: options?.name ?? label.toLowerCase().replace(/\s+/g, "_"),
    label,
    data_type: dataType,
    required: options?.required ?? false,
    nullable: options?.nullable ?? false,
    default_value: null,
    position: 0,
  };
}

function sourceFieldEdge(id: string, sourceNodeId: string, senderFieldId: string, targetNodeId: string): FlowEdge {
  return {
    id,
    source: sourceNodeId,
    sourceHandle: `field:${senderFieldId}`,
    target: targetNodeId,
    targetHandle: "input",
  } as FlowEdge;
}

function targetFieldEdge(id: string, sourceNodeId: string, receiverFieldId: string, targetNodeId: string): FlowEdge {
  return {
    id,
    source: sourceNodeId,
    sourceHandle: "output",
    target: targetNodeId,
    targetHandle: `field:${receiverFieldId}`,
  } as FlowEdge;
}

describe("phase isolation helpers", () => {
  it("Request -> Success Response -> Request keeps only request-compatible IDs active", () => {
    const flow = {
      nodes: [node("request:a"), node("response:b"), node("c")],
      edges: [edge("e1", "request:a", "c"), edge("e2", "response:b", "c")],
    };
    const request = sanitizeCanvasFlowForPhase("request", flow);
    expect(request.nodes.map((n) => n.id)).toEqual(["request:a", "c"]);
    expect(request.edges.map((e) => e.id)).toEqual(["e1"]);
  });

  it("Success Response -> Request -> Success Response keeps only response-compatible IDs active", () => {
    const flow = {
      nodes: [node("request:a"), node("response:b"), node("c")],
      edges: [edge("e1", "request:a", "response:b"), edge("e2", "response:b", "c")],
    };
    const success = sanitizeCanvasFlowForPhase("success-response", flow);
    expect(success.nodes.map((n) => n.id)).toEqual(["response:b", "c"]);
    expect(success.edges.map((e) => e.id)).toEqual(["e2"]);
  });

  it("clears selected node/edge when they are absent after phase switch", () => {
    const nodes = [node("request:a")];
    const edges = [edge("e1", "request:a", "request:a")];
    expect(pruneSelectionForActiveFlow("response:b", "e2", nodes, edges)).toEqual({
      nodeId: "",
      edgeId: "",
    });
  });
});

describe("phase connection validation", () => {
  const sender = matrixField("sender-field", "phone number");
  const receiver = matrixField("receiver-field", "phonenumber");
  const endpoint = (id: string, type: FlowNode["type"]): FlowNode => ({
    ...node(id, type),
    data: { label: id, config: {}, phase: "request" },
  });
  const connect = (
    source: string,
    sourceHandle: string,
    target: string,
    targetHandle: string,
  ): Parameters<typeof validatePhaseConnection>[0] => ({
    source,
    sourceHandle,
    target,
    targetHandle,
  });
  const validate = (
    connection: Parameters<typeof validatePhaseConnection>[0],
    nodes: FlowNode[],
    edges: FlowEdge[] = [],
    phase: Parameters<typeof validatePhaseConnection>[5] = "request",
  ) => validatePhaseConnection(connection, nodes, edges, [sender], [receiver], phase);

  it("rejects target-to-source reverse edges and wrong-direction field handles", () => {
    const nodes = [endpoint("source", "source"), endpoint("target", "target")];
    expect(validate(connect("target", "field:receiver-field", "source", "field:sender-field"), nodes))
      .toEqual({ valid: false, message: "Receiver fields cannot start a connection." });
    const transform = endpoint("transform", "fx");
    expect(validate(connect("transform", "output", "source", "field:sender-field"), [...nodes, transform]))
      .toEqual({ valid: false, message: "Sender fields cannot receive a connection." });
    expect(validate(connect("target", "output", "source", "input"), nodes).valid).toBe(false);
    expect(validate(connect("source", "field:unknown", "target", "field:receiver-field"), nodes).valid).toBe(false);
    const transformNode = endpoint("transform", "fx");
    expect(validate(connect("transform", "input", "target", "field:receiver-field"), [...nodes, transformNode]).valid)
      .toBe(false);
    expect(validate(connect("source", "field:sender-field", "transform", "output"), [...nodes, transformNode]).valid)
      .toBe(false);
  });

  it("allows sender-to-receiver and acyclic transformation paths", () => {
    const nodes = [
      endpoint("source", "source"),
      endpoint("target", "target"),
      endpoint("first-transform", "fx"),
      endpoint("second-transform", "map"),
    ];
    expect(validate(connect("source", "field:sender-field", "target", "field:receiver-field"), nodes).valid).toBe(true);
    expect(validate(connect("source", "field:sender-field", "first-transform", "input"), nodes).valid).toBe(true);
    expect(validate(connect("first-transform", "output", "target", "field:receiver-field"), nodes).valid).toBe(true);
    expect(validate(connect("first-transform", "output", "second-transform", "input"), nodes).valid).toBe(true);
  });

  it("rejects self-loops, duplicate edges, cycles, and cross-phase nodes", () => {
    const source = endpoint("source", "source");
    const transform = endpoint("transform", "fx");
    const target = endpoint("target", "target");
    const direct = connect("source", "field:sender-field", "target", "field:receiver-field");
    expect(validate(connect("transform", "output", "transform", "input"), [transform]).valid).toBe(false);
    expect(validate(direct, [source, target], [{
      id: "existing",
      source: "source",
      sourceHandle: "field:sender-field",
      target: "target",
      targetHandle: "field:receiver-field",
    } as FlowEdge]).valid).toBe(false);
    const firstTransform = endpoint("first-transform", "fx");
    const secondTransform = endpoint("second-transform", "map");
    expect(validate(
      connect("first-transform", "output", "second-transform", "input"),
      [firstTransform, secondTransform],
      [{ id: "path", source: "second-transform", target: "first-transform" } as FlowEdge],
    ).valid).toBe(false);
    const responseNode = {
      ...endpoint("response-node", "fx"),
      data: { label: "response-node", config: {}, phase: "success-response" as const },
    };
    expect(validate(connect("source", "field:sender-field", "response-node", "input"), [source, responseNode]).valid)
      .toBe(false);
  });
});

describe("field-aware transformation layout and position persistence", () => {
  const senderFields = [
    matrixField("s0", "Customer ID"),
    matrixField("s1", "Customer NO"),
    matrixField("s2", "phone number"),
    matrixField("s3", "extra sender"),
  ];
  const receiverFields = [
    matrixField("r0", "Customer ID"),
    matrixField("r1", "CustNo"),
    matrixField("r2", "response"),
    matrixField("r3", "phonenumber"),
  ];
  const source = { ...node("source", "source"), position: { x: 120, y: 100 } };
  const target = { ...node("target", "target"), position: { x: 920, y: 100 } };
  const context = { sourceFields: senderFields, targetFields: receiverFields };
  const fieldInput = (id: string, fieldId: string, targetNode: string): FlowEdge => ({
    id,
    source: "source",
    sourceHandle: `field:${fieldId}`,
    target: targetNode,
    targetHandle: targetNode === "target" ? `field:${fieldId}` : "input",
  } as FlowEdge);
  const transformOutput = (id: string, sourceNode: string, targetFieldId: string): FlowEdge => ({
    id,
    source: sourceNode,
    sourceHandle: "output",
    target: "target",
    targetHandle: `field:${targetFieldId}`,
  } as FlowEdge);

  it("places a one-transform chain inline for equal-height rows", () => {
    const transform = { ...node("fx", "fx"), position: { x: 0, y: 0 } };
    const edges = [
      fieldInput("in", "s1", "fx"),
      transformOutput("out", "fx", "r1"),
    ];
    const result = applyWorkbenchLayout([source, target, transform], edges, context);
    expect(result.find((item) => item.id === "fx")?.position.y).toBe(206);
  });

  it("uses the midpoint of differently positioned sender and receiver rows", () => {
    const lowerTarget = { ...target, position: { x: 920, y: 134 } };
    const transform = { ...node("fx", "fx"), position: { x: 0, y: 0 } };
    const edges = [
      fieldInput("in", "s1", "fx"),
      transformOutput("out", "fx", "r2"),
    ];
    const result = applyWorkbenchLayout([source, lowerTarget, transform], edges, context);
    expect(result.find((item) => item.id === "fx")?.position.y).toBe(240);
  });

  it("distributes multi-step chains in transformation order on one field lane", () => {
    const first = { ...node("fx-1", "fx"), position: { x: 0, y: 0 } };
    const second = { ...node("fx-2", "fx"), position: { x: 0, y: 0 } };
    const edges = [
      fieldInput("in", "s1", first.id),
      { id: "middle", source: first.id, sourceHandle: "output", target: second.id, targetHandle: "input" } as FlowEdge,
      transformOutput("out", second.id, "r1"),
    ];
    const result = applyWorkbenchLayout([source, target, first, second], edges, context);
    const laidFirst = result.find((item) => item.id === first.id)!;
    const laidSecond = result.find((item) => item.id === second.id)!;
    expect(laidFirst.position.x).toBeLessThan(laidSecond.position.x);
    expect(laidFirst.position.y).toBe(laidSecond.position.y);
    expect(laidFirst.position.y).toBe(206);
  });

  it("averages every sender row for fan-in and receiver rows for one-to-many", () => {
    const fanIn = { ...node("fanin", "fx"), position: { x: 0, y: 0 } };
    const fanInEdges = [
      fieldInput("in-a", "s0", fanIn.id),
      fieldInput("in-b", "s2", fanIn.id),
      transformOutput("out", fanIn.id, "r3"),
    ];
    const fanInLayout = applyWorkbenchLayout([source, target, fanIn], fanInEdges, context);
    expect(fanInLayout.find((item) => item.id === fanIn.id)?.position.y).toBe(229);

    const fanOut = { ...node("fanout", "fx"), position: { x: 0, y: 0 } };
    const fanOutEdges = [
      fieldInput("in", "s3", fanOut.id),
      transformOutput("out-a", fanOut.id, "r0"),
      transformOutput("out-b", fanOut.id, "r2"),
    ];
    const fanOutLayout = applyWorkbenchLayout([source, target, fanOut], fanOutEdges, context);
    expect(fanOutLayout.find((item) => item.id === fanOut.id)?.position.y).toBe(206);
  });

  it("preserves usable saved transform coordinates and falls back for default zero coordinates", () => {
    const saved = { ...node("saved", "fx"), position: { x: 330, y: 420 } };
    const defaulted = { ...node("defaulted", "fx"), position: { x: 0, y: 0 } };
    const result = applyWorkbenchLayout(
      [source, target, saved, defaulted],
      [
        fieldInput("saved-in", "s1", saved.id),
        transformOutput("saved-out", saved.id, "r1"),
        fieldInput("default-in", "s1", defaulted.id),
        transformOutput("default-out", defaulted.id, "r1"),
      ],
      context,
      { preservePersisted: true },
    );
    expect(result.find((item) => item.id === saved.id)?.position).toEqual({ x: 330, y: 420 });
    expect(result.find((item) => item.id === defaulted.id)?.position.y).toBe(206);
  });

  it("round-trips a manually moved position and isolates phase drafts", () => {
    const requestTransform = { ...node("request-fx", "fx"), position: { x: 410, y: 275 } };
    const successTransform = { ...node("success-fx", "fx"), position: { x: 620, y: 335 } };
    const requestDraft = graphFromFlow([source, target, requestTransform], []);
    const successDraft = graphFromFlow([source, target, successTransform], []);
    const requestSave = computePhaseGraphsForSave({
      contractView: "request",
      nodes: [source, target, requestTransform],
      edges: [],
      requestGraphDraft: requestDraft,
      responseGraphDraft: successDraft,
      errorResponseGraphDraft: graphFromFlow([], []),
      phaseEdited: { request: true, "success-response": false, "error-response": false, "async-response": false },
    });
    expect(requestSave.request.nodes.find((item) => item.id === requestTransform.id)?.position)
      .toEqual({ x: 410, y: 275 });
    expect(requestSave.response.nodes.find((item) => item.id === successTransform.id)?.position)
      .toEqual({ x: 620, y: 335 });
    const reload = graphFromFlow(
      requestSave.request.nodes.map((item) => ({ ...node(item.id, item.type), position: item.position, data: { label: item.id, config: item.config } })),
      [],
    );
    expect(reload.nodes.find((item) => item.id === requestTransform.id)?.position).toEqual({ x: 410, y: 275 });
  });

  it("does not serialize view-only fallback layout into an unrelated save", () => {
    const savedTransform = { ...node("persisted", "fx"), position: { x: 425, y: 315 } };
    const displayed = applyWorkbenchLayout(
      [source, target, savedTransform],
      [fieldInput("in", "s1", savedTransform.id), transformOutput("out", savedTransform.id, "r1")],
      context,
      { preservePersisted: true },
    );
    const draft = graphFromFlow([source, target, savedTransform], []);
    const result = computePhaseGraphsForSave({
      contractView: "request",
      nodes: displayed,
      edges: [],
      requestGraphDraft: draft,
      responseGraphDraft: graphFromFlow([], []),
      errorResponseGraphDraft: graphFromFlow([], []),
      phaseEdited: { request: false, "success-response": false, "error-response": false, "async-response": false },
    });
    expect(result.request.nodes.find((item) => item.id === "persisted")?.position).toEqual({ x: 425, y: 315 });
  });

  it("keeps IDs and counts stable when reset applies field-aware positions", () => {
    const transform = { ...node("fx", "fx"), position: { x: 0, y: 0 } };
    const edges = [fieldInput("input-edge", "s1", transform.id), transformOutput("output-edge", transform.id, "r1")];
    const result = applyWorkbenchLayout([source, target, transform], edges, context);
    expect(result.map((item) => item.id)).toEqual(["source", "target", "fx"]);
    expect(edges.map((item) => item.id)).toEqual(["input-edge", "output-edge"]);
    expect(result).toHaveLength(3);
    expect(edges).toHaveLength(2);
    expect(result.find((item) => item.id === transform.id)?.position.y).toBe(206);
  });

  it("uses measured handle centers and separates overlapping transformations minimally", () => {
    const first = { ...node("fx-a", "fx"), position: { x: 0, y: 0 } };
    const second = { ...node("fx-b", "fx"), position: { x: 0, y: 0 } };
    const edges = [
      fieldInput("a-in", "s1", first.id),
      transformOutput("a-out", first.id, "r1"),
      fieldInput("b-in", "s1", second.id),
      transformOutput("b-out", second.id, "r1"),
    ];
    const result = applyWorkbenchLayout([source, target, first, second], edges, {
      ...context,
      sourceHandleCenters: new Map([["s1", 500]]),
      targetHandleCenters: new Map([["r1", 500]]),
    });
    const a = result.find((item) => item.id === first.id)!;
    const b = result.find((item) => item.id === second.id)!;
    expect(a.position.y).toBe(482);
    expect(Math.abs(a.position.y - b.position.y)).toBeGreaterThanOrEqual(44);
  });

  it("centers a new transform on the actual handle midpoint", () => {
    expect(transformationPositionBetweenHandles({ x: 300, y: 215 }, { x: 920, y: 247 }, 150, 36))
      .toEqual({ x: 535, y: 213 });
  });

  it("uses compact fallback dimensions when centering a transformation before measurement", () => {
    expect(transformationPositionBetweenHandles({ x: 300, y: 215 }, { x: 920, y: 215 }))
      .toEqual({ x: 535, y: 197 });
  });
});

describe("phase save serialization", () => {
  const requestDraft = graphFromFlow([node("req")], []);
  const responseDraft = graphFromFlow([node("resp")], []);
  const errorDraft = graphFromFlow([], []);

  it("saving Request uses only Request draft when request graph is not edited", () => {
    const graphs = computePhaseGraphsForSave({
      contractView: "request",
      nodes: [node("response:bad")],
      edges: [],
      requestGraphDraft: requestDraft,
      responseGraphDraft: responseDraft,
      errorResponseGraphDraft: errorDraft,
      phaseEdited: {
        request: false,
        "success-response": false,
        "error-response": false,
        "async-response": false,
      },
    });
    expect(graphs.request).toEqual(requestDraft);
  });

  it("saving Success Response uses only response draft when response graph is not edited", () => {
    const graphs = computePhaseGraphsForSave({
      contractView: "success-response",
      nodes: [node("request:bad")],
      edges: [],
      requestGraphDraft: requestDraft,
      responseGraphDraft: responseDraft,
      errorResponseGraphDraft: errorDraft,
      phaseEdited: {
        request: false,
        "success-response": false,
        "error-response": false,
        "async-response": false,
      },
    });
    expect(graphs.response).toEqual(responseDraft);
  });

  it("namespace normalization preserves source/target and port semantics", () => {
    const graph = graphFromFlow(
      [node("response:11111111-1111-4111-8111-111111111111"), node("22222222-2222-4222-8222-222222222222")],
      [{
        id: "response:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        source: "response:11111111-1111-4111-8111-111111111111",
        target: "22222222-2222-4222-8222-222222222222",
        sourceHandle: "output",
        targetHandle: "input",
      } as FlowEdge],
    );
    expect(graph.edges[0]?.sourceNodeId).toBe("11111111-1111-4111-8111-111111111111");
    expect(graph.edges[0]?.targetNodeId).toBe("22222222-2222-4222-8222-222222222222");
    expect(graph.edges[0]?.sourcePortId).toBe("output");
    expect(graph.edges[0]?.targetPortId).toBe("input");
  });

  it("phase sanitization cannot introduce cycles", () => {
    const flow = {
      nodes: [node("request:a"), node("response:b"), node("c")],
      edges: [edge("e1", "request:a", "response:b"), edge("e2", "response:b", "c")],
    };
    const request = sanitizeCanvasFlowForPhase("request", flow);
    expect(request.edges.length).toBeLessThanOrEqual(flow.edges.length);
    expect(request.edges.some((e) => e.source === e.target)).toBe(false);
  });
});

describe("edge animation semantics", () => {
  it("uses a straight path when connected handles share a horizontal line", () => {
    expect(mapperEdgePath(10, 100, 310, 100, undefined, undefined, 12, true)[0])
      .toBe("M 10 100 L 310 100");
    expect(mapperEdgePath(10, 100, 310, 100)[0]).not.toBe("M 10 100 L 310 100");
  });

  it("uses source-to-target animation class independent of visual x ordering", () => {
    expect(edgeAnimationClassName()).toContain("mapper-edge-outbound");
    expect(edgeAnimationClassName()).not.toContain("mapper-edge-inbound");
  });

  it("leaves plain UUID values unchanged", () => {
    const id = "33333333-3333-4333-8333-333333333333";
    expect(normalizeUuidForApi(id)).toBe(id);
  });
});

describe("mapping matrix derivation", () => {
  const sourceNode = node("source-node", "source");
  const targetNode = node("target-node", "target");

  it("derives a direct mapping into one row", () => {
    const sender = matrixField("s-id", "Customer ID");
    const receiver = matrixField("r-id", "Customer ID");
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode],
      edges: [{
        id: "direct-edge",
        source: sourceNode.id,
        sourceHandle: `field:${sender.id}`,
        target: targetNode.id,
        targetHandle: `field:${receiver.id}`,
      } as FlowEdge],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]?.transformation).toBe("Direct");
    expect(rows[0]?.status).toBe("Valid");
  });

  it("derives sender -> transform -> receiver as one row", () => {
    const sender = matrixField("s-no", "Customer NO");
    const receiver = matrixField("r-no", "CustNo");
    const fx = node("fx-1", "fx");
    fx.data.config = { function: "toString" };
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode, fx],
      edges: [
        sourceFieldEdge("in", sourceNode.id, sender.id, fx.id),
        targetFieldEdge("out", fx.id, receiver.id, targetNode.id),
      ],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]?.transformation).toBe("Convert to text");
    expect(rows[0]?.graphEdgeIds.sort()).toEqual(["in", "out"]);
    expect(rows[0]?.primaryIssueEdgeId).toBe("out");
  });

  it("keeps the Matrix fan-in review row compatible while the shared model retains all inputs", () => {
    const senderA = matrixField("s-a", "Customer ID");
    const senderB = matrixField("s-b", "Customer Ref");
    const receiver = matrixField("r-id", "Customer ID");
    const concat = node("concat", "concat");
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode, concat],
      edges: [
        sourceFieldEdge("in-a", sourceNode.id, senderA.id, concat.id),
        sourceFieldEdge("in-b", sourceNode.id, senderB.id, concat.id),
        targetFieldEdge("out", concat.id, receiver.id, targetNode.id),
      ],
      senderFields: [senderA, senderB],
      receiverFields: [receiver],
    });

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      senderFieldId: senderA.id,
      transformation: "Concatenate",
      status: "Error",
      issue: "Transformation has multiple inputs and needs visual review.",
      transformationNodeIds: [concat.id],
      graphEdgeIds: ["out", "in-a"],
    });
  });

  it("preserves multi-step chain order", () => {
    const sender = matrixField("s-no", "Customer NO");
    const receiver = matrixField("r-no", "CustNo");
    const first = node("fx-1", "fx");
    first.data.config = { function: "trim" };
    const second = node("fx-2", "fx");
    second.data.config = { function: "toString" };
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode, first, second],
      edges: [
        sourceFieldEdge("e1", sourceNode.id, sender.id, first.id),
        { id: "e2", source: first.id, sourceHandle: "output", target: second.id, targetHandle: "input" } as FlowEdge,
        targetFieldEdge("e3", second.id, receiver.id, targetNode.id),
      ],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows[0]?.transformation).toBe("trim → Convert to text");
  });

  it("creates separate rows for one sender mapped to multiple receivers", () => {
    const sender = matrixField("s-id", "Customer ID");
    const receiverA = matrixField("r-a", "Customer ID");
    const receiverB = matrixField("r-b", "Customer Ref");
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode],
      edges: [
        { id: "da", source: sourceNode.id, sourceHandle: `field:${sender.id}`, target: targetNode.id, targetHandle: `field:${receiverA.id}` } as FlowEdge,
        { id: "db", source: sourceNode.id, sourceHandle: `field:${sender.id}`, target: targetNode.id, targetHandle: `field:${receiverB.id}` } as FlowEdge,
      ],
      senderFields: [sender],
      receiverFields: [receiverA, receiverB],
    });
    expect(rows.filter((row) => row.status === "Valid")).toHaveLength(2);
  });

  it("marks incomplete chains as Error rows", () => {
    const sender = matrixField("s-no", "Customer NO");
    const receiver = matrixField("r-no", "CustNo");
    const fx = node("fx-1", "fx");
    fx.data.config = { function: "toString" };
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode, fx],
      edges: [targetFieldEdge("out", fx.id, receiver.id, targetNode.id)],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows[0]?.status).toBe("Error");
    expect(rows[0]?.issue).toContain("no input");
  });

  it("marks required unmapped receiver as Error", () => {
    const sender = matrixField("s-id", "Customer ID");
    const requiredReceiver = matrixField("r-id", "Customer ID", "string", { required: true, nullable: false });
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode],
      edges: [],
      senderFields: [sender],
      receiverFields: [requiredReceiver],
    });
    expect(rows.find((row) => row.receiverFieldId === requiredReceiver.id)?.status).toBe("Error");
  });

  it("marks optional unmapped receiver as Unmapped", () => {
    const sender = matrixField("s-id", "Customer ID");
    const optionalReceiver = matrixField("r-id", "Customer ID", "string", { required: false, nullable: true });
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode],
      edges: [],
      senderFields: [sender],
      receiverFields: [optionalReceiver],
    });
    expect(rows.find((row) => row.receiverFieldId === optionalReceiver.id)?.status).toBe("Unmapped");
  });

  it("request phase excludes response mappings after sanitization", () => {
    const sender = matrixField("s-id", "Customer ID");
    const receiver = matrixField("r-id", "Customer ID");
    const mixedFlow = sanitizeCanvasFlowForPhase("request", {
      nodes: [node("request:source", "source"), node("request:target", "target"), node("response:fx", "fx")],
      edges: [
        { id: "request-edge", source: "request:source", sourceHandle: `field:${sender.id}`, target: "request:target", targetHandle: `field:${receiver.id}` } as FlowEdge,
        { id: "response-edge", source: "response:fx", sourceHandle: "output", target: "request:target", targetHandle: `field:${receiver.id}` } as FlowEdge,
      ],
    });
    const rows = deriveMappingMatrixRows({
      nodes: mixedFlow.nodes,
      edges: mixedFlow.edges,
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows.some((row) => row.graphEdgeIds.includes("response-edge"))).toBe(false);
    expect(rows.some((row) => row.graphEdgeIds.includes("request-edge"))).toBe(true);
  });

  it("success-response phase excludes request mappings after sanitization", () => {
    const sender = matrixField("s-id", "CustNo");
    const receiver = matrixField("r-id", "Customer NO");
    const mixedFlow = sanitizeCanvasFlowForPhase("success-response", {
      nodes: [node("request:fx", "fx"), node("response:source", "source"), node("response:target", "target")],
      edges: [
        { id: "request-edge", source: "request:fx", sourceHandle: "output", target: "response:target", targetHandle: `field:${receiver.id}` } as FlowEdge,
        { id: "response-edge", source: "response:source", sourceHandle: `field:${sender.id}`, target: "response:target", targetHandle: `field:${receiver.id}` } as FlowEdge,
      ],
    });
    const rows = deriveMappingMatrixRows({
      nodes: mixedFlow.nodes,
      edges: mixedFlow.edges,
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows.some((row) => row.graphEdgeIds.includes("request-edge"))).toBe(false);
    expect(rows.some((row) => row.graphEdgeIds.includes("response-edge"))).toBe(true);
  });

  it("resolves matrix row selection from related graph entities", () => {
    const sender = matrixField("s-id", "Customer ID");
    const receiver = matrixField("r-id", "Customer ID");
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode],
      edges: [{
        id: "direct-edge",
        source: sourceNode.id,
        sourceHandle: `field:${sender.id}`,
        target: targetNode.id,
        targetHandle: `field:${receiver.id}`,
      } as FlowEdge],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    const selectedRowId = resolveMatrixRowSelection(rows, "", "direct-edge");
    expect(selectedRowId).toBe(rows[0]?.id);
  });

  it("switching Canvas/Matrix preserves dirty state", () => {
    expect(dirtyStateForWorkbenchViewSwitch(true)).toBe(true);
    expect(dirtyStateForWorkbenchViewSwitch(false)).toBe(false);
  });

  it("offers an unambiguous fix suggestion for string -> toString -> integer", () => {
    const sender = matrixField("s-no", "Customer NO");
    const receiver = matrixField("r-no", "CustNo", "integer");
    const fx = node("fx-1", "fx");
    fx.data.config = { function: "toString" };
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode, fx],
      edges: [
        sourceFieldEdge("in", sourceNode.id, sender.id, fx.id),
        targetFieldEdge("out", fx.id, receiver.id, targetNode.id),
      ],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(rows[0]?.status).toBe("Error");
    expect(rows[0]?.suggestedFix?.to).toBe("toInt");
  });

  it("matrix derivation keeps graph counts unchanged", () => {
    const sender = matrixField("s-id", "Customer ID");
    const receiver = matrixField("r-id", "Customer ID");
    const matrixNodes = [sourceNode, targetNode];
    const matrixEdges = [{
      id: "direct-edge",
      source: sourceNode.id,
      sourceHandle: `field:${sender.id}`,
      target: targetNode.id,
      targetHandle: `field:${receiver.id}`,
    } as FlowEdge];
    deriveMappingMatrixRows({
      nodes: matrixNodes,
      edges: matrixEdges,
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(matrixNodes).toHaveLength(2);
    expect(matrixEdges).toHaveLength(1);
  });

  it("filters matrix rows by status", () => {
    const sender = matrixField("s-id", "Customer ID");
    const receiver = matrixField("r-id", "Customer ID");
    const rows = deriveMappingMatrixRows({
      nodes: [sourceNode, targetNode],
      edges: [{
        id: "direct-edge",
        source: sourceNode.id,
        sourceHandle: `field:${sender.id}`,
        target: targetNode.id,
        targetHandle: `field:${receiver.id}`,
      } as FlowEdge],
      senderFields: [sender],
      receiverFields: [receiver],
    });
    expect(filterMappingMatrixRows(rows, "mapped")).toHaveLength(1);
    expect(filterMappingMatrixRows(rows, "issues")).toHaveLength(0);
  });
});
