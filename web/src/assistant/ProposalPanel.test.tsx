// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProposalPanel } from "./ProposalPanel";

const HASH = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890";

const DECISION = {
  decision_id: "decision:op-1:choose_canonical_object",
  operation_id: "op-1",
  kind: "choose_canonical_object",
  question: "Which existing canonical object should be reused?",
  explanation: "The Customer entity is ambiguous.",
  options: [],
  required: true,
  affected_operation_ids: ["op-1"],
  resolution_state: "open",
};

const OPERATION = {
  operation_id: "op-1",
  ordinal: 0,
  domain_action: "create_object",
  target_type: "information_object",
  target_id: null,
  temporary_id: "tmp:customer",
  proposed_value: { kind: "information_object", name: "Customer" },
  depends_on: [],
  validation_status: "unresolved",
  validation_issues: [],
  resolution_state: "active",
  explanation: null,
};

function changeSet(overrides: Record<string, unknown> = {}) {
  return {
    id: "cs-1",
    helper_name: "propose_information_entity",
    status: "draft",
    state_id: "state-1",
    state_type: "candidate",
    summary: "Add a Customer information entity",
    proposal_hash: HASH,
    assumptions: ["Reuses the CRM system"],
    warnings: ["Billing is not enabled"],
    unresolved_decisions: [],
    unresolved_details: [DECISION],
    reused_objects: [{ target_type: "catalog_system", target_id: "sys-1" }],
    proposed_objects: [{ temporary_id: "tmp:customer", target_type: "information_object" }],
    validation_summary: {},
    validated_at: null,
    approved_at: null,
    approved_hash: null,
    applied_at: null,
    undone_at: null,
    apply_summary: {},
    undo_summary: {},
    operations: [OPERATION],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = "";
});

beforeEach(() => {
  document.cookie = "dd_csrf=test-csrf-token";
});

function stubRouter(responses: {
  get?: unknown;
  approve?: unknown;
  apply?: unknown;
  undo?: unknown;
  undoError?: unknown;
}) {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    const url = String(path);
    const method = init?.method ?? "GET";
    if (url.includes("/proposal-events")) {
      return { ok: true, status: 200, json: async () => ({ status: "recorded" }) };
    }
    if (method === "POST" && url.endsWith("/approve")) {
      return { ok: true, status: 200, json: async () => responses.approve };
    }
    if (method === "POST" && url.endsWith("/apply")) {
      return { ok: true, status: 200, json: async () => responses.apply };
    }
    if (method === "POST" && url.endsWith("/undo")) {
      if (responses.undoError) {
        return {
          ok: false,
          status: 409,
          json: async () => ({ detail: responses.undoError }),
        };
      }
      return { ok: true, status: 200, json: async () => responses.undo };
    }
    return { ok: true, status: 200, json: async () => responses.get };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof ProposalPanel>> = {}) {
  return render(
    <ProposalPanel
      workspaceId="ws-1"
      workspaceName="Demo"
      conversationId="conv-1"
      changeSetId="cs-1"
      {...overrides}
    />,
  );
}

describe("ProposalPanel refinement previews", () => {
  it("renders a readable preview line for a refinement operation", async () => {
    stubRouter({
      get: changeSet({
        helper_name: "propose_contract_mediator",
        status: "validated",
        unresolved_details: [],
        validation_summary: { ready_for_approval: true },
        operations: [
          {
            operation_id: "op-1",
            ordinal: 0,
            domain_action: "set_contract_mediator",
            target_type: "contract",
            target_id: "44444444-4444-4444-4444-444444444444",
            temporary_id: null,
            before_value: { mediator_system_id: null, mediator_responsibility: null },
            proposed_value: {
              kind: "contract",
              contract_name: "Onboarding",
              mediator_system_id: "55555555-5555-5555-5555-555555555555",
              mediator_system_name: "FRENDS",
            },
            depends_on: [],
            validation_status: "valid",
            validation_issues: [],
            resolution_state: "active",
            explanation: null,
          },
        ],
      }),
    });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("operation-preview")).toBeTruthy());
    const line = screen.getByTestId("operation-preview").textContent ?? "";
    expect(line).toContain("Mediator");
    expect(line).toContain("FRENDS");
    expect(line).toContain("None →");
  });

  it("shows validation issues for a rejected refinement operation", async () => {
    stubRouter({
      get: changeSet({
        helper_name: "propose_evidence",
        status: "validation_failed",
        unresolved_details: [],
        operations: [
          {
            operation_id: "op-1",
            ordinal: 0,
            domain_action: "attach_evidence",
            target_type: "evidence",
            target_id: null,
            temporary_id: null,
            proposed_value: { target_kind: "integration" },
            depends_on: [],
            validation_status: "invalid",
            validation_issues: [{ code: "unknown_evidence_target", message: "Not found" }],
            resolution_state: "active",
            explanation: null,
          },
        ],
      }),
    });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText("unknown_evidence_target")).toBeTruthy(),
    );
  });
});

describe("ProposalPanel lifecycle", () => {
  it("shows Needs decisions and disables Approve until validated", async () => {
    stubRouter({ get: changeSet() });
    renderPanel();
    await waitFor(() => expect(screen.getByText(/Add a Customer information entity/)).toBeTruthy());
    expect(screen.getByText("Decisions required")).toBeTruthy();
    expect(screen.queryByTestId("approve-button")).toBeNull();
    expect(screen.queryByTestId("apply-button")).toBeNull();
    expect(screen.queryByTestId("undo-button")).toBeNull();
    expect(screen.getByRole("button", { name: "Resolve decisions" }).hasAttribute("disabled")).toBe(false);
  });

  it("enables Approve when validated and ready, then applies via the helper API", async () => {
    stubRouter({
      get: changeSet({
        status: "validated",
        unresolved_details: [],
        validation_summary: { ready_for_approval: true, valid: 1 },
        validated_at: "2026-01-01T00:00:00Z",
      }),
      approve: changeSet({
        status: "approved",
        unresolved_details: [],
        validation_summary: { ready_for_approval: true },
        approved_at: "2026-01-01T00:00:00Z",
      }),
      apply: {
        change_set: changeSet({ status: "applied", applied_at: "2026-01-01T00:00:00Z" }),
        status: "applied",
        applied_operation_count: 1,
        resolution_map: { "tmp:customer": "real-1" },
        applied_operations: [
          {
            operation_id: "op-1",
            domain_action: "create_object",
            applied_id: "real-1",
            role: "created",
          },
        ],
        contract_revisions: [{ contract_id: "c-1", revision: 1, role: "created" }],
        affected_objects: ["real-1"],
        affected_workbenches: ["information"],
        warnings: [],
        conflicts: [],
        audit_event_ref: "cs-1",
      },
    });
    const onApplied = vi.fn();
    renderPanel({ onApplied, onClearHighlights: vi.fn() });

    await waitFor(() => expect(screen.getByText("Ready for review")).toBeTruthy());
    expect(screen.getByTestId("approve-button").hasAttribute("disabled")).toBe(false);

    fireEvent.click(screen.getByTestId("approve-button"));
    expect(screen.getByTestId("confirm-dialog")).toBeTruthy();
    expect(screen.getByText(/Approving records your approval only/i)).toBeTruthy();
    fireEvent.click(screen.getByTestId("confirm-action"));

    await waitFor(() => expect(screen.getByTestId("apply-button").hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByTestId("apply-button"));
    fireEvent.click(screen.getByTestId("confirm-action"));

    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(screen.getByTestId("apply-results")).toBeTruthy();
    expect(screen.getAllByText(/real-1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/c-1 · revision 1/)).toBeTruthy();
    expect(screen.getByTestId("clear-highlights")).toBeTruthy();
  });

  it("enables Undo only when applied and shows conflicts without a force path", async () => {
    stubRouter({
      get: changeSet({ status: "applied", applied_at: "2026-01-01T00:00:00Z" }),
      undoError: {
        code: "undo_conflict",
        message: "Undo would overwrite a later change",
        conflicts: [
          { operation_id: "op-1", code: "object_modified", message: "information_object changed" },
        ],
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("undo-button").hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByTestId("undo-button"));
    expect(screen.getByText(/all-or-nothing/i)).toBeTruthy();
    fireEvent.click(screen.getByTestId("confirm-action"));

    await waitFor(() => expect(screen.getByTestId("undo-conflict")).toBeTruthy());
    expect(screen.getByText(/No changes were undone/i)).toBeTruthy();
    expect(screen.getByText(/object_modified/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /force/i })).toBeNull();
    // Buttons return to a usable state after failure.
    expect(screen.getByTestId("undo-button").hasAttribute("disabled")).toBe(false);
  });

  it("submits a closed resolution through the UI endpoint", async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      if ((init?.method ?? "GET") === "POST" && url.endsWith("/resolve")) {
        return {
          ok: true,
          status: 200,
          json: async () => changeSet({ unresolved_details: [] }),
        };
      }
      return { ok: true, status: 200, json: async () => changeSet() };
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    await waitFor(() => expect(screen.getByText(/Which existing canonical object/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText(/Resolution value for op-1/), {
      target: { value: "33333333-3333-3333-3333-333333333333" },
    });
    fireEvent.click(screen.getByTestId("resolve-op-1"));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith("/resolve"))).toBe(true);
    });
  });

  it("reports a safe failure and keeps no partial success", async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      if (url.includes("/proposal-events")) {
        return { ok: true, status: 200, json: async () => ({ status: "recorded" }) };
      }
      if ((init?.method ?? "GET") === "POST" && url.endsWith("/apply")) {
        return {
          ok: false,
          status: 409,
          json: async () => ({ detail: { code: "before_value_conflict", message: "changed" } }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => changeSet({ status: "approved", approved_hash: HASH, validation_summary: { ready_for_approval: true }, unresolved_details: [] }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("apply-button").hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByTestId("apply-button"));
    fireEvent.click(screen.getByTestId("confirm-action"));
    await waitFor(() => expect(screen.getByTestId("proposal-error")).toBeTruthy());
    expect(screen.queryByTestId("apply-results")).toBeNull();
  });

  it("summarizes key facts and collapses technical sections by default", async () => {
    stubRouter({
      get: changeSet({
        status: "validated",
        unresolved_details: [],
        validation_summary: { ready_for_approval: true, valid: 1 },
        validated_at: "2026-01-01T00:00:00Z",
      }),
    });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("proposal-summary")).toBeTruthy());
    const summary = screen.getByTestId("proposal-summary");
    expect(summary.textContent).toContain("Target state");
    expect(summary.textContent).toContain("Reused");
    expect(summary.textContent).toContain("Proposed");
    expect(summary.textContent).toContain("Decisions");
    expect(summary.textContent).toContain("Readiness");
    const lifecycle = screen.getByTestId("proposal-lifecycle");
    expect(lifecycle.getAttribute("data-tone")).toBe("success");
    const operations = screen.getByTestId("proposal-operations");
    const operationsSection = operations.closest("details") as HTMLDetailsElement;
    expect(operationsSection.open).toBe(false);
  });

  it("opens required decisions by default while keeping operations collapsed", async () => {
    stubRouter({ get: changeSet() });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId("proposal-decisions")).toBeTruthy());
    const decisionsSection = screen.getByTestId("proposal-decisions").closest("details") as HTMLDetailsElement;
    expect(decisionsSection.open).toBe(true);
    const operationsSection = screen.getByTestId("proposal-operations").closest("details") as HTMLDetailsElement;
    expect(operationsSection.open).toBe(false);
    expect(screen.getByTestId("proposal-lifecycle").getAttribute("data-tone")).toBe("draft");
  });
});
