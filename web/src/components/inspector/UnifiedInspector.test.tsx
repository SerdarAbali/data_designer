// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UnifiedInspector from "./UnifiedInspector";

afterEach(cleanup);

function renderInspector() {
  const onCollapse = vi.fn();
  const onClose = vi.fn();
  render(
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
    />,
  );
  return { onCollapse, onClose };
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
});
