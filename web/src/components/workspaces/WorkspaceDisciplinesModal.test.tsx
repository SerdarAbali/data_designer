// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WorkspaceDisciplinesModal from "./WorkspaceDisciplinesModal";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import { ARCHITECTURE_DISCIPLINES, type WorkspaceInfo } from "../../architectureTypes";

const workspace: WorkspaceInfo = {
  id: "workspace-1",
  name: "Original workspace",
  disciplines: ["enterprise", "information", "solution", "integration"],
  created_at: "2026-10-15T00:00:00Z",
  is_active: true,
  systems_count: 5,
  contracts_count: 3,
  scenarios_count: 2,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderModal(overrides: Partial<React.ComponentProps<typeof WorkspaceDisciplinesModal>> = {}) {
  const props = {
    isOpen: true,
    workspace,
    onClose: vi.fn(),
    onUpdate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const result = render(<WorkspaceDisciplinesModal {...props} />);
  return { ...result, props };
}

describe("Workspace Settings", () => {
  it("renders outside the header with a title, close button, name and all four disciplines", () => {
    const { container, props } = renderModal();
    const dialog = screen.getByRole("dialog", { name: "Workspace Settings" });
    expect(dialog.parentElement).toBe(document.body);
    expect(container.childElementCount).toBe(0);
    expect(screen.getByRole("heading", { name: "Workspace Settings" })).toBeTruthy();
    expect(screen.getByRole<HTMLInputElement>("textbox", { name: "Workspace name" }).value)
      .toBe(workspace.name);
    for (const discipline of ARCHITECTURE_DISCIPLINES) {
      expect(screen.getByRole<HTMLInputElement>("checkbox", { name: new RegExp(discipline.label) }).checked)
        .toBe(true);
    }
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(props.onClose).toHaveBeenCalledOnce();
    expect(props.onUpdate).not.toHaveBeenCalled();
  });

  it("saves the trimmed name and selected disciplines before closing", async () => {
    let finishSave!: () => void;
    const onUpdate = vi.fn(() => new Promise<void>((resolve) => { finishSave = resolve; }));
    const { props } = renderModal({ onUpdate });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "  Renamed workspace  " } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Information Architecture/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onUpdate).toHaveBeenCalledWith(workspace.id, "Renamed workspace", [
      "enterprise", "solution", "integration",
    ]);
    expect(props.onClose).not.toHaveBeenCalled();
    finishSave();
    await waitFor(() => expect(props.onClose).toHaveBeenCalledOnce());
  });

  it("shows save errors and keeps edits open for retry", async () => {
    const onUpdate = vi.fn().mockRejectedValue(new Error("A workspace with this name already exists"));
    const { props } = renderModal({ onUpdate });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Duplicate" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already exists");
    expect(props.onClose).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>("textbox").value).toBe("Duplicate");
  });

  it("rejects whitespace names and prevents disabling the final discipline", () => {
    const { props } = renderModal({ workspace: { ...workspace, disciplines: ["enterprise"] } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Enterprise Architecture/ }));
    expect(screen.getByRole("alert").textContent).toContain("At least one discipline");
    expect(screen.getByRole<HTMLInputElement>("checkbox", { name: /Enterprise Architecture/ }).checked)
      .toBe(true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByRole("alert").textContent).toContain("Please enter a workspace name");
    expect(props.onUpdate).not.toHaveBeenCalled();
  });

  it("discards edits and errors when reopened", () => {
    const { props, rerender } = renderModal();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Solution Architecture/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onUpdate).not.toHaveBeenCalled();
    rerender(<WorkspaceDisciplinesModal {...props} isOpen={false} />);
    rerender(<WorkspaceDisciplinesModal {...props} />);
    expect(screen.getByRole<HTMLInputElement>("textbox").value).toBe(workspace.name);
    expect(screen.getByRole<HTMLInputElement>("checkbox", { name: /Solution Architecture/ }).checked)
      .toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("disables editing and submission while saving", () => {
    const { props } = renderModal({ loading: true });
    expect(screen.getByRole<HTMLInputElement>("textbox").disabled).toBe(true);
    for (const checkbox of screen.getAllByRole<HTMLInputElement>("checkbox")) {
      expect(checkbox.disabled).toBe(true);
    }
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Close" }).disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Saving…" }).disabled).toBe(true);
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    expect(props.onUpdate).not.toHaveBeenCalled();
  });

  it("PATCHes both settings with CSRF, refreshes the header and reopens with saved values", async () => {
    const updated: WorkspaceInfo = { ...workspace, name: "Saved workspace", disciplines: ["enterprise"] };
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      Response.json(init?.method === "PATCH" ? updated : [workspace]));
    vi.stubGlobal("fetch", fetchMock);
    const onUpdated = vi.fn();
    const onSwitch = vi.fn();
    const { container } = render(
      <WorkspaceSwitcher
        currentWorkspaceName={workspace.name}
        csrfToken={() => "test-csrf"}
        onSwitch={onSwitch}
        onDisciplinesUpdated={onUpdated}
      />,
    );
    const details = container.querySelector("details")!;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    fireEvent.click(await screen.findByRole("button", { name: "⚙ Settings" }));
    expect(container.querySelector("details")?.open).toBe(false);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: updated.name } });
    for (const name of [/Information Architecture/, /Solution Architecture/, /Integration Architecture/]) {
      fireEvent.click(screen.getByRole("checkbox", { name }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(patch?.[0]).toBe(`/api/workspaces/${workspace.id}`);
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      name: updated.name, disciplines: updated.disciplines,
    });
    expect(new Headers(patch?.[1]?.headers).get("X-CSRF-Token")).toBe("test-csrf");
    expect(onUpdated).toHaveBeenCalledOnce();
    expect(onSwitch).not.toHaveBeenCalled();
    expect(container.querySelector(".ws-switcher-name")?.textContent).toBe(updated.name);
    details.open = true;
    fireEvent.click(screen.getByRole("button", { name: "⚙ Settings" }));
    expect(screen.getByRole<HTMLInputElement>("textbox").value).toBe(updated.name);
    expect(screen.getAllByRole<HTMLInputElement>("checkbox").filter((input) => input.checked))
      .toHaveLength(1);
  });
});
