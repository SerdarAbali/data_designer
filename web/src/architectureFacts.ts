/**
 * Controlled vocabularies for generic architecture facts.
 *
 * These three facts are deliberately separate from architecture state
 * (Current/Candidate/Target) and from a contract's implementation status.
 * Keeping the words in one module means the system inspector, the contract
 * inspector and the type definitions cannot drift apart.
 */

export type LifecycleStage =
  | "strategic"
  | "planned"
  | "active"
  | "transitional"
  | "legacy"
  | "retiring"
  | "retired";

export type OperationalStatus =
  | "unknown"
  | "proposed"
  | "tested"
  | "live"
  | "degraded"
  | "suspended"
  | "retiring"
  | "decommissioned";

export type EnvironmentScope =
  | "unknown"
  | "development"
  | "test"
  | "sandbox"
  | "staging"
  | "production"
  | "mixed";

export type ArchitectureFactKey =
  | "lifecycle_stage"
  | "operational_status"
  | "environment_scope";

export const LIFECYCLE_STAGES: LifecycleStage[] = [
  "strategic",
  "planned",
  "active",
  "transitional",
  "legacy",
  "retiring",
  "retired",
];

export const OPERATIONAL_STATUSES: OperationalStatus[] = [
  "unknown",
  "proposed",
  "tested",
  "live",
  "degraded",
  "suspended",
  "retiring",
  "decommissioned",
];

export const ENVIRONMENT_SCOPES: EnvironmentScope[] = [
  "unknown",
  "development",
  "test",
  "sandbox",
  "staging",
  "production",
  "mixed",
];

export const LIFECYCLE_LABELS: Record<LifecycleStage, string> = {
  strategic: "Strategic",
  planned: "Planned",
  active: "Active",
  transitional: "Transitional",
  legacy: "Legacy",
  retiring: "Retiring",
  retired: "Retired",
};

export const OPERATIONAL_STATUS_LABELS: Record<OperationalStatus, string> = {
  unknown: "Unknown",
  proposed: "Proposed",
  tested: "Tested",
  live: "Live",
  degraded: "Degraded",
  suspended: "Suspended",
  retiring: "Retiring",
  decommissioned: "Decommissioned",
};

export const ENVIRONMENT_SCOPE_LABELS: Record<EnvironmentScope, string> = {
  unknown: "Unknown",
  development: "Development",
  test: "Test",
  sandbox: "Sandbox",
  staging: "Staging",
  production: "Production",
  mixed: "Mixed",
};

export const ARCHITECTURE_FACT_LABELS: Record<ArchitectureFactKey, string> = {
  lifecycle_stage: "Lifecycle stage",
  operational_status: "Operational status",
  environment_scope: "Environment scope",
};

export const ARCHITECTURE_FACT_KEYS: ArchitectureFactKey[] = [
  "lifecycle_stage",
  "operational_status",
  "environment_scope",
];

export const UNSPECIFIED_FACT_LABEL = "Unspecified";

const VALUE_LABELS: Record<string, string> = {
  ...LIFECYCLE_LABELS,
  ...OPERATIONAL_STATUS_LABELS,
  ...ENVIRONMENT_SCOPE_LABELS,
};

/** Human label for a fact value; `null`/empty is shown as "Unspecified". */
export function architectureFactLabel(value: string | null | undefined): string {
  if (!value) return UNSPECIFIED_FACT_LABEL;
  return VALUE_LABELS[value] ?? value.replace(/_/g, " ");
}

/** True when a state override is present and differs from the baseline. */
export function factDiffersFromCanonical(
  override: string | null | undefined,
  canonical: string | null | undefined,
): boolean {
  return Boolean(override) && override !== canonical;
}
