// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ArchitectureDisciplineTabs from "./ArchitectureDisciplineTabs";

afterEach(() => cleanup());

describe("ArchitectureDisciplineTabs", () => {
  it("shows only enabled disciplines and reports view changes", () => {
    const onSelect = vi.fn();
    render(
      <ArchitectureDisciplineTabs
        disciplines={["solution", "integration"]}
        activeDiscipline="solution"
        onSelect={onSelect}
      />,
    );

    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("tab", { name: "Solution Architecture" }).getAttribute("aria-selected"))
      .toBe("true");
    expect(screen.queryByRole("tab", { name: "Enterprise Architecture" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Integration Architecture" }));
    expect(onSelect).toHaveBeenCalledWith("integration");
  });

  it("preserves the full four-discipline tab group for Full Architecture", () => {
    const onSelect = vi.fn();
    render(
      <ArchitectureDisciplineTabs
        disciplines={["enterprise", "information", "solution", "integration"]}
        activeDiscipline="enterprise"
        onSelect={onSelect}
      />,
    );

    expect(screen.getAllByRole("tab")).toHaveLength(4);
    fireEvent.click(screen.getByRole("tab", { name: "Information Architecture" }));
    expect(onSelect).toHaveBeenCalledWith("information");
  });

  it("renders a single enabled discipline as context, not a one-item tab group", () => {
    const onSelect = vi.fn();
    render(
      <ArchitectureDisciplineTabs
        disciplines={["integration"]}
        activeDiscipline="integration"
        onSelect={onSelect}
      />,
    );

    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.queryByRole("tablist")).toBeNull();
    const context = screen.getByLabelText("Architecture discipline: Integration Architecture");
    expect(context.textContent).toContain("Integration Architecture");
  });
});
