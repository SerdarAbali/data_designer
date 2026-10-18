// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import IntegrationWorkbench from "./IntegrationWorkbench";
import type {
  IntegrationConformance,
  IntegrationContractDetail,
  IntegrationContractSummary,
  IntegrationFlowPhase,
  IntegrationLandscape,
  IntegrationMessageFlow,
  IntegrationSequence,
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
    onNodeDoubleClick,
    children,
  }: {
    nodes: {
      id: string;
      data: {
        label: string;
        kind: string;
        detail?: string | null;
        meta?: string | null;
        badge?: string | null;
        mediated?: boolean;
      };
    }[];
    edges: { id: string; data?: { relation: string } }[];
    onNodeClick?: (event: unknown, node: unknown) => void;
    onNodeDoubleClick?: (event: unknown, node: unknown) => void;
    children: ReactNode;
  }) => (
    <div>
      {nodes.map((node) => (
        <button
          key={node.id}
          data-testid={`node-${node.id}`}
          onClick={() => onNodeClick?.(null, node)}
          onDoubleClick={() => onNodeDoubleClick?.(null, node)}
        >
          {[
            node.data.label,
            node.data.kind,
            node.data.detail,
            node.data.meta,
            node.data.badge,
            node.data.mediated ? "mediated" : null,
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

const contract: IntegrationContractSummary = {
  id: "int-1",
  name: "Customer push",
  description: "Push customer changes.",
  interaction_type: "REQUEST_RESPONSE",
  pattern: "request_reply",
  implementation_status: "built",
  revision: 2,
  updated_at: null,
  status: "built",
  source: {
    system_id: "sys-crm",
    system_name: "CRM",
    object_id: "obj-cust",
    object_name: "Customer",
    system_kind: "application",
    is_runtime: false,
  },
  target: {
    system_id: "sys-erp",
    system_name: "ERP",
    object_id: "obj-acct",
    object_name: "Account",
    system_kind: "application",
    is_runtime: false,
  },
  producer_interface: {
    object_id: "iface-1",
    name: "Customer Inbound API",
    direction: "provided",
    interface_kind: "sync",
    protocol: "HTTPS",
    technology: null,
  },
  consumer_interface: null,
  has_request_graph: true,
  has_response_graph: true,
  has_error_graph: false,
  specification: {
    retry: { max_attempts: 2, backoff: "linear" },
    timeout_ms: 3000,
    idempotent: false,
    idempotency_key_field_id: null,
    security: { auth_type: "oauth2", notes: "mTLS" },
    routing: "Route by region",
    orchestration_role: "orchestration",
    error_handling: "Retry then DLQ",
  },
  target_fields_mapped: 1,
  target_fields_total: 2,
  scenario_count: 2,
  lifecycle_stage: { value: null, canonical: null, override: null, overridden: false },
  operational_status: { value: "live", canonical: "live", override: null, overridden: false },
  environment_scope: { value: "retiring", canonical: "tested", override: "retiring", overridden: true },
};

const landscape: IntegrationLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  contracts: [contract],
  interfaces: [
    {
      object_id: "iface-1",
      name: "Customer Inbound API",
      direction: "provided",
      interface_kind: "sync",
      protocol: "HTTPS",
      technology: null,
      description: "Inbound customer API.",
      component_object_id: "comp-1",
      component_name: "Integration Service",
      operations: [
        { object_id: "op-1", name: "CreateCustomer", operation_kind: "operation", description: null },
      ],
      contract_ids: ["int-1"],
    },
  ],
};

const phases: IntegrationFlowPhase[] = [
  {
    phase: "request",
    configured: true,
    node_count: 4,
    transformation_count: 2,
    transformations: [
      {
        node_id: "n1",
        type: "validate",
        label: "validate: required",
        role: "validation",
        position: { x: 120, y: 0 },
      },
      {
        node_id: "n2",
        type: "fx",
        label: "fx: upper",
        role: "transformation",
        position: { x: 260, y: 0 },
      },
    ],
    source_field_count: 1,
    target_field_count: 2,
    mapped_target_count: 1,
    target_fields: ["account_code"],
    unmapped_required_fields: ["region_code"],
  },
  {
    phase: "success-response",
    configured: true,
    node_count: 3,
    transformation_count: 1,
    transformations: [
      {
        node_id: "n3",
        type: "fx",
        label: "fx: upper",
        role: "transformation",
        position: { x: 120, y: 0 },
      },
    ],
    source_field_count: 1,
    target_field_count: 1,
    mapped_target_count: 1,
    target_fields: ["customer_name"],
    unmapped_required_fields: [],
  },
  {
    phase: "error-response",
    configured: false,
    node_count: 0,
    transformation_count: 0,
    transformations: [],
    source_field_count: 0,
    target_field_count: 1,
    mapped_target_count: 0,
    target_fields: [],
    unmapped_required_fields: [],
  },
];

const detail: IntegrationContractDetail = {
  contract,
  source_interface: landscape.interfaces[0],
  target_interface: null,
  phases,
};

const flow: IntegrationMessageFlow = {
  contract,
  routing: "Route by region",
  trigger_config: {},
  channel_kind: "api",
  channel_label: "API endpoint",
  phases,
};

const conformance: IntegrationConformance = {
  contract_id: "int-1",
  contract_name: "Customer push",
  revision: 2,
  updated_at: null,
  request_coverage: { mapped: 1, total: 2, ratio: 0.5 },
  response_coverage: { mapped: 1, total: 1, ratio: 1 },
  error_coverage: { mapped: 0, total: 0, ratio: 0 },
  scenarios: [
    {
      id: "sc-1",
      name: "Happy path",
      category: "happy_path",
      revision: 1,
      updated_at: null,
      status: "passing",
      step_count: 2,
      message: "",
    },
    {
      id: "sc-2",
      name: "Rejected account",
      category: "error",
      revision: 1,
      updated_at: null,
      status: "failing",
      step_count: 1,
      message: "Expected 'ACME', got 'WRONG'",
    },
  ],
  summary: { passing: 1, failing: 1, not_run: 0, outdated: 0 },
};

const sequence: IntegrationSequence = {
  contract_id: "int-1",
  contract_name: "Customer push",
  revision: 2,
  scenarios: [
    {
      id: "sc-1",
      name: "Happy path",
      category: "happy_path",
      status: "passing",
      revision: 1,
      outdated: false,
      step_count: 2,
      participants: [
        { id: "crm", label: "CRM", kind: "system", system_id: "sys-crm", system_name: "CRM", is_runtime: false },
        { id: "erp", label: "ERP", kind: "system", system_id: "sys-erp", system_name: "ERP", is_runtime: false },
      ],
      interactions: [
        {
          id: "step-1",
          kind: "actor",
          phase: null,
          from_id: "crm",
          to_id: "erp",
          label: "Trigger",
          contract_step: false,
        },
        {
          id: "step-2",
          kind: "contract",
          phase: "request",
          from_id: "crm",
          to_id: "erp",
          label: "Customer push · request",
          contract_step: true,
        },
      ],
    },
    {
      id: "sc-2",
      name: "Rejected account",
      category: "error",
      status: "failing",
      revision: 1,
      outdated: false,
      step_count: 1,
      participants: [],
      interactions: [],
    },
  ],
};

const trace = {
  state_id: "state-1",
  object: {
    id: "sys-crm",
    kind: "system",
    name: "CRM",
    description: null,
    discipline: null,
    state_membership: "candidate" as const,
    external: true,
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
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      if (url.includes("/integration-design/landscape")) return reply(landscape);
      if (url.includes("/integration-design/contracts/int-1/sequence")) return reply(sequence);
      if (url.includes("/integration-design/contracts/int-1/flow")) return reply(flow);
      if (url.includes("/integration-design/contracts/int-1/conformance")) return reply(conformance);
      if (url.includes("/integration-design/contracts/int-1")) return reply(detail);
      if (url.includes("/objects/") && url.includes("/usages")) return reply(trace);
      if (url.includes("/api/integrations/int-1") && init?.method === "PATCH") {
        return reply({ ...contract, revision: 3, pattern: "point_to_point" });
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function renderWorkbench(overrides: Partial<Parameters<typeof IntegrationWorkbench>[0]> = {}) {
  return render(
    <IntegrationWorkbench
      workspaceId="ws-1"
      activeState={candidateState}
      editable
      saveStatus="idle"
      onOpenIntegration={vi.fn()}
      onOpenCatalog={vi.fn()}
      {...overrides}
    />,
  );
}

async function selectContract() {
  const picker = await screen.findByLabelText("Contract");
  fireEvent.change(picker, { target: { value: "int-1" } });
  await screen.findByText("CreateCustomer");
}

describe("IntegrationWorkbench", () => {
  it("opens on the landscape topology and renders systems, interfaces and contracts", async () => {
    renderWorkbench();
    await waitFor(() => expect(screen.getByTestId("node-contract:int-1")).toBeTruthy());
    expect(screen.getByTestId("node-contract:int-1").textContent).toContain("Customer push");
    expect(screen.getByTestId("node-system:sys-crm").textContent).toContain("CRM");
    expect(screen.getByTestId("node-system:sys-erp").textContent).toContain("ERP");
    expect(screen.getByTestId("node-interface:iface-1").textContent).toContain("Customer Inbound API");
    expect(screen.getByTestId("node-component:comp-1").textContent).toContain("Integration Service");
  });

  it("opens the unified inspector for a selected system and contract", async () => {
    renderWorkbench();
    fireEvent.click(await screen.findByTestId("node-system:sys-crm"));
    expect(await screen.findByLabelText("System inspector")).toBeTruthy();
    fireEvent.click(screen.getByTestId("node-contract:int-1"));
    expect(await screen.findByLabelText("Contract inspector")).toBeTruthy();
    expect(screen.getAllByText("Request / reply").length).toBeGreaterThan(0);
  });

  it("double-clicks a contract to open Mapping & Tests", async () => {
    const onOpenIntegration = vi.fn();
    renderWorkbench({ onOpenIntegration });
    fireEvent.doubleClick(await screen.findByTestId("node-contract:int-1"));
    expect(onOpenIntegration).toHaveBeenCalledWith("int-1", "request");
  });

  it("explains resilience responsibility without inventing owners", async () => {
    renderWorkbench();
    await screen.findByTestId("node-contract:int-1");
    fireEvent.click(screen.getByRole("button", { name: "Resilience overlay" }));
    expect(await screen.findByText("Architecture resilience")).toBeTruthy();
    expect(screen.getByText("2 attempts")).toBeTruthy();
    expect(screen.getAllByText("Not defined").length).toBeGreaterThan(0);
  });

  it("shows the interface and channel architecture", async () => {
    renderWorkbench();
    await selectContract();
    expect(screen.getByText("Producer system")).toBeTruthy();
    expect(screen.getByText("CreateCustomer")).toBeTruthy();
    expect(screen.getByText("API endpoint")).toBeTruthy();
    expect(screen.getByText("Direct connection")).toBeTruthy();
  });

  it("shows the message flow stages including metadata-only routing", async () => {
    renderWorkbench();
    await selectContract();
    fireEvent.click(screen.getByRole("button", { name: "Message Flow" }));
    expect(await screen.findByText("validate: required")).toBeTruthy();
    expect(screen.getAllByText("fx: upper").length).toBeGreaterThan(0);
    expect(screen.getByText("Route by region")).toBeTruthy();
    expect(screen.getByText(/Unmapped required target fields: region_code/)).toBeTruthy();
  });

  it("projects scenarios as sequences and deep-links into the sequence designer", async () => {
    const onOpenIntegration = vi.fn();
    renderWorkbench({ onOpenIntegration });
    await selectContract();
    fireEvent.click(screen.getByRole("button", { name: "Scenario & Sequence" }));
    expect(await screen.findByText("Customer push · request")).toBeTruthy();
    expect(screen.getByText("Trigger")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open sequence designer" }));
    expect(onOpenIntegration).toHaveBeenCalledWith("int-1", "scenarios");
  });

  it("renders conformance coverage, statuses and outstanding configuration", async () => {
    renderWorkbench();
    await selectContract();
    fireEvent.click(screen.getByRole("button", { name: "Test & Conformance" }));
    expect(await screen.findByText("Request mappings")).toBeTruthy();
    expect(screen.getByText("Rejected account")).toBeTruthy();
    expect(screen.getAllByText("Passing").length).toBeGreaterThan(0);
    expect(screen.getByText("Outstanding configuration")).toBeTruthy();
  });

  it("saves integration properties through the API", async () => {
    renderWorkbench();
    await selectContract();
    fireEvent.click(screen.getByRole("button", { name: "Properties" }));
    fireEvent.change(await screen.findByLabelText("Pattern"), {
      target: { value: "point_to_point" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save properties" }));
    await waitFor(() => {
      const patch = vi
        .mocked(fetch)
        .mock.calls.find(
          ([path, init]) => String(path).includes("/api/integrations/int-1") && init?.method === "PATCH",
        );
      expect(patch).toBeTruthy();
      expect(String(patch?.[1]?.body)).toContain("point_to_point");
    });
  });

  it("keeps one contract selected across subviews via the compact selector", async () => {
    const onOpenIntegration = vi.fn();
    renderWorkbench({ onOpenIntegration });
    const picker = await screen.findByLabelText("Contract");
    expect((picker as HTMLSelectElement).value).toBe("");
    fireEvent.change(picker, { target: { value: "int-1" } });
    expect(await screen.findByText(/CRM → ERP/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Message Flow" }));
    await screen.findByText("validate: required");
    expect((screen.getByLabelText("Contract") as HTMLSelectElement).value).toBe("int-1");
    fireEvent.change(screen.getByLabelText("Contract"), { target: { value: "__new__" } });
    expect(onOpenIntegration).toHaveBeenCalledWith("");
  });

  it("disables property editing when the state is read-only", async () => {
    renderWorkbench({ editable: false });
    await selectContract();
    fireEvent.click(screen.getByRole("button", { name: "Properties" }));
    expect(await screen.findByRole("button", { name: "Save properties" })).toHaveProperty(
      "disabled",
      true,
    );
  });
});
