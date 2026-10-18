// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SolutionLandscapeInspector from "./SolutionLandscapeInspector";
import type { SolutionLandscape, SolutionLandscapeNode } from "./solutionModel";
import { deleteSolutionRelationship, updateSolutionRelationship } from "./solutionModel";

vi.mock("./solutionModel", async () => {
  const actual = await vi.importActual<typeof import("./solutionModel")>("./solutionModel");
  return {
    ...actual,
    updateSolutionRelationship: vi.fn(),
    deleteSolutionRelationship: vi.fn(),
    listSolutionContracts: vi.fn().mockResolvedValue([]),
    listAssociableContracts: vi.fn().mockResolvedValue([]),
    createSolutionContract: vi.fn(),
    updateSolutionContract: vi.fn(),
    deleteSolutionContract: vi.fn(),
  };
});

vi.mock("../components/architecture/EvidencePanel", () => ({ default: () => null }));

const updateMock = vi.mocked(updateSolutionRelationship);
const deleteMock = vi.mocked(deleteSolutionRelationship);

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
    component_count: 2,
    member_count: 1,
    external_system_count: 1,
    members: [{ system_id: "sys-1", name: "Core Banking", kind: "service", external: false }],
    external_systems: [{ system_id: "sys-2", name: "Partner", kind: "service", external: true }],
    contract_counts: { owned: 1, participating: 0, dependency: 0, total: 1 },
    contracts: [
      {
        association_id: "assoc-1",
        role: "owned",
        description: "Owns onboarding.",
        state_applicability: "state",
        state_name: "Candidate",
        contract_id: "int-1",
        contract_name: "Onboarding",
        available: true,
        implementation_status: "built",
        lifecycle_stage: fact("active"),
        operational_status: fact(null),
        environment_scope: fact(null),
        evidence_count: 2,
      },
    ],
    evidence_count: 3,
    relationships_in: 1,
    relationships_out: 1,
    ...overrides,
  };
}

const landscape: SolutionLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  solutions: [
    node(),
    node({ solution_object_id: "sol-2", name: "Beta", owner: "Owner B", contract_counts: { owned: 0, participating: 0, dependency: 0, total: 0 }, contracts: [] }),
  ],
  relationships: [
    {
      id: "rel-1",
      source_object_id: "sol-1",
      target_object_id: "sol-2",
      relationship_type: "depends_on",
      description: "Alpha depends on Beta billing.",
      created_in_state_id: "state-1",
      state_applicability: "state",
      state_name: "Candidate",
      evidence_count: 1,
    },
    {
      id: "rel-2",
      source_object_id: "sol-2",
      target_object_id: "sol-1",
      relationship_type: "provides_to",
      description: null,
      created_in_state_id: "state-1",
      state_applicability: "state",
      state_name: "Candidate",
      evidence_count: 0,
    },
  ],
  warnings: [],
};

function renderInspector(overrides: Partial<React.ComponentProps<typeof SolutionLandscapeInspector>> = {}) {
  const onChanged = vi.fn();
  const onOpenSolution = vi.fn();
  const onOpenContract = vi.fn();
  const onSelectEdge = vi.fn();
  render(
    <SolutionLandscapeInspector
      landscape={landscape}
      workspaceId="ws-1"
      stateId="state-1"
      stateName="Candidate"
      selectedNodeId="sol-1"
      selectedEdgeId={null}
      busy={false}
      onSelectNode={vi.fn()}
      onSelectEdge={onSelectEdge}
      onOpenSolution={onOpenSolution}
      onOpenContract={onOpenContract}
      onChanged={onChanged}
      onClose={vi.fn()}
      onCollapse={vi.fn()}
      {...overrides}
    />,
  );
  return { onChanged, onOpenSolution, onOpenContract, onSelectEdge };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SolutionLandscapeInspector", () => {
  it("shows ownership, counts and missing-value labels for a solution", () => {
    renderInspector();
    const properties = screen.getByRole("complementary", { name: "Solution landscape solution" });
    const value = (label: string) => {
      const terms = [...properties.querySelectorAll("dt")];
      const match = terms.find((term) => term.textContent === label);
      return match?.nextElementSibling?.textContent ?? "";
    };
    expect(value("Owner")).toBe("Unspecified");
    expect(value("Components")).toBe("2");
    expect(value("Member systems")).toBe("1");
    expect(value("External systems")).toBe("1");
    expect(value("Lifecycle")).toBe("Unspecified");
    expect(value("Operational status")).toBe("Unspecified");
  });

  it("summarises Contract roles and associations without contract internals", () => {
    renderInspector();
    fireEvent.click(screen.getByRole("button", { name: /^Contracts/ }));
    expect(screen.getByText("1 owned · 0 participating · 0 dependency")).toBeTruthy();
    expect(screen.getByText("Owned by this solution")).toBeTruthy();
    expect(screen.getByText("Onboarding")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
    expect(screen.getByText("Built")).toBeTruthy();
  });

  it("surfaces an unavailable archived Contract association explicitly", () => {
    renderInspector({
      landscape: {
        ...landscape,
        solutions: [
          node({
            contracts: [
              {
                ...node().contracts[0],
                available: false,
                contract_name: "Archived contract",
                implementation_status: null,
              },
            ],
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Contracts/ }));
    expect(screen.getByText("Archived contract")).toBeTruthy();
    expect(screen.getByText(/Unavailable — the Contract is archived/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open in Integration Architecture" })).toBeNull();
  });

  it("lists incoming and outgoing relationships separately", () => {
    renderInspector();
    fireEvent.click(screen.getByRole("button", { name: /^Relationships/ }));
    const panel = screen.getByRole("complementary", { name: "Solution landscape solution" });
    const list = panel.querySelector(".solution-landscape-relationship-list");
    expect(list?.textContent).toContain("Incoming");
    expect(list?.textContent).toContain("Outgoing");
    expect(list?.textContent).toContain("Beta");
    expect(list?.textContent).toContain("Depends on");
    expect(list?.textContent).toContain("Provides to");
  });

  it("opens the solution in Context", () => {
    const { onOpenSolution } = renderInspector();
    fireEvent.click(screen.getByRole("button", { name: "Open in Context" }));
    expect(onOpenSolution).toHaveBeenCalledWith("sol-1");
  });

  it("opens an associated Contract in Integration Architecture", () => {
    const { onOpenContract } = renderInspector();
    fireEvent.click(screen.getByRole("button", { name: /^Contracts/ }));
    fireEvent.click(screen.getByRole("button", { name: "Open in Integration Architecture" }));
    expect(onOpenContract).toHaveBeenCalledWith("int-1");
  });

  it("renders the relationship inspector with direction and description", () => {
    renderInspector({ selectedNodeId: null, selectedEdgeId: "rel-1" });
    const panel = screen.getByRole("complementary", { name: "Solution relationship" });
    expect(panel.querySelector(".solution-landscape-relationship-flow")?.textContent).toContain(
      "Alpha",
    );
    expect(panel.querySelector(".solution-landscape-relationship-flow")?.textContent).toContain(
      "Beta",
    );
    const value = (label: string) => {
      const terms = [...panel.querySelectorAll("dt")];
      const match = terms.find((term) => term.textContent === label);
      return match?.nextElementSibling?.textContent ?? "";
    };
    expect(value("Type")).toBe("Depends on");
    expect(value("Applies to")).toBe("Candidate state");
    expect(value("Description")).toBe("Alpha depends on Beta billing.");
  });

  it("edits a writable relationship and refreshes the landscape", async () => {
    updateMock.mockResolvedValue({
      id: "rel-1",
      tenant_id: "ws-1",
      source_object_id: "sol-1",
      target_object_id: "sol-2",
      relationship_type: "uses",
      description: "Now uses.",
      created_in_state_id: "state-1",
      state_applicability: "state",
      state_name: "Candidate",
      evidence_count: 0,
      created_at: null,
      updated_at: null,
    });
    const { onChanged } = renderInspector({ selectedNodeId: null, selectedEdgeId: "rel-1" });
    fireEvent.change(screen.getByLabelText("Relationship type"), { target: { value: "uses" } });
    fireEvent.change(screen.getByLabelText("Relationship description"), {
      target: { value: "Now uses." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save relationship" }));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(updateMock).toHaveBeenCalledWith("ws-1", "rel-1", "state-1", {
      relationship_type: "uses",
      description: "Now uses.",
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("removes a relationship only after confirmation", async () => {
    deleteMock.mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { onChanged } = renderInspector({ selectedNodeId: null, selectedEdgeId: "rel-1" });
    fireEvent.click(screen.getByRole("button", { name: "Remove relationship" }));
    expect(deleteMock).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Remove relationship" }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith("ws-1", "rel-1", "state-1"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    confirmSpy.mockRestore();
  });

  it("is display-only in a read-only state", () => {
    renderInspector({
      landscape: { ...landscape, editable: false },
      selectedNodeId: null,
      selectedEdgeId: "rel-1",
    });
    expect(screen.queryByRole("button", { name: "Save relationship" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove relationship" })).toBeNull();
    expect(screen.getByText(/read-only/)).toBeTruthy();
  });

  it("protects a canonical relationship from single-state edits", () => {
    renderInspector({
      selectedNodeId: null,
      selectedEdgeId: "rel-1",
      landscape: {
        ...landscape,
        relationships: [
          { ...landscape.relationships[0], state_applicability: "canonical", state_name: null },
        ],
      },
    });
    expect(screen.getByText("All states (canonical)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save relationship" })).toBeNull();
  });

  it("summarises the landscape when nothing is selected", () => {
    renderInspector({ selectedNodeId: null, selectedEdgeId: null });
    expect(screen.getByText("Solutions")).toBeTruthy();
    expect(screen.getByText("Relationships")).toBeTruthy();
  });
});
