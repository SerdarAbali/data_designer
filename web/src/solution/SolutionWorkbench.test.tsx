// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import SolutionWorkbench from "./SolutionWorkbench";
import type { SolutionDesign } from "./solutionModel";

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
    external_systems: [],
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
      position: { x: 0, y: 0 },
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
      name: "Payment Worker",
      description: null,
      responsibility: "Settle payments asynchronously.",
      component_type: "service",
      technology: "Go",
      position: { x: 0, y: 0 },
      created_in_state_id: "state-1",
      interfaces: [],
    },
  ],
  repositories: [],
  deployment_nodes: [],
  trust_boundaries: [],
  links: [],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const url = String(path);
    if (url.includes("/design")) return reply(design);
    if (url.includes("/solution/solutions") && init?.method === "POST") {
      return reply(design, 201);
    }
    if (url.includes("/solution/solutions")) {
      return reply([
        { object_id: "sol-1", occurrence_id: "occ-sol", name: "Payments Platform", description: null, component_count: 2, member_count: 1 },
      ]);
    }
    if (url.includes("/catalog/systems")) return reply([]);
    throw new Error(`Unexpected request: ${url}`);
  }));
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
      {...overrides}
    />,
  );
}

describe("SolutionWorkbench", () => {
  it("loads the design and shows the context members", async () => {
    renderWorkbench();
    expect(await screen.findByText("Core Banking")).toBeTruthy();
    expect(screen.getByDisplayValue("Payments Team")).toBeTruthy();
  });

  it("drills from component to interface to operation through the breadcrumb", async () => {
    renderWorkbench();
    await screen.findByText("Core Banking");
    fireEvent.click(screen.getByRole("button", { name: "Decomposition" }));
    fireEvent.click(await screen.findByRole("button", { name: /Payment API/ }));
    expect(await screen.findByRole("complementary", { name: "Component details" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Payments API/ }));
    expect(await screen.findByRole("complementary", { name: "Interface details" })).toBeTruthy();

    fireEvent.click(await screen.findByRole("button", { name: /CreatePayment/ }));
    expect(await screen.findByRole("complementary", { name: "Operation details" })).toBeTruthy();

    const breadcrumb = screen.getByRole("navigation", { name: "Solution drill-down" });
    expect(breadcrumb.textContent).toContain("Payment API");
    expect(breadcrumb.textContent).toContain("Payments API");
    expect(breadcrumb.textContent).toContain("CreatePayment");
  });

  it("separates provided and required interfaces on a component card", async () => {
    renderWorkbench();
    await screen.findByText("Core Banking");
    fireEvent.click(screen.getByRole("button", { name: "Decomposition" }));
    const card = await screen.findByRole("button", { name: /Payment API/ });
    expect(card.textContent).toContain("1 provided");
    expect(card.textContent).toContain("1 required");
  });

  it("renders an interaction view with component lifelines and interface messages", async () => {
    renderWorkbench();
    await screen.findByText("Core Banking");
    fireEvent.click(screen.getByRole("button", { name: "Interaction" }));
    const sequence = await screen.findByLabelText("Interaction view for Payments Platform");
    expect(sequence.textContent).toContain("Payment API");
    expect(sequence.textContent).toContain("Payments API");
    expect(sequence.textContent).toContain("Ledger Client");
  });

  it("disables editing controls when the state is current", async () => {
    renderWorkbench({ editable: false });
    await screen.findByText("Core Banking");
    const newComponent = screen.getByRole("button", { name: "+ New component" });
    expect(newComponent).toHaveProperty("disabled", true);
  });

  it("creates a component through the API", async () => {
    renderWorkbench();
    await screen.findByText("Core Banking");
    fireEvent.click(screen.getByRole("button", { name: "+ New component" }));
    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(
        ([path, init]) => String(path).includes("/components") && init?.method === "POST",
      );
      expect(post).toBeTruthy();
    });
  });
});
