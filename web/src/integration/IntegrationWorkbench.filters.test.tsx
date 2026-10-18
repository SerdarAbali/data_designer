// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import IntegrationWorkbench from "./IntegrationWorkbench";
import type {
  IntegrationContractSummary,
  IntegrationLandscape,
} from "./integrationDesignModel";

vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  Panel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  MarkerType: { ArrowClosed: "arrow" },
  Position: { Top: "top", Right: "right", Bottom: "bottom", Left: "left" },
  Handle: () => null,
  BaseEdge: () => null,
  EdgeLabelRenderer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  getBezierPath: () => ["", 0, 0],
  applyNodeChanges: (_changes: unknown, nodes: unknown) => nodes,
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
  }: {
    nodes: { id: string; data: { label: string } }[];
    edges: { id: string; data?: { relation: string } }[];
    onNodeClick?: (event: unknown, node: unknown) => void;
  }) => (
    <div>
      {nodes.map((node) => (
        <button
          key={node.id}
          data-testid={`node-${node.id}`}
          onClick={() => onNodeClick?.(null, node)}
        >
          {node.data.label}
        </button>
      ))}
      {edges.map((edge) => (
        <span key={edge.id} data-testid={`edge-${edge.id}`}>
          {edge.data?.relation}
        </span>
      ))}
    </div>
  ),
}));

const candidateState: ArchitectureState = {
  id: "state-1",
  workspace_id: "ws-1",
  name: "Candidate",
  state_type: "candidate",
  nodes: [],
  relationships: [],
  created_at: "",
  updated_at: "",
};

const emptyFact = () => ({ value: null, canonical: null, override: null, overridden: false });

function contract(overrides: Partial<IntegrationContractSummary>): IntegrationContractSummary {
  return {
    id: "int-1",
    name: "Contract one",
    description: null,
    interaction_type: "REQUEST_RESPONSE",
    pattern: "request_reply",
    implementation_status: "built",
    revision: 1,
    updated_at: null,
    status: "built",
    source: {
      system_id: "sys-crm",
      system_name: "CRM",
      object_id: "obj-cust",
      object_name: "Customer",
      is_runtime: false,
    },
    target: {
      system_id: "sys-erp",
      system_name: "ERP",
      object_id: "obj-acct",
      object_name: "Account",
      is_runtime: false,
    },
    producer_interface: null,
    consumer_interface: null,
    has_request_graph: false,
    has_response_graph: false,
    has_error_graph: false,
    specification: {},
    target_fields_mapped: 0,
    target_fields_total: 0,
    scenario_count: 0,
    evidence_count: 0,
    referenced_information_objects: [],
    lifecycle_stage: emptyFact(),
    operational_status: emptyFact(),
    environment_scope: emptyFact(),
    ...overrides,
  };
}

const direct = contract({ id: "int-direct", name: "Direct contract" });
const mediated = contract({
  id: "int-mediated",
  name: "Mediated contract",
  mediator: {
    system_id: "sys-frends",
    system_name: "FRENDS",
    is_runtime: true,
    responsibility: "Routes.",
    explicit: true,
  },
  explicit_mediator: true,
  mediated: true,
  mediation_source: "explicit",
});

const landscape: IntegrationLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  contracts: [direct, mediated],
  interfaces: [],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  window.history.replaceState({}, "", "/");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const url = String(path);
      if (url.includes("/integration-design/landscape")) return reply(landscape);
      if (url.includes("/objects/") && url.includes("/usages")) {
        return reply({
          state_id: "state-1",
          object: {
            id: "sys-crm",
            kind: "system",
            name: "CRM",
            description: null,
            discipline: null,
            state_membership: "candidate",
            external: true,
          },
          disciplines: [],
          outgoing: [],
          incoming: [],
          groups: [],
          physical_refs: [],
          tests: [],
          principles: [],
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});

function renderWorkbench() {
  return render(
    <IntegrationWorkbench
      workspaceId="ws-1"
      activeState={candidateState}
      editable
      saveStatus="idle"
    />,
  );
}

async function openFilters() {
  await screen.findByRole("button", { name: /^Filters/ });
  fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
}

describe("Integration Landscape filtering", () => {
  it("renders the whole landscape when every filter is empty", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    expect(screen.getByTestId("node-contract:int-mediated")).toBeTruthy();
    expect(screen.getByTestId("node-system:sys-frends")).toBeTruthy();
    expect(screen.getByText("2 of 2 contracts")).toBeTruthy();
  });

  it("renders only contracts passing every active filter", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    await openFilters();
    fireEvent.click(screen.getByLabelText("Mediated", { selector: "input" }));
    await waitFor(() =>
      expect(screen.queryByTestId("node-contract:int-direct")).toBeNull(),
    );
    expect(screen.getByTestId("node-contract:int-mediated")).toBeTruthy();
    expect(screen.getByText("1 of 2 contracts")).toBeTruthy();
  });

  it("keeps the explicit mediator node while its contract is visible and removes orphans", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-system:sys-frends")).toBeTruthy());
    await openFilters();
    fireEvent.click(screen.getByLabelText("Direct", { selector: "input" }));
    await waitFor(() => expect(screen.queryByTestId("node-contract:int-mediated")).toBeNull());
    // The mediator node was only reachable through the filtered-out contract.
    expect(screen.queryByTestId("node-system:sys-frends")).toBeNull();
    expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy();
  });

  it("clears a selected contract that the filters exclude", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    fireEvent.click(screen.getByTestId("node-contract:int-direct"));
    const picker = (await screen.findByLabelText("Contract")) as HTMLSelectElement;
    await waitFor(() => expect(picker.value).toBe("int-direct"));
    await openFilters();
    fireEvent.click(screen.getByLabelText("Mediated", { selector: "input" }));
    await waitFor(() => expect(picker.value).toBe(""));
  });

  it("restores the graph when the filters are cleared", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    await openFilters();
    fireEvent.click(screen.getByLabelText("Mediated", { selector: "input" }));
    await waitFor(() => expect(screen.queryByTestId("node-contract:int-direct")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    expect(screen.getByTestId("node-contract:int-mediated")).toBeTruthy();
  });

  it("shows the no-match state without treating it as an error", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    await openFilters();
    fireEvent.click(screen.getByLabelText("Legacy endpoint heuristic", { selector: "input" }));
    await waitFor(() =>
      expect(screen.getByText("No contracts match the current filters")).toBeTruthy(),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear all filters" }));
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
  });

  it("shows the no-contracts-in-state state when the state has none", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        if (String(path).includes("/integration-design/landscape")) {
          return reply({ ...landscape, contracts: [] });
        }
        throw new Error(`Unexpected request: ${path}`);
      }),
    );
    renderWorkbench();
    await waitFor(() => expect(screen.getByText("No contracts yet")).toBeTruthy());
  });

  it("reads and restores filter state through the URL", async () => {
    window.history.replaceState({}, "", "/?tab=catalog&il_mediation=mediated");
    renderWorkbench();
    await waitFor(() => expect(screen.getByText("1 of 2 contracts")).toBeTruthy());
    expect(screen.queryByTestId("node-contract:int-direct")).toBeNull();
    expect(screen.getByTestId("node-contract:int-mediated")).toBeTruthy();
    // The unrelated parameter survives.
    expect(window.location.search).toContain("tab=catalog");
    expect(window.location.search).toContain("il_mediation=mediated");
  });

  it("writes the filters back to the URL without dropping unrelated parameters", async () => {
    window.history.replaceState({}, "", "/?tab=catalog");
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    await openFilters();
    fireEvent.click(screen.getByLabelText("Direct", { selector: "input" }));
    await waitFor(() => expect(window.location.search).toContain("il_mediation=direct"));
    expect(window.location.search).toContain("tab=catalog");
  });

  it("removes a filter parameter when the filters are cleared from the URL", async () => {
    window.history.replaceState({}, "", "/?tab=catalog&il_mediation=mediated");
    renderWorkbench();
    await waitFor(() => expect(screen.getByText("1 of 2 contracts")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    await waitFor(() => expect(screen.getByText("2 of 2 contracts")).toBeTruthy());
    expect(window.location.search).toContain("tab=catalog");
    expect(window.location.search).not.toContain("il_mediation");
  });

  it("ignores stale contract ids in the URL instead of erroring", async () => {
    window.history.replaceState({}, "", "/?il_contract=does-not-exist");
    renderWorkbench();
    await waitFor(() =>
      expect(screen.getByText("No contracts match the current filters")).toBeTruthy(),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("never issues a write request while filtering", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-direct")).toBeTruthy());
    await openFilters();
    fireEvent.click(screen.getByLabelText("Direct", { selector: "input" }));
    await waitFor(() => expect(screen.getByText("1 of 2 contracts")).toBeTruthy());
    const writes = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method && (init as RequestInit).method !== "GET");
    expect(writes).toHaveLength(0);
  });
});
