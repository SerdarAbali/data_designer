import { describe, expect, it } from "vitest";
import {
  applyBlockedReason,
  changeSummary,
  groupRows,
  issueLabels,
  revisionSummary,
  rowLabel,
  type WorkbookPreview,
  type WorkbookRowPreview,
} from "./contractWorkbook";

function row(overrides: Partial<WorkbookRowPreview> = {}): WorkbookRowPreview {
  return {
    row: 2,
    phase: "request",
    classification: "unchanged",
    action: "keep",
    editable: true,
    transformation: "direct",
    issues: [],
    warnings: [],
    ...overrides,
  };
}

function preview(overrides: Partial<WorkbookPreview> = {}): WorkbookPreview {
  return {
    contract_id: "c",
    contract_name: "Contract",
    contract_revision: 2,
    current_revision: 2,
    filename: "workbook.xlsx",
    stale: false,
    stale_reason: null,
    preview_hash: "h",
    applyable: true,
    has_changes: false,
    blocking_reasons: [],
    contract_changes: [],
    sheets: [],
    counts: {},
    ...overrides,
  };
}

describe("contract workbook model", () => {
  it("groups rows by classification and labels them readably", () => {
    const grouped = groupRows(
      preview({
        sheets: [
          {
            sheet: "Request Mappings",
            phase: "request",
            applicable: true,
            counts: {},
            rows: [
              row({ classification: "add", source_field: "customer_id", target_field: "account_id" }),
              row({ classification: "invalid", issues: [{ code: "archived_reference", message: "gone" }] }),
              row({ classification: "unresolved" }),
            ],
          },
          {
            sheet: "Error Response Mappings",
            phase: "error-response",
            applicable: false,
            counts: {},
            rows: [row({ phase: "error-response", classification: "invalid" })],
          },
        ],
      }),
    );
    expect(grouped.add).toHaveLength(1);
    expect(grouped.unchanged).toHaveLength(0);
    // Invalid rows from every sheet are collected together.
    expect(grouped.invalid).toHaveLength(2);
    expect(grouped.unresolved).toHaveLength(1);
    expect(rowLabel(grouped.add[0])).toBe("customer_id → account_id (direct)");
    expect(issueLabels(grouped.invalid[0])).toContain("archived_reference");
  });

  it("states the revision honestly and explains a blocked apply", () => {
    expect(revisionSummary(preview())).toBe("Workbook and contract both at revision 2");
    const stale = preview({
      stale: true,
      applyable: false,
      workbook_revision: 1,
      current_revision: 3,
      stale_reason: "The contract changed.",
    });
    expect(revisionSummary(stale)).toContain("Workbook revision 1 · current revision 3");
    expect(applyBlockedReason(stale)).toBe("The contract changed.");
    expect(
      applyBlockedReason(
        preview({ applyable: false, blocking_reasons: [{ code: "x", message: "Bad row." }] }),
      ),
    ).toBe("Bad row.");
    expect(applyBlockedReason(preview())).toBeNull();
  });

  it("describes a metadata change without inventing values", () => {
    expect(
      changeSummary({ field: "name", label: "Contract name", current: "A", proposed: "B" }),
    ).toBe("A → B");
    expect(
      changeSummary({ field: "lifecycle_stage", label: "Lifecycle", current: null, proposed: "active" }),
    ).toBe("not set → active");
    expect(
      changeSummary({ field: "pattern", label: "Pattern", current: "batch", proposed: null }),
    ).toBe("batch → cleared");
  });
});
