/**
 * Discipline-scoped workspace simplification (pure selectors).
 *
 * A workspace can enable any non-empty subset of the four architecture
 * disciplines. These helpers answer, from the enabled set alone, which
 * navigation surfaces apply, which discipline and view a workspace should open
 * on, and what discipline-specific first-use guidance to show. They contain no
 * React and never mutate backend semantics: disciplines are the authoritative
 * scope produced by the API.
 */

import {
  ARCHITECTURE_DISCIPLINES,
  type ArchitectureDiscipline,
} from "../architectureTypes";

export type WorkspaceScopeView = "canvas" | "catalog" | "integrations";

export type DemoPreset = "full" | "solution_integration" | "integration_only";

export type InitialArchitectureState = "current" | "candidate";

export const ALL_DISCIPLINES: ArchitectureDiscipline[] = [
  "enterprise",
  "information",
  "solution",
  "integration",
];

/** Canonical order, so nav and defaults are stable regardless of input order. */
export function normalizeDisciplines(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): ArchitectureDiscipline[] {
  const enabled = new Set(disciplines ?? []);
  return ALL_DISCIPLINES.filter((discipline) => enabled.has(discipline));
}

export function isDisciplineEnabled(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
  discipline: ArchitectureDiscipline,
): boolean {
  return normalizeDisciplines(disciplines).includes(discipline);
}

export function integrationEnabled(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): boolean {
  return isDisciplineEnabled(disciplines, "integration");
}

export function disciplineLabel(discipline: ArchitectureDiscipline): string {
  return (
    ARCHITECTURE_DISCIPLINES.find((item) => item.id === discipline)?.label ?? discipline
  );
}

/**
 * The discipline a workspace should open on when there is no stored intent.
 *
 * - Single-discipline workspaces always open on their only discipline.
 * - Solution + Integration opens on Solution (the design workflow entry point);
 *   a stored preference of Integration is honoured by the caller.
 * - Full Architecture preserves the current professional default (first enabled
 *   in canonical order, i.e. Enterprise).
 */
export function defaultDiscipline(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): ArchitectureDiscipline {
  const enabled = normalizeDisciplines(disciplines);
  if (enabled.length === 0) return "enterprise";
  if (enabled.length === 1) return enabled[0];
  return enabled[0];
}

/** The meaningful default view within a discipline workbench. */
export function defaultWorkbenchView(discipline: ArchitectureDiscipline): string {
  switch (discipline) {
    case "enterprise":
      return "strategy";
    case "information":
      return "logical";
    case "solution":
      return "context";
    case "integration":
      return "landscape";
    default:
      return "canvas";
  }
}

export type WorkspaceDestination = {
  view: WorkspaceScopeView;
  discipline: ArchitectureDiscipline;
  workbenchView: string;
};

/**
 * The destination a workspace opens on. Every discipline workbench lives inside
 * the Canvas surface, so the top-level view stays `canvas`; the discipline and
 * its default view carry the meaningful default. Integration also keeps
 * Contracts available as a top-level surface (see `workspaceTabDefinitions`).
 */
export function resolveWorkspaceDestination(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): WorkspaceDestination {
  const discipline = defaultDiscipline(disciplines);
  return {
    view: "canvas",
    discipline,
    workbenchView: defaultWorkbenchView(discipline),
  };
}

export type WorkspaceTab = {
  id: WorkspaceScopeView;
  label: string;
};

/**
 * Top-level shell tabs for the enabled scope.
 *
 * Canvas (the discipline workbenches) is always relevant. Contracts only appear
 * when Integration is enabled, because they are integration contracts. Catalog
 * stays available for every discipline: canonical systems and objects are the
 * substrate every discipline builds on.
 */
export function workspaceTabDefinitions(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): WorkspaceTab[] {
  const tabs: WorkspaceTab[] = [{ id: "canvas", label: "Canvas" }];
  if (integrationEnabled(disciplines)) {
    tabs.push({ id: "integrations", label: "Contracts" });
  }
  tabs.push({ id: "catalog", label: "Catalog" });
  return tabs;
}

export function workspaceTabIds(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): WorkspaceScopeView[] {
  return workspaceTabDefinitions(disciplines).map((tab) => tab.id);
}

/** A one-item tab group is replaced by a plain context label in the top bar. */
export function showsDisciplineSelector(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): boolean {
  return normalizeDisciplines(disciplines).length > 1;
}

export type DisciplineGuidance = {
  title: string;
  steps: string[];
};

/** Compact, discipline-specific first-use guidance. */
export function disciplineGuidance(
  discipline: ArchitectureDiscipline,
): DisciplineGuidance {
  switch (discipline) {
    case "enterprise":
      return {
        title: "Start with strategy and scope",
        steps: [
          "Capture goals, requirements and constraints",
          "Map capabilities and the processes they support",
          "Link the applications that realise them",
        ],
      };
    case "information":
      return {
        title: "Shape the information model",
        steps: [
          "Define entities and their logical attributes",
          "Add relationships and cardinality",
          "Set ownership, authority and physical realization",
        ],
      };
    case "solution":
      return {
        title: "Define the solution boundary",
        steps: [
          "Add components and their responsibilities",
          "Create provided and required interfaces",
          "Model interactions, repositories and deployment",
        ],
      };
    case "integration":
      return {
        title: "Design the integration",
        steps: [
          "Select participating systems",
          "Define a direct, event-driven, mediated or file-based flow",
          "Open or create a Contract, then add mappings and scenarios",
        ],
      };
    default:
      return { title: "Get started", steps: [] };
  }
}

export type WorkspacePreset = {
  id: string;
  label: string;
  description: string;
  disciplines: ArchitectureDiscipline[];
  demoPreset: DemoPreset | null;
};

/** The four useful presets offered at workspace creation. */
export const WORKSPACE_PRESETS: WorkspacePreset[] = [
  {
    id: "integration",
    label: "Integration Workspace",
    description: "Interfaces, contracts, mappings and tests only.",
    disciplines: ["integration"],
    demoPreset: "integration_only",
  },
  {
    id: "solution",
    label: "Solution Design",
    description: "Solution boundaries, components, interfaces and deployment.",
    disciplines: ["solution"],
    demoPreset: null,
  },
  {
    id: "solution_integration",
    label: "Solution + Integration",
    description: "A coherent design workflow from solution to contract.",
    disciplines: ["solution", "integration"],
    demoPreset: "solution_integration",
  },
  {
    id: "full",
    label: "Full Architecture",
    description: "Enterprise, Information, Solution and Integration.",
    disciplines: [...ALL_DISCIPLINES],
    demoPreset: "full",
  },
];

export type DemoPresetOption = {
  id: DemoPreset;
  label: string;
  description: string;
  disciplines: ArchitectureDiscipline[];
};

/** The deterministic demo scopes the backend currently supports. */
export const DEMO_PRESETS: DemoPresetOption[] = [
  {
    id: "integration_only",
    label: "Integration demo",
    description: "Customer onboarding across CRM, billing and an integration runtime.",
    disciplines: ["integration"],
  },
  {
    id: "solution_integration",
    label: "Solution + Integration demo",
    description: "Solution design plus the contracts between its systems.",
    disciplines: ["solution", "integration"],
  },
  {
    id: "full",
    label: "Full Architecture demo",
    description: "Every discipline populated from one deterministic scenario.",
    disciplines: [...ALL_DISCIPLINES],
  },
];

export function demoPresetOption(preset: DemoPreset): DemoPresetOption {
  return DEMO_PRESETS.find((option) => option.id === preset) ?? DEMO_PRESETS[0];
}

/** Demo content is only offered for the scopes the generator actually builds. */
export function demoPresetForDisciplines(
  disciplines: readonly ArchitectureDiscipline[] | null | undefined,
): DemoPreset | null {
  const enabled = normalizeDisciplines(disciplines);
  const match = DEMO_PRESETS.find(
    (option) => option.disciplines.length === enabled.length
      && option.disciplines.every((discipline) => enabled.includes(discipline)),
  );
  return match?.id ?? null;
}

export function presetForId(id: string): WorkspacePreset | null {
  return WORKSPACE_PRESETS.find((preset) => preset.id === id) ?? null;
}
