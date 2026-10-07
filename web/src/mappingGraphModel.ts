import {
  normalizeSchemaType,
  validateTypeChain,
  type NormalizedType,
  type TypeValidationResult,
  type TransformationForValidation,
} from "./mappingTypeValidation";

export type MappingGraphNode = {
  id: string;
  type: string;
  config: Record<string, unknown>;
};

export type MappingGraphEdge = {
  id: string;
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
};

export type MappingGraphDocument = {
  nodes: MappingGraphNode[];
  edges: MappingGraphEdge[];
};

export type MappingGraphField = {
  id: string;
  data_type: string;
  name?: string;
  label?: string;
  required?: boolean;
  nullable?: boolean;
};

export type MappingGraphIssueCode =
  | "invalid_source_port"
  | "invalid_receiver_port"
  | "invalid_transformation_output_port"
  | "invalid_transformation_input_port"
  | "missing_source_field"
  | "missing_receiver_field"
  | "missing_graph_node"
  | "missing_transformation_node"
  | "missing_transformation_input"
  | "receiver_cannot_produce"
  | "cycle"
  | "multiple_inputs_need_review"
  | "disconnected_transformation";

export type MappingGraphIssue = {
  code: MappingGraphIssueCode;
  severity: "Warning" | "Error";
  message: string;
  nodeIds: string[];
  edgeIds: string[];
  senderFieldIds: string[];
  receiverFieldIds: string[];
};

export type MappingGraphTransformation = {
  nodeId: string;
  nodeType: string;
  config: Record<string, unknown>;
  label: string;
};

export type MappingChainInput = {
  senderFieldId: string | null;
  transformationNodeIds: string[];
  nodeIds: string[];
  edgeIds: string[];
  issues: MappingGraphIssue[];
};

export type MappingChain = {
  receiverFieldId: string | null;
  receiverEdgeId: string | null;
  senderNormalizedTypes: { fieldId: string; type: NormalizedType }[];
  receiverNormalizedType: NormalizedType | null;
  inputs: MappingChainInput[];
  transformationNodeIds: string[];
  transformations: MappingGraphTransformation[];
  nodeIds: string[];
  edgeIds: string[];
  issues: MappingGraphIssue[];
  validation: TypeValidationResult | null;
};

type TraceResult = {
  inputs: MappingChainInput[];
  issues: MappingGraphIssue[];
};

function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}

function cloneConfig(config: Record<string, unknown>): Record<string, unknown> {
  function clone(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(clone);
    if (value !== null && typeof value === "object") {
      const entries = Object.entries(value).map(([key, nested]) => [key, clone(nested)] as const);
      return Object.fromEntries(entries);
    }
    return value;
  }
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(config)) result[key] = clone(value);
  return result;
}

function issue(
  code: MappingGraphIssueCode,
  message: string,
  options: {
    severity?: MappingGraphIssue["severity"];
    nodeIds?: string[];
    edgeIds?: string[];
    senderFieldIds?: string[];
    receiverFieldIds?: string[];
  } = {},
): MappingGraphIssue {
  return {
    code,
    severity: options.severity ?? "Error",
    message,
    nodeIds: unique(options.nodeIds ?? []),
    edgeIds: unique(options.edgeIds ?? []),
    senderFieldIds: unique(options.senderFieldIds ?? []),
    receiverFieldIds: unique(options.receiverFieldIds ?? []),
  };
}

function combineIssues(...groups: MappingGraphIssue[][]): MappingGraphIssue[] {
  const result: MappingGraphIssue[] = [];
  const seen = new Set<string>();
  for (const item of groups.flat()) {
    const key = `${item.code}:${item.nodeIds.join(",")}:${item.edgeIds.join(",")}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

function includeEdges(
  issues: MappingGraphIssue[],
  edgeIds: string[],
): MappingGraphIssue[] {
  return issues.map((item) => ({
    ...item,
    edgeIds: unique([...item.edgeIds, ...edgeIds]),
  }));
}

export function fieldIdFromPort(portId: string | null | undefined): string | null {
  if (!portId?.startsWith("field:")) return null;
  const fieldId = portId.slice("field:".length);
  return fieldId.length > 0 ? fieldId : null;
}

function functionDisplayName(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "Function";
  const functionName = value.trim();
  const normalized = functionName.toLowerCase().replace(/[_\-\s]+/g, "");
  if (normalized === "tostring") return "Convert to text";
  if (normalized === "toint" || normalized === "tointeger") return "Convert to integer";
  if (normalized === "tonumber") return "Convert to number";
  if (normalized === "toboolean") return "Convert to boolean";
  if (normalized === "parsedate") return "Parse date";
  if (normalized === "formatdate") return "Format date";
  return functionName;
}

export function transformationLabel(
  type: string,
  config: Record<string, unknown> = {},
): string {
  if (type === "fx") return functionDisplayName(config.function);
  if (type === "source") return "Source";
  if (type === "target") return "Target";
  if (type === "constant") return "Constant";
  if (type === "concat") return "Concatenate";
  if (type === "ifelse") return "If / else";
  if (type === "map") return "Map";
  if (type === "coalesce") return "Coalesce";
  if (type === "lookup") return "Lookup";
  if (type === "filter") return "Filter";
  if (type === "validate") return "Validate";
  return type;
}

export function transformationSummary(
  transformations: readonly MappingGraphTransformation[],
): string {
  return transformations.length
    ? transformations.map((transform) => transform.label).join(" → ")
    : "Direct";
}

function orderTransformations(
  nodeIds: string[],
  nodesById: Map<string, MappingGraphNode>,
  incoming: Map<string, MappingGraphEdge[]>,
): MappingGraphTransformation[] {
  const included = new Set(nodeIds);
  const ordered: MappingGraphTransformation[] = [];
  const visited = new Set<string>();
  const visiting = new Set<string>();

  function visit(nodeId: string): void {
    if (!included.has(nodeId) || visited.has(nodeId) || visiting.has(nodeId)) return;
    visiting.add(nodeId);
    for (const edge of incoming.get(nodeId) ?? []) {
      const predecessor = nodesById.get(edge.sourceNodeId);
      if (predecessor && predecessor.type !== "source" && predecessor.type !== "target") {
        visit(predecessor.id);
      }
    }
    visiting.delete(nodeId);
    visited.add(nodeId);
    const node = nodesById.get(nodeId);
    if (node && node.type !== "source" && node.type !== "target") {
      ordered.push({
        nodeId: node.id,
        nodeType: node.type,
        config: cloneConfig(node.config),
        label: transformationLabel(node.type, node.config),
      });
    }
  }

  for (const nodeId of nodeIds) visit(nodeId);
  return ordered;
}

export function validateMappingChain(input: {
  chain: MappingChain;
  senderFields: readonly MappingGraphField[];
  receiverFields: readonly MappingGraphField[];
}): TypeValidationResult | null {
  const { chain, senderFields, receiverFields } = input;
  if (chain.inputs.length !== 1 || chain.issues.length > 0) return null;
  const senderId = chain.inputs[0]?.senderFieldId;
  const sender = senderFields.find((field) => field.id === senderId);
  const receiver = receiverFields.find((field) => field.id === chain.receiverFieldId);
  if (!sender || !receiver) return null;

  const transformations: TransformationForValidation[] = chain.transformations.map((item) => ({
    nodeType: item.nodeType,
    label: item.label,
    config: item.config,
  }));
  return validateTypeChain({
    senderType: sender.data_type,
    transformations,
    receiverType: receiver.data_type,
    receiverNullable: receiver.nullable || !receiver.required,
  });
}

export function deriveMappingChains(input: {
  graph: MappingGraphDocument;
  senderFields: readonly MappingGraphField[];
  receiverFields: readonly MappingGraphField[];
}): MappingChain[] {
  const { graph, senderFields, receiverFields } = input;
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, MappingGraphEdge[]>();
  const outgoing = new Map<string, MappingGraphEdge[]>();
  for (const edge of graph.edges) {
    incoming.set(edge.targetNodeId, [...(incoming.get(edge.targetNodeId) ?? []), edge]);
    outgoing.set(edge.sourceNodeId, [...(outgoing.get(edge.sourceNodeId) ?? []), edge]);
  }
  const sourceNode = graph.nodes.find((node) => node.type === "source");
  const targetNode = graph.nodes.find((node) => node.type === "target");
  const senderFieldsById = new Map(senderFields.map((field) => [field.id, field]));
  const receiverFieldsById = new Map(receiverFields.map((field) => [field.id, field]));
  const chains: MappingChain[] = [];
  const claimedNodeIds = new Set<string>();
  const claimedEdgeIds = new Set<string>();

  function traceOutput(
    nodeId: string,
    sourcePortId: string,
    pathNodeIds: Set<string>,
  ): TraceResult {
    const node = nodesById.get(nodeId);
    if (!node) {
      const senderFieldId = fieldIdFromPort(sourcePortId);
      const missingTransformation = sourcePortId === "output";
      return {
        inputs: [{
          senderFieldId,
          transformationNodeIds: [],
          nodeIds: [nodeId],
          edgeIds: [],
          issues: [issue(
            missingTransformation ? "missing_transformation_node" : "missing_graph_node",
            missingTransformation
              ? "Mapping chain references a missing transformation node."
              : "Mapping chain references a missing node.",
            {
              nodeIds: [nodeId],
              senderFieldIds: senderFieldId ? [senderFieldId] : [],
            },
          )],
        }],
        issues: [],
      };
    }
    if (pathNodeIds.has(nodeId)) {
      const cycleIssue = issue("cycle", "Cycle detected in mapping chain.", {
        nodeIds: [...pathNodeIds, nodeId],
      });
      return {
        inputs: [{
          senderFieldId: null,
          transformationNodeIds: [],
          nodeIds: [...pathNodeIds, nodeId],
          edgeIds: [],
          issues: [cycleIssue],
        }],
        issues: [cycleIssue],
      };
    }
    const nextPath = new Set(pathNodeIds).add(nodeId);
    claimedNodeIds.add(nodeId);

    if (node.type === "source") {
      const senderFieldId = fieldIdFromPort(sourcePortId);
      if (senderFieldId === null) {
        const sourceIssue = issue("invalid_source_port", "Sender field handle is missing.", {
          nodeIds: [nodeId],
        });
        return {
          inputs: [{
            senderFieldId: null,
            transformationNodeIds: [],
            nodeIds: [nodeId],
            edgeIds: [],
            issues: [sourceIssue],
          }],
          issues: [],
        };
      }
      if (!senderFieldsById.has(senderFieldId)) {
        const missingFieldIssue = issue(
          "missing_source_field",
          "Sender field no longer exists in the active schema.",
          { nodeIds: [nodeId], senderFieldIds: [senderFieldId] },
        );
        return {
          inputs: [{
            senderFieldId,
            transformationNodeIds: [],
            nodeIds: [nodeId],
            edgeIds: [],
            issues: [missingFieldIssue],
          }],
          issues: [],
        };
      }
      return {
        inputs: [{
          senderFieldId,
          transformationNodeIds: [],
          nodeIds: [nodeId],
          edgeIds: [],
          issues: [],
        }],
        issues: [],
      };
    }

    if (node.type === "target") {
      const targetIssue = issue(
        "receiver_cannot_produce",
        "Receiver node cannot produce mappings.",
        { nodeIds: [nodeId] },
      );
      return {
        inputs: [{
          senderFieldId: null,
          transformationNodeIds: [],
          nodeIds: [nodeId],
          edgeIds: [],
          issues: [targetIssue],
        }],
        issues: [],
      };
    }

    const outputIssues = sourcePortId === "output"
      ? []
      : [issue(
        "invalid_transformation_output_port",
        "Transformation output handle is invalid.",
        { nodeIds: [nodeId] },
      )];
    const edges = incoming.get(nodeId) ?? [];
    if (edges.length === 0) {
      const inputIssue = issue(
        "missing_transformation_input",
        "Transformation has no input connection.",
        { nodeIds: [nodeId] },
      );
      return {
        inputs: [{
          senderFieldId: null,
          transformationNodeIds: [nodeId],
          nodeIds: [nodeId],
          edgeIds: [],
          issues: [...outputIssues, inputIssue],
        }],
        issues: [],
      };
    }

    const tracedInputs = edges.map((edge) => {
      claimedEdgeIds.add(edge.id);
      const trace = traceOutput(edge.sourceNodeId, edge.sourcePortId, nextPath);
      const edgeIssues = edge.targetPortId === "input"
        ? []
        : [issue(
          "invalid_transformation_input_port",
          "Transformation input handle is invalid.",
          {
            nodeIds: [nodeId],
            edgeIds: [edge.id],
            senderFieldIds: trace.inputs.flatMap((item) =>
              item.senderFieldId ? [item.senderFieldId] : []),
          },
        )];
      const transformIssues = [...outputIssues, ...edgeIssues];
      return {
        inputs: trace.inputs.map((item) => ({
          ...item,
          transformationNodeIds: [...item.transformationNodeIds, nodeId],
          nodeIds: unique([...item.nodeIds, nodeId]),
          edgeIds: unique([...item.edgeIds, edge.id]),
          issues: combineIssues(
            includeEdges(item.issues, [edge.id]),
            transformIssues,
          ),
        })),
        issues: trace.issues,
      };
    });
    return {
      inputs: tracedInputs.flatMap((result) => result.inputs),
      issues: combineIssues(...tracedInputs.map((result) => result.issues)),
    };
  }

  function makeChain(
    receiverFieldId: string | null,
    receiverEdgeId: string | null,
    inputsForChain: MappingChainInput[],
    initialIssues: MappingGraphIssue[] = [],
    extraNodeIds: string[] = [],
    extraEdgeIds: string[] = [],
  ): MappingChain {
    const inputIssues = inputsForChain.flatMap((item) => item.issues);
    const fanInIssue = inputsForChain.length > 1
      ? [issue(
        "multiple_inputs_need_review",
        "Transformation has multiple inputs and needs visual review.",
        {
          severity: "Warning",
          nodeIds: inputsForChain.flatMap((item) => item.transformationNodeIds),
          edgeIds: inputsForChain.flatMap((item) => item.edgeIds),
          senderFieldIds: inputsForChain.flatMap((item) =>
            item.senderFieldId ? [item.senderFieldId] : []),
          receiverFieldIds: receiverFieldId ? [receiverFieldId] : [],
        },
      )]
      : [];
    const issues = combineIssues(initialIssues, inputIssues, fanInIssue);
    const transformationNodeIds = unique([
      ...inputsForChain.flatMap((item) => item.transformationNodeIds),
      ...extraNodeIds.filter((nodeId) => {
        const node = nodesById.get(nodeId);
        return Boolean(node && node.type !== "source" && node.type !== "target");
      }),
    ]);
    const transformations = orderTransformations(transformationNodeIds, nodesById, incoming);
    const nodeIds = unique([
      ...inputsForChain.flatMap((item) => item.nodeIds),
      ...extraNodeIds,
    ]);
    const edgeIds = unique([
      ...inputsForChain.flatMap((item) => item.edgeIds),
      ...extraEdgeIds,
    ]);
    const chain: MappingChain = {
      receiverFieldId,
      receiverEdgeId,
      senderNormalizedTypes: unique(inputsForChain.flatMap((item) =>
        item.senderFieldId ? [item.senderFieldId] : []))
        .flatMap((fieldId) => {
          const sender = senderFieldsById.get(fieldId);
          return sender ? [{ fieldId, type: normalizeSchemaType(sender.data_type) }] : [];
        }),
      receiverNormalizedType: receiverFieldId && receiverFieldsById.has(receiverFieldId)
        ? normalizeSchemaType(receiverFieldsById.get(receiverFieldId)?.data_type)
        : null,
      inputs: inputsForChain,
      transformationNodeIds,
      transformations,
      nodeIds,
      edgeIds,
      issues,
      validation: null,
    };
    chain.validation = validateMappingChain({ chain, senderFields, receiverFields });
    return chain;
  }

  if (targetNode) {
    for (const edge of incoming.get(targetNode.id) ?? []) {
      claimedEdgeIds.add(edge.id);
      const receiverFieldId = fieldIdFromPort(edge.targetPortId);
      const edgeIssues: MappingGraphIssue[] = [];
      if (receiverFieldId === null) {
        edgeIssues.push(issue(
          "invalid_receiver_port",
          "Receiver field handle is missing.",
          { nodeIds: [targetNode.id], edgeIds: [edge.id] },
        ));
      } else if (!receiverFieldsById.has(receiverFieldId)) {
        edgeIssues.push(issue(
          "missing_receiver_field",
          "Receiver field no longer exists in the active schema.",
          {
            nodeIds: [targetNode.id],
            edgeIds: [edge.id],
            receiverFieldIds: [receiverFieldId],
          },
        ));
      }
      const traced = traceOutput(edge.sourceNodeId, edge.sourcePortId, new Set([targetNode.id]));
      const inputsForChain = traced.inputs.map((item) => ({
        ...item,
        nodeIds: unique([...item.nodeIds, targetNode.id]),
        edgeIds: unique([...item.edgeIds, edge.id]),
        issues: includeEdges(item.issues, [edge.id]),
      }));
      chains.push(makeChain(
        receiverFieldId,
        edge.id,
        inputsForChain,
        [...edgeIssues, ...traced.issues],
        [targetNode.id],
        [edge.id],
      ));
      claimedNodeIds.add(targetNode.id);
    }
  }

  for (const edge of graph.edges) {
    if (claimedEdgeIds.has(edge.id)) continue;
    const source = nodesById.get(edge.sourceNodeId);
    const target = nodesById.get(edge.targetNodeId);
    if (source && target) continue;
    const senderFieldId = source?.type === "source" ? fieldIdFromPort(edge.sourcePortId) : null;
    const receiverFieldId = target?.type === "target" || !target
      ? fieldIdFromPort(edge.targetPortId)
      : null;
    const missingNodeId = !source ? edge.sourceNodeId : edge.targetNodeId;
    const inferredTransformation = (!source && edge.sourcePortId === "output")
      || (!target && edge.targetPortId === "input");
    const missingNodeIssueCode = inferredTransformation
      ? "missing_transformation_node"
      : "missing_graph_node";
    const missingIssue = issue(
      missingNodeIssueCode,
      inferredTransformation
        ? "Mapping chain references a missing transformation node."
        : "Mapping chain references a missing node.",
      {
        nodeIds: [missingNodeId],
        edgeIds: [edge.id],
        senderFieldIds: senderFieldId ? [senderFieldId] : [],
        receiverFieldIds: receiverFieldId ? [receiverFieldId] : [],
      },
    );
    const traced = source
      ? traceOutput(source.id, edge.sourcePortId, new Set())
      : null;
    const inputsForMissingNode = traced
      ? traced.inputs.map((item) => ({
        ...item,
        nodeIds: unique([...item.nodeIds, missingNodeId]),
        edgeIds: unique([...item.edgeIds, edge.id]),
        issues: combineIssues(
          includeEdges(item.issues, [edge.id]),
          [missingIssue],
        ),
      }))
      : senderFieldId
        ? [{
          senderFieldId,
          transformationNodeIds: [],
          nodeIds: [missingNodeId],
          edgeIds: [edge.id],
          issues: [missingIssue],
        }]
        : [];
    chains.push(makeChain(
      receiverFieldId,
      target?.type === "target" ? edge.id : null,
      inputsForMissingNode,
      [...(traced?.issues ?? []), missingIssue],
      [missingNodeId, ...(source ? [source.id] : []), ...(target ? [target.id] : [])],
      [edge.id],
    ));
    claimedEdgeIds.add(edge.id);
  }

  for (const node of graph.nodes) {
    if (node.type === "source" || node.type === "target" || claimedNodeIds.has(node.id)) continue;
    const componentNodeIds = new Set<string>();
    const componentEdgeIds = new Set<string>();
    const senderFieldIds = new Set<string>();
    const receiverFieldIds = new Set<string>();
    const pending = [node.id];
    while (pending.length) {
      const current = pending.pop()!;
      if (componentNodeIds.has(current)) continue;
      componentNodeIds.add(current);
      for (const edge of [...(incoming.get(current) ?? []), ...(outgoing.get(current) ?? [])]) {
        componentEdgeIds.add(edge.id);
        const predecessor = nodesById.get(edge.sourceNodeId);
        const successor = nodesById.get(edge.targetNodeId);
        const incomingFieldId = fieldIdFromPort(edge.sourcePortId);
        const outgoingFieldId = fieldIdFromPort(edge.targetPortId);
        if (predecessor?.type === "source" || (!predecessor && incomingFieldId)) {
          const fieldId = incomingFieldId;
          if (fieldId) senderFieldIds.add(fieldId);
        } else if (predecessor && predecessor.type !== "target") {
          pending.push(predecessor.id);
        }
        if (successor?.type === "target" || (!successor && outgoingFieldId)) {
          const fieldId = outgoingFieldId;
          if (fieldId) receiverFieldIds.add(fieldId);
        } else if (successor && successor.type !== "source") {
          pending.push(successor.id);
        }
      }
    }
    const disconnectedIssue = issue(
      "disconnected_transformation",
      "Transformation is not connected to a complete sender-to-receiver mapping.",
      {
        nodeIds: [...componentNodeIds],
        edgeIds: [...componentEdgeIds],
        senderFieldIds: [...senderFieldIds],
        receiverFieldIds: [...receiverFieldIds],
      },
    );
    const inputsForChain = [...senderFieldIds].map((senderFieldId) => ({
      senderFieldId,
      transformationNodeIds: orderTransformations([...componentNodeIds], nodesById, incoming)
        .map((transform) => transform.nodeId),
      nodeIds: [...componentNodeIds],
      edgeIds: [...componentEdgeIds],
      issues: [disconnectedIssue],
    }));
    chains.push(makeChain(
      [...receiverFieldIds][0] ?? null,
      null,
      inputsForChain,
      [disconnectedIssue],
      [...componentNodeIds],
      [...componentEdgeIds],
    ));
    for (const componentNodeId of componentNodeIds) claimedNodeIds.add(componentNodeId);
    for (const componentEdgeId of componentEdgeIds) claimedEdgeIds.add(componentEdgeId);
  }

  for (const edge of graph.edges) {
    if (claimedEdgeIds.has(edge.id)) continue;
    const sourceNode = nodesById.get(edge.sourceNodeId);
    const targetNodeForEdge = nodesById.get(edge.targetNodeId);
    if (sourceNode?.type === "source" && targetNodeForEdge?.type === "target") {
      const senderFieldId = fieldIdFromPort(edge.sourcePortId);
      const receiverFieldId = fieldIdFromPort(edge.targetPortId);
      const directIssues: MappingGraphIssue[] = [];
      if (!senderFieldId) directIssues.push(issue(
        "invalid_source_port",
        "Sender field handle is missing.",
        { nodeIds: [sourceNode.id], edgeIds: [edge.id] },
      ));
      else if (!senderFieldsById.has(senderFieldId)) directIssues.push(issue(
        "missing_source_field",
        "Sender field no longer exists in the active schema.",
        { nodeIds: [sourceNode.id], edgeIds: [edge.id], senderFieldIds: [senderFieldId] },
      ));
      if (!receiverFieldId) directIssues.push(issue(
        "invalid_receiver_port",
        "Receiver field handle is missing.",
        { nodeIds: [targetNodeForEdge.id], edgeIds: [edge.id] },
      ));
      else if (!receiverFieldsById.has(receiverFieldId)) directIssues.push(issue(
        "missing_receiver_field",
        "Receiver field no longer exists in the active schema.",
        {
          nodeIds: [targetNodeForEdge.id],
          edgeIds: [edge.id],
          receiverFieldIds: [receiverFieldId],
        },
      ));
      if (senderFieldId && receiverFieldId) {
        chains.push(makeChain(
          receiverFieldId,
          edge.id,
          [{
            senderFieldId,
            transformationNodeIds: [],
            nodeIds: [sourceNode.id, targetNodeForEdge.id],
            edgeIds: [edge.id],
            issues: directIssues,
          }],
          directIssues,
          [sourceNode.id, targetNodeForEdge.id],
          [edge.id],
        ));
      }
      claimedEdgeIds.add(edge.id);
    }
  }

  return chains;
}
