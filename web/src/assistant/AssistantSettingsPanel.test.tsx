// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssistantSettingsPanel } from "./AssistantSettingsPanel";

const OWNER_SETTINGS = {
  workspace_enabled: true,
  is_owner: true,
  provider: "openai",
  model_id: "gpt-x",
  reasoning_effort: "medium",
  max_input_tokens: 16000,
  max_output_tokens: 4000,
  timeout_seconds: 180,
  step_limit: 12,
  retention_days: 30,
  privacy_classification: "internal",
  trains_on_data: false,
  approved_for_sensitive: true,
  fallback_enabled: false,
  fallback_provider: null,
  fallback_model_id: null,
  credential_status: "configured",
  credential_last_verified_at: "2026-01-01T00:00:00Z",
  privacy_allowed: true,
  privacy_reason: null,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = "";
});

beforeEach(() => {
  document.cookie = "dd_csrf=test-csrf-token";
});

function stub(payload: unknown) {
  const fetchMock = vi.fn(async (_path: string, _init?: RequestInit) => ({
    ok: true,
    status: 200,
    json: async () => payload,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AssistantSettingsPanel", () => {
  it("shows owner fields and only the credential status, never a secret", async () => {
    stub(OWNER_SETTINGS);
    render(<AssistantSettingsPanel workspaceId="ws-1" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("assistant-settings")).toBeTruthy());
    expect(screen.getByLabelText("Provider")).toHaveProperty("value", "openai");
    expect(screen.getByLabelText("Conversation retention (days)")).toHaveProperty("value", "30");
    expect(screen.getByTestId("credential-status").textContent).toContain("Configured");
    const text = screen.getByTestId("assistant-settings").textContent?.toLowerCase() ?? "";
    for (const forbidden of ["api_key", "apikey", "bearer", "secret", "sk-"]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("saves owner changes through the settings endpoint", async () => {
    const fetchMock = stub(OWNER_SETTINGS);
    render(<AssistantSettingsPanel workspaceId="ws-1" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("save-settings")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "gpt-y" } });
    fireEvent.click(screen.getByTestId("save-settings"));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([path, init]) =>
          String(path).endsWith("/settings/model") && (init as RequestInit)?.method === "PUT",
        ),
      ).toBe(true);
    });
  });

  it("shows only safe availability to non-owners", async () => {
    stub({
      workspace_enabled: false,
      is_owner: false,
      privacy_classification: "internal",
      credential_status: "missing",
      privacy_allowed: true,
      privacy_reason: null,
    });
    render(<AssistantSettingsPanel workspaceId="ws-1" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("settings-readonly")).toBeTruthy());
    expect(screen.queryByLabelText("Provider")).toBeNull();
    expect(screen.getByText(/Only a workspace owner can change/i)).toBeTruthy();
  });
});
