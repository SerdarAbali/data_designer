// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import WorkspaceNav from "./WorkspaceNav";

afterEach(() => cleanup());

describe("WorkspaceNav", () => {
  it("shows only relevant surfaces per discipline scope", () => {
    const { rerender } = render(
      <WorkspaceNav disciplines={["integration"]} activeView="canvas" onNavigate={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Canvas" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Contracts" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Catalog" })).toBeTruthy();

    rerender(<WorkspaceNav disciplines={["solution"]} activeView="canvas" onNavigate={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Contracts" })).toBeNull();
    expect(screen.getByRole("button", { name: "Catalog" })).toBeTruthy();

    rerender(<WorkspaceNav disciplines={["enterprise"]} activeView="canvas" onNavigate={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Contracts" })).toBeNull();
    expect(screen.getByRole("button", { name: "Catalog" })).toBeTruthy();
  });

  it("keeps Contracts for Solution + Integration and Full Architecture", () => {
    for (const disciplines of [
      ["solution", "integration"],
      ["enterprise", "information", "solution", "integration"],
    ] as const) {
      const { unmount } = render(
        <WorkspaceNav disciplines={[...disciplines]} activeView="canvas" onNavigate={vi.fn()} />,
      );
      expect(screen.getByRole("button", { name: "Contracts" })).toBeTruthy();
      unmount();
    }
  });

  it("marks the active surface and reports navigation", () => {
    const onNavigate = vi.fn();
    render(<WorkspaceNav disciplines={["integration"]} activeView="integrations" onNavigate={onNavigate} />);
    expect(screen.getByRole("button", { name: "Contracts" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Catalog" }));
    expect(onNavigate).toHaveBeenCalledWith("catalog");
  });
});
