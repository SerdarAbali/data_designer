import { useMemo, useState } from "react";

import {
  architectureFactLabel,
  ENVIRONMENT_SCOPE_LABELS,
  LIFECYCLE_LABELS,
  OPERATIONAL_STATUS_LABELS,
} from "../architectureFacts";
import {
  IMPLEMENTATION_STATUS_LABELS,
  INTERACTION_TYPE_LABELS,
  type IntegrationLandscape,
} from "./integrationDesignModel";
import {
  activeFilterCount,
  EVIDENCE_PRESENCE_LABELS,
  EVIDENCE_PRESENCE_VALUES,
  filterChips,
  LANDSCAPE_FACT_LABELS,
  LIFECYCLE_FILTER_VALUES,
  MEDIATION_MODE_LABELS,
  MEDIATION_MODE_VALUES,
  MEDIATION_SOURCE_LABELS,
  MEDIATION_SOURCE_VALUES,
  OPERATIONAL_FILTER_VALUES,
  ENVIRONMENT_FILTER_VALUES,
  INTERACTION_FILTER_VALUES,
  IMPLEMENTATION_FILTER_VALUES,
  removeFilterChip,
  UNSPECIFIED_FILTER_VALUE,
  UNSPECIFIED_OPTION_LABEL,
  type EvidencePresence,
  type IntegrationLandscapeFilters,
  type MediationMode,
} from "./landscapeFilters";
import type { MediationSource } from "./integrationDesignModel";

type Props = {
  filters: IntegrationLandscapeFilters;
  landscape: IntegrationLandscape;
  /** How many Contracts exist in the selected state before filtering. */
  totalContracts: number;
  /** How many survive the filters (and the existing search box). */
  visibleContracts: number;
  onChange: (next: IntegrationLandscapeFilters) => void;
  onClear: () => void;
};

type Option = { value: string; label: string };

const UNSPECIFIED: Option = { value: UNSPECIFIED_FILTER_VALUE, label: UNSPECIFIED_OPTION_LABEL };

function vocabularyOptions(
  values: readonly string[],
  labels: Record<string, string>,
): Option[] {
  return values.map((value) => ({
    value,
    label:
      value === UNSPECIFIED_FILTER_VALUE
        ? UNSPECIFIED_OPTION_LABEL
        : labels[value] ?? architectureFactLabel(value),
  }));
}

function toggleValue(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

export default function LandscapeFilterBar({
  filters,
  landscape,
  totalContracts,
  visibleContracts,
  onChange,
  onClear,
}: Props) {
  const [open, setOpen] = useState(false);

  const systemOptions = useMemo<Option[]>(() => {
    const seen = new Map<string, string>();
    for (const contract of landscape.contracts) {
      seen.set(contract.source.system_id, contract.source.system_name);
      seen.set(contract.target.system_id, contract.target.system_name);
    }
    return [...seen.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label) || a.value.localeCompare(b.value));
  }, [landscape.contracts]);

  const contractOptions = useMemo<Option[]>(
    () =>
      landscape.contracts
        .map((contract) => ({ value: contract.id, label: contract.name }))
        .sort((a, b) => a.label.localeCompare(b.label) || a.value.localeCompare(b.value)),
    [landscape.contracts],
  );

  const informationOptions = useMemo<Option[]>(() => {
    const seen = new Map<string, string>();
    for (const contract of landscape.contracts) {
      for (const reference of contract.referenced_information_objects ?? []) {
        seen.set(reference.object_id, reference.label || reference.name);
      }
    }
    return [...seen.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label) || a.value.localeCompare(b.value));
  }, [landscape.contracts]);

  // A selected value that the current payload no longer offers is stale, not an
  // error: it stays selected, is labelled "(unavailable)" and remains removable.
  function withStale(options: Option[], selected: readonly string[]): Option[] {
    const known = new Set(options.map((option) => option.value));
    const stale = selected
      .filter((value) => !known.has(value))
      .sort()
      .map((value) => ({ value, label: `${value} (unavailable)` }));
    return [...stale, ...options];
  }

  const chipLabels = useMemo(() => {
    const labels: Record<string, Record<string, string>> = {
      lifecycleStages: LIFECYCLE_LABELS,
      operationalStatuses: OPERATIONAL_STATUS_LABELS,
      environmentScopes: ENVIRONMENT_SCOPE_LABELS,
      interactionTypes: INTERACTION_TYPE_LABELS,
      implementationStatuses: IMPLEMENTATION_STATUS_LABELS as Record<string, string>,
      mediationModes: MEDIATION_MODE_LABELS as Record<string, string>,
      mediationSources: MEDIATION_SOURCE_LABELS as Record<string, string>,
      evidencePresence: EVIDENCE_PRESENCE_LABELS as Record<string, string>,
    };
    const systemNames = new Map(systemOptions.map((option) => [option.value, option.label]));
    const contractNames = new Map(contractOptions.map((option) => [option.value, option.label]));
    const informationNames = new Map(
      informationOptions.map((option) => [option.value, option.label]),
    );
    return { labels, systemNames, contractNames, informationNames };
  }, [systemOptions, contractOptions, informationOptions]);

  function chipLabel(category: string, value: string): string {
    if (value === UNSPECIFIED_FILTER_VALUE) return UNSPECIFIED_OPTION_LABEL;
    if (category === "sourceSystemIds" || category === "targetSystemIds") {
      return chipLabels.systemNames.get(value) ?? value;
    }
    if (category === "contractIds") return chipLabels.contractNames.get(value) ?? value;
    if (category === "informationObjectIds") {
      return chipLabels.informationNames.get(value) ?? value;
    }
    return chipLabels.labels[category]?.[value] ?? value;
  }

  const chips = filterChips(filters, chipLabel);
  const count = activeFilterCount(filters);

  function group(
    legend: string,
    category: keyof IntegrationLandscapeFilters,
    options: Option[],
    selected: readonly string[],
    hint?: string,
  ) {
    return (
      <fieldset className="landscape-filter-group" key={legend}>
        <legend>{legend}</legend>
        {hint && <p className="landscape-filter-hint">{hint}</p>}
        <div className="landscape-filter-options">
          {withStale(options, selected).map((option) => (
            <label key={option.value} className="landscape-filter-option" title={option.label}>
              <input
                type="checkbox"
                checked={selected.includes(option.value)}
                onChange={() =>
                  onChange({ ...filters, [category]: toggleValue([...selected], option.value) })
                }
              />
              <span className="landscape-filter-option-label">{option.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  const hasUnspecified = landscape.contracts.some(
    (contract) =>
      !contract.lifecycle_stage?.value ||
      !contract.operational_status?.value ||
      !contract.environment_scope?.value,
  );
  const noInformation = landscape.contracts.some(
    (contract) => (contract.referenced_information_objects ?? []).length === 0,
  );
  const noEvidence = landscape.contracts.some((contract) => (contract.evidence_count ?? 0) === 0);

  return (
    <section className="landscape-filter-bar" aria-label="Landscape filters">
      <div className="landscape-filter-summary">
        <button
          type="button"
          className="landscape-filter-toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          Filters
          <span className="landscape-filter-count" aria-label={`${count} active filters`}>
            {count}
          </span>
        </button>
        <span className="landscape-filter-result" role="status">
          {visibleContracts} of {totalContracts} contracts
        </span>
        {count > 0 && (
          <button type="button" className="landscape-filter-clear" onClick={onClear}>
            Clear all
          </button>
        )}
        {chips.length > 0 && (
          <ul className="landscape-filter-chips" aria-label="Active filters">
            {chips.map((chip) => (
              <li key={`${chip.category}:${chip.value}`}>
                <button
                  type="button"
                  className="landscape-filter-chip"
                  aria-label={`Remove ${chip.label}`}
                  title={`Remove ${chip.label}`}
                  onClick={() => onChange(removeFilterChip(filters, chip))}
                >
                  <span className="landscape-filter-chip-category">
                    {LANDSCAPE_FACT_LABELS[chip.category] ?? chip.category}
                  </span>
                  <span className="landscape-filter-chip-label">{chip.label}</span>
                  <span aria-hidden="true">✕</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {open && (
        <div className="landscape-filter-panel">
          <div className="landscape-filter-columns">
            {group(
              "Status",
              "lifecycleStages",
              vocabularyOptions(LIFECYCLE_FILTER_VALUES, LIFECYCLE_LABELS),
              filters.lifecycleStages,
            )}
            {group(
              "Operational status",
              "operationalStatuses",
              vocabularyOptions(OPERATIONAL_FILTER_VALUES, OPERATIONAL_STATUS_LABELS),
              filters.operationalStatuses,
            )}
            {group(
              "Environment",
              "environmentScopes",
              vocabularyOptions(ENVIRONMENT_FILTER_VALUES, ENVIRONMENT_SCOPE_LABELS),
              filters.environmentScopes,
            )}
            {group(
              "Implementation",
              "implementationStatuses",
              vocabularyOptions(
                IMPLEMENTATION_FILTER_VALUES,
                IMPLEMENTATION_STATUS_LABELS as Record<string, string>,
              ),
              filters.implementationStatuses,
            )}
            {group("Source system", "sourceSystemIds", systemOptions, filters.sourceSystemIds)}
            {group("Target system", "targetSystemIds", systemOptions, filters.targetSystemIds)}
            {group(
              "Flow",
              "interactionTypes",
              vocabularyOptions(INTERACTION_FILTER_VALUES, INTERACTION_TYPE_LABELS),
              filters.interactionTypes,
            )}
            {group(
              "Mediation",
              "mediationModes",
              MEDIATION_MODE_VALUES.map((value) => ({
                value,
                label: MEDIATION_MODE_LABELS[value as MediationMode],
              })),
              filters.mediationModes,
            )}
            {group(
              "Mediation source",
              "mediationSources",
              MEDIATION_SOURCE_VALUES.map((value) => ({
                value,
                label: MEDIATION_SOURCE_LABELS[value as MediationSource],
              })),
              filters.mediationSources,
            )}
            {group(
              "Information",
              "informationObjectIds",
              informationOptions,
              filters.informationObjectIds,
              noInformation
                ? "Contracts with no mapped Catalog objects have no information references."
                : undefined,
            )}
            {group("Contract", "contractIds", contractOptions, filters.contractIds)}
            <fieldset className="landscape-filter-group">
              <legend>Evidence</legend>
              {noEvidence && (
                <p className="landscape-filter-hint">
                  Contracts with no recorded evidence show a count of zero.
                </p>
              )}
              <div className="landscape-filter-options">
                {EVIDENCE_PRESENCE_VALUES.map((value) => (
                  <label key={value} className="landscape-filter-option">
                    <input
                      type="radio"
                      name="landscape-evidence"
                      checked={filters.evidencePresence === value}
                      onChange={() =>
                        onChange({ ...filters, evidencePresence: value as EvidencePresence })
                      }
                    />
                    <span className="landscape-filter-option-label">
                      {EVIDENCE_PRESENCE_LABELS[value]}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <p className="landscape-filter-footnote">
            {hasUnspecified
              ? "Some visible contracts have unspecified metadata; choose \u201cUnspecified\u201d to match them."
              : "Filters combine with AND between groups and OR inside a group."}
          </p>
        </div>
      )}
    </section>
  );
}
