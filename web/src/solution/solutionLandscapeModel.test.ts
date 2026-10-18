import { describe, expect, it } from "vitest";

import {
  contractRoleSummary,
  isSymmetricRelationship,
  landscapeLayout,
  nodeWarnings,
  relationshipLabel,
  warningLabel,
} from "./solutionLandscapeModel";
import type { SolutionLandscape, SolutionLandscapeNode } from "./solutionModel";

const fact = (value: string | null) => ({
  value,
  canonical: value,
  override: null,
  overridden: false,
});

function node(overrides: Partial<SolutionLandscapeNode> = {}): SolutionLandscapeNode {
  return {
    solution_object_id: "sol-1",
    occurrence_id: null,
    name: "Alpha",
    description: null,
    owner: null,
    lifecycle_stage: null,
    operational_status: null,
    component_count: 0,
    member_count: 0,
    external_system_count: 0,
    members: [],
    external_systems: [],
    contract_counts: { owned: 0, participating: 0, dependency: 0, total: 0 },
    contracts: [],
    evidence_count: 0,
    relationships_in: 0,
    relationships_out: 0,
    ...overrides,
  };
}

function landscape(overrides: Partial<SolutionLandscape> = {}): SolutionLandscape {
  return {
    state_id: "state-1",
    state_type: "candidate",
    editable: true,
    solutions: [],
    relationships: [],
    warnings: [],
    ...overrides,
  };
}

const association = (overrides: Record<string, unknown> = {}) => ({
  association_id: "assoc-1",
  role: "owned" as const,
  description: null,
  state_applicability: "state" as const,
  state_name: "Candidate",
  contract_id: "int-1",
  contract_name: "Onboarding",
  available: true,
  implementation_status: "built",
  lifecycle_stage: fact("active"),
  operational_status: fact(null),
  environment_scope: fact(null),
  evidence_count: 0,
  ...overrides,
});

describe("landscapeLayout", () => {
  it("is deterministic for the same ids regardless of input order", () => {
    const first = landscapeLayout(["c", "a", "b"]);
    const second = landscapeLayout(["b", "c", "a"]);
    expect([...first.entries()]).toEqual([...second.entries()]);
  });

  it("places every id and is stable across calls", () => {
    const positions = landscapeLayout(["b", "a"]);
    expect(positions.size).toBe(2);
    expect(positions.get("a")).toEqual(landscapeLayout(["a", "b"]).get("a"));
  });

  it("handles the empty case", () => {
    expect(landscapeLayout([]).size).toBe(0);
  });
});

describe("landscape labels", () => {
  it("describes each approved relationship type", () => {
    expect(relationshipLabel("depends_on")).toBe("Depends on");
    expect(relationshipLabel("shares_information_with")).toBe("Shares information with");
    expect(isSymmetricRelationship("shares_information_with")).toBe(true);
    expect(isSymmetricRelationship("depends_on")).toBe(false);
  });

  it("summarises association roles textually", () => {
    expect(contractRoleSummary(node())).toBe("No associated contracts");
    expect(
      contractRoleSummary(
        node({ contract_counts: { owned: 1, participating: 2, dependency: 0, total: 3 } }),
      ),
    ).toBe("1 owned · 2 participating · 0 dependency");
  });

  it("labels unavailable references in words", () => {
    expect(warningLabel("archived_contract_association")).toBe("Unavailable contract association");
    expect(warningLabel("member_system_unavailable")).toBe("Unavailable member system");
  });

  it("scopes warnings to the right solution", () => {
    const data = landscape({
      warnings: [
        {
          code: "archived_contract_association",
          message: "Archived.",
          solution_object_id: "sol-1",
          relationship_id: null,
          association_id: "assoc-1",
          integration_id: "int-1",
        },
        {
          code: "archived_contract_association",
          message: "Archived.",
          solution_object_id: "sol-2",
          relationship_id: null,
          association_id: "assoc-2",
          integration_id: "int-2",
        },
      ],
    });
    expect(nodeWarnings(data, "sol-1")).toHaveLength(1);
    expect(nodeWarnings(data, "sol-3")).toHaveLength(0);
  });

  it("keeps association facts available for display decisions", () => {
    const entry = association();
    expect(entry.lifecycle_stage.value).toBe("active");
    expect(entry.operational_status.value).toBeNull();
  });
});
