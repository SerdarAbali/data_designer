// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import IntegrationWorkspace from "./IntegrationWorkspace";
import type { GraphDocument } from "./contractGraphTypes";
import { CSV_COLUMNS, serializeCsv } from "./contractMappingCsv";

vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return { ...actual, ReactFlow: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    MiniMap: () => null, Background: () => null, Controls: () => null };
});

const ids = {
  contract: "10000000-0000-4000-8000-000000000001",
  sourceSystem: "10000000-0000-4000-8000-000000000002",
  targetSystem: "10000000-0000-4000-8000-000000000003",
  sourceObject: "10000000-0000-4000-8000-000000000004",
  targetObject: "10000000-0000-4000-8000-000000000005",
  errorObject: "10000000-0000-4000-8000-000000000006",
  sourceField: "10000000-0000-4000-8000-000000000007",
  targetField: "10000000-0000-4000-8000-000000000008",
  errorField: "10000000-0000-4000-8000-000000000009",
};
const emptyGraph = (): GraphDocument => ({
  version: 1,
  nodes: [
    { id: "10000000-0000-4000-8000-000000000010", type: "source",
      position: { x: 80, y: 100 }, config: {} },
    { id: "10000000-0000-4000-8000-000000000011", type: "target",
      position: { x: 700, y: 100 }, config: {} },
  ], edges: [],
});
const field = (id: string, objectId: string, name: string) => ({
  id, object_id: objectId, name, label: name, data_type: "string",
  required: false, nullable: true, default_value: null, position: 0,
});
const sourceFields = [field(ids.sourceField, ids.sourceObject, "sender")];
const targetFields = [field(ids.targetField, ids.targetObject, "receiver")];
const errorFields = [field(ids.errorField, ids.errorObject, "error")];
const systems = [
  { id: ids.sourceSystem, name: "Source system", kind: "application" },
  { id: ids.targetSystem, name: "Target system", kind: "application" },
];
const objects = [
  { id: ids.sourceObject, system_id: ids.sourceSystem, name: "Source", label: "Source" },
  { id: ids.targetObject, system_id: ids.targetSystem, name: "Target", label: "Target" },
  { id: ids.errorObject, system_id: ids.targetSystem, name: "Error", label: "Error" },
];
const initialContract = () => ({
  id: ids.contract, source_system_id: ids.sourceSystem, target_system_id: ids.targetSystem,
  source_object_id: ids.sourceObject, target_object_id: ids.targetObject,
  error_response_object_id: ids.errorObject, name: "CSV test",
  interaction_type: "REQUEST_RESPONSE", graph: emptyGraph(), response_graph: emptyGraph(),
  error_response_graph: emptyGraph(), revision: 1, sample_rows: [],
});
let saved = initialContract();
let conflict = false;
let writes: Record<string, unknown>[] = [];

beforeEach(() => {
  document.cookie = "dd_csrf=test-token";
  saved = initialContract();
  conflict = false;
  writes = [];
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); },
  });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "http://localhost").pathname;
    let value: unknown;
    if (path === `/api/integrations/${ids.contract}/graph`) {
      const body = JSON.parse(String(init?.body));
      writes.push(body);
      if (conflict) return new Response(JSON.stringify({ detail: "Revision conflict." }), { status: 409 });
      saved = { ...saved, ...body, revision: saved.revision + 1 };
      return Response.json(saved);
    }
    if (path.endsWith("/dry-run")) {
      return Response.json({
        integrationId: ids.contract, revision: saved.revision,
        summary: { total: 0, ok: 0, skipped: 0, failed: 0 }, rows: [],
        requestOutcomes: [], responseOutcomes: [], responseSummary: { total: 0, ok: 0, skipped: 0, failed: 0 },
      });
    }
    if (path === "/api/integrations/architecture") value = { integrations: [], conflicts: [] };
    else if (path === "/api/integrations") value = [saved];
    else if (path === `/api/integrations/${ids.contract}`) value = saved;
    else if (path === "/api/catalog/systems") value = systems;
    else if (systems.some((system) => path === `/api/catalog/systems/${system.id}`)) {
      value = systems.find((system) => path.endsWith(system.id));
    } else if (path.endsWith("/objects") && path.includes("/systems/")) {
      value = objects.filter((object) => path.includes(object.system_id));
    } else if (path.endsWith("/fields")) {
      value = path.includes(ids.sourceObject) ? sourceFields
        : path.includes(ids.targetObject) ? targetFields : errorFields;
    } else if (objects.some((object) => path === `/api/catalog/objects/${object.id}`)) {
      value = objects.find((object) => path.endsWith(object.id));
    } else throw new Error(`Unexpected API call: ${path}`);
    return Response.json(value);
  }));
});
afterEach(() => {
  cleanup();
  document.cookie = "dd_csrf=; Max-Age=0";
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openEditor(tab = "Request") {
  render(<IntegrationWorkspace onBack={vi.fn()} />);
  await screen.findByRole("heading", { name: "CSV test", level: 1 });
  await screen.findByRole("button", { name: tab });
  await waitFor(() => expect((screen.getByRole("button", { name: "Reload Schema" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: tab }));
}
async function importMapping(source = "sender", target = "receiver") {
  fireEvent.click(screen.getByText("⋯"));
  fireEvent.click(screen.getByRole("button", { name: "Import CSV" }));
  const text = serializeCsv(CSV_COLUMNS, [["1", source, target, "", "", "", "", ""]]);
  const file = new File([text], "test.csv");
  Object.defineProperty(file, "arrayBuffer", { value: async () => new TextEncoder().encode(text).buffer });
  fireEvent.change(screen.getByLabelText("Choose CSV (or drop one here)"), { target: { files: [file] } });
  await screen.findByText("Direct");
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Apply 1 changes to draft" }));
  await screen.findByRole("button", { name: "Undo import" });
}

describe("CSV editor draft and persistence integration", () => {
  it("applies and undoes without saving, restoring the previous clean state", async () => {
    await openEditor();
    await importMapping();
    expect(writes).toEqual([]);
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Undo import" }));
    expect(screen.getByText("Saved · r1")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("saves request mappings through the existing revision-aware API and preserves other graphs", async () => {
    const responseBefore = structuredClone(saved.response_graph);
    const errorBefore = structuredClone(saved.error_response_graph);
    await openEditor();
    await importMapping();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved · r2");
    expect(writes[0].expected_revision).toBe(1);
    expect(saved.graph.edges).toHaveLength(1);
    expect(saved.response_graph).toEqual(responseBefore);
    expect(saved.error_response_graph).toEqual(errorBefore);
    expect(screen.queryByRole("button", { name: "Undo import" })).toBeNull();
    cleanup();
    await openEditor();
    fireEvent.click(screen.getByRole("tab", { name: "Mapping Matrix" }));
    expect(screen.getAllByText("Direct").length).toBeGreaterThan(0);
  });
  it.each([
    ["Success Response", "receiver", "response_graph", ids.targetField],
    ["Error Response", "error", "error_response_graph", ids.errorField],
  ])("imports %s using its sender/receiver fields without altering request", async (tab, source, key, sourceId) => {
    const requestBefore = structuredClone(saved.graph);
    await openEditor(tab);
    await importMapping(source, "sender");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved · r2");
    const graph = key === "response_graph" ? saved.response_graph : saved.error_response_graph;
    expect(graph.edges[0].sourcePortId).toBe(`field:${sourceId}`);
    expect(graph.edges[0].targetPortId).toBe(`field:${ids.sourceField}`);
    expect(saved.graph).toEqual(requestBefore);
  });
  it("imports async response into shared response storage, not a new phase graph", async () => {
    saved.interaction_type = "ASYNC_CALLBACK";
    const requestBefore = structuredClone(saved.graph);
    await openEditor("Response");
    await importMapping("receiver", "sender");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved · r2");
    expect(saved.response_graph.edges[0].sourcePortId).toBe(`field:${ids.targetField}`);
    expect(saved.graph).toEqual(requestBefore);
  });
  it("Undo preserves unrelated preexisting unsaved changes", async () => {
    await openEditor();
    fireEvent.click(screen.getByText("⋯"));
    fireEvent.click(screen.getByRole("button", { name: "Contract settings" }));
    const nameInput = screen.getByLabelText("Contract name");
    fireEvent.change(nameInput, { target: { value: "Renamed draft" } });
    await importMapping();
    fireEvent.click(screen.getByRole("button", { name: "Undo import" }));
    expect(screen.getByRole("heading", { name: "Renamed draft", level: 1 })).toBeTruthy();
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved · r2");
    expect(saved.name).toBe("Renamed draft");
    expect(saved.graph.edges).toHaveLength(0);
  });
  it("preserves imported drafts on revision conflicts and shows the existing reload guidance", async () => {
    conflict = true;
    await openEditor();
    await importMapping();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/Revision conflict.*Reload/);
    expect(saved.graph.edges).toHaveLength(0);
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
  });
  it("invalidates Undo on phase switching without dropping the imported draft", async () => {
    await openEditor();
    await importMapping();
    fireEvent.click(screen.getByRole("button", { name: "Success Response" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Undo import" })).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Request" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved · r2");
    expect(saved.graph.edges).toHaveLength(1);
  });
});
