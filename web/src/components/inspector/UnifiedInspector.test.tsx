// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UnifiedInspector from "./UnifiedInspector";

afterEach(cleanup);

function renderInspector(overrides: Partial<React.ComponentProps<typeof UnifiedInspector>> = {}) {
  const onCollapse = vi.fn();
  const onClose = vi.fn();
  const utils = render(
    <UnifiedInspector
      ariaLabel="Thing details"
      eyebrow="THING"
      title="Payment API"
      stateName="Candidate"
      status="Editable"
      collapseLabel="Collapse thing inspector"
      closeLabel="Close thing details"
      onCollapse={onCollapse}
      onClose={onClose}
      panels={[
        { id: "properties", label: "Properties", content: <p>Properties body</p> },
        { id: "relationships", label: "Relationships", count: 2, content: <p>Relationships body</p> },
        { id: "traceability", label: "Traceability", content: <p>Traceability body</p> },
      ]}
      {...overrides}
    />,
  );
  return { ...utils, onCollapse, onClose };
}

describe("UnifiedInspector", () => {
  it("shows one tab at a time and switches content", () => {
    renderInspector();
    const panelOf = (text: string) =>
      screen.getByText(text).closest(".unified-inspector-panel") as HTMLElement;
    expect(panelOf("Properties body").hidden).toBe(false);
    expect(panelOf("Relationships body").hidden).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Relationships (2)" }));
    expect(panelOf("Relationships body").hidden).toBe(false);
    expect(panelOf("Properties body").hidden).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Traceability" }));
    expect(panelOf("Traceability body").hidden).toBe(false);
  });

  it("exposes collapse and close actions", () => {
    const { onCollapse, onClose } = renderInspector();
    fireEvent.click(screen.getByRole("button", { name: "Collapse thing inspector" }));
    expect(onCollapse).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Close thing details" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps the manage menu keyboard operable and restores focus on Escape", () => {
    renderInspector({
      manageMenu: (
        <button type="button" className="more-menu-item more-menu-item--danger">
          Archive
        </button>
      ),
    });
    const trigger = screen.getByRole("button", { name: "Manage object" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const menu = screen.getByRole("menu", { name: "Manage object" });
    expect(menu.hidden).toBe(false);
    expect(screen.getByRole("button", { name: "Archive" })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
  });

  it("shows a save status chip only when a save is in flight or failed", () => {
    const { rerender } = renderInspector({ saveStatus: "saved" });
    expect(screen.getByRole("status").textContent).toContain("Saved");
    rerender(
      <UnifiedInspector
        ariaLabel="Thing details"
        eyebrow="THING"
        title="Payment API"
        stateName="Candidate"
        status="Editable"
        saveStatus="error"
        collapseLabel="Collapse thing inspector"
        closeLabel="Close thing details"
        onCollapse={() => {}}
        onClose={() => {}}
        panels={[{ id: "properties", label: "Properties", content: <p>Properties body</p> }]}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("Save failed");
  });

  it("restores focus to the opener when the inspector unmounts", () => {
    const opener = document.createElement("button");
    opener.textContent = "opener";
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = renderInspector();
    unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
