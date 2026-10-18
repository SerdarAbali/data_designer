// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import type { WorkspaceInfo } from "../../architectureTypes";

const workspace: WorkspaceInfo = {
  id: "workspace-1",
  name: "Default workspace",
  disciplines: ["enterprise", "information", "solution", "integration"],
  created_at: "2026-10-15T00:00:00Z",
  is_active: true,
  systems_count: 0,
  contracts_count: 0,
  scenarios_count: 0,
};

const created: WorkspaceInfo = {
  ...workspace,
  id: "workspace-new",
  name: "New integration workspace",
  disciplines: ["integration"],
  is_active: true,
};

beforeEach(() => {
  sessionStorage.clear();
  document.cookie = "dd_csrf=test";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function openNewWorkspaceForm() {
  const container = document.body;
  const details = container.querySelector("details.workspace-switcher") as HTMLDetailsElement;
  details.open = true;
  fireEvent(details, new Event("toggle"));
  fireEvent.click(await screen.findByRole("button", { name: "+ New Workspace" }));
}

function stubFetch(overrides: Record<string, Response | (() => Response)> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      calls.push({ url, init });
      const key = `${init?.method ?? "GET"} ${url}`;
      if (overrides[key]) {
        const value = overrides[key];
        return typeof value === "function" ? value() : value;
      }
      if (url === "/api/workspaces" && init?.method === "POST") {
        return new Response(JSON.stringify(created), { status: 201 });
      }
      if (url === "/api/workspaces") return new Response(JSON.stringify([workspace]));
      if (url === "/api/workspaces/workspace-new/states" && init?.method === "POST") {
        return new Response(JSON.stringify({ id: "state-candidate" }), { status: 201 });
      }
      if (url === "/api/workspaces/workspace-new/states") {
        return new Response(JSON.stringify([{ id: "state-current", state_type: "current" }]));
      }
      return new Response(JSON.stringify([]));
    }),
  );
  return calls;
}

describe("WorkspaceSwitcher workspace creation", () => {
  it("creates a scoped workspace and seeds a candidate starter when requested", async () => {
    const calls = stubFetch();
    const onSwitch = vi.fn();
    render(
      <WorkspaceSwitcher
        currentWorkspaceName={workspace.name}
        csrfToken={() => "test-csrf"}
        onSwitch={onSwitch}
      />,
    );
    await openNewWorkspaceForm();
    fireEvent.change(screen.getByRole("textbox", { name: /Workspace Name/ }), {
      target: { value: "New integration workspace" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Integration Workspace/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Candidate starter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create Workspace" }));

    await waitFor(() => expect(onSwitch).toHaveBeenCalled());
    const createCall = calls.find(
      ({ url, init }) => url === "/api/workspaces" && init?.method === "POST",
    );
    expect(JSON.parse(String(createCall?.init?.body))).toEqual({
      name: "New integration workspace",
      description: null,
      seed_demo_data: false,
      demo_preset: null,
      baseline: "candidate_starter",
      disciplines: ["integration"],
    });
    // The server materialises the baseline states, so no follow-up call is made.
    const statePosts = calls.filter(
      ({ url, init }) => url.endsWith("/states") && init?.method === "POST",
    );
    expect(statePosts).toHaveLength(0);
  });

  it("creates a demo workspace without seeding a separate candidate", async () => {
    const calls = stubFetch();
    const onSwitch = vi.fn();
    render(
      <WorkspaceSwitcher
        currentWorkspaceName={workspace.name}
        csrfToken={() => "test-csrf"}
        onSwitch={onSwitch}
      />,
    );
    await openNewWorkspaceForm();
    fireEvent.change(screen.getByRole("textbox", { name: /Workspace Name/ }), {
      target: { value: "Demo workspace" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Start with a deterministic demo/ }));
    fireEvent.click(screen.getByRole("radio", { name: /^Integration demo/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create Workspace" }));

    await waitFor(() => expect(onSwitch).toHaveBeenCalled());
    const createCall = calls.find(
      ({ url, init }) => url === "/api/workspaces" && init?.method === "POST",
    );
    expect(JSON.parse(String(createCall?.init?.body))).toMatchObject({
      demo_preset: "integration_only",
      disciplines: ["integration"],
    });
    expect(
      calls.filter(({ url, init }) => url.endsWith("/states") && init?.method === "POST"),
    ).toHaveLength(0);
  });
});
