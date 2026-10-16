// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import InformationWorkbench from "./InformationWorkbench";
import type { InformationModel } from "./informationModel";

type MockFlowNode = {
  id: string;
  data: {
    entity?: { name: string };
    label?: string;
    kind?: string;
    detail?: string | null;
    meta?: string | null;
    gap?: boolean;
  };
};

vi.mock("@xyflow/react", () => ({
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => children,
  Background: () => null,
  Controls: ({ children }: { children: React.ReactNode }) => children,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MarkerType: { ArrowClosed: "arrow" },
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
  Handle: () => null,
  BaseEdge: () => null,
  EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  getSmoothStepPath: () => ["", 0, 0],
  getBezierPath: () => ["", 0, 0],
  applyNodeChanges: (_changes: unknown, nodes: unknown) => nodes,
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
    onConnect,
    children,
  }: {
    nodes: MockFlowNode[];
    edges?: { id: string; data?: { relation: string } }[];
    onNodeClick?: (event: null, node: unknown) => void;
    onConnect?: (connection: {
      source: string;
      target: string;
      sourceHandle: string | null;
      targetHandle: string | null;
    }) => void;
    children: React.ReactNode;
  }) => (
    <div>
      {nodes.map((node) => (
        <button
          key={node.id}
          data-testid={`flow-node-${node.id}`}
          onClick={() => onNodeClick?.(null, node)}
        >
          {node.data.entity?.name ?? node.data.label ?? node.id}
        </button>
      ))}
      {(edges ?? []).map((edge) => (
        <span key={edge.id} data-testid={`flow-edge-${edge.id}`}>
          {edge.data?.relation}
        </span>
      ))}
      <button
        onClick={() =>
          onConnect?.({
            source: nodes[0]?.id ?? "",
            target: nodes[1]?.id ?? "",
            sourceHandle: "s-top",
            targetHandle: "t-top",
          })
        }
      >
        manual-connect
      </button>
      {children}
    </div>
  ),
}));

const activeState: ArchitectureState = {
  id: "candidate-a",
  workspace_id: "ws-a",
  name: "Candidate",
  state_type: "candidate",
  nodes: [],
  relationships: [],
  created_at: "",
  updated_at: "",
};

const model: InformationModel = {
  state_id: "candidate-a",
  state_type: "candidate",
  editable: true,
  entities: [
    {
      object_id: "ent-1",
      occurrence_id: "occ-1",
      name: "Customer",
      description: null,
      owner: null,
      steward: null,
      authoritative_system_id: null,
      authoritative_system_name: null,
      classification: null,
      sensitivity: null,
      external_identifier: null,
      position: { x: 0, y: 0 },
      attributes: [
        {
          object_id: "attr-1",
          entity_object_id: "ent-1",
          name: "customer_id",
          data_type: "uuid",
          required: true,
          nullable: false,
          is_key: false,
          is_identifier: true,
          ordinal: 0,
          definition: null,
          created_in_state_id: "candidate-a",
          realization: null,
        },
      ],
    },
    {
      object_id: "ent-2",
      occurrence_id: "occ-2",
      name: "Order",
      description: null,
      owner: null,
      steward: null,
      authoritative_system_id: null,
      authoritative_system_name: null,
      classification: null,
      sensitivity: null,
      external_identifier: null,
      position: { x: 320, y: 0 },
      attributes: [],
    },
  ],
  relationships: [],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const conceptual = {
  state_id: "candidate-a",
  concepts: [
    { object_id: "ent-1", name: "Customer", description: "Master data", owner: "Customer Ops" },
    { object_id: "ent-2", name: "Order", description: null, owner: null },
  ],
  relationships: [
    {
      id: "rel-1",
      source_object_id: "ent-1",
      target_object_id: "ent-2",
      name: "places",
      cardinality: "one_to_many",
    },
  ],
};

const physical = {
  state_id: "candidate-a",
  summary: { realized: 1, partial: 0, unmapped: 0, invalid: 0 },
  mappings: [
    {
      entity_object_id: "ent-1",
      entity_name: "Customer",
      attribute_object_id: "attr-1",
      attribute_name: "customer_id",
      data_type: "uuid",
      required: true,
      status: "realized",
      system_id: "sys-1",
      system_name: "CRM",
      catalog_object_id: "obj-1",
      catalog_object_name: "customer",
      catalog_field_id: "field-1",
      catalog_field_name: "customer_id",
      contracts: [
        { id: "contract-1", name: "Customer onboarding (direct)", direction: "source" },
      ],
    },
  ],
};

const ownership = {
  state_id: "candidate-a",
  entries: [
    {
      object_id: "ent-1",
      name: "Customer",
      owner: null,
      steward: null,
      authoritative_system_id: null,
      authoritative_system_name: null,
      authoritative_in_state: false,
      classification: null,
      sensitivity: "high",
      realization_count: 1,
      systems: ["CRM"],
      issues: ["missing_owner", "missing_steward", "sensitive_without_ownership"],
    },
  ],
};

const lineage = {
  state_id: "candidate-a",
  nodes: [
    {
      id: "attribute:attr-1",
      kind: "information_attribute",
      name: "Customer.customer_id",
      detail: "uuid",
      system_name: null,
      catalog_field_id: null,
      contract_id: null,
    },
    {
      id: "field:field-1",
      kind: "catalog_field",
      name: "customer_id",
      detail: "customer",
      system_name: "CRM",
      catalog_field_id: "field-1",
      contract_id: null,
    },
    {
      id: "contract:contract-1",
      kind: "contract",
      name: "Customer onboarding (direct)",
      detail: null,
      system_name: null,
      catalog_field_id: null,
      contract_id: "contract-1",
    },
  ],
  edges: [
    { id: "e1", source: "attribute:attr-1", target: "field:field-1", relation: "realized as" },
    { id: "e2", source: "field:field-1", target: "contract:contract-1", relation: "mapped by" },
  ],
  gaps: [],
};

const impact = {
  state_id: "candidate-a",
  baseline_state_id: null,
  supported: true,
  unresolved: [],
  summary: { added: 1, removed: 0, changed: 0, reused: 1 },
  changes: [
    {
      object_type: "entity",
      object_id: "ent-1",
      name: "Customer",
      entity_object_id: null,
      entity_name: null,
      change: "reused",
      changed_fields: [],
      reason: null,
    },
    {
      object_type: "attribute",
      object_id: "attr-2",
      name: "email",
      entity_object_id: "ent-1",
      entity_name: "Customer",
      change: "added",
      changed_fields: [],
      reason: null,
    },
  ],
};

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const url = String(path);
    if (url.includes("/information/model")) return reply(model);
    if (url.includes("/information/conceptual")) return reply(conceptual);
    if (url.includes("/information/physical")) return reply(physical);
    if (url.includes("/information/ownership")) return reply(ownership);
    if (url.includes("/information/lineage")) return reply(lineage);
    if (url.includes("/information/impact")) return reply(impact);
    if (url.includes("/information/entities") && init?.method === "POST") {
      return reply(
        {
          entity: { ...model.entities[0], object_id: "ent-2", occurrence_id: "occ-2", name: "New entity", attributes: [] },
          state: activeState,
        },
        201,
      );
    }
    if (url.includes("/information/relationships") && init?.method === "POST") {
      return reply(
        {
          id: "rel-1",
          source_object_id: "ent-1",
          target_object_id: "ent-2",
          name: null,
          cardinality: "one_to_many",
          source_optional: false,
          target_optional: true,
          source_handle: "s-top",
          target_handle: "t-top",
        },
        201,
      );
    }
    if (url.includes("/catalog/")) return reply([]);
    throw new Error(`Unexpected request: ${url}`);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const baseProps = {
  workspaceId: "ws-a",
  activeState,
  editable: true,
  saveStatus: "idle" as const,
  onAdoptState: vi.fn(),
  mutateActive: vi.fn(),
  onOpenCatalog: vi.fn(),
};

describe("InformationWorkbench", () => {
  it("renders entities from the model", async () => {
    render(<InformationWorkbench {...baseProps} />);
    expect(await screen.findByRole("button", { name: "Customer" })).toBeTruthy();
  });

  it("creates an entity and adopts the returned state", async () => {
    const onAdoptState = vi.fn();
    render(<InformationWorkbench {...baseProps} onAdoptState={onAdoptState} />);
    await screen.findByRole("button", { name: "Customer" });
    fireEvent.click(screen.getByRole("button", { name: "+ New entity" }));
    await waitFor(() => expect(onAdoptState).toHaveBeenCalledWith(activeState));
    const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "POST");
    expect(post).toBeTruthy();
    expect(String(post?.[0])).toContain("/information/entities");
  });

  it("preserves the manually selected handles when creating a relationship", async () => {
    render(<InformationWorkbench {...baseProps} />);
    await screen.findByRole("button", { name: "Customer" });
    fireEvent.click(screen.getByRole("button", { name: "manual-connect" }));
    await waitFor(() => {
      const post = vi
        .mocked(fetch)
        .mock.calls.find(
          ([path, init]) => String(path).includes("/information/relationships") && init?.method === "POST",
        );
      expect(post).toBeTruthy();
      const body = String(post?.[1]?.body);
      expect(body).toContain('"source_handle":"s-top"');
      expect(body).toContain('"target_handle":"t-top"');
    });
  });

  it("opens the entity inspector and attribute inspector", async () => {
    render(<InformationWorkbench {...baseProps} />);
    fireEvent.click(await screen.findByRole("button", { name: "Customer" }));
    expect(screen.getByRole("complementary", { name: "Entity details" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /customer_id/ }));
    expect(screen.getByRole("complementary", { name: "Attribute details" })).toBeTruthy();
    expect(await screen.findByText("Catalog realization")).toBeTruthy();
  });

  it("defaults to the Logical Model and keeps the ER editor", async () => {
    render(<InformationWorkbench {...baseProps} />);
    expect(await screen.findByRole("button", { name: "Customer" })).toBeTruthy();
    const logical = screen.getByRole("button", { name: "Logical Model" });
    expect(logical.getAttribute("aria-current")).toBe("page");
    expect(screen.getByLabelText("Filter attributes")).toBeTruthy();
  });

  it("switches to the physical realization view and loads its projection", async () => {
    render(<InformationWorkbench {...baseProps} />);
    fireEvent.click(await screen.findByRole("button", { name: "Physical Realization" }));
    expect(await screen.findByText("CRM", { selector: ".information-physical-system" })).toBeTruthy();
    expect(screen.getByText("customer_id", { selector: ".information-physical-field" })).toBeTruthy();
    const request = vi
      .mocked(fetch)
      .mock.calls.find(([path]) => String(path).includes("/information/physical"));
    expect(request).toBeTruthy();
  });

  it("renders the conceptual, ownership and impact projections", async () => {
    render(<InformationWorkbench {...baseProps} />);
    fireEvent.click(await screen.findByRole("button", { name: "Conceptual Model" }));
    expect(await screen.findByTestId("flow-node-ent-1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ownership & Authority" }));
    expect(await screen.findByText("Missing owner")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Current vs Candidate Impact" }));
    expect((await screen.findAllByText("Reused")).length).toBeGreaterThan(0);
  });

  it("navigates from lineage into the catalog and a contract", async () => {
    const onNavigateTrace = vi.fn();
    render(<InformationWorkbench {...baseProps} onNavigateTrace={onNavigateTrace} />);
    fireEvent.click(await screen.findByRole("button", { name: "Information Lineage" }));
    fireEvent.click(await screen.findByTestId("flow-node-field:field-1"));
    const focus = screen.getByRole("group", { name: "Lineage focus" });
    fireEvent.click(within(focus).getByRole("button", { name: "Open catalog" }));
    expect(baseProps.onOpenCatalog).toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("flow-node-contract:contract-1"));
    fireEvent.click(within(focus).getByRole("button", { name: "Open contract" }));
    expect(onNavigateTrace).toHaveBeenCalledWith(
      expect.objectContaining({ id: "contract-1", discipline: "integration" }),
    );
  });
});
