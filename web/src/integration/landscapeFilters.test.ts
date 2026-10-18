import { describe, expect, it } from "vitest";

import type { IntegrationContractSummary, IntegrationLandscape } from "./integrationDesignModel";
import {
  activeFilterCount,
  buildSearchString,
  EMPTY_LANDSCAPE_FILTERS,
  filterLandscape,
  filterChips,
  isFilterEmpty,
  matchesLandscapeFilters,
  normalizeFilters,
  parseFilters,
  removeFilterChip,
  serializeFilters,
  UNSPECIFIED_FILTER_VALUE,
  type IntegrationLandscapeFilters,
} from "./landscapeFilters";

function emptyFact(): IntegrationContractSummary["lifecycle_stage"] {
  return { value: null, canonical: null, override: null, overridden: false };
}

function fact(value: string | null): IntegrationContractSummary["lifecycle_stage"] {
  return { value, canonical: value, override: null, overridden: false };
}

function contract(overrides: Partial<IntegrationContractSummary> = {}): IntegrationContractSummary {
  return {
    id: "int-1",
    name: "Contract one",
    description: null,
    interaction_type: "REQUEST_RESPONSE",
    pattern: "request_reply",
    implementation_status: "built",
    revision: 1,
    updated_at: null,
    status: "built",
    source: {
      system_id: "sys-crm",
      system_name: "CRM",
      object_id: "obj-cust",
      object_name: "Customer",
      is_runtime: false,
    },
    target: {
      system_id: "sys-erp",
      system_name: "ERP",
      object_id: "obj-acct",
      object_name: "Account",
      is_runtime: false,
    },
    producer_interface: null,
    consumer_interface: null,
    has_request_graph: false,
    has_response_graph: false,
    has_error_graph: false,
    specification: {},
    target_fields_mapped: 0,
    target_fields_total: 0,
    scenario_count: 0,
    evidence_count: 0,
    referenced_information_objects: [],
    lifecycle_stage: emptyFact(),
    operational_status: emptyFact(),
    environment_scope: emptyFact(),
    ...overrides,
  };
}

function landscape(contracts: IntegrationContractSummary[]): IntegrationLandscape {
  return { state_id: "state-1", state_type: "candidate", editable: true, contracts, interfaces: [] };
}

const filters = (
  overrides: Partial<IntegrationLandscapeFilters> = {},
): IntegrationLandscapeFilters => ({ ...EMPTY_LANDSCAPE_FILTERS, ...overrides });

const crm = contract({ id: "int-crm", name: "CRM to ERP" });
const legacy = contract({
  id: "int-legacy",
  name: "Legacy runtime",
  target: {
    system_id: "sys-runtime",
    system_name: "Integration Runtime",
    object_id: "obj-queue",
    object_name: "Queue",
    is_runtime: true,
  },
});
const explicit = contract({
  id: "int-explicit",
  name: "Explicit mediator",
  mediator: {
    system_id: "sys-frends",
    system_name: "FRENDS",
    is_runtime: true,
    responsibility: "Routes.",
    explicit: true,
  },
  explicit_mediator: true,
  mediated: true,
  mediation_source: "explicit",
});
const withFacts = contract({
  id: "int-facts",
  name: "Facts",
  lifecycle_stage: fact("active"),
  operational_status: fact("live"),
  environment_scope: fact("production"),
  implementation_status: "verified",
  evidence_count: 3,
  referenced_information_objects: [
    { object_id: "obj-acct", name: "account", label: "Account", anchors: ["target"] },
  ],
  interaction_type: "ONE_WAY",
});

const ids = (result: IntegrationLandscape) => result.contracts.map((item) => item.id);

describe("matchesLandscapeFilters", () => {
  it("returns the original landscape unchanged when no filter is set", () => {
    const input = landscape([crm, legacy, explicit]);
    expect(isFilterEmpty(EMPTY_LANDSCAPE_FILTERS)).toBe(true);
    expect(filterLandscape(input, EMPTY_LANDSCAPE_FILTERS)).toBe(input);
  });

  it("filters by effective lifecycle stage", () => {
    expect(ids(filterLandscape(landscape([crm, withFacts]), filters({ lifecycleStages: ["active"] })))).toEqual([
      "int-facts",
    ]);
  });

  it("filters by effective operational status", () => {
    expect(
      ids(filterLandscape(landscape([crm, withFacts]), filters({ operationalStatuses: ["live"] }))),
    ).toEqual(["int-facts"]);
  });

  it("filters by effective environment scope", () => {
    expect(
      ids(filterLandscape(landscape([crm, withFacts]), filters({ environmentScopes: ["production"] }))),
    ).toEqual(["int-facts"]);
  });

  it("matches the business source and never the mediator", () => {
    const all = landscape([crm, explicit, legacy]);
    expect(ids(filterLandscape(all, filters({ sourceSystemIds: ["sys-crm"] })))).toEqual([
      "int-crm",
      "int-explicit",
      "int-legacy",
    ]);
    // FRENDS mediates int-explicit but is not its source.
    expect(ids(filterLandscape(all, filters({ sourceSystemIds: ["sys-frends"] })))).toEqual([]);
  });

  it("matches the business target and never the mediator", () => {
    const all = landscape([crm, explicit, legacy]);
    expect(ids(filterLandscape(all, filters({ targetSystemIds: ["sys-erp"] })))).toEqual([
      "int-crm",
      "int-explicit",
    ]);
    // The legacy heuristic runtime is a real endpoint, so it is a legitimate target.
    expect(ids(filterLandscape(all, filters({ targetSystemIds: ["sys-runtime"] })))).toEqual([
      "int-legacy",
    ]);
    // FRENDS mediates int-explicit but is not its target.
    expect(ids(filterLandscape(all, filters({ targetSystemIds: ["sys-frends"] })))).toEqual([]);
  });

  it("filters by interaction type", () => {
    expect(
      ids(filterLandscape(landscape([crm, withFacts]), filters({ interactionTypes: ["ONE_WAY"] }))),
    ).toEqual(["int-facts"]);
  });

  it("filters by referenced information object", () => {
    expect(
      ids(
        filterLandscape(
          landscape([crm, withFacts]),
          filters({ informationObjectIds: ["obj-acct"] }),
        ),
      ),
    ).toEqual(["int-facts"]);
  });

  it("filters by implementation status", () => {
    expect(
      ids(
        filterLandscape(landscape([crm, withFacts]), filters({ implementationStatuses: ["verified"] })),
      ),
    ).toEqual(["int-facts"]);
  });

  it("filters direct-only and mediated-only contracts", () => {
    const all = landscape([crm, explicit, legacy]);
    expect(ids(filterLandscape(all, filters({ mediationModes: ["direct"] })))).toEqual(["int-crm"]);
    expect(ids(filterLandscape(all, filters({ mediationModes: ["mediated"] })))).toEqual([
      "int-explicit",
      "int-legacy",
    ]);
  });

  it("filters explicit mediation and the legacy heuristic separately", () => {
    const all = landscape([crm, explicit, legacy]);
    expect(
      ids(filterLandscape(all, filters({ mediationSources: ["explicit"] }))),
    ).toEqual(["int-explicit"]);
    expect(
      ids(filterLandscape(all, filters({ mediationSources: ["legacy_endpoint_heuristic"] }))),
    ).toEqual(["int-legacy"]);
    expect(ids(filterLandscape(all, filters({ mediationSources: ["none"] })))).toEqual(["int-crm"]);
  });

  it("filters by stable contract id", () => {
    expect(ids(filterLandscape(landscape([crm, withFacts]), filters({ contractIds: ["int-facts"] })))).toEqual([
      "int-facts",
    ]);
  });

  it("filters by evidence presence", () => {
    const all = landscape([crm, withFacts]);
    expect(ids(filterLandscape(all, filters({ evidencePresence: "with_evidence" })))).toEqual([
      "int-facts",
    ]);
    expect(ids(filterLandscape(all, filters({ evidencePresence: "without_evidence" })))).toEqual([
      "int-crm",
    ]);
  });

  it("combines categories with AND", () => {
    const result = filterLandscape(
      landscape([crm, withFacts]),
      filters({ lifecycleStages: ["active"], implementationStatuses: ["verified"] }),
    );
    expect(ids(result)).toEqual(["int-facts"]);
    const none = filterLandscape(
      landscape([crm, withFacts]),
      filters({ lifecycleStages: ["active"], sourceSystemIds: ["sys-erp"] }),
    );
    expect(ids(none)).toEqual([]);
  });

  it("combines values inside one category with OR", () => {
    const result = filterLandscape(
      landscape([crm, legacy, explicit]),
      filters({ mediationSources: ["explicit", "legacy_endpoint_heuristic"] }),
    );
    expect(ids(result)).toEqual(["int-legacy", "int-explicit"]);
  });

  it("matches unspecified metadata through the explicit unspecified value", () => {
    const result = filterLandscape(
      landscape([crm, withFacts]),
      filters({ lifecycleStages: [UNSPECIFIED_FILTER_VALUE] }),
    );
    expect(ids(result)).toEqual(["int-crm"]);
  });

  it("preserves the payload order and never mutates the input", () => {
    const input = landscape([crm, legacy, explicit]);
    const snapshot = input.contracts.map((item) => item.id);
    const result = filterLandscape(input, filters({ mediationModes: ["mediated"] }));
    expect(ids(result)).toEqual(["int-legacy", "int-explicit"]);
    expect(input.contracts.map((item) => item.id)).toEqual(snapshot);
  });

  it("ignores a duplicate selection", () => {
    const duplicated = { ...filters(), contractIds: ["int-crm", "int-crm"] };
    expect(ids(filterLandscape(landscape([crm, legacy]), duplicated))).toEqual(["int-crm"]);
  });

  it("treats a filter with only unknown values as no constraint", () => {
    const normalized = normalizeFilters({
      lifecycleStages: ["not-a-stage"],
      mediationModes: ["sideways" as never],
    });
    expect(isFilterEmpty(normalized)).toBe(true);
  });
});

describe("filter normalization", () => {
  it("deduplicates and sorts every category", () => {
    const normalized = normalizeFilters({
      lifecycleStages: ["planned", "active", "planned"],
      contractIds: ["b", "a", "b"],
      evidencePresence: "with_evidence",
    });
    expect(normalized.lifecycleStages).toEqual(["active", "planned"]);
    expect(normalized.contractIds).toEqual(["a", "b"]);
  });

  it("counts active categories, not active values", () => {
    expect(activeFilterCount(filters({ lifecycleStages: ["active", "planned"], contractIds: ["a"] }))).toBe(2);
    expect(activeFilterCount(filters({ evidencePresence: "with_evidence" }))).toBe(1);
    expect(activeFilterCount(EMPTY_LANDSCAPE_FILTERS)).toBe(0);
  });
});

describe("URL serialization", () => {
  it("writes keys in a fixed order with sorted values", () => {
    const filtersA = filters({
      lifecycleStages: ["planned", "active"],
      sourceSystemIds: ["sys-z", "sys-a"],
    });
    expect(serializeFilters(filtersA)).toBe(
      "il_lifecycle=active%2Cplanned&il_source=sys-a%2Csys-z",
    );
    // A different input order serializes identically.
    const filtersB = filters({
      lifecycleStages: ["active", "planned"],
      sourceSystemIds: ["sys-a", "sys-z"],
    });
    expect(serializeFilters(filtersB)).toBe(serializeFilters(filtersA));
  });

  it("round-trips through the query string", () => {
    const original = normalizeFilters({
      lifecycleStages: ["active"],
      environmentScopes: ["production"],
      sourceSystemIds: ["sys-crm"],
      mediationSources: ["explicit", "none"],
      evidencePresence: "with_evidence",
    });
    expect(parseFilters(`?${serializeFilters(original)}`)).toEqual(original);
  });

  it("ignores unknown values when parsing", () => {
    const parsed = parseFilters("?il_lifecycle=bogus,active&il_mediation=sideways");
    expect(parsed.lifecycleStages).toEqual(["active"]);
    expect(parsed.mediationModes).toEqual([]);
  });

  it("produces empty filters from a missing or empty query", () => {
    expect(parseFilters("")).toEqual(EMPTY_LANDSCAPE_FILTERS);
    expect(parseFilters("?")).toEqual(EMPTY_LANDSCAPE_FILTERS);
  });

  it("preserves unrelated query parameters", () => {
    const search = buildSearchString("?tab=catalog&il_lifecycle=active", filters({
      sourceSystemIds: ["sys-crm"],
    }));
    const params = new URLSearchParams(search);
    expect(params.get("tab")).toBe("catalog");
    expect(params.get("il_lifecycle")).toBeNull();
    expect(params.get("il_source")).toBe("sys-crm");
  });

  it("removes every filter parameter when the filters are cleared", () => {
    const search = buildSearchString(
      "?tab=catalog&il_lifecycle=active&il_evidence=with_evidence&il_contract=a",
      { ...EMPTY_LANDSCAPE_FILTERS },
    );
    const params = new URLSearchParams(search);
    expect(params.get("tab")).toBe("catalog");
    expect([...params.keys()]).toEqual(["tab"]);
  });
});

describe("filter chips", () => {
  const label = (category: string, value: string) => `${category}:${value}`;

  it("lists one removable chip per selected value", () => {
    const chips = filterChips(
      filters({ lifecycleStages: ["active"], evidencePresence: "with_evidence" }),
      label,
    );
    expect(chips).toEqual([
      { category: "lifecycleStages", value: "active", label: "lifecycleStages:active" },
      { category: "evidencePresence", value: "with_evidence", label: "evidencePresence:with_evidence" },
    ]);
  });

  it("removes exactly one value and leaves the rest intact", () => {
    const before = filters({ lifecycleStages: ["active", "planned"], contractIds: ["int-1"] });
    const after = removeFilterChip(before, { category: "lifecycleStages", value: "active" });
    expect(after.lifecycleStages).toEqual(["planned"]);
    expect(after.contractIds).toEqual(["int-1"]);
    expect(before.lifecycleStages).toEqual(["active", "planned"]);
  });

  it("clears the evidence selection by resetting it to any", () => {
    const after = removeFilterChip(filters({ evidencePresence: "with_evidence" }), {
      category: "evidencePresence",
      value: "with_evidence",
    });
    expect(after.evidencePresence).toBe("any");
  });
});
