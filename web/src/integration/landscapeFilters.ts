/**
 * Deterministic Integration Landscape filtering.
 *
 * One typed filter model, one pure matcher, and one stable URL encoding. The
 * architecture state is deliberately *not* part of this model: it stays owned by
 * the existing active-state selector, so there is never a second, competing
 * state model inside the filter bar.
 *
 * Semantics:
 *  * an empty array (or `evidencePresence: "any"`) means "no constraint";
 *  * different categories combine with AND, values inside one category with OR;
 *  * the input landscape is never mutated and the output keeps the payload's
 *    original deterministic ordering.
 */

import {
  ENVIRONMENT_SCOPES,
  LIFECYCLE_STAGES,
  OPERATIONAL_STATUSES,
  type EnvironmentScope,
  type LifecycleStage,
  type OperationalStatus,
} from "../architectureFacts";
import {
  contractMediation,
  IMPLEMENTATION_STATUSES,
  INTERACTION_TYPE_LABELS,
  type IntegrationContractSummary,
  type IntegrationLandscape,
  type MediationSource,
} from "./integrationDesignModel";

/** Selectable value that matches a Contract whose fact is not recorded. */
export const UNSPECIFIED_FILTER_VALUE = "unspecified";

export type MediationMode = "direct" | "mediated";
export type EvidencePresence = "any" | "with_evidence" | "without_evidence";

export type IntegrationLandscapeFilters = {
  lifecycleStages: string[];
  operationalStatuses: string[];
  environmentScopes: string[];
  sourceSystemIds: string[];
  targetSystemIds: string[];
  interactionTypes: string[];
  informationObjectIds: string[];
  implementationStatuses: string[];
  mediationModes: MediationMode[];
  mediationSources: MediationSource[];
  contractIds: string[];
  evidencePresence: EvidencePresence;
};

export const EMPTY_LANDSCAPE_FILTERS: IntegrationLandscapeFilters = {
  lifecycleStages: [],
  operationalStatuses: [],
  environmentScopes: [],
  sourceSystemIds: [],
  targetSystemIds: [],
  interactionTypes: [],
  informationObjectIds: [],
  implementationStatuses: [],
  mediationModes: [],
  mediationSources: [],
  contractIds: [],
  evidencePresence: "any",
};

const withUnspecified = (values: readonly string[]): string[] => [
  ...values,
  UNSPECIFIED_FILTER_VALUE,
];

export const LIFECYCLE_FILTER_VALUES = withUnspecified(LIFECYCLE_STAGES);
export const OPERATIONAL_FILTER_VALUES = withUnspecified(OPERATIONAL_STATUSES);
export const ENVIRONMENT_FILTER_VALUES = withUnspecified(ENVIRONMENT_SCOPES);
export const INTERACTION_FILTER_VALUES = Object.keys(INTERACTION_TYPE_LABELS);
export const IMPLEMENTATION_FILTER_VALUES = [...IMPLEMENTATION_STATUSES];
export const MEDIATION_MODE_VALUES: MediationMode[] = ["direct", "mediated"];
export const MEDIATION_SOURCE_VALUES: MediationSource[] = [
  "explicit",
  "legacy_endpoint_heuristic",
  "none",
];
export const EVIDENCE_PRESENCE_VALUES: EvidencePresence[] = [
  "any",
  "with_evidence",
  "without_evidence",
];

/**
 * The URL keys in their fixed, deterministic order. Values are sorted before
 * serialization, so the same filter state always produces the same query string.
 */
export const FILTER_QUERY_KEYS: readonly [keyof IntegrationLandscapeFilters, string][] = [
  ["lifecycleStages", "il_lifecycle"],
  ["operationalStatuses", "il_operational"],
  ["environmentScopes", "il_environment"],
  ["sourceSystemIds", "il_source"],
  ["targetSystemIds", "il_target"],
  ["interactionTypes", "il_interaction"],
  ["informationObjectIds", "il_information"],
  ["implementationStatuses", "il_implementation"],
  ["mediationModes", "il_mediation"],
  ["mediationSources", "il_mediation_source"],
  ["contractIds", "il_contract"],
];

export const EVIDENCE_QUERY_KEY = "il_evidence";

const ALL_FILTER_QUERY_KEYS = [
  ...FILTER_QUERY_KEYS.map(([, key]) => key),
  EVIDENCE_QUERY_KEY,
];

/** Deduplicate and sort, so a filter set has exactly one canonical form. */
function canonical(values: readonly string[]): string[] {
  return [...new Set(values.filter((value) => value !== "" && value != null))].sort();
}

function canonicalAllowed(values: readonly string[], allowed: readonly string[]): string[] {
  const permitted = new Set(allowed);
  return canonical(values.filter((value) => permitted.has(value)));
}

/**
 * Drop unknown values, deduplicate, sort and fall back to the empty state.
 * Never throws, so a hand-edited or stale URL cannot break the workbench.
 */
export function normalizeFilters(
  raw: Partial<IntegrationLandscapeFilters> | null | undefined,
): IntegrationLandscapeFilters {
  if (!raw) return { ...EMPTY_LANDSCAPE_FILTERS };
  return {
    lifecycleStages: canonicalAllowed(raw.lifecycleStages ?? [], LIFECYCLE_FILTER_VALUES),
    operationalStatuses: canonicalAllowed(
      raw.operationalStatuses ?? [],
      OPERATIONAL_FILTER_VALUES,
    ),
    environmentScopes: canonicalAllowed(raw.environmentScopes ?? [], ENVIRONMENT_FILTER_VALUES),
    sourceSystemIds: canonical(raw.sourceSystemIds ?? []),
    targetSystemIds: canonical(raw.targetSystemIds ?? []),
    interactionTypes: canonicalAllowed(raw.interactionTypes ?? [], INTERACTION_FILTER_VALUES),
    informationObjectIds: canonical(raw.informationObjectIds ?? []),
    implementationStatuses: canonicalAllowed(
      raw.implementationStatuses ?? [],
      IMPLEMENTATION_FILTER_VALUES,
    ),
    mediationModes: canonicalAllowed(
      raw.mediationModes ?? [],
      MEDIATION_MODE_VALUES,
    ) as MediationMode[],
    mediationSources: canonicalAllowed(
      raw.mediationSources ?? [],
      MEDIATION_SOURCE_VALUES,
    ) as MediationSource[],
    contractIds: canonical(raw.contractIds ?? []),
    evidencePresence: EVIDENCE_PRESENCE_VALUES.includes(raw.evidencePresence as EvidencePresence)
      ? (raw.evidencePresence as EvidencePresence)
      : "any",
  };
}

const ARRAY_CATEGORIES: (keyof IntegrationLandscapeFilters)[] = [
  "lifecycleStages",
  "operationalStatuses",
  "environmentScopes",
  "sourceSystemIds",
  "targetSystemIds",
  "interactionTypes",
  "informationObjectIds",
  "implementationStatuses",
  "mediationModes",
  "mediationSources",
  "contractIds",
];

export function isFilterEmpty(filters: IntegrationLandscapeFilters): boolean {
  return (
    ARRAY_CATEGORIES.every((key) => (filters[key] as string[]).length === 0) &&
    filters.evidencePresence === "any"
  );
}

/** How many filter *categories* are active; the number shown in the filter bar. */
export function activeFilterCount(filters: IntegrationLandscapeFilters): number {
  let count = 0;
  for (const [key] of FILTER_QUERY_KEYS) {
    const value = filters[key];
    if (Array.isArray(value) && value.length > 0) count += 1;
  }
  if (filters.evidencePresence !== "any") count += 1;
  return count;
}

function matchesFact(value: string | null | undefined, selected: readonly string[]): boolean {
  if (selected.length === 0) return true;
  const normalised = value ?? UNSPECIFIED_FILTER_VALUE;
  return selected.includes(normalised);
}

function mediationModeOf(contract: IntegrationContractSummary): MediationMode {
  return contractMediation(contract).mediated ? "mediated" : "direct";
}

/**
 * Pure matcher. `true` means the Contract survives every active category.
 * Never mutates its arguments.
 */
export function matchesLandscapeFilters(
  contract: IntegrationContractSummary,
  filters: IntegrationLandscapeFilters,
): boolean {
  if (!matchesFact(contract.lifecycle_stage?.value, filters.lifecycleStages)) return false;
  if (!matchesFact(contract.operational_status?.value, filters.operationalStatuses)) return false;
  if (!matchesFact(contract.environment_scope?.value, filters.environmentScopes)) return false;
  if (
    filters.sourceSystemIds.length > 0 &&
    !filters.sourceSystemIds.includes(contract.source.system_id)
  ) {
    return false;
  }
  if (
    filters.targetSystemIds.length > 0 &&
    !filters.targetSystemIds.includes(contract.target.system_id)
  ) {
    return false;
  }
  if (
    filters.interactionTypes.length > 0 &&
    !filters.interactionTypes.includes(contract.interaction_type)
  ) {
    return false;
  }
  if (filters.informationObjectIds.length > 0) {
    const referenced = (contract.referenced_information_objects ?? []).map(
      (item) => item.object_id,
    );
    if (!referenced.some((objectId) => filters.informationObjectIds.includes(objectId))) {
      return false;
    }
  }
  if (
    filters.implementationStatuses.length > 0 &&
    !filters.implementationStatuses.includes(contract.implementation_status)
  ) {
    return false;
  }
  const mediation = contractMediation(contract);
  if (
    filters.mediationModes.length > 0 &&
    !filters.mediationModes.includes(mediationModeOf(contract))
  ) {
    return false;
  }
  if (
    filters.mediationSources.length > 0 &&
    !filters.mediationSources.includes(mediation.source)
  ) {
    return false;
  }
  if (filters.contractIds.length > 0 && !filters.contractIds.includes(contract.id)) {
    return false;
  }
  const evidenceCount = contract.evidence_count ?? 0;
  if (filters.evidencePresence === "with_evidence" && evidenceCount <= 0) return false;
  if (filters.evidencePresence === "without_evidence" && evidenceCount > 0) return false;
  return true;
}

/**
 * Apply the filters to a landscape, returning a new object. Ordering follows the
 * original payload exactly and the input is never mutated.
 */
export function filterLandscape(
  landscape: IntegrationLandscape,
  filters: IntegrationLandscapeFilters,
): IntegrationLandscape {
  if (isFilterEmpty(filters)) return landscape;
  return {
    ...landscape,
    contracts: landscape.contracts.filter((contract) =>
      matchesLandscapeFilters(contract, filters),
    ),
  };
}

function serializeValues(values: readonly string[]): string {
  return canonical(values).join(",");
}

/** Only the filter keys, in their fixed order, with sorted values. */
export function filtersToSearchParams(filters: IntegrationLandscapeFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, queryKey] of FILTER_QUERY_KEYS) {
    const value = filters[key];
    if (Array.isArray(value) && value.length > 0) params.set(queryKey, serializeValues(value));
  }
  if (filters.evidencePresence !== "any") {
    params.set(EVIDENCE_QUERY_KEY, filters.evidencePresence);
  }
  return params;
}

export function serializeFilters(filters: IntegrationLandscapeFilters): string {
  return filtersToSearchParams(filters).toString();
}

/**
 * Rebuild a full query string: all filter parameters are replaced, every
 * unrelated parameter is preserved in place.
 */
export function buildSearchString(
  originalSearch: string,
  filters: IntegrationLandscapeFilters,
): string {
  const params = new URLSearchParams(originalSearch.startsWith("?") ? originalSearch.slice(1) : originalSearch);
  for (const key of ALL_FILTER_QUERY_KEYS) params.delete(key);
  const filterParams = filtersToSearchParams(filters);
  const additions: [string, string][] = [];
  filterParams.forEach((value, key) => additions.push([key, value]));
  // Re-add in the fixed filter-key order, after the preserved parameters.
  for (const key of ALL_FILTER_QUERY_KEYS) {
    const match = additions.find(([candidate]) => candidate === key);
    if (match) params.append(match[0], match[1]);
  }
  return params.toString();
}

/** Parse a query string; unknown values are ignored and missing keys are empty. */
export function parseFilters(search: string): IntegrationLandscapeFilters {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const read = (queryKey: string): string[] => {
    const raw = params.getAll(queryKey).join(",");
    return raw ? raw.split(",").map((value) => value.trim()) : [];
  };
  return normalizeFilters({
    lifecycleStages: read("il_lifecycle"),
    operationalStatuses: read("il_operational"),
    environmentScopes: read("il_environment"),
    sourceSystemIds: read("il_source"),
    targetSystemIds: read("il_target"),
    interactionTypes: read("il_interaction"),
    informationObjectIds: read("il_information"),
    implementationStatuses: read("il_implementation"),
    mediationModes: read("il_mediation") as MediationMode[],
    mediationSources: read("il_mediation_source") as MediationSource[],
    contractIds: read("il_contract"),
    evidencePresence: (params.get(EVIDENCE_QUERY_KEY) as EvidencePresence | null) ?? "any",
  });
}

// --- Presentation helpers -----------------------------------------------------

export type FilterChip = {
  category: keyof IntegrationLandscapeFilters;
  value: string;
  label: string;
};

function labelFor(
  category: keyof IntegrationLandscapeFilters,
  value: string,
  resolve: (category: keyof IntegrationLandscapeFilters, value: string) => string,
): string {
  return resolve(category, value);
}

/**
 * The removable summary. Identity is always the category + raw value; the label
 * is presentation only, so display text can never become an identity.
 */
export function filterChips(
  filters: IntegrationLandscapeFilters,
  resolve: (category: keyof IntegrationLandscapeFilters, value: string) => string,
): FilterChip[] {
  const chips: FilterChip[] = [];
  for (const key of ARRAY_CATEGORIES) {
    const values = filters[key];
    if (!Array.isArray(values)) continue;
    for (const value of values) {
      chips.push({ category: key, value, label: labelFor(key, value, resolve) });
    }
  }
  if (filters.evidencePresence !== "any") {
    chips.push({
      category: "evidencePresence",
      value: filters.evidencePresence,
      label: labelFor("evidencePresence", filters.evidencePresence, resolve),
    });
  }
  return chips;
}

/** Remove exactly one chip, leaving every other category untouched. */
export function removeFilterChip(
  filters: IntegrationLandscapeFilters,
  chip: { category: keyof IntegrationLandscapeFilters; value: string },
): IntegrationLandscapeFilters {
  if (chip.category === "evidencePresence") {
    return { ...filters, evidencePresence: "any" };
  }
  const values = filters[chip.category];
  if (!Array.isArray(values)) return filters;
  return { ...filters, [chip.category]: values.filter((value) => value !== chip.value) };
}

export const LANDSCAPE_FACT_LABELS: Record<string, string> = {
  lifecycleStages: "Lifecycle",
  operationalStatuses: "Operational",
  environmentScopes: "Environment",
  sourceSystemIds: "Source",
  targetSystemIds: "Target",
  interactionTypes: "Flow",
  informationObjectIds: "Information",
  implementationStatuses: "Implementation",
  mediationModes: "Mediation",
  mediationSources: "Mediation source",
  contractIds: "Contract",
  evidencePresence: "Evidence",
};

export const MEDIATION_MODE_LABELS: Record<MediationMode, string> = {
  direct: "Direct",
  mediated: "Mediated",
};

export const MEDIATION_SOURCE_LABELS: Record<MediationSource, string> = {
  explicit: "Explicit mediator",
  legacy_endpoint_heuristic: "Legacy endpoint heuristic",
  none: "No mediation",
};

export const EVIDENCE_PRESENCE_LABELS: Record<EvidencePresence, string> = {
  any: "Any",
  with_evidence: "With evidence",
  without_evidence: "Without evidence",
};

export const UNSPECIFIED_OPTION_LABEL = "Unspecified";
