// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import NewWorkspaceModal from "./NewWorkspaceModal";

afterEach(() => {
  cleanup();
});

function renderModal(overrides: Partial<React.ComponentProps<typeof NewWorkspaceModal>> = {}) {
  const props = {
    isOpen: true,
    onClose: vi.fn(),
    onCreate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const result = render(<NewWorkspaceModal {...props} />);
  return { ...result, props };
}

function checkbox(name: RegExp): HTMLInputElement {
  return screen.getByRole<HTMLInputElement>("checkbox", { name });
}

describe("NewWorkspaceModal", () => {
  it("portals the dialog to the document body so the sticky header cannot clip it", () => {
    renderModal();
    const dialog = screen.getByRole("dialog");
    expect(dialog.parentElement).toBe(document.body);
  });

  it("offers workspace presets, disciplines with explanations and an initial state", () => {
    renderModal();
    for (const preset of [
      "Integration Workspace",
      "Solution Design",
      "Solution \\+ Integration",
      "Full Architecture",
    ]) {
      expect(screen.getByRole("button", { name: new RegExp(preset) })).toBeTruthy();
    }
    expect(screen.getByRole("checkbox", { name: /Enterprise Architecture/ })).toBeTruthy();
    expect(screen.getByText(/Information objects, logical attributes/)).toBeTruthy();
    expect(screen.getByRole("radio", { name: /^Current baseline draft/ })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /Candidate starter/ })).toBeTruthy();
  });

  it("selects a preset's disciplines and submits a candidate starter", () => {
    const { props } = renderModal();
    fireEvent.click(screen.getByRole("button", { name: /Integration Workspace/ }));
    expect(checkbox(/Integration Architecture/).checked).toBe(true);
    expect(checkbox(/Solution Architecture/).checked).toBe(false);
    fireEvent.change(screen.getByRole("textbox", { name: /Workspace Name/ }), {
      target: { value: "Payments integration" },
    });
    fireEvent.click(screen.getByRole("radio", { name: /Candidate starter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create Workspace" }));
    expect(props.onCreate).toHaveBeenCalledWith(
      "Payments integration",
      "",
      null,
      ["integration"],
      "candidate",
    );
  });

  it("passes the chosen demo preset and its disciplines, and pins the initial state", () => {
    const { props } = renderModal();
    fireEvent.change(screen.getByRole("textbox", { name: /Workspace Name/ }), {
      target: { value: "Solution demo" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Start with a deterministic demo/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Solution \+ Integration demo/ }));
    expect(checkbox(/Solution Architecture/).checked).toBe(true);
    expect(checkbox(/Integration Architecture/).checked).toBe(true);
    expect(screen.getByRole("radio", { name: /^Current baseline draft/ }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Create Workspace" }));
    expect(props.onCreate).toHaveBeenCalledWith(
      "Solution demo",
      "",
      "solution_integration",
      ["solution", "integration"],
      "current",
    );
  });

  it("clears demo content when the disciplines no longer match its scope", () => {
    renderModal();
    fireEvent.click(screen.getByRole("checkbox", { name: /Start with a deterministic demo/ }));
    const demo = screen.getByRole("radio", { name: /^Integration demo/ });
    fireEvent.click(demo);
    expect(checkbox(/Solution Architecture/).checked).toBe(false);
    fireEvent.click(checkbox(/Enterprise Architecture/));
    expect(screen.queryByRole("radio", { name: /^Integration demo/ })).toBeNull();
    expect(checkbox(/Enterprise Architecture/).checked).toBe(true);
  });

  it("requires a name and keeps at least one discipline enabled", () => {
    const { props } = renderModal();
    fireEvent.change(screen.getByRole("textbox", { name: /Workspace Name/ }), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Workspace" }));
    expect(screen.getByRole("alert").textContent).toContain("workspace name");

    // Disable three disciplines, then refuse to disable the last one.
    fireEvent.click(checkbox(/Enterprise Architecture/));
    fireEvent.click(checkbox(/Information Architecture/));
    fireEvent.click(checkbox(/Solution Architecture/));
    fireEvent.click(checkbox(/Integration Architecture/));
    expect(checkbox(/Integration Architecture/).checked).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("At least one");
    expect(props.onCreate).not.toHaveBeenCalled();
  });
});
