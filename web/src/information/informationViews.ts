import type {
  InformationChangeType,
  InformationConceptual,
  InformationImpactChange,
  InformationLineage,
} from "./informationModel";

/** Purpose-specific Information Architecture views. */
export type InformationViewId =
  | "conceptual"
  | "logical"
  | "physical"
  | "ownership"
  | "lineage"
  | "impact";

export const INFORMATION_VIEWS: {
  id: InformationViewId;
  label: string;
  description: string;
}[] = [
  {
    id: "conceptual",
    label: "Conceptual Model",
    description: "Business concepts and their high-level relationships.",
  },
  {
    id: "logical",
    label: "Logical Model",
    description: "Entities, inline attributes, keys and cardinality.",
  },
  {
    id: "physical",
    label: "Physical Realization",
    description: "Logical attributes mapped to existing catalog fields.",
  },
  {
    id: "ownership",
    label: "Ownership & Authority",
    description: "Owner, steward and authoritative system by entity.",
  },
  {
    id: "lineage",
    label: "Information Lineage",
    description: "Source-to-target field lineage through contracts.",
  },
  {
    id: "impact",
    label: "Current vs Candidate Impact",
    description: "What changes between Current and this state.",
  },
];

export type InformationLayoutPoint = { x: number; y: number };

/**
 * Layered layout shared by the projection graphs. Nodes are placed by their
 * longest path from a root so directed flows read left-to-right, stacked within
 * each layer. Deterministic for a given input.
 */
export function layeredLayout(
  ids: string[],
  edges: { source: string; target: string }[],
  direction: "ltr" | "ttb" = "ltr",
  columnGap = 320,
  rowGap = 160,
): Map<string, InformationLayoutPoint> {
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
  const positions = new Map<string, InformationLayoutPoint>();
  const ordered = [...ids].sort((a, b) => {
    const byLevel = (level.get(a) ?? 0) - (level.get(b) ?? 0);
    return byLevel !== 0 ? byLevel : a.localeCompare(b);
  });
  for (const id of ordered) {
    const lane = level.get(id) ?? 0;
    const row = rows.get(lane) ?? 0;
    rows.set(lane, row + 1);
    positions.set(
      id,
      direction === "ltr"
        ? { x: 60 + lane * columnGap, y: 60 + row * rowGap }
        : { x: 60 + row * rowGap, y: 60 + lane * columnGap },
    );
  }
  return positions;
}

export function conceptualLayout(conceptual: InformationConceptual): {
  positions: Map<string, InformationLayoutPoint>;
  edges: { id: string; source: string; target: string; label: string }[];
} {
  const positions = layeredLayout(
    conceptual.concepts.map((concept) => concept.object_id),
    conceptual.relationships.map((relationship) => ({
      source: relationship.source_object_id,
      target: relationship.target_object_id,
    })),
  );
  const edges = conceptual.relationships.map((relationship) => ({
    id: relationship.id,
    source: relationship.source_object_id,
    target: relationship.target_object_id,
    label: relationship.name ?? relationship.cardinality.replace(/_/g, " "),
  }));
  return { positions, edges };
}

export function lineageLayout(lineage: InformationLineage): Map<string, InformationLayoutPoint> {
  return layeredLayout(
    lineage.nodes.map((node) => node.id),
    lineage.edges.map((edge) => ({ source: edge.source, target: edge.target })),
    "ltr",
    LINEAGE_COLUMN_GAP,
    LINEAGE_ROW_GAP,
  );
}

/**
 * Column and row spacing for the lineage. Connectors bend inside the corridor
 * between two columns, so the corridor has to be wide enough to hold one lane
 * per connector plus the relationship labels that sit on them.
 */
export const LINEAGE_COLUMN_GAP = 440;
export const LINEAGE_ROW_GAP = 160;

/** Horizontal spacing between two connectors that share a corridor. */
export const PROJECTION_LANE_SPACING = 9;

/** Furthest a connector may be pushed from its own column edge. */
const PROJECTION_LANE_LIMIT = 78;

/**
 * Assigns every connector a lane inside its corridor. Without this, each
 * connector bends at the same distance from its source node, so all the jogs in
 * a corridor land on one line and the graph becomes unreadable. Lanes are
 * deterministic: ordered by source row, then target row, then id.
 */
export function assignProjectionLanes(
  positions: Map<string, InformationLayoutPoint>,
  edges: { id: string; source: string; target: string }[],
): Map<string, number> {
  const corridors = new Map<number, { id: string; source: string; target: string }[]>();
  for (const edge of edges) {
    const source = positions.get(edge.source);
    if (!source) continue;
    const list = corridors.get(source.x) ?? [];
    list.push(edge);
    corridors.set(source.x, list);
  }
  const lanes = new Map<string, number>();
  for (const list of corridors.values()) {
    const ordered = [...list].sort((a, b) => {
      const aSource = positions.get(a.source);
      const bSource = positions.get(b.source);
      const bySource = (aSource?.y ?? 0) - (bSource?.y ?? 0);
      if (bySource !== 0) return bySource;
      const byTarget = (positions.get(a.target)?.y ?? 0) - (positions.get(b.target)?.y ?? 0);
      return byTarget !== 0 ? byTarget : a.id.localeCompare(b.id);
    });
    ordered.forEach((edge, index) => {
      const offset = (index - (ordered.length - 1) / 2) * PROJECTION_LANE_SPACING;
      lanes.set(
        edge.id,
        Math.max(-PROJECTION_LANE_LIMIT, Math.min(PROJECTION_LANE_LIMIT, offset)),
      );
    });
  }
  return lanes;
}

function push(map: Map<string, string[]>, key: string, value: string): void {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

/** Walk proven lineage edges from a node, in one or both directions. */
export function lineageNeighborhood(
  lineage: InformationLineage,
  rootId: string,
  direction: "upstream" | "downstream" | "both" = "both",
): Set<string> {
  const forward = new Map<string, string[]>();
  const backward = new Map<string, string[]>();
  for (const edge of lineage.edges) {
    push(forward, edge.source, edge.target);
    push(backward, edge.target, edge.source);
  }
  const visited = new Set<string>([rootId]);
  const queue = [rootId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    const next =
      direction === "upstream"
        ? backward.get(current) ?? []
        : direction === "downstream"
          ? forward.get(current) ?? []
          : [...(forward.get(current) ?? []), ...(backward.get(current) ?? [])];
    for (const neighbor of next) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
  }
  return visited;
}

/**
 * Filter lineage to the connected neighbourhood of every node matching a term,
 * so visible chains stay intact. An empty term returns the full graph.
 */
export function filterLineage(
  lineage: InformationLineage,
  term: string,
): InformationLineage {
  const query = term.trim().toLowerCase();
  if (!query) return lineage;
  const keep = new Set<string>();
  for (const node of lineage.nodes) {
    const haystack = [node.name, node.detail, node.system_name]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (haystack.includes(query)) {
      for (const id of lineageNeighborhood(lineage, node.id, "both")) keep.add(id);
    }
  }
  return {
    ...lineage,
    nodes: lineage.nodes.filter((node) => keep.has(node.id)),
    edges: lineage.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target)),
  };
}

export const LINEAGE_KIND_LABELS: Record<string, string> = {
  information_entity: "Entity",
  information_attribute: "Attribute",
  catalog_system: "System",
  catalog_object: "Catalog object",
  catalog_field: "Catalog field",
  contract: "Contract",
};

export const OWNERSHIP_ISSUE_LABELS: Record<string, string> = {
  missing_owner: "Missing owner",
  missing_steward: "Missing steward",
  missing_authoritative_system: "Missing authoritative system",
  authoritative_not_in_state: "Authoritative system not in state",
  multiple_authoritative_sources: "Multiple authoritative sources",
  sensitive_without_ownership: "Sensitive without owner/steward",
};

export const CHANGE_LABELS: Record<InformationChangeType, string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  reused: "Reused",
};

export const CHANGE_ORDER: InformationChangeType[] = ["added", "removed", "changed", "reused"];

export const OBJECT_TYPE_LABELS: Record<string, string> = {
  entity: "Entity",
  attribute: "Attribute",
  relationship: "Relationship",
  realization: "Realization",
};

export function filterImpactChanges(
  changes: InformationImpactChange[],
  filters: { change?: InformationChangeType | "all"; objectType?: string | "all" },
): InformationImpactChange[] {
  return changes.filter((change) => {
    if (filters.change && filters.change !== "all" && change.change !== filters.change) return false;
    if (filters.objectType && filters.objectType !== "all" && change.object_type !== filters.objectType) {
      return false;
    }
    return true;
  });
}

export function impactObjectTypes(changes: InformationImpactChange[]): string[] {
  return [...new Set(changes.map((change) => change.object_type))].sort();
}
