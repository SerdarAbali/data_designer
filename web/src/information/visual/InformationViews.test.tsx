// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  InformationConceptual,
  InformationImpact,
  InformationLineage,
  InformationOwnership,
  InformationPhysical,
} from "../informationModel";
import ConceptualModelView from "./ConceptualModelView";
import InformationImpactView from "./InformationImpactView";
import InformationLineageView from "./InformationLineageView";
import OwnershipAuthorityView from "./OwnershipAuthorityView";
import PhysicalRealizationView from "./PhysicalRealizationView";

vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MarkerType: { ArrowClosed: "arrow" },
  Position: { Top: "top", Right: "right", Bottom: "bottom", Left: "left" },
  Handle: () => null,
  BaseEdge: () => null,
  EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  getBezierPath: () => ["", 0, 0],
  applyNodeChanges: (_changes: unknown, nodes: unknown) => nodes,
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
    children,
  }: {
    nodes: {
      id: string;
      data: {
        label: string;
        kind: string;
        detail?: string | null;
        meta?: string | null;
        gap?: boolean;
      };
    }[];
    edges: { id: string; data?: { relation: string } }[];
    onNodeClick?: (event: unknown, node: unknown) => void;
    children: React.ReactNode;
  }) => (
    <div>
      {nodes.map((node) => (
        <button key={node.id} data-testid={`node-${node.id}`} onClick={() => onNodeClick?.(null, node)}>
          {[
            node.data.label,
            node.data.kind,
            node.data.detail,
            node.data.meta,
            node.data.gap ? "gap" : null,
          ]
            .filter(Boolean)
            .join("|")}
        </button>
      ))}
      {edges.map((edge) => (
        <span key={edge.id} data-testid={`edge-${edge.id}`}>
          {edge.data?.relation}
        </span>
      ))}
      {children}
    </div>
  ),
}));

afterEach(cleanup);

const conceptual: InformationConceptual = {
  state_id: "state-1",
  concepts: [
    { object_id: "ent-1", name: "Customer", description: "Master data", owner: "Customer Ops" },
    { object_id: "ent-2", name: "Consent", description: null, owner: null },
  ],
  relationships: [
    { id: "rel-1", source_object_id: "ent-1", target_object_id: "ent-2", name: "has consent", cardinality: "one_to_many" },
  ],
};

describe("ConceptualModelView", () => {
  it("shows only business concepts, never technical detail", () => {
    render(
      <ConceptualModelView
        conceptual={conceptual}
        stateId="state-1"
        selectedObjectId={null}
        onSelectConcept={vi.fn()}
      />,
    );
    const node = screen.getByTestId("node-ent-1");
    expect(node.textContent).toContain("Customer");
    expect(node.textContent).toContain("Concept");
    expect(node.textContent).toContain("Owner: Customer Ops");
    // No attributes, data types, catalog or realization detail leaks in.
    expect(node.textContent).not.toMatch(/customer_id|catalog|realized|string/i);
    expect(screen.getByText("has consent")).toBeTruthy();
  });

  it("selects a concept for the unified inspector", () => {
    const onSelectConcept = vi.fn();
    render(
      <ConceptualModelView
        conceptual={conceptual}
        stateId="state-1"
        selectedObjectId={null}
        onSelectConcept={onSelectConcept}
      />,
    );
    fireEvent.click(screen.getByTestId("node-ent-2"));
    expect(onSelectConcept).toHaveBeenCalledWith("ent-2");
  });
});

const physical: InformationPhysical = {
  state_id: "state-1",
  summary: { realized: 1, partial: 0, unmapped: 1, invalid: 0 },
  mappings: [
    {
      entity_object_id: "ent-1",
      entity_name: "Customer",
      attribute_object_id: "attr-email",
      attribute_name: "email",
      data_type: "string",
      required: true,
      status: "realized",
      system_id: "sys-1",
      system_name: "CRM",
      catalog_object_id: "obj-1",
      catalog_object_name: "customer",
      catalog_field_id: "field-1",
      catalog_field_name: "email",
      contracts: [{ id: "contract-1", name: "Customer onboarding (direct)", direction: "source" }],
    },
    {
      entity_object_id: "ent-1",
      entity_name: "Customer",
      attribute_object_id: "attr-phone",
      attribute_name: "phone",
      data_type: "string",
      required: false,
      status: "unmapped",
      system_id: null,
      system_name: null,
      catalog_object_id: null,
      catalog_object_name: null,
      catalog_field_id: null,
      catalog_field_name: null,
      contracts: [],
    },
  ],
};

describe("PhysicalRealizationView", () => {
  it("reuses the existing catalog identity and shows status", () => {
    render(
      <PhysicalRealizationView
        physical={physical}
        onSelectAttribute={vi.fn()}
        onOpenCatalog={vi.fn()}
        onOpenContract={vi.fn()}
      />,
    );
    expect(screen.getByText("CRM")).toBeTruthy();
    expect(screen.getByText("customer")).toBeTruthy();
    expect(screen.getByText("email")).toBeTruthy();
    expect(screen.getByText("Realized")).toBeTruthy();
    expect(screen.getByText("Unmapped")).toBeTruthy();
    // Primary names and the relationship status are explicit elements so they
    // can carry the theme foreground tokens rather than inheriting button colour.
    expect(screen.getByText("Customer.email").className).toBe("information-physical-name");
    expect(screen.getByText("Realized").className).toContain("information-physical-status");
    expect(screen.getByText("Contracts")).toBeTruthy();
  });

  it("opens the catalog and the owning contract", () => {
    const onOpenCatalog = vi.fn();
    const onOpenContract = vi.fn();
    render(
      <PhysicalRealizationView
        physical={physical}
        onSelectAttribute={vi.fn()}
        onOpenCatalog={onOpenCatalog}
        onOpenContract={onOpenContract}
      />,
    );
    fireEvent.click(screen.getByText("CRM"));
    expect(onOpenCatalog).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Customer onboarding (direct)"));
    expect(onOpenContract).toHaveBeenCalledWith("contract-1");
  });

  it("opens the attribute inspector for mapping or remapping", () => {
    const onSelectAttribute = vi.fn();
    render(
      <PhysicalRealizationView
        physical={physical}
        onSelectAttribute={onSelectAttribute}
        onOpenCatalog={vi.fn()}
        onOpenContract={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText(/Customer\.email/));
    expect(onSelectAttribute).toHaveBeenCalledWith("ent-1", "attr-email");
  });
});

const ownership: InformationOwnership = {
  state_id: "state-1",
  entries: [
    {
      object_id: "ent-1",
      name: "Customer",
      owner: "Customer Ops",
      steward: "Data Steward",
      authoritative_system_id: "sys-1",
      authoritative_system_name: "CRM",
      authoritative_in_state: true,
      classification: "internal",
      sensitivity: "medium",
      realization_count: 3,
      systems: ["CRM"],
      issues: [],
    },
    {
      object_id: "ent-2",
      name: "Customer Consent",
      owner: null,
      steward: null,
      authoritative_system_id: null,
      authoritative_system_name: null,
      authoritative_in_state: false,
      classification: null,
      sensitivity: "high",
      realization_count: 0,
      systems: [],
      issues: [
        "missing_owner",
        "missing_steward",
        "missing_authoritative_system",
        "sensitive_without_ownership",
      ],
    },
  ],
};

describe("OwnershipAuthorityView", () => {
  it("identifies missing owner, steward and authoritative source", () => {
    render(
      <OwnershipAuthorityView
        ownership={ownership}
        selectedObjectId={null}
        onSelectEntity={vi.fn()}
      />,
    );
    expect(screen.getByText("Missing owner")).toBeTruthy();
    expect(screen.getByText("Missing steward")).toBeTruthy();
    expect(screen.getByText("Missing authoritative system")).toBeTruthy();
    expect(screen.getByText("Sensitive without owner/steward")).toBeTruthy();
    expect(screen.getByText("No gaps")).toBeTruthy();
  });

  it("selects an entity for the unified inspector", () => {
    const onSelectEntity = vi.fn();
    render(
      <OwnershipAuthorityView
        ownership={ownership}
        selectedObjectId={null}
        onSelectEntity={onSelectEntity}
      />,
    );
    fireEvent.click(screen.getByText("Customer Consent"));
    expect(onSelectEntity).toHaveBeenCalledWith("ent-2");
  });
});

const lineage: InformationLineage = {
  state_id: "state-1",
  nodes: [
    { id: "attribute:a1", kind: "information_attribute", name: "Customer.email", detail: "string", system_name: null, catalog_field_id: null, contract_id: null },
    { id: "field:f1", kind: "catalog_field", name: "email", detail: "customer", system_name: "CRM", catalog_field_id: "f1", contract_id: null },
    { id: "contract:c1", kind: "contract", name: "Customer onboarding (direct)", detail: null, system_name: null, catalog_field_id: null, contract_id: "c1" },
    { id: "field:f2", kind: "catalog_field", name: "email_address", detail: "billing_account", system_name: "Billing", catalog_field_id: "f2", contract_id: null },
  ],
  edges: [
    { id: "e1", source: "attribute:a1", target: "field:f1", relation: "realized as" },
    { id: "e2", source: "field:f1", target: "contract:c1", relation: "mapped by" },
    { id: "e3", source: "contract:c1", target: "field:f2", relation: "delivered to" },
  ],
  gaps: [],
};

describe("InformationLineageView", () => {
  it("renders only the proven reference chain with semantic labels", () => {
    render(
      <InformationLineageView
        lineage={lineage}
        selectedNodeId={null}
        onSelectNode={vi.fn()}
        onOpenCatalog={vi.fn()}
      />,
    );
    expect(screen.getByText("realized as")).toBeTruthy();
    expect(screen.getByText("mapped by")).toBeTruthy();
    expect(screen.getByText("delivered to")).toBeTruthy();
    expect(screen.getByTestId("node-field:f2").textContent).toContain("System: Billing");
  });

  it("navigates to the catalog and the contract from the focused node", () => {
    const onOpenCatalog = vi.fn();
    const onOpenContract = vi.fn();
    const { rerender } = render(
      <InformationLineageView
        lineage={lineage}
        selectedNodeId={null}
        onSelectNode={vi.fn()}
        onOpenCatalog={onOpenCatalog}
        onOpenContract={onOpenContract}
      />,
    );
    rerender(
      <InformationLineageView
        lineage={lineage}
        selectedNodeId="field:f1"
        onSelectNode={vi.fn()}
        onOpenCatalog={onOpenCatalog}
        onOpenContract={onOpenContract}
      />,
    );
    fireEvent.click(screen.getByText("Open catalog"));
    expect(onOpenCatalog).toHaveBeenCalled();

    rerender(
      <InformationLineageView
        lineage={lineage}
        selectedNodeId="contract:c1"
        onSelectNode={vi.fn()}
        onOpenCatalog={onOpenCatalog}
        onOpenContract={onOpenContract}
      />,
    );
    fireEvent.click(screen.getByText("Open contract"));
    expect(onOpenContract).toHaveBeenCalledWith("c1");
  });

  it("reports where lineage ends without inventing paths", () => {
    render(
      <InformationLineageView
        lineage={{ ...lineage, gaps: ["Customer.phone has no physical realization"] }}
        selectedNodeId={null}
        onSelectNode={vi.fn()}
        onOpenCatalog={vi.fn()}
      />,
    );
    expect(screen.getByText("Lineage ends")).toBeTruthy();
    expect(screen.getByText("Customer.phone has no physical realization")).toBeTruthy();
  });
});

const impact: InformationImpact = {
  state_id: "state-1",
  baseline_state_id: "state-0",
  supported: true,
  unresolved: [],
  summary: { added: 1, removed: 1, changed: 1, reused: 1 },
  changes: [
    { object_type: "entity", object_id: "ent-1", name: "Customer", entity_object_id: null, entity_name: null, change: "reused", changed_fields: [], reason: null },
    { object_type: "entity", object_id: "ent-2", name: "Customer Consent", entity_object_id: null, entity_name: null, change: "added", changed_fields: [], reason: null },
    { object_type: "attribute", object_id: "attr-1", name: "email", entity_object_id: "ent-1", entity_name: "Customer", change: "added", changed_fields: [], reason: null },
    { object_type: "attribute", object_id: "attr-2", name: "status", entity_object_id: "ent-1", entity_name: "Customer", change: "changed", changed_fields: ["data_type"], reason: "attribute properties changed" },
    { object_type: "attribute", object_id: "attr-3", name: "legacy_code", entity_object_id: "ent-1", entity_name: "Customer", change: "removed", changed_fields: [], reason: null },
  ],
};

describe("InformationImpactView", () => {
  it("groups added, removed, changed and reused items", () => {
    render(
      <InformationImpactView impact={impact} selectedObjectId={null} onSelectChange={vi.fn()} />,
    );
    // The change status appears both as a group heading and a semantic per-item badge.
    for (const label of ["Added", "Removed", "Changed", "Reused"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("data_type")).toBeTruthy();
    const badge = screen.getByText("Changed", { selector: ".information-impact-change" });
    expect(badge.className).toContain("change-changed");
    expect(screen.getByText("Customer.status").className).toBe("information-impact-name");
  });

  it("filters by change type", () => {
    render(
      <InformationImpactView impact={impact} selectedObjectId={null} onSelectChange={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Filter by change type"), { target: { value: "added" } });
    expect(screen.queryByText("legacy_code")).toBeNull();
    expect(screen.getByText("Customer Consent")).toBeTruthy();
  });

  it("opens the inspector for a selected change", () => {
    const onSelectChange = vi.fn();
    render(
      <InformationImpactView impact={impact} selectedObjectId={null} onSelectChange={onSelectChange} />,
    );
    fireEvent.click(screen.getByText(/Customer\.status/));
    expect(onSelectChange).toHaveBeenCalledWith(expect.objectContaining({ object_id: "attr-2" }));
  });

  it("shows an explicit unsupported state instead of fabricating", () => {
    render(
      <InformationImpactView
        impact={{ ...impact, supported: false, changes: [], unresolved: ["No Current baseline state is available for comparison."] }}
        selectedObjectId={null}
        onSelectChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Comparison unavailable")).toBeTruthy();
    expect(screen.getByText("No Current baseline state is available for comparison.")).toBeTruthy();
  });
});
