import type { ArchitectureState, ArchitectureStateNode } from "../architectureTypes";
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

export type Point = { x: number; y: number };

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

function envelope(points: Point[], fallback: Point): { position: Point; width: number; height: number } {
  if (points.length === 0) {
    return {
      position: fallback,
      width: SOLUTION_NODE_SIZES.boundary.width,
      height: SOLUTION_NODE_SIZES.boundary.height,
    };
  }
  const padX = 60;
  const padTop = 78;
  const padBottom = 64;
  const minX = Math.min(...points.map((point) => point.x)) - padX;
  const minY = Math.min(...points.map((point) => point.y)) - padTop;
  const maxX = Math.max(...points.map((point) => point.x + SOLUTION_NODE_SIZES.system.width)) + padX;
  const maxY = Math.max(...points.map((point) => point.y + SOLUTION_NODE_SIZES.system.height)) + padBottom;
  return {
    position: { x: minX, y: minY },
    width: Math.max(SOLUTION_NODE_SIZES.boundary.width, maxX - minX),
    height: Math.max(SOLUTION_NODE_SIZES.boundary.height, maxY - minY),
  };
}

function placeSystem(
  systemId: string,
  name: string,
  kind: string,
  external: boolean,
  index: number,
  nodes: Map<string, ArchitectureStateNode>,
  fallback: Point,
): PlacedSystem {
  const node = nodes.get(systemId);
  const position = node?.position ?? {
    x: fallback.x + index * (SOLUTION_NODE_SIZES.system.width + 40),
    y: fallback.y,
  };
  return {
    key: systemOccurrenceId(systemId, node?.occurrence_id ?? null),
    systemId,
    occurrenceId: node?.occurrence_id ?? "",
    name,
    kind,
    external,
    position: { x: position.x, y: position.y },
  };
}

export function contextGraph(design: SolutionDesign, state: ArchitectureState | null): ContextGraph {
  const nodes = stateNodesByObject(state);
  const members = design.solution.members.map((member, index) =>
    placeSystem(
      member.system_id,
      member.name,
      member.kind,
      false,
      index,
      nodes,
      { x: design.solution.position.x + 40, y: design.solution.position.y + 70 },
    ),
  );
  const externalSystems = design.solution.external_systems.map((system, index) =>
    placeSystem(
      system.system_id,
      system.name,
      system.kind,
      true,
      index,
      nodes,
      { x: design.solution.position.x + 40, y: design.solution.position.y + 260 },
    ),
  );
  const systems = [...members, ...externalSystems];

  const memberKeys = new Set(members.map((member) => member.key));
  const nodeKeys = new Map<string, string>();
  for (const system of systems) nodeKeys.set(system.systemId, system.key);

  const edges: GraphEdge[] = [];
  for (const member of members) {
    edges.push({
      id: `member-${member.systemId}`,
      source: design.solution.occurrence_id || `solution-${design.solution.solution_object_id}`,
      target: member.key,
      kind: "member",
      label: "member",
    });
  }
  for (const external of externalSystems) {
    edges.push({
      id: `external-${external.systemId}`,
      source: external.key,
      target: design.solution.occurrence_id || `solution-${design.solution.solution_object_id}`,
      kind: "external",
      label: "external",
    });
  }

  // Real state relationships that touch the solution, a member or an external
  // system are surfaced as labelled dependency edges.
  const boundaryKey = design.solution.occurrence_id || `solution-${design.solution.solution_object_id}`;
  const known = new Set<string>([boundaryKey, ...systems.map((system) => system.key)]);
  for (const relationship of state?.relationships ?? []) {
    const source = resolveOccurrenceKey(relationship.source_id, state, nodeKeys, boundaryKey);
    const target = resolveOccurrenceKey(relationship.target_id, state, nodeKeys, boundaryKey);
    if (!source || !target || source === target) continue;
    if (!known.has(source) || !known.has(target)) continue;
    if (edges.some((edge) => edge.source === source && edge.target === target && edge.kind !== "relationship")) continue;
    edges.push({
      id: `rel-${relationship.id}`,
      source,
      target,
      kind: "relationship",
      label: relationship.type,
    });
  }

  const memberPoints = members.map((member) => member.position);
  const frame = envelope(memberPoints, design.solution.position);

  return {
    boundary: {
      id: boundaryKey,
      occurrenceId: design.solution.occurrence_id,
      position: design.solution.position,
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

export function decompositionGraph(
  design: SolutionDesign,
  state: ArchitectureState | null,
): DecompositionGraph {
  const nodes = stateNodesByObject(state);
  const components: DecompositionComponent[] = design.components.map((component) => {
    const node = nodes.get(component.object_id);
    return {
      key: component.occurrence_id || `comp-${component.object_id}`,
      component,
      occurrenceId: component.occurrence_id,
      position: component.position,
      provided: component.interfaces.filter((ui) => ui.direction === "provided"),
      required: component.interfaces.filter((ui) => ui.direction === "required"),
    };
  });

  const boundaryKey = design.solution.occurrence_id || `solution-${design.solution.solution_object_id}`;
  const componentByObject = new Map(components.map((item) => [item.component.object_id, item]));
  const interfaceOwner = new Map<string, DecompositionComponent>();
  for (const item of components) {
    for (const ui of item.component.interfaces) interfaceOwner.set(ui.object_id, item);
  }

  const edges: GraphEdge[] = [];

  // Provided/required connections and the component dependency they imply.
  for (const link of design.links.filter((item) => item.relationship_type === "connects_to")) {
    const source = interfaceOwner.get(link.source_object_id);
    const target = interfaceOwner.get(link.target_object_id);
    if (!source || !target) continue;
    const sourceInterface = source.component.interfaces.find((ui) => ui.object_id === link.source_object_id);
    const targetInterface = target.component.interfaces.find((ui) => ui.object_id === link.target_object_id);
    edges.push({
      id: link.id,
      source: source.key,
      target: target.key,
      sourceHandle: interfaceHandle(link.source_object_id),
      targetHandle: interfaceHandle(link.target_object_id),
      kind: "connects_to",
      label: `${sourceInterface?.name ?? "required"} → ${targetInterface?.name ?? "provided"}`,
    });
  }

  // Repository satellite nodes, placed next to the components that use them.
  const repositoryUsage = new Map<string, Set<string>>();
  for (const link of design.links.filter((item) => item.relationship_type === "uses_repository")) {
    const owner = componentByObject.get(link.source_object_id) ?? interfaceOwner.get(link.source_object_id);
    if (!owner) continue;
    const users = repositoryUsage.get(link.target_object_id) ?? new Set<string>();
    users.add(owner.component.object_id);
    repositoryUsage.set(link.target_object_id, users);
  }

  const repositories: DecompositionRepository[] = design.repositories.map((repository, index) => {
    const usedBy = [...(repositoryUsage.get(repository.object_id) ?? new Set<string>())];
    const users = usedBy
      .map((objectId) => componentByObject.get(objectId))
      .filter((item): item is DecompositionComponent => Boolean(item));
    const position: Point = users.length
      ? {
          x: users.reduce((sum, item) => sum + item.position.x, 0) / users.length + 40,
          y: Math.min(...users.map((item) => item.position.y)) + 150 + index * 10,
        }
      : {
          x: design.solution.position.x + 40 + index * (SOLUTION_NODE_SIZES.repository.width + 30),
          y: design.solution.position.y + frameBottom(components) + 40,
        };
    return { key: repositoryNodeKey(repository.object_id), repository, position, usedBy };
  });

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

  // External (non-member) catalog systems placed on the solution canvas.
  const externals = design.solution.external_systems.map((system, index) =>
    placeSystem(system.system_id, system.name, system.kind, true, index, nodes, {
      x: design.solution.position.x + 40,
      y: design.solution.position.y + frameBottom(components) + 180,
    }),
  );
  const externalByObject = new Map(externals.map((item) => [item.systemId, item]));

  // State relationships between components and external systems.
  const componentByOccurrence = new Map(components.map((item) => [item.occurrenceId, item]));
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
    } else if (sourceComponent && targetComponent) {
      const sourceKey = componentByOccurrence.get(sourceComponent.occurrenceId)?.key ?? sourceComponent.key;
      edges.push({ id: `dep-${relationship.id}`, source: sourceKey, target: targetComponent.key, kind: "external", label: relationship.type });
    }
  }

  const memberPoints = design.solution.members.map((member) => {
    const node = nodes.get(member.system_id);
    return node?.position ?? null;
  }).filter((point): point is Point => Boolean(point));
  const componentPoints = components.map((item) => item.position);
  const frame = envelope(componentPoints.length ? componentPoints : memberPoints, design.solution.position);

  return {
    boundary: {
      id: boundaryKey,
      occurrenceId: design.solution.occurrence_id,
      position: design.solution.position,
      width: frame.width,
      height: frame.height,
      label: design.solution.name,
    },
    components,
    repositories,
    externals,
    edges,
  };
}

function frameBottom(components: DecompositionComponent[]): number {
  if (components.length === 0) return 0;
  return Math.max(...components.map((item) => item.position.y)) - Math.min(...components.map((item) => item.position.y));
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
