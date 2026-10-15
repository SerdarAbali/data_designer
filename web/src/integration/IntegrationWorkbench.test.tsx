// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import IntegrationWorkbench from "./IntegrationWorkbench";
import type {
  IntegrationConformance,
  IntegrationContractDetail,
  IntegrationContractSummary,
  IntegrationLandscape,
  IntegrationMessageFlow,
} from "./integrationDesignModel";

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
  },
  target: {
    system_id: "sys-erp",
    system_name: "ERP",
    object_id: "obj-acct",
    object_name: "Account",
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
  target_fields_total: 1,
  scenario_count: 3,
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

const detail: IntegrationContractDetail = {
  contract,
  source_interface: landscape.interfaces[0],
  target_interface: null,
  phases: [
    {
      phase: "request",
      configured: true,
      node_count: 3,
      transformation_count: 1,
      transformations: [{ node_id: "n1", type: "fx", label: "fx: upper" }],
      source_field_count: 1,
      target_field_count: 1,
      mapped_target_count: 1,
      target_fields: ["account_code"],
    },
    {
      phase: "success-response",
      configured: true,
      node_count: 3,
      transformation_count: 1,
      transformations: [{ node_id: "n2", type: "fx", label: "fx: upper" }],
      source_field_count: 1,
      target_field_count: 1,
      mapped_target_count: 1,
      target_fields: ["customer_name"],
    },
  ],
};

const flow: IntegrationMessageFlow = {
  contract,
  routing: "Route by region",
  trigger_config: {},
  phases: detail.phases,
};

const conformance: IntegrationConformance = {
  contract_id: "int-1",
  contract_name: "Customer push",
  revision: 2,
  updated_at: null,
  request_coverage: { mapped: 1, total: 1, ratio: 1 },
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
    {
      id: "sc-3",
      name: "Deferred callback",
      category: "alternative",
      revision: 1,
      updated_at: null,
      status: "not_run",
      step_count: 0,
      message: "No contract steps or field assertions to evaluate",
    },
  ],
  summary: { passing: 1, failing: 1, not_run: 1, outdated: 0 },
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      if (url.includes("/integration-design/landscape")) return reply(landscape);
      if (url.includes("/integration-design/contracts/int-1/flow")) return reply(flow);
      if (url.includes("/integration-design/contracts/int-1/conformance")) return reply(conformance);
      if (url.includes("/integration-design/contracts/int-1")) return reply(detail);
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

describe("IntegrationWorkbench", () => {
  it("loads the landscape and lists contracts", async () => {
    renderWorkbench();
    expect(await screen.findByText("Customer push")).toBeTruthy();
    expect(screen.getByText("Request / reply")).toBeTruthy();
    expect(screen.getByText("Customer Inbound API")).toBeTruthy();
  });

  it("shows the interface and contract view", async () => {
    renderWorkbench();
    fireEvent.click(await screen.findByRole("button", { name: "Interfaces" }));
    expect(await screen.findByText("Producer: Customer Inbound API")).toBeTruthy();
    expect(screen.getByText("CreateCustomer")).toBeTruthy();
    expect(screen.getByText("Success response")).toBeTruthy();
  });

  it("shows the message flow with transformations", async () => {
    renderWorkbench();
    fireEvent.click(await screen.findByRole("button", { name: "Flow" }));
    expect(await screen.findByText("Route by region")).toBeTruthy();
    expect(screen.getAllByText("fx: upper").length).toBeGreaterThan(0);
  });

  it("deep-links into the sequence designer from the scenario view", async () => {
    const onOpenIntegration = vi.fn();
    renderWorkbench({ onOpenIntegration });
    fireEvent.click(await screen.findByRole("button", { name: "Conformance" }));
    await screen.findAllByText("Test & Conformance");
    fireEvent.click(screen.getByRole("button", { name: "Scenario & Sequence" }));
    expect((await screen.findAllByText("Happy path")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Open sequence designer" }));
    expect(onOpenIntegration).toHaveBeenCalledWith("int-1", "scenarios");
  });

  it("renders conformance coverage and statuses", async () => {
    renderWorkbench();
    fireEvent.click(await screen.findByRole("button", { name: "Conformance" }));
    expect(await screen.findByText("Request mappings")).toBeTruthy();
    expect(screen.getByText("Rejected account")).toBeTruthy();
    expect(screen.getAllByText("Passing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Outdated: 0").length).toBeGreaterThan(0);
  });

  it("saves integration properties through the API", async () => {
    renderWorkbench();
    await screen.findByText("Customer push");
    fireEvent.click(screen.getByRole("button", { name: "Interfaces" }));
    fireEvent.click(await screen.findByRole("button", { name: "Properties" }));
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
    expect(await screen.findByText(/CRM · Customer → ERP · Account/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Message Flow" }));
    await screen.findByText("Route by region");
    expect((screen.getByLabelText("Contract") as HTMLSelectElement).value).toBe("int-1");
    fireEvent.change(screen.getByLabelText("Contract"), { target: { value: "__new__" } });
    expect(onOpenIntegration).toHaveBeenCalledWith("");
  });

  it("disables property editing when the state is read-only", async () => {
    renderWorkbench({ editable: false });
    await screen.findByText("Customer push");
    fireEvent.click(screen.getByRole("button", { name: "Interfaces" }));
    fireEvent.click(await screen.findByRole("button", { name: "Properties" }));
    expect(await screen.findByRole("button", { name: "Save properties" })).toHaveProperty(
      "disabled",
      true,
    );
  });
});
