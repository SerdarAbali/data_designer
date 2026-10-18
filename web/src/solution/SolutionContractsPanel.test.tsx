// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SolutionContractsPanel from "./SolutionContractsPanel";
import type { SolutionIntegration } from "./solutionModel";

vi.mock("./solutionModel", async () => {
  const actual = await vi.importActual<typeof import("./solutionModel")>("./solutionModel");
  return {
    ...actual,
    listSolutionContracts: vi.fn(),
    listAssociableContracts: vi.fn(),
    createSolutionContract: vi.fn(),
    updateSolutionContract: vi.fn(),
    deleteSolutionContract: vi.fn(),
  };
});

import {
  createSolutionContract,
  deleteSolutionContract,
  listAssociableContracts,
  listSolutionContracts,
  updateSolutionContract,
} from "./solutionModel";

const listMock = vi.mocked(listSolutionContracts);
const contractsMock = vi.mocked(listAssociableContracts);
const createMock = vi.mocked(createSolutionContract);
const updateMock = vi.mocked(updateSolutionContract);
const deleteMock = vi.mocked(deleteSolutionContract);

const fact = (value: string | null) => ({
  value,
  canonical: value,
  override: null,
  overridden: false,
});

function association(overrides: Partial<SolutionIntegration> = {}): SolutionIntegration {
  return {
    id: "assoc-1",
    tenant_id: "ws-1",
    solution_object_id: "sol-1",
    integration_id: "int-1",
    role: "owned",
    description: "Owns the onboarding contract.",
    created_in_state_id: "state-1",
    state_applicability: "state",
    state_name: "Candidate",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    contract: {
      id: "int-1",
      name: "Customer onboarding",
      interaction_type: "REQUEST_RESPONSE",
      implementation_status: "built",
      source: {
        system_id: "sys-sf",
        system_name: "Salesforce",
        object_id: "obj-1",
        object_name: "Customer",
        is_runtime: false,
      },
      target: {
        system_id: "sys-ns",
        system_name: "NetSuite",
        object_id: "obj-2",
        object_name: "Account",
        is_runtime: false,
      },
      mediator: null,
      explicit_mediator: false,
      mediated: false,
      mediation_source: "none",
      evidence_count: 2,
      lifecycle_stage: fact("active"),
      operational_status: fact("live"),
      environment_scope: fact(null),
    },
    ...overrides,
  };
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof SolutionContractsPanel>> = {}) {
  const onOpenContract = vi.fn();
  render(
    <SolutionContractsPanel
      workspaceId="ws-1"
      solutionId="sol-1"
      stateId="state-1"
      editable
      busy={false}
      onOpenContract={onOpenContract}
      {...overrides}
    />,
  );
  return { onOpenContract };
}

beforeEach(() => {
  listMock.mockResolvedValue([]);
  contractsMock.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SolutionContractsPanel", () => {
  it("explains that ownership is never inferred when nothing is associated", async () => {
    renderPanel();
    await screen.findByText(/No Contracts are associated with this solution yet/);
    expect(screen.getByText(/never linked automatically/)).toBeTruthy();
  });

  it("renders the association summary with source, mediator and target", async () => {
    listMock.mockResolvedValue([
      association({
        contract: {
          ...association().contract,
          mediator: {
            system_id: "sys-frends",
            system_name: "FRENDS",
            is_runtime: true,
            explicit: true,
          },
          explicit_mediator: true,
          mediated: true,
          mediation_source: "explicit",
        },
      }),
    ]);
    renderPanel();
    await screen.findByText("Customer onboarding");
    expect(screen.getByText("Owned by this solution")).toBeTruthy();
    expect(screen.getByText("Salesforce")).toBeTruthy();
    expect(screen.getByText("FRENDS (explicit)")).toBeTruthy();
    expect(screen.getByText("NetSuite")).toBeTruthy();
    expect(screen.getByText("Owns the onboarding contract.")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });

  it("shows lifecycle, operational, environment, implementation and evidence", async () => {
    listMock.mockResolvedValue([association()]);
    renderPanel();
    await screen.findByText("Customer onboarding");
    const value = (label: string) =>
      screen.getByText(label).nextElementSibling?.textContent ?? "";
    expect(value("Lifecycle")).toBe("Active");
    expect(value("Operational")).toBe("Live");
    expect(value("Environment")).toBe("Unspecified");
    expect(value("Implementation")).toBe("Built");
    expect(value("Evidence")).toBe("2");
    expect(value("Applies to")).toBe("Candidate state");
  });

  it("labels a canonical association as applicable to all states", async () => {
    listMock.mockResolvedValue([
      association({ state_applicability: "canonical", created_in_state_id: null, state_name: null }),
    ]);
    renderPanel();
    await screen.findByText("Customer onboarding");
    expect(screen.getByText("All states (canonical)")).toBeTruthy();
  });

  it("distinguishes the three roles textually", async () => {
    listMock.mockResolvedValue([
      association({ id: "a", role: "owned" }),
      association({ id: "b", role: "participating", integration_id: "int-2" }),
      association({ id: "c", role: "dependency", integration_id: "int-3" }),
    ]);
    renderPanel();
    await screen.findByText("Owned by this solution");
    expect(screen.getByText("Participating")).toBeTruthy();
    expect(screen.getByText("Dependency")).toBeTruthy();
  });

  it("opens the Contract in Integration Architecture", async () => {
    listMock.mockResolvedValue([association()]);
    const { onOpenContract } = renderPanel();
    await screen.findByText("Customer onboarding");
    fireEvent.click(screen.getByRole("button", { name: "Open in Integration Architecture" }));
    expect(onOpenContract).toHaveBeenCalledWith("int-1");
  });

  it("hides writing controls in a read-only state", async () => {
    listMock.mockResolvedValue([association()]);
    renderPanel({ editable: false });
    await screen.findByText("Customer onboarding");
    expect(screen.queryByRole("button", { name: "+ Associate a contract" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
    // Opening the Contract is always available.
    expect(screen.getByRole("button", { name: "Open in Integration Architecture" })).toBeTruthy();
  });

  it("creates an association with the selected role and description", async () => {
    contractsMock.mockResolvedValue([
      { id: "int-1", name: "Customer onboarding" },
      { id: "int-9", name: "Billing sync" },
    ]);
    createMock.mockResolvedValue(association());
    renderPanel();
    await screen.findByRole("button", { name: "+ Associate a contract" });
    fireEvent.click(screen.getByRole("button", { name: "+ Associate a contract" }));
    fireEvent.change(screen.getByLabelText("Contract"), { target: { value: "int-9" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "dependency" } });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Depends on billing." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Associate contract" }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock).toHaveBeenCalledWith("ws-1", "sol-1", {
      state_id: "state-1",
      integration_id: "int-9",
      role: "dependency",
      description: "Depends on billing.",
    });
  });

  it("refuses to create without a selected Contract", async () => {
    contractsMock.mockResolvedValue([]);
    renderPanel();
    await screen.findByText(/No Contracts are associated/);
    // With no associable contracts the create action is disabled.
    expect(screen.getByRole("button", { name: "+ Associate a contract" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(createMock).not.toHaveBeenCalled();
  });

  it("edits the role and description without re-selecting the contract", async () => {
    listMock.mockResolvedValue([association()]);
    contractsMock.mockResolvedValue([{ id: "int-1", name: "Customer onboarding" }]);
    updateMock.mockResolvedValue(association({ role: "participating" }));
    renderPanel();
    await screen.findByText("Customer onboarding");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect((screen.getByLabelText("Contract") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "participating" } });
    fireEvent.click(screen.getByRole("button", { name: "Save association" }));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(updateMock).toHaveBeenCalledWith("ws-1", "sol-1", "assoc-1", {
      role: "participating",
      description: "Owns the onboarding contract.",
    });
  });

  it("removes only after an explicit confirmation", async () => {
    listMock.mockResolvedValue([association()]);
    deleteMock.mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPanel();
    await screen.findByText("Customer onboarding");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(deleteMock).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith("ws-1", "sol-1", "assoc-1"));
    confirmSpy.mockRestore();
  });

  it("surfaces a load failure as an error, not as an empty state", async () => {
    listMock.mockRejectedValue(new Error("Landscape unavailable"));
    renderPanel();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Landscape unavailable");
  });
});
