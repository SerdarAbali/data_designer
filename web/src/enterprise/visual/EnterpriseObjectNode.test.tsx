// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import EnterpriseObjectNode from "./EnterpriseObjectNode";

vi.mock("@xyflow/react", () => ({
  Handle: () => null,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}));

afterEach(cleanup);

const baseData = {
  name: "Reduce customer onboarding time",
  kind: "goal",
  kindLabel: "Goal",
  owner: "Head of Customer Operations" as string | null,
  description: null as string | null,
  processType: null,
  gap: null,
  editable: false,
};

function renderNode(overrides: Partial<typeof baseData> = {}) {
  const props = {
    id: "node-1",
    type: "enterpriseObject",
    selected: false,
    data: { ...baseData, ...overrides },
  } as unknown as React.ComponentProps<typeof EnterpriseObjectNode>;
  return render(<EnterpriseObjectNode {...props} />);
}

describe("EnterpriseObjectNode", () => {
  it("renders the object description so enterprise cards are not bare", () => {
    renderNode({ description: "Cut onboarding time by half while preserving consent." });
    expect(
      screen.getByText("Cut onboarding time by half while preserving consent."),
    ).toBeDefined();
    expect(screen.getByText("Reduce customer onboarding time")).toBeDefined();
  });

  it("omits the description line when the object has none", () => {
    const { container } = renderNode({ description: null });
    expect(container.querySelector(".enterprise-node-description")).toBeNull();
  });
});
