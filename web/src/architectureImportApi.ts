import type { ImportIssue, ImportKind, MatchMethod, RowDecision } from "./architectureImport";
import { ApiError, api as request } from "./apiClient";

export class ImportApiError extends Error {
  status: number;
  issues: readonly ImportIssue[];

  constructor(message: string, status: number, issues: readonly ImportIssue[] = []) {
    super(message);
    this.status = status;
    this.issues = issues;
  }
}

export type ImportMatchCandidate = {
  id: string;
  kind: string;
  name: string;
  method: MatchMethod;
  score: number | null;
};

export type ImportRowPreview = {
  row_number: number;
  external_id: string | null;
  name: string | null;
  values: Record<string, string>;
  issues: ImportIssue[];
  warnings: ImportIssue[];
  matches: ImportMatchCandidate[];
  suggested_decision: RowDecision;
};

export type ImportPreviewResponse = {
  import_type: ImportKind;
  rows: ImportRowPreview[];
  blocked_count: number;
  resolved_reference_counts: Record<string, number>;
};

export type ImportRowResult = {
  row_number: number;
  external_id?: string | null;
  status: string;
  target_kind: string | null;
  target_id: string | null;
  message: string | null;
  issues: ImportIssue[];
};

export type ImportBatch = {
  id: string;
  workspace_id: string;
  source_filename: string;
  sheet_name: string;
  import_type: ImportKind;
  status: "applied" | "undone" | "undo_blocked";
  counts: Record<string, number>;
  rows: ImportRowResult[];
  imported_at: string;
  undone_at: string | null;
};

export type ImportCommitPayload = {
  import_type: ImportKind;
  headers: string[];
  rows: string[][];
  column_mapping: Record<string, string>;
  source_filename: string;
  sheet_name: string;
  decisions: { row_number: number; decision: RowDecision; target_id?: string | null }[];
};

export type IncludeObjectsResult = {
  added_occurrences: number;
  added_relationships: number;
  skipped: { kind: string; id: string; name: string | null; message: string }[];
};

function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first = detail[0] as { msg?: string };
  const message = (first.msg ?? "The import request was rejected").replace(/^Value error, /, "");
  return detail.length > 1 ? `${message} (+${detail.length - 1} more)` : message;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await request<T>(path, init);
  } catch (caught) {
    if (caught instanceof ApiError) {
      throw new ImportApiError(
        validationMessage(caught.detail) ?? caught.message,
        caught.status,
      );
    }
    throw caught;
  }
}

export function previewImport(
  workspaceId: string,
  payload: Omit<ImportCommitPayload, "decisions">,
): Promise<ImportPreviewResponse> {
  return api(`/api/workspaces/${workspaceId}/imports/preview`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function commitImport(
  workspaceId: string,
  payload: ImportCommitPayload,
): Promise<ImportBatch> {
  return api(`/api/workspaces/${workspaceId}/imports/commit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listImportBatches(workspaceId: string): Promise<ImportBatch[]> {
  return api(`/api/workspaces/${workspaceId}/imports`);
}

export function listArchitectureStates(
  workspaceId: string,
): Promise<{ id: string; state_type: string }[]> {
  return api(`/api/workspaces/${workspaceId}/states`);
}

export function undoImportBatch(workspaceId: string, batchId: string): Promise<ImportBatch> {
  return api(`/api/workspaces/${workspaceId}/imports/${batchId}/undo`, { method: "POST" });
}

export function includeImportedObjects(
  workspaceId: string,
  stateId: string,
  body: {
    system_ids: string[];
    architecture_object_ids: string[];
    integration_ids: string[];
    visualize_solution_membership: boolean;
  },
): Promise<IncludeObjectsResult> {
  return api(`/api/workspaces/${workspaceId}/states/${stateId}/include-objects`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
