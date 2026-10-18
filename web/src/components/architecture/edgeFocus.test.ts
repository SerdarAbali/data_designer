import { describe, expect, it } from "vitest";

import { edgeFocusSets } from "./edgeFocus";

const edges = [
  { id: "e1", source: "a", target: "b" },
  { id: "e2", source: "b", target: "c" },
  { id: "e3", source: "c", target: "d" },
];

describe("edgeFocusSets", () => {
  it("keeps everything at full strength when nothing is hovered", () => {
    expect(edgeFocusSets(null, null, edges)).toBeNull();
  });

  it("isolates a hovered edge and its two endpoints", () => {
    const focus = edgeFocusSets(null, "e2", edges)!;
    expect([...focus.edges]).toEqual(["e2"]);
    expect([...focus.nodes].sort()).toEqual(["b", "c"]);
  });

  it("keeps a hovered node plus every connection that touches it", () => {
    const focus = edgeFocusSets("b", null, edges)!;
    expect([...focus.edges].sort()).toEqual(["e1", "e2"]);
    expect([...focus.nodes].sort()).toEqual(["a", "b", "c"]);
  });

  it("ignores an unknown edge id instead of dimming the whole canvas", () => {
    expect(edgeFocusSets(null, "missing", edges)).toBeNull();
  });
});
