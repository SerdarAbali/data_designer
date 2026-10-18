import { describe, expect, it } from "vitest";

import {
  defaultDiscipline,
  defaultWorkbenchView,
  demoPresetForDisciplines,
  disciplineGuidance,
  normalizeDisciplines,
  resolveWorkspaceDestination,
  showsDisciplineSelector,
  workspaceTabDefinitions,
  workspaceTabIds,
  WORKSPACE_PRESETS,
} from "./disciplineScope";
import type { ArchitectureDiscipline } from "../architectureTypes";

const ENTERPRISE_ONLY: ArchitectureDiscipline[] = ["enterprise"];
const INFORMATION_ONLY: ArchitectureDiscipline[] = ["information"];
const SOLUTION_ONLY: ArchitectureDiscipline[] = ["solution"];
const INTEGRATION_ONLY: ArchitectureDiscipline[] = ["integration"];
const SOLUTION_INTEGRATION: ArchitectureDiscipline[] = ["solution", "integration"];
const FULL: ArchitectureDiscipline[] = ["enterprise", "information", "solution", "integration"];

function viewLabel(disciplines: ArchitectureDiscipline[], view: string): string | undefined {
  return workspaceTabDefinitions(disciplines).find((tab) => tab.id === view)?.label;
}

describe("discipline-scoped workspace simplify", () => {
  it("normalizes disciplines into canonical order and ignores duplicates", () => {
    expect(normalizeDisciplines(["integration", "solution", "solution"])).toEqual([
      "solution",
      "integration",
    ]);
    expect(normalizeDisciplines(null)).toEqual([]);
  });

  it("defaults Enterprise only to Strategy Trace", () => {
    expect(defaultDiscipline(ENTERPRISE_ONLY)).toBe("enterprise");
    expect(defaultWorkbenchView("enterprise")).toBe("strategy");
    expect(resolveWorkspaceDestination(ENTERPRISE_ONLY)).toEqual({
      view: "canvas",
      discipline: "enterprise",
      workbenchView: "strategy",
    });
  });

  it("defaults Information only to the Logical Model", () => {
    expect(defaultDiscipline(INFORMATION_ONLY)).toBe("information");
    expect(defaultWorkbenchView("information")).toBe("logical");
  });

  it("defaults Solution only to Context", () => {
    expect(defaultDiscipline(SOLUTION_ONLY)).toBe("solution");
    expect(defaultWorkbenchView("solution")).toBe("context");
  });

  it("defaults Integration only to the Integration Landscape", () => {
    expect(defaultDiscipline(INTEGRATION_ONLY)).toBe("integration");
    expect(defaultWorkbenchView("integration")).toBe("landscape");
  });

  it("defaults Solution + Integration to Solution Context but keeps Integration Landscape reachable", () => {
    expect(defaultDiscipline(SOLUTION_INTEGRATION)).toBe("solution");
    expect(resolveWorkspaceDestination(SOLUTION_INTEGRATION).workbenchView).toBe("context");
    expect(defaultWorkbenchView("integration")).toBe("landscape");
  });

  it("preserves the Full Architecture professional default (Enterprise Strategy Trace)", () => {
    expect(defaultDiscipline(FULL)).toBe("enterprise");
    expect(resolveWorkspaceDestination(FULL)).toEqual({
      view: "canvas",
      discipline: "enterprise",
      workbenchView: "strategy",
    });
  });

  it("shows only relevant navigation per scope", () => {
    // Enterprise / Information / Solution only: no Contracts.
    for (const scope of [ENTERPRISE_ONLY, INFORMATION_ONLY, SOLUTION_ONLY]) {
      expect(workspaceTabIds(scope)).toEqual(["canvas", "catalog"]);
      expect(viewLabel(scope, "integrations")).toBeUndefined();
    }
    // Integration only: Contracts and Catalog.
    expect(workspaceTabIds(INTEGRATION_ONLY)).toEqual(["canvas", "integrations", "catalog"]);
    // Solution + Integration keeps Contracts for Mapping & Tests.
    expect(workspaceTabIds(SOLUTION_INTEGRATION)).toEqual(["canvas", "integrations", "catalog"]);
    // Full Architecture keeps the complete professional experience.
    expect(workspaceTabIds(FULL)).toEqual(["canvas", "integrations", "catalog"]);
  });

  it("replaces a one-item tab group with plain context", () => {
    for (const scope of [ENTERPRISE_ONLY, INFORMATION_ONLY, SOLUTION_ONLY, INTEGRATION_ONLY]) {
      expect(showsDisciplineSelector(scope)).toBe(false);
    }
    expect(showsDisciplineSelector(SOLUTION_INTEGRATION)).toBe(true);
    expect(showsDisciplineSelector(FULL)).toBe(true);
  });

  it("provides compact discipline-specific first-use guidance", () => {
    expect(disciplineGuidance("integration").steps).toEqual([
      "Select participating systems",
      "Define a direct, event-driven, mediated or file-based flow",
      "Open or create a Contract, then add mappings and scenarios",
    ]);
    expect(disciplineGuidance("solution").steps).toEqual([
      "Add components and their responsibilities",
      "Create provided and required interfaces",
      "Model interactions, repositories and deployment",
    ]);
    for (const discipline of FULL) {
      expect(disciplineGuidance(discipline).steps.length).toBeGreaterThan(0);
    }
  });

  it("offers the four workspace presets with matching disciplines", () => {
    expect(WORKSPACE_PRESETS.map((preset) => preset.label)).toEqual([
      "Integration Workspace",
      "Solution Design",
      "Solution + Integration",
      "Full Architecture",
    ]);
    expect(WORKSPACE_PRESETS.find((preset) => preset.id === "integration")?.disciplines).toEqual([
      "integration",
    ]);
    expect(WORKSPACE_PRESETS.find((preset) => preset.id === "solution")?.disciplines).toEqual([
      "solution",
    ]);
  });

  it("only maps demo content onto the scopes the backend builds", () => {
    expect(demoPresetForDisciplines(INTEGRATION_ONLY)).toBe("integration_only");
    expect(demoPresetForDisciplines(SOLUTION_INTEGRATION)).toBe("solution_integration");
    expect(demoPresetForDisciplines(FULL)).toBe("full");
    expect(demoPresetForDisciplines(SOLUTION_ONLY)).toBeNull();
    expect(demoPresetForDisciplines(ENTERPRISE_ONLY)).toBeNull();
  });
});
