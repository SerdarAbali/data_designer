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

describe("architecture studio context", () => {
  it("keeps shared objects and the active state when switching projection; saves all hidden content", async () => {
    render(<ArchitectureCanvas {...props} />);
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "Move CRM" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved"));
    const request = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "PUT")!;
    const body = JSON.parse(String(request[1]?.body));
    expect(body.nodes).toHaveLength(2);
    expect(body.relationships).toEqual(candidate.relationships);
    expect(body.nodes[0].position).toEqual({ x: 99, y: 88 });
    fireEvent.click(screen.getByRole("tab", { name: "Information Architecture" }));
    await screen.findByRole("button", { name: "Customer" });
    expect((screen.getByRole("combobox", { name: "Architecture state" }) as HTMLSelectElement).value).toBe(candidate.id);
  });

  it("waits for pending writes before navigation and blocks failed writes until retried", async () => {
    let finish!: (response: Response) => void;
    const original = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((path, init) => init?.method === "PUT"
      ? new Promise<Response>((resolve) => { finish = resolve; })
      : original(path, init));
    let guard!: () => Promise<boolean>;
    render(<ArchitectureCanvas {...props} registerNavigationGuard={(next) => { guard = next; }} />);
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
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "+ Add Object" }));
    expect(screen.getByRole("button", { name: "Existing system" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Existing contract" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Interface" })).toBeNull();
  });

  it("serializes object creation after a pending layout write without losing hidden occurrences", async () => {
    let finish!: (response: Response) => void;
    const original = vi.mocked(fetch).getMockImplementation()!;
    const created = { id: "req-new", kind: "business_requirement", name: "Refund support" };
    const savedState = {
      ...candidate,
      nodes: [
        { ...candidate.nodes[0]!, position: { x: 99, y: 88 } },
        candidate.nodes[1]!,
        { occurrence_id: "occ-new", object_id: created.id, position: { x: 600, y: 0 }, discipline: "enterprise" },
      ],
    };
    vi.mocked(fetch).mockImplementation((path, init) => {
      if (init?.method === "PUT") return new Promise<Response>((resolve) => { finish = resolve; });
      if (init?.method === "POST") return Promise.resolve(reply({ object: created, state: savedState }));
      return original(path, init);
    });
    render(<ArchitectureCanvas {...props} />);
    await screen.findByRole("button", { name: "CRM" });
    fireEvent.click(screen.getByRole("button", { name: "Move CRM" }));
    await waitFor(() => expect(finish).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: "+ Add Object" }));
    fireEvent.click(screen.getByRole("button", { name: "Requirement" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: created.name } });
    fireEvent.click(screen.getByRole("button", { name: "Add Business Requirement" }));
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    await act(async () => { finish(reply(savedState)); });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("complementary", { name: "Object details" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Saved");
    fireEvent.click(screen.getByRole("tab", { name: "Information Architecture" }));
    await screen.findByRole("button", { name: "Customer" });
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
    await waitFor(() => expect(finishOld).toBeDefined());
    active = "b";
    rerender(<ArchitectureCanvas key="b" {...props} workspace={{ ...workspace, id: "ws-b", name: "Workspace B" }} />);
    await screen.findByRole("button", { name: "CRM b" });
    await act(async () => { finishOld(reply([current, candidate])); });
    expect(screen.queryByRole("button", { name: "CRM a" })).toBeNull();
    expect((screen.getByRole("combobox", { name: "Architecture state" }) as HTMLSelectElement).value).toBe("candidate-b");
  });
});
