import { describe, expect, it } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import {
  contextGraph,
  decompositionGraph,
  deploymentGroups,
  trustGroups,
  unassignedComponents,
} from "./solutionCanvasModel";
import type { SolutionDesign } from "./solutionModel";

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
    members: [{ system_id: "sys-1", name: "Core Banking", kind: "service" }],
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
    { occurrence_id: "occ-sys-1", object_id: "sys-1", position: { x: 40, y: 70 } },
    { occurrence_id: "occ-sys-2", object_id: "sys-2", position: { x: 40, y: 320 } },
  ],
  relationships: [],
  created_at: "",
  updated_at: "",
};

describe("contextGraph", () => {
  it("renders the solution boundary, members inside and external systems outside", () => {
    const graph = contextGraph(design, state);
    expect(graph.boundary.label).toBe("Payments Platform");
    const member = graph.systems.find((system) => system.systemId === "sys-1");
    const external = graph.systems.find((system) => system.systemId === "sys-2");
    expect(member?.external).toBe(false);
    expect(external?.external).toBe(true);
    expect(member?.position).toEqual({ x: 40, y: 70 });
    expect(graph.edges.some((edge) => edge.kind === "member" && edge.target === member?.key)).toBe(true);
    expect(graph.edges.some((edge) => edge.kind === "external" && edge.source === external?.key)).toBe(true);
  });
});

describe("decompositionGraph", () => {
  it("exposes explicit provided and required interfaces per component", () => {
    const graph = decompositionGraph(design, state);
    const api = graph.components.find((item) => item.component.object_id === "comp-1")!;
    expect(api.provided.map((ui) => ui.name)).toEqual(["Payments API"]);
    expect(api.required.map((ui) => ui.name)).toEqual(["Ledger Client"]);
  });

  it("connects a required interface to a provided interface with port handles", () => {
    const graph = decompositionGraph(design, state);
    const connection = graph.edges.find((edge) => edge.kind === "connects_to")!;
    expect(connection.source).toBe("occ-comp-1");
    expect(connection.target).toBe("occ-comp-2");
    expect(connection.sourceHandle).toBe("iface-iface-2");
    expect(connection.targetHandle).toBe("iface-iface-3");
  });

  it("renders repositories where they are used with semantic edges", () => {
    const graph = decompositionGraph(design, state);
    const repository = graph.repositories.find((item) => item.repository.object_id === "repo-1")!;
    expect(repository.usedBy).toEqual(["comp-2"]);
    expect(graph.edges.some((edge) => edge.kind === "uses" && edge.target === repository.key)).toBe(true);
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
