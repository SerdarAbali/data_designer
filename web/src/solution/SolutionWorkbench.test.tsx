// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import { WorkbenchNavigationProvider, useWorkbenchNavigation } from "../workbench/WorkbenchNavigation";
import SolutionWorkbench from "./SolutionWorkbench";
import type { SolutionDesign } from "./solutionModel";

vi.mock("@xyflow/react", () => {
  const Handle = () => null;
  const ReactFlow = ({
    nodes,
    edges,
    nodeTypes,
    onNodeClick,
    onNodeDragStop,
  }: {
    nodes: { id: string; type: string; selected?: boolean; data: unknown }[];
    edges: { id: string; data?: { label?: string } }[];
    nodeTypes: Record<string, React.ComponentType<{ id: string; type: string; data: unknown; selected?: boolean }>>;
    onNodeClick?: (event: null, node: unknown) => void;
    onNodeDragStop?: (event: null, node: unknown) => void;
  }) => (
    <div data-testid="react-flow">
      {nodes.map((node) => {
        const Component = nodeTypes[node.type];
        return (
          <div key={node.id} data-testid={`node-${node.id}`}>
            <div onClick={() => onNodeClick?.(null, node)}>
              {Component ? <Component id={node.id} type={node.type} data={node.data} selected={node.selected} /> : null}
            </div>
            <button
              type="button"
              aria-label={`drag ${node.id}`}
              onClick={() => onNodeDragStop?.(null, { ...node, position: { x: 999, y: 888 } })}
            >
              drag
            </button>
          </div>
        );
      })}
      {edges.map((edge) => (
        <div key={edge.id} data-testid={`edge-${edge.id}`}>{edge.data?.label}</div>
      ))}
    </div>
  );
  return {
    ReactFlow,
    Background: () => null,
    Controls: () => null,
    Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    Handle,
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
  nodes: [
    { occurrence_id: "occ-sol", object_id: "sol-1", position: { x: 0, y: 0 } },
    { occurrence_id: "occ-sys-1", object_id: "sys-1", position: { x: 40, y: 70 } },
    { occurrence_id: "occ-sys-2", object_id: "sys-2", position: { x: 40, y: 320 } },
  ],
  relationships: [],
  created_at: "",
  updated_at: "",
};

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
      responsibility: "Expose payment endpoints.",
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
            {
              object_id: "op-2",
              interface_object_id: "iface-1",
              name: "PaymentCreated",
              description: null,
              operation_kind: "event",
              request_object_id: null,
              response_object_id: null,
              ordinal: 1,
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
          operations: [],
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
    { id: "l7", source_object_id: "comp-2", target_object_id: "dep-1", relationship_type: "deployed_on" },
    { id: "l4", source_object_id: "comp-1", target_object_id: "trust-1", relationship_type: "contained_in" },
    { id: "l5", source_object_id: "sys-1", target_object_id: "trust-1", relationship_type: "contained_in" },
    { id: "l6", source_object_id: "iface-1", target_object_id: "trust-1", relationship_type: "crosses" },
  ],
};

const emptyTrace = {
  state_id: "state-1",
  object: {
    id: "comp-1",
    kind: "component",
    name: "Payment API",
    description: null,
    discipline: "solution",
    state_membership: "included",
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

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const url = String(path);
    if (url.includes("/design")) return reply(design);
    if (url.includes("/usages") || url.includes("/trace")) return reply(emptyTrace);
    if (url.includes("/catalog/systems")) {
      return reply([{ id: "sys-1", name: "Core Banking", kind: "service" }]);
    }
    if (url.includes("/solution/solutions") && (!init?.method || init.method === "GET")) {
      return reply([
        { object_id: "sol-1", occurrence_id: "occ-sol", name: "Payments Platform", description: null, component_count: 2, member_count: 1 },
      ]);
    }
    if (url.includes("/solution/")) return reply(design, init?.method === "POST" ? 201 : 200);
    throw new Error(`Unexpected request: ${url}`);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function renderWorkbench(overrides: Partial<Parameters<typeof SolutionWorkbench>[0]> = {}) {
  const mutateActive = vi.fn();
  const utils = render(
    <SolutionWorkbench
      workspaceId="ws-1"
      activeState={candidateState}
      editable
      saveStatus="idle"
      onOpenCatalog={vi.fn()}
      mutateActive={mutateActive}
      {...overrides}
    />,
  );
  return { ...utils, mutateActive };
}

async function openView(name: string) {
  fireEvent.click(await screen.findByRole("button", { name }));
}

describe("SolutionWorkbench", () => {
  it("renders the visual context boundary and member systems", async () => {
    renderWorkbench();
    expect(await screen.findByLabelText("Context view for Payments Platform")).toBeTruthy();
    const memberNode = await screen.findByTestId("node-occ-sys-1");
    expect(within(memberNode).getByText("Core Banking")).toBeTruthy();
    expect(within(screen.getByTestId("node-occ-sys-2")).getByText("Partner Bank")).toBeTruthy();
    expect(screen.getByDisplayValue("Payments Team")).toBeTruthy();
  });

  it("renders components with explicit provided and required interface ports", async () => {
    renderWorkbench();
    await openView("Decomposition");
    const node = await screen.findByTestId("node-occ-comp-1");
    expect(within(node).getByText("Payment API")).toBeTruthy();
    expect(within(node).getByLabelText("provided interface Payments API")).toBeTruthy();
    expect(within(node).getByLabelText("required interface Ledger Client")).toBeTruthy();
  });

  it("persists component layout when a component is dragged", async () => {
    const { mutateActive } = renderWorkbench();
    await openView("Decomposition");
    await screen.findByTestId("node-occ-comp-1");
    fireEvent.click(screen.getByLabelText("drag occ-comp-1"));
    await waitFor(() => expect(mutateActive).toHaveBeenCalled());
    const mutate = mutateActive.mock.calls[0][0] as (state: ArchitectureState) => ArchitectureState;
    const next = mutate({
      ...candidateState,
      nodes: [...candidateState.nodes, { occurrence_id: "occ-comp-1", object_id: "comp-1", position: { x: 100, y: 100 } }],
    });
    expect(next.nodes.find((node) => node.occurrence_id === "occ-comp-1")?.position).toEqual({ x: 999, y: 888 });
  });

  it("renders repository relationships inside the decomposition", async () => {
    renderWorkbench();
    await openView("Decomposition");
    const repository = await screen.findByTestId("node-repo-repo-1");
    expect(within(repository).getByText("Ledger Store")).toBeTruthy();
    expect(screen.getByTestId("edge-uses-comp-2-repo-1").textContent).toContain("uses");
  });

  it("shows deployed components inside their deployment node", async () => {
    renderWorkbench();
    await openView("Deployment");
    const container = await screen.findByLabelText("Deployment node Production Cluster");
    expect(within(container).getByText("Payment API")).toBeTruthy();
    expect(within(container).getByText("Ledger Service")).toBeTruthy();
    expect(within(container).getByText("production")).toBeTruthy();
    expect(within(container).getByText(/Ledger Store/)).toBeTruthy();
  });

  it("shows contained objects and highlights crossing flows in trust boundaries", async () => {
    renderWorkbench();
    await openView("Trust boundaries");
    const container = await screen.findByLabelText("Trust boundary Internal Zone");
    expect(within(container).getAllByText("Payment API").length).toBeGreaterThanOrEqual(1);
    expect(within(container).getByText("Core Banking")).toBeTruthy();
    expect(within(container).getByText("Payments API")).toBeTruthy();
    expect(within(container).getByText("private")).toBeTruthy();
  });

  it("renders ordered messages in the interaction view", async () => {
    renderWorkbench();
    await openView("Interaction");
    const view = await screen.findByLabelText("Interaction view for Payments Platform");
    expect(view.textContent).toContain("Payment API");
    expect(view.textContent).toContain("Payments API");
    expect(view.textContent).toContain("Ledger Client");
    expect(view.textContent).toContain("CreatePayment");
  });

  it("drills down Solution → Component → Interface → Operation keeping canonical ids", async () => {
    renderWorkbench();
    await openView("Decomposition");
    const node = await screen.findByTestId("node-occ-comp-1");
    fireEvent.click(within(node).getByText("Payment API"));
    const componentPanel = await screen.findByRole("complementary", { name: "Component details" });
    expect(within(componentPanel).getByText("comp-1")).toBeTruthy();

    fireEvent.click(within(node).getByLabelText("provided interface Payments API"));
    const interfacePanel = await screen.findByRole("complementary", { name: "Interface details" });
    expect(within(interfacePanel).getByText("iface-1")).toBeTruthy();

    fireEvent.click(within(node).getByRole("button", { name: /CreatePayment/ }));
    const operationPanel = await screen.findByRole("complementary", { name: "Operation details" });
    expect(within(operationPanel).getByText("op-1")).toBeTruthy();

    const breadcrumb = screen.getByRole("navigation", { name: "Solution drill-down" });
    expect(breadcrumb.textContent).toContain("Payment API");
    expect(breadcrumb.textContent).toContain("Payments API");
    expect(breadcrumb.textContent).toContain("CreatePayment");
  });

  it("keeps the current state read-only and does not mutate it", async () => {
    const currentDesign: SolutionDesign = { ...design, state_type: "current", editable: false };
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      const url = String(path);
      if (url.includes("/design")) return reply(currentDesign);
      if (url.includes("/usages") || url.includes("/trace")) return reply(emptyTrace);
      if (url.includes("/catalog/systems")) return reply([]);
      if (url.includes("/solution/solutions")) {
        return reply([
          { object_id: "sol-1", occurrence_id: "occ-sol", name: "Payments Platform", description: null, component_count: 2, member_count: 1 },
        ]);
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const { mutateActive } = renderWorkbench({ editable: false });
    await openView("Decomposition");
    await screen.findByTestId("node-occ-comp-1");
    expect(screen.getByRole("button", { name: "Auto arrange" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText("drag occ-comp-1"));
    fireEvent.click(screen.getByRole("button", { name: "Auto arrange" }));
    expect(mutateActive).not.toHaveBeenCalled();
  });

  it("does not overwrite a saved manual layout on load", async () => {
    const { mutateActive } = renderWorkbench();
    await openView("Decomposition");
    await screen.findByTestId("node-occ-comp-1");
    expect(mutateActive).not.toHaveBeenCalled();
  });

  it("auto arrange recomputes and persists a valid layout", async () => {
    const { mutateActive } = renderWorkbench();
    await openView("Decomposition");
    await screen.findByTestId("node-occ-comp-1");
    fireEvent.click(screen.getByRole("button", { name: "Auto arrange" }));
    await waitFor(() => expect(mutateActive).toHaveBeenCalled());
    const mutate = mutateActive.mock.calls.at(-1)![0] as (state: ArchitectureState) => ArchitectureState;
    const next = mutate({
      ...candidateState,
      nodes: [
        ...candidateState.nodes,
        { occurrence_id: "occ-comp-1", object_id: "comp-1", position: { x: 100, y: 100 } },
        { occurrence_id: "occ-comp-2", object_id: "comp-2", position: { x: 420, y: 100 } },
      ],
    });
    const portal = next.nodes.find((node) => node.occurrence_id === "occ-comp-1")!.position;
    const ledger = next.nodes.find((node) => node.occurrence_id === "occ-comp-2")!.position;
    expect(portal.x).toBeLessThan(ledger.x);
    expect(portal).not.toEqual({ x: 100, y: 100 });
    expect(ledger).not.toEqual({ x: 420, y: 100 });
  });

  it("selects the destination solution object when navigating from traceability", async () => {
    function Navigator() {
      const { requestFocus } = useWorkbenchNavigation();
      return (
        <button
          type="button"
          onClick={() => requestFocus({ id: "comp-1", kind: "component", name: "Payment API", description: null, discipline: "solution", state_membership: "candidate", external: false })}
        >
          go to component
        </button>
      );
    }
    render(
      <WorkbenchNavigationProvider>
        <SolutionWorkbench
          workspaceId="ws-1"
          activeState={candidateState}
          editable
          saveStatus="idle"
          onOpenCatalog={vi.fn()}
        />
        <Navigator />
      </WorkbenchNavigationProvider>,
    );
    await screen.findByLabelText("Context view for Payments Platform");
    fireEvent.click(screen.getByRole("button", { name: "go to component" }));
    const componentPanel = await screen.findByRole("complementary", { name: "Component details" });
    expect(within(componentPanel).getByText("comp-1")).toBeTruthy();
  });
});
