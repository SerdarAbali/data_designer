/**
 * Client-side model for the governed Contract mapping workbook.
 *
 * The preview is a projection the server already validated and classified. The
 * studio only groups and labels it: it never decides what is applyable, and it
 * never writes anything except through an explicit, confirmed apply call.
 */

export type WorkbookIssue = {
  code: string;
  message: string;
  row?: number;
  column?: string | null;
};

export type WorkbookRowPreview = {
  row: number;
  phase: string;
  classification: string;
  action: string;
  editable: boolean;
  mapping_id?: string | null;
  target_field_id?: string | null;
  target_field?: string | null;
  source_field?: string | null;
  transformation: string;
  issues: WorkbookIssue[];
  warnings: WorkbookIssue[];
};

export type WorkbookSheetPreview = {
  sheet: string;
  phase: string;
  applicable: boolean;
  counts: Record<string, number>;
  rows: WorkbookRowPreview[];
};

export type ContractChange = {
  field: string;
  label: string;
  current?: string | null;
  proposed?: string | null;
};

export type WorkbookPreview = {
  contract_id: string;
  contract_name: string;
  contract_revision: number;
  current_revision: number;
  workbook_revision?: number | null;
  workbook_format_version?: number | null;
  exported_at?: string | null;
  filename: string;
  stale: boolean;
  stale_reason?: string | null;
  preview_hash: string;
  applyable: boolean;
  has_changes: boolean;
  blocking_reasons: WorkbookIssue[];
  contract_changes: ContractChange[];
  sheets: WorkbookSheetPreview[];
  counts: Record<string, number>;
};

export type WorkbookApplyResult = {
  contract_id: string;
  revision: number;
  applied: boolean;
  counts: Record<string, number>;
  sheets: WorkbookSheetPreview[];
};

export const CLASSIFICATION_ORDER = [
  "add",
  "update",
  "remove",
  "unchanged",
  "invalid",
  "unresolved",
] as const;

export const CLASSIFICATION_LABELS: Record<string, string> = {
  add: "Added",
  update: "Updated",
  remove: "Removed",
  unchanged: "Unchanged",
  invalid: "Invalid",
  unresolved: "Unresolved",
  stale: "Stale",
};

export const CLASSIFICATION_TONES: Record<string, string> = {
  add: "ok",
  update: "ok",
  remove: "warn",
  unchanged: "muted",
  invalid: "danger",
  unresolved: "danger",
};

export const WORKBOOK_PHASE_LABELS: Record<string, string> = {
  request: "Request",
  "success-response": "Success response",
  "error-response": "Error response",
};

/** Every classified row, grouped by classification, in a stable order. */
export function groupRows(
  preview: WorkbookPreview,
): Record<string, WorkbookRowPreview[]> {
  const grouped: Record<string, WorkbookRowPreview[]> = {};
  for (const classification of CLASSIFICATION_ORDER) grouped[classification] = [];
  for (const sheet of preview.sheets) {
    for (const row of sheet.rows) {
      const bucket = grouped[row.classification] ?? grouped.invalid;
      bucket.push(row);
    }
  }
  return grouped;
}

export function rowLabel(row: WorkbookRowPreview): string {
  const target = row.target_field ?? row.target_field_id ?? "target field";
  const source = row.source_field ?? "unknown source";
  const transformation = row.transformation === "direct" ? "direct" : row.transformation;
  return `${source} → ${target} (${transformation})`;
}

export function issueLabels(row: WorkbookRowPreview): string {
  return [...row.issues, ...row.warnings]
    .map((issue) => `${issue.code}: ${issue.message}`)
    .join("; ");
}

/** The revision line the reviewer needs: workbook against the live contract. */
export function revisionSummary(preview: WorkbookPreview): string {
  if (preview.stale) {
    return `Workbook revision ${preview.workbook_revision ?? "?"} · current revision ${preview.current_revision}`;
  }
  return `Workbook and contract both at revision ${preview.current_revision}`;
}

/** A short, honest reason the review cannot be applied yet. */
export function applyBlockedReason(preview: WorkbookPreview): string | null {
  if (preview.stale) return preview.stale_reason ?? "This workbook is stale.";
  if (preview.blocking_reasons.length > 0) {
    return preview.blocking_reasons[0].message;
  }
  return null;
}

export function changeSummary(change: ContractChange): string {
  const before = change.current ?? "not set";
  const after = change.proposed ?? "cleared";
  return `${before} → ${after}`;
}
