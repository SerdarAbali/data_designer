// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import SolutionWorkbench from "./SolutionWorkbench";
import type { SolutionLandscape } from "./solutionModel";

vi.mock("@xyflow/react", () => {
  const ReactFlow = ({
    nodes,
    edges,
    nodeTypes,
    onNodeClick,
    onNodeDoubleClick,
    onEdgeClick,
    children,
  }: {
    nodes: {
      id: string;
      type: string;
      selected?: boolean;
      position: { x: number; y: number };
      data: unknown;
    }[];
    edges: { id: string; data?: { label?: string } }[];
    nodeTypes: Record<
      string,
      React.ComponentType<{ id: string; type: string; data: unknown; selected?: boolean }>
    >;
    onNodeClick?: (event: null, node: unknown) => void;
    onNodeDoubleClick?: (event: null, node: unknown) => void;
    onEdgeClick?: (event: null, edge: unknown) => void;
    children?: React.ReactNode;
  }) => (
    <div data-testid="react-flow">
      {nodes.map((node) => {
        const Component = nodeTypes[node.type];
        return (
          <div
            key={node.id}
            data-testid={`node-${node.id}`}
            data-position={`${node.position.x},${node.position.y}`}
            onClick={() => onNodeClick?.(null, node)}
            onDoubleClick={() => onNodeDoubleClick?.(null, node)}
          >
            {Component ? (
              <Component id={node.id} type={node.type} data={node.data} selected={node.selected} />
            ) : null}
          </div>
        );
      })}
      {edges.map((edge) => (
        <button
          key={edge.id}
          type="button"
          data-testid={`edge-${edge.id}`}
          onClick={() => onEdgeClick?.(null, edge)}
        >
          {edge.data?.label}
        </button>
      ))}
      {children}
    </div>
  );
  return {
    ReactFlow,
    Background: () => null,
    Controls: () => null,
    Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    Handle: () => null,
    Position: { Top: "top", Right: "right", Bottom: "bottom", Left: "left" },
    MarkerType: { ArrowClosed: "arrow" },
    applyNodeChanges: (_changes: unknown, nodes: unknown) => nodes,
    getBezierPath: () => ["M0 0", 0, 0],
    BaseEdge: () => null,
    EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

const candidateState: ArchitectureState = {
  id: "state-1",
  workspace_id: "ws-1",
  name: "Candidate",
  state_type: "candidate",
  nodes: [{ occurrence_id: "occ-sol", object_id: "sol-1", position: { x: 0, y: 0 } }],
  relationships: [],
  created_at: "",
  updated_at: "",
};

const currentState: ArchitectureState = { ...candidateState, state_type: "current" };

const fact = (value: string | null) => ({
  value,
  canonical: value,
  override: null,
  overridden: false,
});

const landscape: SolutionLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  solutions: [
    {
      solution_object_id: "sol-1",
      occurrence_id: "occ-sol",
      name: "Payments Platform",
      description: null,
      owner: "Payments Team",
      lifecycle_stage: null,
      operational_status: null,
      component_count: 2,
      member_count: 1,
      external_system_count: 0,
      members: [],
      external_systems: [],
      contract_counts: { owned: 1, participating: 0, dependency: 0, total: 1 },
      contracts: [],
      evidence_count: 0,
      relationships_in: 0,
      relationships_out: 1,
    },
    {
      solution_object_id: "sol-2",
      occurrence_id: "occ-sol2",
      name: "Ledger Platform",
      description: null,
      owner: null,
      lifecycle_stage: null,
      operational_status: null,
      component_count: 1,
      member_count: 0,
      external_system_count: 0,
      members: [],
      external_systems: [],
      contract_counts: { owned: 0, participating: 0, dependency: 0, total: 0 },
      contracts: [],
      evidence_count: 0,
      relationships_in: 1,
      relationships_out: 0,
    },
  ],
  relationships: [
    {
      id: "rel-1",
      source_object_id: "sol-1",
      target_object_id: "sol-2",
      relationship_type: "depends_on",
      description: "Payments depends on the ledger.",
      created_in_state_id: "state-1",
      state_applicability: "state",
      state_name: "Candidate",
      evidence_count: 0,
    },
  ],
  warnings: [],
};

const emptyLandscape: SolutionLandscape = { ...landscape, solutions: [], relationships: [] };

const design = {
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
    members: [],
    external_systems: [],
  },
  components: [],
  repositories: [],
  deployment_nodes: [],
  trust_boundaries: [],
  links: [],
};

const emptyTrace = {
  state_id: "state-1",
  object: {
    id: "sol-1",
    kind: "solution_boundary",
    name: "Payments Platform",
    description: null,
    discipline: "solution",
    state_membership: "candidate",
    external: false,
  },
  disciplines: [],
  outgoing: [],
  incoming: [],
  groups: [],
  physical_refs: [],
  tests: [],
  principles: [],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

let landscapeBody: SolutionLandscape = landscape;

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  landscapeBody = landscape;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const url = String(path);
      if (url.includes("/solution/landscape")) return reply(landscapeBody);
      if (url.includes("/design")) return reply(design);
      if (url.includes("/usages") || url.includes("/trace")) return reply(emptyTrace);
      if (url.includes("/catalog/systems")) return reply([]);
      if (url.includes("/solution/solutions")) {
        return reply([
          {
            object_id: "sol-1",
            occurrence_id: "occ-sol",
            name: "Payments Platform",
            description: null,
            component_count: 2,
            member_count: 1,
          },
        ]);
      }
      if (url.includes("/solution/")) return reply(design);
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function renderWorkbench(overrides: Partial<Parameters<typeof SolutionWorkbench>[0]> = {}) {
  return render(
    <SolutionWorkbench
      workspaceId="ws-1"
      activeState={candidateState}
      editable
      saveStatus="idle"
      onOpenCatalog={vi.fn()}
      mutateActive={vi.fn()}
      {...overrides}
    />,
  );
}

async function openLandscape() {
  fireEvent.click(await screen.findByRole("button", { name: "Landscape" }));
  await screen.findByTestId("react-flow");
}

describe("Solution Landscape navigation", () => {
  it("lists Landscape first and keeps the five detailed views navigable", async () => {
    renderWorkbench();
    const nav = await screen.findByRole("navigation", { name: "Solution views" });
    const labels = [...nav.querySelectorAll("button")].map((button) => button.textContent);
    expect(labels).toEqual([
      "Landscape",
      "Context",
      "Decomposition",
      "Deployment",
      "Trust boundaries",
      "Interaction",
    ]);
    await openLandscape();
    fireEvent.click(screen.getByRole("button", { name: "Context" }));
    expect(await screen.findByLabelText("Context view for Payments Platform")).toBeTruthy();
    // Returning to Landscape preserves the selected architecture state.
    fireEvent.click(screen.getByRole("button", { name: "Landscape" }));
    expect(await screen.findByTestId("react-flow")).toBeTruthy();
    expect(screen.getByTestId("node-solution:sol-1")).toBeTruthy();
  });

  it("renders every Solution as a node and every relationship as a typed edge", async () => {
    renderWorkbench();
    await openLandscape();
    expect(screen.getByTestId("node-solution:sol-1")).toBeTruthy();
    expect(screen.getByTestId("node-solution:sol-2")).toBeTruthy();
    const edge = screen.getByTestId("edge-rel-1");
    expect(edge.textContent).toContain("Depends on");
    expect(screen.getByText("2 solutions · 1 relationship")).toBeTruthy();
  });

  it("arranges nodes deterministically", async () => {
    const first = renderWorkbench();
    await openLandscape();
    const before = screen.getByTestId("node-solution:sol-1").getAttribute("data-position");
    first.unmount();
    renderWorkbench();
    await openLandscape();
    const after = screen.getByTestId("node-solution:sol-1").getAttribute("data-position");
    expect(after).toBe(before);
  });

  it("drills into Context when a Solution is opened", async () => {
    renderWorkbench();
    await openLandscape();
    fireEvent.doubleClick(screen.getByTestId("node-solution:sol-1"));
    expect(await screen.findByLabelText("Context view for Payments Platform")).toBeTruthy();
  });

  it("opens a Solution in Context from the inspector action", async () => {
    renderWorkbench();
    await openLandscape();
    fireEvent.click(screen.getByTestId("node-solution:sol-2"));
    fireEvent.click(await screen.findByRole("button", { name: "Open in Context" }));
    expect(await screen.findByLabelText("Context view for Payments Platform")).toBeTruthy();
  });

  it("shows an empty Landscape state when the state has no solutions", async () => {
    landscapeBody = emptyLandscape;
    renderWorkbench();
    await openLandscape();
    expect(screen.getByText("No solutions in this state")).toBeTruthy();
  });

  it("is read-only in Current and editable in Candidate", async () => {
    renderWorkbench();
    await openLandscape();
    fireEvent.click(screen.getByTestId("edge-rel-1"));
    expect(await screen.findByRole("button", { name: "Save relationship" })).toBeTruthy();

    cleanup();
    landscapeBody = { ...landscape, editable: false, state_type: "current" };
    renderWorkbench({ activeState: currentState, editable: false });
    await openLandscape();
    fireEvent.click(screen.getByTestId("edge-rel-1"));
    await screen.findByRole("complementary", { name: "Solution relationship" });
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Save relationship" })).toBeNull(),
    );
    expect(screen.queryByRole("button", { name: "Remove relationship" })).toBeNull();
    expect(screen.getByText(/read-only/)).toBeTruthy();
  });

  it("summarises a node with ownership and contract roles in the inspector", async () => {
    renderWorkbench();
    await openLandscape();
    fireEvent.click(screen.getByTestId("node-solution:sol-1"));
    const panel = await screen.findByRole("complementary", {
      name: "Solution landscape solution",
    });
    expect(panel.textContent).toContain("Payments Team");
    fireEvent.click(screen.getByRole("button", { name: /^Contracts/ }));
    expect(panel.textContent).toContain("1 owned · 0 participating · 0 dependency");
  });
});
