// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProposalPanel } from "./ProposalPanel";

const CHANGE_SET = {
  id: "cs-1",
  helper_name: "propose_information_entity",
  status: "draft",
  state_id: "state-1",
  state_type: "candidate",
  summary: "Add a Customer information entity",
  proposal_hash: "abcdef1234567890",
  assumptions: ["Reuses the CRM system"],
  warnings: ["Billing is not enabled"],
  unresolved_decisions: [],
  unresolved_details: [
    {
      decision_id: "decision:op-1:choose_canonical_object",
      operation_id: "op-1",
      kind: "choose_canonical_object",
      question: "Which existing canonical object should be reused?",
      explanation: "The Customer entity is ambiguous.",
      options: [],
      required: true,
      affected_operation_ids: ["op-1"],
      resolution_state: "open",
    },
  ],
  reused_objects: [{ target_type: "catalog_system", target_id: "sys-1" }],
  proposed_objects: [{ temporary_id: "tmp:customer", target_type: "information_object" }],
  validation_summary: { valid: 1, invalid: 0, unresolved: 1, ready_for_approval: false },
  validated_at: null,
  approved_at: null,
  applied_at: null,
  undone_at: null,
  operations: [
    {
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
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => payload })),
  );
}

describe("ProposalPanel", () => {
  it("renders the proposal, decisions, and no approve/apply/undo controls", async () => {
    stubFetch(CHANGE_SET);
    render(<ProposalPanel workspaceId="ws-1" changeSetId="cs-1" />);

    await waitFor(() => {
      expect(screen.getByText(/Add a Customer information entity/)).toBeTruthy();
    });
    expect(screen.getByText(/Which existing canonical object should be reused/)).toBeTruthy();
    expect(screen.getByTestId("proposal-operations")).toBeTruthy();
    expect(screen.getByTestId("preview-counts")).toBeTruthy();
    expect(screen.getByText(/Decisions required/)).toBeTruthy();

    for (const forbidden of [/^approve$/i, /^apply$/i, /^undo$/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).toBeNull();
    }
    expect(screen.getByRole("button", { name: "Validate" })).toBeTruthy();
  });

  it("submits a closed resolution and refreshes the proposal", async () => {
    document.cookie = "dd_csrf=test-csrf-token";
    const resolved = { ...CHANGE_SET, status: "draft", unresolved_details: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => CHANGE_SET })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => resolved });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProposalPanel workspaceId="ws-1" changeSetId="cs-1" />);

    await waitFor(() => {
      expect(screen.getByText(/Which existing canonical object/)).toBeTruthy();
    });
    fireEvent.change(screen.getByLabelText(/Resolution value for op-1/), {
      target: { value: "33333333-3333-3333-3333-333333333333" },
    });
    fireEvent.click(screen.getByTestId("resolve-op-1"));

    await waitFor(() => {
      expect(screen.queryByText(/Which existing canonical object/)).toBeNull();
    });
    const resolveCall = fetchMock.mock.calls[1];
    expect(String(resolveCall[0])).toContain("/resolve");
  });
});
