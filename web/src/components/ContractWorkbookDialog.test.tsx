// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ContractWorkbookDialog from "./ContractWorkbookDialog";
import type { WorkbookPreview } from "../contractWorkbook";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";
const INTEGRATION = "22222222-2222-2222-2222-222222222222";

function row(overrides: Partial<WorkbookPreview["sheets"][number]["rows"][number]>) {
  return {
    row: 2,
    phase: "request",
    classification: "unchanged",
    action: "keep",
    editable: true,
    mapping_id: null,
    target_field_id: null,
    target_field: null,
    source_field: null,
    transformation: "direct",
    issues: [],
    warnings: [],
    ...overrides,
  };
}

function preview(overrides: Partial<WorkbookPreview> = {}): WorkbookPreview {
  return {
    contract_id: INTEGRATION,
    contract_name: "Onboarding",
    contract_revision: 4,
    current_revision: 4,
    workbook_revision: 4,
    workbook_format_version: 1,
    exported_at: "2026-01-01T00:00:00+00:00",
    filename: "workbook.xlsx",
    stale: false,
    stale_reason: null,
    preview_hash: "0123456789abcdef",
    applyable: true,
    has_changes: true,
    blocking_reasons: [],
    contract_changes: [],
    sheets: [],
    counts: { add: 0, update: 0, remove: 0, unchanged: 0, invalid: 0, unresolved: 0, rejected: 0 },
    ...overrides,
  };
}

function props(kind: "import" | "export" = "import") {
  return {
    kind,
    workspaceId: WORKSPACE,
    integrationId: INTEGRATION,
    contractName: "Onboarding",
    revision: 4,
    onApplied: vi.fn(),
    onClose: vi.fn(),
  };
}

function file(): File {
  const result = new File([new Uint8Array([80, 75, 3, 4])], "workbook.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  Object.defineProperty(result, "arrayBuffer", { value: async () => new ArrayBuffer(4) });
  return result;
}

function stubFetch(handler: (url: string, init?: RequestInit) => unknown) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = handler(String(url), init);
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function upload() {
  fireEvent.change(screen.getByTestId("workbook-file"), { target: { files: [file()] } });
}

beforeEach(() => {
  document.cookie = "dd_csrf=workbook-test-token";
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
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Contract mapping workbook dialog", () => {
  it("separates valid, invalid and unresolved rows and reports stale", async () => {
    stubFetch(() =>
      preview({
        stale: true,
        applyable: false,
        stale_reason: "The contract changed after this workbook was exported.",
        workbook_revision: 3,
        current_revision: 4,
        counts: { add: 1, update: 1, remove: 1, unchanged: 2, invalid: 1, unresolved: 1, rejected: 2 },
        sheets: [
          {
            sheet: "Request Mappings",
            phase: "request",
            applicable: true,
            counts: {},
            rows: [
              row({ row: 2, classification: "add", target_field: "account_id", source_field: "customer_id" }),
              row({ row: 3, classification: "update", target_field: "status", transformation: "fx" }),
              row({ row: 4, classification: "remove", target_field: "notes" }),
              row({ row: 5, classification: "unchanged", target_field: "email" }),
              row({
                row: 6,
                classification: "invalid",
                target_field: "ghost",
                issues: [{ code: "archived_reference", message: "The field exists but is archived." }],
              }),
              row({
                row: 7,
                classification: "unresolved",
                issues: [{ code: "unknown_field", message: "No field matches that exact name." }],
              }),
            ],
          },
        ],
      }),
    );
    render(<ContractWorkbookDialog {...props()} />);
    upload();

    await screen.findByTestId("workbook-preview");
    expect(screen.getByTestId("workbook-stale").textContent).toContain("Export it again");
    expect(screen.getByTestId("workbook-revisions").textContent).toContain(
      "Workbook revision 3 · current revision 4",
    );
    expect(screen.getByTestId("workbook-rows-added").children).toHaveLength(1);
    expect(screen.getByTestId("workbook-rows-updated").children).toHaveLength(1);
    expect(screen.getByTestId("workbook-rows-removed").children).toHaveLength(1);
    expect(screen.getByTestId("workbook-rows-unchanged").children).toHaveLength(1);
    expect(screen.getByTestId("workbook-rows-invalid").children).toHaveLength(1);
    expect(screen.getByTestId("workbook-rows-unresolved").children).toHaveLength(1);
    expect(screen.getByTestId("workbook-rows-invalid").textContent).toContain(
      "archived_reference",
    );

    // Stale previews cannot be applied even after confirmation.
    const applyButton = screen.getByTestId("workbook-apply") as HTMLButtonElement;
    expect(applyButton.disabled).toBe(true);
    expect((screen.getByTestId("workbook-confirm") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByTestId("workbook-blocked-reason").textContent).toContain(
      "changed after this workbook was exported",
    );
  });

  it("writes nothing on file selection and requires confirmation before applying", async () => {
    const mock = stubFetch((url) =>
      url.endsWith("/apply")
        ? {
            contract_id: INTEGRATION,
            revision: 5,
            applied: true,
            counts: { add: 1, update: 0, remove: 0, unchanged: 4, invalid: 0, unresolved: 0, rejected: 0 },
            sheets: [],
          }
        : preview({
            counts: { add: 1, update: 0, remove: 0, unchanged: 4, invalid: 0, unresolved: 0, rejected: 0 },
            contract_changes: [
              { field: "name", label: "Contract name", current: "Onboarding", proposed: "Onboarding v2" },
            ],
            sheets: [
              {
                sheet: "Request Mappings",
                phase: "request",
                applicable: true,
                counts: {},
                rows: [row({ row: 2, classification: "add", target_field: "account_id" })],
              },
            ],
          }),
    );
    const input = props();
    render(<ContractWorkbookDialog {...input} />);
    upload();
    await screen.findByTestId("workbook-preview");

    // Selecting the file only previewed: no write call was made.
    const calls = mock.mock.calls.map((call) => String(call[0]));
    expect(calls.filter((url) => url.endsWith("/apply"))).toHaveLength(0);
    expect(calls.filter((url) => url.endsWith("/preview"))).toHaveLength(1);
    expect(screen.getByTestId("workbook-contract-changes").textContent).toContain(
      "Onboarding → Onboarding v2",
    );

    const applyButton = screen.getByTestId("workbook-apply") as HTMLButtonElement;
    expect(applyButton.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("workbook-confirm"));
    expect(applyButton.disabled).toBe(false);

    fireEvent.click(applyButton);
    await waitFor(() => expect(input.onApplied).toHaveBeenCalledTimes(1));
    const applyCall = mock.mock.calls.find((call) => String(call[0]).endsWith("/apply"));
    const body = JSON.parse(String(applyCall?.[1]?.body ?? "{}"));
    expect(body.expected_revision).toBe(4);
    expect(body.preview_hash).toBe("0123456789abcdef");
    expect(await screen.findByTestId("workbook-result")).toBeTruthy();
  });

  it("blocks apply for an invalid preview and explains why", async () => {
    stubFetch(() =>
      preview({
        applyable: false,
        has_changes: true,
        counts: { add: 0, update: 0, remove: 0, unchanged: 0, invalid: 1, unresolved: 0, rejected: 1 },
        blocking_reasons: [
          { code: "protected_mapping", message: "This mapping cannot be changed from the workbook.", row: 2 },
        ],
        sheets: [
          {
            sheet: "Request Mappings",
            phase: "request",
            applicable: true,
            counts: {},
            rows: [row({ row: 2, classification: "invalid", editable: false })],
          },
        ],
      }),
    );
    render(<ContractWorkbookDialog {...props()} />);
    upload();
    await screen.findByTestId("workbook-blocking");
    expect(screen.getByTestId("workbook-blocking").textContent).toContain("protected_mapping");
    expect((screen.getByTestId("workbook-apply") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("workbook-confirm") as HTMLInputElement).disabled).toBe(true);
  });

  it("surfaces an upload failure without previewing anything", async () => {
    const mock = vi.fn(async () => ({
      ok: false,
      status: 400,
      json: async () => ({ detail: { code: "not_xlsx", message: "Only an .xlsx workbook can be imported." } }),
    }));
    vi.stubGlobal("fetch", mock);
    render(<ContractWorkbookDialog {...props()} />);
    upload();
    await screen.findByTestId("workbook-error");
    expect(screen.getByTestId("workbook-error").textContent).toContain("Only an .xlsx workbook");
    expect(screen.queryByTestId("workbook-preview")).toBeNull();
  });

  it("previews how the export will behave without writing", async () => {
    const mock = stubFetch((url) =>
      String(url).endsWith("/workbook") ? { summary: "workbook" } : preview(),
    );
    render(<ContractWorkbookDialog {...props("export")} />);
    expect(screen.getByText(/Instructions sheet, the Contract sheet/)).toBeTruthy();
    expect(mock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("workbook-file")).toBeNull();
  });
});
