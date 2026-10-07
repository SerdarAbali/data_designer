import {
  deriveMappingChains,
  fieldIdFromPort,
  type MappingChain,
  type MappingGraphDocument,
  type MappingGraphEdge,
  type MappingGraphField,
  type MappingGraphIssue,
  type MappingGraphNode,
} from "./mappingGraphModel";
import type { TypeValidationResult } from "./mappingTypeValidation";

export type ArchitectureInteractionType = "ONE_WAY" | "REQUEST_RESPONSE" | "ASYNC_CALLBACK";
export type ArchitecturePhaseKind = "request" | "success-response" | "async-response" | "error-response";
export type ArchitectureValidationStatus =
  | "Valid"
  | "Warnings"
  | "Errors"
  | "Incomplete"
  | "Unconfigured";
export type ArchitectureIndexState = "complete" | "partial" | "failed";

export type ArchitectureSystemRecord = {
  id: string;
  name: string;
  kind: string;
  description?: string | null;
  icon?: string | null;
  color?: string | null;
  position?: { x: number; y: number } | null;
};

export type ArchitectureObjectRecord = {
  id: string;
  system_id: string;
  name: string;
  label: string;
};

export type ArchitectureFieldRecord = Omit<MappingGraphField, "name" | "label"> & {
  object_id: string;
  name: string;
  label: string;
  required: boolean;
  nullable: boolean;
};

export type ArchitectureGraphNode = MappingGraphNode & {
  position?: { x: number; y: number };
};

export type ArchitectureGraphDocument = MappingGraphDocument & {
  version: number;
  nodes: ArchitectureGraphNode[];
  edges: MappingGraphEdge[];
};

export type ArchitectureGraphSnapshot = {
  raw: unknown;
  document: Readonly<ArchitectureGraphDocument> | null;
};

export type ArchitectureContractRecord = {
  id: string;
  name: string;
  source_system_id: string;
  source_object_id: string;
  target_system_id: string;
  target_object_id: string;
  interaction_type: ArchitectureInteractionType;
  graph: ArchitectureGraphDocument;
  response_graph: ArchitectureGraphDocument;
  error_response_graph?: ArchitectureGraphDocument;
  error_response_object_id?: string | null;
  revision?: number;
  updated_at?: string | null;
  sample_rows?: readonly unknown[];
  description?: string | null;
};

export type ArchitectureSystem = Readonly<{
  id: string;
  name: string;
  kind: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  position: Readonly<{ x: number; y: number }> | null;
  objectIds: readonly string[];
}>;

export type ArchitectureObject = Readonly<{
  id: string;
  systemId: string;
  displayName: string;
  technicalName: string;
  fieldIds: readonly string[];
}>;

export type ArchitectureField = Readonly<{
  id: string;
  systemId: string;
  objectId: string;
  displayName: string;
  technicalName: string;
  dataType: string;
  required: boolean;
  nullable: boolean;
}>;

export type ArchitectureContract = Readonly<{
  id: string;
  name: string;
  interactionType: ArchitectureInteractionType;
  sourceSystemId: string;
  sourceObjectId: string;
  targetSystemId: string;
  targetObjectId: string;
  errorResponseObjectId: string | null;
  requestGraph: ArchitectureGraphSnapshot;
  responseGraph: ArchitectureGraphSnapshot;
  errorResponseGraph: ArchitectureGraphSnapshot;
  revision: number | null;
  savedState: Readonly<{ updatedAt: string | null }> | null;
  description: string | null;
  sampleRows: readonly unknown[];
  architectureHealth: Readonly<ArchitectureHealthMetadata> | null;
  validationStatus: ArchitectureValidationStatus;
}>;

export type ArchitectureHealthMetadata = {
  status: "draft" | "attention" | "healthy";
  reasons: readonly string[];
  conflictFields: readonly Readonly<{
    objectId: string;
    fieldId: string;
    objectLabel: string;
    fieldLabel: string;
  }>[];
};

export type ArchitectureValidationSummary = Readonly<{
  status: ArchitectureValidationStatus;
  validMappingCount: number;
  warningCount: number;
  errorCount: number;
  incompleteMappingCount: number;
  requiredUnmappedReceiverCount: number;
  optionalUnmappedReceiverCount: number;
}>;

export type ArchitecturePhase = Readonly<{
  contractId: string;
  phase: ArchitecturePhaseKind;
  configured: boolean;
  senderSystemId: string;
  senderObjectId: string | null;
  receiverSystemId: string;
  receiverObjectId: string;
  graph: Readonly<ArchitectureGraphDocument> | null;
  chains: readonly Readonly<MappingChain>[];
  validationSummary: ArchitectureValidationSummary;
}>;

export type ArchitectureDiagnosticCode =
  | "index_load_failed"
  | "systems_load_failed"
  | "contracts_load_failed"
  | "object_load_failed"
  | "field_load_failed"
  | "missing_contract_system"
  | "missing_contract_object"
  | "malformed_phase_graph"
  | "missing_referenced_field"
  | "unconfigured_error_response"
  | "mapping_graph_issue"
  | "duplicate_record_id"
  | "object_system_mismatch"
  | "field_object_mismatch";

export type ArchitectureDiagnostic = Readonly<{
  code: ArchitectureDiagnosticCode;
  message: string;
  contractId?: string;
  systemId?: string;
  objectId?: string;
  fieldId?: string;
  phase?: ArchitecturePhaseKind;
  issue?: MappingGraphIssue;
}>;

export type EnterpriseArchitectureIndex = Readonly<{
  state: ArchitectureIndexState;
  systemsById: ReadonlyMap<string, ArchitectureSystem>;
  objectsById: ReadonlyMap<string, ArchitectureObject>;
  fieldsById: ReadonlyMap<string, ArchitectureField>;
  contractsById: ReadonlyMap<string, ArchitectureContract>;
  phasesByContractId: ReadonlyMap<string, readonly ArchitecturePhase[]>;
  contractsBySystemId: ReadonlyMap<string, readonly string[]>;
  contractsByObjectId: ReadonlyMap<string, readonly string[]>;
  contractsByFieldId: ReadonlyMap<string, readonly string[]>;
  loadDiagnostics: readonly ArchitectureDiagnostic[];
}>;

export type ArchitectureLineageDirection = "upstream" | "downstream" | "both";

export type ArchitectureLineageField = Readonly<{
  key: string;
  systemId: string;
  objectId: string;
  fieldId: string;
  depth: number;
}>;

export type ArchitectureLineageHop = Readonly<{
  id: string;
  contractId: string;
  phase: ArchitecturePhaseKind;
  sender: Readonly<{
    systemId: string;
    objectId: string;
    fieldId: string;
  }>;
  receiver: Readonly<{
    systemId: string;
    objectId: string;
    fieldId: string;
  }>;
  transformations: readonly MappingChain["transformations"][number][];
  senderType: string;
  receiverType: string;
  validation: TypeValidationResult | null;
  issues: readonly MappingGraphIssue[];
}>;

export type ArchitectureLineageTrace = Readonly<{
  selectedFieldKey: string;
  direction: ArchitectureLineageDirection;
  maxDepth: number;
  fields: readonly ArchitectureLineageField[];
  hops: readonly Readonly<{
    hop: ArchitectureLineageHop;
    depth: number;
    traversalDirection: "upstream" | "downstream";
  }>[];
}>;

export type ArchitectureHealthRecord = {
  id: string;
  status: "draft" | "attention" | "healthy";
  reasons?: string[];
  conflict_fields?: {
    object_id: string;
    object_label: string;
    field_id: string;
    field_label: string;
  }[];
};

export type ArchitectureCatalogLoaders = {
  systems: readonly ArchitectureSystemRecord[];
  contracts: readonly ArchitectureContractRecord[];
  architectureHealth?: readonly ArchitectureHealthRecord[];
  loadDiagnostics?: readonly ArchitectureDiagnostic[];
  rootsPartial?: boolean;
  rootsFailed?: boolean;
  listObjectsForSystem: (systemId: string) => Promise<readonly ArchitectureObjectRecord[]>;
  listFieldsForObject: (objectId: string) => Promise<readonly ArchitectureFieldRecord[]>;
  concurrencyLimit?: number;
  onObjectsLoaded?: (objects: readonly ArchitectureObjectRecord[]) => void;
};

type LoadOutcome<T> = { value: T } | { error: unknown };

const DEFAULT_CONCURRENCY_LIMIT = 6;
function freezeDeep<T>(value: T, visited = new WeakSet<object>()): T {
  if (value === null || typeof value !== "object") return value;
  const objectValue = value as object;
  if (visited.has(objectValue)) return value;
  visited.add(objectValue);
  for (const nested of Object.values(objectValue)) freezeDeep(nested, visited);
  return Object.freeze(value);
}

function cloneDeep<T>(value: T, visited = new WeakMap<object, unknown>()): T {
  if (value === null || typeof value !== "object") return value;
  const objectValue = value as object;
  const prior = visited.get(objectValue);
  if (prior) return prior as T;
  if (Array.isArray(value)) {
    const copy: unknown[] = [];
    visited.set(objectValue, copy);
    for (const item of value) copy.push(cloneDeep(item, visited));
    return copy as T;
  }
  const copy: Record<string, unknown> = {};
  visited.set(objectValue, copy);
  for (const [key, nested] of Object.entries(value)) copy[key] = cloneDeep(nested, visited);
  return copy as T;
}

function readonlyMap<K, V>(entries: Iterable<readonly [K, V]>): ReadonlyMap<K, V> {
  const map = new Map(entries);
  let proxy: ReadonlyMap<K, V>;
  proxy = new Proxy(map, {
    get(target, property) {
      if (property === "set" || property === "delete" || property === "clear") {
        return () => {
          throw new TypeError("Architecture indexes are read-only.");
        };
      }
      if (property === "forEach") {
        return (
          callback: (value: V, key: K, map: ReadonlyMap<K, V>) => void,
          thisArg?: unknown,
        ) => target.forEach((value, key) => callback.call(thisArg, value, key, proxy));
      }
      if (property === "valueOf") return () => proxy;
      const value = Reflect.get(target, property, target) as unknown;
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
  return proxy;
}

async function mapWithConcurrency<T, R>(
  items: readonly T[],
  concurrencyLimit: number,
  mapper: (item: T, index: number) => Promise<R>,
): Promise<LoadOutcome<R>[]> {
  if (!Number.isInteger(concurrencyLimit) || concurrencyLimit < 1) {
    throw new RangeError("Concurrency limit must be a positive integer.");
  }
  const outcomes: LoadOutcome<R>[] = new Array(items.length);
  let nextIndex = 0;
  const workerCount = Math.min(concurrencyLimit, items.length);
  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      try {
        outcomes[index] = { value: await mapper(items[index]!, index) };
      } catch (error) {
        outcomes[index] = { error };
      }
    }
  }));
  return outcomes;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseGraph(raw: unknown): ArchitectureGraphSnapshot {
  const rawSnapshot = freezeDeep(cloneDeep(raw));
  if (!isRecord(raw)
    || typeof raw.version !== "number"
    || !Array.isArray(raw.nodes)
    || !Array.isArray(raw.edges)) {
    return { raw: rawSnapshot, document: null };
  }
  const validNodes = raw.nodes.every((node) =>
    isRecord(node)
    && typeof node.id === "string"
    && typeof node.type === "string"
    && isRecord(node.config));
  const validEdges = raw.edges.every((edge) =>
    isRecord(edge)
    && typeof edge.id === "string"
    && typeof edge.sourceNodeId === "string"
    && typeof edge.sourcePortId === "string"
    && typeof edge.targetNodeId === "string"
    && typeof edge.targetPortId === "string");
  if (!validNodes || !validEdges) return { raw: rawSnapshot, document: null };
  const document = freezeDeep(cloneDeep(raw)) as ArchitectureGraphDocument;
  return { raw: rawSnapshot, document };
}

function phaseKinds(interactionType: ArchitectureInteractionType): ArchitecturePhaseKind[] {
  if (interactionType === "ONE_WAY") return ["request"];
  return [
    "request",
    interactionType === "ASYNC_CALLBACK" ? "async-response" : "success-response",
    "error-response",
  ];
}

export function isSharedResponseGraphPhase(
  phase: string,
): phase is "success-response" | "async-response" {
  return phase === "success-response" || phase === "async-response";
}

export function isArchitectureResponsePhase(
  phase: string,
): phase is "success-response" | "async-response" | "error-response" {
  return isSharedResponseGraphPhase(phase) || phase === "error-response";
}

type PhaseEndpoint = {
  senderSystemId: string;
  senderObjectId: string | null;
  receiverSystemId: string;
  receiverObjectId: string;
  graph: ArchitectureGraphSnapshot;
  configured: boolean;
};

function phaseEndpoint(
  contract: ArchitectureContractRecord,
  phase: ArchitecturePhaseKind,
  requestGraph: ArchitectureGraphSnapshot,
  responseGraph: ArchitectureGraphSnapshot,
  errorGraph: ArchitectureGraphSnapshot,
): PhaseEndpoint {
  if (phase === "request") {
    return {
      senderSystemId: contract.source_system_id,
      senderObjectId: contract.source_object_id,
      receiverSystemId: contract.target_system_id,
      receiverObjectId: contract.target_object_id,
      graph: requestGraph,
      configured: true,
    };
  }
  if (isSharedResponseGraphPhase(phase)) {
    return {
      senderSystemId: contract.target_system_id,
      senderObjectId: contract.target_object_id,
      receiverSystemId: contract.source_system_id,
      receiverObjectId: contract.source_object_id,
      graph: responseGraph,
      configured: true,
    };
  }
  return {
    senderSystemId: contract.target_system_id,
    senderObjectId: contract.error_response_object_id ?? null,
    receiverSystemId: contract.source_system_id,
    receiverObjectId: contract.source_object_id,
    graph: errorGraph,
    configured: Boolean(contract.error_response_object_id),
  };
}

function emptySummary(status: ArchitectureValidationStatus): ArchitectureValidationSummary {
  return {
    status,
    validMappingCount: 0,
    warningCount: 0,
    errorCount: 0,
    incompleteMappingCount: 0,
    requiredUnmappedReceiverCount: 0,
    optionalUnmappedReceiverCount: 0,
  };
}

function validationSummary(
  chains: readonly MappingChain[],
  receiverFields: readonly ArchitectureField[],
  complete: boolean,
): ArchitectureValidationSummary {
  let validMappingCount = 0;
  let warningCount = 0;
  let errorCount = 0;
  let incompleteMappingCount = 0;
  const mappedReceiverIds = new Set<string>();
  for (const chain of chains) {
    if (chain.receiverFieldId) mappedReceiverIds.add(chain.receiverFieldId);
    const hasError = chain.validation?.status === "Error"
      || chain.issues.some((item) => item.severity === "Error");
    const hasWarning = chain.validation?.status === "Warning"
      || chain.issues.some((item) => item.severity === "Warning");
    if (chain.validation?.status === "Valid" && !hasError && !hasWarning) validMappingCount += 1;
    if (hasWarning) warningCount += 1;
    if (hasError) errorCount += 1;
    if (!chain.validation) incompleteMappingCount += 1;
  }
  let requiredUnmappedReceiverCount = 0;
  let optionalUnmappedReceiverCount = 0;
  for (const field of receiverFields) {
    if (mappedReceiverIds.has(field.id)) continue;
    if (field.required) requiredUnmappedReceiverCount += 1;
    else optionalUnmappedReceiverCount += 1;
  }
  errorCount += requiredUnmappedReceiverCount;
  const status: ArchitectureValidationStatus = !complete
    ? "Incomplete"
    : errorCount > 0
      ? "Errors"
      : warningCount > 0
        ? "Warnings"
        : "Valid";
  return {
    status,
    validMappingCount,
    warningCount,
    errorCount,
    incompleteMappingCount,
    requiredUnmappedReceiverCount,
    optionalUnmappedReceiverCount,
  };
}

function addIndexReference(index: Map<string, string[]>, key: string, contractId: string): void {
  const list = index.get(key) ?? [];
  if (!list.includes(contractId)) list.push(contractId);
  index.set(key, list);
}

function graphFieldReferences(graph: ArchitectureGraphSnapshot): string[] {
  if (!graph.document) return [];
  const result = new Set<string>();
  for (const edge of graph.document.edges) {
    const sourceId = fieldIdFromPort(edge.sourcePortId);
    const receiverId = fieldIdFromPort(edge.targetPortId);
    if (sourceId) result.add(sourceId);
    if (receiverId) result.add(receiverId);
  }
  return [...result];
}

function toHealthMetadata(
  record: ArchitectureHealthRecord | undefined,
): Readonly<ArchitectureHealthMetadata> | null {
  if (!record) return null;
  return freezeDeep({
    status: record.status,
    reasons: [...(record.reasons ?? [])],
    conflictFields: (record.conflict_fields ?? []).map((field) => ({
      objectId: field.object_id,
      fieldId: field.field_id,
      objectLabel: field.object_label,
      fieldLabel: field.field_label,
    })),
  });
}

function buildIndex(input: {
  systems: readonly ArchitectureSystemRecord[];
  contracts: readonly ArchitectureContractRecord[];
  objects: readonly ArchitectureObjectRecord[];
  fieldsByObjectId: ReadonlyMap<string, readonly ArchitectureFieldRecord[]>;
  failedFieldObjectIds: ReadonlySet<string>;
  diagnostics: ArchitectureDiagnostic[];
  rootsFailed: boolean;
  rootsPartial: boolean;
  architectureHealth: readonly ArchitectureHealthRecord[];
}): EnterpriseArchitectureIndex {
  const diagnostics = input.diagnostics;
  const systemsMutable = new Map<string, {
    id: string;
    name: string;
    kind: string;
    description: string | null;
    icon: string | null;
    color: string | null;
    position: { x: number; y: number } | null;
    objectIds: string[];
  }>();
  const objectsMutable = new Map<string, {
    id: string;
    systemId: string;
    displayName: string;
    technicalName: string;
    fieldIds: string[];
  }>();
  const fieldsMutable = new Map<string, ArchitectureField>();
  const contractsMutable = new Map<string, ArchitectureContract>();
  const phasesMutable = new Map<string, readonly ArchitecturePhase[]>();
  const contractsBySystem = new Map<string, string[]>();
  const contractsByObject = new Map<string, string[]>();
  const contractsByField = new Map<string, string[]>();
  const seenSystemIds = new Set<string>();
  const seenObjectIds = new Set<string>();
  const seenFieldIds = new Set<string>();
  const healthById = new Map(input.architectureHealth.map((item) => [item.id, item]));

  for (const system of input.systems) {
    if (seenSystemIds.has(system.id)) {
      diagnostics.push({ code: "duplicate_record_id", message: `Duplicate system ID ${system.id}.`, systemId: system.id });
      continue;
    }
    seenSystemIds.add(system.id);
    systemsMutable.set(system.id, {
      id: system.id,
      name: system.name,
      kind: system.kind,
      description: system.description ?? null,
      icon: system.icon ?? null,
      color: system.color ?? null,
      position: system.position ? { ...system.position } : null,
      objectIds: [],
    });
  }

  for (const object of input.objects) {
    if (seenObjectIds.has(object.id)) {
      diagnostics.push({ code: "duplicate_record_id", message: `Duplicate object ID ${object.id}.`, objectId: object.id });
      continue;
    }
    seenObjectIds.add(object.id);
    const system = systemsMutable.get(object.system_id);
    if (!system) {
      diagnostics.push({
        code: "object_system_mismatch",
        message: `Object ${object.id} belongs to unavailable system ${object.system_id}.`,
        systemId: object.system_id,
        objectId: object.id,
      });
      continue;
    }
    system.objectIds.push(object.id);
    objectsMutable.set(object.id, {
      id: object.id,
      systemId: object.system_id,
      displayName: object.label,
      technicalName: object.name,
      fieldIds: [],
    });
  }

  for (const [objectId, fields] of input.fieldsByObjectId) {
    const object = objectsMutable.get(objectId);
    if (!object) continue;
    for (const field of fields) {
      if (seenFieldIds.has(field.id)) {
        diagnostics.push({ code: "duplicate_record_id", message: `Duplicate field ID ${field.id}.`, objectId, fieldId: field.id });
        continue;
      }
      seenFieldIds.add(field.id);
      if (field.object_id !== objectId) {
        diagnostics.push({
          code: "field_object_mismatch",
          message: `Field ${field.id} was returned for object ${objectId} but belongs to ${field.object_id}.`,
          objectId,
          fieldId: field.id,
        });
        continue;
      }
      object.fieldIds.push(field.id);
      fieldsMutable.set(field.id, freezeDeep({
        id: field.id,
        systemId: object.systemId,
        objectId,
        displayName: field.label ?? field.name,
        technicalName: field.name,
        dataType: field.data_type,
        required: Boolean(field.required),
        nullable: field.nullable ?? !field.required,
      }));
    }
  }

  for (const contractRecord of input.contracts) {
    if (contractsMutable.has(contractRecord.id)) {
      diagnostics.push({ code: "duplicate_record_id", message: `Duplicate contract ID ${contractRecord.id}.`, contractId: contractRecord.id });
      continue;
    }
    const requestGraph = parseGraph(contractRecord.graph);
    const responseGraph = parseGraph(contractRecord.response_graph);
    const errorResponseGraph = parseGraph(contractRecord.error_response_graph);
    const contract = freezeDeep({
      id: contractRecord.id,
      name: contractRecord.name,
      interactionType: contractRecord.interaction_type,
      sourceSystemId: contractRecord.source_system_id,
      sourceObjectId: contractRecord.source_object_id,
      targetSystemId: contractRecord.target_system_id,
      targetObjectId: contractRecord.target_object_id,
      errorResponseObjectId: contractRecord.error_response_object_id ?? null,
      requestGraph,
      responseGraph,
      errorResponseGraph,
      revision: contractRecord.revision ?? null,
      savedState: contractRecord.updated_at ? { updatedAt: contractRecord.updated_at } : null,
      description: contractRecord.description ?? null,
      sampleRows: cloneDeep(contractRecord.sample_rows ?? []),
      architectureHealth: toHealthMetadata(healthById.get(contractRecord.id)),
      validationStatus: "Incomplete" as ArchitectureValidationStatus,
    });
    contractsMutable.set(contract.id, contract);

    for (const systemId of new Set([contract.sourceSystemId, contract.targetSystemId])) {
      addIndexReference(contractsBySystem, systemId, contract.id);
      if (!systemsMutable.has(systemId)) {
        diagnostics.push({
          code: "missing_contract_system",
          message: `Contract ${contract.id} references missing system ${systemId}.`,
          contractId: contract.id,
          systemId,
        });
      }
    }
    const endpointObjectIds = new Set([
      contract.sourceObjectId,
      contract.targetObjectId,
      ...(contract.errorResponseObjectId ? [contract.errorResponseObjectId] : []),
    ]);
    for (const objectId of endpointObjectIds) {
      addIndexReference(contractsByObject, objectId, contract.id);
      if (!objectsMutable.has(objectId)) {
        diagnostics.push({
          code: "missing_contract_object",
          message: `Contract ${contract.id} references missing object ${objectId}.`,
          contractId: contract.id,
          objectId,
        });
      }
    }
    const allGraphs = phaseKinds(contract.interactionType).map((phase) => [
      phase,
      phase === "request"
        ? requestGraph
        : isSharedResponseGraphPhase(phase)
          ? responseGraph
          : errorResponseGraph,
    ] as const);
    for (const [phase, graph] of allGraphs) {
      if (graph.document) {
        for (const fieldId of graphFieldReferences(graph)) {
          addIndexReference(contractsByField, fieldId, contract.id);
        }
      } else if (phase !== "error-response" || contract.errorResponseObjectId) {
        diagnostics.push({
          code: "malformed_phase_graph",
          message: `Contract ${contract.id} has a malformed ${phase} graph.`,
          contractId: contract.id,
          phase,
        });
      }
    }

    const phases: ArchitecturePhase[] = [];
    for (const phaseKind of phaseKinds(contract.interactionType)) {
      const endpoint = phaseEndpoint(
        contractRecord,
        phaseKind,
        requestGraph,
        responseGraph,
        errorResponseGraph,
      );
      if (phaseKind === "error-response" && !endpoint.configured) {
        diagnostics.push({
          code: "unconfigured_error_response",
          message: `Contract ${contract.id} has no configured error response object.`,
          contractId: contract.id,
          phase: phaseKind,
        });
      }
      if (!endpoint.configured) {
        phases.push(freezeDeep({
          contractId: contract.id,
          phase: phaseKind,
          configured: false,
          senderSystemId: endpoint.senderSystemId,
          senderObjectId: endpoint.senderObjectId,
          receiverSystemId: endpoint.receiverSystemId,
          receiverObjectId: endpoint.receiverObjectId,
          graph: endpoint.graph.document,
          chains: [],
          validationSummary: emptySummary("Unconfigured"),
        }));
        continue;
      }
      const senderObject = endpoint.senderObjectId
        ? objectsMutable.get(endpoint.senderObjectId)
        : undefined;
      const receiverObject = objectsMutable.get(endpoint.receiverObjectId);
      const senderFieldsLoaded = Boolean(endpoint.senderObjectId)
        && !input.failedFieldObjectIds.has(endpoint.senderObjectId ?? "");
      const receiverFieldsLoaded = !input.failedFieldObjectIds.has(endpoint.receiverObjectId);
      const graphIsValid = endpoint.graph.document !== null;
      const endpointExists = Boolean(senderObject && receiverObject);
      const evaluable = senderFieldsLoaded && receiverFieldsLoaded && graphIsValid && endpointExists;
      const senderFields = senderObject?.fieldIds.flatMap((id) => {
        const field = fieldsMutable.get(id);
        return field ? [{
          id: field.id,
          data_type: field.dataType,
          required: field.required,
          nullable: field.nullable,
        }] : [];
      }) ?? [];
      const receiverFields = receiverObject?.fieldIds.flatMap((id) => {
        const field = fieldsMutable.get(id);
        return field ? [{
          id: field.id,
          data_type: field.dataType,
          required: field.required,
          nullable: field.nullable,
        }] : [];
      }) ?? [];
      const chains = evaluable
        ? deriveMappingChains({
          graph: {
            nodes: cloneDeep(endpoint.graph.document!.nodes) as MappingGraphNode[],
            edges: cloneDeep(endpoint.graph.document!.edges) as MappingGraphEdge[],
          } satisfies MappingGraphDocument,
          senderFields,
          receiverFields,
        })
        : [];
      for (const chain of chains) {
        for (const graphIssue of chain.issues) {
          diagnostics.push({
            code: "mapping_graph_issue",
            message: graphIssue.message,
            contractId: contract.id,
            phase: phaseKind,
            issue: freezeDeep(cloneDeep(graphIssue)),
          });
          for (const fieldId of [...graphIssue.senderFieldIds, ...graphIssue.receiverFieldIds]) {
            addIndexReference(contractsByField, fieldId, contract.id);
          }
          for (const [fieldId, endpointObjectId, schemaLoaded] of [
            ...graphIssue.senderFieldIds.map((fieldId) => [
              fieldId,
              endpoint.senderObjectId,
              senderFieldsLoaded,
            ] as const),
            ...graphIssue.receiverFieldIds.map((fieldId) => [
              fieldId,
              endpoint.receiverObjectId,
              receiverFieldsLoaded,
            ] as const),
          ]) {
            const existsAtEndpoint = endpointObjectId
              ? objectsMutable.get(endpointObjectId)?.fieldIds.includes(fieldId) ?? false
              : false;
            if (schemaLoaded && !existsAtEndpoint) {
              diagnostics.push({
                code: "missing_referenced_field",
                message: `Contract ${contract.id} ${phaseKind} graph references missing field ${fieldId}.`,
                contractId: contract.id,
                phase: phaseKind,
                fieldId,
              });
            }
          }
        }
      }
      const summary = validationSummary(chains, receiverFields.map((field) => {
        const indexed = fieldsMutable.get(field.id)!;
        return indexed;
      }), evaluable);
      phases.push(freezeDeep({
        contractId: contract.id,
        phase: phaseKind,
        configured: true,
        senderSystemId: endpoint.senderSystemId,
        senderObjectId: endpoint.senderObjectId,
        receiverSystemId: endpoint.receiverSystemId,
        receiverObjectId: endpoint.receiverObjectId,
        graph: endpoint.graph.document,
        chains,
        validationSummary: summary,
      }));
    }
    phasesMutable.set(contract.id, freezeDeep(phases));
    const configuredPhases = phases.filter((phase) => phase.configured);
    const rollup: ArchitectureValidationStatus = configuredPhases.some(
      (phase) => phase.validationSummary.errorCount > 0,
    )
      ? "Errors"
      : configuredPhases.some((phase) => phase.validationSummary.status === "Incomplete")
        ? "Incomplete"
        : configuredPhases.some((phase) => phase.validationSummary.warningCount > 0)
          ? "Warnings"
          : "Valid";
    contractsMutable.set(contract.id, freezeDeep({ ...contract, validationStatus: rollup }));
  }

  const isDataFailure = (diagnostic: ArchitectureDiagnostic) => [
    "index_load_failed",
    "systems_load_failed",
    "contracts_load_failed",
    "object_load_failed",
    "field_load_failed",
    "missing_contract_system",
    "missing_contract_object",
    "malformed_phase_graph",
    "missing_referenced_field",
    "duplicate_record_id",
    "object_system_mismatch",
    "field_object_mismatch",
  ].includes(diagnostic.code);
  const hasDataFailures = diagnostics.some(isDataFailure);
  const state: ArchitectureIndexState = input.rootsFailed
    ? "failed"
    : input.rootsPartial || hasDataFailures
      ? "partial"
      : "complete";
  return freezeDeep({
    state,
    systemsById: readonlyMap([...systemsMutable].map(([id, system]) => [id, freezeDeep({
      ...system,
      objectIds: [...system.objectIds],
    })] as const)),
    objectsById: readonlyMap([...objectsMutable].map(([id, object]) => [id, freezeDeep({
      ...object,
      fieldIds: [...object.fieldIds],
    })] as const)),
    fieldsById: readonlyMap(fieldsMutable),
    contractsById: readonlyMap(contractsMutable),
    phasesByContractId: readonlyMap(phasesMutable),
    contractsBySystemId: readonlyMap([...contractsBySystem].map(([key, value]) => [key, freezeDeep([...value])] as const)),
    contractsByObjectId: readonlyMap([...contractsByObject].map(([key, value]) => [key, freezeDeep([...value])] as const)),
    contractsByFieldId: readonlyMap([...contractsByField].map(([key, value]) => [key, freezeDeep([...value])] as const)),
    loadDiagnostics: freezeDeep(diagnostics),
  });
}

export async function loadEnterpriseArchitectureIndex(
  input: ArchitectureCatalogLoaders,
): Promise<EnterpriseArchitectureIndex> {
  const diagnostics: ArchitectureDiagnostic[] = [...(input.loadDiagnostics ?? [])];
  const systems = input.systems;
  const contracts = input.contracts;
  const concurrencyLimit = input.concurrencyLimit ?? DEFAULT_CONCURRENCY_LIMIT;
  const systemObjectOutcomes = await mapWithConcurrency(
    systems,
    concurrencyLimit,
    (system) => input.listObjectsForSystem(system.id),
  );
  const objects: ArchitectureObjectRecord[] = [];
  systemObjectOutcomes.forEach((outcome, index) => {
    const system = systems[index]!;
    if ("error" in outcome) {
      diagnostics.push({
        code: "object_load_failed",
        message: outcome.error instanceof Error ? outcome.error.message : "Could not load system objects.",
        systemId: system.id,
      });
      return;
    }
    objects.push(...outcome.value);
  });
  input.onObjectsLoaded?.(objects);

  const fieldsByObjectId = new Map<string, readonly ArchitectureFieldRecord[]>();
  const failedFieldObjectIds = new Set<string>();
  const fieldOutcomes = await mapWithConcurrency(
    objects,
    concurrencyLimit,
    (object) => input.listFieldsForObject(object.id),
  );
  fieldOutcomes.forEach((outcome, index) => {
    const object = objects[index]!;
    if ("error" in outcome) {
      failedFieldObjectIds.add(object.id);
      diagnostics.push({
        code: "field_load_failed",
        message: outcome.error instanceof Error ? outcome.error.message : "Could not load object fields.",
        systemId: object.system_id,
        objectId: object.id,
      });
      return;
    }
    fieldsByObjectId.set(object.id, outcome.value);
  });

  return buildIndex({
    systems,
    contracts,
    objects,
    fieldsByObjectId,
    failedFieldObjectIds,
    diagnostics,
    rootsFailed: input.rootsFailed ?? false,
    rootsPartial: input.rootsPartial ?? false,
    architectureHealth: input.architectureHealth ?? [],
  });
}

export const architectureIndexConcurrencyLimit = DEFAULT_CONCURRENCY_LIMIT;

export function architectureFieldKey(
  systemId: string,
  objectId: string,
  fieldId: string,
): string {
  return JSON.stringify([systemId, objectId, fieldId]);
}

function lineageHops(index: EnterpriseArchitectureIndex): ArchitectureLineageHop[] {
  const result: ArchitectureLineageHop[] = [];
  for (const [contractId, phases] of index.phasesByContractId) {
    for (const phase of phases) {
      if (!phase.configured || !phase.senderObjectId) continue;
      for (const chain of phase.chains) {
        if (!chain.receiverFieldId) continue;
        for (const input of chain.inputs) {
          if (!input.senderFieldId) continue;
          const sender = index.fieldsById.get(input.senderFieldId);
          const receiver = index.fieldsById.get(chain.receiverFieldId);
          if (!sender || !receiver) continue;
          if (sender.objectId !== phase.senderObjectId
            || sender.systemId !== phase.senderSystemId
            || receiver.objectId !== phase.receiverObjectId
            || receiver.systemId !== phase.receiverSystemId) continue;
          result.push(freezeDeep({
            id: JSON.stringify([
              contractId,
              phase.phase,
              chain.receiverEdgeId,
              input.senderFieldId,
              input.edgeIds,
            ]),
            contractId,
            phase: phase.phase,
            sender: { systemId: sender.systemId, objectId: sender.objectId, fieldId: sender.id },
            receiver: { systemId: receiver.systemId, objectId: receiver.objectId, fieldId: receiver.id },
            transformations: chain.transformations,
            senderType: sender.dataType,
            receiverType: receiver.dataType,
            validation: chain.validation,
            issues: chain.issues,
          }));
        }
      }
    }
  }
  return result;
}

export function traceFieldLineage(
  index: EnterpriseArchitectureIndex,
  selectedField: { systemId: string; objectId: string; fieldId: string },
  direction: ArchitectureLineageDirection,
  maxDepth: number,
): ArchitectureLineageTrace {
  if (!Number.isInteger(maxDepth) || maxDepth < 1) {
    throw new RangeError("Lineage depth must be a positive integer.");
  }
  const selectedFieldKey = architectureFieldKey(
    selectedField.systemId,
    selectedField.objectId,
    selectedField.fieldId,
  );
  const selected = index.fieldsById.get(selectedField.fieldId);
  if (!selected
    || selected.systemId !== selectedField.systemId
    || selected.objectId !== selectedField.objectId) {
    throw new Error("The selected field is not present at the supplied system and object endpoint.");
  }

  const hops = lineageHops(index);
  const upstream = new Map<string, ArchitectureLineageHop[]>();
  const downstream = new Map<string, ArchitectureLineageHop[]>();
  const keyFor = (endpoint: ArchitectureLineageHop["sender"]) =>
    architectureFieldKey(endpoint.systemId, endpoint.objectId, endpoint.fieldId);
  for (const hop of hops) {
    const senderKey = keyFor(hop.sender);
    const receiverKey = keyFor(hop.receiver);
    downstream.set(senderKey, [...(downstream.get(senderKey) ?? []), hop]);
    upstream.set(receiverKey, [...(upstream.get(receiverKey) ?? []), hop]);
  }

  const depths = new Map<string, number>([[selectedFieldKey, 0]]);
  const traversalHops = new Map<string, ArchitectureLineageTrace["hops"][number]>();
  const queue = [selectedFieldKey];
  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const currentKey = queue[cursor]!;
    const depth = depths.get(currentKey)!;
    if (depth >= maxDepth) continue;
    const candidates: { hop: ArchitectureLineageHop; nextKey: string; traversalDirection: "upstream" | "downstream" }[] = [];
    if (direction === "upstream" || direction === "both") {
      for (const hop of upstream.get(currentKey) ?? []) {
        candidates.push({ hop, nextKey: keyFor(hop.sender), traversalDirection: "upstream" });
      }
    }
    if (direction === "downstream" || direction === "both") {
      for (const hop of downstream.get(currentKey) ?? []) {
        candidates.push({ hop, nextKey: keyFor(hop.receiver), traversalDirection: "downstream" });
      }
    }
    for (const candidate of candidates) {
      const nextDepth = depth + 1;
      const priorDepth = depths.get(candidate.nextKey);
      if (priorDepth === undefined) {
        depths.set(candidate.nextKey, nextDepth);
        queue.push(candidate.nextKey);
      } else if (priorDepth < nextDepth) {
        continue;
      }
      if (!traversalHops.has(candidate.hop.id)) {
        traversalHops.set(candidate.hop.id, {
          hop: candidate.hop,
          depth: nextDepth,
          traversalDirection: candidate.traversalDirection,
        });
      }
    }
  }

  const fields: ArchitectureLineageField[] = [];
  for (const [key, depth] of depths) {
    const [systemId, objectId, fieldId] = JSON.parse(key) as [string, string, string];
    fields.push(freezeDeep({ key, systemId, objectId, fieldId, depth }));
  }
  return freezeDeep({
    selectedFieldKey,
    direction,
    maxDepth,
    fields,
    hops: [...traversalHops.values()],
  });
}

export function createFailedEnterpriseArchitectureIndex(message: string): EnterpriseArchitectureIndex {
  return buildIndex({
    systems: [],
    contracts: [],
    objects: [],
    fieldsByObjectId: new Map(),
    failedFieldObjectIds: new Set(),
    diagnostics: [{ code: "index_load_failed", message }],
    rootsFailed: true,
    rootsPartial: false,
    architectureHealth: [],
  });
}
