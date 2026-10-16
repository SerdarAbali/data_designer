import { describe, expect, it } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import {
  contextGraph,
  decompositionGraph,
  deploymentGroups,
  hasUsableLayout,
  componentNodeHeight,
  trustGroups,
  unassignedComponents,
} from "./solutionCanvasModel";
import type { SolutionDesign } from "./solutionModel";

type Rect = { x: number; y: number; width: number; height: number };

function overlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

const design: SolutionDesign = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  solution: {
    solution_object_id: "sol-1",
    occurrence_id: "occ-sol",
    name: "Payments Platform",
    description: null,
    owner: "Payments Team",
    position: { x: 0, y: 0 },
    members: [
      { system_id: "sys-1", name: "Core Banking", kind: "service" },
      { system_id: "sys-3", name: "Billing", kind: "service" },
    ],
    external_systems: [{ system_id: "sys-2", name: "Partner Bank", kind: "external" }],
  },
  components: [
    {
      object_id: "comp-1",
      occurrence_id: "occ-comp-1",
      solution_object_id: "sol-1",
      parent_component_object_id: null,
      name: "Payment API",
      description: null,
      responsibility: "Expose payments.",
      component_type: "service",
      technology: "FastAPI",
      position: { x: 100, y: 100 },
      created_in_state_id: "state-1",
      interfaces: [
        {
          object_id: "iface-1",
          component_object_id: "comp-1",
          name: "Payments API",
          description: null,
          direction: "provided",
          interface_kind: "sync",
          protocol: "HTTPS",
          technology: null,
          created_in_state_id: "state-1",
          operations: [
            {
              object_id: "op-1",
              interface_object_id: "iface-1",
              name: "CreatePayment",
              description: null,
              operation_kind: "operation",
              request_object_id: null,
              response_object_id: null,
              ordinal: 0,
              created_in_state_id: "state-1",
            },
          ],
        },
        {
          object_id: "iface-2",
          component_object_id: "comp-1",
          name: "Ledger Client",
          description: null,
          direction: "required",
          interface_kind: null,
          protocol: "gRPC",
          technology: null,
          created_in_state_id: "state-1",
          operations: [],
        },
      ],
    },
    {
      object_id: "comp-2",
      occurrence_id: "occ-comp-2",
      solution_object_id: "sol-1",
      parent_component_object_id: null,
      name: "Ledger Service",
      description: null,
      responsibility: "Own the ledger.",
      component_type: "service",
      technology: "Go",
      position: { x: 420, y: 100 },
      created_in_state_id: "state-1",
      interfaces: [
        {
          object_id: "iface-3",
          component_object_id: "comp-2",
          name: "Ledger API",
          description: null,
          direction: "provided",
          interface_kind: "sync",
          protocol: "gRPC",
          technology: null,
          created_in_state_id: "state-1",
          operations: [
            {
              object_id: "op-2",
              interface_object_id: "iface-3",
              name: "PostEntry",
              description: null,
              operation_kind: "operation",
              request_object_id: null,
              response_object_id: null,
              ordinal: 0,
              created_in_state_id: "state-1",
            },
          ],
        },
      ],
    },
  ],
  repositories: [
    {
      object_id: "repo-1",
      solution_object_id: "sol-1",
      name: "Ledger Store",
      description: null,
      owner: "Payments Team",
      repository_type: "relational",
      technology: "PostgreSQL",
      created_in_state_id: "state-1",
    },
  ],
  deployment_nodes: [
    {
      object_id: "dep-1",
      solution_object_id: "sol-1",
      name: "Production Cluster",
      description: null,
      technology: "Kubernetes",
      environment: "production",
      hosting: "cloud",
      created_in_state_id: "state-1",
    },
  ],
  trust_boundaries: [
    {
      object_id: "trust-1",
      solution_object_id: "sol-1",
      name: "Internal Zone",
      description: null,
      security_level: "private",
      created_in_state_id: "state-1",
    },
  ],
  links: [
    { id: "l1", source_object_id: "iface-2", target_object_id: "iface-3", relationship_type: "connects_to" },
    { id: "l2", source_object_id: "comp-2", target_object_id: "repo-1", relationship_type: "uses_repository" },
    { id: "l3", source_object_id: "comp-1", target_object_id: "dep-1", relationship_type: "deployed_on" },
    { id: "l4", source_object_id: "comp-1", target_object_id: "trust-1", relationship_type: "contained_in" },
    { id: "l5", source_object_id: "sys-1", target_object_id: "trust-1", relationship_type: "contained_in" },
    { id: "l6", source_object_id: "iface-1", target_object_id: "trust-1", relationship_type: "crosses" },
  ],
};

const state: ArchitectureState = {
  id: "state-1",
  workspace_id: "ws-1",
  name: "Candidate",
  state_type: "candidate",
  nodes: [
    { occurrence_id: "occ-sol", object_id: "sol-1", position: { x: 0, y: 0 } },
    { occurrence_id: "occ-sys-1", object_id: "sys-1", position: { x: 120, y: 140 } },
    { occurrence_id: "occ-sys-3", object_id: "sys-3", position: { x: 420, y: 140 } },
  ],
  relationships: [
    { id: "rel-1", source_id: "occ-sys-1", target_id: "occ-sys-3", type: "Publishes" },
  ],
  created_at: "",
  updated_at: "",
};

function insideBoundary(rect: Rect, boundary: { position: { x: number; y: number }; width: number; height: number }): boolean {
  return (
    rect.x >= boundary.position.x &&
    rect.y >= boundary.position.y &&
    rect.x + rect.width <= boundary.position.x + boundary.width &&
    rect.y + rect.height <= boundary.position.y + boundary.height
  );
}

describe("hasUsableLayout", () => {
  it("treats an all-origin layout as unusable and a placed layout as usable", () => {
    expect(hasUsableLayout([])).toBe(true);
    expect(hasUsableLayout([{ x: 0, y: 0 }, { x: 0, y: 0 }])).toBe(false);
    expect(hasUsableLayout([{ x: 10, y: 40 }, { x: 0, y: 0 }])).toBe(true);
  });
});

describe("contextGraph", () => {
  it("places members inside the solution boundary and externals outside", () => {
    const graph = contextGraph(design, state);
    const boundary = graph.boundary;
    const member = graph.systems.find((system) => system.systemId === "sys-1")!;
    const external = graph.systems.find((system) => system.systemId === "sys-2")!;
    expect(insideBoundary({ x: member.position.x, y: member.position.y, width: 200, height: 72 }, boundary)).toBe(true);
    expect(external.position.y).toBeGreaterThanOrEqual(boundary.position.y + boundary.height);
  });

  it("sizes the boundary around its members with padding", () => {
    const graph = contextGraph(design, state);
    const memberXs = graph.systems
      .filter((system) => !system.external)
      .map((system) => system.position.x);
    expect(graph.boundary.position.x).toBeLessThanOrEqual(Math.min(...memberXs) - 40);
    expect(graph.boundary.position.y).toBeLessThanOrEqual(140 - 40);
  });

  it("keeps semantic relationships and drops membership lines", () => {
    const graph = contextGraph(design, state);
    expect(graph.edges.some((edge) => edge.kind === "relationship" && edge.label === "Publishes")).toBe(true);
    expect(graph.edges.some((edge) => edge.kind === "member")).toBe(false);
    expect(graph.edges.some((edge) => edge.kind === "external")).toBe(false);
  });

  it("preserves a saved manual layout instead of overwriting it", () => {
    const graph = contextGraph(design, state);
    expect(graph.systems.find((system) => system.systemId === "sys-1")!.position).toEqual({ x: 120, y: 140 });
    expect(graph.systems.find((system) => system.systemId === "sys-3")!.position).toEqual({ x: 420, y: 140 });
  });

  it("auto-arranges members when no usable saved layout exists", () => {
    const flat: ArchitectureState = {
      ...state,
      nodes: [
        { occurrence_id: "occ-sol", object_id: "sol-1", position: { x: 0, y: 0 } },
        { occurrence_id: "occ-sys-1", object_id: "sys-1", position: { x: 0, y: 0 } },
        { occurrence_id: "occ-sys-3", object_id: "sys-3", position: { x: 0, y: 0 } },
      ],
    };
    const graph = contextGraph(design, flat);
    const members = graph.systems.filter((system) => !system.external);
    expect(members[0].position.x).not.toBe(members[1].position.x);
    for (const member of members) {
      expect(insideBoundary({ x: member.position.x, y: member.position.y, width: 200, height: 72 }, graph.boundary)).toBe(true);
    }
  });
});

describe("decompositionGraph", () => {
  function contentRects(graph: ReturnType<typeof decompositionGraph>): Rect[] {
    return [
      ...graph.components.map((item) => ({
        x: item.position.x,
        y: item.position.y,
        width: 260,
        height: item.height,
      })),
      ...graph.repositories.map((item) => ({
        x: item.position.x,
        y: item.position.y,
        width: 210,
        height: 78,
      })),
    ];
  }

  it("preserves a saved manual component layout", () => {
    const graph = decompositionGraph(design, state);
    expect(graph.components.find((item) => item.component.object_id === "comp-1")!.position).toEqual({ x: 100, y: 100 });
    expect(graph.components.find((item) => item.component.object_id === "comp-2")!.position).toEqual({ x: 420, y: 100 });
  });

  it("does not overlap any decomposition nodes", () => {
    const graph = decompositionGraph(design, state);
    const rects = contentRects(graph);
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        expect(overlap(rects[i], rects[j])).toBe(false);
      }
    }
  });

  it("places the repository below its connected component without overlap", () => {
    const graph = decompositionGraph(design, state);
    const component = graph.components.find((item) => item.component.object_id === "comp-2")!;
    const repository = graph.repositories.find((item) => item.repository.object_id === "repo-1")!;
    const componentRect = { x: component.position.x, y: component.position.y, width: 260, height: component.height };
    const repositoryRect = { x: repository.position.x, y: repository.position.y, width: 210, height: 78 };
    expect(repositoryRect.y).toBeGreaterThanOrEqual(componentRect.y + componentRect.height);
    expect(overlap(componentRect, repositoryRect)).toBe(false);
  });

  it("sizes the boundary compactly around components and repositories", () => {
    const graph = decompositionGraph(design, state);
    const rects = contentRects(graph);
    for (const rect of rects) {
      expect(insideBoundary(rect, graph.boundary)).toBe(true);
    }
    const minX = Math.min(...rects.map((rect) => rect.x));
    const minY = Math.min(...rects.map((rect) => rect.y));
    expect(graph.boundary.position.x).toBeLessThanOrEqual(minX - 40);
    expect(graph.boundary.position.y).toBeLessThanOrEqual(minY - 40);
    // Compact: the frame is not vastly larger than its contents.
    const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
    const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
    expect(graph.boundary.width).toBeLessThanOrEqual(maxX - minX + 120);
    expect(graph.boundary.height).toBeLessThanOrEqual(maxY - minY + 140);
  });

  it("auto-arranges components left to right following dependencies", () => {
    const graph = decompositionGraph(design, state, { auto: true });
    const portal = graph.components.find((item) => item.component.object_id === "comp-1")!;
    const ledger = graph.components.find((item) => item.component.object_id === "comp-2")!;
    expect(portal.position.x).toBeLessThan(ledger.position.x);
    const rects = contentRects(graph);
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        expect(overlap(rects[i], rects[j])).toBe(false);
      }
    }
  });

  it("accounts for component height when estimating node size", () => {
    expect(componentNodeHeight(design.components[0])).toBeGreaterThanOrEqual(96);
    expect(componentNodeHeight(design.components[1])).toBeLessThan(componentNodeHeight(design.components[0]));
  });
});

describe("deploymentGroups", () => {
  it("places deployed components inside their deployment node", () => {
    const groups = deploymentGroups(design);
    const node = groups.find((group) => group.node.object_id === "dep-1")!;
    expect(node.components.map((component) => component.name)).toEqual(["Payment API"]);
    expect(unassignedComponents(design).map((component) => component.name)).toEqual(["Ledger Service"]);
  });
});

describe("trustGroups", () => {
  it("lists contained objects and highlights crossing flows", () => {
    const groups = trustGroups(design);
    const group = groups.find((item) => item.boundary.object_id === "trust-1")!;
    expect(group.components.map((component) => component.name)).toEqual(["Payment API"]);
    expect(group.systems.map((system) => system.name)).toEqual(["Core Banking"]);
    expect(group.crossings.map((crossing) => crossing.interface.name)).toEqual(["Payments API"]);
    expect(group.boundary.security_level).toBe("private");
  });
});
