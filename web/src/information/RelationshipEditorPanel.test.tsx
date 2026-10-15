// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RelationshipEditorPanel from "./RelationshipEditorPanel";
import type { InformationRelationship } from "./informationModel";

const base: InformationRelationship = {
  id: "rel-1",
  source_object_id: "ent-1",
  target_object_id: "ent-2",
  name: "places",
  cardinality: "one_to_many",
  source_optional: false,
  target_optional: true,
  source_handle: "s-top",
  target_handle: "t-top",
};

afterEach(cleanup);

function renderPanel(relationship: InformationRelationship, onChange = vi.fn()) {
  render(
    <RelationshipEditorPanel
      relationship={relationship}
      sourceLabel="Customer"
      targetLabel="Order"
      editable
      stateName="Candidate"
      saveStatus="idle"
      busy={false}
      onChange={onChange}
      onDelete={vi.fn()}
      onClose={vi.fn()}
      onCollapse={vi.fn()}
    />,
  );
  return onChange;
}

describe("RelationshipEditorPanel routing", () => {
  it("resets stored manual handles to automatic routing", () => {
    const onChange = renderPanel(base);
    expect(screen.getByText("Manual")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset to automatic routing" }));
    expect(onChange).toHaveBeenCalledWith("rel-1", { source_handle: null, target_handle: null });
  });

  it("hides the reset action when routing is already automatic", () => {
    renderPanel({ ...base, source_handle: null, target_handle: null });
    expect(screen.getByText("Automatic")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reset to automatic routing" })).toBeNull();
  });
});
