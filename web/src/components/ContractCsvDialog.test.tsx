// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ContractCsvDialog from "./ContractCsvDialog";
import { CSV_COLUMNS, serializeCsv } from "../contractMappingCsv";
import type { GraphDocument } from "../contractGraphTypes";

const graph: GraphDocument = {
  version: 1,
  nodes: [
    { id: "source", type: "source", config: {}, position: { x: 80, y: 100 } },
    { id: "target", type: "target", config: {}, position: { x: 700, y: 100 } },
  ],
  edges: [],
};
const senderFields = [{ id: "s1", name: "sender", data_type: "string" }];
const receiverFields = [{ id: "t1", name: "receiver", data_type: "string" }];
let nextId = 0;
const props = () => ({
  kind: "import" as const, contractName: "Test", phase: "request", dirty: false,
  graph, senderFields, receiverFields, contextKey: "current", newId: () => `id-${++nextId}`,
  onApply: vi.fn(), onClose: vi.fn(),
});
function file(text: string): File {
  const result = new File([text], "mappings.csv", { type: "text/csv" });
  Object.defineProperty(result, "arrayBuffer", {
    value: async () => new TextEncoder().encode(text).buffer,
  });
  return result;
}
function upload(text: string) {
  fireEvent.change(screen.getByLabelText("Choose CSV (or drop one here)"), {
    target: { files: [file(text)] },
  });
}
const valid = () => serializeCsv(CSV_COLUMNS, [["1", "sender", "receiver", "", "", "", "", ""]]);

beforeEach(() => {
  nextId = 0;
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); },
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Contract CSV dialog", () => {
  it("previews mappings, requires confirmation, then applies only a draft", async () => {
    const input = props();
    render(<ContractCsvDialog {...input} />);
    upload(valid());
    await screen.findByText("Direct");
    const button = screen.getByRole("button", { name: "Apply 1 changes to draft" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(input.onApply).toHaveBeenCalledOnce();
    const [updated, context, count] = input.onApply.mock.calls[0];
    expect(updated.edges).toHaveLength(1);
    expect(context).toBe("current");
    expect(count).toBe(1);
    expect(graph.edges).toEqual([]);
  });
  it("invalid rows block apply and field resolution allows deliberate repair", async () => {
    const input = props();
    render(<ContractCsvDialog {...input} />);
    upload(serializeCsv(CSV_COLUMNS, [["1", "missing", "receiver", "", "", "", "", ""]]));
    await screen.findByText("Resolve these issues before continuing");
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Source field for row 2"), { target: { value: "s1" } });
    await waitFor(() => expect(screen.queryByText("Resolve these issues before continuing")).toBeNull());
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Apply 1 changes to draft" }));
    expect(input.onApply.mock.calls[0][0].edges[0].sourcePortId).toBe("field:s1");
  });
  it("supports remapping equivalent custom headers", async () => {
    render(<ContractCsvDialog {...props()} />);
    upload("Version,Sender,Receiver\n1,sender,receiver");
    await screen.findByText("Resolve these issues before continuing");
    for (const [name, value] of [["format_version (required)", "0"], ["source_field (required)", "1"], ["target_field (required)", "2"]]) {
      fireEvent.change(screen.getByLabelText(name), { target: { value } });
    }
    await screen.findByText("Direct");
    expect(screen.queryByText("Resolve these issues before continuing")).toBeNull();
  });
  it("changing conflict mode is explicit and confirmation resets", async () => {
    const input = props();
    const mapped = {
      ...graph,
      edges: [{ id: "existing", sourceNodeId: "source", sourcePortId: "field:s2",
        targetNodeId: "target", targetPortId: "field:t1" }],
    };
    render(<ContractCsvDialog {...input} graph={mapped} senderFields={[
      ...senderFields, { id: "s2", name: "other", data_type: "string" },
    ]} />);
    upload(valid());
    await screen.findByText("conflict");
    fireEvent.change(screen.getByLabelText("Existing mappings"), { target: { value: "replace" } });
    await screen.findByText("replace");
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Apply 1 changes to draft" }));
    expect(input.onApply.mock.calls[0][0].edges).toHaveLength(1);
    expect(input.onApply.mock.calls[0][0].edges[0].id).not.toBe("existing");
  });
  it("a stale preview blocks application until explicitly refreshed", async () => {
    const input = props();
    const view = render(<ContractCsvDialog {...input} />);
    upload(valid());
    await screen.findByText("Direct");
    fireEvent.click(screen.getByRole("checkbox"));
    view.rerender(<ContractCsvDialog {...input} contextKey="changed" />);
    expect((screen.getByRole("button", { name: "Apply 1 changes to draft" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Refresh preview" }));
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Apply 1 changes to draft" }));
    expect(input.onApply.mock.calls[0][1]).toBe("changed");
  });
  it("reports empty files and cancels without applying", async () => {
    const input = props();
    render(<ContractCsvDialog {...input} />);
    upload("");
    await screen.findByText("The file is empty. Download a template to get started.");
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }));
    expect(input.onClose).toHaveBeenCalledOnce();
    expect(input.onApply).not.toHaveBeenCalled();
  });
  it("shows an explicit export failure for advanced nodes, never a partial download", () => {
    const advanced: GraphDocument = {
      ...graph, nodes: [...graph.nodes, {
        id: "constant", type: "constant", config: { value: "value" }, position: { x: 300, y: 100 },
      }],
    };
    render(<ContractCsvDialog {...props()} kind="export" graph={advanced} />);
    expect((screen.getByRole("button", { name: "Download CSV" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Nothing will be downloaded/)).toBeTruthy();
  });
  it("restores focus on close", () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const view = render(<ContractCsvDialog {...props()} />);
    view.unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
});
