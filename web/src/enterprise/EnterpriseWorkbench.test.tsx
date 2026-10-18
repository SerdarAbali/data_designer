// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import EnterpriseWorkbench from "./EnterpriseWorkbench";
import type {
  ApplicationSupport,
  CapabilityMap,
  EnterpriseImpact,
  EnterpriseModel,
  ProcessImpact,
  StrategyTrace,
} from "./enterpriseModel";

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
    { occurrence_id: "occ-goal", object_id: "goal-1", position: { x: 80, y: 60 } },
    { occurrence_id: "occ-req", object_id: "req-1", position: { x: 80, y: 260 } },
    { occurrence_id: "occ-cap", object_id: "cap-1", position: { x: 420, y: 60 } },
    { occurrence_id: "occ-proc", object_id: "proc-1", position: { x: 420, y: 260 } },
  ],
  relationships: [],
  created_at: "",
  updated_at: "",
};

const goal = {
  object_id: "goal-1", kind: "goal" as const, name: "Grow revenue", description: "Grow recurring revenue.",
  owner: "CFO", outcome_metric: "+10% ARR", horizon: "FY27", process_type: null, principle_type: null,
  rationale: null, role_type: null, created_in_state_id: "state-1",
};
const requirement = { ...goal, object_id: "req-1", kind: "requirement" as const, name: "Real-time payments", owner: null, outcome_metric: null, horizon: null };
const capability = { ...goal, object_id: "cap-1", kind: "capability" as const, name: "Payment processing", owner: null, outcome_metric: null, horizon: null };
const processObject = { ...goal, object_id: "proc-1", kind: "process" as const, name: "Card settlement", owner: "Payments Ops", outcome_metric: null, horizon: null, process_type: "process" };
const principle = { ...goal, object_id: "prin-1", kind: "principle" as const, name: "Data residency", owner: null, outcome_metric: null, horizon: null, principle_type: "constraint", rationale: "Regulated workloads stay in-region." };
const role = { ...goal, object_id: "role-1", kind: "role" as const, name: "Payments Team", owner: null, outcome_metric: null, horizon: null, role_type: "role" };

const application = { object_id: "sys-1", name: "Core Banking", kind: "system" };

const model: EnterpriseModel = {
  state_id: "state-1", state_type: "candidate", editable: true,
  goals: [goal], requirements: [requirement], capabilities: [capability], processes: [processObject],
  principles: [principle], roles: [role], applications: [application],
  links: [
    { id: "link-1", source_object_id: "goal-1", target_object_id: "req-1", relationship_type: "drives" },
    { id: "link-2", source_object_id: "req-1", target_object_id: "cap-1", relationship_type: "needs" },
    { id: "link-3", source_object_id: "cap-1", target_object_id: "proc-1", relationship_type: "has_process" },
    { id: "link-4", source_object_id: "sys-1", target_object_id: "cap-1", relationship_type: "supports" },
  ],
};

const capabilityMap: CapabilityMap = {
  state_id: "state-1",
  capabilities: [
    { capability, processes: [processObject], applications: [application], principles: [principle], owner_role: role },
  ],
};

const processImpact: ProcessImpact = {
  state_id: "state-1",
  processes: [
    { process: processObject, capabilities: [capability], applications: [application], requirements: [requirement], governed_by: [principle], impacted: true },
  ],
};

const strategyTrace: StrategyTrace = {
  state_id: "state-1",
  chains: [
    {
      goal,
      steps: [{ requirement, capabilities: [capability], processes: [processObject], applications: [application] }],
      gaps: [],
    },
  ],
  unlinked_requirements: [],
  gaps: [],
};

const applicationSupport: ApplicationSupport = {
  state_id: "state-1",
  applications: [
    { application, capabilities: [capability], processes: [processObject], requirements: [requirement] },
  ],
};

const impact: EnterpriseImpact = {
  state_id: "state-1", baseline_state_id: "state-current",
  changes: [
    { object_id: "goal-1", kind: "goal", name: "Grow revenue", change: "added" },
    { object_id: "cap-1", kind: "capability", name: "Payment processing", change: "reused" },
  ],
  affected_applications: [application], affected_capabilities: [capability], affected_processes: [],
  unresolved_dependencies: [], unresolved_constraints: ["Constraint 'Data residency' governs no object"], risks: [], gaps: [],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      if (url.includes("/enterprise/capability-map")) return reply(capabilityMap);
      if (url.includes("/enterprise/process-impact")) return reply(processImpact);
      if (url.includes("/enterprise/strategy-trace")) return reply(strategyTrace);
      if (url.includes("/enterprise/application-support")) return reply(applicationSupport);
      if (url.includes("/enterprise/impact")) return reply(impact);
      if (url.includes("/enterprise/objects") && init?.method === "POST") return reply(model, 201);
      if (url.includes("/enterprise/links")) return reply(model, 201);
      if (url.includes("/enterprise/model")) return reply(model);
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function renderWorkbench(overrides: Partial<Parameters<typeof EnterpriseWorkbench>[0]> = {}) {
  const mutateActive = vi.fn();
  const utils = render(
    <EnterpriseWorkbench
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

describe("EnterpriseWorkbench", () => {
  it("defaults to the strategy trace and renders the stored chain", async () => {
    renderWorkbench();
    expect(await screen.findByText("Grow revenue")).toBeTruthy();
    expect(screen.getByText("Real-time payments")).toBeTruthy();
    expect(screen.getByText("Payment processing")).toBeTruthy();
    expect(screen.getByText("Card settlement")).toBeTruthy();
    expect(screen.getByText("Core Banking")).toBeTruthy();
    expect(screen.getByTestId("edge-link-1").textContent).toBe("drives");
    expect(screen.getByTestId("edge-link-4").textContent).toBe("supports");
  });

  it("selects an object and opens the unified inspector", async () => {
    renderWorkbench();
    fireEvent.click(await screen.findByText("Grow revenue"));
    const panel = await screen.findByRole("complementary", { name: "Enterprise object details" });
    expect(panel.textContent).toContain("drives");
  });

  it("navigates to the destination discipline when an application is selected", async () => {
    const onNavigateTrace = vi.fn();
    renderWorkbench({ onNavigateTrace });
    fireEvent.click(await screen.findByText("Core Banking"));
    await waitFor(() => expect(onNavigateTrace).toHaveBeenCalled());
    const node = onNavigateTrace.mock.calls[0][0] as { id: string; kind: string };
    expect(node.id).toBe("sys-1");
    expect(node.kind).toBe("system");
  });

  it("shows trace gaps without fabricating edges", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        const url = String(path);
        if (url.includes("/enterprise/strategy-trace")) {
          return reply({
            ...strategyTrace,
            gaps: ["Process 'Card settlement' has no supporting system"],
          });
        }
        if (url.includes("/enterprise/model")) return reply(model);
        if (url.includes("/enterprise/impact")) return reply(impact);
        if (url.includes("/enterprise/capability-map")) return reply(capabilityMap);
        if (url.includes("/enterprise/process-impact")) return reply(processImpact);
        if (url.includes("/enterprise/application-support")) return reply(applicationSupport);
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    renderWorkbench();
    expect(await screen.findByText("Process 'Card settlement' has no supporting system")).toBeTruthy();
  });

  it("renders the capability map grouped by owner role", async () => {
    renderWorkbench();
    await openView("Capability Map");
    expect(await screen.findByText("Payments Team")).toBeTruthy();
    expect(screen.getByText("Payment processing")).toBeTruthy();
  });

  it("renders the process flow with connected objects and the no-steps note", async () => {
    renderWorkbench();
    await openView("Process Impact");
    expect(await screen.findByText("Payment processing")).toBeTruthy();
    expect(screen.getByText("Core Banking")).toBeTruthy();
    expect(screen.getByText(/Ordered process steps are not modeled/)).toBeTruthy();
  });

  it("toggles the application support graph and matrix", async () => {
    renderWorkbench();
    await openView("Application Support");
    expect(await screen.findByText("Core Banking")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Matrix" }));
    expect(await screen.findByRole("table")).toBeTruthy();
  });

  it("auto arrange persists a layered layout", async () => {
    const { mutateActive } = renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Auto arrange" }));
    await waitFor(() => expect(mutateActive).toHaveBeenCalled());
    const mutate = mutateActive.mock.calls.at(-1)![0] as (state: ArchitectureState) => ArchitectureState;
    const next = mutate({ ...candidateState });
    const reqNode = next.nodes.find((node) => node.occurrence_id === "occ-req")!;
    expect(reqNode.position.x).toBe(400);
    expect(reqNode.display_metadata?.enterprise_manual).toBe(true);
  });

  it("does not overwrite a saved manual layout on load", async () => {
    const manualState: ArchitectureState = {
      ...candidateState,
      nodes: candidateState.nodes.map((node) => ({
        ...node,
        display_metadata: { enterprise_manual: true },
      })),
    };
    const { mutateActive } = renderWorkbench({ activeState: manualState });
    await screen.findByText("Grow revenue");
    expect(mutateActive).not.toHaveBeenCalled();
  });

  it("creates an enterprise object through the API", async () => {
    renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.click(screen.getByRole("button", { name: "+ New object" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Reduce risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(
        ([path, init]) => String(path).includes("/enterprise/objects") && init?.method === "POST",
      );
      expect(post).toBeTruthy();
      expect(String(post?.[1]?.body)).toContain("Reduce risk");
    });
  });

  it("keeps the current state read-only", async () => {
    renderWorkbench({ editable: false });
    await screen.findByText("Grow revenue");
    expect(screen.getByRole("button", { name: "+ New object" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("button", { name: "Auto arrange" })).toHaveProperty("disabled", true);
  });
});
