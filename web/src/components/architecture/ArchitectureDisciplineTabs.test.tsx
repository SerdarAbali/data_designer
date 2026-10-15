// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ArchitectureDisciplineTabs from "./ArchitectureDisciplineTabs";

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
});
