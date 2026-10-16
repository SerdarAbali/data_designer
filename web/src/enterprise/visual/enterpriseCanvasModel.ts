import type { ArchitectureState, ArchitectureStateNode } from "../../architectureTypes";
import type {
  ApplicationSupport,
  CapabilityMap,
  CapabilityMapEntry,
  EnterpriseApplication,
  EnterpriseImpact,
  EnterpriseLink,
  EnterpriseModel,
  EnterpriseObject,
  EnterpriseObjectType,
  ProcessImpact,
  StrategyTrace,
} from "../enterpriseModel";

export const ENTERPRISE_NODE_SIZES = {
  object: { width: 220, height: 64 },
  application: { width: 200, height: 56 },
} as const;

export const TRACE_COLUMNS: EnterpriseObjectType[] = [
  "goal",
  "requirement",
  "capability",
  "process",
];

export const TRACE_COLUMN_GAP = 320;
export const TRACE_ORIGIN = { x: 80, y: 80 };
export const TRACE_ROW_GAP = 60;

export type Point = { x: number; y: number };

export type EnterpriseTraceNode = {
  id: string;
  objectId: string;
  name: string;
  kind: EnterpriseObjectType | "application";
  column: number;
  position: Point;
  gap: string | null;
  owner: string | null;
  description: string | null;
  processType: string | null;
  applicationKind: string | null;
  occurrenceId: string;
};

export type EnterpriseTraceEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
};

export type EnterpriseTraceGraph = {
  nodes: EnterpriseTraceNode[];
  edges: EnterpriseTraceEdge[];
  gaps: string[];
  useSavedLayout: boolean;
};

export type CapabilityFlags = {
  lacksProcesses: boolean;
  lacksApplications: boolean;
  lacksOwner: boolean;
  lacksRequirements: boolean;
};

export type CapabilityNode = {
  objectId: string;
  name: string;
  owner: string | null;
  processNames: string[];
  applicationNames: string[];
  principleNames: string[];
  flags: CapabilityFlags;
  change: string | null;
};

export type CapabilityCluster = {
  id: string;
  label: string;
  capabilities: CapabilityNode[];
};

export type ProcessFlow = {
  process: EnterpriseObject;
  capabilities: EnterpriseObject[];
  applications: EnterpriseApplication[];
  requirements: EnterpriseObject[];
  governedBy: EnterpriseObject[];
  owner: EnterpriseObject | null;
  impacted: boolean;
  change: string | null;
};

export type AppSupportGraphNode = {
  id: string;
  name: string;
  kind: "application" | EnterpriseObjectType;
  applicationKind: string | null;
  description: string | null;
  position: Point;
};

export type AppSupportGraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
};

export type AppSupportGraph = {
  nodes: AppSupportGraphNode[];
  edges: AppSupportGraphEdge[];
};

export type AppSupportMatrix = {
  applications: EnterpriseApplication[];
  capabilities: EnterpriseObject[];
  processes: EnterpriseObject[];
  requirements: EnterpriseObject[];
  supported: Map<string, Set<string>>;
  satisfied: Map<string, Set<string>>;
};

function nodeForObject(state: ArchitectureState | null, objectId: string): ArchitectureStateNode | undefined {
  return (state?.nodes ?? []).find((node) => node.object_id === objectId);
}

export function enterpriseNodeByObject(state: ArchitectureState | null): Map<string, ArchitectureStateNode> {
  const map = new Map<string, ArchitectureStateNode>();
  for (const node of state?.nodes ?? []) map.set(node.object_id, node);
  return map;
}

export function hasManualLayout(state: ArchitectureState | null): boolean {
  return (state?.nodes ?? []).some(
    (node) => Boolean(node.display_metadata && node.display_metadata.enterprise_manual),
  );
}

function columnOfKind(kind: string): number {
  const index = TRACE_COLUMNS.indexOf(kind as EnterpriseObjectType);
  return index >= 0 ? index : 0;
}

function computedPosition(column: number, row: number): Point {
  return {
    x: TRACE_ORIGIN.x + column * TRACE_COLUMN_GAP,
    y: TRACE_ORIGIN.y + row * TRACE_ROW_GAP,
  };
}

function outgoingMap(model: EnterpriseModel): Map<string, EnterpriseLink[]> {
  const map = new Map<string, EnterpriseLink[]>();
  for (const link of model.links) {
    const list = map.get(link.source_object_id) ?? [];
    list.push(link);
    map.set(link.source_object_id, list);
  }
  return map;
}

function incomingMap(model: EnterpriseModel): Map<string, EnterpriseLink[]> {
  const map = new Map<string, EnterpriseLink[]>();
  for (const link of model.links) {
    const list = map.get(link.target_object_id) ?? [];
    list.push(link);
    map.set(link.target_object_id, list);
  }
  return map;
}

export function objectGap(
  kind: EnterpriseObjectType,
  objectId: string,
  outgoing: Map<string, EnterpriseLink[]>,
  incoming: Map<string, EnterpriseLink[]>,
): string | null {
  const has = (links: EnterpriseLink[] | undefined, type: string) =>
    Boolean(links?.some((link) => link.relationship_type === type));
  if (kind === "goal" && !has(outgoing.get(objectId), "drives")) return "no linked requirement";
  if (kind === "requirement") {
    if (!has(incoming.get(objectId), "drives")) return "not driven by a goal";
    if (!has(outgoing.get(objectId), "needs")) return "no linked capability";
  }
  if (kind === "capability" && !has(outgoing.get(objectId), "has_process")) return "no linked process";
  if (kind === "process" && !has(incoming.get(objectId), "supports")) return "no supporting system";
  return null;
}

/**
 * Builds the layered Goal -> Requirement -> Capability -> Process -> Application
 * trace from the stored links and the strategy-trace projection. Gap markers are
 * computed from the relationships themselves; no relationship is fabricated.
 */
export function strategyTraceGraph(
  model: EnterpriseModel,
  strategyTrace: StrategyTrace,
  state: ArchitectureState | null,
  options: { forceAuto?: boolean } = {},
): EnterpriseTraceGraph {
  const nodes: EnterpriseTraceNode[] = [];
  const seen = new Set<string>();
  const outgoing = outgoingMap(model);
  const incoming = incomingMap(model);

  const addObject = (
    object: EnterpriseObject,
    column: number,
    gap: string | null,
  ): EnterpriseTraceNode => {
    const existing = nodes.find((node) => node.id === object.object_id);
    if (existing) return existing;
    const node = nodeForObject(state, object.object_id);
    const placeholder: EnterpriseTraceNode = {
      id: object.object_id,
      objectId: object.object_id,
      name: object.name,
      kind: object.kind,
      column,
      position: computedPosition(column, 0),
      gap,
      owner: object.owner ?? null,
      description: object.description ?? null,
      processType: object.process_type ?? null,
      applicationKind: null,
      occurrenceId: node?.occurrence_id ?? "",
    };
    nodes.push(placeholder);
    seen.add(object.object_id);
    return placeholder;
  };

  const addApplication = (application: EnterpriseApplication, column: number): EnterpriseTraceNode => {
    const existing = nodes.find((node) => node.id === application.object_id);
    if (existing) return existing;
    const placeholder: EnterpriseTraceNode = {
      id: application.object_id,
      objectId: application.object_id,
      name: application.name,
      kind: "application",
      column,
      position: computedPosition(column, 0),
      gap: null,
      owner: null,
      description: null,
      processType: null,
      applicationKind: application.kind,
      occurrenceId: nodeForObject(state, application.object_id)?.occurrence_id ?? "",
    };
    nodes.push(placeholder);
    seen.add(application.object_id);
    return placeholder;
  };

  for (const chain of strategyTrace.chains) {
    const goalGap = objectGap("goal", chain.goal.object_id, outgoing, incoming);
    addObject(chain.goal, columnOfKind("goal"), goalGap);
    for (const step of chain.steps) {
      addObject(step.requirement, columnOfKind("requirement"), objectGap("requirement", step.requirement.object_id, outgoing, incoming));
      for (const capability of step.capabilities) {
        addObject(capability, columnOfKind("capability"), objectGap("capability", capability.object_id, outgoing, incoming));
      }
      for (const process of step.processes) {
        addObject(process, columnOfKind("process"), objectGap("process", process.object_id, outgoing, incoming));
      }
      for (const application of step.applications) {
        addApplication(application, TRACE_COLUMNS.length);
      }
    }
  }
  for (const requirement of strategyTrace.unlinked_requirements) {
    addObject(requirement, columnOfKind("requirement"), "not driven by a goal");
  }

  const idSet = new Set(nodes.map((node) => node.id));
  const edges: EnterpriseTraceEdge[] = [];
  for (const link of model.links) {
    if (!idSet.has(link.source_object_id) || !idSet.has(link.target_object_id)) continue;
    const label = ENTERPRISE_LINK_LABELS[link.relationship_type] ?? link.relationship_type;
    edges.push({
      id: link.id,
      source: link.source_object_id,
      target: link.target_object_id,
      type: link.relationship_type,
      label,
    });
  }

  // Resolve positions: honour a saved layout only when it was authored manually
  // or is already consistent with the trace columns.
  const computed = new Map<string, Point>();
  const rows = new Map<number, number>();
  for (const node of nodes) {
    const row = rows.get(node.column) ?? 0;
    computed.set(node.id, computedPosition(node.column, row));
    rows.set(node.column, row + 1);
  }
  const useSavedLayout = options.forceAuto ? false : resolveSavedLayout(nodes, state, computed);
  if (useSavedLayout) {
    for (const node of nodes) {
      if (node.kind === "application") {
        node.position = computed.get(node.id)!;
        continue;
      }
      const saved = nodeForObject(state, node.objectId)?.position;
      node.position = saved ? { x: saved.x, y: saved.y } : computed.get(node.id)!;
    }
  } else {
    for (const node of nodes) node.position = computed.get(node.id)!;
  }

  return {
    nodes,
    edges,
    gaps: strategyTrace.gaps,
    useSavedLayout,
  };
}

function resolveSavedLayout(
  nodes: EnterpriseTraceNode[],
  state: ArchitectureState | null,
  computed: Map<string, Point>,
): boolean {
  if (hasManualLayout(state)) return true;
  const objects = nodes.filter((node) => node.kind !== "application");
  if (objects.length === 0) return false;
  const allHave = objects.every((node) => Boolean(nodeForObject(state, node.objectId)));
  if (!allHave) return false;
  return objects.every((node) => {
    const saved = nodeForObject(state, node.objectId)!.position;
    const target = computed.get(node.id)!;
    return Math.abs(saved.x - target.x) <= TRACE_COLUMN_GAP * 0.6;
  });
}

const ENTERPRISE_LINK_LABELS: Record<string, string> = {
  drives: "drives",
  needs: "needs",
  has_process: "has process",
  supports: "supports",
  satisfies: "satisfies",
  governed_by: "governed by",
  owned_by: "owned by",
  depends_on: "depends on",
  impacts: "impacts",
  affects: "affects",
};

export function capabilityCoverage(model: EnterpriseModel, entry: CapabilityMapEntry): CapabilityFlags {
  const hasIncomingNeeds = model.links.some(
    (link) => link.relationship_type === "needs" && link.target_object_id === entry.capability.object_id,
  );
  return {
    lacksProcesses: entry.processes.length === 0,
    lacksApplications: entry.applications.length === 0,
    lacksOwner: entry.owner_role == null,
    lacksRequirements: !hasIncomingNeeds,
  };
}

export function capabilityClusters(
  model: EnterpriseModel,
  capabilityMap: CapabilityMap,
  impact: EnterpriseImpact | null,
): CapabilityCluster[] {
  const changeById = new Map((impact?.changes ?? []).map((change) => [change.object_id, change.change]));
  const clusters = new Map<string, CapabilityCluster>();
  const ensure = (id: string, label: string): CapabilityCluster => {
    const existing = clusters.get(id);
    if (existing) return existing;
    const cluster = { id, label, capabilities: [] as CapabilityNode[] };
    clusters.set(id, cluster);
    return cluster;
  };

  for (const entry of capabilityMap.capabilities) {
    const cluster = ensure(
      entry.owner_role?.object_id ?? "unowned",
      entry.owner_role?.name ?? "Unowned",
    );
    cluster.capabilities.push({
      objectId: entry.capability.object_id,
      name: entry.capability.name,
      owner: entry.owner_role?.name ?? null,
      processNames: entry.processes.map((item) => item.name),
      applicationNames: entry.applications.map((item) => item.name),
      principleNames: entry.principles.map((item) => item.name),
      flags: capabilityCoverage(model, entry),
      change: changeById.get(entry.capability.object_id) ?? null,
    });
  }

  return [...clusters.values()].sort((a, b) => a.label.localeCompare(b.label));
}

export function processFlows(
  model: EnterpriseModel,
  processImpact: ProcessImpact,
  impact: EnterpriseImpact | null,
): ProcessFlow[] {
  const changeById = new Map((impact?.changes ?? []).map((change) => [change.object_id, change.change]));
  const ownerByProcess = new Map<string, EnterpriseObject>();
  for (const link of model.links) {
    if (link.relationship_type !== "owned_by") continue;
    const role = model.roles.find((item) => item.object_id === link.target_object_id);
    if (role) ownerByProcess.set(link.source_object_id, role);
  }
  return processImpact.processes.map((entry) => ({
    process: entry.process,
    capabilities: entry.capabilities,
    applications: entry.applications,
    requirements: entry.requirements,
    governedBy: entry.governed_by,
    owner: ownerByProcess.get(entry.process.object_id) ?? null,
    impacted: entry.impacted,
    change: changeById.get(entry.process.object_id) ?? null,
  }));
}

export function applicationSupportGraph(model: EnterpriseModel): AppSupportGraph {
  const nodes: AppSupportGraphNode[] = [];
  const byId = new Map<string, AppSupportGraphNode>();
  const appById = new Map(model.applications.map((app) => [app.object_id, app]));
  const objectById = new Map<string, EnterpriseObject>();
  for (const object of [
    ...model.goals,
    ...model.requirements,
    ...model.capabilities,
    ...model.processes,
    ...model.principles,
    ...model.roles,
  ]) {
    objectById.set(object.object_id, object);
  }

  const addNode = (id: string): void => {
    if (byId.has(id)) return;
    const app = appById.get(id);
    const object = objectById.get(id);
    if (app) {
      byId.set(id, {
        id,
        name: app.name,
        kind: "application",
        applicationKind: app.kind,
        description: app.description ?? null,
        position: { x: 0, y: 0 },
      });
    } else if (object) {
      byId.set(id, {
        id,
        name: object.name,
        kind: object.kind,
        applicationKind: null,
        description: object.description ?? null,
        position: { x: 0, y: 0 },
      });
    }
  };

  const edges: AppSupportGraphEdge[] = [];
  for (const link of model.links) {
    if (link.relationship_type !== "supports" && link.relationship_type !== "satisfies") continue;
    addNode(link.source_object_id);
    addNode(link.target_object_id);
    edges.push({
      id: link.id,
      source: link.source_object_id,
      target: link.target_object_id,
      type: link.relationship_type,
      label: link.relationship_type,
    });
  }

  // Left/right layered layout: applications on the left, enterprise objects right.
  const apps = [...byId.values()].filter((node) => node.kind === "application");
  const objects = [...byId.values()].filter((node) => node.kind !== "application");
  apps.forEach((node, index) => {
    node.position = { x: 80, y: 80 + index * 90 };
  });
  objects.forEach((node, index) => {
    node.position = { x: 440, y: 80 + index * 80 };
  });

  return { nodes: [...apps, ...objects], edges };
}

export function applicationSupportMatrix(
  applicationSupport: ApplicationSupport,
): AppSupportMatrix {
  const supported = new Map<string, Set<string>>();
  const satisfied = new Map<string, Set<string>>();
  for (const entry of applicationSupport.applications) {
    for (const capability of entry.capabilities) add(supported, entry.application.object_id, capability.object_id);
    for (const process of entry.processes) add(supported, entry.application.object_id, process.object_id);
    for (const requirement of entry.requirements) add(satisfied, entry.application.object_id, requirement.object_id);
  }
  const capabilities = dedupeObjects(applicationSupport.applications.flatMap((entry) => entry.capabilities));
  const processes = dedupeObjects(applicationSupport.applications.flatMap((entry) => entry.processes));
  const requirements = dedupeObjects(applicationSupport.applications.flatMap((entry) => entry.requirements));
  return {
    applications: applicationSupport.applications.map((entry) => entry.application),
    capabilities,
    processes,
    requirements,
    supported,
    satisfied,
  };
}

function add(map: Map<string, Set<string>>, key: string, value: string): void {
  const set = map.get(key) ?? new Set<string>();
  set.add(value);
  map.set(key, set);
}

function dedupeObjects(items: EnterpriseObject[]): EnterpriseObject[] {
  const seen = new Map<string, EnterpriseObject>();
  for (const item of items) seen.set(item.object_id, item);
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
}
