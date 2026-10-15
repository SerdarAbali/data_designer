import { api } from "../information/api";

export type TraceStateMembership = "current" | "candidate" | "target" | "none";
export type TraceDirection = "both" | "outgoing" | "incoming";

export type TraceObjectRef = {
  id: string;
  kind: string;
  name: string;
  description: string | null;
  discipline: string | null;
  state_membership: TraceStateMembership;
  external: boolean;
};

export type TraceEdge = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  relationship_type: string;
  derived: boolean;
};

export type TraceNeighbor = {
  relationship_type: string;
  direction: "outgoing" | "incoming";
  derived: boolean;
  object: TraceObjectRef;
};

export type TraceUsageGroup = {
  label: string;
  objects: TraceObjectRef[];
};

export type ObjectTrace = {
  state_id: string;
  object: TraceObjectRef;
  disciplines: string[];
  outgoing: TraceNeighbor[];
  incoming: TraceNeighbor[];
  groups: TraceUsageGroup[];
  physical_refs: TraceObjectRef[];
  tests: TraceObjectRef[];
  principles: TraceObjectRef[];
};

export type ArchitectureGraph = {
  state_id: string;
  nodes: TraceObjectRef[];
  edges: TraceEdge[];
};

export type TraceResult = {
  state_id: string;
  direction: TraceDirection;
  max_depth: number;
  root: TraceObjectRef;
  nodes: TraceObjectRef[];
  edges: TraceEdge[];
  depths: Record<string, number>;
};

export const TRACE_KIND_LABELS: Record<string, string> = {
  system: "System",
  business_goal: "Goal",
  business_requirement: "Requirement",
  business_capability: "Capability",
  business_process: "Process",
  architecture_principle: "Principle",
  organization_role: "Role",
  information_object: "Entity",
  information_attribute: "Attribute",
  catalog_object_ref: "Catalog object",
  catalog_field_ref: "Catalog field",
  solution_boundary: "Solution",
  component: "Component",
  interface: "Interface",
  interface_operation: "Operation",
  data_repository: "Repository",
  deployment_node: "Deployment node",
  trust_boundary: "Trust boundary",
  contract_ref: "Contract",
  scenario_ref: "Scenario",
};

export const TRACE_RELATIONSHIP_LABELS: Record<string, string> = {
  has_attribute: "has attribute",
  has_operation: "has operation",
  contains_component: "contains component",
  provides: "provides",
  requires: "requires",
  has_member: "has member",
  has_repository: "has repository",
  has_deployment: "has deployment",
  has_trust_boundary: "has trust boundary",
  realizes: "realizes",
  mapped_by: "mapped by",
  verified_by: "verified by",
  produces: "produces",
  consumes: "consumes",
  references: "references",
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

export function traceKindLabel(kind: string): string {
  return TRACE_KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}

export function traceRelationshipLabel(relationshipType: string): string {
  return TRACE_RELATIONSHIP_LABELS[relationshipType] ?? relationshipType.replace(/_/g, " ");
}

export function traceMembershipLabel(membership: TraceStateMembership): string {
  switch (membership) {
    case "current":
      return "Current";
    case "candidate":
      return "Candidate";
    case "target":
      return "Target";
    default:
      return "Not on canvas";
  }
}

function traceBase(workspaceId: string): string {
  return `/api/workspaces/${workspaceId}`;
}

export function fetchObjectUsages(
  workspaceId: string,
  stateId: string,
  objectId: string,
): Promise<ObjectTrace> {
  return api<ObjectTrace>(
    `${traceBase(workspaceId)}/objects/${objectId}/usages?state_id=${encodeURIComponent(stateId)}`,
  );
}

export function fetchArchitectureGraph(
  workspaceId: string,
  stateId: string,
): Promise<ArchitectureGraph> {
  return api<ArchitectureGraph>(
    `${traceBase(workspaceId)}/architecture-graph?state_id=${encodeURIComponent(stateId)}`,
  );
}

export function fetchTrace(
  workspaceId: string,
  stateId: string,
  objectId: string,
  direction: TraceDirection,
  depth: number,
): Promise<TraceResult> {
  const params = new URLSearchParams({
    state_id: stateId,
    object_id: objectId,
    direction,
    depth: String(depth),
  });
  return api<TraceResult>(`${traceBase(workspaceId)}/trace?${params.toString()}`);
}
