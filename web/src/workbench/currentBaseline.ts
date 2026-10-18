/**
 * Client-side model for the Current baseline lifecycle.
 *
 * The server owns the policy: it decides whether a state accepts writes, whether
 * a baseline can be locked, and it records the lock actor and time. The studio
 * only labels what the server reported and never decides on its own that a
 * baseline may be locked.
 */

import type { ArchitectureState, BaselineStatus } from "../architectureTypes";

export type BaselineIssue = {
  code: string;
  message: string;
  count?: number;
};

export type BaselineValidation = {
  blocking: BaselineIssue[];
  warnings: BaselineIssue[];
  summary: Record<string, unknown>;
};

export type BaselineLockResponse = {
  state: ArchitectureState;
  validation: BaselineValidation;
  locked: boolean;
};

export const BASELINE_STATUS_LABELS: Record<BaselineStatus, string> = {
  draft: "Current baseline draft",
  locked: "Current baseline locked",
};

export const BASELINE_SUMMARY_FIELDS: { key: string; label: string }[] = [
  { key: "object_count", label: "Objects captured" },
  { key: "node_count", label: "Canvas nodes" },
  { key: "relationship_count", label: "Canvas relationships" },
  { key: "included_systems", label: "Catalog systems included" },
  { key: "included_contracts", label: "Contracts included" },
];

/** The status line the workbench shows for the Current baseline. */
export function baselineStatusLabel(state: ArchitectureState | null): string {
  if (!state) return "";
  if (state.state_type !== "current") return "";
  return state.baseline_status === "draft"
    ? BASELINE_STATUS_LABELS.draft
    : BASELINE_STATUS_LABELS.locked;
}

/** Who locked the baseline and when, when that provenance exists. */
export function baselineLockSummary(state: ArchitectureState | null): string | null {
  if (!state || state.state_type !== "current" || state.baseline_status !== "locked") {
    return null;
  }
  const parts: string[] = [];
  if (state.baseline_locked_by) parts.push(`by ${state.baseline_locked_by.slice(0, 8)}`);
  if (state.baseline_locked_at) parts.push(`on ${state.baseline_locked_at.slice(0, 10)}`);
  if (parts.length === 0) return "Provided baseline, not locked by a user.";
  return `Locked ${parts.join(" ")}.`;
}

/** The reason the lock cannot proceed yet, or null when it can. */
export function baselineBlockingReason(validation: BaselineValidation | null): string | null {
  if (!validation || validation.blocking.length === 0) return null;
  return validation.blocking[0].message;
}

/** An empty capture needs an extra, explicit confirmation before it can lock. */
export function baselineNeedsEmptyConfirmation(validation: BaselineValidation | null): boolean {
  return Boolean(validation) && validation!.warnings.some((issue) => issue.code === "empty_baseline");
}

export function baselineCanLock(validation: BaselineValidation | null): boolean {
  return Boolean(validation) && validation!.blocking.length === 0;
}

/** The summary entries worth showing, in a fixed order. */
export function baselineSummary(validation: BaselineValidation | null): { label: string; value: string }[] {
  if (!validation) return [];
  return BASELINE_SUMMARY_FIELDS.filter((field) => validation.summary[field.key] !== undefined).map(
    (field) => ({ label: field.label, value: String(validation.summary[field.key]) }),
  );
}

export function issueLabel(issue: BaselineIssue): string {
  const count = issue.count && issue.count > 1 ? ` (${issue.count})` : "";
  return `${issue.code}: ${issue.message}${count}`;
}
