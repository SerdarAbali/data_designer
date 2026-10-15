// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import ArchitectureImportDialog from "./ArchitectureImportDialog";

const previewResponse = {
  import_type: "system",
  blocked_count: 1,
  resolved_reference_counts: { rows_matched: 1 },
  rows: [
    {
      row_number: 1,
      external_id: "SYS-1",
      name: "Billing",
      values: { name: "Billing", external_id: "SYS-1" },
      issues: [],
      warnings: [],
      matches: [
        { id: "system-1", kind: "system", name: "Billing", method: "external_id", score: null },
      ],
      suggested_decision: "use_existing",
    },
    {
      row_number: 2,
      external_id: null,
      name: "CRM",
      values: { name: "CRM" },
      issues: [{ row: 2, column: "owner", message: "Owner is required" }],
      warnings: [],
      matches: [],
      suggested_decision: "create",
    },
  ],
};

const batchResponse = {
  id: "11111111-2222-3333-4444-555555555555",
  workspace_id: "workspace-1",
  source_filename: "systems.csv",
  sheet_name: "CSV",
  import_type: "system",
  status: "applied",
  counts: { created: 0, updated: 0, matched: 1, skipped: 1, blocked: 0, failed: 0 },
  rows: [
    {
      row_number: 1,
      status: "matched",
      target_kind: "system",
      target_id: "system-1",
      message: "Using the existing record.",
      issues: [],
    },
    {
      row_number: 2,
      status: "skipped",
      target_kind: "system",
      target_id: null,
      message: "Skipped.",
      issues: [],
    },
  ],
  imported_at: "2026-10-15T10:00:00Z",
  undone_at: null,
};

function csvFile(text: string): File {
  const file = new File([text], "systems.csv", { type: "text/csv" });
  Object.defineProperty(file, "text", { value: async () => text });
  return file;
}

function renderDialog(currentStateId: string | null = "state-1") {
  const props = {
    workspaceId: "workspace-1",
    currentStateId,
    onClose: vi.fn(),
    onCommitted: vi.fn(),
    onOpenCanvas: vi.fn(),
  };
  render(<ArchitectureImportDialog {...props} />);
  return props;
}

async function uploadFile() {
  fireEvent.change(screen.getByLabelText("Import file"), {
    target: { files: [csvFile("Name,External ID\nBilling,SYS-1\nCRM,\n")] },
  });
  const previewButton = await screen.findByRole("button", { name: "Preview parsed rows" });
  await waitFor(() => expect((previewButton as HTMLButtonElement).disabled).toBe(false));
  return previewButton;
}

async function uploadAndPreview() {
  const previewButton = await uploadFile();
  fireEvent.click(previewButton);
  await screen.findByText(/matched by external ID/);
}

beforeEach(() => {
  document.cookie = "dd_csrf=test-token";
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const json = (body: unknown) =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      if (url.endsWith("/imports") && method === "GET") return json([]);
      if (url.endsWith("/imports/preview")) return json(previewResponse);
      if (url.endsWith("/imports/commit")) {
        return new Response(JSON.stringify(batchResponse), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/undo")) {
        return json({ ...batchResponse, status: "undone", undone_at: "2026-10-15T11:00:00Z" });
      }
      if (url.includes("/include-objects")) {
        return json({
          state: { id: "state-1" },
          added_occurrences: 1,
          added_relationships: 0,
          skipped: [],
        });
      }
      return json({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ArchitectureImportDialog", () => {
  it("maps columns, previews matches, and gates commit on confirmation", async () => {
    const props = renderDialog();
    const previewButton = await uploadFile();

    expect((screen.getByLabelText("Column for External ID") as HTMLSelectElement).value).toBe(
      "External ID",
    );

    fireEvent.click(previewButton);
    await screen.findByText(/matched by external ID/);
    expect(screen.getByText("Owner is required")).toBeTruthy();

    const apply = screen.getByRole("button", { name: "Apply 2 changes" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I reviewed the proposed changes/));
    await waitFor(() => expect(apply.disabled).toBe(false));
    fireEvent.click(apply);

    await screen.findByText("Import results");
    expect(screen.getAllByText(/matched/).length).toBeGreaterThan(0);
    expect(props.onCommitted).toHaveBeenCalledWith(expect.stringContaining("1 matched"));
  });

  it("undoes the committed batch and reports the result", async () => {
    renderDialog();
    await uploadAndPreview();
    fireEvent.click(screen.getByLabelText(/I reviewed the proposed changes/));
    fireEvent.click(await screen.findByRole("button", { name: "Apply 2 changes" }));
    await screen.findByText("Import results");

    fireEvent.click(screen.getByRole("button", { name: "Undo import" }));
    await screen.findByText(/Import batch undone/);
    const calls = (
      fetch as unknown as { mock: { calls: [RequestInfo | URL, RequestInit?][] } }
    ).mock.calls;
    expect(
      calls.some(([url]) =>
        String(url).endsWith("/imports/11111111-2222-3333-4444-555555555555/undo"),
      ),
    ).toBe(true);
  });

  it("places only the selected imported objects into the Current state", async () => {
    renderDialog();
    await uploadAndPreview();
    fireEvent.click(screen.getByLabelText(/I reviewed the proposed changes/));
    fireEvent.click(await screen.findByRole("button", { name: "Apply 2 changes" }));
    await screen.findByText("Import results");

    fireEvent.click(screen.getByLabelText("Include Billing"));
    fireEvent.click(screen.getByRole("button", { name: "Add selected to Current architecture" }));
    await screen.findByText(/Current architecture updated/);
  });

  it("explains how to initialize Current when the workspace has no state yet", async () => {
    renderDialog(null);
    await uploadAndPreview();
    fireEvent.click(screen.getByLabelText(/I reviewed the proposed changes/));
    fireEvent.click(await screen.findByRole("button", { name: "Apply 2 changes" }));
    await screen.findByText(/Open the Canvas once/);
  });
});
