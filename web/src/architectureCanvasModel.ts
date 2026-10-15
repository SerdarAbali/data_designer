import type {
  ArchitectureObject,
  ArchitectureState,
  ArchitectureDiscipline,
  ArchitectureStateNode,
  ArchitectureStateRelationship,
} from "./architectureTypes";

export type CanonicalSystem = {
  id: string;
  name: string;
  description?: string | null;
  kind: string;
  icon: string | null;
  color: string | null;
};

export type ResolvedOccurrence = {
  occurrenceId: string;
  objectId: string;
  position: { x: number; y: number };
  name: string;
  description: string;
  kind: string;
  icon: string;
  color: string;
  missing: boolean;
  overridden: boolean;
};

const OBJECT_COLORS: Record<ArchitectureObject["kind"], string> = {
  business_requirement: "var(--discipline-enterprise)",
  business_capability: "var(--discipline-enterprise)",
  information_object: "var(--discipline-information)",
  solution_boundary: "var(--discipline-solution)",
  component: "var(--discipline-solution)",
  interface: "var(--semantic-interface)",
};

const OBJECT_LABELS: Record<ArchitectureObject["kind"], string> = {
  business_requirement: "Business Requirement",
  business_capability: "Business Capability",
  information_object: "Information Object",
  solution_boundary: "Solution Boundary",
  component: "Component",
  interface: "Interface",
};
export const ARCHITECTURE_OBJECT_ICONS: Record<ArchitectureObject["kind"], string> = {
  business_requirement: "≡",
  business_capability: "◇",
  information_object: "▤",
  solution_boundary: "▧",
  component: "▣",
  interface: "⇄",
};

export type ResolvedRelationship = {
  id: string;
  sourceOccurrenceId: string;
  targetOccurrenceId: string;
  type: string;
  name: string | null;
  integrationId: string | null;
};

export function isEditableState(state: ArchitectureState | null): boolean {
  return state != null && state.state_type !== "current";
}

export function projectStateNodes(
  state: ArchitectureState | null,
  discipline: ArchitectureDiscipline,
  objects: Map<string, ArchitectureObject>,
): ArchitectureStateNode[] {
  return (state?.nodes ?? []).filter((node) => {
    const object = objects.get(node.object_id);
    if (object?.kind === "interface") return discipline === "solution" || discipline === "integration";
    return !node.discipline || node.discipline === discipline;
  });
}

function overrideString(node: ArchitectureStateNode, key: string): string | undefined {
  const value = node.candidate_overrides?.[key];
  return typeof value === "string" && value.trim() ? value : undefined;
}

/**
 * Resolves an occurrence against its canonical object. Canonical properties come
 * from the shared system; candidate overrides only apply in non-current states.
 */
export function resolveOccurrence(
  node: ArchitectureStateNode,
  systemsById: Map<string, CanonicalSystem>,
  applyOverrides: boolean,
  architectureObjectsById: Map<string, ArchitectureObject> = new Map(),
): ResolvedOccurrence {
  const system = systemsById.get(node.object_id);
  const architectureObject = architectureObjectsById.get(node.object_id);
  const name = applyOverrides ? overrideString(node, "name") : undefined;
  const description = applyOverrides ? overrideString(node, "description") : undefined;
  return {
    occurrenceId: node.occurrence_id,
    objectId: node.object_id,
    position: node.position,
    name: name ?? architectureObject?.name ?? system?.name ?? "Unknown object",
    description: description ?? architectureObject?.description ?? system?.description ?? "",
    kind: architectureObject ? OBJECT_LABELS[architectureObject.kind] : system?.kind ?? "System",
    icon: architectureObject
      ? ARCHITECTURE_OBJECT_ICONS[architectureObject.kind]
      : system?.icon ?? "",
    color: architectureObject
      ? OBJECT_COLORS[architectureObject.kind]
      : system?.color || "#527ca4",
    missing: !system && !architectureObject,
    overridden: Boolean(name || description),
  };
}

/**
 * Relationship endpoints may reference an occurrence_id (canvas placement) or an
 * object_id (canonical object). Occurrence matches win; object references resolve
 * to the first occurrence of that object in the state.
 */
export function resolveEndpoint(
  nodes: ArchitectureStateNode[],
  endpointId: string,
): string | null {
  if (nodes.some((node) => node.occurrence_id === endpointId)) return endpointId;
  return nodes.find((node) => node.object_id === endpointId)?.occurrence_id ?? null;
}

export function resolveRelationships(
  state: ArchitectureState,
  visibleNodes: ArchitectureStateNode[] = state.nodes,
): ResolvedRelationship[] {
  const resolved: ResolvedRelationship[] = [];
  for (const rel of state.relationships) {
    const source = resolveEndpoint(visibleNodes, rel.source_id);
    const target = resolveEndpoint(visibleNodes, rel.target_id);
    if (!source || !target) continue;
    resolved.push({
      id: rel.id,
      sourceOccurrenceId: source,
      targetOccurrenceId: target,
      type: rel.type,
      name: rel.name ?? null,
      integrationId: rel.integration_id ?? null,
    });
  }
  return resolved;
}

export function moveOccurrence(
  state: ArchitectureState,
  occurrenceId: string,
  position: { x: number; y: number },
): ArchitectureState {
  return {
    ...state,
    nodes: state.nodes.map((node) =>
      node.occurrence_id === occurrenceId ? { ...node, position: { x: position.x, y: position.y } } : node),
  };
}

export function addOccurrence(
  state: ArchitectureState,
  objectId: string,
  position: { x: number; y: number },
  occurrenceId: string,
  discipline?: ArchitectureDiscipline,
): ArchitectureState {
  const node: ArchitectureStateNode = {
    occurrence_id: occurrenceId,
    object_id: objectId,
    position,
    discipline: discipline ?? null,
    parent_occurrence_id: null,
    display_metadata: {},
    candidate_overrides: {},
  };
  return { ...state, nodes: [...state.nodes, node] };
}

/** Removes an occurrence and any relationships attached to it (by occurrence or object reference). */
export function removeOccurrence(state: ArchitectureState, occurrenceId: string): ArchitectureState {
  const nodes = state.nodes.filter((node) => node.occurrence_id !== occurrenceId);
  const relationships = state.relationships.filter((rel) =>
    resolveEndpoint(nodes, rel.source_id) != null && resolveEndpoint(nodes, rel.target_id) != null);
  return { ...state, nodes, relationships };
}

export function addRelationship(
  state: ArchitectureState,
  relationship: ArchitectureStateRelationship,
): ArchitectureState {
  return { ...state, relationships: [...state.relationships, relationship] };
}

export function updateRelationship(
  state: ArchitectureState,
  relationshipId: string,
  patch: Partial<ArchitectureStateRelationship>,
): ArchitectureState {
  return {
    ...state,
    relationships: state.relationships.map((rel) => rel.id === relationshipId ? { ...rel, ...patch } : rel),
  };
}

export function removeRelationship(state: ArchitectureState, relationshipId: string): ArchitectureState {
  return { ...state, relationships: state.relationships.filter((rel) => rel.id !== relationshipId) };
}

export function nextFreePosition(state: ArchitectureState): { x: number; y: number } {
  if (state.nodes.length === 0) return { x: 80, y: 80 };
  const maxY = Math.max(...state.nodes.map((node) => node.position.y));
  const lowest = state.nodes.filter((node) => node.position.y === maxY);
  const maxX = Math.max(...lowest.map((node) => node.position.x));
  return maxX > 900 ? { x: 80, y: maxY + 200 } : { x: maxX + 360, y: maxY };
}

export type BoundaryGeometry = {
  position: { x: number; y: number };
  width: number;
  height: number;
  memberIds: string[];
};

export function solutionBoundaryGeometry(
  state: ArchitectureState,
  objects: Map<string, ArchitectureObject>,
): Map<string, BoundaryGeometry> {
  const nodesById = new Map(state.nodes.map((node) => [node.occurrence_id, node]));
  const boundaries = state.nodes.filter((node) => objects.get(node.object_id)?.kind === "solution_boundary");
  const boundaryIds = new Set(boundaries.map((node) => node.occurrence_id));
  const children = new Map(boundaries.map((node) => [node.occurrence_id, new Set<string>()]));
  for (const node of state.nodes) {
    if (node.parent_occurrence_id && node.parent_occurrence_id !== node.occurrence_id) {
      children.get(node.parent_occurrence_id)?.add(node.occurrence_id);
    }
  }
  for (const relationship of resolveRelationships(state)) {
    const member = nodesById.get(relationship.targetOccurrenceId);
    if (relationship.type.toLowerCase() === "contains"
      && boundaryIds.has(relationship.sourceOccurrenceId)
      && relationship.sourceOccurrenceId !== relationship.targetOccurrenceId
      && !member?.parent_occurrence_id) {
      children.get(relationship.sourceOccurrenceId)?.add(relationship.targetOccurrenceId);
    }
  }
  const result = new Map<string, BoundaryGeometry>();
  function envelope(id: string, ancestors: Set<string>): BoundaryGeometry | null {
    if (ancestors.has(id)) return null;
    const existing = result.get(id);
    if (existing) return existing;
    const boundary = nodesById.get(id);
    if (!boundary) return null;
    const path = new Set([...ancestors, id]);
    const memberIds: string[] = [];
    const bounds: { x: number; y: number; width: number; height: number }[] = [];
    for (const childId of children.get(id) ?? []) {
      if (path.has(childId)) continue;
      const child = nodesById.get(childId);
      if (!child) continue;
      const nested = boundaryIds.has(childId) ? envelope(childId, path) : null;
      memberIds.push(childId, ...(nested?.memberIds ?? []));
      bounds.push({
        ...(nested?.position ?? child.position),
        width: nested?.width ?? 220,
        height: nested?.height ?? 90,
      });
    }
    const position = bounds.length ? {
      x: Math.min(...bounds.map((box) => box.x)) - 32,
      y: Math.min(...bounds.map((box) => box.y)) - 52,
    } : boundary.position;
    const width = bounds.length
      ? Math.max(420, boundary.width ?? 0, Math.max(...bounds.map((box) => box.x + box.width)) + 32 - position.x)
      : Math.max(420, boundary.width ?? 0);
    const height = bounds.length
      ? Math.max(240, boundary.height ?? 0, Math.max(...bounds.map((box) => box.y + box.height)) + 32 - position.y)
      : Math.max(240, boundary.height ?? 0);
    const geometry = { position, width, height, memberIds: [...new Set(memberIds)] };
    result.set(id, geometry);
    return geometry;
  }
  for (const boundary of boundaries) envelope(boundary.occurrence_id, new Set());
  return result;
}
