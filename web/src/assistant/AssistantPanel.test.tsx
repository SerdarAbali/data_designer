// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantLauncher, AssistantPanel } from "./AssistantPanel";

const READY_STATUS = {
  assistant_enabled: true,
  runtime_status: "ready",
  expected_opencode_version: "2.0.30",
  observed_opencode_version: "2.0.30",
  probe_checked_at: "2026-01-01T00:00:00Z",
  reason_code: "ok",
  correlation_id: "cor_test",
  workspace_enabled: true,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPanel(overrides: Partial<React.ComponentProps<typeof AssistantPanel>> = {}) {
  return render(
    <AssistantPanel
      workspaceId={null}
      workspaceName="Demo"
      disciplines={["enterprise", "information"]}
      discipline="enterprise"
      states={[]}
      stateId={null}
      workbenchView="canvas"
      selectionIds={[]}
      open
      onClose={() => {}}
      {...overrides}
    />,
  );
}

describe("AssistantLauncher", () => {
  it("is a labelled, expandable control", () => {
    render(<AssistantLauncher open={false} onOpen={() => {}} />);
    const button = screen.getByRole("button", { name: /assistant/i });
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("AssistantPanel", () => {
  it("shows the explicit notice and no write controls", () => {
    renderPanel();
    expect(
      screen.getByText(
        /The Assistant can inspect architecture and prepare proposals. It cannot approve, apply, or undo changes. Those actions require you./i,
      ),
    ).toBeTruthy();
    for (const forbidden of [/apply/i, /approve/i, /undo/i, /propose/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).toBeNull();
    }
  });

  it("shows the active discipline published by the canvas (Integration tab)", () => {
    renderPanel({ discipline: "integration", workbenchView: "integration" });
    expect(screen.getByText(/Discipline: integration/)).toBeTruthy();
    expect(screen.queryByText(/Discipline: enterprise/)).toBeNull();
    expect(screen.getByText(/View: integration/)).toBeTruthy();
  });

  it("clarifies that Current is read-only", () => {
    renderPanel({
      states: [{ id: "s-current", name: "Current", state_type: "current" }],
      stateId: "s-current",
    });
    expect(
      screen.getByText(/Current is read-only. Switch to a Candidate or Target state to prepare proposals./i),
    ).toBeTruthy();
  });

  it("updates the state chip immediately when the canvas state changes", () => {
    const states = [
      { id: "s-current", name: "Current", state_type: "current" },
      { id: "s-candidate", name: "Candidate", state_type: "candidate" },
    ];
    const { rerender } = renderPanel({ states, stateId: "s-current" });
    expect(screen.getByLabelText("Architecture state")).toHaveProperty("value", "s-current");
    rerender(
      <AssistantPanel
        workspaceId={null}
        workspaceName="Demo"
        disciplines={["enterprise"]}
        discipline="enterprise"
        states={states}
        stateId="s-candidate"
        workbenchView="canvas"
        selectionIds={[]}
        open
        onClose={() => {}}
      />,
    );
    expect(screen.getByLabelText("Architecture state")).toHaveProperty("value", "s-candidate");
    expect(screen.queryByText(/Current is read-only/)).toBeNull();
  });

  it("renders a disabled state when the workspace is not enabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = String(input);
        const body = url.includes("/status")
          ? { ...READY_STATUS, workspace_enabled: false, runtime_status: "disabled" }
          : [];
        return { ok: true, status: 200, json: async () => body };
      }),
    );
    renderPanel({ workspaceId: "ws-1" });
    await waitFor(() => {
      expect(screen.getByText(/disabled for this workspace/i)).toBeTruthy();
    });
  });

  it("shows a ready state and enables starting a conversation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const url = String(input);
        const body = url.includes("/status") ? READY_STATUS : [];
        return { ok: true, status: 200, json: async () => body };
      }),
    );
    renderPanel({ workspaceId: "ws-1" });
    await waitFor(() => {
      expect(screen.getByText(/Ready — read-only architecture assistant/i)).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: "New" }).hasAttribute("disabled")).toBe(false);
  });

  it("is hidden when closed", () => {
    renderPanel({ open: false });
    const panel = screen.getByTestId("assistant-panel");
    expect(panel.hasAttribute("hidden")).toBe(true);
  });
});
