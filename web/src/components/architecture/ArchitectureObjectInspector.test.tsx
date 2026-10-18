// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CanonicalSystem } from "../../architectureCanvasModel";
import ArchitectureObjectInspector from "./ArchitectureObjectInspector";

vi.mock("./ObjectTracePanel", () => ({ default: () => null }));

afterEach(cleanup);

const system: CanonicalSystem = {
  id: "sys-1",
  name: "CRM",
  description: "Customer system",
  kind: "application",
  icon: null,
  color: null,
  lifecycle_stage: "active",
  operational_status: "live",
  environment_scope: "production",
};

function renderInspector(overrides?: Record<string, unknown>, currentSystem: CanonicalSystem = system) {
  render(
    <ArchitectureObjectInspector
      object={null}
      system={currentSystem}
      systems={[currentSystem]}
      readOnly
      onClose={vi.fn()}
      onSave={vi.fn(async () => {})}
      onCollapse={vi.fn()}
      occurrenceId="occ-1"
      stateName="Candidate"
      saveStatus="idle"
      relationships={[]}
      onSelectRelationship={vi.fn()}
      overrides={overrides}
    />,
  );
}

function factRow(label: RegExp): string {
  const paragraph = screen.getByText(label).closest("p");
  return paragraph?.textContent ?? "";
}

describe("ArchitectureObjectInspector system facts", () => {
  it("shows the canonical facts and labels unspecified ones", () => {
    renderInspector(undefined, { ...system, environment_scope: null });
    expect(factRow(/Lifecycle stage:/)).toContain("Active");
    expect(factRow(/Operational status:/)).toContain("Live");
    expect(factRow(/Environment scope:/)).toContain("Unspecified");
  });

  it("shows the state override and its baseline when a Candidate/target differs", () => {
    renderInspector({ lifecycle_stage: "retiring", operational_status: "live" });
    const lifecycle = factRow(/Lifecycle stage:/);
    expect(lifecycle).toContain("Retiring");
    expect(lifecycle).toContain("override (baseline: Active)");
    // An override that matches the baseline is not flagged as a departure.
    expect(factRow(/Operational status:/)).not.toContain("override");
  });
});
