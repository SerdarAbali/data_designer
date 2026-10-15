// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import EnterpriseWorkbench from "../enterprise/EnterpriseWorkbench";
import InformationWorkbench from "../information/InformationWorkbench";
import IntegrationWorkbench from "../integration/IntegrationWorkbench";
import SolutionWorkbench from "../solution/SolutionWorkbench";
import type { InformationModel } from "../information/informationModel";
import type { EnterpriseModel } from "../enterprise/enterpriseModel";
import type {
  IntegrationConformance,
  IntegrationContractDetail,
  IntegrationContractSummary,
  IntegrationLandscape,
  IntegrationMessageFlow,
} from "../integration/integrationDesignModel";
import type { SolutionDesign, SolutionSummary } from "../solution/solutionModel";
import {
  useWorkbenchNavigation,
  WorkbenchNavigationProvider,
} from "./WorkbenchNavigation";
import type { TraceObjectRef } from "./workbenchTypes";

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
    nodes: { id: string; data: { entity?: { name: string } } }[];
    onNodeClick?: (event: null, node: unknown) => void;
    children: React.ReactNode;
  }) => (
    <div>
      {nodes.map((node) => (
        <button key={node.id} onClick={() => onNodeClick?.(null, node)}>
          {node.data.entity?.name ?? node.id}
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

const enterpriseModel: EnterpriseModel = {
  state_id: "candidate-a",
  state_type: "candidate",
  editable: true,
  goals: [],
  requirements: [],
  capabilities: [
    {
      object_id: "cap-1",
      kind: "capability",
      name: "Payment processing",
      description: null,
      owner: null,
      outcome_metric: null,
      horizon: null,
      process_type: null,
      principle_type: null,
      rationale: null,
      role_type: null,
      created_in_state_id: null,
    },
  ],
  processes: [],
  principles: [],
  roles: [],
  applications: [],
  links: [],
};

const informationModel: InformationModel = {
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

const contract: IntegrationContractSummary = {
  id: "int-1",
  name: "Customer push",
  description: null,
  interaction_type: "REQUEST_RESPONSE",
  pattern: null,
  implementation_status: "draft",
  revision: 1,
  updated_at: null,
  status: "draft",
  source: { system_id: "sys-1", system_name: "CRM", object_id: "obj-1", object_name: "Customer" },
  target: { system_id: "sys-2", system_name: "ERP", object_id: "obj-2", object_name: "Account" },
  producer_interface: null,
  consumer_interface: null,
  has_request_graph: false,
  has_response_graph: false,
  has_error_graph: false,
  specification: {},
  target_fields_mapped: 0,
  target_fields_total: 0,
  scenario_count: 0,
};
const integrationLandscape: IntegrationLandscape = {
  state_id: "candidate-a",
  state_type: "candidate",
  editable: true,
  contracts: [contract],
  interfaces: [],
};
const integrationDetail: IntegrationContractDetail = {
  contract,
  source_interface: null,
  target_interface: null,
  phases: [],
};
const integrationFlow: IntegrationMessageFlow = {
  contract,
  routing: "",
  trigger_config: {},
  phases: [],
};
const integrationConformance: IntegrationConformance = {
  contract_id: "int-1",
  contract_name: "Customer push",
  revision: 1,
  updated_at: null,
  request_coverage: { mapped: 0, total: 0, ratio: 0 },
  response_coverage: { mapped: 0, total: 0, ratio: 0 },
  error_coverage: { mapped: 0, total: 0, ratio: 0 },
  scenarios: [],
  summary: {},
};

const solutionSummary: SolutionSummary = {
  object_id: "sol-1",
  occurrence_id: "occ-sol",
  name: "Payments Platform",
  description: null,
  component_count: 1,
  member_count: 0,
};
const solutionDesign: SolutionDesign = {
  state_id: "candidate-a",
  state_type: "candidate",
  editable: true,
  solution: {
    solution_object_id: "sol-1",
    occurrence_id: "occ-sol",
    name: "Payments Platform",
    description: null,
    owner: null,
    position: { x: 0, y: 0 },
    members: [],
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
      technology: null,
      position: { x: 0, y: 0 },
      created_in_state_id: "candidate-a",
      interfaces: [],
    },
  ],
  repositories: [],
  deployment_nodes: [],
  trust_boundaries: [],
  links: [],
};

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const url = String(path);
      if (url.includes("/enterprise/model")) return reply(enterpriseModel);
      if (url.includes("/information/model")) return reply(informationModel);
      if (url.includes("/integration-design/landscape")) return reply(integrationLandscape);
      if (url.includes("/integration-design/contracts/")) {
        if (url.includes("/flow")) return reply(integrationFlow);
        if (url.includes("/conformance")) return reply(integrationConformance);
        return reply(integrationDetail);
      }
      if (url.includes("/solution/solutions/") && url.includes("/design")) return reply(solutionDesign);
      if (url.includes("/solution/solutions")) return reply([solutionSummary]);
      if (url.includes("/catalog/")) return reply([]);
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const traceNode = (overrides: Partial<TraceObjectRef>): TraceObjectRef => ({
  id: "x",
  kind: "information_object",
  name: "Object",
  description: null,
  discipline: "information",
  state_membership: "candidate",
  external: false,
  ...overrides,
});

function FocusHarness({ node, children }: { node: TraceObjectRef; children: React.ReactNode }) {
  const { requestFocus, clearFocus, focus } = useWorkbenchNavigation();
  return (
    <div>
      <button type="button" onClick={() => requestFocus(node)}>
        Request focus
      </button>
      <button type="button" onClick={() => focus && clearFocus(focus.nonce)}>
        Clear focus
      </button>
      <span data-testid="focus-id">{focus?.objectId ?? "none"}</span>
      {children}
    </div>
  );
}

describe("workbench trace navigation", () => {
  it("reveals a focused enterprise object and clears the request", async () => {
    render(
      <WorkbenchNavigationProvider>
        <FocusHarness node={traceNode({ id: "cap-1", kind: "business_capability", discipline: "enterprise" })}>
          <EnterpriseWorkbench
            workspaceId="ws-a"
            activeState={activeState}
            editable
            saveStatus="idle"
          />
        </FocusHarness>
      </WorkbenchNavigationProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Request focus" }));
    expect(await screen.findByRole("complementary", { name: "Enterprise object details" })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("focus-id").textContent).toBe("none"));
  });

  it("reveals the entity owning a focused information attribute", async () => {
    render(
      <WorkbenchNavigationProvider>
        <FocusHarness node={traceNode({ id: "attr-1", kind: "information_attribute" })}>
          <InformationWorkbench
            workspaceId="ws-a"
            activeState={activeState}
            editable
            saveStatus="idle"
            onAdoptState={vi.fn()}
            mutateActive={vi.fn()}
            onOpenCatalog={vi.fn()}
          />
        </FocusHarness>
      </WorkbenchNavigationProvider>,
    );
    await screen.findByRole("button", { name: "Customer" });
    fireEvent.click(screen.getByRole("button", { name: "Request focus" }));
    expect(await screen.findByRole("complementary", { name: "Attribute details" })).toBeTruthy();
    expect(screen.getByText("customer_id", { selector: "h3" })).toBeTruthy();
  });

  it("opens the destination contract for a focused integration contract", async () => {
    render(
      <WorkbenchNavigationProvider>
        <FocusHarness node={traceNode({ id: "int-1", kind: "contract_ref", discipline: "integration" })}>
          <IntegrationWorkbench workspaceId="ws-a" activeState={activeState} editable saveStatus="idle" />
        </FocusHarness>
      </WorkbenchNavigationProvider>,
    );
    await screen.findByRole("button", { name: "Customer push" });
    fireEvent.click(screen.getByRole("button", { name: "Request focus" }));
    expect(await screen.findByRole("heading", { name: "Customer push", level: 3 })).toBeTruthy();
  });

  it("reveals the destination component for a focused solution object", async () => {
    render(
      <WorkbenchNavigationProvider>
        <FocusHarness node={traceNode({ id: "comp-1", kind: "component", discipline: "solution" })}>
          <SolutionWorkbench workspaceId="ws-a" activeState={activeState} editable saveStatus="idle" />
        </FocusHarness>
      </WorkbenchNavigationProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Request focus" }));
    expect(await screen.findByRole("complementary", { name: "Component details" })).toBeTruthy();
    expect(screen.getByText("Payment API", { selector: "h3" })).toBeTruthy();
  });

  it("leaves a focus meant for another discipline for that workbench to consume", async () => {
    render(
      <WorkbenchNavigationProvider>
        <FocusHarness node={traceNode({ id: "ent-1", kind: "information_object", discipline: "information" })}>
          <EnterpriseWorkbench
            workspaceId="ws-a"
            activeState={activeState}
            editable
            saveStatus="idle"
          />
        </FocusHarness>
      </WorkbenchNavigationProvider>,
    );
    await screen.findByRole("button", { name: /Payment processing/ });
    fireEvent.click(screen.getByRole("button", { name: "Request focus" }));
    await waitFor(() => expect(screen.getByTestId("focus-id").textContent).toBe("ent-1"));
    expect(screen.queryByRole("complementary", { name: "Enterprise object details" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear focus" }));
    await waitFor(() => expect(screen.getByTestId("focus-id").textContent).toBe("none"));
  });

  it("provides a safe no-op outside a provider", () => {
    function Standalone() {
      const { focus, requestFocus, clearFocus } = useWorkbenchNavigation();
      requestFocus(traceNode({ id: "anything" }));
      clearFocus(0);
      return <span data-testid="standalone-focus">{focus === null ? "none" : "set"}</span>;
    }
    render(<Standalone />);
    expect(screen.getByTestId("standalone-focus").textContent).toBe("none");
  });
});
