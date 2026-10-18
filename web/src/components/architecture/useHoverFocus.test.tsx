// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHoverFocus } from "./useHoverFocus";

const edges = [
  { id: "e1", source: "a", target: "b" },
  { id: "e2", source: "b", target: "c" },
];

describe("useHoverFocus", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("engages the focus only once the pointer has settled", () => {
    const { result } = renderHook(() => useHoverFocus(edges));
    expect(result.current.focus).toBeNull();
    act(() => result.current.onEdgeEnter({ id: "e1" }));
    // Still nothing: a pointer sweeping across the canvas must not dim it.
    expect(result.current.focus).toBeNull();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect([...result.current.focus!.edges]).toEqual(["e1"]);
    expect([...result.current.focus!.nodes].sort()).toEqual(["a", "b"]);
  });

  it("does not blank the canvas while the pointer moves between elements", () => {
    const { result } = renderHook(() => useHoverFocus(edges));
    act(() => result.current.onNodeEnter({ id: "b" }));
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect([...result.current.focus!.edges].sort()).toEqual(["e1", "e2"]);

    // Leaving and immediately entering another element cancels the clear.
    act(() => result.current.onLeave());
    act(() => result.current.onEdgeEnter({ id: "e2" }));
    expect(result.current.focus).not.toBeNull();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect([...result.current.focus!.edges]).toEqual(["e2"]);
    expect(result.current.target.edge).toBe("e2");
  });

  it("clears the focus once the pointer settles away from every element", () => {
    const { result } = renderHook(() => useHoverFocus(edges));
    act(() => result.current.onEdgeEnter({ id: "e1" }));
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.focus).not.toBeNull();
    act(() => result.current.onLeave());
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.focus).toBeNull();
    expect(result.current.target).toEqual({ node: null, edge: null });
  });
});
