import type {
  ChannelKind,
  FlowNodeRole,
  FlowPhaseName,
  IntegrationContractSummary,
  IntegrationFlowPhase,
  IntegrationInterfaceRef,
  IntegrationInterfaceSummary,
  IntegrationLandscape,
  IntegrationMessageFlow,
  IntegrationScenarioSequence,
  IntegrationSequence,
  IntegrationSequenceParticipant,
} from "./integrationDesignModel";

/** Purpose-specific Integration Architecture views. Landscape stays the default. */
export type IntegrationViewId =
  | "landscape"
  | "contract"
  | "flow"
  | "mapping"
  | "scenarios"
  | "conformance";

export const INTEGRATION_VIEWS: {
  id: IntegrationViewId;
  label: string;
  description: string;
}[] = [
  {
    id: "landscape",
    label: "Landscape",
    description: "Visual topology of systems, interfaces, contracts and runtimes.",
  },
  {
    id: "contract",
    label: "Interface & Channel",
    description: "Provided and required interfaces, operations, protocol and channel.",
  },
  {
    id: "flow",
    label: "Message Flow",
    description: "End-to-end flow stages per contract phase.",
  },
  {
    id: "mapping",
    label: "Transformation & Mapping",
    description: "Mapping coverage and transformations over the existing engine.",
  },
  {
    id: "scenarios",
    label: "Scenario & Sequence",
    description: "Participants and ordered interactions per scenario.",
  },
  {
    id: "conformance",
    label: "Test & Conformance",
    description: "Scenario status, coverage and outstanding configuration.",
  },
];

export const CHANNEL_LABELS: Record<ChannelKind, string> = {
  api: "API endpoint",
  event: "Event / topic",
  file: "File exchange",
};

export const FLOW_ROLE_LABELS: Record<FlowNodeRole, string> = {
  validation: "Validation",
  routing: "Routing decision",
  transformation: "Transformation",
  constant: "Constant",
};

export const SEQUENCE_CATEGORY_LABELS: Record<string, string> = {
  happy_path: "Happy path",
  alternative: "Alternative",
  error: "Error",
};

// --- Topology -----------------------------------------------------------------

export type IntegrationTopologyNodeKind =
  | "system"
  | "runtime"
  | "solution"
  | "interface"
  | "contract";

export type IntegrationTopologyNode = {
  id: string;
  refId: string;
  kind: IntegrationTopologyNodeKind;
  name: string;
  subtitle: string | null;
  detail: string | null;
  badge: string | null;
  pattern: string | null;
  status: string | null;
  direction: string | null;
  runtime: boolean;
  mediated: boolean;
};

export type IntegrationTopologyEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
};

export type IntegrationTopology = {
  nodes: IntegrationTopologyNode[];
  edges: IntegrationTopologyEdge[];
  mediatedContractIds: string[];
};

export function interfaceRelation(iface: IntegrationInterfaceRef): string {
  return iface.direction === "required" ? "requires" : "provides";
}

function channelRelation(pattern: string | null): string {
  if (
    pattern === "publish_subscribe" ||
    pattern === "event_streaming" ||
    pattern === "message_queue"
  ) {
    return "publishes";
  }
  if (pattern === "file_transfer" || pattern === "batch") return "sends file";
  return "invokes";
}

/**
 * Builds the Landscape topology from the existing landscape projection only. It
 * reuses canonical system, interface and contract ids; edges describe the
 * modelled direction of each interaction and are never invented. A contract is
 * "mediated" only when a modelled runtime system is one of its endpoints.
 */
export function integrationTopology(landscape: IntegrationLandscape): IntegrationTopology {
  const nodes = new Map<string, IntegrationTopologyNode>();
  const edges: IntegrationTopologyEdge[] = [];
  const seenEdges = new Set<string>();
  const mediatedContractIds: string[] = [];

  const addNode = (node: IntegrationTopologyNode): IntegrationTopologyNode => {
    const existing = nodes.get(node.id);
    if (existing) return existing;
    nodes.set(node.id, node);
    return node;
  };

  const addEdge = (source: string, target: string, relation: string): void => {
    if (source === target) return;
    const id = `${source}->${target}:${relation}`;
    if (seenEdges.has(id)) return;
    seenEdges.add(id);
    edges.push({ id, source, target, relation });
  };

  const systemNode = (endpoint: {
    system_id: string;
    system_name: string;
    system_kind?: string | null;
    is_runtime?: boolean;
  }): IntegrationTopologyNode =>
    addNode({
      id: `system:${endpoint.system_id}`,
      refId: endpoint.system_id,
      kind: endpoint.is_runtime ? "runtime" : "system",
      name: endpoint.system_name,
      subtitle: endpoint.is_runtime ? "Integration runtime" : endpoint.system_kind ?? null,
      detail: null,
      badge: null,
      pattern: null,
      status: null,
      direction: null,
      runtime: Boolean(endpoint.is_runtime),
      mediated: false,
    });

  const interfaceNode = (iface: IntegrationInterfaceRef): IntegrationTopologyNode =>
    addNode({
      id: `interface:${iface.object_id}`,
      refId: iface.object_id,
      kind: "interface",
      name: iface.name,
      subtitle: iface.direction ?? null,
      detail: [iface.interface_kind, iface.protocol].filter(Boolean).join(" · ") || null,
      badge: iface.direction ?? null,
      pattern: null,
      status: null,
      direction: iface.direction ?? null,
      runtime: false,
      mediated: false,
    });

  const componentEdge = (
    summary: IntegrationInterfaceSummary,
    iface: IntegrationInterfaceRef,
    targetId: string,
  ): void => {
    if (!summary.component_object_id) return;
    addNode({
      id: `component:${summary.component_object_id}`,
      refId: summary.component_object_id,
      kind: "solution",
      name: summary.component_name ?? "Component",
      subtitle: "Solution component",
      detail: null,
      badge: null,
      pattern: null,
      status: null,
      direction: null,
      runtime: false,
      mediated: false,
    });
    addEdge(`component:${summary.component_object_id}`, targetId, interfaceRelation(iface));
  };

  const summaryById = new Map(landscape.interfaces.map((item) => [item.object_id, item]));

  for (const contract of landscape.contracts) {
    const contractId = `contract:${contract.id}`;
    const mediated = Boolean(contract.source.is_runtime || contract.target.is_runtime);
    if (mediated) mediatedContractIds.push(contract.id);
    addNode({
      id: contractId,
      refId: contract.id,
      kind: "contract",
      name: contract.name,
      subtitle: contract.interaction_type,
      detail: null,
      badge: contract.status,
      pattern: contract.pattern ?? null,
      status: contract.status,
      direction: null,
      runtime: false,
      mediated,
    });

    const source = systemNode(contract.source);
    const target = systemNode(contract.target);
    const producer = contract.producer_interface;
    const consumer = contract.consumer_interface;

    if (producer) {
      const producerNode = interfaceNode(producer);
      const summary = summaryById.get(producer.object_id);
      if (summary) componentEdge(summary, producer, producerNode.id);
      addEdge(source.id, producerNode.id, interfaceRelation(producer));
      addEdge(producerNode.id, contractId, channelRelation(contract.pattern));
    } else {
      addEdge(source.id, contractId, "produces");
    }

    if (consumer) {
      const consumerNode = interfaceNode(consumer);
      const summary = summaryById.get(consumer.object_id);
      if (summary) componentEdge(summary, consumer, consumerNode.id);
      addEdge(contractId, consumerNode.id, "delivers");
      addEdge(consumerNode.id, target.id, "consumes");
    } else {
      addEdge(contractId, target.id, mediated ? "mediated by" : "delivers");
    }
  }

  return { nodes: [...nodes.values()], edges, mediatedContractIds };
}

export type IntegrationLayoutPoint = { x: number; y: number };

/**
 * Layered left-to-right layout shared by the topology and sequence projections.
 * Nodes are placed by their longest path from a root so directed flows read
 * left-to-right, stacked within each layer. Deterministic for a given input.
 */
export function layeredLayout(
  ids: string[],
  edges: { source: string; target: string }[],
  columnGap = 260,
  rowGap = 110,
): Map<string, IntegrationLayoutPoint> {
  const known = new Set(ids);
  const adjacency = new Map<string, string[]>();
  const level = new Map<string, number>();
  for (const id of ids) {
    adjacency.set(id, []);
    level.set(id, 0);
  }
  for (const edge of edges) {
    if (known.has(edge.source) && known.has(edge.target) && edge.source !== edge.target) {
      adjacency.get(edge.source)!.push(edge.target);
    }
  }
  let changed = true;
  let guard = 0;
  while (changed && guard <= ids.length + 1) {
    changed = false;
    guard += 1;
    for (const [source, targets] of adjacency) {
      for (const target of targets) {
        const next = (level.get(source) ?? 0) + 1;
        if (next > (level.get(target) ?? 0)) {
          level.set(target, next);
          changed = true;
        }
      }
    }
  }
  const rows = new Map<number, number>();
  const positions = new Map<string, IntegrationLayoutPoint>();
  const ordered = [...ids].sort((a, b) => {
    const byLevel = (level.get(a) ?? 0) - (level.get(b) ?? 0);
    return byLevel !== 0 ? byLevel : a.localeCompare(b);
  });
  for (const id of ordered) {
    const lane = level.get(id) ?? 0;
    const row = rows.get(lane) ?? 0;
    rows.set(lane, row + 1);
    positions.set(id, { x: 40 + lane * columnGap, y: 40 + row * rowGap });
  }
  return positions;
}

// --- Flow designer ------------------------------------------------------------

export type FlowStageRole =
  | "system"
  | "interface"
  | "channel"
  | "runtime"
  | "validation"
  | "routing"
  | "transformation"
  | "constant"
  | "metadata";

export type FlowStage = {
  id: string;
  role: FlowStageRole;
  label: string;
  detail: string | null;
  configured: boolean;
  metadata: boolean;
};

export function phaseDirection(phase: FlowPhaseName): "request" | "response" {
  return phase === "request" ? "request" : "response";
}

/** Ordered stages for one contract phase, in its actual data-flow direction. */
export function flowStages(flow: IntegrationMessageFlow, phase: IntegrationFlowPhase): FlowStage[] {
  const contract = flow.contract;
  const mediated = Boolean(contract.source.is_runtime || contract.target.is_runtime);
  const reverse = phaseDirection(phase.phase) === "response";

  const sourceStage: FlowStage = {
    id: `system:${contract.source.system_id}`,
    role: contract.source.is_runtime ? "runtime" : "system",
    label: contract.source.system_name,
    detail: contract.source.is_runtime
      ? `${contract.source.object_name} · mediated path`
      : contract.source.object_name,
    configured: true,
    metadata: false,
  };
  const targetStage: FlowStage = {
    id: `system:${contract.target.system_id}`,
    role: contract.target.is_runtime ? "runtime" : "system",
    label: contract.target.system_name,
    detail: contract.target.is_runtime
      ? `${contract.target.object_name} · mediated path`
      : contract.target.object_name,
    configured: true,
    metadata: false,
  };

  const producerInterface = contract.producer_interface
    ? ({
        id: `interface:${contract.producer_interface.object_id}`,
        role: "interface" as const,
        label: contract.producer_interface.name,
        detail: [contract.producer_interface.direction, contract.producer_interface.protocol]
          .filter(Boolean)
          .join(" · "),
        configured: true,
        metadata: false,
      } satisfies FlowStage)
    : null;

  const consumerInterface = contract.consumer_interface
    ? ({
        id: `interface:${contract.consumer_interface.object_id}`,
        role: "interface" as const,
        label: contract.consumer_interface.name,
        detail: [contract.consumer_interface.direction, contract.consumer_interface.protocol]
          .filter(Boolean)
          .join(" · "),
        configured: true,
        metadata: false,
      } satisfies FlowStage)
    : null;

  const channelStage: FlowStage = {
    id: `channel:${phase.phase}`,
    role: "channel",
    label: flow.channel_label ?? "Channel not configured",
    detail: [reverse ? "response" : "request", mediated ? "via Integration Runtime" : null]
      .filter(Boolean)
      .join(" · "),
    configured: Boolean(flow.channel_kind),
    metadata: false,
  };

  const graphStages: FlowStage[] = [...phase.transformations]
    .sort(
      (a, b) => (a.position?.x ?? 0) - (b.position?.x ?? 0) || a.node_id.localeCompare(b.node_id),
    )
    .map((item) => ({
      id: item.node_id,
      role: item.role,
      label: item.label,
      detail: item.type,
      configured: true,
      metadata: false,
    }));

  const metadataStages = flowMetadataStages(flow, phase);

  const stages: FlowStage[] = [
    sourceStage,
    ...(producerInterface ? [producerInterface] : []),
    channelStage,
    ...graphStages,
    ...metadataStages,
    ...(consumerInterface ? [consumerInterface] : []),
    targetStage,
  ];

  return reverse ? [...stages].reverse() : stages;
}

/**
 * Resilience/recovery properties that exist only as metadata are surfaced as
 * explicit, annotated stages so the diagram never implies a processing step it
 * cannot prove.
 */
export function flowMetadataStages(
  flow: IntegrationMessageFlow,
  phase: IntegrationFlowPhase,
): FlowStage[] {
  const spec = flow.contract.specification ?? {};
  const stages: FlowStage[] = [];
  const hasRoutingNode = phase.transformations.some((item) => item.role === "routing");
  const hasValidationNode = phase.transformations.some((item) => item.role === "validation");
  const isRequest = phase.phase === "request";

  if (isRequest && flow.routing && !hasRoutingNode) {
    stages.push({
      id: `metadata:routing:${phase.phase}`,
      role: "metadata",
      label: "Routing",
      detail: flow.routing,
      configured: true,
      metadata: true,
    });
  }
  if (isRequest && !hasValidationNode && spec.security?.auth_type && spec.security.auth_type !== "none") {
    stages.push({
      id: `metadata:auth:${phase.phase}`,
      role: "metadata",
      label: "Authentication",
      detail: `${spec.security.auth_type}${spec.security.notes ? ` · ${spec.security.notes}` : ""}`,
      configured: true,
      metadata: true,
    });
  }
  if (isRequest && (spec.retry?.max_attempts ?? 0) > 0) {
    stages.push({
      id: `metadata:retry:${phase.phase}`,
      role: "metadata",
      label: "Retry",
      detail: `${spec.retry?.max_attempts} attempts · ${spec.retry?.backoff ?? "none"} backoff`,
      configured: true,
      metadata: true,
    });
  }
  if (isRequest && spec.timeout_ms) {
    stages.push({
      id: `metadata:timeout:${phase.phase}`,
      role: "metadata",
      label: "Timeout",
      detail: `${spec.timeout_ms} ms`,
      configured: true,
      metadata: true,
    });
  }
  if (isRequest && spec.idempotent) {
    stages.push({
      id: `metadata:idempotency:${phase.phase}`,
      role: "metadata",
      label: "Idempotency",
      detail: flow.contract.idempotency_key_field_name ?? "enabled",
      configured: true,
      metadata: true,
    });
  }
  const isError = phase.phase === "error-response";
  if (isError && spec.error_handling) {
    stages.push({
      id: `metadata:recovery:${phase.phase}`,
      role: "metadata",
      label: "Recovery",
      detail: spec.error_handling,
      configured: true,
      metadata: true,
    });
  }
  return stages;
}

// --- Resilience ---------------------------------------------------------------

export type ResilienceResponsibility = "source" | "target" | "runtime" | "undefined";

export const RESPONSIBILITY_LABELS: Record<ResilienceResponsibility, string> = {
  source: "Source-managed",
  target: "Target-managed",
  runtime: "Integration-runtime-managed",
  undefined: "Not defined",
};

export type ResilienceItem = {
  key: string;
  label: string;
  value: string;
  configured: boolean;
  responsibility: ResilienceResponsibility;
};

/**
 * Every resilience property is read from the modelled contract specification. The
 * owner of each behaviour is not part of the model, so responsibility is reported
 * as "Not defined" rather than invented.
 */
export function resilienceItems(contract: IntegrationContractSummary): ResilienceItem[] {
  const spec = contract.specification ?? {};
  const retry = spec.retry ?? { max_attempts: 0, backoff: "none" as const };
  const security = spec.security ?? { auth_type: "none" as const, notes: "" };
  return [
    {
      key: "retry",
      label: "Retry strategy",
      value: retry.max_attempts > 0 ? `${retry.max_attempts} attempts` : "Not configured",
      configured: retry.max_attempts > 0,
      responsibility: "undefined",
    },
    {
      key: "max_attempts",
      label: "Maximum attempts",
      value: String(retry.max_attempts),
      configured: retry.max_attempts > 0,
      responsibility: "undefined",
    },
    {
      key: "backoff",
      label: "Backoff",
      value: retry.backoff,
      configured: retry.backoff !== "none",
      responsibility: "undefined",
    },
    {
      key: "timeout",
      label: "Timeout",
      value: spec.timeout_ms ? `${spec.timeout_ms} ms` : "Not configured",
      configured: Boolean(spec.timeout_ms),
      responsibility: "undefined",
    },
    {
      key: "idempotency",
      label: "Idempotency",
      value: spec.idempotent ? "Idempotent" : "Not idempotent",
      configured: Boolean(spec.idempotent),
      responsibility: "undefined",
    },
    {
      key: "idempotency_key",
      label: "Idempotency key",
      value: contract.idempotency_key_field_name ?? "Not configured",
      configured: Boolean(spec.idempotency_key_field_id),
      responsibility: "undefined",
    },
    {
      key: "routing",
      label: "Routing",
      value: spec.routing || "Not configured",
      configured: Boolean(spec.routing),
      responsibility: "undefined",
    },
    {
      key: "orchestration_role",
      label: "Orchestration role",
      value: spec.orchestration_role ?? "none",
      configured: (spec.orchestration_role ?? "none") !== "none",
      responsibility: "undefined",
    },
    {
      key: "authentication",
      label: "Authentication",
      value: security.auth_type,
      configured: security.auth_type !== "none",
      responsibility: "undefined",
    },
    {
      key: "security_notes",
      label: "Security notes",
      value: security.notes || "None",
      configured: Boolean(security.notes),
      responsibility: "undefined",
    },
    {
      key: "error_handling",
      label: "Error handling",
      value: spec.error_handling || "Not configured",
      configured: Boolean(spec.error_handling),
      responsibility: "undefined",
    },
    {
      key: "implementation_status",
      label: "Implementation status",
      value: contract.implementation_status,
      configured: true,
      responsibility: "undefined",
    },
  ];
}

export const RESILIENCE_NOTE =
  "Behaviour ownership is not modelled, so every property reports Not defined.";

// --- Sequences ----------------------------------------------------------------

export function sequenceGroups(
  sequence: IntegrationSequence,
): { key: string; label: string; items: IntegrationScenarioSequence[] }[] {
  const order: { key: string; label: string }[] = [
    { key: "happy_path", label: "Happy path" },
    { key: "alternative", label: "Alternative" },
    { key: "error", label: "Error" },
  ];
  return order
    .map((group) => ({
      ...group,
      items: sequence.scenarios.filter((item) => item.category === group.key),
    }))
    .filter((group) => group.items.length > 0);
}

/** Interactions in participant order, so a diagram reads top-to-bottom. */
export function sequenceLifelines(
  scenario: IntegrationScenarioSequence,
): IntegrationSequenceParticipant[] {
  return scenario.participants;
}
