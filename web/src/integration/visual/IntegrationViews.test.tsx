// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  IntegrationContractDetail,
  IntegrationContractSummary,
  IntegrationFlowPhase,
  IntegrationLandscape,
  IntegrationMessageFlow,
  IntegrationSequence,
} from "../integrationDesignModel";
import FlowDesignerView from "./FlowDesignerView";
import IntegrationSequenceView from "./IntegrationSequenceView";
import IntegrationTopologyView from "./IntegrationTopologyView";
import InterfaceChannelView from "./InterfaceChannelView";

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
    onNodeDragStop,
    children,
  }: {
    nodes: { id: string; position: { x: number; y: number }; data: { label: string; kind: string } }[];
    edges: { id: string; data?: { relation: string } }[];
    onNodeClick?: (event: unknown, node: unknown) => void;
    onNodeDoubleClick?: (event: unknown, node: unknown) => void;
    onNodeDragStop?: (event: unknown, node: { id: string; position: { x: number; y: number } }) => void;
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
          {[node.data.label, node.data.kind].filter(Boolean).join("|")}
        </button>
      ))}
      {edges.map((edge) => (
        <button
          key={edge.id}
          data-testid={`edge-${edge.id}`}
          onClick={() => onNodeDragStop?.(null, { id: edge.id, position: { x: 5, y: 5 } })}
        >
          {edge.data?.relation}
        </button>
      ))}
      {children}
    </div>
  ),
}));

afterEach(cleanup);

const contract: IntegrationContractSummary = {
  id: "int-1",
  name: "Customer push",
  description: null,
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
  has_response_graph: false,
  has_error_graph: false,
  specification: {},
  target_fields_mapped: 1,
  target_fields_total: 1,
  scenario_count: 0,
};

const landscape: IntegrationLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  contracts: [contract],
  interfaces: [],
};

describe("IntegrationTopologyView", () => {
  it("renders systems, interfaces and contracts and selects a node", () => {
    const onSelectNode = vi.fn();
    render(
      <IntegrationTopologyView
        landscape={landscape}
        selectedRefId={null}
        onSelectNode={onSelectNode}
        onOpenContract={vi.fn()}
        manualPositions={{}}
        onMoveNode={vi.fn()}
        onArrange={vi.fn()}
        showResilience={false}
        onToggleResilience={vi.fn()}
        onViewportChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId("node-system:sys-crm")).toBeTruthy();
    expect(screen.getByTestId("node-interface:iface-1").textContent).toContain("Customer Inbound API");
    fireEvent.click(screen.getByTestId("node-contract:int-1"));
    expect(onSelectNode).toHaveBeenCalledWith(expect.objectContaining({ refId: "int-1", kind: "contract" }));
  });

  it("opens a contract on double click", () => {
    const onOpenContract = vi.fn();
    render(
      <IntegrationTopologyView
        landscape={landscape}
        selectedRefId={null}
        onSelectNode={vi.fn()}
        onOpenContract={onOpenContract}
        manualPositions={{}}
        onMoveNode={vi.fn()}
        onArrange={vi.fn()}
        showResilience={false}
        onToggleResilience={vi.fn()}
        onViewportChange={vi.fn()}
      />,
    );
    fireEvent.doubleClick(screen.getByTestId("node-contract:int-1"));
    expect(onOpenContract).toHaveBeenCalledWith("int-1");
  });

  it("shows the resilience overlay when toggled", () => {
    render(
      <IntegrationTopologyView
        landscape={landscape}
        selectedRefId={null}
        onSelectNode={vi.fn()}
        onOpenContract={vi.fn()}
        manualPositions={{}}
        onMoveNode={vi.fn()}
        onArrange={vi.fn()}
        showResilience
        onToggleResilience={vi.fn()}
        onViewportChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Architecture resilience")).toBeTruthy();
    expect(screen.getAllByText("Not defined").length).toBeGreaterThan(0);
  });
});

const requestPhase: IntegrationFlowPhase = {
  phase: "request",
  configured: true,
  node_count: 3,
  transformation_count: 1,
  transformations: [
    {
      node_id: "n1",
      type: "map",
      label: "map customer",
      role: "transformation",
      position: { x: 200, y: 0 },
    },
  ],
  source_field_count: 1,
  target_field_count: 1,
  mapped_target_count: 1,
  target_fields: ["account_code"],
  unmapped_required_fields: [],
};
const emptyPhase: IntegrationFlowPhase = {
  phase: "error-response",
  configured: false,
  node_count: 0,
  transformation_count: 0,
  transformations: [],
  source_field_count: 0,
  target_field_count: 1,
  mapped_target_count: 0,
  target_fields: [],
  unmapped_required_fields: ["reason_code"],
};
const flow: IntegrationMessageFlow = {
  contract,
  routing: "Route by region",
  trigger_config: {},
  channel_kind: "api",
  channel_label: "API endpoint",
  phases: [requestPhase, emptyPhase],
};

describe("FlowDesignerView", () => {
  it("renders stages and reports an unconfigured phase truthfully", () => {
    render(
      <FlowDesignerView
        flow={flow}
        selectedPhase="request"
        onSelectPhase={vi.fn()}
        onSelectStage={vi.fn()}
        onOpenContract={vi.fn()}
        onOpenMapping={vi.fn()}
      />,
    );
    expect(screen.getByRole("tab", { name: "Request" })).toBeTruthy();
    expect(screen.getByText("map customer")).toBeTruthy();
    const errorTab = screen.getByRole("tab", { name: /Error response/ });
    expect(errorTab.textContent).toContain("unconfigured");
    fireEvent.click(errorTab);
    expect(screen.getAllByText("No graph is configured for this phase yet. Stages appear once mappings exist.").length).toBeGreaterThan(0);
  });

  it("opens the mapping engine for a phase", () => {
    const onOpenMapping = vi.fn();
    render(
      <FlowDesignerView
        flow={flow}
        selectedPhase="request"
        onSelectPhase={vi.fn()}
        onSelectStage={vi.fn()}
        onOpenContract={vi.fn()}
        onOpenMapping={onOpenMapping}
      />,
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Open Mapping & Tests" })[0]);
    expect(onOpenMapping).toHaveBeenCalledWith("request");
  });
});

const detail: IntegrationContractDetail = {
  contract,
  source_interface: {
    object_id: "iface-1",
    name: "Customer Inbound API",
    direction: "provided",
    interface_kind: "sync",
    protocol: "HTTPS",
    technology: "REST",
    description: null,
    component_object_id: "comp-1",
    component_name: "Integration Service",
    operations: [
      { object_id: "op-1", name: "CreateCustomer", operation_kind: "operation", description: null },
    ],
    contract_ids: ["int-1"],
  },
  target_interface: null,
  phases: [requestPhase, emptyPhase],
};

describe("InterfaceChannelView", () => {
  it("renders interfaces, operations, channel and contract phases", () => {
    const onSelectInterface = vi.fn();
    const onOpenContract = vi.fn();
    render(
      <InterfaceChannelView
        detail={detail}
        flow={flow}
        onSelectInterface={onSelectInterface}
        onSelectSystem={vi.fn()}
        onOpenContract={onOpenContract}
        onOpenMapping={vi.fn()}
      />,
    );
    expect(screen.getByText("Producer system")).toBeTruthy();
    expect(screen.getByText("CreateCustomer")).toBeTruthy();
    expect(screen.getByText("API endpoint")).toBeTruthy();
    expect(screen.getByText("Direct connection")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
    expect(onSelectInterface).toHaveBeenCalledWith("iface-1");
    fireEvent.click(screen.getByRole("button", { name: "Customer push" }));
    expect(onOpenContract).toHaveBeenCalledWith("int-1");
  });
});

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
      ],
      interactions: [
        {
          id: "step-1",
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
      name: "Outdated path",
      category: "error",
      status: "outdated",
      revision: 1,
      outdated: true,
      step_count: 1,
      participants: [],
      interactions: [],
    },
  ],
};

describe("IntegrationSequenceView", () => {
  it("projects participants and ordered interactions and flags outdated scenarios", () => {
    const onSelectScenario = vi.fn();
    const onOpenScenarios = vi.fn();
    render(
      <IntegrationSequenceView
        sequence={sequence}
        loading={false}
        selectedScenarioId={null}
        onSelectScenario={onSelectScenario}
        onOpenScenarios={onOpenScenarios}
      />,
    );
    expect(screen.getByText("Customer push · request")).toBeTruthy();
    expect(screen.getAllByText("CRM").length).toBeGreaterThan(0);
    expect(screen.getByText("outdated")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Outdated path/ }));
    expect(onSelectScenario).toHaveBeenCalledWith("sc-2");
    fireEvent.click(screen.getByRole("button", { name: "Open sequence designer" }));
    expect(onOpenScenarios).toHaveBeenCalled();
  });
});
