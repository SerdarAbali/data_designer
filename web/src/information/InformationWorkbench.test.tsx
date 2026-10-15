// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import InformationWorkbench from "./InformationWorkbench";
import type { InformationModel } from "./informationModel";

vi.mock("@xyflow/react", () => ({
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => children,
  Background: () => null,
  Controls: ({ children }: { children: React.ReactNode }) => children,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MarkerType: { ArrowClosed: "arrow" },
  Position: { Left: "left", Right: "right" },
  Handle: () => null,
  BaseEdge: () => null,
  EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  getSmoothStepPath: () => ["", 0, 0],
  applyNodeChanges: (_changes: unknown, nodes: unknown) => nodes,
  ReactFlow: ({
    nodes,
    onNodeClick,
    children,
  }: {
    nodes: { id: string; data: { entity: { name: string } } }[];
    onNodeClick: (event: null, node: unknown) => void;
    children: React.ReactNode;
  }) => (
    <div>
      {nodes.map((node) => (
        <button key={node.id} onClick={() => onNodeClick(null, node)}>
          {node.data.entity.name}
        </button>
      ))}
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
  ],
  relationships: [],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const url = String(path);
    if (url.includes("/information/model")) return reply(model);
    if (url.includes("/information/entities") && init?.method === "POST") {
      return reply(
        {
          entity: { ...model.entities[0], object_id: "ent-2", occurrence_id: "occ-2", name: "New entity", attributes: [] },
          state: activeState,
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

  it("opens the entity inspector and attribute inspector", async () => {
    render(<InformationWorkbench {...baseProps} />);
    fireEvent.click(await screen.findByRole("button", { name: "Customer" }));
    expect(screen.getByRole("complementary", { name: "Entity details" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /customer_id/ }));
    expect(screen.getByRole("complementary", { name: "Attribute details" })).toBeTruthy();
    expect(await screen.findByText("Catalog realization")).toBeTruthy();
  });
});
