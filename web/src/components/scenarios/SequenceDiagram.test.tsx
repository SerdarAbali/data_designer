// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import SequenceDiagram from "./SequenceDiagram";
import { sampleScenario, scenarioTestIndex } from "../../scenarioTestFixtures";

afterEach(cleanup);

describe("SequenceDiagram", () => {
  it("renders lifelines, fragments, and contract/phase labels", async () => {
    const index = await scenarioTestIndex();
    const { container } = render(<SequenceDiagram document={sampleScenario()} index={index} />);

    expect(screen.getByRole("group", { name: "Scenario sequence diagram" })).toBeTruthy();
    expect(container.querySelectorAll(".scenario-lifeline")).toHaveLength(4);
    expect(container.querySelector(".scenario-fragment-alt")).toBeTruthy();
    expect(container.querySelector(".scenario-fragment-loop")).toBeTruthy();
    expect(screen.getByText("[accepted]")).toBeTruthy();
    expect(screen.getByText("[each site]")).toBeTruthy();
    expect(container.textContent).toContain("Customer push · Request");
    expect(container.textContent).toContain("Customer push · Error response");
    expect(container.textContent).toContain("Site sync · Request");
  });

  it("opens the referenced contract phase on click and keyboard", async () => {
    const index = await scenarioTestIndex();
    const onOpen = vi.fn();
    render(<SequenceDiagram document={sampleScenario()} index={index} onOpenContractPhase={onOpen} />);

    const contractMessages = screen.getAllByRole("button");
    // Only the four contract steps are clickable; actor messages and self-calls are not.
    expect(contractMessages).toHaveLength(4);
    fireEvent.click(contractMessages[0]);
    expect(onOpen).toHaveBeenLastCalledWith("c-push", "request");
    fireEvent.keyDown(contractMessages[2], { key: "Enter" });
    expect(onOpen).toHaveBeenLastCalledWith("c-push", "error-response");
    fireEvent.keyDown(contractMessages[3], { key: " " });
    expect(onOpen).toHaveBeenLastCalledWith("c-site", "request");
  });
});
