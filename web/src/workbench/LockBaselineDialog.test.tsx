// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import LockBaselineDialog from "./LockBaselineDialog";
import {
  baselineBlockingReason,
  baselineCanLock,
  baselineLockSummary,
  baselineNeedsEmptyConfirmation,
  baselineStatusLabel,
  baselineSummary,
  type BaselineValidation,
} from "./currentBaseline";
import type { ArchitectureState } from "../architectureTypes";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";
const STATE = "22222222-2222-2222-2222-222222222222";

function state(overrides: Partial<ArchitectureState> = {}): ArchitectureState {
  return {
    id: STATE,
    workspace_id: WORKSPACE,
    name: "Current State",
    state_type: "current",
    baseline_status: "draft",
    nodes: [],
    relationships: [],
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

function validation(overrides: Partial<BaselineValidation> = {}): BaselineValidation {
  return {
    blocking: [],
    warnings: [],
    summary: { object_count: 3, node_count: 3, relationship_count: 1 },
    ...overrides,
  };
}

function stub(validate: BaselineValidation, locked = true) {
  const mock = vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body ?? "{}"));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        state: locked && !body.validate_only ? state({ baseline_status: "locked" }) : state(),
        validation: validate,
        locked: Boolean(locked && !body.validate_only),
      }),
    };
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function props() {
  return {
    workspaceId: WORKSPACE,
    state: state(),
    onLocked: vi.fn(),
    onClose: vi.fn(),
  };
}

beforeEach(() => {
  document.cookie = "dd_csrf=baseline-test-token";
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Current baseline model", () => {
  it("labels the baseline status and its provenance honestly", () => {
    expect(baselineStatusLabel(state())).toBe("Current baseline draft");
    expect(baselineStatusLabel(state({ baseline_status: "locked" }))).toBe(
      "Current baseline locked",
    );
    expect(baselineStatusLabel(state({ state_type: "candidate", baseline_status: null }))).toBe("");
    expect(baselineStatusLabel(null)).toBe("");

    expect(
      baselineLockSummary(
        state({
          baseline_status: "locked",
          baseline_locked_by: "abcdef01-2345-6789-abcd-ef0123456789",
          baseline_locked_at: "2026-02-03T10:00:00+00:00",
        }),
      ),
    ).toBe("Locked by abcdef01 on 2026-02-03.");
    expect(baselineLockSummary(state({ baseline_status: "locked" }))).toBe(
      "Provided baseline, not locked by a user.",
    );
    expect(baselineLockSummary(state())).toBeNull();
  });

  it("decides lockability from the server report only", () => {
    expect(baselineCanLock(validation())).toBe(true);
    const blocked = validation({
      blocking: [{ code: "unknown_state_object", message: "A node is missing." }],
    });
    expect(baselineCanLock(blocked)).toBe(false);
    expect(baselineBlockingReason(blocked)).toBe("A node is missing.");
    expect(baselineBlockingReason(null)).toBeNull();

    const empty = validation({ warnings: [{ code: "empty_baseline", message: "No objects." }] });
    expect(baselineNeedsEmptyConfirmation(empty)).toBe(true);
    expect(baselineNeedsEmptyConfirmation(validation())).toBe(false);
    expect(baselineSummary(validation())).toEqual([
      { label: "Objects captured", value: "3" },
      { label: "Canvas nodes", value: "3" },
      { label: "Canvas relationships", value: "1" },
    ]);
  });
});

describe("Lock baseline dialog", () => {
  it("shows the summary, warnings and blocking errors, and refuses to lock when blocked", async () => {
    stub(
      validation({
        blocking: [{ code: "unknown_state_object", message: "A node is missing." }],
        warnings: [{ code: "missing_owner", message: "No owner.", count: 2 }],
      }),
    );
    render(<LockBaselineDialog {...props()} />);

    await screen.findByTestId("baseline-validation");
    expect(screen.getByTestId("baseline-summary").textContent).toContain("Objects captured");
    expect(screen.getByTestId("baseline-blocking").textContent).toContain("A node is missing.");
    expect(screen.getByTestId("baseline-warnings").textContent).toContain("No owner. (2)");
    expect(screen.getByTestId("baseline-blocked-reason").textContent).toContain("A node is missing.");
    expect((screen.getByTestId("baseline-lock") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("baseline-confirm") as HTMLInputElement).disabled).toBe(true);
  });

  it("requires a confirmation, and an extra one for an empty baseline, before locking", async () => {
    const mock = stub(
      validation({ warnings: [{ code: "empty_baseline", message: "This baseline is empty." }] }),
    );
    const input = props();
    render(<LockBaselineDialog {...input} />);
    await screen.findByTestId("baseline-validation");

    const lockButton = screen.getByTestId("baseline-lock") as HTMLButtonElement;
    expect(lockButton.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("baseline-confirm"));
    // The empty-baseline confirmation is still outstanding.
    expect(lockButton.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("baseline-confirm-empty"));
    expect(lockButton.disabled).toBe(false);

    fireEvent.click(lockButton);
    await waitFor(() => expect(input.onLocked).toHaveBeenCalledTimes(1));
    expect(input.onLocked.mock.calls[0][0].baseline_status).toBe("locked");
    const write = mock.mock.calls.find(
      (call) => !JSON.parse(String(call[1]?.body ?? "{}")).validate_only,
    );
    expect(JSON.parse(String(write?.[1]?.body)).confirm_empty).toBe(true);
  });

  it("locks a validated baseline after a single confirmation and never offers an unlock", async () => {
    const mock = stub(validation({ warnings: [] }));
    const input = props();
    render(<LockBaselineDialog {...input} />);
    await screen.findByTestId("baseline-validation");

    // The first call only validated: no lock happened on open.
    expect(JSON.parse(String(mock.mock.calls[0][1]?.body)).validate_only).toBe(true);
    fireEvent.click(screen.getByTestId("baseline-confirm"));
    fireEvent.click(screen.getByTestId("baseline-lock"));
    await waitFor(() => expect(input.onLocked).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/unlock/i)?.textContent ?? "").toContain("cannot be unlocked");
  });

  it("surfaces a failed lock without closing the dialog", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}"));
        if (body.validate_only) {
          return { ok: true, status: 200, json: async () => ({ state: state(), validation: validation(), locked: false }) };
        }
        return {
          ok: false,
          status: 409,
          json: async () => ({ detail: { code: "baseline_confirmation_required", message: "Confirm the empty baseline." } }),
        };
      }),
    );
    const input = props();
    render(<LockBaselineDialog {...input} />);
    await screen.findByTestId("baseline-validation");
    fireEvent.click(screen.getByTestId("baseline-confirm"));
    fireEvent.click(screen.getByTestId("baseline-lock"));

    await screen.findByTestId("baseline-error");
    expect(screen.getByTestId("baseline-error").textContent).toContain("Confirm the empty baseline.");
    expect(input.onLocked).not.toHaveBeenCalled();
  });
});
