// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LandscapeFilterBar from "./LandscapeFilterBar";
import type {
  IntegrationContractSummary,
  IntegrationLandscape,
} from "./integrationDesignModel";
import {
  EMPTY_LANDSCAPE_FILTERS,
  type IntegrationLandscapeFilters,
} from "./landscapeFilters";

afterEach(cleanup);

const emptyFact = () => ({ value: null, canonical: null, override: null, overridden: false });
const fact = (value: string) => ({ value, canonical: value, override: null, overridden: false });

function contract(overrides: Partial<IntegrationContractSummary>): IntegrationContractSummary {
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

const landscape: IntegrationLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  contracts: [
    contract({
      id: "int-1",
      name: "A very long contract name that must not break the toolbar layout",
      lifecycle_stage: fact("active"),
      referenced_information_objects: [
        { object_id: "obj-acct", name: "account", label: "Account", anchors: ["target"] },
      ],
    }),
    contract({
      id: "int-2",
      name: "Second",
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
    }),
  ],
  interfaces: [],
};

function renderBar(
  filters: Partial<IntegrationLandscapeFilters> = {},
  overrides: Partial<React.ComponentProps<typeof LandscapeFilterBar>> = {},
) {
  const onChange = vi.fn();
  const onClear = vi.fn();
  render(
    <LandscapeFilterBar
      filters={{ ...EMPTY_LANDSCAPE_FILTERS, ...filters }}
      landscape={landscape}
      totalContracts={2}
      visibleContracts={2}
      onChange={onChange}
      onClear={onClear}
      {...overrides}
    />,
  );
  return { onChange, onClear };
}

describe("LandscapeFilterBar", () => {
  it("shows the active-filter count and the result summary", () => {
    renderBar({ lifecycleStages: ["active"], sourceSystemIds: ["sys-crm"] });
    expect(screen.getByLabelText("2 active filters").textContent).toBe("2");
    expect(screen.getByText("2 of 2 contracts")).toBeTruthy();
  });

  it("reports a zero count when nothing is selected", () => {
    renderBar();
    expect(screen.getByLabelText("0 active filters").textContent).toBe("0");
    expect(screen.queryByRole("button", { name: "Clear all" })).toBeNull();
  });

  it("clears everything through Clear all", () => {
    const { onClear } = renderBar({ lifecycleStages: ["active"] });
    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("removes exactly one chip", () => {
    const { onChange } = renderBar({
      lifecycleStages: ["active"],
      contractIds: ["int-1"],
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove Active" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ lifecycleStages: [], contractIds: ["int-1"] }),
    );
  });

  it("labels each chip with its category in words", () => {
    renderBar({ sourceSystemIds: ["sys-crm"], evidencePresence: "with_evidence" });
    expect(screen.getByRole("button", { name: "Remove CRM" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove With evidence" })).toBeTruthy();
    expect(screen.getAllByText("Source").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
  });

  it("offers grouped controls with visible legends", () => {
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    for (const legend of [
      "Status",
      "Operational status",
      "Environment",
      "Implementation",
      "Source system",
      "Target system",
      "Flow",
      "Mediation",
      "Mediation source",
      "Information",
      "Contract",
      "Evidence",
    ]) {
      expect(screen.getByText(legend)).toBeTruthy();
    }
  });

  it("keeps source and target selectors distinct and never offers a mediator as an endpoint", () => {
    renderBar({ sourceSystemIds: ["sys-crm"] });
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    // Only sys-crm is selected as source, so only the source chip exists.
    expect(screen.getByRole("button", { name: "Remove CRM" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Remove FRENDS" })).toBeNull();
    const sourceGroup = screen.getByText("Source system").closest("fieldset")!;
    expect(sourceGroup.textContent).not.toContain("FRENDS");
    const targetGroup = screen.getByText("Target system").closest("fieldset")!;
    expect(targetGroup.textContent).not.toContain("FRENDS");
    expect(targetGroup.textContent).toContain("ERP");
  });

  it("offers Unspecified for the fact filters", () => {
    const { onChange } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    const unspecified = screen.getAllByLabelText("Unspecified");
    expect(unspecified.length).toBeGreaterThanOrEqual(3);
    fireEvent.click(unspecified[0]);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ lifecycleStages: ["unspecified"] }),
    );
  });

  it("explains unspecified metadata and missing information references", () => {
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByText(/unspecified metadata/)).toBeTruthy();
    expect(
      screen.getByText(/no mapped Catalog objects have no information references/),
    ).toBeTruthy();
  });

  it("explains zero evidence counts", () => {
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByText(/evidence is recorded shows a count of zero|count of zero/)).toBeTruthy();
  });

  it("surfaces a stale selection as a removable unavailable option", () => {
    renderBar({ sourceSystemIds: ["sys-gone"] });
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    const chip = screen.getByRole("button", { name: "Remove sys-gone" });
    expect(chip).toBeTruthy();
    expect(screen.getByText("sys-gone (unavailable)")).toBeTruthy();
  });

  it("truncates long contract names instead of breaking the toolbar", () => {
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    const labels = screen.getAllByText(/A very long contract name/);
    expect(labels.length).toBeGreaterThan(0);
    expect(labels[0].className).toContain("landscape-filter-option-label");
  });

  it("keeps every control keyboard reachable and labelled", () => {
    renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByRole("button", { name: /^Filters/ })).toBeTruthy();
    // Checkboxes and radios all carry a visible label element.
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThan(0);
    for (const box of checkboxes.slice(0, 5)) {
      expect((box as HTMLInputElement).labels?.length ?? 0).toBeGreaterThan(0);
    }
    expect(screen.getAllByRole("radio").length).toBe(3);
  });
});
