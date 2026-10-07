import React from "react";
import type { GraphDocument, GraphNodeDocument, GraphNodeType } from "./contractGraphTypes";
import ContractCsvDialog from "./components/ContractCsvDialog";
import { downloadCsv, templateMappingCsv } from "./contractMappingCsv";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type EdgeTypes,
  type Node,
  type NodeChange,
  type NodeProps,
  type NodeTypes,
  type ReactFlowInstance,
} from "@xyflow/react";
import MapperEdge from "./components/mapper/MapperEdge";
import ScenarioWorkspace from "./components/scenarios/ScenarioWorkspace";
import { designStatusLabel, designValidationReason } from "./designLabels";
import {
  normalizeSchemaType,
  validateTypeChain,
  type TypeValidationResult,
} from "./mappingTypeValidation";
import {
  deriveMappingChains,
  transformationLabel,
  transformationSummary,
} from "./mappingGraphModel";
import {
  isArchitectureResponsePhase,
  isSharedResponseGraphPhase,
} from "./enterpriseArchitectureIndex";

type System = { id: string; name: string; kind: string };
type CatalogObject = { id: string; system_id: string; name: string; label: string };
type CatalogField = {
  id: string;
  object_id: string;
  name: string;
  label: string;
  data_type: string;
  required: boolean;
  nullable: boolean;
  default_value: unknown;
  position: number;
};
type InteractionType = "ONE_WAY" | "REQUEST_RESPONSE" | "ASYNC_CALLBACK";
type ContractView = "overview" | "request" | "success-response" | "error-response" | "async-response";
type MappingPhase = "request" | "success-response" | "error-response" | "async-response";
type Integration = {
  id: string;
  source_system_id: string;
  source_object_id: string;
  target_system_id: string;
  target_object_id: string;
  name: string;
  graph: GraphDocument;
  response_graph: GraphDocument;
  error_response_graph?: GraphDocument;
  error_response_object_id?: string | null;
  interaction_type: InteractionType;
  sample_rows: SimulationRowInput[];
  revision: number;
};
type SimulationRowInput = { rowId: string; values: Record<string, unknown> };
type TraceEntry = {
  nodeId: string;
  nodeType: GraphNodeType;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  outcome: string;
  errorCode?: string | null;
};
type SimulationRow = {
  rowId: string;
  rowIndex: number;
  outcome: "ok" | "skipped" | "failed";
  targetValues: Record<string, unknown>;
  errors: { code: string; rowId: string; rowIndex: number; nodeId: string | null; message: string; recovered: boolean }[];
  trace: TraceEntry[];
  traceTruncated: boolean;
};
type SimulationResult = {
  integrationId: string;
  revision: number;
  summary: { total: number; ok: number; skipped: number; failed: number };
  rows: SimulationRow[];
  traceTruncated: boolean;
  requestOutcomes: SimulationRow[];
  responseOutcomes: SimulationRow[];
  responseSummary: { total: number; ok: number; skipped: number; failed: number };
  responseTraceTruncated: boolean;
};
type ArchitectureAnalysis = {
  integrations: {
    id: string;
    name: string;
    status: "draft" | "attention" | "healthy";
    reasons: string[];
    target_mapping_count: number;
    conflict_fields: {
      object_id: string;
      object_label: string;
      field_id: string;
      field_label: string;
    }[];
    upstream: { id: string; name: string; status: "draft" | "attention" | "healthy" }[];
  }[];
  conflicts: {
    object_id: string;
    object_label: string;
    field_id: string;
    field_label: string;
    integrations: { id: string; name: string; status: "attention" }[];
  }[];
};
type NodeData = {
  label: string;
  fields?: CatalogField[];
  config: Record<string, unknown>;
  evaluation?: string;
  direction?: "outbound" | "inbound";
  phase?: ContractView;
  onAddField?: (endpoint: "source" | "target") => void;
  onEditField?: (endpoint: "source" | "target", field: CatalogField) => void;
  onDeleteField?: (endpoint: "source" | "target", field: CatalogField) => void;
  onRemove?: (id: string) => void;
};
export type FlowNode = Node<NodeData, GraphNodeType>;
export type FlowEdge = Edge<{
  direction?: "outbound" | "inbound";
  routeOffset?: number;
  phase?: ContractView;
  validationStatus?: MappingMatrixStatus;
  validationIssue?: string;
  onIssueHover?: (active: boolean) => void;
  onIssueSelect?: () => void;
}>;
type ConnectionAssist = {
  connection: Connection;
  sourceField: CatalogField;
  targetField: CatalogField;
  suggestedFunction: "toInt" | "toNumber" | "toString" | "toBoolean" | "parseDate" | "formatDate";
  position: { x: number; y: number };
};
type MappingWorkbenchView = "canvas" | "matrix";
type MappingMatrixFilter = "all" | "mapped" | "unmapped" | "issues";
export type MappingMatrixStatus = "Valid" | "Warning" | "Error" | "Unmapped";
export type MappingMatrixRow = {
  id: string;
  senderFieldId: string | null;
  senderFieldLabel: string;
  senderFieldName: string;
  senderType: string;
  transformation: string;
  receiverFieldId: string | null;
  receiverFieldLabel: string;
  receiverFieldName: string;
  receiverType: string;
  status: MappingMatrixStatus;
  issue: string;
  senderNormalizedType: string;
  receiverNormalizedType: string;
  outputNormalizedType: string;
  typeProgression: string[];
  lossy: boolean;
  transformationNodeIds: string[];
  primaryIssueEdgeId: string | null;
  suggestedFix?: {
    kind: "replace-function";
    nodeId: string;
    from: string;
    to: string;
    fromLabel: string;
    toLabel: string;
    buttonLabel: string;
  };
  graphNodeIds: string[];
  graphEdgeIds: string[];
};

type Props = {
  onBack: () => void;
  initialIntegrationId?: string;
  /** Phase tab (or the Scenarios tab) to show once the initial contract has loaded. */
  initialContractView?: ContractView | "scenarios";
  newIntegrationSystemId?: string;
};

const TRANSFORM_TYPES: GraphNodeType[] = [
  "constant",
  "fx",
  "concat",
  "ifelse",
  "map",
  "coalesce",
  "lookup",
  "filter",
  "validate",
];

const DEFAULT_CONFIG: Record<GraphNodeType, Record<string, unknown>> = {
  source: {},
  target: {},
  constant: { value: "" },
  fx: { function: "trim", errorPolicy: "fail" },
  concat: { separator: "", errorPolicy: "fail" },
  ifelse: { errorPolicy: "fail" },
  map: { mapping: {}, errorPolicy: "fail" },
  coalesce: { errorPolicy: "fail" },
  lookup: { table: {}, errorPolicy: "fail" },
  filter: { errorPolicy: "fail" },
  validate: { rules: { required: true }, errorPolicy: "fail" },
};

const NODE_LABELS: Record<GraphNodeType, string> = {
  source: "Source",
  target: "Target",
  constant: "Constant",
  fx: "Function",
  concat: "Concatenate",
  ifelse: "If / else",
  map: "Map",
  coalesce: "Coalesce",
  lookup: "Lookup",
  filter: "Filter",
  validate: "Validate",
};

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ID_NAMESPACES = [
  "request:",
  "response:",
  "success-response:",
  "error-response:",
  "async-response:",
];
const RESPONSE_ID_NAMESPACES = ["response:", "success-response:", "error-response:", "async-response:"];

function isResponsePhase(view: ContractView): view is MappingPhase {
  return isArchitectureResponsePhase(view);
}

function usesSuccessResponseGraph(view: ContractView): boolean {
  return isSharedResponseGraphPhase(view);
}

function isErrorResponsePhase(view: ContractView): boolean {
  return view === "error-response";
}

export function normalizeUuidForApi(value: string): string {
  if (UUID_PATTERN.test(value)) return value;
  for (const prefix of ID_NAMESPACES) {
    if (!value.startsWith(prefix)) continue;
    const remainder = value.slice(prefix.length);
    if (UUID_PATTERN.test(remainder)) return remainder;
  }
  return value;
}

function isResponseNamespacedId(value: string): boolean {
  return RESPONSE_ID_NAMESPACES.some((prefix) => value.startsWith(prefix));
}

function isRequestNamespacedId(value: string): boolean {
  return value.startsWith("request:");
}

export function sanitizeCanvasFlowForPhase(
  phase: ContractView,
  flow: { nodes: FlowNode[]; edges: FlowEdge[] },
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  if (phase === "overview") return flow;
  const allowNode = (id: string) => {
    if (phase === "request") return !isResponseNamespacedId(id);
    return !isRequestNamespacedId(id);
  };
  const nodes = flow.nodes.filter((node) => allowNode(node.id));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = flow.edges.filter((edge) =>
    allowNode(edge.source)
    && allowNode(edge.target)
    && nodeIds.has(edge.source)
    && nodeIds.has(edge.target),
  );
  return { nodes, edges };
}

export function computePhaseGraphsForSave(input: {
  contractView: ContractView;
  nodes: FlowNode[];
  edges: FlowEdge[];
  requestGraphDraft: GraphDocument;
  responseGraphDraft: GraphDocument;
  errorResponseGraphDraft: GraphDocument;
  phaseEdited: Record<MappingPhase, boolean>;
}): { request: GraphDocument; response: GraphDocument; errorResponse: GraphDocument } {
  const { contractView, nodes, edges, requestGraphDraft, responseGraphDraft, errorResponseGraphDraft, phaseEdited } = input;
  const phaseFlow = sanitizeCanvasFlowForPhase(contractView, { nodes, edges });
  const activeGraph = graphFromFlow(phaseFlow.nodes, phaseFlow.edges);
  return {
    request: contractView === "request" && phaseEdited.request ? activeGraph : requestGraphDraft,
    response: usesSuccessResponseGraph(contractView)
      && (phaseEdited["success-response"] || phaseEdited["async-response"])
      ? activeGraph
      : responseGraphDraft,
    errorResponse: contractView === "error-response" && phaseEdited["error-response"]
      ? activeGraph
      : errorResponseGraphDraft,
  };
}

export function pruneSelectionForActiveFlow(
  selectedNodeId: string,
  selectedEdgeId: string,
  nodes: FlowNode[],
  edges: FlowEdge[],
): { nodeId: string; edgeId: string } {
  const nodeId = selectedNodeId && nodes.some((node) => node.id === selectedNodeId) ? selectedNodeId : "";
  const edgeId = selectedEdgeId && edges.some((edge) => edge.id === selectedEdgeId) ? selectedEdgeId : "";
  return { nodeId, edgeId };
}

function mappingSuggestion(input: {
  senderNormalizedType: string;
  receiverNormalizedType: string;
  transformationNodes: FlowNode[];
  status: MappingMatrixStatus;
  lossy: boolean;
}): MappingMatrixRow["suggestedFix"] | undefined {
  const { senderNormalizedType, receiverNormalizedType, transformationNodes, status, lossy } = input;
  if (status !== "Error" || lossy) return undefined;
  if (senderNormalizedType !== "string" || receiverNormalizedType !== "integer") return undefined;
  if (transformationNodes.length !== 1) return undefined;
  const node = transformationNodes[0]!;
  if (node.type !== "fx") return undefined;
  const fn = String(node.data.config.function ?? "").trim().toLowerCase();
  if (fn !== "tostring") return undefined;
  return {
    kind: "replace-function",
    nodeId: node.id,
    from: "toString",
    to: "toInt",
    fromLabel: "Convert to text",
    toLabel: "Convert to integer",
    buttonLabel: "Apply suggested fix",
  };
}

export function deriveMappingMatrixRows(input: {
  nodes: FlowNode[];
  edges: FlowEdge[];
  senderFields: CatalogField[];
  receiverFields: CatalogField[];
}): MappingMatrixRow[] {
  const { nodes, edges, senderFields, receiverFields } = input;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const senderById = new Map(senderFields.map((field) => [field.id, field]));
  const sourceNode = nodes.find((node) => node.type === "source");
  const targetNode = nodes.find((node) => node.type === "target");
  const rows: MappingMatrixRow[] = [];
  const mappedSenderIds = new Set<string>();
  if (!sourceNode || !targetNode) return rows;
  const chains = deriveMappingChains({
    graph: {
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        config: node.data.config,
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        sourceNodeId: edge.source,
        sourcePortId: edge.sourceHandle ?? "",
        targetNodeId: edge.target,
        targetPortId: edge.targetHandle ?? "",
      })),
    },
    senderFields,
    receiverFields,
  });
  const chainByReceiverEdgeId = new Map(
    chains.flatMap((chain) => chain.receiverEdgeId
      ? [[chain.receiverEdgeId, chain] as const]
      : []),
  );

  for (const receiverField of receiverFields) {
    const incoming = edges.filter((edge) =>
      edge.target === targetNode.id && edge.targetHandle === `field:${receiverField.id}`,
    );
    if (incoming.length === 0) {
      const required = receiverField.required && !receiverField.nullable;
      rows.push({
        id: `receiver-unmapped:${receiverField.id}`,
        senderFieldId: null,
        senderFieldLabel: "—",
        senderFieldName: "",
        senderType: "—",
        transformation: "Unmapped",
        receiverFieldId: receiverField.id,
        receiverFieldLabel: receiverField.label,
        receiverFieldName: receiverField.name,
        receiverType: receiverField.data_type,
        status: required ? "Error" : "Unmapped",
        issue: required ? "Required receiver field is unmapped." : "Receiver field is unmapped.",
        senderNormalizedType: "unknown",
        receiverNormalizedType: normalizeSchemaType(receiverField.data_type),
        outputNormalizedType: "unknown",
        typeProgression: [],
        lossy: false,
        transformationNodeIds: [],
        primaryIssueEdgeId: null,
        graphNodeIds: [targetNode.id],
        graphEdgeIds: [],
      });
      continue;
    }

    for (const edge of incoming) {
      const chain = chainByReceiverEdgeId.get(edge.id);
      const primaryInput = chain?.inputs[0];
      const transformationNodes = (primaryInput?.transformationNodeIds ?? [])
        .map((nodeId) => nodeById.get(nodeId))
        .filter((node): node is FlowNode => node !== undefined);
      const primaryIssueCode = primaryInput?.issues[0]?.code;
      const primaryIssue = primaryIssueCode === "missing_transformation_node"
        ? "Mapping chain references a missing node."
        : primaryInput?.issues[0]?.message ?? "";
      const multiInputIssue = chain && chain.inputs.length > 1
        ? "Transformation has multiple inputs and needs visual review."
        : "";
      const trace = {
        senderFieldId: primaryInput?.senderFieldId ?? null,
        transformationNodes,
        issue: primaryIssue || multiInputIssue,
        graphNodeIds: new Set([targetNode.id, ...(primaryInput?.nodeIds ?? [])]),
        graphEdgeIds: new Set([edge.id, ...(primaryInput?.edgeIds ?? [])]),
      };
      if (trace.senderFieldId) mappedSenderIds.add(trace.senderFieldId);
      const senderField = trace.senderFieldId ? senderById.get(trace.senderFieldId) : undefined;
      const validation: TypeValidationResult = trace.issue
        ? { status: "Error", issue: trace.issue, outputType: "unknown", steps: [], lossy: false }
        : chain?.validation ?? validateTypeChain({
          senderType: senderField?.data_type,
          transformations: trace.transformationNodes.map((node) => ({
            nodeType: node.type,
            label: transformationLabel(node.type, node.data.config),
            config: node.data.config,
          })),
          receiverType: receiverField.data_type,
          receiverNullable: receiverField.nullable || !receiverField.required,
        });
      const senderNormalizedType = normalizeSchemaType(senderField?.data_type);
      const receiverNormalizedType = normalizeSchemaType(receiverField.data_type);
      const progression = [
        senderNormalizedType,
        ...validation.steps.map((step) => `${step.label}: ${step.output}`),
        `expected ${receiverNormalizedType}`,
      ];
      rows.push({
        id: `mapping:${edge.id}`,
        senderFieldId: trace.senderFieldId,
        senderFieldLabel: senderField?.label ?? "—",
        senderFieldName: senderField?.name ?? "",
        senderType: senderField?.data_type ?? "—",
        transformation: transformationSummary(trace.transformationNodes.map((node) => ({
          nodeId: node.id,
          nodeType: node.type,
          config: node.data.config,
          label: transformationLabel(node.type, node.data.config),
        }))),
        receiverFieldId: receiverField.id,
        receiverFieldLabel: receiverField.label,
        receiverFieldName: receiverField.name,
        receiverType: receiverField.data_type,
        status: validation.status,
        issue: validation.issue,
        senderNormalizedType,
        receiverNormalizedType,
        outputNormalizedType: validation.outputType,
        typeProgression: progression,
        lossy: validation.lossy,
        transformationNodeIds: trace.transformationNodes.map((node) => node.id),
        primaryIssueEdgeId: edge.id,
        suggestedFix: mappingSuggestion({
          senderNormalizedType,
          receiverNormalizedType,
          transformationNodes: trace.transformationNodes,
          status: validation.status,
          lossy: validation.lossy,
        }),
        graphNodeIds: [...trace.graphNodeIds],
        graphEdgeIds: [...trace.graphEdgeIds],
      });
    }
  }

  const optionalUnmappedSenders = senderFields.filter((field) =>
    (!field.required || field.nullable) && !mappedSenderIds.has(field.id),
  );
  for (const senderField of optionalUnmappedSenders) {
    rows.push({
      id: `sender-unmapped:${senderField.id}`,
      senderFieldId: senderField.id,
      senderFieldLabel: senderField.label,
      senderFieldName: senderField.name,
      senderType: senderField.data_type,
      transformation: "Unmapped",
      receiverFieldId: null,
      receiverFieldLabel: "—",
      receiverFieldName: "",
      receiverType: "—",
      status: "Unmapped",
      issue: "Sender field is not mapped to a receiver field.",
      senderNormalizedType: normalizeSchemaType(senderField.data_type),
      receiverNormalizedType: "unknown",
      outputNormalizedType: normalizeSchemaType(senderField.data_type),
      typeProgression: [],
      lossy: false,
      transformationNodeIds: [],
      primaryIssueEdgeId: null,
      graphNodeIds: [sourceNode.id],
      graphEdgeIds: [],
    });
  }

  return rows;
}

export function filterMappingMatrixRows(
  rows: MappingMatrixRow[],
  filter: MappingMatrixFilter,
): MappingMatrixRow[] {
  if (filter === "all") return rows;
  if (filter === "mapped") return rows.filter((row) => row.status !== "Unmapped");
  if (filter === "unmapped") return rows.filter((row) => row.status === "Unmapped");
  return rows.filter((row) => row.status === "Error" || row.status === "Warning");
}

export function resolveMatrixRowSelection(
  rows: MappingMatrixRow[],
  selectedNodeId: string,
  selectedEdgeId: string,
): string {
  if (selectedEdgeId) {
    const byEdge = rows.find((row) => row.graphEdgeIds.includes(selectedEdgeId));
    if (byEdge) return byEdge.id;
  }
  if (selectedNodeId) {
    const byNode = rows.find((row) => row.graphNodeIds.includes(selectedNodeId));
    if (byNode) return byNode.id;
  }
  return "";
}

export function dirtyStateForWorkbenchViewSwitch(currentDirty: boolean): boolean {
  return currentDirty;
}

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function csrfToken(): string {
  const raw = document.cookie.split("; ").find((item) => item.startsWith("dd_csrf="))?.slice(8);
  if (!raw) throw new Error("Your session could not be verified. Reload and try again.");
  return decodeURIComponent(raw);
}

function newUuid(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function readableError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) return String(item.msg);
      return JSON.stringify(item);
    }).join("; ");
  }
  if (detail && typeof detail === "object") {
    const data = detail as { code?: string; message?: string; issues?: { path: string; message: string }[] };
    if (data.issues?.length) {
      return data.issues.map((issue) => `${issue.path}: ${issue.message}`).join("; ");
    }
    return data.message ?? data.code ?? JSON.stringify(detail);
  }
  return "The request could not be completed.";
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(readableError(body.detail), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function list<T>(path: string): Promise<T[]> {
  const result: T[] = [];
  let offset = 0;
  while (true) {
    const page = await api<T[]>(`${path}?limit=500&offset=${offset}`);
    result.push(...page);
    if (page.length < 500) return result;
    offset += page.length;
  }
}

function toFlowNode(
  item: GraphNodeDocument,
  sourceFields: CatalogField[],
  targetFields: CatalogField[],
  sourceObject: CatalogObject | undefined,
  targetObject: CatalogObject | undefined,
  onAddField?: (endpoint: "source" | "target") => void,
  onEditField?: (endpoint: "source" | "target", field: CatalogField) => void,
  onDeleteField?: (endpoint: "source" | "target", field: CatalogField) => void,
): FlowNode {
  const label = item.type === "source"
    ? `Source · ${sourceObject?.label ?? "object"}`
    : item.type === "target"
      ? `Target · ${targetObject?.label ?? "object"}`
      : NODE_LABELS[item.type];
  return {
    id: item.id,
    type: item.type,
    deletable: item.type !== "source" && item.type !== "target",
    draggable: item.type !== "source" && item.type !== "target",
    position: item.position,
    data: {
      label,
      config: item.config ?? {},
      fields: item.type === "source" ? sourceFields : item.type === "target" ? targetFields : undefined,
      onAddField: item.type === "source" || item.type === "target" ? onAddField : undefined,
      onEditField: item.type === "source" || item.type === "target" ? onEditField : undefined,
      onDeleteField: item.type === "source" || item.type === "target" ? onDeleteField : undefined,
    },
  };
}

function flowFromGraph(
  graph: GraphDocument,
  sourceFields: CatalogField[],
  targetFields: CatalogField[],
  sourceObject: CatalogObject | undefined,
  targetObject: CatalogObject | undefined,
  onAddField?: (endpoint: "source" | "target") => void,
  onEditField?: (endpoint: "source" | "target", field: CatalogField) => void,
  onDeleteField?: (endpoint: "source" | "target", field: CatalogField) => void,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  return {
    nodes: graph.nodes.map((node) => toFlowNode(
      node,
      sourceFields,
      targetFields,
      sourceObject,
      targetObject,
      onAddField,
      onEditField,
      onDeleteField,
    )),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.sourceNodeId,
      sourceHandle: edge.sourcePortId,
      target: edge.targetNodeId,
      targetHandle: edge.targetPortId,
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { direction: "outbound" as const },
    })),
  };
}

const RESPONSE_NODE_PREFIX = "response:";

function graphWithEndpoints(
  graph: GraphDocument,
  requestGraph: GraphDocument,
): GraphDocument {
  if (graph.nodes.some((node) => node.type === "source") && graph.nodes.some((node) => node.type === "target")) {
    return graph;
  }
  const source = requestGraph.nodes.find((node) => node.type === "source");
  const target = requestGraph.nodes.find((node) => node.type === "target");
  if (!source || !target) return graph;
  return {
    version: 1,
    nodes: [
      { ...target, type: "source", config: {} },
      { ...source, type: "target", config: {} },
    ],
    edges: graph.edges,
  };
}

function orientResponseGraph(graph: GraphDocument): GraphDocument {
  if (graph.nodes.length < 2) return graph;
  const source = graph.nodes.find((node) => node.type === "source");
  const target = graph.nodes.find((node) => node.type === "target");
  if (source && target && source.position.x <= target.position.x) return graph;
  const xPositions = graph.nodes.map((node) => node.position.x);
  const minX = Math.min(...xPositions);
  const maxX = Math.max(...xPositions);
  return {
    ...graph,
    nodes: graph.nodes.map((node) => ({
      ...node,
      position: { ...node.position, x: minX + maxX - node.position.x },
    })),
  };
}

function unifiedFlowFromGraphs(
  requestGraph: GraphDocument,
  responseGraphInput: GraphDocument,
  sourceFields: CatalogField[],
  targetFields: CatalogField[],
  sourceObject: CatalogObject | undefined,
  targetObject: CatalogObject | undefined,
  responseEnabled: boolean,
  onAddField?: (endpoint: "source" | "target") => void,
  onEditField?: (endpoint: "source" | "target", field: CatalogField) => void,
  onDeleteField?: (endpoint: "source" | "target", field: CatalogField) => void,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const responseGraph = graphWithEndpoints(responseGraphInput, requestGraph);
  const request = flowFromGraph(
    requestGraph, sourceFields, targetFields, sourceObject, targetObject,
    onAddField, onEditField, onDeleteField,
  );
  const requestSource = request.nodes.find((node) => node.type === "source");
  const requestTarget = request.nodes.find((node) => node.type === "target");
  const responseSource = responseGraph.nodes.find((node) => node.type === "source");
  const responseTarget = responseGraph.nodes.find((node) => node.type === "target");
  if (!requestSource || !requestTarget || !responseSource || !responseTarget) {
    return { nodes: request.nodes, edges: request.edges };
  }

  const responseNodeIds = new Map<string, string>([
    [responseSource.id, requestTarget.id],
    [responseTarget.id, requestSource.id],
  ]);
  const responseNodes = responseGraph.nodes
    .filter((node) => node.type !== "source" && node.type !== "target")
    .map((node) => ({
      ...toFlowNode(
        node, targetFields, sourceFields, targetObject, sourceObject,
        undefined, undefined, undefined,
      ),
      id: `${RESPONSE_NODE_PREFIX}${node.id}`,
      data: { ...toFlowNode(
        node, targetFields, sourceFields, targetObject, sourceObject,
        undefined, undefined, undefined,
      ).data, direction: "inbound" as const },
    }));
  for (const node of responseGraph.nodes) {
    if (node.type !== "source" && node.type !== "target") {
      responseNodeIds.set(node.id, `${RESPONSE_NODE_PREFIX}${node.id}`);
    }
  }
  const responseEdges = responseGraph.edges.map((edge) => ({
    id: `${RESPONSE_NODE_PREFIX}${edge.id}`,
    source: responseNodeIds.get(edge.sourceNodeId) ?? `${RESPONSE_NODE_PREFIX}${edge.sourceNodeId}`,
    sourceHandle: edge.sourcePortId,
    target: responseNodeIds.get(edge.targetNodeId) ?? `${RESPONSE_NODE_PREFIX}${edge.targetNodeId}`,
    targetHandle: edge.targetPortId,
    markerEnd: { type: MarkerType.ArrowClosed },
    data: { direction: "inbound" as const },
  }));
  const nodes = request.nodes.map((node) => ({
    ...node,
    data: { ...node.data, responseEnabled },
  }));
  return { nodes: [...nodes, ...responseNodes], edges: [...request.edges, ...responseEdges] };
}

function graphsFromUnifiedFlow(
  nodes: FlowNode[],
  edges: FlowEdge[],
  responseGraphInput: GraphDocument,
): { request: GraphDocument; response: GraphDocument } {
  const requestNodes = nodes.filter((node) => !node.id.startsWith(RESPONSE_NODE_PREFIX));
  const responseGraph = graphWithEndpoints(responseGraphInput, {
    version: 1,
    nodes: requestNodes.map((node) => ({
      id: node.id,
      type: node.type as GraphNodeType,
      position: node.position,
      config: node.data.config,
    })),
    edges: [],
  });
  const request = graphFromFlow(
    requestNodes,
    edges.filter((edge) => edge.data?.direction !== "inbound"),
  );
  const canvasSource = nodes.find((node) => node.type === "source");
  const canvasTarget = nodes.find((node) => node.type === "target");
  const responseSource = responseGraph.nodes.find((node) => node.type === "source");
  const responseTarget = responseGraph.nodes.find((node) => node.type === "target");
  if (!canvasSource || !canvasTarget || !responseSource || !responseTarget) {
    return { request, response: responseGraph };
  }

  const responseNodeIds = new Map<string, string>([
    [canvasTarget.id, responseSource.id],
    [canvasSource.id, responseTarget.id],
  ]);
  const responseNodes = nodes
    .filter((node) => node.id.startsWith(RESPONSE_NODE_PREFIX))
    .map((node) => ({
      id: node.id.slice(RESPONSE_NODE_PREFIX.length),
      type: node.type as GraphNodeType,
      position: node.position,
      config: node.data.config,
    }));
  for (const node of responseNodes) responseNodeIds.set(`${RESPONSE_NODE_PREFIX}${node.id}`, node.id);
  const responseEdges = edges
    .filter((edge) => edge.data?.direction === "inbound")
    .map((edge) => ({
      id: edge.id.startsWith(RESPONSE_NODE_PREFIX) ? edge.id.slice(RESPONSE_NODE_PREFIX.length) : edge.id,
      sourceNodeId: responseNodeIds.get(edge.source) ?? edge.source.replace(RESPONSE_NODE_PREFIX, ""),
      sourcePortId: edge.sourceHandle ?? "output",
      targetNodeId: responseNodeIds.get(edge.target) ?? edge.target.replace(RESPONSE_NODE_PREFIX, ""),
      targetPortId: edge.targetHandle ?? "input",
    }));
  const responseNodeDocuments = responseGraph.nodes
    .filter((node) => node.type === "source" || node.type === "target")
    .map((node) => {
      const canvasNode = node.type === "source" ? canvasTarget : canvasSource;
      return { ...node, position: canvasNode.position };
    });
  return {
    request,
    response: {
      version: 1,
      nodes: [...responseNodeDocuments, ...responseNodes],
      edges: responseEdges,
    },
  };
}

type ConnectionValidation = { valid: true } | { valid: false; message: string };

export function validatePhaseConnection(
  connection: Connection,
  nodes: FlowNode[],
  edges: FlowEdge[],
  senderFields: CatalogField[],
  receiverFields: CatalogField[],
  phase: ContractView,
): ConnectionValidation {
  if (phase === "overview") return { valid: false, message: "Connections must stay within the active phase." };
  if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) {
    return { valid: false, message: "Choose a valid output and input handle." };
  }
  if (connection.source === connection.target) {
    return { valid: false, message: "A node cannot connect to itself." };
  }

  const sourceNode = nodes.find((node) => node.id === connection.source);
  const targetNode = nodes.find((node) => node.id === connection.target);
  if (!sourceNode || !targetNode) {
    return { valid: false, message: "Connections must stay within the active phase." };
  }
  if (
    (sourceNode.data.phase && sourceNode.data.phase !== phase)
    || (targetNode.data.phase && targetNode.data.phase !== phase)
    || edges.some((edge) => edge.data?.phase && edge.data.phase !== phase)
  ) {
    return { valid: false, message: "Connections must stay within the active phase." };
  }

  const sourceFieldId = connection.sourceHandle.startsWith("field:")
    ? connection.sourceHandle.slice("field:".length)
    : null;
  const targetFieldId = connection.targetHandle.startsWith("field:")
    ? connection.targetHandle.slice("field:".length)
    : null;
  const sourceHandleValid = sourceNode.type === "source"
    ? Boolean(sourceFieldId && senderFields.some((field) => field.id === sourceFieldId))
    : TRANSFORM_TYPES.includes(sourceNode.type)
      && connection.sourceHandle === "output";
  const targetHandleValid = targetNode.type === "target"
    ? Boolean(targetFieldId && receiverFields.some((field) => field.id === targetFieldId))
    : TRANSFORM_TYPES.includes(targetNode.type)
      && connection.targetHandle === "input";

  if (!sourceHandleValid) {
    return {
      valid: false,
      message: sourceNode.type === "target"
        ? "Receiver fields cannot start a connection."
        : sourceNode.type === "source"
          ? "Choose an available sender field output."
          : "Transformation inputs cannot start a connection.",
    };
  }
  if (!targetHandleValid) {
    return {
      valid: false,
      message: targetNode.type === "source"
        ? "Sender fields cannot receive a connection."
        : targetNode.type === "target"
          ? "Choose an available receiver field input."
          : "Choose a transformation input.",
    };
  }

  const duplicate = edges.some((edge) =>
    edge.source === connection.source
    && edge.sourceHandle === connection.sourceHandle
    && edge.target === connection.target
    && edge.targetHandle === connection.targetHandle,
  );
  if (duplicate) return { valid: false, message: "This connection already exists." };

  const nextBySource = new Map<string, string[]>();
  for (const edge of edges) {
    nextBySource.set(edge.source, [...(nextBySource.get(edge.source) ?? []), edge.target]);
  }
  const pending = [connection.target];
  const visited = new Set<string>();
  while (pending.length) {
    const nodeId = pending.pop()!;
    if (nodeId === connection.source) {
      return { valid: false, message: "This connection would create a cycle." };
    }
    if (visited.has(nodeId)) continue;
    visited.add(nodeId);
    pending.push(...(nextBySource.get(nodeId) ?? []));
  }
  return { valid: true };
}

function connectionDirection(
  _connection: Connection,
  _nodes: FlowNode[],
  _edges: FlowEdge[],
): "outbound" | "inbound" {
  return "outbound";
}

function FieldNode({ data, type }: NodeProps<FlowNode>) {
  const source = type === "source";
  const target = type === "target";
  const transformationTitle = type === "fx"
    ? transformationLabel("fx", data.config)
    : type === "map"
      ? "mapping"
      : type === "concat"
        ? "join"
        : data.label;
  const [search, setSearch] = React.useState("");
  const query = search.trim().toLowerCase();
  const visibleFields = (data.fields ?? []).filter((field) =>
    !query || `${field.name} ${field.label} ${field.data_type}`.toLowerCase().includes(query),
  );
  return (
    <article
      className={`flow-card ${source ? "flow-source" : target ? "flow-target" : "flow-transform"}`}
      title={!source && !target
        ? data.evaluation
          ? `${transformationTitle}\nOutput: ${data.evaluation}`
          : transformationTitle
        : undefined}
    >
      {(source || target) && (
        <>
          <div className="flow-node-title">{data.label}</div>
          <label className="flow-field-search nodrag nopan">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search fields..."
              aria-label={`Search ${source ? "source" : "target"} fields`}
            />
          </label>
        </>
      )}
      {!source && !target && (
        <>
          <Handle
            type="target"
            position={Position.Left}
            id="input"
            className="flow-handle"
          />
          <div className="flow-transform-line">
            <span className="flow-node-kicker" aria-hidden="true">{type === "fx" ? "⚡" : "◇"}</span>
            <span className="flow-node-title">
              {transformationTitle}
            </span>
          </div>
          <Handle
            type="source"
            position={Position.Right}
            id="output"
            className="flow-handle"
          />
        </>
      )}
      {(source || target) && (
        <div className="flow-field-list">
          {visibleFields.map((field) => (
            <div className="flow-field" key={field.id}>
              {source && (
                <Handle type="source" position={Position.Right} id={`field:${field.id}`} className="flow-handle" />
              )}
              {target && (
                <Handle type="target" position={Position.Left} id={`field:${field.id}`} className="flow-handle" />
              )}
              <span className="flow-field-label">{field.label}</span>
              <small className="field-type-pill">{field.data_type}</small>
              {(data.onEditField || data.onDeleteField) && (
              <span className="flow-field-actions nodrag nopan">
                <button
                  type="button"
                  className="flow-field-action"
                  aria-label={`Edit ${field.label}`}
                  title={`Edit ${field.label}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    data.onEditField?.(source ? "source" : "target", field);
                  }}
                >
                  <svg aria-hidden="true" viewBox="0 0 16 16"><path d="m11.7 2.3 2 2a.9.9 0 0 1 0 1.3l-7.9 7.9-3.3.8.8-3.3 7.9-7.9a.9.9 0 0 1 1.3 0Z" /><path d="m9.9 4.1 2 2" /></svg>
                </button>
                <button
                  type="button"
                  className="flow-field-action danger"
                  aria-label={`Delete ${field.label}`}
                  title={`Delete ${field.label}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    data.onDeleteField?.(source ? "source" : "target", field);
                  }}
                >
                  <svg aria-hidden="true" viewBox="0 0 16 16"><path d="M3 4.5h10M6 4.5V3h4v1.5m2-.0-.5 9h-7l-.5-9m3 2v4m3-4v4" /></svg>
                </button>
              </span>
              )}
            </div>
          ))}
          {data.fields?.length === 0 && <small className="flow-no-fields">No available fields</small>}
          {!!data.fields?.length && !visibleFields.length && <small className="flow-no-fields">No matching fields</small>}
          {data.onAddField && <button
            type="button"
            className="flow-add-field"
            onClick={(event) => {
              event.stopPropagation();
              data.onAddField?.(source ? "source" : "target");
            }}
          >
            + Add field
          </button>}
        </div>
      )}
    </article>
  );
}

const nodeTypes: NodeTypes = {
  source: FieldNode,
  target: FieldNode,
  constant: FieldNode,
  fx: FieldNode,
  concat: FieldNode,
  ifelse: FieldNode,
  map: FieldNode,
  coalesce: FieldNode,
  lookup: FieldNode,
  filter: FieldNode,
  validate: FieldNode,
};

const edgeTypes: EdgeTypes = {
  "mapper-edge": MapperEdge,
};

export function graphFromFlow(nodes: FlowNode[], edges: FlowEdge[]): GraphDocument {
  return {
    version: 1,
    nodes: nodes.map((node) => ({
      id: normalizeUuidForApi(node.id),
      type: node.type as GraphNodeType,
      position: { x: node.position.x, y: node.position.y },
      config: node.data.config,
    })),
    edges: edges.map((edge) => ({
      id: normalizeUuidForApi(edge.id),
      sourceNodeId: normalizeUuidForApi(edge.source),
      sourcePortId: edge.sourceHandle ?? "output",
      targetNodeId: normalizeUuidForApi(edge.target),
      targetPortId: edge.targetHandle ?? "input",
    })),
  };
}

function defaultNodeConfig(type: GraphNodeType): Record<string, unknown> {
  return structuredClone(DEFAULT_CONFIG[type]);
}

function targetNodeType(node: FlowNode | undefined): GraphNodeType | undefined {
  return node?.type as GraphNodeType | undefined;
}

function objectName(
  objects: CatalogObject[],
  id: string,
): string {
  return objects.find((item) => item.id === id)?.label ?? "Choose object";
}

function parseSampleRows(text: string): { rows: SimulationRowInput[] | null; error: string } {
  try {
    const parsed: unknown = JSON.parse(text);
    if (!Array.isArray(parsed)) return { rows: null, error: "Sample rows must be a JSON array." };
    const rows: SimulationRowInput[] = [];
    for (const [index, item] of parsed.entries()) {
      if (
        !item
        || typeof item !== "object"
        || Array.isArray(item)
        || !("rowId" in item)
        || typeof item.rowId !== "string"
        || !("values" in item)
        || !item.values
        || typeof item.values !== "object"
        || Array.isArray(item.values)
      ) {
        return {
          rows: null,
          error: `Sample row ${index + 1} must contain a string rowId and an object of field values.`,
        };
      }
      rows.push({ rowId: item.rowId, values: item.values as Record<string, unknown> });
    }
    if (rows.length > 100) return { rows: null, error: "A maximum of 100 sample rows is supported." };
    return { rows, error: "" };
  } catch {
    return { rows: null, error: "Sample rows must be valid JSON." };
  }
}

function mockSampleValue(field: CatalogField, rowIndex: number): unknown {
  const name = `${field.name} ${field.label}`.toLowerCase().replace(/[^a-z0-9]+/g, " ");
  const type = field.data_type.toLowerCase();
  if (/\b(email|e mail)\b/.test(name)) return `person${rowIndex + 1}@example.com`;
  if (/\b(phone|mobile|telephone)\b/.test(name)) return `+1555010${String(rowIndex + 1).padStart(3, "0")}`;
  if (/\b(first name|firstname)\b/.test(name)) return ["Alex", "Jordan", "Taylor"][rowIndex];
  if (/\b(last name|lastname|surname)\b/.test(name)) return ["Morgan", "Reed", "Patel"][rowIndex];
  if (/\b(full name|customer name|contact name|person name)\b/.test(name)) {
    return ["Alex Morgan", "Jordan Reed", "Taylor Patel"][rowIndex];
  }
  if (/\b(company|organization|organisation)\b/.test(name)) {
    return ["Northstar Labs", "Cedar Works", "Bluebird Studio"][rowIndex];
  }
  if (/\b(country)\b/.test(name)) return ["United States", "Canada", "United Kingdom"][rowIndex];
  if (/\b(status|state)\b/.test(name)) return ["active", "pending", "active"][rowIndex];
  if (/\b(created|updated|birth|start|end).*date\b|\b(date|dob)\b/.test(name) || type === "date") {
    return `202${rowIndex + 4}-0${rowIndex + 1}-15`;
  }
  if (/\b(amount|price|total|revenue|salary|cost)\b/.test(name) || /decimal|float|double|numeric/.test(type)) {
    return [129.5, 84.25, 245.0][rowIndex];
  }
  if (/\b(count|quantity|age|score|number)\b/.test(name) || /int|number/.test(type)) {
    return [3, 7, 12][rowIndex];
  }
  if (/\b(active|enabled|verified|subscribed|is .*)\b/.test(name) || /bool/.test(type)) {
    return rowIndex !== 1;
  }
  if (/\b(id|uuid|key)\b/.test(name)) return `sample-${rowIndex + 1}`;
  return `Example ${field.label || field.name} ${rowIndex + 1}`;
}

function conversionFunction(sourceType: string, targetType: string): ConnectionAssist["suggestedFunction"] {
  const source = sourceType.trim().toLowerCase();
  const target = targetType.trim().toLowerCase();
  const sourceInteger = ["integer", "int"].includes(source);
  const sourceNumber = ["number", "float", "decimal", "double", "numeric"].includes(source);
  const sourceString = ["string", "text"].includes(source);
  const targetInteger = ["integer", "int"].includes(target);
  const targetNumber = ["number", "float", "decimal", "double", "numeric"].includes(target);
  const targetBoolean = ["boolean", "bool"].includes(target);
  const targetString = ["string", "text"].includes(target);
  const sourceDate = ["date", "datetime"].includes(source);
  const targetDate = ["date", "datetime"].includes(target);
  if (sourceString && targetInteger) return "toInt";
  if (sourceString && targetNumber) return "toNumber";
  if (sourceString && targetBoolean) return "toBoolean";
  if (sourceString && targetDate) return "parseDate";
  if ((sourceInteger || sourceNumber || targetDate) && targetString) return sourceDate ? "formatDate" : "toString";
  if (sourceDate && targetString) return "formatDate";
  if (sourceNumber && targetInteger) return "toInt";
  return "toString";
}

function normalizedFieldName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export type WorkbenchLayoutContext = {
  sourceFields: CatalogField[];
  targetFields: CatalogField[];
  sourceHandleCenters?: Map<string, number>;
  targetHandleCenters?: Map<string, number>;
};

const TRANSFORM_NODE_FALLBACK_WIDTH = 150;
const TRANSFORM_NODE_HEIGHT = 36;

function estimatedFieldCenterY(
  nodeY: number,
  fieldId: string | undefined,
  fields: CatalogField[],
  measuredCenters?: Map<string, number>,
): number | null {
  if (!fieldId) return null;
  const measured = measuredCenters?.get(fieldId);
  if (measured !== undefined) return measured;
  const index = fields.findIndex((field) => field.id === fieldId);
  if (index < 0) return null;
  const firstHandleCenter = 90;
  const fieldRowHeight = 34;
  return nodeY + firstHandleCenter + index * fieldRowHeight;
}

function hasPersistedPosition(node: FlowNode): boolean {
  return Number.isFinite(node.position.x)
    && Number.isFinite(node.position.y)
    && (node.position.x !== 0 || node.position.y !== 0);
}

function fieldIdFromHandle(handle: string | null | undefined): string | undefined {
  return handle?.startsWith("field:") ? handle.slice("field:".length) : undefined;
}

export function transformationPositionBetweenHandles(
  source: { x: number; y: number },
  target: { x: number; y: number },
  width = TRANSFORM_NODE_FALLBACK_WIDTH,
  height = TRANSFORM_NODE_HEIGHT,
): { x: number; y: number } {
  return {
    x: Math.round((source.x + target.x) / 2 - width / 2),
    y: Math.round((source.y + target.y) / 2 - height / 2),
  };
}

export function applyWorkbenchLayout(
  flowNodes: FlowNode[],
  flowEdges: FlowEdge[],
  context: WorkbenchLayoutContext,
  options: { preservePersisted?: boolean; repositionNodeIds?: Set<string> } = {},
): FlowNode[] {
  const sourceNode = flowNodes.find((node) => node.type === "source");
  const targetNode = flowNodes.find((node) => node.type === "target");
  if (!sourceNode || !targetNode) return flowNodes;
  const transformNodes = flowNodes.filter((node) => !["source", "target"].includes(node.type));
  const nodeById = new Map(flowNodes.map((node) => [node.id, node]));
  const edgeByTarget = new Map<string, FlowEdge[]>();
  const edgeBySource = new Map<string, FlowEdge[]>();
  for (const edge of flowEdges) {
    edgeByTarget.set(edge.target, [...(edgeByTarget.get(edge.target) ?? []), edge]);
    edgeBySource.set(edge.source, [...(edgeBySource.get(edge.source) ?? []), edge]);
  }
  const transformIds = new Set(transformNodes.map((node) => node.id));
  const nextPositions = new Map<string, { x: number; y: number }>();
  const endpointHandleY = (node: FlowNode, handle: string | null | undefined): number | null => {
    const fieldId = fieldIdFromHandle(handle);
    if (node.type === "source") {
      return estimatedFieldCenterY(node.position.y, fieldId, context.sourceFields, context.sourceHandleCenters);
    }
    if (node.type === "target") {
      return estimatedFieldCenterY(node.position.y, fieldId, context.targetFields, context.targetHandleCenters);
    }
    return null;
  };
  const visited = new Set<string>();
  const orderedTransformIds: string[] = [];
  const rankById = new Map<string, number>();
  const rankFor = (id: string, path: Set<string>): number => {
    if (path.has(id)) return 0;
    const nextPath = new Set(path).add(id);
    const parents = (edgeByTarget.get(id) ?? [])
      .map((edge) => nodeById.get(edge.source))
      .filter((parent): parent is FlowNode => Boolean(parent && transformIds.has(parent.id)));
    const rank = parents.length ? 1 + Math.max(...parents.map((parent) => rankFor(parent.id, nextPath))) : 0;
    rankById.set(id, Math.max(rankById.get(id) ?? 0, rank));
    return rank;
  };
  for (const node of transformNodes) rankFor(node.id, new Set());
  const maxRank = Math.max(1, ...rankById.values());
  const sourceRight = sourceNode.position.x + (sourceNode.measured?.width ?? 220);
  const targetLeft = targetNode.position.x;
  const horizontalSpan = Math.max(160, targetLeft - sourceRight);
  for (const node of [...transformNodes].sort((a, b) =>
    (rankById.get(a.id) ?? 0) - (rankById.get(b.id) ?? 0) || a.id.localeCompare(b.id),
  )) {
    if (visited.has(node.id)) continue;
    visited.add(node.id);
    const upstreamFields: number[] = [];
    const downstreamFields: number[] = [];
    const upstreamTransforms: string[] = [];
    const downstreamTransforms: string[] = [];
    const trace = (
      currentId: string,
      edges: Map<string, FlowEdge[]>,
      direction: "upstream" | "downstream",
      path: Set<string>,
    ) => {
      if (path.has(currentId)) return;
      const nextPath = new Set(path).add(currentId);
      const links = edges.get(currentId) ?? [];
      for (const edge of links) {
        const neighborId = direction === "upstream" ? edge.source : edge.target;
        const neighbor = nodeById.get(neighborId);
        if (!neighbor) continue;
        if (neighbor.type === "source" || neighbor.type === "target") {
          const handle = direction === "upstream" ? edge.sourceHandle : edge.targetHandle;
          const y = endpointHandleY(neighbor, handle);
          if (y !== null) {
            (neighbor.type === "source" ? upstreamFields : downstreamFields).push(y);
          }
        } else if (transformIds.has(neighbor.id)) {
          (direction === "upstream" ? upstreamTransforms : downstreamTransforms).push(neighbor.id);
          trace(neighbor.id, edges, direction, nextPath);
        }
      }
    };
    trace(node.id, edgeByTarget, "upstream", new Set());
    trace(node.id, edgeBySource, "downstream", new Set());
    const allFieldY = [...upstreamFields, ...downstreamFields];
    let centerY: number;
    if (upstreamFields.length > 1 && downstreamFields.length) {
      centerY = [...upstreamFields, ...downstreamFields].reduce((sum, y) => sum + y, 0)
        / (upstreamFields.length + downstreamFields.length);
    } else if (downstreamFields.length > 1) {
      centerY = downstreamFields.reduce((sum, y) => sum + y, 0) / downstreamFields.length;
    } else if (allFieldY.length) {
      centerY = allFieldY.reduce((sum, y) => sum + y, 0) / allFieldY.length;
    } else {
      centerY = node.position.y + 18;
    }
    const beforeCount = new Set(upstreamTransforms).size;
    const chainLength = beforeCount + new Set(downstreamTransforms).size + 1;
    const rank = (rankById.get(node.id) ?? beforeCount) + 1;
    const chainSteps = Math.max(chainLength, maxRank);
    const centerX = sourceRight + horizontalSpan * (rank / (chainSteps + 1));
    const width = node.measured?.width ?? TRANSFORM_NODE_FALLBACK_WIDTH;
    const height = node.measured?.height ?? TRANSFORM_NODE_HEIGHT;
    const siblings = transformNodes.filter((other) =>
      other.id !== node.id
      && (rankById.get(other.id) ?? 0) === (rankById.get(node.id) ?? 0)
      && (
        nextPositions.has(other.id)
        || (options.preservePersisted && hasPersistedPosition(other) && !options.repositionNodeIds?.has(other.id))
      ),
    );
    const clearance = 8;
    const offsets = Array.from({ length: siblings.length * 2 + 1 }, (_, index) => {
      if (index === 0) return 0;
      const distance = Math.ceil(index / 2) * (height + clearance);
      return index % 2 === 1 ? distance : -distance;
    });
    let selectedCenterY = centerY;
    for (const offset of offsets) {
      const candidateY = centerY + offset;
      const overlaps = siblings.some((sibling) => {
        const siblingPosition = nextPositions.get(sibling.id) ?? sibling.position;
        const siblingWidth = sibling.measured?.width ?? TRANSFORM_NODE_FALLBACK_WIDTH;
        const siblingHeight = sibling.measured?.height ?? TRANSFORM_NODE_HEIGHT;
        const horizontalOverlap = Math.abs(centerX - (siblingPosition.x + siblingWidth / 2))
          < (width + siblingWidth) / 2;
        const verticalOverlap = Math.abs(candidateY - (siblingPosition.y + siblingHeight / 2))
          < (height + siblingHeight) / 2 + clearance;
        return horizontalOverlap && verticalOverlap;
      });
      if (!overlaps) {
        selectedCenterY = candidateY;
        break;
      }
    }
    const position = {
      x: Math.round(centerX - width / 2),
      y: Math.round(selectedCenterY - height / 2),
    };
    nextPositions.set(
      node.id,
      options.preservePersisted && hasPersistedPosition(node) && !options.repositionNodeIds?.has(node.id)
        ? node.position
        : position,
    );
  }
  return flowNodes.map((node) => ({
    ...node,
    position: node.type === "source" || node.type === "target"
      ? node.position
      : nextPositions.get(node.id) ?? node.position,
  }));
}

function fieldNameSimilarity(left: string, right: string): number {
  const a = normalizedFieldName(left);
  const b = normalizedFieldName(right);
  if (!a || !b) return 0;
  if (a === b) return 1;
  if (Math.min(a.length, b.length) / Math.max(a.length, b.length) < 0.72) return 0;
  const bigrams = (value: string) =>
    new Set(Array.from({ length: value.length - 1 }, (_, index) => value.slice(index, index + 2)));
  const leftBigrams = bigrams(a);
  const rightBigrams = bigrams(b);
  const shared = [...leftBigrams].filter((gram) => rightBigrams.has(gram)).length;
  return (2 * shared) / (leftBigrams.size + rightBigrams.size);
}

function integrationUsesField(integration: Integration, fieldId: string): boolean {
  const portId = `field:${fieldId}`;
  return integration.graph.edges.some((edge) =>
    edge.sourcePortId === portId || edge.targetPortId === portId,
  ) || integration.response_graph.edges.some((edge) =>
    edge.sourcePortId === portId || edge.targetPortId === portId,
  ) || (integration.error_response_graph?.edges ?? []).some((edge) =>
    edge.sourcePortId === portId || edge.targetPortId === portId,
  ) || integration.sample_rows.some((row) => Object.hasOwn(row.values, fieldId));
}

export default function IntegrationWorkspace({
  onBack,
  initialIntegrationId,
  initialContractView,
  newIntegrationSystemId,
}: Props) {
  const [systems, setSystems] = React.useState<System[]>([]);
  const [sourceObjects, setSourceObjects] = React.useState<CatalogObject[]>([]);
  const [targetObjects, setTargetObjects] = React.useState<CatalogObject[]>([]);
  const [sourceFields, setSourceFields] = React.useState<CatalogField[]>([]);
  const [targetFields, setTargetFields] = React.useState<CatalogField[]>([]);
  const [sourceCatalogObject, setSourceCatalogObject] = React.useState<CatalogObject>();
  const [targetCatalogObject, setTargetCatalogObject] = React.useState<CatalogObject>();
  const [errorResponseCatalogObject, setErrorResponseCatalogObject] = React.useState<CatalogObject>();
  const [integrations, setIntegrations] = React.useState<Integration[]>([]);
  const [architecture, setArchitecture] = React.useState<ArchitectureAnalysis | null>(null);
  const [dependencyCandidateId, setDependencyCandidateId] = React.useState("");
  const [dependencySaving, setDependencySaving] = React.useState(false);
  const [quickAddEndpoint, setQuickAddEndpoint] = React.useState<"source" | "target" | null>(null);
  const [quickFieldName, setQuickFieldName] = React.useState("");
  const [quickFieldType, setQuickFieldType] = React.useState("string");
  const [quickFieldSaving, setQuickFieldSaving] = React.useState(false);
  const [editingField, setEditingField] = React.useState<{ endpoint: "source" | "target"; field: CatalogField } | null>(null);
  const [fieldSaving, setFieldSaving] = React.useState(false);
  const [editorNotice, setEditorNotice] = React.useState("");
  const [connectionError, setConnectionError] = React.useState("");
  const [selectedIntegrationId, setSelectedIntegrationId] = React.useState("");
  const [integrationLoadSequence, setIntegrationLoadSequence] = React.useState(0);
  const [sourceSystemId, setSourceSystemId] = React.useState("");
  const [sourceObjectId, setSourceObjectId] = React.useState("");
  const [targetSystemId, setTargetSystemId] = React.useState("");
  const [targetObjectId, setTargetObjectId] = React.useState("");
  const [name, setName] = React.useState("");
  const [sourceObjectLabel, setSourceObjectLabel] = React.useState("object");
  const [targetObjectLabel, setTargetObjectLabel] = React.useState("object");
  const [interactionType, setInteractionType] = React.useState<InteractionType>("ONE_WAY");
  const [contractView, setContractView] = React.useState<ContractView>("overview");
  // Scenarios render over the static overview so the phase canvas logic stays untouched.
  const [scenariosOpen, setScenariosOpen] = React.useState(false);
  const [loadedContractKey, setLoadedContractKey] = React.useState("");
  const pendingContractViewRef = React.useRef<{ integrationId: string; view: ContractView | "scenarios" } | null>(
    initialIntegrationId && initialContractView
      ? { integrationId: initialIntegrationId, view: initialContractView }
      : null,
  );
  const [errorResponseObjectId, setErrorResponseObjectId] = React.useState("");
  const [errorResponseFields, setErrorResponseFields] = React.useState<CatalogField[]>([]);
  const [requestGraphDraft, setRequestGraphDraft] = React.useState<GraphDocument>({
    version: 1, nodes: [], edges: [],
  });
  const [responseGraphDraft, setResponseGraphDraft] = React.useState<GraphDocument>({
    version: 1, nodes: [], edges: [],
  });
  const [errorResponseGraphDraft, setErrorResponseGraphDraft] = React.useState<GraphDocument>({
    version: 1, nodes: [], edges: [],
  });
  const [nodes, setNodes] = React.useState<FlowNode[]>([]);
  const [edges, setEdges] = React.useState<FlowEdge[]>([]);
  const [connectionAssist, setConnectionAssist] = React.useState<ConnectionAssist | null>(null);
  const flowShellRef = React.useRef<HTMLDivElement>(null);
  const [selectedNodeId, setSelectedNodeId] = React.useState("");
  const [selectedEdgeId, setSelectedEdgeId] = React.useState("");
  const [workbenchView, setWorkbenchView] = React.useState<MappingWorkbenchView>("canvas");
  const [matrixFilter, setMatrixFilter] = React.useState<MappingMatrixFilter>("all");
  const [selectedMatrixRowId, setSelectedMatrixRowId] = React.useState("");
  const [drawerView, setDrawerView] = React.useState<"inspector" | "validation" | "settings" | null>(null);
  const [transformMenuOpen, setTransformMenuOpen] = React.useState(false);
  const [canvasReadyVersion, setCanvasReadyVersion] = React.useState(0);
  const [pendingErrorCanvasObjectId, setPendingErrorCanvasObjectId] = React.useState("");
  const flowInstance = React.useRef<ReactFlowInstance<FlowNode, FlowEdge> | null>(null);
  const [configText, setConfigText] = React.useState("{}");
  const [rowsText, setRowsText] = React.useState("[]");
  const [responsePayloadText, setResponsePayloadText] = React.useState("[]");
  const [sampleMode, setSampleMode] = React.useState<"form" | "json">("form");
  const [samplePanelExpanded, setSamplePanelExpanded] = React.useState(false);
  const [dataPreviewOpen, setDataPreviewOpen] = React.useState(false);
  const [revision, setRevision] = React.useState(0);
  const [dirty, setDirty] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [simulationLoading, setSimulationLoading] = React.useState(false);
  const [simulation, setSimulation] = React.useState<SimulationResult | null>(null);
  const [selectedRowIndex, setSelectedRowIndex] = React.useState(0);
  const [editorError, setEditorError] = React.useState("");
  const [configError, setConfigError] = React.useState("");
  const [csvDialog, setCsvDialog] = React.useState<"import" | "export" | null>(null);
  const [csvUndo, setCsvUndo] = React.useState<{
    nodes: FlowNode[];
    edges: FlowEdge[];
    dirty: boolean;
    phaseEdited: Record<MappingPhase, boolean>;
    afterKey: string;
  } | null>(null);
  const simulationRequest = React.useRef(0);
  const debounceTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const deleteFieldRef = React.useRef<(endpoint: "source" | "target", field: CatalogField) => Promise<void>>(async () => {});
  const suppressDirtyRef = React.useRef(false);
  const activeCanvasPhaseRef = React.useRef<ContractView>("overview");
  const phaseSwitchTokenRef = React.useRef(0);
  const phaseGraphEditedRef = React.useRef<Record<MappingPhase, boolean>>({
    request: false,
    "success-response": false,
    "error-response": false,
    "async-response": false,
  });
  const viewOnlyFallbackNodeIdsRef = React.useRef<Record<ContractView, Set<string>>>({
    overview: new Set(),
    request: new Set(),
    "success-response": new Set(),
    "error-response": new Set(),
    "async-response": new Set(),
  });

  const selectedIntegration =
    integrations.find((item) => item.id === selectedIntegrationId) ?? null;
  const parsedSampleRows = React.useMemo(() => parseSampleRows(rowsText), [rowsText]);
  const parsedResponsePayload = React.useMemo(
    () => parseSampleRows(responsePayloadText),
    [responsePayloadText],
  );
  const responsePhase = isResponsePhase(contractView);
  const ordinaryResponsePhase = usesSuccessResponseGraph(contractView);
  const canvasSourceFields = responsePhase
    ? contractView === "error-response" ? errorResponseFields : targetFields
    : sourceFields;
  const canvasTargetFields = responsePhase ? sourceFields : targetFields;
  const canvasSourceObject = responsePhase
    ? contractView === "error-response" ? errorResponseCatalogObject : targetCatalogObject
    : sourceCatalogObject;
  const canvasTargetObject = responsePhase ? sourceCatalogObject : targetCatalogObject;
  const activeSourceFields = canvasSourceFields;
  const activeTargetFields = canvasTargetFields;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const testingResponse = ordinaryResponsePhase;
  const activeSimulationRows = testingResponse
    ? simulation?.responseOutcomes ?? []
    : simulation?.requestOutcomes ?? simulation?.rows ?? [];
  const activeSimulationSummary = testingResponse ? simulation?.responseSummary : simulation?.summary;
  const activeTraceTruncated = testingResponse
    ? simulation?.responseTraceTruncated
    : simulation?.traceTruncated;
  const selectedRow = activeSimulationRows[selectedRowIndex] ?? null;
  const sourceSystem = systems.find((system) => system.id === sourceSystemId);
  const targetSystem = systems.find((system) => system.id === targetSystemId);
  const mappingMatrixRows = React.useMemo(() => deriveMappingMatrixRows({
    nodes,
    edges,
    senderFields: activeSourceFields,
    receiverFields: activeTargetFields,
  }), [nodes, edges, activeSourceFields, activeTargetFields]);
  const visibleMappingRows = React.useMemo(
    () => filterMappingMatrixRows(mappingMatrixRows, matrixFilter),
    [mappingMatrixRows, matrixFilter],
  );
  const matrixRowByEdgeId = React.useMemo(() => {
    const map = new Map<string, MappingMatrixRow>();
    for (const row of mappingMatrixRows) {
      for (const edgeId of row.graphEdgeIds) map.set(edgeId, row);
    }
    return map;
  }, [mappingMatrixRows]);
  const edgeValidationById = React.useMemo(() => {
    const map = new Map<string, { status: MappingMatrixStatus; issue: string }>();
    for (const row of mappingMatrixRows) {
      if (row.status !== "Error" && row.status !== "Warning") continue;
      if (row.primaryIssueEdgeId) {
        map.set(row.primaryIssueEdgeId, { status: row.status, issue: row.issue });
      }
    }
    return map;
  }, [mappingMatrixRows]);
  const activeValidationCounts = React.useMemo(() => ({
    errors: mappingMatrixRows.filter((row) => row.status === "Error").length,
    warnings: mappingMatrixRows.filter((row) => row.status === "Warning").length,
  }), [mappingMatrixRows]);
  const phaseValidationSummary = React.useMemo(() => {
    const graphsForValidation = computePhaseGraphsForSave({
      contractView,
      nodes,
      edges,
      requestGraphDraft,
      responseGraphDraft,
      errorResponseGraphDraft,
      phaseEdited: phaseGraphEditedRef.current,
    });
    const rowsForPhase = (phase: MappingPhase): MappingMatrixRow[] => {
      if (phase === "error-response" && !errorResponseObjectId) return [];
      const graph = phase === "request"
        ? graphsForValidation.request
        : phase === "error-response"
          ? graphWithEndpoints(graphsForValidation.errorResponse, graphsForValidation.request)
          : graphWithEndpoints(graphsForValidation.response, graphsForValidation.request);
      const flow = flowFromGraph(
        graph,
        phase === "request" ? sourceFields : phase === "error-response" ? errorResponseFields : targetFields,
        phase === "request" ? targetFields : sourceFields,
        phase === "request" ? sourceCatalogObject : phase === "error-response" ? errorResponseCatalogObject : targetCatalogObject,
        phase === "request" ? targetCatalogObject : sourceCatalogObject,
      );
      return deriveMappingMatrixRows({
        nodes: flow.nodes,
        edges: flow.edges,
        senderFields: phase === "request" ? sourceFields : phase === "error-response" ? errorResponseFields : targetFields,
        receiverFields: phase === "request" ? targetFields : sourceFields,
      });
    };
    const request = rowsForPhase("request");
    const success = rowsForPhase("success-response");
    const error = rowsForPhase("error-response");
    const summarize = (rows: MappingMatrixRow[]) => ({
      rows,
      errors: rows.filter((row) => row.status === "Error").length,
      warnings: rows.filter((row) => row.status === "Warning").length,
    });
    return {
      request: summarize(request),
      "success-response": summarize(success),
      "error-response": summarize(error),
    };
  }, [
    contractView,
    nodes,
    edges,
    requestGraphDraft,
    responseGraphDraft,
    errorResponseGraphDraft,
    errorResponseObjectId,
    sourceFields,
    targetFields,
    errorResponseFields,
    sourceCatalogObject,
    targetCatalogObject,
    errorResponseCatalogObject,
  ]);
  const contractHasMappingErrors = phaseValidationSummary.request.errors
    + phaseValidationSummary["success-response"].errors
    + phaseValidationSummary["error-response"].errors > 0;
  const currentGraphs = React.useMemo(() => {
    return computePhaseGraphsForSave({
      contractView,
      nodes,
      edges,
      requestGraphDraft,
      responseGraphDraft,
      errorResponseGraphDraft,
      phaseEdited: phaseGraphEditedRef.current,
    });
  }, [nodes, edges, contractView, requestGraphDraft, responseGraphDraft, errorResponseGraphDraft]);
  const currentGraph = currentGraphs.request;
  const currentResponseGraph = currentGraphs.response;
  const currentErrorResponseGraph = currentGraphs.errorResponse;
  const graphKey = JSON.stringify(currentGraphs);
  const csvGraph = React.useMemo(() => {
    const flow = sanitizeCanvasFlowForPhase(contractView, { nodes, edges });
    return graphFromFlow(flow.nodes, flow.edges);
  }, [contractView, nodes, edges]);
  const csvContextBase = JSON.stringify([
    selectedIntegrationId, integrationLoadSequence, contractView, revision,
    interactionType, errorResponseObjectId, sourceFields, targetFields, errorResponseFields,
    name, rowsText, responsePayloadText,
  ]);
  const csvContextKey = JSON.stringify([csvContextBase, csvGraph]);
  const csvUnavailableReason = contractView === "overview"
    ? "Open a mapping tab to exchange CSV mappings."
    : contractView === "error-response" && !errorResponseObjectId
      ? "Choose an error response schema first."
      : loading || saving ? "Wait for the contract to finish loading or saving."
        : configError ? "Resolve the transformation configuration error first." : "";

  React.useEffect(() => {
    if (csvUndo && csvUndo.afterKey !== csvContextKey) setCsvUndo(null);
  }, [csvContextKey, csvUndo]);

  React.useEffect(() => {
    setCsvDialog(null);
  }, [selectedIntegrationId, contractView, integrationLoadSequence]);

  function applyCsvImport(graph: GraphDocument, expectedContext: string, count: number) {
    if (csvUnavailableReason || expectedContext !== csvContextKey || contractView === "overview") {
      setEditorError("CSV preview is out of date. Refresh it before applying the import.");
      return;
    }
    const actualEndpoint = (endpoint: "source" | "target") =>
      responsePhase ? endpoint === "source" ? "target" : "source" : endpoint;
    const flow = flowFromGraph(
      graph, activeSourceFields, activeTargetFields, canvasSourceObject, canvasTargetObject,
      (endpoint) => setQuickAddEndpoint(actualEndpoint(endpoint)),
      (endpoint, field) => setEditingField({ endpoint: actualEndpoint(endpoint), field }),
      (endpoint, field) => { void deleteFieldRef.current(actualEndpoint(endpoint), field); },
    );
    const existingIds = new Set(csvGraph.nodes.map((node) => node.id));
    const importedIds = new Set(graph.nodes.filter((node) => !existingIds.has(node.id)).map((node) => node.id));
    const laidOut = applyWorkbenchLayout(flow.nodes, flow.edges, phaseLayoutContext(contractView), {
      preservePersisted: true, repositionNodeIds: importedIds,
    });
    const nextNodes = laidOut.map((node) => ({ ...node, data: { ...node.data, phase: contractView } }));
    const nextEdges = flow.edges.map((edge) => ({ ...edge, data: { ...edge.data, phase: contractView } }));
    setCsvUndo({
      nodes, edges, dirty, phaseEdited: { ...phaseGraphEditedRef.current },
      afterKey: JSON.stringify([csvContextBase, graphFromFlow(nextNodes, nextEdges)]),
    });
    viewOnlyFallbackNodeIdsRef.current[contractView] = new Set();
    markActivePhaseGraphEdited();
    setNodes(nextNodes);
    setEdges(nextEdges);
    setDirty(true);
    setCsvDialog(null);
    setSelectedNodeId("");
    setSelectedEdgeId("");
    setSelectedMatrixRowId("");
    setConnectionAssist(null);
    setDrawerView(null);
    setEditorError("");
    setEditorNotice(`Applied ${count} CSV mapping changes to this tab's draft. Inspect the mappings, then Save, or Undo import.`);
    frameCanvas();
  }

  function undoCsvImport() {
    if (!csvUndo || csvUndo.afterKey !== csvContextKey) {
      setEditorError("This import can no longer be undone because the draft changed.");
      return;
    }
    phaseGraphEditedRef.current = { ...csvUndo.phaseEdited };
    setNodes(csvUndo.nodes);
    setEdges(csvUndo.edges);
    setDirty(csvUndo.dirty);
    setCsvUndo(null);
    setSelectedNodeId("");
    setSelectedEdgeId("");
    setSelectedMatrixRowId("");
    setDrawerView(null);
    setConnectionAssist(null);
    setEditorNotice("CSV import undone. Your previous draft has been restored.");
    frameCanvas();
  }
  function markActivePhaseGraphEdited() {
    if (contractView === "overview") return;
    phaseGraphEditedRef.current[contractView] = true;
  }

  function phaseLayoutContext(phase: ContractView, readRenderedHandles = false): WorkbenchLayoutContext {
    const response = isResponsePhase(phase);
    const layoutSourceFields = response
      ? phase === "error-response" ? errorResponseFields : targetFields
      : sourceFields;
    const layoutTargetFields = response ? sourceFields : targetFields;
    const sourceHandleCenters = new Map<string, number>();
    const targetHandleCenters = new Map<string, number>();
    if (readRenderedHandles && flowShellRef.current && flowInstance.current) {
      const readCenters = (nodeType: "source" | "target", fields: CatalogField[], result: Map<string, number>) => {
        const node = nodes.find((item) => item.type === nodeType);
        if (!node) return;
        for (const field of fields) {
          const handle = [...flowShellRef.current!.querySelectorAll<HTMLElement>(".react-flow__handle")]
            .find((item) => item.dataset.nodeid === node.id && item.dataset.handleid === `field:${field.id}`);
          if (!handle) continue;
          const rect = handle.getBoundingClientRect();
          const point = flowInstance.current!.screenToFlowPosition({
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          });
          result.set(field.id, point.y);
        }
      };
      readCenters("source", layoutSourceFields, sourceHandleCenters);
      readCenters("target", layoutTargetFields, targetHandleCenters);
    }
    return {
      sourceFields: layoutSourceFields,
      targetFields: layoutTargetFields,
      ...(sourceHandleCenters.size ? { sourceHandleCenters } : {}),
      ...(targetHandleCenters.size ? { targetHandleCenters } : {}),
    };
  }

  function frameCanvas(duration = 220) {
    window.requestAnimationFrame(() => {
      void flowInstance.current?.fitView({
        padding: 0.18,
        minZoom: 0.72,
        maxZoom: 1.05,
        duration,
      });
    });
  }

  function loadPhaseCanvas(phase: ContractView, options?: { applyAutoLayout?: boolean; markDirty?: boolean }) {
    if (phase === "overview") return;
    const resetLayout = options?.applyAutoLayout === true;
    const loadedFlow = sanitizeCanvasFlowForPhase(phase, flowForPhase(phase));
    const currentNodeById = new Map(nodes.map((node) => [node.id, node]));
    const flow = resetLayout
      ? {
        ...loadedFlow,
        nodes: loadedFlow.nodes.map((node) => {
          const measured = currentNodeById.get(node.id)?.measured;
          return measured ? { ...node, measured } : node;
        }),
      }
      : loadedFlow;
    viewOnlyFallbackNodeIdsRef.current[phase] = new Set(
      flow.nodes.filter((node) => !["source", "target"].includes(node.type) && !hasPersistedPosition(node))
        .map((node) => node.id),
    );
    const positionedNodes = applyWorkbenchLayout(
      flow.nodes,
      flow.edges,
      phaseLayoutContext(phase, resetLayout),
      { preservePersisted: !resetLayout },
    );
    const phaseEdges = flow.edges.map((edge) => ({
      ...edge,
      data: { ...edge.data, phase },
    }));
    const phaseNodes = positionedNodes.map((node) => ({
      ...node,
      data: { ...node.data, phase },
    }));
    const phaseSwitchToken = ++phaseSwitchTokenRef.current;
    activeCanvasPhaseRef.current = phase;
    suppressDirtyRef.current = true;
    setNodes(phaseNodes);
    setEdges(phaseEdges);
    setConnectionError("");
    window.requestAnimationFrame(() => {
      if (phaseSwitchTokenRef.current === phaseSwitchToken) suppressDirtyRef.current = false;
    });
    frameCanvas(resetLayout ? 240 : 160);
    if (options?.markDirty) setDirty(true);
  }

  React.useEffect(() => {
    if (contractView === "overview" || !flowShellRef.current || !flowInstance.current) return;
    const pendingIds = viewOnlyFallbackNodeIdsRef.current[contractView];
    if (!pendingIds.size) return;
    const frame = window.requestAnimationFrame(() => {
      if (!flowShellRef.current || !flowInstance.current) return;
      const laidOut = applyWorkbenchLayout(
        nodes,
        edges,
        phaseLayoutContext(contractView, true),
        { preservePersisted: true, repositionNodeIds: pendingIds },
      );
      viewOnlyFallbackNodeIdsRef.current[contractView] = new Set();
      setNodes((current) => current.map((node) => {
        const next = laidOut.find((item) => item.id === node.id);
        return next ? { ...node, position: next.position } : node;
      }));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [canvasReadyVersion, contractView, nodes, edges]);

  React.useEffect(() => {
    if (!pendingErrorCanvasObjectId) return;
    if (pendingErrorCanvasObjectId !== errorResponseObjectId) {
      setPendingErrorCanvasObjectId("");
      return;
    }
    if (contractView !== "error-response") {
      setPendingErrorCanvasObjectId("");
      return;
    }
    if (errorResponseCatalogObject?.id !== errorResponseObjectId || !flowInstance.current) return;
    setPendingErrorCanvasObjectId("");
    loadPhaseCanvas("error-response", { applyAutoLayout: true });
  }, [pendingErrorCanvasObjectId, errorResponseObjectId, errorResponseCatalogObject, errorResponseFields, contractView, canvasReadyVersion]);

  function resetLayout() {
    if (contractView === "overview") return;
    markActivePhaseGraphEdited();
    loadPhaseCanvas(contractView, { applyAutoLayout: true, markDirty: true });
  }

  function flowForPhase(phase: ContractView) {
    if (phase === "error-response" && !errorResponseObjectId) {
      return { nodes: [], edges: [] };
    }
    const response = isResponsePhase(phase);
    const phaseGraph = phase === "request"
      ? requestGraphDraft
      : usesSuccessResponseGraph(phase)
        ? graphWithEndpoints(responseGraphDraft, requestGraphDraft)
        : graphWithEndpoints(errorResponseGraphDraft, requestGraphDraft);
    const graph = response ? orientResponseGraph(phaseGraph) : phaseGraph;
    const actualEndpoint = (endpoint: "source" | "target") =>
      response ? endpoint === "source" ? "target" : "source" : endpoint;
    return flowFromGraph(
      graph,
      phase === "request" ? sourceFields : phase === "error-response" ? errorResponseFields : targetFields,
      phase === "request" ? targetFields : sourceFields,
      phase === "request" ? sourceCatalogObject : phase === "error-response" ? errorResponseCatalogObject : targetCatalogObject,
      phase === "request" ? targetCatalogObject : sourceCatalogObject,
      (endpoint) => setQuickAddEndpoint(actualEndpoint(endpoint)),
      (endpoint, field) => setEditingField({ endpoint: actualEndpoint(endpoint), field }),
      (endpoint, field) => { void deleteFieldRef.current(actualEndpoint(endpoint), field); },
    );
  }
  const renderedEdges = React.useMemo(() => {
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const sourceById = new Map(canvasSourceFields.map((field) => [field.id, field]));
    const targetById = new Map(canvasTargetFields.map((field) => [field.id, field]));
    const parallelEdgeIndexes = new Map<string, number>();
    const phase: MappingPhase = contractView === "request"
      ? "request"
      : contractView === "error-response"
        ? "error-response"
        : contractView === "async-response"
          ? "async-response"
          : "success-response";
    return edges.map((edge) => {
      const sourceNode = nodeById.get(edge.source);
      const targetNode = nodeById.get(edge.target);
      const sourceId = edge.sourceHandle?.startsWith("field:")
        ? edge.sourceHandle.slice("field:".length)
        : "";
      const targetId = edge.targetHandle?.startsWith("field:")
        ? edge.targetHandle.slice("field:".length)
        : "";
      const direction = edge.data?.direction ?? "outbound";
      const sourceField = sourceNode?.type === (direction === "inbound" ? "target" : "source")
        ? (direction === "inbound" ? targetById : sourceById).get(sourceId)
        : undefined;
      const targetField = targetNode?.type === (direction === "inbound" ? "source" : "target")
        ? (direction === "inbound" ? sourceById : targetById).get(targetId)
        : undefined;
      const incompatible = sourceField && targetField
        && sourceField.data_type.trim().toLowerCase() !== targetField.data_type.trim().toLowerCase();
      const pairKey = `${edge.source}:${edge.target}`;
      const parallelEdgeIndex = parallelEdgeIndexes.get(pairKey) ?? 0;
      parallelEdgeIndexes.set(pairKey, parallelEdgeIndex + 1);
      const sourceType = sourceNode?.type;
      const targetType = targetNode?.type;
      const directSchemaLink = (
        (sourceType === "source" || sourceType === "target")
        && (targetType === "source" || targetType === "target")
      );
      const routeOffset = directSchemaLink
        ? 12 + parallelEdgeIndex * 8
        : 12;
      const validationMeta = edgeValidationById.get(edge.id);
      const rowForEdge = matrixRowByEdgeId.get(edge.id);
      const mapperData = {
        ...edge.data,
        direction,
        routeOffset,
        straightWhenAligned: true,
        phase,
        validationStatus: validationMeta?.status,
        validationIssue: validationMeta?.issue ?? "",
        onIssueHover: rowForEdge ? (active: boolean) => hoverIssueChain(rowForEdge, active) : undefined,
        onIssueSelect: rowForEdge ? () => selectChainByRow(rowForEdge, { anchorEdgeId: edge.id }) : undefined,
      };
      return incompatible
        ? {
          ...edge,
          type: "mapper-edge" as const,
          zIndex: 1000,
          data: mapperData,
          label: "Implicit cast",
          labelStyle: { fill: "#805a16", fontSize: 10, fontWeight: 650 },
          labelBgStyle: { fill: "#fff5d9", fillOpacity: 0.96 },
          labelBgPadding: [5, 3] as [number, number],
          labelBgBorderRadius: 4,
          style: { ...edge.style, strokeWidth: 2.5 },
        }
        : { ...edge, type: "mapper-edge" as const, zIndex: 1000, data: mapperData };
    });
  }, [
    edges,
    nodes,
    canvasSourceFields,
    canvasTargetFields,
    contractView,
    edgeValidationById,
    matrixRowByEdgeId,
    selectedEdgeId,
    selectedNodeId,
    mappingMatrixRows,
  ]);
  const canCreate =
    Boolean(name.trim() && sourceSystemId && sourceObjectId && targetSystemId && targetObjectId);

  const loadCatalog = React.useCallback(async () => {
    const allSystems = await list<System>("/api/catalog/systems");
    setSystems(allSystems);
    if (allSystems.length) {
      setSourceSystemId((current) => allSystems.some((item) => item.id === current) ? current : allSystems[0].id);
      setTargetSystemId((current) => allSystems.some((item) => item.id === current) ? current : allSystems[0].id);
      if (newIntegrationSystemId && allSystems.some((item) => item.id === newIntegrationSystemId)) {
        setSourceSystemId(newIntegrationSystemId);
        setTargetSystemId(
          allSystems.find((item) => item.id !== newIntegrationSystemId)?.id ?? newIntegrationSystemId,
        );
      }
    }
    const allIntegrations = await list<Integration>("/api/integrations");
    setIntegrations(allIntegrations);
    setSelectedIntegrationId((current) => {
      if (initialIntegrationId && allIntegrations.some((item) => item.id === initialIntegrationId)) {
        return initialIntegrationId;
      }
      if (newIntegrationSystemId) return "";
      return allIntegrations.some((item) => item.id === current) ? current : (allIntegrations[0]?.id ?? "");
    });
  }, [initialIntegrationId, newIntegrationSystemId]);

  React.useEffect(() => {
    void loadCatalog()
      .catch((error: unknown) => setEditorError(error instanceof Error ? error.message : "Could not load catalog."))
      .finally(() => setLoading(false));
  }, [loadCatalog]);

  React.useEffect(() => {
    if (!sourceSystemId) {
      setSourceObjects([]);
      setSourceObjectId("");
      return;
    }
    let active = true;
    void list<CatalogObject>(`/api/catalog/systems/${sourceSystemId}/objects`)
      .then((items) => {
        if (!active) return;
        setSourceObjects(items);
        setSourceObjectId((current) => items.some((item) => item.id === current) ? current : (items[0]?.id ?? ""));
      })
      .catch((error: unknown) => {
        if (active) setEditorError(error instanceof Error ? error.message : "Could not load source objects.");
      });
    return () => { active = false; };
  }, [sourceSystemId]);

  React.useEffect(() => {
    if (!targetSystemId) {
      setTargetObjects([]);
      setTargetObjectId("");
      return;
    }
    let active = true;
    void list<CatalogObject>(`/api/catalog/systems/${targetSystemId}/objects`)
      .then((items) => {
        if (!active) return;
        setTargetObjects(items);
        setTargetObjectId((current) => items.some((item) => item.id === current) ? current : (items[0]?.id ?? ""));
      })
      .catch((error: unknown) => {
        if (active) setEditorError(error instanceof Error ? error.message : "Could not load target objects.");
      });
    return () => { active = false; };
  }, [targetSystemId]);

  React.useEffect(() => {
    if (!sourceObjectId) {
      setSourceFields([]);
      return;
    }
    let active = true;
    void list<CatalogField>(`/api/catalog/objects/${sourceObjectId}/fields`)
      .then((items) => { if (active) setSourceFields(items); })
      .catch((error: unknown) => {
        if (active) setEditorError(error instanceof Error ? error.message : "Could not load source fields.");
      });
    return () => { active = false; };
  }, [sourceObjectId]);

  React.useEffect(() => {
    if (!targetObjectId) {
      setTargetFields([]);
      return;
    }
    let active = true;
    void list<CatalogField>(`/api/catalog/objects/${targetObjectId}/fields`)
      .then((items) => { if (active) setTargetFields(items); })
      .catch((error: unknown) => {
        if (active) setEditorError(error instanceof Error ? error.message : "Could not load target fields.");
      });
    return () => { active = false; };
  }, [targetObjectId]);

  React.useEffect(() => {
    simulationRequest.current += 1;
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!selectedIntegration) {
      activeCanvasPhaseRef.current = "overview";
      setNodes([]);
      setEdges([]);
      setRevision(0);
      setDirty(false);
      setArchitecture(null);
      setSimulation(null);
      setSimulationLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setSimulation(null);
    setSimulationLoading(false);
    setArchitecture(null);
    setDependencyCandidateId("");
    setConnectionAssist(null);
    void Promise.all([
      api<System>(`/api/catalog/systems/${selectedIntegration.source_system_id}`),
      api<System>(`/api/catalog/systems/${selectedIntegration.target_system_id}`),
      api<CatalogObject>(`/api/catalog/objects/${selectedIntegration.source_object_id}`),
      api<CatalogObject>(`/api/catalog/objects/${selectedIntegration.target_object_id}`),
      list<CatalogField>(`/api/catalog/objects/${selectedIntegration.source_object_id}/fields`),
      list<CatalogField>(`/api/catalog/objects/${selectedIntegration.target_object_id}/fields`),
      selectedIntegration.error_response_object_id
        ? api<CatalogObject>(`/api/catalog/objects/${selectedIntegration.error_response_object_id}`)
        : Promise.resolve(null),
      selectedIntegration.error_response_object_id
        ? list<CatalogField>(`/api/catalog/objects/${selectedIntegration.error_response_object_id}/fields`)
        : Promise.resolve([] as CatalogField[]),
      api<ArchitectureAnalysis>("/api/integrations/architecture"),
    ]).then(([
      sourceSystemDetail,
      targetSystemDetail,
      sourceObject,
      targetObject,
      sourceFieldList,
      targetFieldList,
      errorResponseObject,
      errorResponseFieldList,
      nextArchitecture,
    ]) => {
      if (!active) return;
      setSourceSystemId(sourceSystemDetail.id);
      setTargetSystemId(targetSystemDetail.id);
      setSourceObjectId(sourceObject.id);
      setTargetObjectId(targetObject.id);
      setSourceCatalogObject(sourceObject);
      setTargetCatalogObject(targetObject);
      setErrorResponseCatalogObject(errorResponseObject ?? undefined);
      setSourceObjectLabel(sourceObject.label);
      setTargetObjectLabel(targetObject.label);
      setSourceFields(sourceFieldList);
      setTargetFields(targetFieldList);
      setErrorResponseObjectId(errorResponseObject?.id ?? "");
      setErrorResponseFields(errorResponseFieldList);
      setArchitecture(nextArchitecture);
      setName(selectedIntegration.name);
      setRevision(selectedIntegration.revision);
      setInteractionType(selectedIntegration.interaction_type ?? "ONE_WAY");
      setRequestGraphDraft(selectedIntegration.graph);
      const savedResponseGraph = graphWithEndpoints(
        selectedIntegration.response_graph ?? { version: 1 as const, nodes: [], edges: [] },
        selectedIntegration.graph,
      );
      setResponseGraphDraft(savedResponseGraph);
      const savedErrorResponseGraph = selectedIntegration.error_response_graph
        ?? { version: 1 as const, nodes: [], edges: [] };
      setErrorResponseGraphDraft(savedErrorResponseGraph);
      phaseGraphEditedRef.current = {
        request: false,
        "success-response": false,
        "error-response": false,
        "async-response": false,
      };
      setContractView("overview");
      activeCanvasPhaseRef.current = "request";
      setResponsePayloadText(JSON.stringify([{
        rowId: "response-1",
        values: Object.fromEntries(targetFieldList.map((field) => [field.id, null])),
      }], null, 2));
      setSampleMode("form");
      setSamplePanelExpanded(false);
      const savedRows = selectedIntegration.sample_rows ?? [];
      setRowsText(JSON.stringify(
        savedRows.length
          ? savedRows
          : [{ rowId: "sample-1", values: Object.fromEntries(sourceFieldList.map((field) => [field.id, null])) }],
        null,
        2,
      ));
      const canvasFlow = flowFromGraph(
        selectedIntegration.graph,
        sourceFieldList,
        targetFieldList,
        sourceObject,
        targetObject,
        setQuickAddEndpoint,
        (endpoint, field) => setEditingField({ endpoint, field }),
        (endpoint, field) => { void deleteFieldRef.current(endpoint, field); },
      );
      suppressDirtyRef.current = true;
      setNodes(canvasFlow.nodes);
      setEdges(canvasFlow.edges);
      window.requestAnimationFrame(() => { suppressDirtyRef.current = false; });
      setSelectedNodeId("");
      setSelectedEdgeId("");
      setDrawerView(null);
      setDirty(false);
      setSimulation(null);
      setEditorError("");
      setScenariosOpen(false);
      setLoadedContractKey(`${selectedIntegration.id}:${Date.now()}`);
    }).catch((error: unknown) => {
      if (active) setEditorError(error instanceof Error ? error.message : "Could not load contract.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [selectedIntegrationId, integrationLoadSequence]);

  React.useEffect(() => {
    const generation = ++simulationRequest.current;
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    setSimulationLoading(false);
    if (!selectedIntegration || loading) {
      if (!selectedIntegration) setSimulation(null);
      return;
    }
    if (
      configError
      || !parsedSampleRows.rows
      || (interactionType !== "ONE_WAY" && !parsedResponsePayload.rows)
    ) {
      setSimulation(null);
      return;
    }
    const timer = setTimeout(() => {
      if (generation === simulationRequest.current) {
        void runSimulation(currentGraph, currentResponseGraph);
      }
    }, 300);
    debounceTimer.current = timer;
    return () => clearTimeout(timer);
  }, [
    graphKey,
    rowsText,
    responsePayloadText,
    currentGraph,
    currentResponseGraph,
    interactionType,
    selectedIntegrationId,
    loading,
    configError,
  ]);

  React.useEffect(() => {
    const outputByNodeId = new Map(
      (selectedRow?.trace ?? []).map((entry) => [entry.nodeId, JSON.stringify(entry.outputs)]),
    );
    setNodes((items) => items.map((node) => ({
      ...node,
      data: {
        ...node.data,
        evaluation: outputByNodeId.get(node.id),
      },
    })));
  }, [selectedRow]);

  React.useEffect(() => {
    const pruned = pruneSelectionForActiveFlow(selectedNodeId, selectedEdgeId, nodes, edges);
    if (pruned.nodeId !== selectedNodeId) setSelectedNodeId(pruned.nodeId);
    if (pruned.edgeId !== selectedEdgeId) setSelectedEdgeId(pruned.edgeId);
  }, [nodes, edges, selectedNodeId, selectedEdgeId]);

  React.useEffect(() => {
    const resolved = resolveMatrixRowSelection(mappingMatrixRows, selectedNodeId, selectedEdgeId);
    if (resolved !== selectedMatrixRowId) setSelectedMatrixRowId(resolved);
  }, [mappingMatrixRows, selectedNodeId, selectedEdgeId, selectedMatrixRowId]);

  function selectChainByRow(row: MappingMatrixRow, options?: { openCanvas?: boolean; anchorEdgeId?: string }) {
    if (options?.openCanvas) setWorkbenchView("canvas");
    setSelectedMatrixRowId(row.id);
    const selectedNodeIds = new Set(row.graphNodeIds);
    const selectedEdgeIds = new Set(row.graphEdgeIds);
    setNodes((items) => items.map((node) => ({ ...node, selected: selectedNodeIds.has(node.id) })));
    setEdges((items) => items.map((edge) => ({ ...edge, selected: selectedEdgeIds.has(edge.id) })));
    if (row.graphEdgeIds.length) {
      setSelectedEdgeId(options?.anchorEdgeId && row.graphEdgeIds.includes(options.anchorEdgeId)
        ? options.anchorEdgeId
        : row.primaryIssueEdgeId && row.graphEdgeIds.includes(row.primaryIssueEdgeId)
          ? row.primaryIssueEdgeId
          : row.graphEdgeIds[row.graphEdgeIds.length - 1]!);
      setSelectedNodeId("");
      setDrawerView("inspector");
      return;
    }
    if (row.graphNodeIds.length) {
      const node = nodes.find((item) => item.id === row.graphNodeIds[0]);
      if (node) {
        setSelectedNodeId(node.id);
        setSelectedEdgeId("");
        setConfigText(JSON.stringify(node.data.config, null, 2));
        setConfigError("");
        setDrawerView("inspector");
      }
    }
  }

  function selectMatrixRow(row: MappingMatrixRow, options?: { openCanvas?: boolean }) {
    selectChainByRow(row, options);
  }

  function hoverIssueChain(row: MappingMatrixRow, active: boolean) {
    if (active) {
      const selectedNodeIds = new Set(row.graphNodeIds);
      const selectedEdgeIds = new Set(row.graphEdgeIds);
      setNodes((items) => items.map((node) => ({ ...node, selected: selectedNodeIds.has(node.id) })));
      setEdges((items) => items.map((edge) => ({ ...edge, selected: selectedEdgeIds.has(edge.id) })));
      return;
    }
    const resolved = resolveMatrixRowSelection(mappingMatrixRows, selectedNodeId, selectedEdgeId);
    if (!resolved) {
      setNodes((items) => items.map((node) => ({ ...node, selected: false })));
      setEdges((items) => items.map((edge) => ({ ...edge, selected: false })));
      return;
    }
    const rowForSelection = mappingMatrixRows.find((item) => item.id === resolved);
    if (rowForSelection) selectChainByRow(rowForSelection);
  }

  function removeMatrixRowMapping(row: MappingMatrixRow) {
    if (row.graphEdgeIds.length === 0 || contractView === "overview") return;
    onEdgesChange(row.graphEdgeIds.map((id) => ({ id, type: "remove" })));
    setDrawerView(null);
  }

  function applySuggestedFix(row: MappingMatrixRow) {
    const suggestion = row.suggestedFix;
    if (!suggestion) return;
    if (suggestion.kind === "replace-function") {
      const node = nodes.find((item) => item.id === suggestion.nodeId);
      if (!node || node.type !== "fx") return;
      setNodes((items) => items.map((item) => {
        if (item.id !== suggestion.nodeId) return item;
        return {
          ...item,
          data: {
            ...item.data,
            config: {
              ...item.data.config,
              function: suggestion.to,
            },
          },
        };
      }));
      markActivePhaseGraphEdited();
      setDirty(true);
      setEditorNotice(`Applied fix: ${suggestion.fromLabel} → ${suggestion.toLabel}.`);
      window.setTimeout(() => setEditorNotice(""), 3500);
      selectChainByRow(row);
    }
  }

  async function createIntegration(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate) return;
    setEditorError("");
    setSaving(true);
    try {
      if (
        !sourceObjects.some((item) => item.id === sourceObjectId)
        || !targetObjects.some((item) => item.id === targetObjectId)
      ) {
        throw new Error("Choose available source and target objects.");
      }
      const sourceNodeId = newUuid();
      const targetNodeId = newUuid();
      const graph: GraphDocument = {
        version: 1,
        nodes: [
          { id: sourceNodeId, type: "source", position: { x: 80, y: 150 }, config: {} },
          { id: targetNodeId, type: "target", position: { x: 700, y: 150 }, config: {} },
        ],
        edges: [],
      };
      const created = await api<Integration>("/api/integrations", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          source_system_id: sourceSystemId,
          source_object_id: sourceObjectId,
          target_system_id: targetSystemId,
          target_object_id: targetObjectId,
          graph,
          sample_rows: [],
        }),
      });
      const next = await list<Integration>("/api/integrations");
      setIntegrations(next);
      setSelectedIntegrationId(created.id);
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not create contract.");
    } finally {
      setSaving(false);
    }
  }

  async function reloadIntegration() {
    if (!selectedIntegration) return;
    setEditorError("");
    try {
      const updated = await api<Integration>(`/api/integrations/${selectedIntegration.id}`);
      setIntegrations((items) => items.map((item) => item.id === updated.id ? updated : item));
      setIntegrationLoadSequence((sequence) => sequence + 1);
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not reload contract.");
    }
  }

  async function refreshFieldMetadata() {
    if (!selectedIntegration) return;
    setEditorError("");
    try {
      const [sourceFieldList, targetFieldList] = await Promise.all([
        list<CatalogField>(`/api/catalog/objects/${selectedIntegration.source_object_id}/fields`),
        list<CatalogField>(`/api/catalog/objects/${selectedIntegration.target_object_id}/fields`),
      ]);
      setSourceFields(sourceFieldList);
      setTargetFields(targetFieldList);
      setNodes((items) => items.map((node) => ({
        ...node,
        data: {
          ...node.data,
          fields: node.type === "source"
            ? sourceFieldList
            : node.type === "target"
              ? targetFieldList
              : node.data.fields,
        },
      })));
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not refresh field metadata.");
    }
  }

  async function createQuickField(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!quickAddEndpoint) return;
    const isErrorSchema = contractView === "error-response" && quickAddEndpoint === "target";
    const objectId = isErrorSchema
      ? errorResponseObjectId
      : quickAddEndpoint === "source" ? sourceObjectId : targetObjectId;
    const nameValue = quickFieldName.trim();
    if (!objectId || !nameValue) return;
    setQuickFieldSaving(true);
    setEditorError("");
    try {
      const created = await api<CatalogField>(`/api/catalog/objects/${objectId}/fields`, {
        method: "POST",
        body: JSON.stringify({
          name: nameValue,
          label: nameValue,
          data_type: quickFieldType.trim() || "string",
          required: false,
          nullable: true,
        }),
      });
      const currentFields = isErrorSchema
        ? errorResponseFields
        : quickAddEndpoint === "source" ? sourceFields : targetFields;
      const nextFields = [...currentFields, created]
        .sort((left, right) => left.position - right.position);
      const canvasEndpoint = isErrorSchema
        ? "source"
        : responsePhase
          ? quickAddEndpoint === "source" ? "target" : "source"
          : quickAddEndpoint;
      if (isErrorSchema) {
        setErrorResponseFields(nextFields);
        setNodes((items) => items.map((node) =>
          node.type === canvasEndpoint ? { ...node, data: { ...node.data, fields: nextFields } } : node,
        ));
      } else if (quickAddEndpoint === "source") {
        setSourceFields(nextFields);
        setNodes((items) => items.map((node) =>
          node.type === canvasEndpoint ? { ...node, data: { ...node.data, fields: nextFields } } : node,
        ));
      } else {
        setTargetFields(nextFields);
        setNodes((items) => items.map((node) =>
          node.type === canvasEndpoint ? { ...node, data: { ...node.data, fields: nextFields } } : node,
        ));
      }
      setQuickAddEndpoint(null);
      setQuickFieldName("");
      setQuickFieldType("string");
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not create field.");
    } finally {
      setQuickFieldSaving(false);
    }
  }

  function updateEndpointFields(endpoint: "source" | "target", nextFields: CatalogField[]) {
    const errorSchema = contractView === "error-response" && endpoint === "target";
    if (errorSchema) setErrorResponseFields(nextFields);
    else if (endpoint === "source") setSourceFields(nextFields);
    else setTargetFields(nextFields);
    const canvasEndpoint = responsePhase
      ? endpoint === "source" ? "target" : "source"
      : endpoint;
    setNodes((items) => items.map((node) =>
      node.type === canvasEndpoint
        ? { ...node, data: { ...node.data, fields: nextFields } }
        : node,
    ));
  }

  async function saveFieldEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingField) return;
    const form = new FormData(event.currentTarget);
    const nameValue = String(form.get("name") ?? "").trim();
    const dataType = String(form.get("data_type") ?? "").trim();
    if (!nameValue || !dataType) return;
    setFieldSaving(true);
    setEditorError("");
    try {
      const updated = await api<CatalogField>(`/api/catalog/fields/${editingField.field.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: nameValue,
          data_type: dataType,
          ...(editingField.field.label === editingField.field.name ? { label: nameValue } : {}),
        }),
      });
      const currentFields = editingField.endpoint === "source" ? sourceFields : targetFields;
      updateEndpointFields(editingField.endpoint, currentFields.map((field) =>
        field.id === updated.id ? updated : field,
      ));
      setEditingField(null);
      setEditorNotice(`Updated ${updated.label}.`);
      window.setTimeout(() => setEditorNotice(""), 3500);
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not update field.");
    } finally {
      setFieldSaving(false);
    }
  }

  async function deleteCanvasField(endpoint: "source" | "target", field: CatalogField) {
    if (!selectedIntegration) return;
    const canvasEndpoint = responsePhase
      ? endpoint === "source" ? "target" : "source"
      : endpoint;
    const externalReferences = integrations.filter((integration) =>
      integration.id !== selectedIntegration.id && integrationUsesField(integration, field.id),
    );
    if (externalReferences.length) {
      setEditorError(
        `Cannot delete ${field.label}; it is used by ${externalReferences.map((item) => item.name).join(", ")}. Remove its mappings and sample values from those contracts first.`,
      );
      return;
    }
    const endpointNodeIds = new Set(nodes.filter((node) => node.type === canvasEndpoint).map((node) => node.id));
    const portId = `field:${field.id}`;
    const connectedEdges = edges.filter((edge) =>
      (endpointNodeIds.has(edge.source) && edge.sourceHandle === portId)
      || (endpointNodeIds.has(edge.target) && edge.targetHandle === portId),
    );
    const confirmation = connectedEdges.length
      ? `This field is connected to ${connectedEdges.length} edges. Deleting it will remove these connections.`
      : `Delete field "${field.label}" from this object's schema?`;
    if (!window.confirm(confirmation)) return;

    let nextRows: SimulationRowInput[];
    try {
      const parsed: unknown = JSON.parse(rowsText);
      if (!Array.isArray(parsed)) throw new Error("Sample rows must be a JSON array.");
      nextRows = endpoint === "source"
        ? (parsed as SimulationRowInput[]).map((row) => ({
          ...row,
          values: Object.fromEntries(
            Object.entries(row.values).filter(([fieldId]) => fieldId !== field.id),
          ),
        }))
        : parsed as SimulationRowInput[];
    } catch (caught) {
      setEditorError(
        `Fix the sample rows JSON before deleting this ${endpoint} field: ${
          caught instanceof Error ? caught.message : "invalid JSON"
        }`,
      );
      return;
    }

    setEditorError("");
    const nextEdges = edges.filter((edge) => !connectedEdges.some((connected) => connected.id === edge.id));
    const currentHasReference = integrationUsesField(selectedIntegration, field.id);
    const withoutFieldEdges = (graph: GraphDocument): GraphDocument => ({
      ...graph,
      edges: graph.edges.filter((edge) =>
        edge.sourcePortId !== portId && edge.targetPortId !== portId,
      ),
    });
    const activeGraph = graphFromFlow(nodes, nextEdges);
    const requestGraph = withoutFieldEdges(contractView === "request" ? activeGraph : requestGraphDraft);
    const responseGraph = withoutFieldEdges(usesSuccessResponseGraph(contractView) ? activeGraph : responseGraphDraft);
    const errorResponseGraph = withoutFieldEdges(contractView === "error-response" ? activeGraph : errorResponseGraphDraft);
    const removedDraftMappings =
      requestGraph.edges.length !== requestGraphDraft.edges.length
      || responseGraph.edges.length !== responseGraphDraft.edges.length
      || errorResponseGraph.edges.length !== errorResponseGraphDraft.edges.length;
    try {
      if (currentHasReference) {
        const updated = await api<Integration>(`/api/integrations/${selectedIntegration.id}/graph`, {
          method: "PUT",
          body: JSON.stringify({
            expected_revision: revision,
            graph: requestGraph,
            response_graph: responseGraph,
            error_response_object_id: errorResponseObjectId || null,
            error_response_graph: errorResponseGraph,
            name: name.trim(),
            sample_rows: nextRows,
          }),
        });
        setRevision(updated.revision);
        setRequestGraphDraft(updated.graph);
        setResponseGraphDraft(updated.response_graph);
        setErrorResponseGraphDraft(updated.error_response_graph ?? { version: 1, nodes: [], edges: [] });
        setIntegrations((items) => items.map((item) => item.id === updated.id ? updated : item));
        setEdges(nextEdges);
        setRowsText(JSON.stringify(nextRows, null, 2));
        setDirty(false);
      }
      await api<void>(`/api/catalog/fields/${field.id}`, { method: "DELETE" });
      const remainingFields = (endpoint === "source" ? sourceFields : targetFields)
        .filter((item) => item.id !== field.id);
      updateEndpointFields(endpoint, remainingFields);
      setRequestGraphDraft(requestGraph);
      setResponseGraphDraft(responseGraph);
      setErrorResponseGraphDraft(errorResponseGraph);
      markActivePhaseGraphEdited();
      setEdges(nextEdges);
      if (endpoint === "source") setRowsText(JSON.stringify(nextRows, null, 2));
      if (!currentHasReference) {
        setDirty((wasDirty) => wasDirty || connectedEdges.length > 0
          || removedDraftMappings
          || (endpoint === "source" && nextRows.some((row, index) =>
            JSON.stringify(row.values) !== JSON.stringify((JSON.parse(rowsText) as SimulationRowInput[])[index]?.values),
          )));
      }
      setEditorNotice(`Deleted ${field.label}.`);
      window.setTimeout(() => setEditorNotice(""), 3500);
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not delete field.");
    }
  }

  deleteFieldRef.current = deleteCanvasField;

  function autoMapFields() {
    const sourceNode = nodes.find((node) => node.type === "source");
    const targetNode = nodes.find((node) => node.type === "target");
    if (!sourceNode || !targetNode) {
      setEditorError("Auto-map requires source and target nodes on the canvas.");
      return;
    }
    const usedSourceIds = new Set<string>();
    const usedTargetIds = new Set<string>();
    for (const edge of edges) {
      if (edge.data?.direction === "inbound") continue;
      if (edge.source === sourceNode.id && edge.sourceHandle?.startsWith("field:")) {
        usedSourceIds.add(edge.sourceHandle.slice("field:".length));
      }
      if (edge.target === targetNode.id && edge.targetHandle?.startsWith("field:")) {
        usedTargetIds.add(edge.targetHandle.slice("field:".length));
      }
    }
    const candidates = activeTargetFields.flatMap((target) =>
      activeSourceFields.map((source) => ({
        source,
        target,
        score: Math.max(
          fieldNameSimilarity(source.name, target.name),
          fieldNameSimilarity(source.name, target.label),
          fieldNameSimilarity(source.label, target.name),
          fieldNameSimilarity(source.label, target.label),
        ),
      })).filter((candidate) => candidate.score >= 0.8),
    );
    const bestUnique = (
      matches: typeof candidates,
      key: (candidate: typeof candidates[number]) => string,
    ) => {
      const bestByKey = new Map<string, typeof candidates>();
      for (const candidate of matches) {
        const id = key(candidate);
        const current = bestByKey.get(id) ?? [];
        if (!current.length || candidate.score > current[0].score) bestByKey.set(id, [candidate]);
        else if (candidate.score === current[0].score) current.push(candidate);
      }
      return new Map([...bestByKey].flatMap(([id, best]) => best.length === 1 ? [[id, best[0]]] : []));
    };
    const bestByTarget = bestUnique(candidates, (candidate) => candidate.target.id);
    const bestBySource = bestUnique(candidates, (candidate) => candidate.source.id);
    const additions: FlowEdge[] = [];
    for (const candidate of candidates.sort((left, right) => right.score - left.score)) {
      if (
        bestByTarget.get(candidate.target.id) !== candidate
        || bestBySource.get(candidate.source.id) !== candidate
        || usedSourceIds.has(candidate.source.id)
        || usedTargetIds.has(candidate.target.id)
      ) continue;
      additions.push({
        id: newUuid(),
        source: sourceNode.id,
        sourceHandle: `field:${candidate.source.id}`,
        target: targetNode.id,
        targetHandle: `field:${candidate.target.id}`,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
      usedSourceIds.add(candidate.source.id);
      usedTargetIds.add(candidate.target.id);
    }
    if (additions.length) {
      setEdges((current) => [...current, ...additions]);
      markActivePhaseGraphEdited();
      setDirty(true);
    }
    setEditorError("");
    setEditorNotice(`Auto-mapped ${additions.length} matching field${additions.length === 1 ? "" : "s"}.`);
    window.setTimeout(() => setEditorNotice(""), 3500);
  }

  function updateSampleRows(rows: SimulationRowInput[]) {
    setRowsText(JSON.stringify(rows, null, 2));
    setDirty(true);
    setEditorError("");
  }

  function addSampleRow() {
    if (!parsedSampleRows.rows || parsedSampleRows.rows.length >= 100) return;
    const nextIndex = parsedSampleRows.rows.length;
    updateSampleRows([
      ...parsedSampleRows.rows,
      {
        rowId: `sample-${newUuid()}`,
        values: Object.fromEntries(sourceFields.map((field) => [field.id, null])),
      },
    ]);
    setEditorNotice(`Added sample row ${nextIndex + 1}.`);
    window.setTimeout(() => setEditorNotice(""), 2500);
  }

  function removeSampleRow(index: number) {
    if (!parsedSampleRows.rows) return;
    updateSampleRows(parsedSampleRows.rows.filter((_, rowIndex) => rowIndex !== index));
  }

  function updateSampleCell(rowIndex: number, fieldId: string, value: unknown) {
    if (!parsedSampleRows.rows) return;
    updateSampleRows(parsedSampleRows.rows.map((row, index) =>
      index === rowIndex
        ? { ...row, values: { ...row.values, [fieldId]: value } }
        : row,
    ));
  }

  function generateMockRows() {
    if (!sourceFields.length) {
      setEditorError("Add fields to the source object before generating sample data.");
      return;
    }
    const generated = Array.from({ length: 3 }, (_, rowIndex): SimulationRowInput => ({
      rowId: `sample-${newUuid()}`,
      values: Object.fromEntries(
        sourceFields.map((field) => [field.id, mockSampleValue(field, rowIndex)]),
      ),
    }));
    updateSampleRows(generated);
    setSampleMode("form");
    setSamplePanelExpanded(true);
    setEditorNotice("Generated 3 sample rows from the source schema.");
    window.setTimeout(() => setEditorNotice(""), 3500);
  }

  function selectContractView(nextView: ContractView) {
    if (contractView !== "overview") {
      if (
        (contractView === "request" && phaseGraphEditedRef.current.request)
        || (usesSuccessResponseGraph(contractView)
          && (phaseGraphEditedRef.current["success-response"] || phaseGraphEditedRef.current["async-response"]))
        || (isErrorResponsePhase(contractView) && phaseGraphEditedRef.current["error-response"])
      ) {
        const phaseFlow = sanitizeCanvasFlowForPhase(contractView, { nodes, edges });
        const activeGraph = graphFromFlow(phaseFlow.nodes, phaseFlow.edges);
        if (contractView === "request") setRequestGraphDraft(activeGraph);
        else if (usesSuccessResponseGraph(contractView)) setResponseGraphDraft(activeGraph);
        else setErrorResponseGraphDraft(activeGraph);
      }
    }
    setConnectionAssist(null);
    setSelectedNodeId("");
    setSelectedEdgeId("");
    setDrawerView(null);
    setScenariosOpen(false);
    setContractView(nextView);
    loadPhaseCanvas(nextView);
  }

  function openScenarios() {
    if (contractView !== "overview") selectContractView("overview");
    setDrawerView(null);
    setScenariosOpen(true);
  }

  React.useEffect(() => {
    const pending = pendingContractViewRef.current;
    if (!pending || !loadedContractKey.startsWith(`${pending.integrationId}:`)) return;
    pendingContractViewRef.current = null;
    if (pending.view === "scenarios") openScenarios();
    else if (pending.view !== "overview" && phaseAvailable(pending.view)) selectContractView(pending.view);
  }, [loadedContractKey]);

  function phaseAvailable(phase: MappingPhase) {
    if (phase === "request") return true;
    if (phase === "async-response") return interactionType === "ASYNC_CALLBACK";
    return interactionType === "REQUEST_RESPONSE";
  }

  function openScenarioContractPhase(contractId: string, phase: MappingPhase) {
    if (contractId === selectedIntegrationId) {
      selectContractView(phaseAvailable(phase) ? phase : "overview");
      return;
    }
    if (!integrations.some((item) => item.id === contractId)) return;
    if (dirty && !window.confirm("Discard unsaved contract changes and open the other contract?")) return;
    pendingContractViewRef.current = { integrationId: contractId, view: phase };
    setEditorError("");
    setDirty(false);
    setDrawerView(null);
    setSelectedIntegrationId(contractId);
  }

  async function saveGraph() {
    if (!selectedIntegration) return;
    setEditorError("");
    const sampleRows = parsedSampleRows.rows;
    if (!sampleRows) {
      setEditorError(parsedSampleRows.error);
      return;
    }
    setSaving(true);
    try {
      const updated = await api<Integration>(
        `/api/integrations/${selectedIntegration.id}/graph`,
        {
          method: "PUT",
          body: JSON.stringify({
          expected_revision: revision,
          graph: currentGraph,
          response_graph: currentResponseGraph,
          error_response_object_id: errorResponseObjectId || null,
          error_response_graph: currentErrorResponseGraph,
          interaction_type: interactionType,
          name: name.trim(),
          sample_rows: sampleRows,
          }),
        },
      );
      setRevision(updated.revision);
      setRequestGraphDraft(updated.graph);
      setResponseGraphDraft(updated.response_graph);
      setErrorResponseObjectId(updated.error_response_object_id ?? "");
      setErrorResponseGraphDraft(updated.error_response_graph ?? { version: 1, nodes: [], edges: [] });
      phaseGraphEditedRef.current = {
        request: false,
        "success-response": false,
        "error-response": false,
        "async-response": false,
      };
      setIntegrations((items) => items.map((item) => item.id === updated.id ? updated : item));
      setDirty(false);
      setEditorError("");
      try {
        await refreshArchitecture();
      } catch (caught) {
        setEditorError(
          `Contract saved, but design validation could not be refreshed: ${
            caught instanceof Error ? caught.message : "request failed"
          }`,
        );
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setEditorError(`${caught.message} Use Reload to discard local changes and load the current version.`);
      } else {
        setEditorError(caught instanceof Error ? caught.message : "Could not save contract.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function refreshArchitecture() {
    const next = await api<ArchitectureAnalysis>("/api/integrations/architecture");
    setArchitecture(next);
    return next;
  }

  async function addDependency() {
    if (!selectedIntegration || !dependencyCandidateId) return;
    setDependencySaving(true);
    setEditorError("");
    try {
      await api(`/api/integrations/${dependencyCandidateId}/dependencies`, {
        method: "POST",
        body: JSON.stringify({ downstream_integration_id: selectedIntegration.id }),
      });
      setDependencyCandidateId("");
      await refreshArchitecture();
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not add the dependency.");
    } finally {
      setDependencySaving(false);
    }
  }

  async function removeDependency(upstreamIntegrationId: string) {
    if (!selectedIntegration) return;
    setDependencySaving(true);
    setEditorError("");
    try {
      await api(
        `/api/integrations/${upstreamIntegrationId}/dependencies/${selectedIntegration.id}`,
        { method: "DELETE" },
      );
      await refreshArchitecture();
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not remove the dependency.");
    } finally {
      setDependencySaving(false);
    }
  }

  async function changeErrorResponseObject(objectId: string) {
    setErrorResponseObjectId(objectId);
    setErrorResponseGraphDraft({ version: 1, nodes: [], edges: [] });
    phaseGraphEditedRef.current["error-response"] = true;
    setErrorResponseFields([]);
    setErrorResponseCatalogObject(undefined);
    setDirty(true);
    if (!objectId) {
      if (contractView === "error-response") {
        suppressDirtyRef.current = true;
        setNodes([]);
        setEdges([]);
        window.requestAnimationFrame(() => { suppressDirtyRef.current = false; });
      }
      return;
    }
    try {
      const [object, fields] = await Promise.all([
        api<CatalogObject>(`/api/catalog/objects/${objectId}`),
        list<CatalogField>(`/api/catalog/objects/${objectId}/fields`),
      ]);
      setErrorResponseCatalogObject(object);
      setErrorResponseFields(fields);
      // Load after the new schema state commits; calling loadPhaseCanvas here would read stale (empty) fields.
      setPendingErrorCanvasObjectId(objectId);
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "Could not load error response schema.");
    }
  }

  function updateInteractionType(nextType: InteractionType) {
    setInteractionType(nextType);
    if (nextType === "ONE_WAY" && responsePhase) selectContractView("request");
    setDirty(true);
  }

  async function runSimulation(graph: GraphDocument, responseGraph: GraphDocument) {
    if (!selectedIntegration) return;
    const requestId = ++simulationRequest.current;
    setSimulationLoading(true);
    try {
      if (!parsedSampleRows.rows) throw new Error(parsedSampleRows.error);
      if (interactionType !== "ONE_WAY" && !parsedResponsePayload.rows) {
        throw new Error(parsedResponsePayload.error);
      }
      const result = await api<SimulationResult>(
        `/api/integrations/${selectedIntegration.id}/dry-run`,
        {
          method: "POST",
          body: JSON.stringify({
            expectedRevision: revision || undefined,
            graph,
            responseGraph,
            rows: parsedSampleRows.rows,
            ...(interactionType !== "ONE_WAY"
              ? { responsePayload: parsedResponsePayload.rows }
              : {}),
            options: { includeTraceValues: true },
          }),
        },
      );
      if (requestId !== simulationRequest.current) return;
      setSimulation(result);
      setSelectedRowIndex(0);
      setEditorError("");
    } catch (caught) {
      if (requestId !== simulationRequest.current) return;
      setSimulation(null);
      setEditorError(caught instanceof Error ? caught.message : "Simulation failed.");
    } finally {
      if (requestId === simulationRequest.current) setSimulationLoading(false);
    }
  }

  function updateConfig(text: string) {
    setCsvUndo(null);
    setConfigText(text);
    try {
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Node configuration must be a JSON object.");
      }
      const node = nodes.find((item) => item.id === selectedNodeId);
      if (!node) return;
      const config = parsed as Record<string, unknown>;
      setConfigError("");
      setNodes((items) => items.map((item) =>
        item.id === node.id
          ? { ...item, data: { ...item.data, config }, ...(node.type === "fx" ? { data: { ...item.data, config, label: String(config.function ?? "Function") } } : {}) }
          : item,
      ));
      markActivePhaseGraphEdited();
      setDirty(true);
    } catch (caught) {
      setConfigError(caught instanceof Error ? caught.message : "Invalid node configuration.");
    }
  }

  function addTransform(type: GraphNodeType) {
    const nodeId = newUuid();
    const node: FlowNode = {
      id: nodeId,
      type,
      position: { x: 360 + Math.random() * 80, y: 280 + Math.random() * 80 },
      deletable: true,
      data: {
        label: NODE_LABELS[type],
        config: defaultNodeConfig(type),
        direction: "outbound",
        phase: contractView,
      },
    };
    setNodes((items) => [...items, node]);
    setSelectedNodeId(nodeId);
    setSelectedEdgeId("");
    setDrawerView("inspector");
    setConfigText(JSON.stringify(node.data.config, null, 2));
    setConfigError("");
    markActivePhaseGraphEdited();
    setDirty(true);
  }

  function removeNode(nodeId: string) {
    setNodes((items) => items.filter((node) => node.id !== nodeId));
    setEdges((items) => items.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
    if (selectedNodeId === nodeId) {
      setSelectedNodeId("");
      setDrawerView(null);
    }
    markActivePhaseGraphEdited();
    setDirty(true);
  }

  const onNodesChange = React.useCallback((changes: NodeChange<FlowNode>[]) => {
    if (contractView !== activeCanvasPhaseRef.current) return;
    const safeChanges = changes.filter((change) =>
      change.type !== "remove"
      || !["source", "target"].includes(nodes.find((node) => node.id === change.id)?.type ?? ""),
    );
    setNodes((items) => applyNodeChanges(safeChanges, items));
    if (!suppressDirtyRef.current && safeChanges.some((change) => change.type === "remove")) {
      if (contractView !== "overview") phaseGraphEditedRef.current[contractView] = true;
      setDirty(true);
    }
  }, [nodes, contractView]);
  const onEdgesChange = React.useCallback((changes: EdgeChange<FlowEdge>[]) => {
    if (contractView !== activeCanvasPhaseRef.current) return;
    setEdges((items) => applyEdgeChanges(changes, items));
    if (changes.some((change) => change.type === "remove")) {
      if (contractView !== "overview") phaseGraphEditedRef.current[contractView] = true;
      setDirty(true);
    }
  }, [contractView]);

  function validateCurrentConnection(connection: Connection | FlowEdge): boolean {
    if (contractView !== activeCanvasPhaseRef.current) {
      setConnectionError("Connections must stay within the active phase.");
      return false;
    }
    const candidate: Connection = {
      source: connection.source,
      sourceHandle: connection.sourceHandle ?? null,
      target: connection.target,
      targetHandle: connection.targetHandle ?? null,
    };
    const result = validatePhaseConnection(
      candidate,
      nodes,
      edges,
      activeSourceFields,
      activeTargetFields,
      contractView,
    );
    setConnectionError(result.valid ? "" : result.message);
    return result.valid;
  }

  function handleConnection(connection: Connection) {
    if (!validateCurrentConnection(connection)) return;
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;
    const sourceNode = nodes.find((node) => node.id === connection.source);
    const targetNode = nodes.find((node) => node.id === connection.target);
    const direction = connectionDirection(connection, nodes, edges);
    const sourceFieldId = connection.sourceHandle.startsWith("field:")
      ? connection.sourceHandle.slice("field:".length)
      : "";
    const targetFieldId = connection.targetHandle.startsWith("field:")
      ? connection.targetHandle.slice("field:".length)
      : "";
    const sourceField = sourceNode?.type === "source"
      ? activeSourceFields.find((field) => field.id === sourceFieldId)
      : undefined;
    const targetField = targetNode?.type === "target"
      ? activeTargetFields.find((field) => field.id === targetFieldId)
      : undefined;

    if (
      sourceField
      && targetField
      && sourceField.data_type.trim().toLowerCase() !== targetField.data_type.trim().toLowerCase()
    ) {
      const shell = flowShellRef.current;
      const targetHandle = shell
        ? [...shell.querySelectorAll<HTMLElement>(".react-flow__handle")].find(
          (handle) => handle.dataset.nodeid === connection.target
            && handle.dataset.handleid === connection.targetHandle,
        )
        : undefined;
      const shellRect = shell?.getBoundingClientRect();
      const handleRect = targetHandle?.getBoundingClientRect();
      const position = shellRect && handleRect
        ? {
          x: Math.max(170, Math.min(shellRect.width - 170, handleRect.left - shellRect.left + handleRect.width / 2)),
        y: Math.max(8, Math.min(shellRect.height - 12, handleRect.top - shellRect.top + handleRect.height / 2)),
        }
        : { x: 240, y: 120 };
      setConnectionAssist({
        connection,
        sourceField,
        targetField,
        suggestedFunction: conversionFunction(sourceField.data_type, targetField.data_type),
        position,
      });
      return;
    }

    setEdges((current) => addEdge({
      ...connection,
      id: newUuid(),
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { direction, phase: contractView },
    }, current));
    markActivePhaseGraphEdited();
    setDirty(true);
  }

  function connectionFieldHandleCenter(
    nodeId: string,
    handleId: string,
    fallback: { x: number; y: number },
  ): { x: number; y: number } {
    const handle = flowShellRef.current
      ? [...flowShellRef.current.querySelectorAll<HTMLElement>(".react-flow__handle")]
        .find((item) => item.dataset.nodeid === nodeId && item.dataset.handleid === handleId)
      : undefined;
    if (handle && flowInstance.current) {
      const rect = handle.getBoundingClientRect();
      return flowInstance.current.screenToFlowPosition({
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      });
    }
    return fallback;
  }

  function acceptConnectionAssist(kind: "toInt" | "toNumber" | "toString" | "toBoolean" | "parseDate" | "formatDate" | "map") {
    if (contractView !== activeCanvasPhaseRef.current) return;
    if (!connectionAssist) return;
    const { connection, sourceField, targetField } = connectionAssist;
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) {
      setConnectionAssist(null);
      return;
    }
    const sourceNode = nodes.find((node) => node.id === connection.source);
    const targetNode = nodes.find((node) => node.id === connection.target);
    if (!sourceNode || !targetNode) {
      setConnectionAssist(null);
      return;
    }
    const sourceIndex = activeSourceFields.findIndex((field) => field.id === connection.sourceHandle!.slice("field:".length));
    const targetIndex = activeTargetFields.findIndex((field) => field.id === connection.targetHandle!.slice("field:".length));
    const sourceFallback = {
      x: sourceNode.position.x + (sourceNode.measured?.width ?? 220),
      y: sourceNode.position.y + 90 + Math.max(0, sourceIndex) * 34,
    };
    const targetFallback = {
      x: targetNode.position.x,
      y: targetNode.position.y + 90 + Math.max(0, targetIndex) * 34,
    };
    const fromHandle = connectionFieldHandleCenter(connection.source, connection.sourceHandle, sourceFallback);
    const toHandle = connectionFieldHandleCenter(connection.target, connection.targetHandle, targetFallback);
    const nodePosition = transformationPositionBetweenHandles(fromHandle, toHandle);
    const nodeId = newUuid();
    const direction = connectionDirection(connection, nodes, edges);
    const flowNodeId = nodeId;
    const flowEdgeId = () => newUuid();
    let config: Record<string, unknown>;
    let nodeType: "fx" | "map";
    if (kind !== "map") {
      nodeType = "fx";
      config = {
        function: kind,
        errorPolicy: "fail",
        ...(kind === "parseDate" ? { inputFormat: "%Y-%m-%d" } : {}),
        ...(kind === "formatDate" ? { outputFormat: "%Y-%m-%d" } : {}),
      };
    } else {
      nodeType = "map";
      const mapping: Record<string, string> = {};
      for (const row of ((responsePhase)
        ? parsedResponsePayload.rows
        : parsedSampleRows.rows) ?? []) {
        const value = row.values[sourceField.id];
        if (value === null || value === undefined) continue;
        const key = typeof value === "string" ? value : JSON.stringify(value);
        mapping[key] = key;
      }
      config = { mapping, errorPolicy: "fail" };
    }
    const newNode: FlowNode = {
      id: flowNodeId,
      type: nodeType,
      position: nodePosition,
      deletable: true,
      data: {
        label: nodeType === "fx" ? kind : NODE_LABELS.map,
        config,
        direction,
        phase: contractView,
      },
    };
    const firstEdge: FlowEdge = {
      id: flowEdgeId(),
      source: connection.source,
      sourceHandle: connection.sourceHandle,
      target: flowNodeId,
      targetHandle: "input",
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { direction, phase: contractView },
    };
    const secondEdge: FlowEdge = {
      id: flowEdgeId(),
      source: flowNodeId,
      sourceHandle: "output",
      target: connection.target,
      targetHandle: connection.targetHandle,
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { direction, phase: contractView },
    };
    setNodes((current) => [...current, newNode]);
    setEdges((current) => [...current, firstEdge, secondEdge]);
    setSelectedNodeId(flowNodeId);
    setSelectedEdgeId("");
    setDrawerView("inspector");
    setConfigText(JSON.stringify(config, null, 2));
    setConfigError("");
    markActivePhaseGraphEdited();
    setDirty(true);
    setConnectionAssist(null);
    const mappingRows = responsePhase || direction === "inbound"
      ? parsedResponsePayload.rows
      : parsedSampleRows.rows;
    if (nodeType === "map" && !mappingRows?.some((row) => row.values[sourceField.id] != null)) {
      setEditorNotice(`Inserted a MAP node for ${sourceField.label} → ${targetField.label}; no non-empty sample values were available to populate it.`);
    } else {
      setEditorNotice(`Inserted ${nodeType === "fx" ? kind : "MAP"} between ${sourceField.label} and ${targetField.label}.`);
    }
    window.setTimeout(() => setEditorNotice(""), 5000);
  }

  React.useEffect(() => {
    if (!connectionAssist) return;
    const suggestedFunction = connectionAssist.suggestedFunction;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setConnectionAssist(null);
      } else if (event.key === "Enter") {
        if (event.target instanceof HTMLElement && event.target.closest(".connection-assist-actions button")) {
          return;
        }
        event.preventDefault();
        acceptConnectionAssist(suggestedFunction);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    document.getElementById("connection-assist-default")?.focus();
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [connectionAssist]);

  const selectedTrace = selectedRow?.trace ?? [];
  const selectedArchitecture = architecture?.integrations.find(
    (item) => item.id === selectedIntegration?.id,
  );
  const upstreamIds = new Set(selectedArchitecture?.upstream.map((item) => item.id) ?? []);
  const previewRows = React.useMemo(() => {
    if (!selectedRow) return [];
    const activeInputRows = testingResponse ? parsedResponsePayload.rows : parsedSampleRows.rows;
    const previewInputRow = activeInputRows?.find((row) => row.rowId === selectedRow.rowId);
    const sourceNode = nodes.find((node) => node.type === "source");
    const targetNode = nodes.find((node) => node.type === "target");
    return activeTargetFields.map((targetField) => {
      const mappingEdge = edges.find((edge) =>
        edge.target === targetNode?.id && edge.targetHandle === `field:${targetField.id}`,
      );
      const sourceIds = new Set<string>();
      const chainLabels = new Set<string>();
      const pathNodeIds = new Set<string>();
      function traceSources(nodeId: string | undefined, outputPortId: string | undefined, visited: Set<string>) {
        if (!nodeId || visited.has(nodeId)) return;
        visited.add(nodeId);
        const node = nodes.find((item) => item.id === nodeId);
        if (!node) return;
        pathNodeIds.add(node.id);
        if (node.type === "source" && outputPortId?.startsWith("field:")) {
          sourceIds.add(outputPortId.slice("field:".length));
          return;
        }
        if (node.type === "source" || node.type === "target") return;
        const operation = transformationLabel(node.type, node.data.config);
        chainLabels.add(operation);
        for (const inputEdge of edges.filter((edge) => edge.target === node.id)) {
          traceSources(inputEdge.source, inputEdge.sourceHandle ?? undefined, new Set(visited));
        }
      }
      if (mappingEdge) {
        traceSources(mappingEdge.source, mappingEdge.sourceHandle ?? undefined, new Set());
        pathNodeIds.add(targetNode?.id ?? "");
      }
      const sourceFieldsForRow = activeSourceFields.filter((field) => sourceIds.has(field.id));
      const rawValues = sourceFieldsForRow.map((field) => ({
        fieldId: field.id,
        label: field.label,
        value: previewInputRow && Object.hasOwn(previewInputRow.values, field.id)
          ? JSON.stringify(previewInputRow.values[field.id])
          : "Missing",
      }));
      const outputExists = Object.hasOwn(selectedRow.targetValues, targetField.id);
      const pathFailed = selectedRow.errors.some((error) =>
        error.nodeId !== null && pathNodeIds.has(error.nodeId),
      );
      const status = !mappingEdge || pathFailed || (!outputExists && selectedRow.outcome !== "ok")
        ? "Error"
        : "OK";
      return {
        fieldId: targetField.id,
        targetLabel: targetField.label,
        sourceValues: rawValues,
        chain: chainLabels.size ? [...chainLabels].reverse().join(" → ") : mappingEdge ? "Direct mapping" : "Unmapped",
        output: outputExists ? JSON.stringify(selectedRow.targetValues[targetField.id]) : "—",
        status,
      };
    });
  }, [
    selectedRow,
    parsedSampleRows,
    parsedResponsePayload,
    nodes,
    edges,
    activeSourceFields,
    activeTargetFields,
    testingResponse,
  ]);

  function renderDetailsDrawer(options: { canvas: boolean } = { canvas: true }) {
    if (!selectedIntegration || !drawerView || (!options.canvas && drawerView === "inspector")) return null;
    return (
      <aside className="editor-sidepanel" aria-label="Workspace details">
        <header className="drawer-heading">
          <h2>
            {drawerView === "inspector"
              ? selectedEdgeId ? "Mapping edge" : "Node inspector"
              : drawerView === "validation" ? "Design validation" : "Contract settings"}
          </h2>
          <button type="button" className="drawer-close" aria-label="Close details drawer" onClick={() => setDrawerView(null)}>×</button>
        </header>
        <div className="drawer-content">
          {drawerView === "inspector" && selectedEdgeId ? (
            (() => {
              const edge = edges.find((item) => item.id === selectedEdgeId);
              const sourceNode = nodes.find((node) => node.id === edge?.source);
              const targetNode = nodes.find((node) => node.id === edge?.target);
              const row = edge ? matrixRowByEdgeId.get(edge.id) : undefined;
              const phaseLabel = contractView === "request"
                ? "Request mapping"
                : contractView === "success-response"
                  ? "Success response mapping"
                  : contractView === "error-response"
                    ? "Error response mapping"
                    : "Response mapping";
              const phaseSystems = contractView === "request"
                ? `${sourceSystem?.name ?? "System A"} → ${targetSystem?.name ?? "System B"}`
                : `${targetSystem?.name ?? "System B"} → ${sourceSystem?.name ?? "System A"}`;
              return edge ? (
                <section className="inspector">
                  <p className="eyebrow">FIELD MAPPING</p>
                  <h3>{row ? `${row.senderFieldLabel} → ${row.receiverFieldLabel}` : `${sourceNode?.data.label ?? "Source"} → ${targetNode?.data.label ?? "Target"}`}</h3>
                  <p className="node-id">Mapping edge · {edge.id}</p>
                  <p>{phaseLabel}</p>
                  <p className="muted">{phaseSystems}</p>
                  {row && (
                    <div className="mapping-type-details">
                      <table className="matrix-type-progression">
                        <tbody>
                          <tr>
                            <td><strong>{row.senderFieldLabel}</strong></td>
                            <td>{row.senderNormalizedType}</td>
                          </tr>
                          {row.transformation !== "Direct"
                            && row.transformation.split(" → ").filter(Boolean).map((label, index) => (
                            <tr key={`${row.id}:step:${index}`}>
                              <td>{label}</td>
                              <td>{row.typeProgression[index + 1]?.split(": ").at(-1) ?? "unknown"}</td>
                            </tr>
                            ))}
                          <tr>
                            <td><strong>{row.receiverFieldLabel}</strong></td>
                            <td>{row.receiverNormalizedType}</td>
                          </tr>
                        </tbody>
                      </table>
                      <p>
                        <strong>Validation status:</strong>{" "}
                        <span className={`preview-status ${
                          row.status === "Valid"
                            ? "ok"
                            : row.status === "Warning"
                              ? "warning"
                              : row.status === "Error"
                                ? "error"
                                : "unmapped"
                        }`}>{row.status}</span>
                      </p>
                      {row.issue && <p className="inline-error">{row.issue}</p>}
                      {row.lossy && <p className="muted">This chain may perform a lossy conversion.</p>}
                      {row.suggestedFix && (
                        <div className="matrix-actions">
                          <p className="muted">Suggested fix: Replace {row.suggestedFix.fromLabel} with {row.suggestedFix.toLabel}</p>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => applySuggestedFix(row)}
                          >
                            {row.suggestedFix.buttonLabel}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              ) : null;
            })()
          ) : drawerView === "inspector" && selectedNode ? (
            <section className="inspector">
              <div className="sidepanel-title">
                <div>
                  <p className="eyebrow">NODE INSPECTOR</p>
                  <h2>{selectedNode.type === "fx" ? transformationLabel("fx", selectedNode.data.config) : NODE_LABELS[targetNodeType(selectedNode)!]}</h2>
                </div>
                {!["source", "target"].includes(selectedNode.type) && (
                  <button type="button" className="danger-button" onClick={() => removeNode(selectedNode.id)}>Remove</button>
                )}
              </div>
              <p className="node-id">ID · {selectedNode.id}</p>
              <label className="config-editor">
                Configuration (JSON)
                <textarea
                  rows={12}
                  value={configText}
                  spellCheck={false}
                  disabled={["source", "target"].includes(selectedNode.type)}
                  onChange={(event) => updateConfig(event.target.value)}
                />
              </label>
              {configError && <p className="inline-error" role="alert">{configError}</p>}
              <p className="config-hint">
                {selectedNode.type === "fx" && "Functions: trim, title, lower, upper, e164, date, toString. Configure date formats explicitly; errors support fail, skip, or default with defaultValue."}
                {selectedNode.type === "constant" && "Set value to any JSON value."}
                {["map", "lookup"].includes(selectedNode.type) && "Configure mapping/table as a local JSON object; no external lookup is performed."}
                {selectedNode.type === "validate" && "Supported rules: required, type, min, max, allowedValues."}
                {selectedNode.type === "concat" && "Connect one or more string inputs; edge order controls concatenation order. Configure an optional separator."}
                {selectedNode.type === "ifelse" && "Connect inputs in order: boolean condition, true value, false value."}
                {selectedNode.type === "coalesce" && "Connect values in priority order; returns the first non-null, present value."}
                {selectedNode.type === "filter" && "Connect a boolean input. False skips the row without an error."}
              </p>
            </section>
          ) : drawerView === "validation" ? (
            architecture && selectedArchitecture ? (
              <section className="architecture-panel" aria-label="Design validation">
                <div className="validation-summary">
                  <span className={`integration-status-dot ${
                    contractHasMappingErrors
                      ? "attention"
                      : activeValidationCounts.warnings > 0
                        ? "draft"
                        : selectedArchitecture.status
                  }`}
                  />
                  <strong>{contractHasMappingErrors ? "Validation issues detected" : designStatusLabel(selectedArchitecture.status)}</strong>
                </div>
                {selectedArchitecture.reasons.length ? (
                  <ul className="architecture-reasons">
                    {selectedArchitecture.reasons.map((reason) => <li key={reason}>{designValidationReason(reason)}</li>)}
                  </ul>
                ) : <p className="muted">No mapping conflicts or contract dependencies needing validation.</p>}
                <div className="architecture-conflict-list">
                  <strong>Mapping type issues by phase</strong>
                  {([
                    ["request", "Request"],
                    ["success-response", "Success Response"],
                    ["error-response", "Error Response"],
                  ] as const).map(([phaseKey, label]) => {
                    const summary = phaseValidationSummary[phaseKey];
                    return (
                      <span key={phaseKey}>
                        <strong>{label}:</strong>{" "}
                        {summary.errors} errors, {summary.warnings} warnings
                      </span>
                    );
                  })}
                </div>
                <div className="architecture-conflict-list">
                  <strong>Active phase mapping checks</strong>
                  {mappingMatrixRows
                    .filter((row) => row.status === "Error" || row.status === "Warning")
                    .slice(0, 8)
                    .map((row) => (
                      <span key={`validation:${row.id}`}>
                        {row.senderFieldLabel} → {row.receiverFieldLabel}: {row.issue || row.status}
                      </span>
                    ))}
                  {!mappingMatrixRows.some((row) => row.status === "Error" || row.status === "Warning")
                    && <span>No type issues in this phase.</span>}
                </div>
                {selectedArchitecture.conflict_fields.length > 0 && (
                  <div className="architecture-conflict-list">
                    <strong>Target field issues</strong>
                    {selectedArchitecture.conflict_fields.map((field) => (
                      <span key={`${field.object_id}:${field.field_id}`}>{field.object_label} · {field.field_label}</span>
                    ))}
                  </div>
                )}
              </section>
            ) : <p className="muted">Design validation is loading.</p>
          ) : (
            <section className="contract-settings">
              <label className="integration-name">
                Contract name
                <input
                  value={name}
                  maxLength={160}
                  onChange={(event) => {
                    setName(event.target.value);
                    setDirty(true);
                  }}
                />
              </label>
              {interactionType !== "ONE_WAY" && (
                <label className="error-schema-selector">
                  Error response schema
                  <select
                    value={errorResponseObjectId}
                    onChange={(event) => void changeErrorResponseObject(event.target.value)}
                  >
                    <option value="">Select an object</option>
                    {targetObjects.map((object) => (
                      <option value={object.id} key={object.id}>{object.label}</option>
                    ))}
                  </select>
                  <small>Choose an existing object in {targetSystem?.name ?? "System B"}; no schema is generated.</small>
                </label>
              )}
              <div className="dependency-manager">
                <h3>Contract Dependencies</h3>
                {selectedArchitecture?.upstream.length ? (
                  <ul>
                    {selectedArchitecture.upstream.map((item) => (
                      <li key={item.id}>
                        <span><strong>{item.name}</strong><small>{designStatusLabel(item.status)}</small></span>
                        <button type="button" className="secondary-button" onClick={() => void removeDependency(item.id)} disabled={dependencySaving}>Remove</button>
                      </li>
                    ))}
                  </ul>
                ) : <p className="muted">No contract dependencies.</p>}
                <label>
                  Add contract dependency
                  <select
                    value={dependencyCandidateId}
                    onChange={(event) => setDependencyCandidateId(event.target.value)}
                    disabled={dependencySaving}
                  >
                    <option value="">Select a contract</option>
                    {integrations
                      .filter((item) => item.id !== selectedIntegration.id && !upstreamIds.has(item.id))
                      .map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
                <button type="button" className="secondary-button" onClick={() => void addDependency()} disabled={!dependencyCandidateId || dependencySaving}>
                  {dependencySaving ? "Updating…" : "Add contract dependency"}
                </button>
              </div>
            </section>
          )}
        </div>
      </aside>
    );
  }

  return (
    <section className={`integration-workspace${selectedIntegration ? " has-integration" : ""}`}>
      <header className="integration-header">
        <button type="button" className="back-link" onClick={onBack}>← Back</button>
        <div className="contract-heading">
          <h1>{selectedIntegration ? name || selectedIntegration.name : "New contract"}</h1>
          <p>
            {sourceSystem?.name ?? "Source"} / {objectName(sourceObjects, sourceObjectId)}
            <span aria-hidden="true"> → </span>
            {targetSystem?.name ?? "Target"} / {objectName(targetObjects, targetObjectId)}
          </p>
        </div>
        <div className="integration-toolbar">
          <label className="compact-picker switch-contract-picker">
            <span className="compact-picker-label">Switch contract</span>
            <select
              value={selectedIntegrationId}
              onChange={(event) => {
                if (event.target.value === "__new__") {
                  setEditorError("");
                  setName("");
                  setSelectedIntegrationId("");
                  setDrawerView(null);
                  setSamplePanelExpanded(false);
                  setDataPreviewOpen(false);
                  return;
                }
                setEditorError("");
                setDirty(false);
                setSelectedIntegrationId(event.target.value);
                setDrawerView(null);
                setSamplePanelExpanded(false);
                setDataPreviewOpen(false);
              }}
              aria-label="Contract"
            >
              <option value="">Select a contract</option>
              {integrations.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
              <option value="__new__">+ New contract</option>
            </select>
          </label>
          {selectedIntegration && (
            <>
              <span className={dirty ? "save-state unsaved" : "save-state"} aria-live="polite">
                {dirty ? "Unsaved changes" : `Saved · r${revision}`}
              </span>
              <button type="button" className="secondary-button" onClick={() => void refreshFieldMetadata()} disabled={loading}>
                Reload Schema
              </button>
              <button
                type="button"
                className={`secondary-button${dataPreviewOpen ? " preview-toggle-active" : ""}`}
                aria-label="Preview payload"
                aria-expanded={dataPreviewOpen}
                onClick={() => {
                  setSamplePanelExpanded(false);
                  setDataPreviewOpen((open) => !open);
                }}
              >
                Preview Payload
              </button>
              <label className="compact-picker">
                <select
                  value={interactionType}
                  onChange={(event) => updateInteractionType(event.target.value as InteractionType)}
                  aria-label="Interaction"
                >
                  <option value="ONE_WAY">One way</option>
                  <option value="REQUEST_RESPONSE">Request / response</option>
                  <option value="ASYNC_CALLBACK">Async callback</option>
                </select>
              </label>
              <button type="button" onClick={() => void saveGraph()} disabled={saving || !dirty || Boolean(configError)}>
                {saving ? "Saving…" : "Save"}
              </button>
              {csvUndo && csvUndo.afterKey === csvContextKey &&
                <button type="button" className="secondary-button" onClick={undoCsvImport} disabled={saving}>Undo import</button>}
              <details className="contract-overflow">
                <summary aria-label="Contract settings">⋯</summary>
                <div
                  className="contract-overflow-menu"
                  onClick={(event) => {
                    if ((event.target as HTMLElement).closest("button")) {
                      event.currentTarget.closest("details")?.removeAttribute("open");
                    }
                  }}
                >
                  <button type="button" onClick={() => setDrawerView("settings")}>Contract settings</button>
                  <button type="button" onClick={() => setDrawerView("validation")}>Design validation</button>
                  <button type="button" disabled={Boolean(csvUnavailableReason)} title={csvUnavailableReason}
                    onClick={() => setCsvDialog("import")}>Import CSV</button>
                  <button type="button" disabled={Boolean(csvUnavailableReason)} title={csvUnavailableReason}
                    onClick={() => setCsvDialog("export")}>Export CSV</button>
                  <button type="button" disabled={Boolean(csvUnavailableReason)} title={csvUnavailableReason}
                    onClick={() => {
                      downloadCsv(templateMappingCsv(activeSourceFields, activeTargetFields),
                        `${name}-${contractView}-mappings-v1-template.csv`);
                      setEditorNotice("Template downloaded. It may contain one example mapping; review it before importing.");
                    }}>Download CSV template</button>
                  {csvUnavailableReason && <p>{csvUnavailableReason}</p>}
                  <button type="button" onClick={() => {
                    setSamplePanelExpanded(false);
                    setDataPreviewOpen((open) => !open);
                  }}>Preview Payload</button>
                </div>
              </details>
            </>
          )}
        </div>
      </header>

      {editorError && (
        <div className="editor-toast" role="alert">
          <span>{editorError}</span>
          {editorError.includes("Reload") && <button type="button" className="secondary-button" onClick={() => void reloadIntegration()}>Reload current version</button>}
        </div>
      )}
      {editorNotice && <div className="editor-toast success" role="status">
        <span>{editorNotice}</span>
      </div>}
      {csvDialog && selectedIntegration && <ContractCsvDialog
        kind={csvDialog} contractName={name} phase={contractView} dirty={dirty}
        graph={csvGraph} senderFields={activeSourceFields} receiverFields={activeTargetFields}
        contextKey={csvContextKey} newId={newUuid}
        onApply={applyCsvImport} onClose={() => setCsvDialog(null)}
      />}

      {!selectedIntegration && (
        <section className="new-integration-card">
          <p className="eyebrow">START MAPPING</p>
          <h2>Create a contract</h2>
          {loading ? <p role="status">Loading systems and objects…</p> : systems.length === 0 ? (
            <p>Create a system, object, and fields in the catalog before creating a contract.</p>
          ) : (
            <form className="new-integration-form" onSubmit={(event) => void createIntegration(event)}>
              <label>
                Integration contract name
                <input value={name} onChange={(event) => setName(event.target.value)} maxLength={160} required placeholder="Customer sync" />
              </label>
              <fieldset>
                <legend>Source</legend>
                <label>System<select value={sourceSystemId} onChange={(event) => setSourceSystemId(event.target.value)}>
                  {systems.map((system) => <option key={system.id} value={system.id}>{system.name}</option>)}
                </select></label>
                <label>Object<select value={sourceObjectId} onChange={(event) => setSourceObjectId(event.target.value)} disabled={!sourceObjects.length}>
                  {sourceObjects.map((object) => <option key={object.id} value={object.id}>{object.label}</option>)}
                </select></label>
              </fieldset>
              <fieldset>
                <legend>Target</legend>
                <label>System<select value={targetSystemId} onChange={(event) => setTargetSystemId(event.target.value)}>
                  {systems.map((system) => <option key={system.id} value={system.id}>{system.name}</option>)}
                </select></label>
                <label>Object<select value={targetObjectId} onChange={(event) => setTargetObjectId(event.target.value)} disabled={!targetObjects.length}>
                  {targetObjects.map((object) => <option key={object.id} value={object.id}>{object.label}</option>)}
                </select></label>
              </fieldset>
              <button type="submit" disabled={!canCreate || saving}>{saving ? "Creating…" : "Create contract"}</button>
            </form>
          )}
        </section>
      )}

      {selectedIntegration && (
        <>
          <nav className="contract-phase-tabs" aria-label="Contract views">
            <button
              type="button"
              className={contractView === "overview" && !scenariosOpen ? "active" : ""}
              aria-current={contractView === "overview" && !scenariosOpen ? "page" : undefined}
              onClick={() => selectContractView("overview")}
            >
              Overview
            </button>
            <button
              type="button"
              className={contractView === "request" ? "active" : ""}
              aria-current={contractView === "request" ? "page" : undefined}
              onClick={() => selectContractView("request")}
            >
              Request
            </button>
            {interactionType === "REQUEST_RESPONSE" && (
              <>
                <button
                  type="button"
                  className={contractView === "success-response" ? "active" : ""}
                  aria-current={contractView === "success-response" ? "page" : undefined}
                  onClick={() => selectContractView("success-response")}
                >
                  Success Response
                </button>
                <button
                  type="button"
                  className={contractView === "error-response" ? "active" : ""}
                  aria-current={contractView === "error-response" ? "page" : undefined}
                  onClick={() => selectContractView("error-response")}
                >
                  Error Response
                </button>
              </>
            )}
            {interactionType === "ASYNC_CALLBACK" && (
              <button
                type="button"
                className={contractView === "async-response" ? "active" : ""}
                aria-current={contractView === "async-response" ? "page" : undefined}
                onClick={() => selectContractView("async-response")}
              >
                Response
              </button>
            )}
            <button
              type="button"
              className={`contract-scenarios-tab${scenariosOpen ? " active" : ""}`}
              aria-current={scenariosOpen ? "page" : undefined}
              onClick={openScenarios}
            >
              Scenarios
            </button>
          </nav>
          {scenariosOpen && contractView === "overview" ? (
            <div className="contract-static-body contract-scenarios-body">
              <ScenarioWorkspace
                scopeIntegrationId={selectedIntegration.id}
                onOpenContractPhase={openScenarioContractPhase}
              />
            </div>
          ) : contractView === "overview" ? (
            <div className={`contract-static-body${drawerView && drawerView !== "inspector" ? " with-drawer" : ""}`}>
            <section className="contract-overview">
              <div className="interaction-diagram">
                <div className="interaction-system">
                  <span>System A · Initiates</span>
                  <strong>{sourceSystem?.name ?? "System A"}</strong>
                  <small>{sourceObjectLabel}</small>
                </div>
                <div className="interaction-messages">
                  <div className="interaction-arrow request">
                    <span>Request · {sourceObjectLabel} → {targetObjectLabel}</span>
                    <span className="arrow-line" aria-hidden="true"><i /></span>
                  </div>
                  {interactionType === "REQUEST_RESPONSE" && (
                    <>
                      <div className="interaction-arrow success">
                        <span>Success response · {targetObjectLabel} → {sourceObjectLabel}</span>
                        <span className="arrow-line reverse" aria-hidden="true"><i /></span>
                      </div>
                      <div className="interaction-arrow error">
                        <span>Error response · {targetObjectLabel} → {sourceObjectLabel}</span>
                        <span className="arrow-line reverse" aria-hidden="true"><i /></span>
                      </div>
                    </>
                  )}
                  {interactionType === "ASYNC_CALLBACK" && (
                    <div className="interaction-arrow request">
                      <span>Response · {targetObjectLabel} → {sourceObjectLabel}</span>
                      <span className="arrow-line reverse" aria-hidden="true"><i /></span>
                    </div>
                  )}
                </div>
                <div className="interaction-system">
                  <span>System B · Receives request</span>
                  <strong>{targetSystem?.name ?? "System B"}</strong>
                  <small>{targetObjectLabel}</small>
                </div>
                <p className="interaction-pattern">
                  {interactionType === "ONE_WAY"
                    ? "One way"
                    : interactionType === "ASYNC_CALLBACK"
                      ? "Async callback"
                      : "Request / response"}
                  <span>{selectedIntegration.name}</span>
                </p>
              </div>
              <section className="contract-summary" aria-label="Contract summary">
                <h2>Contract summary</h2>
                <dl>
                  <div><dt>Contract</dt><dd>{selectedIntegration.name}</dd></div>
                  <div><dt>Source</dt><dd>{sourceSystem?.name ?? "—"} · {sourceObjectLabel}</dd></div>
                  <div><dt>Target</dt><dd>{targetSystem?.name ?? "—"} · {targetObjectLabel}</dd></div>
                  <div><dt>Interaction pattern</dt><dd>{interactionType === "ONE_WAY" ? "One way" : interactionType === "ASYNC_CALLBACK" ? "Async callback" : "Request / response"}</dd></div>
                  <div><dt>Save state</dt><dd>{dirty ? "Unsaved changes" : `Saved · r${revision}`}</dd></div>
                  <div><dt>Design validation</dt><dd>{selectedArchitecture ? designStatusLabel(selectedArchitecture.status) : "Loading"}</dd></div>
                  <div><dt>Contract dependencies</dt><dd>{selectedArchitecture?.upstream.length ? selectedArchitecture.upstream.map((item) => item.name).join(", ") : "None"}</dd></div>
                </dl>
              </section>
            </section>
            {renderDetailsDrawer({ canvas: false })}
            </div>
          ) : (
            <>
              <div className={`mapping-direction-label ${contractView}`}>
                {contractView === "request"
                  ? `REQUEST · ${sourceSystem?.name ?? "System A"} → ${targetSystem?.name ?? "System B"}`
                  : contractView === "success-response"
                    ? `SUCCESS RESPONSE · ${targetSystem?.name ?? "System B"} → ${sourceSystem?.name ?? "System A"}`
                    : contractView === "error-response"
                      ? `ERROR RESPONSE · ${targetSystem?.name ?? "System B"} → ${sourceSystem?.name ?? "System A"}`
                      : `RESPONSE · ${targetSystem?.name ?? "System B"} → ${sourceSystem?.name ?? "System A"}`}
              </div>
              {contractView === "error-response" && !errorResponseObjectId ? (
                <div className={`contract-static-body${drawerView && drawerView !== "inspector" ? " with-drawer" : ""}`}>
                <section className="phase-schema-empty">
                  <h2>Error response schema not selected</h2>
                  <p>Select an existing object from {targetSystem?.name ?? "System B"} in Contract settings to design this message.</p>
                  <button type="button" onClick={() => setDrawerView("settings")}>Open Contract settings</button>
                </section>
                {renderDetailsDrawer({ canvas: false })}
                </div>
              ) : ordinaryResponsePhase && targetFields.length === 0 ? (
                <div className={`contract-static-body${drawerView && drawerView !== "inspector" ? " with-drawer" : ""}`}>
                <section className="phase-schema-empty">
                  <h2>Success response schema has no fields</h2>
                  <p>Add fields to {targetObjectLabel} to map the response back to {sourceObjectLabel}.</p>
                  <button type="button" onClick={() => setQuickAddEndpoint("target")}>Add schema field</button>
                </section>
                {renderDetailsDrawer({ canvas: false })}
                </div>
              ) : (
                <>
          <section className="editor-toolbar-panel">
            {samplePanelExpanded && <section className="sample-data-panel expanded" aria-label="Sample data test payload">
              <div className="sample-collapsed-toolbar">
                <button
                  type="button"
                  className="sample-payload-toggle"
                  aria-expanded="true"
                  onClick={() => setSamplePanelExpanded(false)}
                >
                  <span className="sample-payload-chevron" aria-hidden="true">▼</span>
                  <span>Test Payload <small>({parsedSampleRows.rows?.length ?? "—"} rows)</small></span>
                </button>
                <button
                  type="button"
                  className="sample-auto-generate"
                  onClick={generateMockRows}
                  disabled={!sourceFields.length}
                >
                  Generate Sample Data
                </button>
                <button
                  type="button"
                  className="sample-edit-rows"
                  onClick={() => setSampleMode("form")}
                >
                  Edit Rows
                </button>
                <button type="button" className="sample-edit-rows" onClick={() => setSamplePanelExpanded(false)}>Close</button>
              </div>
              <div className="sample-drawer">
                <div className="sample-drawer-content">
                  <div className="sample-inputs">
                    <div className="sample-panel-header">
                      <div>
                        <p className="eyebrow">SAMPLE INPUT</p>
                        <h3>Sample payload rows</h3>
                        <p>Changes update the sample payload and are saved with the contract.</p>
                      </div>
                      <div className="sample-panel-actions">
                        <div className="sample-mode-toggle" role="group" aria-label="Sample data editor mode">
                    <button
                      type="button"
                      className={sampleMode === "form" ? "active" : ""}
                      aria-pressed={sampleMode === "form"}
                      onClick={() => setSampleMode("form")}
                    >
                      Form / Table
                    </button>
                    <button
                      type="button"
                      className={sampleMode === "json" ? "active" : ""}
                      aria-pressed={sampleMode === "json"}
                      onClick={() => setSampleMode("json")}
                    >
                      Raw JSON
                    </button>
                        </div>
                  </div>
                </div>
                {sampleMode === "json" ? (
                <>
                  <textarea
                    className="sample-json-editor"
                    value={rowsText}
                    rows={7}
                    spellCheck={false}
                    onChange={(event) => {
                      setRowsText(event.target.value);
                      setDirty(true);
                    }}
                    aria-label="Sample payload rows JSON"
                  />
                  <small>Use a JSON array of {"{ rowId, values }"}; each values object is keyed by source field UUID.</small>
                  {!parsedSampleRows.rows && <p className="inline-error" role="alert">{parsedSampleRows.error}</p>}
                </>
              ) : (
                <>
                  <div className="sample-table-toolbar">
                    <span>{parsedSampleRows.rows?.length ?? 0} / 100 rows</span>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={addSampleRow}
                      disabled={!parsedSampleRows.rows || parsedSampleRows.rows.length >= 100}
                    >
                      + Add row
                    </button>
                  </div>
                  {!parsedSampleRows.rows ? (
                    <div className="sample-invalid-state" role="alert">
                      <p>{parsedSampleRows.error}</p>
                      <button type="button" className="secondary-button" onClick={() => setSampleMode("json")}>Fix in Raw JSON</button>
                    </div>
                  ) : sourceFields.length === 0 ? (
                    <p className="sample-empty-state">The source object has no fields. Add source fields to build table inputs.</p>
                  ) : (
                    <div className="sample-table-scroll">
                      <table className="sample-data-table">
                        <thead>
                          <tr>
                            <th scope="col">Row</th>
                            {sourceFields.map((field) => (
                              <th scope="col" key={field.id}>
                                <span>{field.label}</span><small>{field.data_type}</small>
                              </th>
                            ))}
                            <th scope="col">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {parsedSampleRows.rows.map((row, rowIndex) => (
                            <tr key={row.rowId}>
                              <th scope="row"><span title={row.rowId}>{rowIndex + 1}</span></th>
                              {sourceFields.map((field) => {
                                const value = row.values[field.id];
                                const fieldType = field.data_type.toLowerCase();
                                const isBoolean = /bool/.test(fieldType);
                                const isNumber = /int|decimal|float|double|numeric|number/.test(fieldType);
                                const isDate = /date|timestamp/.test(fieldType);
                                return (
                                  <td key={field.id}>
                                    {isBoolean ? (
                                      <input
                                        className="sample-boolean-input"
                                        type="checkbox"
                                        checked={value === true || value === 1 || value === "true"}
                                        onChange={(event) => updateSampleCell(rowIndex, field.id, event.target.checked)}
                                        aria-label={`${field.label}, row ${rowIndex + 1}`}
                                      />
                                    ) : (
                                      <input
                                        type={isNumber ? "number" : isDate ? "date" : "text"}
                                        step={isNumber && !/int/.test(fieldType) ? "any" : undefined}
                                        value={value == null
                                          ? ""
                                          : isDate && typeof value === "string"
                                            ? value.slice(0, 10)
                                            : typeof value === "string" || typeof value === "number"
                                              ? value
                                              : JSON.stringify(value)}
                                        onChange={(event) => {
                                          const nextValue = isNumber
                                            ? event.target.value === "" || !Number.isFinite(event.target.valueAsNumber)
                                              ? null
                                              : event.target.valueAsNumber
                                            : event.target.value || null;
                                          updateSampleCell(rowIndex, field.id, nextValue);
                                        }}
                                        aria-label={`${field.label}, row ${rowIndex + 1}`}
                                      />
                                    )}
                                  </td>
                                );
                              })}
                              <td>
                                <button
                                  type="button"
                                  className="sample-remove-row"
                                  onClick={() => removeSampleRow(rowIndex)}
                                  aria-label={`Remove row ${rowIndex + 1}`}
                                >
                                  Remove
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <small className="sample-data-hint">Form edits are synchronized to the JSON payload immediately. Sample rows remain in this editor until Save.</small>
                </>
                )}
                  </div>
                  {interactionType !== "ONE_WAY" && (
                    <section className="response-payload-input" aria-label="Mock response payload">
                      <label htmlFor="response-payload-editor">Mock System B response payload (JSON)</label>
                      <textarea
                        id="response-payload-editor"
                        className="sample-json-editor"
                        value={responsePayloadText}
                        rows={5}
                        spellCheck={false}
                        onChange={(event) => setResponsePayloadText(event.target.value)}
                      />
                      <small>Provide an array of {"{ rowId, values }"} keyed by System B field UUIDs; this data is used only for sample-data evaluation.</small>
                      {!parsedResponsePayload.rows && (
                        <p className="inline-error" role="alert">{parsedResponsePayload.error}</p>
                      )}
                    </section>
                  )}
                  <section className="sample-test-results" aria-live="polite">
                    <header className="sample-results-header">
                      <div>
                        <p className="eyebrow">SAMPLE DATA TEST</p>
                        <h3>{simulationLoading ? "Evaluating…" : simulation ? "Latest test result" : "Ready to test"}</h3>
                      </div>
                      {activeTraceTruncated && <span className="trace-badge">Trace truncated</span>}
                      <button
                        type="button"
                        onClick={() => void runSimulation(currentGraph, currentResponseGraph)}
                        disabled={simulationLoading}
                      >
                        {simulationLoading ? "Testing…" : "Run test"}
                      </button>
                    </header>
                    {simulation ? (
                      <>
                        <div className="simulation-counts">
                          <span><strong>{activeSimulationSummary?.total ?? 0}</strong> {testingResponse ? "response rows" : "request rows"}</span>
                          <span className="count-ok">{activeSimulationSummary?.ok ?? 0} OK</span>
                          <span className="count-skipped">{activeSimulationSummary?.skipped ?? 0} skipped</span>
                          <span className="count-failed">{activeSimulationSummary?.failed ?? 0} failed</span>
                        </div>
                        {activeSimulationRows.length ? (
                          <label className="row-picker">
                            Result row
                            <select value={selectedRowIndex} onChange={(event) => setSelectedRowIndex(Number(event.target.value))}>
                              {activeSimulationRows.map((row, index) => (
                                <option key={`${row.rowId}-${index}`} value={index}>{row.rowId} · {row.outcome}</option>
                              ))}
                            </select>
                          </label>
                        ) : <p className="empty-state">Add sample rows to see a trace.</p>}
                        {selectedRow && (
                          <>
                            <div className="target-output">
                              <h3>Target values</h3>
                              {Object.entries(selectedRow.targetValues).length ? (
                                <dl>{Object.entries(selectedRow.targetValues).map(([id, value]) => (
                                  <div key={id}>
                                    <dt>{activeTargetFields.find((field) => field.id === id)?.label ?? id}</dt>
                                    <dd>{JSON.stringify(value)}</dd>
                                  </div>
                                ))}</dl>
                              ) : <p className="muted">No target values produced.</p>}
                            </div>
                            {selectedRow.errors.length > 0 && (
                              <div className="simulation-errors">
                                <h3>Row errors</h3>
                                {selectedRow.errors.map((item, index) => (
                                  <p key={`${item.code}-${index}`}><strong>{item.code}</strong> · {item.message}</p>
                                ))}
                              </div>
                            )}
                            <div className="trace-list">
                              <h3>Node trace</h3>
                              {selectedTrace.map((entry, index) => (
                                <button
                                  type="button"
                                  className={`trace-entry${entry.nodeId === selectedNodeId ? " active" : ""}`}
                                  key={`${entry.nodeId}-${index}`}
                                  onClick={() => {
                                    setSelectedNodeId(entry.nodeId);
                                    setSelectedEdgeId("");
                                    setDrawerView("inspector");
                                    setNodes((items) => items.map((node) => ({
                                      ...node,
                                      selected: node.id === entry.nodeId,
                                    })));
                                    const tracedNode = nodes.find((node) => node.id === entry.nodeId);
                                    if (tracedNode) {
                                      setConfigText(JSON.stringify(tracedNode.data.config, null, 2));
                                      setConfigError("");
                                    }
                                  }}
                                >
                                  <span><strong>{NODE_LABELS[entry.nodeType] ?? entry.nodeType}</strong><small>{entry.outcome}</small></span>
                                  <code>{JSON.stringify(entry.outputs)}</code>
                                </button>
                              ))}
                              {!selectedTrace.length && <p className="muted">No node trace is available for this row.</p>}
                            </div>
                          </>
                        )}
                      </>
                    ) : (
                      <p className="muted">{simulationLoading
                        ? "Evaluating sample data…"
                        : "Connect the source and target nodes, then run a sample-data test."}</p>
                    )}
                  </section>
                </div>
              </div>
            </section>}
          </section>

          <div className="canvas-toolbar" aria-label="Mapping canvas tools">
            <div className="workbench-view-toggle" role="tablist" aria-label="Mapping workbench view">
              <button
                type="button"
                role="tab"
                aria-selected={workbenchView === "canvas"}
                className={workbenchView === "canvas" ? "active" : ""}
                onClick={() => {
                  setWorkbenchView("canvas");
                  setDirty((wasDirty) => dirtyStateForWorkbenchViewSwitch(wasDirty));
                }}
              >
                Canvas
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={workbenchView === "matrix"}
                className={workbenchView === "matrix" ? "active" : ""}
                onClick={() => {
                  setWorkbenchView("matrix");
                  setDirty((wasDirty) => dirtyStateForWorkbenchViewSwitch(wasDirty));
                }}
              >
                Mapping Matrix
              </button>
            </div>
            <details className="transform-menu" open={transformMenuOpen} onToggle={(event) => setTransformMenuOpen(event.currentTarget.open)}>
              <summary>Add transformation</summary>
              <div className="transform-menu-items">
                {TRANSFORM_TYPES.map((type) => (
                  <button
                    type="button"
                    key={type}
                    onClick={() => {
                      addTransform(type);
                      setTransformMenuOpen(false);
                    }}
                  >
                    {NODE_LABELS[type]}
                  </button>
                ))}
              </div>
            </details>
            <button type="button" className="secondary-button" onClick={autoMapFields}>Auto-map</button>
            <button type="button" className="secondary-button" onClick={() => {
              setDataPreviewOpen(false);
              setSamplePanelExpanded(true);
            }}>Test data</button>
            <button
              type="button"
              className={`validation-trigger ${
                contractHasMappingErrors || selectedArchitecture?.status === "attention"
                  ? "errors"
                  : activeValidationCounts.warnings > 0 || selectedArchitecture?.status === "draft"
                    ? "warnings"
                    : "valid"
              }`}
              onClick={() => setDrawerView("validation")}
            >
              {contractHasMappingErrors || selectedArchitecture?.conflict_fields.length
                ? "Errors"
                : activeValidationCounts.warnings > 0 || selectedArchitecture?.status !== "healthy"
                  ? "Warnings"
                  : "Valid"}
            </button>
            {workbenchView === "matrix" && (
              <div className="matrix-filter-group" role="group" aria-label="Mapping Matrix filter">
                <button
                  type="button"
                  className={matrixFilter === "all" ? "active" : ""}
                  onClick={() => setMatrixFilter("all")}
                >
                  All
                </button>
                <button
                  type="button"
                  className={matrixFilter === "mapped" ? "active" : ""}
                  onClick={() => setMatrixFilter("mapped")}
                >
                  Mapped
                </button>
                <button
                  type="button"
                  className={matrixFilter === "unmapped" ? "active" : ""}
                  onClick={() => setMatrixFilter("unmapped")}
                >
                  Unmapped
                </button>
                <button
                  type="button"
                  className={matrixFilter === "issues" ? "active" : ""}
                  onClick={() => setMatrixFilter("issues")}
                >
                  Issues
                </button>
              </div>
            )}
            <span className="canvas-toolbar-spacer" />
            <button type="button" className="secondary-button" onClick={resetLayout}>Reset layout</button>
            <button type="button" className="secondary-button" onClick={() => frameCanvas(200)}>Fit view</button>
            <button type="button" className="secondary-button canvas-zoom" aria-label="Zoom out" onClick={() => flowInstance.current?.zoomOut()}>−</button>
            <button type="button" className="secondary-button canvas-zoom" aria-label="Zoom in" onClick={() => flowInstance.current?.zoomIn()}>+</button>
          </div>

          <div className={`editor-body${drawerView ? " with-drawer" : ""}`}>
            <section className={`flow-shell${workbenchView === "matrix" ? " is-hidden" : ""}`} aria-label="Contract graph canvas" ref={flowShellRef}>
              {loading ? (
                <p className="canvas-loading" role="status">Loading graph…</p>
              ) : (
                <>
                  {connectionError && (
                    <div className="connection-validation-message" role="status">
                      {connectionError}
                    </div>
                  )}
                  <ReactFlow<FlowNode, FlowEdge>
                    key={`${selectedIntegrationId}:${contractView}`}
                    nodes={nodes}
                    edges={renderedEdges}
                    nodeTypes={nodeTypes}
                    edgeTypes={edgeTypes}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    isValidConnection={validateCurrentConnection}
                    onConnect={handleConnection}
                    onNodeDragStop={() => {
                      if (contractView !== activeCanvasPhaseRef.current) return;
                      markActivePhaseGraphEdited();
                      setDirty(true);
                    }}
                    onNodeClick={(_, node) => {
                      setSelectedNodeId(node.id);
                      setSelectedEdgeId("");
                      setConfigText(JSON.stringify(node.data.config, null, 2));
                      setConfigError("");
                      setDrawerView("inspector");
                    }}
                    onEdgeClick={(_, edge) => {
                      const row = matrixRowByEdgeId.get(edge.id);
                      if (row) {
                        selectChainByRow(row, { anchorEdgeId: edge.id });
                        return;
                      }
                      setSelectedEdgeId(edge.id);
                      setSelectedNodeId("");
                      setDrawerView("inspector");
                    }}
                    onPaneClick={() => {
                      setSelectedNodeId("");
                      setSelectedEdgeId("");
                      setDrawerView(null);
                    }}
                    onInit={(instance) => {
                      flowInstance.current = instance;
                      setCanvasReadyVersion((version) => version + 1);
                    }}
                    deleteKeyCode={["Backspace", "Delete"]}
                    proOptions={{ hideAttribution: true }}
                  >
                    <Background color="#d5dee6" gap={18} size={1.2} variant={BackgroundVariant.Dots} />
                    <MiniMap pannable zoomable />
                    <Controls />
                  </ReactFlow>
                </>
              )}
              {connectionAssist && (
                <section
                  className={`connection-assist${connectionAssist.position.y < 180 ? " below" : ""}`}
                  role="dialog"
                  aria-modal="false"
                  aria-labelledby="connection-assist-title"
                  style={{ left: connectionAssist.position.x, top: connectionAssist.position.y }}
                  onMouseDown={(event) => event.stopPropagation()}
                  onClick={(event) => event.stopPropagation()}
                >
                  <h2 id="connection-assist-title">Type Conversion Needed</h2>
                  <p>
                    Source <code>{connectionAssist.sourceField.data_type}</code> needs conversion to{" "}
                    <code>{connectionAssist.targetField.data_type}</code> for this target.
                  </p>
                  <div className="connection-assist-actions">
                    <button
                      id="connection-assist-default"
                      type="button"
                      onClick={() => acceptConnectionAssist(connectionAssist.suggestedFunction)}
                    >
                      Auto-Insert: Function ({connectionAssist.suggestedFunction})
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => acceptConnectionAssist("map")}
                    >
                      Accept: Insert MAP Node
                    </button>
                    <button type="button" className="connection-assist-cancel" onClick={() => setConnectionAssist(null)}>
                      Cancel
                    </button>
                  </div>
                  <small>Press Enter to insert {connectionAssist.suggestedFunction} or Esc to cancel.</small>
                </section>
              )}
            </section>

            {workbenchView === "matrix" && (
              <section className="matrix-shell" aria-label="Mapping matrix">
                {visibleMappingRows.length === 0 ? (
                  <p className="data-preview-empty">No mappings match this filter for the active phase.</p>
                ) : (
                  <div className="matrix-table-wrap">
                    <table className="matrix-table">
                      <thead>
                        <tr>
                          <th>Sender field</th>
                          <th>Sender type</th>
                          <th>Transformation</th>
                          <th>Receiver field</th>
                          <th>Receiver type</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleMappingRows.map((row) => (
                          <tr
                            key={row.id}
                            className={selectedMatrixRowId === row.id ? "active" : ""}
                            onClick={() => selectMatrixRow(row)}
                          >
                            <td>
                              <strong>{row.senderFieldLabel}</strong>
                              {row.senderFieldName && <small>{row.senderFieldName}</small>}
                            </td>
                            <td><span className="field-type-pill">{row.senderType}</span></td>
                            <td>
                              <span className="matrix-transform-pill">{row.transformation}</span>
                              {row.issue && <small className="matrix-issue-text">{row.issue}</small>}
                            </td>
                            <td>
                              <strong>{row.receiverFieldLabel}</strong>
                              {row.receiverFieldName && <small>{row.receiverFieldName}</small>}
                            </td>
                            <td><span className="field-type-pill">{row.receiverType}</span></td>
                            <td>
                              <span className={`preview-status ${
                                row.status === "Valid"
                                  ? "ok"
                                  : row.status === "Warning"
                                    ? "warning"
                                    : row.status === "Error"
                                      ? "error"
                                      : "unmapped"
                              }`}>
                                {row.status}
                              </span>
                            </td>
                            <td>
                              <div className="matrix-actions">
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    selectMatrixRow(row, { openCanvas: true });
                                  }}
                                >
                                  Open in Canvas
                                </button>
                                {row.graphEdgeIds.length > 0 && (
                                  <button
                                    type="button"
                                    className="secondary-button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      removeMatrixRowMapping(row);
                                    }}
                                  >
                                    Remove mapping
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {renderDetailsDrawer()}
          </div>
          {dataPreviewOpen && (
            <section className="data-preview-drawer" aria-label="Sample payload preview">
              <header className="data-preview-header">
                <div>
                  <p className="eyebrow">SAMPLE PAYLOAD PREVIEW</p>
                  <h2>Preview Payload</h2>
                </div>
                <div className="data-preview-controls">
                  {simulation && activeSimulationRows.length > 0 && (
                    <label className="row-picker">
                      Preview row
                      <select
                        value={selectedRowIndex}
                        onChange={(event) => setSelectedRowIndex(Number(event.target.value))}
                      >
                        {activeSimulationRows.map((row, index) => (
                          <option key={`${row.rowId}-preview-${index}`} value={index}>
                            {row.rowId} · {row.outcome}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    aria-label="Close payload preview"
                    onClick={() => setDataPreviewOpen(false)}
                  >
                    Close
                  </button>
                </div>
              </header>
              {simulationLoading ? (
                <p className="data-preview-empty" role="status">Refreshing payload preview…</p>
              ) : !simulation || !selectedRow ? (
                <p className="data-preview-empty">Add sample rows and connect fields to preview the resulting payload.</p>
              ) : (
                <div className="data-preview-table-wrap">
                  <table className="data-preview-table">
                    <thead>
                      <tr>
                        <th scope="col">Source Field &amp; Raw Input</th>
                        <th scope="col">Transformation Chain</th>
                        <th scope="col">Target Field &amp; Final Output</th>
                        <th scope="col">Validation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((row) => (
                        <tr key={row.fieldId}>
                          <td>
                            {row.sourceValues.length ? row.sourceValues.map((source) => (
                              <span className="preview-source-value" key={`${row.fieldId}-${source.fieldId}`}>
                                <span className="preview-field-label">{source.label}</span>
                                <code>{source.value}</code>
                              </span>
                            )) : <span className="preview-muted">—</span>}
                          </td>
                          <td><span className="preview-chain">{row.chain}</span></td>
                          <td>
                            <span className="preview-field-label">{row.targetLabel}</span>
                            <code>{row.output}</code>
                          </td>
                          <td>
                            <span className={`preview-status ${row.status.toLowerCase()}`}>
                              {row.status === "OK" ? "✓ OK" : "⚠ Error"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
              </>
            )}
        </>
      )}
        </>
      )}
      {quickAddEndpoint && (
        <div className="catalog-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !quickFieldSaving) setQuickAddEndpoint(null);
        }}>
          <section className="catalog-modal quick-field-modal" role="dialog" aria-modal="true" aria-labelledby="quick-field-title">
            <header>
              <div>
                <p className="eyebrow">{quickAddEndpoint === "source" ? "SOURCE SCHEMA" : "TARGET SCHEMA"}</p>
                <h2 id="quick-field-title">Add field</h2>
              </div>
              <button type="button" className="secondary-button" onClick={() => setQuickAddEndpoint(null)} disabled={quickFieldSaving} aria-label="Close">×</button>
            </header>
            <form className="editor-form" onSubmit={(event) => void createQuickField(event)}>
              <label>
                Field name
                <input autoFocus value={quickFieldName} onChange={(event) => setQuickFieldName(event.target.value)} required maxLength={160} placeholder="phone_number" />
              </label>
              <label>
                Data type
                <input value={quickFieldType} onChange={(event) => setQuickFieldType(event.target.value)} required maxLength={100} placeholder="string" />
              </label>
              <p className="muted">This adds a generic field to the selected object and exposes its port immediately.</p>
              <div className="catalog-modal-actions">
                <button type="button" className="secondary-button" onClick={() => setQuickAddEndpoint(null)} disabled={quickFieldSaving}>Cancel</button>
                <button type="submit" disabled={quickFieldSaving}>{quickFieldSaving ? "Adding…" : "Add field"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
      {editingField && (
        <div className="catalog-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !fieldSaving) setEditingField(null);
        }}>
          <section key={editingField.field.id} className="catalog-modal quick-field-modal" role="dialog" aria-modal="true" aria-labelledby="edit-field-title">
            <header>
              <div>
                <p className="eyebrow">{editingField.endpoint === "source" ? "SOURCE SCHEMA" : "TARGET SCHEMA"}</p>
                <h2 id="edit-field-title">Edit field</h2>
              </div>
              <button type="button" className="secondary-button" onClick={() => setEditingField(null)} disabled={fieldSaving} aria-label="Close">×</button>
            </header>
            <form className="editor-form" onSubmit={(event) => void saveFieldEdit(event)}>
              <label>
                Field name
                <input name="name" autoFocus required maxLength={160} defaultValue={editingField.field.name} />
              </label>
              <label>
                Data type
                <input name="data_type" required maxLength={100} defaultValue={editingField.field.data_type} />
              </label>
              <div className="catalog-modal-actions">
                <button type="button" className="secondary-button" onClick={() => setEditingField(null)} disabled={fieldSaving}>Cancel</button>
                <button type="submit" disabled={fieldSaving}>{fieldSaving ? "Saving…" : "Save field"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
