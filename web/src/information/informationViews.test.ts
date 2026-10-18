import { describe, expect, it } from "vitest";

import type { InformationImpactChange, InformationLineage } from "./informationModel";
import {
  assignProjectionLanes,
  filterImpactChanges,
  filterLineage,
  impactObjectTypes,
  layeredLayout,
  lineageNeighborhood,
} from "./informationViews";

const lineage: InformationLineage = {
  state_id: "state-1",
  nodes: [
    { id: "attribute:a1", kind: "information_attribute", name: "Customer.email", detail: "string", system_name: null, catalog_field_id: null, contract_id: null },
    { id: "field:f1", kind: "catalog_field", name: "email", detail: "customer", system_name: "CRM", catalog_field_id: "f1", contract_id: null },
    { id: "contract:c1", kind: "contract", name: "Customer onboarding (direct)", detail: null, system_name: null, catalog_field_id: null, contract_id: "c1" },
    { id: "field:f2", kind: "catalog_field", name: "email_address", detail: "billing_account", system_name: "Billing", catalog_field_id: "f2", contract_id: null },
    { id: "attribute:a2", kind: "information_attribute", name: "Customer.phone", detail: "string", system_name: null, catalog_field_id: null, contract_id: null },
  ],
  edges: [
    { id: "e1", source: "attribute:a1", target: "field:f1", relation: "realized as" },
    { id: "e2", source: "field:f1", target: "contract:c1", relation: "mapped by" },
    { id: "e3", source: "contract:c1", target: "field:f2", relation: "delivered to" },
  ],
  gaps: ["Customer.phone has no physical realization"],
};

const changes: InformationImpactChange[] = [
  { object_type: "entity", object_id: "e1", name: "Customer", entity_object_id: null, entity_name: null, change: "reused", changed_fields: [], reason: null },
  { object_type: "attribute", object_id: "a1", name: "email", entity_object_id: "e1", entity_name: "Customer", change: "added", changed_fields: [], reason: null },
  { object_type: "attribute", object_id: "a2", name: "status", entity_object_id: "e1", entity_name: "Customer", change: "changed", changed_fields: ["data_type"], reason: null },
];

describe("layeredLayout", () => {
  it("places connected nodes in increasing columns", () => {
    const positions = layeredLayout(["a", "b", "c"], [
      { source: "a", target: "b" },
      { source: "b", target: "c" },
    ]);
    expect(positions.get("a")!.x).toBeLessThan(positions.get("b")!.x);
    expect(positions.get("b")!.x).toBeLessThan(positions.get("c")!.x);
  });

  it("ignores edges referencing unknown nodes", () => {
    const positions = layeredLayout(["a"], [{ source: "a", target: "missing" }]);
    expect(positions.get("a")).toEqual({ x: 60, y: 60 });
  });
});

describe("assignProjectionLanes", () => {
  const positions = new Map([
    ["a", { x: 60, y: 60 }],
    ["b", { x: 60, y: 240 }],
    ["c", { x: 500, y: 60 }],
    ["d", { x: 500, y: 240 }],
  ]);

  it("gives connectors sharing a corridor different lanes", () => {
    const lanes = assignProjectionLanes(positions, [
      { id: "e1", source: "a", target: "c" },
      { id: "e2", source: "b", target: "d" },
    ]);
    expect(lanes.get("e1")).toBe(-4.5);
    expect(lanes.get("e2")).toBe(4.5);
  });

  it("keeps a lone connector on the corridor centre and stays deterministic", () => {
    const edges = [
      { id: "e0", source: "b", target: "d" },
      { id: "e1", source: "a", target: "c" },
    ];
    expect(assignProjectionLanes(positions, [edges[1]])).toEqual(new Map([["e1", 0]]));
    expect([...assignProjectionLanes(positions, edges).entries()])
      .toEqual([...assignProjectionLanes(positions, [...edges].reverse()).entries()]);
  });

  it("does not lane connectors that leave from different columns", () => {
    const lanes = assignProjectionLanes(positions, [
      { id: "e1", source: "a", target: "c" },
      { id: "e2", source: "c", target: "d" },
    ]);
    expect(lanes.get("e1")).toBe(0);
    expect(lanes.get("e2")).toBe(0);
  });
});

describe("lineageNeighborhood", () => {
  it("walks downstream proven edges only", () => {
    const downstream = lineageNeighborhood(lineage, "attribute:a1", "downstream");
    expect([...downstream].sort()).toEqual(["attribute:a1", "contract:c1", "field:f1", "field:f2"]);
    const upstream = lineageNeighborhood(lineage, "field:f2", "upstream");
    expect(upstream.has("contract:c1")).toBe(true);
    expect(upstream.has("attribute:a2")).toBe(false);
  });
});

describe("filterLineage", () => {
  it("keeps the connected chain of a matching node", () => {
    const filtered = filterLineage(lineage, "Customer.email");
    expect(filtered.nodes.map((node) => node.id)).toEqual([
      "attribute:a1",
      "field:f1",
      "contract:c1",
      "field:f2",
    ]);
    expect(filtered.edges).toHaveLength(3);
  });

  it("returns the full graph for a blank term", () => {
    expect(filterLineage(lineage, "  ").nodes).toHaveLength(5);
  });

  it("drops unrelated gaps that cannot be reached", () => {
    const filtered = filterLineage(lineage, "Customer.email");
    expect(filtered.gaps).toEqual(lineage.gaps);
  });
});

describe("impact filters", () => {
  it("filters by change type and object type", () => {
    expect(filterImpactChanges(changes, { change: "added" })).toHaveLength(1);
    expect(filterImpactChanges(changes, { objectType: "attribute" })).toHaveLength(2);
    expect(filterImpactChanges(changes, { change: "changed", objectType: "attribute" })).toHaveLength(1);
  });

  it("lists distinct object types", () => {
    expect(impactObjectTypes(changes)).toEqual(["attribute", "entity"]);
  });
});
