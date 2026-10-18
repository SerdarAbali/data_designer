import type { ArchitectureState, ArchitectureStateNode } from "../architectureTypes";
import {
  chooseHandles,
  handleId,
  type FlowSide,
  type Rect,
} from "../components/architecture/architectureRouting";
import type {
  SolutionComponent,
  SolutionDesign,
  SolutionDeploymentNode,
  SolutionInterface,
  SolutionLink,
  SolutionRepository,
  SolutionTrustBoundary,
} from "./solutionModel";

export const SOLUTION_NODE_SIZES = {
  boundary: { width: 520, height: 320 },
  component: { width: 260, height: 96 },
  system: { width: 200, height: 72 },
  repository: { width: 210, height: 78 },
} as const;

const LAYOUT = {
  originX: 80,
  originY: 80,
  systemGapX: 60,
  systemGapY: 48,
  componentGapX: 140,
  componentGapY: 60,
  repositoryGapY: 56,
  externalGapY: 80,
  laneSpacing: 26,
  boundaryPad: { left: 44, right: 44, top: 56, bottom: 44 },
} as const;

export type Point = { x: number; y: number };

export type LayoutOptions = { auto?: boolean };

export type PlacedSystem = {
  key: string;
  systemId: string;
  occurrenceId: string;
  name: string;
  kind: string;
  external: boolean;
  position: Point;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  /** Routing sides of the handles, when the handle id does not encode them. */
  sourceSide?: FlowSide;
  targetSide?: FlowSide;
  sourceOffset?: Point;
  targetOffset?: Point;
  kind: "member" | "external" | "connects_to" | "uses" | "relationship";
  label: string;
};

export type BoundaryFrame = {
  id: string;
  occurrenceId: string;
  position: Point;
  width: number;
  height: number;
  label: string;
};

export type ContextGraph = {
  boundary: BoundaryFrame;
  systems: PlacedSystem[];
  edges: GraphEdge[];
};

export type DecompositionComponent = {
  key: string;
  component: SolutionComponent;
  occurrenceId: string;
  position: Point;
  height: number;
  provided: SolutionInterface[];
  required: SolutionInterface[];
};

export type DecompositionRepository = {
  key: string;
  repository: SolutionRepository;
  position: Point;
  usedBy: string[];
};

export type DecompositionGraph = {
  boundary: BoundaryFrame;
  components: DecompositionComponent[];
  repositories: DecompositionRepository[];
  externals: PlacedSystem[];
  edges: GraphEdge[];
  /**
   * Which side of its component each interface port sits on. Ports face the
   * component they connect to, so a ``connects_to`` link (always
   * required → provided) runs straight across instead of looping around the
   * whole diagram.
   */
  portSides: Record<string, FlowSide>;
};

export type DeploymentGroup = {
  key: string;
  node: SolutionDeploymentNode;
  components: SolutionComponent[];
  repositories: SolutionRepository[];
};

export type TrustGroup = {
  key: string;
  boundary: SolutionTrustBoundary;
  components: SolutionComponent[];
  systems: { systemId: string; name: string; kind: string }[];
  crossings: { interface: SolutionInterface; component: SolutionComponent | null }[];
};

export function interfaceHandle(interfaceId: string): string {
  return `iface-${interfaceId}`;
}

export function repositoryNodeKey(objectId: string): string {
  return `repo-${objectId}`;
}

export function systemOccurrenceId(systemId: string, occurrenceId: string | null): string {
  return occurrenceId || `sys-${systemId}`;
}

function stateNodesByObject(state: ArchitectureState | null): Map<string, ArchitectureStateNode> {
  const map = new Map<string, ArchitectureStateNode>();
  for (const node of state?.nodes ?? []) map.set(node.object_id, node);
  return map;
}

/** A saved layout is usable when at least one placed node has a real position. */
export function hasUsableLayout(positions: Point[]): boolean {
  if (positions.length === 0) return true;
  return !positions.every((point) => point.x === 0 && point.y === 0);
}

export function componentNodeHeight(component: SolutionComponent): number {
  let height = 74;
  if (component.responsibility) height += 16;
  for (const ui of component.interfaces) {
    height += 30;
    height += ui.operations.length * 18;
  }
  return Math.max(SOLUTION_NODE_SIZES.component.height, height + 12);
}

function systemRect(position: Point, width: number, height: number): Rect {
  return { x: position.x, y: position.y, width, height };
}

function rectsOverlap(a: Rect, b: Rect, gap = 0): boolean {
  return (
    a.x < b.x + b.width + gap &&
    a.x + a.width + gap > b.x &&
    a.y < b.y + b.height + gap &&
    a.y + a.height + gap > b.y
  );
}

/** Pushes a rectangle down until it clears every already-placed rectangle. */
function resolveVerticalOverlap(rect: Rect, placed: Rect[]): Rect {
  let next = rect;
  let guard = 0;
  while (placed.some((other) => rectsOverlap(next, other, 24)) && guard < 200) {
    const colliders = placed.filter((other) => rectsOverlap(next, other, 24));
    next = { ...next, y: Math.max(...colliders.map((other) => other.y + other.height)) + LAYOUT.repositoryGapY };
    guard += 1;
  }
  return next;
}

function autoLayoutRow(count: number, width: number, height: number, origin: Point, gapX: number, gapY: number): Point[] {
  const perRow = Math.max(1, Math.min(count, 4));
  return Array.from({ length: count }, (_, index) => ({
    x: origin.x + (index % perRow) * (width + gapX),
    y: origin.y + Math.floor(index / perRow) * (height + gapY),
  }));
}

function boundaryFrame(rects: Rect[]): { position: Point; width: number; height: number } {
  const pad = LAYOUT.boundaryPad;
  if (rects.length === 0) {
    return { position: { x: LAYOUT.originX, y: LAYOUT.originY }, width: 300, height: 180 };
  }
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
  return {
    position: { x: minX - pad.left, y: minY - pad.top },
    width: maxX + pad.right - (minX - pad.left),
    height: maxY + pad.bottom - (minY - pad.top),
  };
}

function perpendicular(side: string): Point {
  return side === "left" || side === "right" ? { x: 0, y: 1 } : { x: 1, y: 0 };
}

function sideOf(handle: string | null | undefined): string {
  if (!handle) return "right";
  return handle.split("-")[1] ?? "right";
}

/**
 * Routes each relationship between distinct handle pairs and spreads parallel
 * connectors that share a handle into separate lanes so they stay legible.
 */
function applyLaneOffsets(edges: GraphEdge[]): void {
  const sourceGroups = new Map<string, GraphEdge[]>();
  const targetGroups = new Map<string, GraphEdge[]>();
  for (const edge of edges) {
    if (!edge.sourceHandle || !edge.targetHandle) continue;
    const sourceKey = `${edge.source}|${edge.sourceHandle}`;
    const targetKey = `${edge.target}|${edge.targetHandle}`;
    sourceGroups.set(sourceKey, [...(sourceGroups.get(sourceKey) ?? []), edge]);
    targetGroups.set(targetKey, [...(targetGroups.get(targetKey) ?? []), edge]);
  }
  for (const group of sourceGroups.values()) {
    if (group.length < 2) continue;
    group.forEach((edge, index) => {
      const offset = (index - (group.length - 1) / 2) * LAYOUT.laneSpacing;
      const dir = perpendicular(edge.sourceSide ?? sideOf(edge.sourceHandle));
      edge.sourceOffset = { x: dir.x * offset, y: dir.y * offset };
    });
  }
  for (const group of targetGroups.values()) {
    if (group.length < 2) continue;
    group.forEach((edge, index) => {
      const offset = (index - (group.length - 1) / 2) * LAYOUT.laneSpacing;
      const dir = perpendicular(edge.targetSide ?? sideOf(edge.targetHandle));
      edge.targetOffset = { x: dir.x * offset, y: dir.y * offset };
    });
  }
}

function placeSystem(
  systemId: string,
  name: string,
  kind: string,
  external: boolean,
  nodes: Map<string, ArchitectureStateNode>,
  fallback: Point,
): PlacedSystem {
  const node = nodes.get(systemId);
  return {
    key: systemOccurrenceId(systemId, node?.occurrence_id ?? null),
    systemId,
    occurrenceId: node?.occurrence_id ?? "",
    name,
    kind,
    external,
    position: node?.position ? { x: node.position.x, y: node.position.y } : { x: fallback.x, y: fallback.y },
  };
}

export function contextGraph(
  design: SolutionDesign,
  state: ArchitectureState | null,
  options: LayoutOptions = {},
): ContextGraph {
  const nodes = stateNodesByObject(state);
  const memberIds = design.solution.members.map((member) => member.system_id);
  const savedMemberPositions = memberIds
    .map((id) => nodes.get(id)?.position)
    .filter((position): position is Point => Boolean(position));
  const autoMembers = options.auto || !hasUsableLayout(savedMemberPositions);

  const memberFallbacks = autoLayoutRow(
    memberIds.length,
    SOLUTION_NODE_SIZES.system.width,
    SOLUTION_NODE_SIZES.system.height,
    { x: LAYOUT.originX, y: LAYOUT.originY },
    LAYOUT.systemGapX,
    LAYOUT.systemGapY,
  );
  const members = design.solution.members.map((member, index) =>
    placeSystem(
      member.system_id,
      member.name,
      member.kind,
      false,
      autoMembers ? new Map() : nodes,
      memberFallbacks[index] ?? { x: LAYOUT.originX, y: LAYOUT.originY },
    ),
  );

  const memberRects = members.map((member) =>
    systemRect(member.position, SOLUTION_NODE_SIZES.system.width, SOLUTION_NODE_SIZES.system.height),
  );
  const frame = boundaryFrame(memberRects);

  const externalIds = design.solution.external_systems.map((system) => system.system_id);
  const savedExternalPositions = externalIds
    .map((id) => nodes.get(id)?.position)
    .filter((position): position is Point => Boolean(position));
  const autoExternals = options.auto || !hasUsableLayout(savedExternalPositions);
  const externalFallbacks = autoLayoutRow(
    externalIds.length,
    SOLUTION_NODE_SIZES.system.width,
    SOLUTION_NODE_SIZES.system.height,
    { x: frame.position.x + LAYOUT.boundaryPad.left, y: frame.position.y + frame.height + LAYOUT.externalGapY },
    LAYOUT.systemGapX,
    LAYOUT.systemGapY,
  );
  const externals = design.solution.external_systems.map((system, index) =>
    placeSystem(
      system.system_id,
      system.name,
      system.kind,
      true,
      autoExternals ? new Map() : nodes,
      externalFallbacks[index] ?? externalFallbacks[0] ?? { x: LAYOUT.originX, y: LAYOUT.originY },
    ),
  );
  const systems = [...members, ...externals];

  const boundaryKey = design.solution.occurrence_id || `solution-${design.solution.solution_object_id}`;
  const nodeKeys = new Map<string, string>();
  for (const system of systems) nodeKeys.set(system.systemId, system.key);
  const rectByKey = new Map<string, Rect>();
  for (const system of systems) {
    rectByKey.set(
      system.key,
      systemRect(system.position, SOLUTION_NODE_SIZES.system.width, SOLUTION_NODE_SIZES.system.height),
    );
  }
  if (rectByKey.has(boundaryKey)) rectByKey.delete(boundaryKey);

  // Visual containment already communicates membership, so only genuine
  // semantic relationships are drawn.
  const edges: GraphEdge[] = [];
  for (const relationship of state?.relationships ?? []) {
    const source = resolveOccurrenceKey(relationship.source_id, state, nodeKeys, boundaryKey);
    const target = resolveOccurrenceKey(relationship.target_id, state, nodeKeys, boundaryKey);
    if (!source || !target || source === target) continue;
    const sourceRect = rectByKey.get(source);
    const targetRect = rectByKey.get(target);
    if (!sourceRect || !targetRect) continue;
    const handles = chooseHandles(sourceRect, targetRect);
    edges.push({
      id: `rel-${relationship.id}`,
      source,
      target,
      sourceHandle: handleId("source", handles.source),
      targetHandle: handleId("target", handles.target),
      kind: "relationship",
      label: relationship.type,
    });
  }
  applyLaneOffsets(edges);

  return {
    boundary: {
      id: boundaryKey,
      occurrenceId: design.solution.occurrence_id,
      position: frame.position,
      width: frame.width,
      height: frame.height,
      label: design.solution.name,
    },
    systems,
    edges,
  };
}

function resolveOccurrenceKey(
  endpoint: string,
  state: ArchitectureState | null,
  nodeKeys: Map<string, string>,
  boundaryKey: string,
): string | null {
  const node = (state?.nodes ?? []).find((item) => item.occurrence_id === endpoint);
  const objectId = node?.object_id ?? endpoint;
  if (objectId === boundaryKey) return boundaryKey;
  return nodeKeys.get(objectId) ?? null;
}

function dependencyOrder(components: DecompositionComponent[], links: SolutionLink[]): Map<string, number> {
  const targetsBySource = new Map<string, string[]>();
  const incoming = new Map<string, number>();
  for (const item of components) incoming.set(item.component.object_id, 0);
  for (const link of links) {
    if (link.relationship_type !== "connects_to") continue;
    const sourceOwner = components.find((item) =>
      item.component.interfaces.some((ui) => ui.object_id === link.source_object_id),
    );
    const targetOwner = components.find((item) =>
      item.component.interfaces.some((ui) => ui.object_id === link.target_object_id),
    );
    if (!sourceOwner || !targetOwner || sourceOwner === targetOwner) continue;
    const list = targetsBySource.get(sourceOwner.component.object_id) ?? [];
    list.push(targetOwner.component.object_id);
    targetsBySource.set(sourceOwner.component.object_id, list);
    incoming.set(targetOwner.component.object_id, (incoming.get(targetOwner.component.object_id) ?? 0) + 1);
  }
  const depth = new Map<string, number>();
  const queue = components
    .map((item) => item.component.object_id)
    .filter((id) => (incoming.get(id) ?? 0) === 0);
  for (const id of queue) depth.set(id, 0);
  let cursor = 0;
  while (cursor < queue.length) {
    const current = queue[cursor];
    cursor += 1;
    for (const next of targetsBySource.get(current) ?? []) {
      depth.set(next, Math.max(depth.get(next) ?? 0, (depth.get(current) ?? 0) + 1));
      incoming.set(next, (incoming.get(next) ?? 0) - 1);
      if ((incoming.get(next) ?? 0) === 0) queue.push(next);
    }
  }
  // Any node left in a cycle gets a stable trailing column.
  let fallback = Math.max(0, ...[...depth.values()]) + 1;
  for (const item of components) {
    if (!depth.has(item.component.object_id)) {
      depth.set(item.component.object_id, fallback);
      fallback += 1;
    }
  }
  return depth;
}

function autoLayoutComponents(components: DecompositionComponent[], links: SolutionLink[]): Point[] {
  const positions = new Map<string, Point>();
  const hasDependencies = links.some((link) => link.relationship_type === "connects_to");
  if (!hasDependencies) {
    components.forEach((item, index) => {
      positions.set(item.component.object_id, {
        x: LAYOUT.originX + index * (SOLUTION_NODE_SIZES.component.width + LAYOUT.componentGapX),
        y: LAYOUT.originY,
      });
    });
    return components.map((item) => positions.get(item.component.object_id)!);
  }
  const depth = dependencyOrder(components, links);
  const columnCursor = new Map<number, number>();
  for (const item of components) {
    const column = depth.get(item.component.object_id) ?? 0;
    const y = columnCursor.get(column) ?? LAYOUT.originY;
    positions.set(item.component.object_id, {
      x: LAYOUT.originX + column * (SOLUTION_NODE_SIZES.component.width + LAYOUT.componentGapX),
      y,
    });
    columnCursor.set(column, y + item.height + LAYOUT.componentGapY);
  }
  return components.map((item) => positions.get(item.component.object_id)!);
}

export function decompositionGraph(
  design: SolutionDesign,
  state: ArchitectureState | null,
  options: LayoutOptions = {},
): DecompositionGraph {
  const nodes = stateNodesByObject(state);
  const baseComponents: DecompositionComponent[] = design.components.map((component) => {
    const node = nodes.get(component.object_id);
    return {
      key: component.occurrence_id || `comp-${component.object_id}`,
      component,
      occurrenceId: component.occurrence_id,
      position: component.position,
      height: componentNodeHeight(component),
      provided: component.interfaces.filter((ui) => ui.direction === "provided"),
      required: component.interfaces.filter((ui) => ui.direction === "required"),
    };
  });

  const savedPositions = baseComponents.map((item) => item.position);
  const usesAutoLayout = options.auto || !hasUsableLayout(savedPositions);
  const autoPositions = usesAutoLayout ? autoLayoutComponents(baseComponents, design.links) : [];
  const components: DecompositionComponent[] = baseComponents.map((item, index) => ({
    ...item,
    position: usesAutoLayout ? autoPositions[index] ?? item.position : item.position,
  }));

  const componentByObject = new Map(components.map((item) => [item.component.object_id, item]));
  const interfaceOwner = new Map<string, DecompositionComponent>();
  for (const item of components) {
    for (const ui of item.component.interfaces) interfaceOwner.set(ui.object_id, item);
  }

  const componentRectByObject = new Map<string, Rect>();
  for (const item of components) {
    componentRectByObject.set(item.component.object_id, {
      x: item.position.x,
      y: item.position.y,
      width: SOLUTION_NODE_SIZES.component.width,
      height: item.height,
    });
  }

  // Interface ports sit on the side facing the component they connect to. A
  // `connects_to` link always runs required → provided, so with a fixed
  // required-left / provided-right convention both ends face away from each
  // other and the connector has to loop around the entire diagram.
  const sideVotes = new Map<string, { left: number; right: number }>();
  const voteSide = (interfaceId: string, side: "left" | "right"): void => {
    const votes = sideVotes.get(interfaceId) ?? { left: 0, right: 0 };
    votes[side] += 1;
    sideVotes.set(interfaceId, votes);
  };
  for (const link of design.links.filter((item) => item.relationship_type === "connects_to")) {
    const source = interfaceOwner.get(link.source_object_id);
    const target = interfaceOwner.get(link.target_object_id);
    if (!source || !target || source === target) continue;
    const sourceRect = componentRectByObject.get(source.component.object_id);
    const targetRect = componentRectByObject.get(target.component.object_id);
    if (!sourceRect || !targetRect) continue;
    const targetIsRight =
      targetRect.x + targetRect.width / 2 >= sourceRect.x + sourceRect.width / 2;
    voteSide(link.source_object_id, targetIsRight ? "right" : "left");
    voteSide(link.target_object_id, targetIsRight ? "left" : "right");
  }
  const portSides: Record<string, FlowSide> = {};
  for (const [interfaceId, votes] of sideVotes) {
    portSides[interfaceId] = votes.right >= votes.left ? "right" : "left";
  }

  const repositoryUsage = new Map<string, Set<string>>();
  for (const link of design.links.filter((item) => item.relationship_type === "uses_repository")) {
    const owner = componentByObject.get(link.source_object_id) ?? interfaceOwner.get(link.source_object_id);
    if (!owner) continue;
    const users = repositoryUsage.get(link.target_object_id) ?? new Set<string>();
    users.add(owner.component.object_id);
    repositoryUsage.set(link.target_object_id, users);
  }

  // Repositories sit below the components that use them; overlapping placements
  // are pushed down until the node rectangles are clear.
  const placedRects: Rect[] = components.map((item) =>
    ({ x: item.position.x, y: item.position.y, width: SOLUTION_NODE_SIZES.component.width, height: item.height }),
  );
  const repositories: DecompositionRepository[] = design.repositories.map((repository) => {
    const usedBy = [...(repositoryUsage.get(repository.object_id) ?? new Set<string>())];
    const users = usedBy
      .map((objectId) => componentByObject.get(objectId))
      .filter((item): item is DecompositionComponent => Boolean(item));
    const width = SOLUTION_NODE_SIZES.repository.width;
    if (users.length === 0) {
      const x = LAYOUT.originX + placedRects.length * 20;
      const y = Math.max(...placedRects.map((rect) => rect.y + rect.height)) + LAYOUT.repositoryGapY;
      const rect = resolveVerticalOverlap({ x, y, width, height: SOLUTION_NODE_SIZES.repository.height }, placedRects);
      placedRects.push(rect);
      return { key: repositoryNodeKey(repository.object_id), repository, position: { x: rect.x, y: rect.y }, usedBy };
    }
    const anchor = users[0];
    const anchorRect = placedRects.find((rect) => rect.x === anchor.position.x && rect.y === anchor.position.y);
    const baseX = anchor.position.x + (SOLUTION_NODE_SIZES.component.width - width) / 2;
    const baseY = anchor.position.y + anchor.height + LAYOUT.repositoryGapY;
    const rect = resolveVerticalOverlap(
      { x: baseX, y: baseY, width, height: SOLUTION_NODE_SIZES.repository.height },
      placedRects.filter((candidate) => candidate !== anchorRect),
    );
    placedRects.push(rect);
    return { key: repositoryNodeKey(repository.object_id), repository, position: { x: rect.x, y: rect.y }, usedBy };
  });

  const boundaryKey = design.solution.occurrence_id || `solution-${design.solution.solution_object_id}`;
  const edges: GraphEdge[] = [];

  for (const link of design.links.filter((item) => item.relationship_type === "connects_to")) {
    const source = interfaceOwner.get(link.source_object_id);
    const target = interfaceOwner.get(link.target_object_id);
    if (!source || !target) continue;
    const sourceInterface = source.component.interfaces.find((ui) => ui.object_id === link.source_object_id);
    const targetInterface = target.component.interfaces.find((ui) => ui.object_id === link.target_object_id);
    // A link connects a *required* interface to a *provided* one; the label only
    // repeats the name when the two ends are called differently.
    const sourceName = sourceInterface?.name ?? "required";
    const targetName = targetInterface?.name ?? "provided";
    edges.push({
      id: link.id,
      source: source.key,
      target: target.key,
      sourceHandle: interfaceHandle(link.source_object_id),
      targetHandle: interfaceHandle(link.target_object_id),
      sourceSide: portSides[link.source_object_id] ?? "right",
      targetSide: portSides[link.target_object_id] ?? "left",
      kind: "connects_to",
      label: sourceName === targetName ? sourceName : `${sourceName} → ${targetName}`,
    });
  }

  const repositoryByObject = new Map(repositories.map((item) => [item.repository.object_id, item]));
  for (const [repositoryId, users] of repositoryUsage) {
    const repository = repositoryByObject.get(repositoryId);
    if (!repository) continue;
    for (const objectId of users) {
      const component = componentByObject.get(objectId);
      if (!component) continue;
      edges.push({
        id: `uses-${objectId}-${repositoryId}`,
        source: component.key,
        target: repository.key,
        kind: "uses",
        label: "uses",
      });
    }
  }

  const contentBottom = Math.max(
    ...placedRects.map((rect) => rect.y + rect.height),
    ...components.map((item) => item.position.y + item.height),
  );
  const externalIds = design.solution.external_systems.map((system) => system.system_id);
  const savedExternalPositions = externalIds
    .map((id) => nodes.get(id)?.position)
    .filter((position): position is Point => Boolean(position));
  const autoExternals = options.auto || !hasUsableLayout(savedExternalPositions);
  const externalFallbacks = autoLayoutRow(
    externalIds.length,
    SOLUTION_NODE_SIZES.system.width,
    SOLUTION_NODE_SIZES.system.height,
    { x: LAYOUT.originX, y: contentBottom + LAYOUT.externalGapY },
    LAYOUT.systemGapX,
    LAYOUT.systemGapY,
  );
  const externals = design.solution.external_systems.map((system, index) =>
    placeSystem(
      system.system_id,
      system.name,
      system.kind,
      true,
      autoExternals ? new Map() : nodes,
      externalFallbacks[index] ?? externalFallbacks[0] ?? { x: LAYOUT.originX, y: contentBottom + LAYOUT.externalGapY },
    ),
  );
  const externalByObject = new Map(externals.map((item) => [item.systemId, item]));

  for (const relationship of state?.relationships ?? []) {
    const sourceNode = (state?.nodes ?? []).find((node) => node.occurrence_id === relationship.source_id);
    const targetNode = (state?.nodes ?? []).find((node) => node.occurrence_id === relationship.target_id);
    const sourceObject = sourceNode?.object_id ?? relationship.source_id;
    const targetObject = targetNode?.object_id ?? relationship.target_id;
    const sourceComponent = componentByObject.get(sourceObject);
    const targetComponent = componentByObject.get(targetObject);
    const sourceExternal = externalByObject.get(sourceObject);
    const targetExternal = externalByObject.get(targetObject);
    if (sourceComponent && targetExternal) {
      edges.push({ id: `ext-${relationship.id}`, source: sourceComponent.key, target: targetExternal.key, kind: "external", label: relationship.type });
    } else if (targetComponent && sourceExternal) {
      edges.push({ id: `ext-${relationship.id}`, source: sourceExternal.key, target: targetComponent.key, kind: "external", label: relationship.type });
    } else if (sourceComponent && targetComponent && sourceComponent !== targetComponent) {
      edges.push({ id: `dep-${relationship.id}`, source: sourceComponent.key, target: targetComponent.key, kind: "external", label: relationship.type });
    }
  }
  applyLaneOffsets(edges);

  const contentRects: Rect[] = [
    ...components.map((item) => ({ x: item.position.x, y: item.position.y, width: SOLUTION_NODE_SIZES.component.width, height: item.height })),
    ...repositories.map((item) => ({ x: item.position.x, y: item.position.y, width: SOLUTION_NODE_SIZES.repository.width, height: SOLUTION_NODE_SIZES.repository.height })),
  ];
  const frame = boundaryFrame(contentRects);

  return {
    boundary: {
      id: boundaryKey,
      occurrenceId: design.solution.occurrence_id,
      position: frame.position,
      width: frame.width,
      height: frame.height,
      label: design.solution.name,
    },
    components,
    repositories,
    externals,
    edges,
    portSides,
  };
}

export function deploymentGroups(design: SolutionDesign): DeploymentGroup[] {
  const deployed = new Map<string, Set<string>>();
  for (const link of design.links.filter((item) => item.relationship_type === "deployed_on")) {
    const users = deployed.get(link.target_object_id) ?? new Set<string>();
    users.add(link.source_object_id);
    deployed.set(link.target_object_id, users);
  }
  const repositoryUsage = new Map<string, Set<string>>();
  for (const link of design.links.filter((item) => item.relationship_type === "uses_repository")) {
    const users = repositoryUsage.get(link.source_object_id) ?? new Set<string>();
    users.add(link.target_object_id);
    repositoryUsage.set(link.source_object_id, users);
  }
  const componentById = new Map(design.components.map((component) => [component.object_id, component]));
  const repositoryById = new Map(design.repositories.map((repository) => [repository.object_id, repository]));

  return design.deployment_nodes.map((node) => {
    const componentIds = [...(deployed.get(node.object_id) ?? new Set<string>())];
    const components = componentIds
      .map((objectId) => componentById.get(objectId))
      .filter((item): item is SolutionComponent => Boolean(item));
    const repositoryIds = new Set<string>();
    for (const componentId of componentIds) {
      for (const repositoryId of repositoryUsage.get(componentId) ?? []) repositoryIds.add(repositoryId);
    }
    const repositories = [...repositoryIds]
      .map((objectId) => repositoryById.get(objectId))
      .filter((item): item is SolutionRepository => Boolean(item));
    return { key: `deploy-${node.object_id}`, node, components, repositories };
  });
}

export function unassignedComponents(design: SolutionDesign): SolutionComponent[] {
  const assigned = new Set(
    design.links
      .filter((item) => item.relationship_type === "deployed_on")
      .map((item) => item.source_object_id),
  );
  return design.components.filter((component) => !assigned.has(component.object_id));
}

export function trustGroups(design: SolutionDesign): TrustGroup[] {
  const systemNames = new Map<string, { name: string; kind: string }>();
  for (const member of [...design.solution.members, ...design.solution.external_systems]) {
    systemNames.set(member.system_id, { name: member.name, kind: member.kind });
  }
  const componentById = new Map(design.components.map((component) => [component.object_id, component]));
  const interfaceById = new Map<string, SolutionInterface>();
  const interfaceOwner = new Map<string, SolutionComponent>();
  for (const component of design.components) {
    for (const ui of component.interfaces) {
      interfaceById.set(ui.object_id, ui);
      interfaceOwner.set(ui.object_id, component);
    }
  }

  return design.trust_boundaries.map((boundary) => {
    const contained = design.links
      .filter((item) => item.relationship_type === "contained_in" && item.target_object_id === boundary.object_id)
      .map((item) => item.source_object_id);
    const components: SolutionComponent[] = [];
    const systems: { systemId: string; name: string; kind: string }[] = [];
    for (const objectId of contained) {
      const component = componentById.get(objectId);
      if (component) {
        components.push(component);
        continue;
      }
      const system = systemNames.get(objectId);
      if (system) systems.push({ systemId: objectId, name: system.name, kind: system.kind });
    }
    const crossings = design.links
      .filter((item) => item.relationship_type === "crosses" && item.target_object_id === boundary.object_id)
      .map((item) => ({
        interface: interfaceById.get(item.source_object_id) ?? null,
        component: interfaceOwner.get(item.source_object_id) ?? null,
      }))
      .filter((item): item is { interface: SolutionInterface; component: SolutionComponent | null } => Boolean(item.interface));
    return { key: `trust-${boundary.object_id}`, boundary, components, systems, crossings };
  });
}

export function linkTargets(links: SolutionLink[], relationshipType: string, targetId: string): string[] {
  return links
    .filter((link) => link.relationship_type === relationshipType && link.target_object_id === targetId)
    .map((link) => link.source_object_id);
}
