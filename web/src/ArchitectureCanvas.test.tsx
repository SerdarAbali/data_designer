// @vitest-environment jsdom
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ArchitectureState, WorkspaceInfo } from "./architectureTypes";
import ArchitectureCanvas from "./ArchitectureCanvas";

const flow = vi.hoisted(() => ({
  getViewport: vi.fn(() => ({ x: 20, y: 30, zoom: 1 })),
  setViewport: vi.fn(),
  fitView: vi.fn(),
}));
vi.mock("@xyflow/react", () => ({
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => children,
  useReactFlow: () => flow,
  Background: () => null,
  Controls: ({ children }: { children: React.ReactNode }) => children,
  MiniMap: () => null,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MarkerType: { ArrowClosed: "arrow" },
  Position: { Left: "left", Right: "right" },
  Handle: () => null,
  applyNodeChanges: (_changes: unknown, nodes: unknown) => nodes,
  ReactFlow: ({ nodes, onNodeClick, onNodeDragStop, children }: {
    nodes: { id: string; data: { label: string }; position: { x: number; y: number } }[];
    onNodeClick: (event: null, node: unknown) => void;
    onNodeDragStop: (event: null, node: unknown, nodes: unknown[]) => void;
    children: React.ReactNode;
  }) => <div>{nodes.map((node) => <div key={node.id}>
    <button onClick={() => onNodeClick(null, node)}>{node.data.label}</button>
    <button onClick={() => onNodeDragStop(null, node, [{ ...node, position: { x: 99, y: 88 } }])}>Move {node.data.label}</button>
  </div>)}{children}</div>,
}));

const workspace: WorkspaceInfo = {
  id: "ws-a", name: "Workspace A", disciplines: ["enterprise", "information", "solution", "integration"],
  created_at: "", is_active: true, systems_count: 1, contracts_count: 0, scenarios_count: 0,
};
const candidate: ArchitectureState = {
  id: "candidate-a", workspace_id: "ws-a", name: "Candidate", state_type: "candidate",
  nodes: [
    { occurrence_id: "occ-system", object_id: "system-a", position: { x: 0, y: 0 } },
    { occurrence_id: "occ-info", object_id: "info-a", position: { x: 300, y: 0 }, discipline: "information" },
  ],
  relationships: [{ id: "rel", source_id: "info-a", target_id: "system-a", type: "Authoritative source" }],
  created_at: "", updated_at: "",
};
const current = { ...candidate, id: "current-a", name: "Current", state_type: "current" as const };
const objects = [{ id: "info-a", kind: "information_object", name: "Customer", owner: "Data team", authoritative_system_id: "system-a" }];
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem("dd_active_state_id:ws-a", candidate.id);
  sessionStorage.setItem("dd_active_discipline:ws-a", "integration");
  document.cookie = "dd_csrf=test";
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === "PUT") return reply({ ...candidate, ...JSON.parse(String(init.body)) });
    if (path.includes("architecture-objects")) return reply(objects);
    if (path.includes("/states")) return reply([current, candidate]);
    if (path.includes("/systems")) return reply([{ id: "system-a", name: "CRM", kind: "application", icon: null, color: null }]);
    if (path.includes("/integrations")) return reply([]);
    throw new Error(`Unexpected request: ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

const props = { workspace, onOpenIntegration: vi.fn(), onAddIntegration: vi.fn(), onOpenCatalog: vi.fn() };

function openCanvasOverview() {
  fireEvent.click(screen.getByRole("button", { name: "View options" }));
  fireEvent.click(screen.getByRole("button", { name: "Architecture canvas" }));
}

describe("architecture studio context", () => {
  it("keeps shared objects and the active state when switching projection; saves all hidden content", async () => {
    render(<ArchitectureCanvas {...props} />);
    openCanvasOverview();
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "Move CRM" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved"));
    const request = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "PUT")!;
    const body = JSON.parse(String(request[1]?.body));
    expect(body.nodes).toHaveLength(2);
    expect(body.relationships).toEqual(candidate.relationships);
    expect(body.nodes[0].position).toEqual({ x: 99, y: 88 });
    fireEvent.click(screen.getByRole("tab", { name: "Solution Architecture" }));
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Architecture state" }) as HTMLSelectElement).value).toBe(candidate.id));
  });

  it("waits for pending writes before navigation and blocks failed writes until retried", async () => {
    let finish!: (response: Response) => void;
    const original = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((path, init) => init?.method === "PUT"
      ? new Promise<Response>((resolve) => { finish = resolve; })
      : original(path, init));
    let guard!: () => Promise<boolean>;
    render(<ArchitectureCanvas {...props} registerNavigationGuard={(next) => { guard = next; }} />);
    openCanvasOverview();
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "Move CRM" }));
    await waitFor(() => expect(finish).toBeDefined());
    let allowed: boolean | undefined;
    const navigation = guard().then((value) => { allowed = value; });
    expect(allowed).toBeUndefined();
    await act(async () => { finish(reply({ detail: "Workspace not found" }, 404)); await navigation; });
    expect(allowed).toBe(false);
    expect(screen.getByRole("alert").textContent).toContain("Workspace not found");
    expect(screen.getByRole("status").textContent).toBe("Save failed");
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await act(async () => { await Promise.resolve(); finish(reply(candidate)); });
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved"));
    await expect(guard()).resolves.toBe(true);
  });

  it("keeps the inspector closed until selection and supports collapse/reopen", async () => {
    render(<ArchitectureCanvas {...props} />);
    openCanvasOverview();
    await screen.findByRole("button", { name: "CRM" });
    expect(screen.queryByRole("complementary", { name: "Object details" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "CRM" }));
    expect(screen.getByRole("complementary", { name: "Object details" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Collapse object inspector" }));
    expect(screen.queryByRole("complementary", { name: "Object details" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open inspector" }));
    expect(screen.getByRole("complementary", { name: "Object details" })).toBeTruthy();
  });

  it("offers only supported contextual objects in an Integration-only workspace", async () => {
    render(<ArchitectureCanvas {...props} workspace={{ ...workspace, disciplines: ["integration"] }} />);
    openCanvasOverview();
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "+ Add Object" }));
    expect(screen.getByRole("button", { name: "Existing system" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Existing contract" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Interface" })).toBeNull();
  });

  it("serializes object creation after a pending layout write without losing hidden occurrences", async () => {
    let finish!: (response: Response) => void;
    const original = vi.mocked(fetch).getMockImplementation()!;
    const created = { id: "int-new", kind: "interface", name: "Refund support" };
    const savedState = {
      ...candidate,
      nodes: [
        { ...candidate.nodes[0]!, position: { x: 99, y: 88 } },
        candidate.nodes[1]!,
        { occurrence_id: "occ-new", object_id: created.id, position: { x: 600, y: 0 }, discipline: "solution" },
      ],
    };
    vi.mocked(fetch).mockImplementation((path, init) => {
      if (init?.method === "PUT") return new Promise<Response>((resolve) => { finish = resolve; });
      if (init?.method === "POST") return Promise.resolve(reply({ object: created, state: savedState }));
      return original(path, init);
    });
    render(<ArchitectureCanvas {...props} />);
    openCanvasOverview();
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "Move CRM" }));
    await waitFor(() => expect(finish).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: "+ Add Object" }));
    fireEvent.click(screen.getByRole("button", { name: "Interface" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: created.name } });
    fireEvent.click(screen.getByRole("button", { name: "Add Interface" }));
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    await act(async () => { finish(reply(savedState)); });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("complementary", { name: "Object details" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Saved");
  });

  it("does not apply an old workspace response after a keyed workspace reset", async () => {
    let finishOld!: (response: Response) => void;
    let active = "a";
    vi.mocked(fetch).mockImplementation(async (path) => {
      const url = String(path);
      if (url.includes("/ws-a/states")) return new Promise<Response>((resolve) => { finishOld = resolve; });
      if (url.includes("/states")) return reply([{ ...candidate, id: "candidate-b", workspace_id: "ws-b", nodes: [candidate.nodes[0]] }]);
      if (url.includes("/systems")) return reply([{ id: "system-a", name: `CRM ${active}`, kind: "application", icon: null, color: null }]);
      return reply([]);
    });
    const { rerender } = render(<ArchitectureCanvas key="a" {...props} />);
    openCanvasOverview();
    await waitFor(() => expect(finishOld).toBeDefined());
    active = "b";
    sessionStorage.setItem("dd_active_discipline:ws-b", "integration");
    rerender(<ArchitectureCanvas key="b" {...props} workspace={{ ...workspace, id: "ws-b", name: "Workspace B" }} />);
    openCanvasOverview();
    await screen.findByRole("button", { name: "CRM b" });
    await act(async () => { finishOld(reply([current, candidate])); });
    expect(screen.queryByRole("button", { name: "CRM a" })).toBeNull();
    expect((screen.getByRole("combobox", { name: "Architecture state" }) as HTMLSelectElement).value).toBe("candidate-b");
  });
});

describe("workbench trace navigation", () => {
  it("switches workbench from a trace link while preserving the workspace and active state", async () => {
    sessionStorage.setItem("dd_active_discipline:ws-a", "enterprise");
    const enterpriseModel = {
      state_id: candidate.id,
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
    const usages = {
      state_id: candidate.id,
      object: {
        id: "cap-1",
        kind: "business_capability",
        name: "Payment processing",
        description: null,
        discipline: "enterprise",
        state_membership: "candidate",
        external: false,
      },
      disciplines: ["enterprise", "integration"],
      outgoing: [],
      incoming: [],
      groups: [
        {
          label: "Mapped into contracts",
          objects: [
            {
              id: "int-1",
              kind: "contract_ref",
              name: "Customer push",
              description: null,
              discipline: "integration",
              state_membership: "candidate",
              external: true,
            },
          ],
        },
      ],
      physical_refs: [],
      tests: [],
      principles: [],
    };
    const contract = {
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
    const detail = { contract, source_interface: null, target_interface: null, phases: [] };
    vi.mocked(fetch).mockImplementation(async (path) => {
      const url = String(path);
      if (url.includes("/enterprise/model")) return reply(enterpriseModel);
      if (url.includes("/usages")) return reply(usages);
      if (url.includes("/integration-design/landscape")) {
        return reply({ state_id: candidate.id, state_type: "candidate", editable: true, contracts: [contract], interfaces: [] });
      }
      if (url.includes("/integration-design/contracts/")) {
        if (url.includes("/flow")) return reply({ contract, routing: "", trigger_config: {}, phases: [] });
        if (url.includes("/conformance")) {
          return reply({
            contract_id: "int-1",
            contract_name: "Customer push",
            revision: 1,
            updated_at: null,
            request_coverage: { mapped: 0, total: 0, ratio: 0 },
            response_coverage: { mapped: 0, total: 0, ratio: 0 },
            error_coverage: { mapped: 0, total: 0, ratio: 0 },
            scenarios: [],
            summary: {},
          });
        }
        return reply(detail);
      }
      if (url.includes("architecture-objects")) return reply(objects);
      if (url.includes("/states")) return reply([current, candidate]);
      if (url.includes("/systems")) return reply([{ id: "system-a", name: "CRM", kind: "application", icon: null, color: null }]);
      if (url.includes("/integrations")) return reply([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<ArchitectureCanvas {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: /Payment processing/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Traceability" }));
    fireEvent.click(await screen.findByRole("button", { name: /Customer push/ }));
    expect(await screen.findByRole("heading", { name: "Customer push", level: 3 })).toBeTruthy();
    // Same workspace and state survive the workbench switch.
    expect((screen.getByRole("combobox", { name: "Architecture state" }) as HTMLSelectElement).value).toBe(candidate.id);
  });
});
