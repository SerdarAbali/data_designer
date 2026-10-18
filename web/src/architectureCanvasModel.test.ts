import { describe, expect, it } from "vitest";
import type { ArchitectureObject, ArchitectureState } from "./architectureTypes";
import {
  addOccurrence,
  isEditableState,
  moveOccurrence,
  removeOccurrence,
  resolveEndpoint,
  resolveOccurrence,
  resolveRelationships,
  solutionBoundaryGeometry,
  projectStateNodes,
  type CanonicalSystem,
} from "./architectureCanvasModel";

function state(overrides: Partial<ArchitectureState> = {}): ArchitectureState {
  return {
    id: "state-1",
    workspace_id: "ws-1",
    name: "Candidate Design",
    state_type: "candidate",
    nodes: [
      { occurrence_id: "occ-a", object_id: "sys-a", position: { x: 0, y: 0 }, candidate_overrides: {} },
      { occurrence_id: "occ-b", object_id: "sys-b", position: { x: 400, y: 0 }, candidate_overrides: {} },
    ],
    relationships: [
      { id: "rel-1", source_id: "occ-a", target_id: "occ-b", type: "Consumes", integration_id: "int-1" },
    ],
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

const systems = new Map<string, CanonicalSystem>([
  ["sys-a", { id: "sys-a", name: "Orders", kind: "service", icon: null, color: null }],
  ["sys-b", { id: "sys-b", name: "Billing", kind: "service", icon: null, color: "#123456" }],
]);

const architectureObjects = new Map<string, ArchitectureObject>([
  ["req-a", {
    id: "req-a",
    kind: "business_requirement",
    name: "Support refunds",
    description: "Refund workflows must be supported.",
  }],
]);

describe("architectureCanvasModel", () => {
  it("resolves canonical properties through object_id and applies candidate overrides only when requested", () => {
    const node = { ...state().nodes[0]!, candidate_overrides: { name: "Orders v2" } };
    expect(resolveOccurrence(node, systems, false).name).toBe("Orders");
    const candidate = resolveOccurrence(node, systems, true);
    expect(candidate.name).toBe("Orders v2");
    expect(candidate.overridden).toBe(true);
    expect(candidate.objectId).toBe("sys-a");
    expect(candidate.occurrenceId).toBe("occ-a");
  });

  it("flags occurrences whose canonical object is unavailable", () => {
    const resolved = resolveOccurrence(
      { occurrence_id: "occ-x", object_id: "gone", position: { x: 0, y: 0 } },
      systems,
      false,
    );
    expect(resolved.missing).toBe(true);
  });

  it("resolves architecture occurrences through canonical architecture object IDs", () => {
    const resolved = resolveOccurrence(
      {
        occurrence_id: "occ-req",
        object_id: "req-a",
        position: { x: 0, y: 0 },
        discipline: "enterprise",
      },
      systems,
      false,
      architectureObjects,
    );
    expect(resolved).toMatchObject({
      objectId: "req-a",
      name: "Support refunds",
      kind: "Business Requirement",
      missing: false,
    });
  });

  it("resolves relationship endpoints by occurrence_id or by object_id", () => {
    const nodes = state().nodes;
    expect(resolveEndpoint(nodes, "occ-b")).toBe("occ-b");
    expect(resolveEndpoint(nodes, "sys-b")).toBe("occ-b");
    expect(resolveEndpoint(nodes, "unknown")).toBeNull();

    const legacy = state({
      relationships: [{ id: "rel-legacy", source_id: "sys-a", target_id: "sys-b", type: "Uses", integration_id: "int-9" }],
    });
    expect(resolveRelationships(legacy)).toEqual([{
      id: "rel-legacy",
      sourceOccurrenceId: "occ-a",
      targetOccurrenceId: "occ-b",
      type: "Uses",
      name: null,
      integrationId: "int-9",
    }]);
  });

  it("projects the same state relationships into only views containing both endpoints", () => {
    const full = state({
      nodes: [
        ...state().nodes,
        {
          occurrence_id: "occ-req",
          object_id: "req-a",
          position: { x: 0, y: 200 },
          discipline: "enterprise",
        },
      ],
      relationships: [
        {
          id: "rel-req-system",
          source_id: "occ-req",
          target_id: "occ-a",
          type: "Impacts",
        },
      ],
    });
    expect(resolveRelationships(full)).toHaveLength(1);
    expect(resolveRelationships(full, full.nodes.filter((node) => !node.discipline))).toEqual([]);
    expect(resolveRelationships(full, full.nodes.filter((node) =>
      !node.discipline || node.discipline === "enterprise"))).toHaveLength(1);
  });

  it("removes an occurrence and its relationships without touching other occurrences", () => {
    const original = state();
    const next = removeOccurrence(original, "occ-b");
    expect(next.nodes.map((node) => node.occurrence_id)).toEqual(["occ-a"]);
    expect(next.relationships).toEqual([]);
    expect(original.nodes).toHaveLength(2);
  });

  it("adds and moves occurrences immutably", () => {
    const original = state();
    const added = addOccurrence(original, "sys-a", { x: 10, y: 20 }, "occ-a2");
    expect(added.nodes.at(-1)).toMatchObject({ occurrence_id: "occ-a2", object_id: "sys-a" });
    const moved = moveOccurrence(added, "occ-a", { x: 99, y: 88 });
    expect(moved.nodes[0]!.position).toEqual({ x: 99, y: 88 });
    expect(original.nodes[0]!.position).toEqual({ x: 0, y: 0 });
  });

  it("follows the baseline lifecycle for a Current state", () => {
    // A Current state without a recorded status fails closed, like the server.
    expect(isEditableState(state({ state_type: "current" }))).toBe(false);
    expect(isEditableState(state({ state_type: "current", baseline_status: "locked" }))).toBe(false);
    expect(isEditableState(state({ state_type: "current", baseline_status: "draft" }))).toBe(true);
    expect(isEditableState(state())).toBe(true);
    expect(isEditableState(null)).toBe(false);
  });

  it("renders Contains members inside a derived boundary without mutating persisted positions", () => {
    const objects = new Map<string, ArchitectureObject>([["boundary", {
      id: "boundary", name: "Payments", kind: "solution_boundary",
    }]]);
    const original = state({
      nodes: [...state().nodes, {
        occurrence_id: "occ-boundary", object_id: "boundary", position: { x: 900, y: 500 },
      }],
      relationships: [{
        id: "contains-a", source_id: "boundary", target_id: "sys-a", type: "Contains",
      }],
    });

    const snapshot = JSON.stringify(original);
    const box = solutionBoundaryGeometry(original, objects).get("occ-boundary")!;
    expect(box.memberIds).toEqual(["occ-a"]);
    expect(box.position.x).toBeLessThan(original.nodes[0]!.position.x);
    expect(box.position.y).toBeLessThan(original.nodes[0]!.position.y);
    expect(box.position.x + box.width).toBeGreaterThan(original.nodes[0]!.position.x + 220);
    expect(box.position.y + box.height).toBeGreaterThan(original.nodes[0]!.position.y + 90);
    expect(JSON.stringify(original)).toBe(snapshot);
  });

  it("shares an interface occurrence between Solution and Integration without copying it", () => {
    const object: ArchitectureObject = { id: "api", kind: "interface", name: "Customer API" };
    const full = state({ nodes: [
      state().nodes[0]!,
      { occurrence_id: "occ-api", object_id: "api", position: { x: 10, y: 20 }, discipline: "solution" },
    ] });
    const objects = new Map([[object.id, object]]);
    expect(projectStateNodes(full, "solution", objects)).toEqual(full.nodes);
    expect(projectStateNodes(full, "integration", objects)).toEqual(full.nodes);
    expect(projectStateNodes(full, "enterprise", objects)).toEqual([full.nodes[0]]);
  });

  it("honors explicit parents and existing dimensions without duplicate membership", () => {
    const objects = new Map<string, ArchitectureObject>(["a", "b"].map((id) => [id, {
      id, name: id, kind: "solution_boundary",
    }]));
    const full = state({
      nodes: [
        { ...state().nodes[0]!, parent_occurrence_id: "boundary-b" },
        { occurrence_id: "boundary-a", object_id: "a", position: { x: 0, y: 0 }, width: 600, height: 350 },
        { occurrence_id: "boundary-b", object_id: "b", position: { x: 0, y: 0 } },
      ],
      relationships: [{ id: "rel", source_id: "a", target_id: "sys-a", type: "Contains" }],
    });
    const boxes = solutionBoundaryGeometry(full, objects);
    expect(boxes.get("boundary-a")).toMatchObject({ width: 600, height: 350, memberIds: [] });
    expect(boxes.get("boundary-b")?.memberIds).toEqual(["occ-a"]);
  });

  it("bounds nested containers and safely handles cyclic containment and missing endpoints", () => {
    const objects = new Map<string, ArchitectureObject>(["outer", "inner"].map((id) => [id, {
      id, name: id, kind: "solution_boundary",
    }]));
    const full = state({
      nodes: [
        state().nodes[0]!,
        { occurrence_id: "outer", object_id: "outer", position: { x: 0, y: 0 } },
        { occurrence_id: "inner", object_id: "inner", position: { x: 0, y: 0 } },
      ],
      relationships: [
        { id: "a", source_id: "outer", target_id: "inner", type: "Contains" },
        { id: "b", source_id: "inner", target_id: "sys-a", type: "Contains" },
        { id: "c", source_id: "inner", target_id: "outer", type: "Contains" },
        { id: "d", source_id: "outer", target_id: "missing", type: "Contains" },
      ],
    });
    const boxes = solutionBoundaryGeometry(full, objects);
    expect(boxes.get("outer")?.memberIds).toEqual(["inner", "occ-a"]);
    expect(boxes.get("inner")?.memberIds).not.toContain("outer");
    expect(boxes.get("outer")!.position.x).toBeLessThan(boxes.get("inner")!.position.x);
  });
});
