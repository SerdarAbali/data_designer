import { describe, expect, it } from "vitest";

import { resolveRelationshipHandles } from "./informationModel";

describe("resolveRelationshipHandles", () => {
  it("preserves a manual top-to-top selection", () => {
    const handles = resolveRelationshipHandles(
      { source_handle: "s-top", target_handle: "t-top" },
      { x: 0, y: 0 },
      { x: 300, y: 0 },
    );
    expect(handles).toEqual({ sourceHandle: "s-top", targetHandle: "t-top" });
  });

  it("preserves a manual bottom-to-left selection", () => {
    const handles = resolveRelationshipHandles(
      { source_handle: "s-bottom", target_handle: "t-left" },
      { x: 0, y: 0 },
      { x: 300, y: 0 },
    );
    expect(handles).toEqual({ sourceHandle: "s-bottom", targetHandle: "t-left" });
  });

  it("uses automatic routing when no handles are stored", () => {
    expect(
      resolveRelationshipHandles(
        { source_handle: null, target_handle: null },
        { x: 0, y: 0 },
        { x: 300, y: 0 },
      ),
    ).toEqual({ sourceHandle: "s-right", targetHandle: "t-left" });
    expect(
      resolveRelationshipHandles(
        { source_handle: null, target_handle: null },
        { x: 0, y: 0 },
        { x: 10, y: 300 },
      ),
    ).toEqual({ sourceHandle: "s-bottom", targetHandle: "t-top" });
  });

  it("falls back per endpoint when only one handle was stored", () => {
    expect(
      resolveRelationshipHandles(
        { source_handle: "s-top", target_handle: null },
        { x: 0, y: 0 },
        { x: 300, y: 0 },
      ),
    ).toEqual({ sourceHandle: "s-top", targetHandle: "t-left" });
  });

  it("returns to automatic routing after the handles are reset", () => {
    const reset = resolveRelationshipHandles(
      { source_handle: null, target_handle: null },
      { x: 300, y: 0 },
      { x: 0, y: 0 },
    );
    expect(reset).toEqual({ sourceHandle: "s-left", targetHandle: "t-right" });
  });
});
