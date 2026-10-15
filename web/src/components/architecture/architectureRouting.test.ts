import { describe, expect, it } from "vitest";

import {
  buildRoute,
  chooseHandles,
  handleId,
  labelPoint,
  ROUTE_CLEARANCE,
  roundedOrthogonalPath,
  type Rect,
} from "./architectureRouting";

function segmentClears(a: { x: number; y: number }, b: { x: number; y: number }, obstacle: Rect) {
  const minX = obstacle.x - ROUTE_CLEARANCE;
  const maxX = obstacle.x + obstacle.width + ROUTE_CLEARANCE;
  const minY = obstacle.y - ROUTE_CLEARANCE;
  const maxY = obstacle.y + obstacle.height + ROUTE_CLEARANCE;
  if (a.x === b.x) {
    const overlapY = Math.min(Math.max(a.y, b.y), maxY) - Math.max(Math.min(a.y, b.y), minY);
    return !(a.x > minX && a.x < maxX && overlapY > 0);
  }
  if (a.y === b.y) {
    const overlapX = Math.min(Math.max(a.x, b.x), maxX) - Math.max(Math.min(a.x, b.x), minX);
    return !(a.y > minY && a.y < maxY && overlapX > 0);
  }
  return true;
}

describe("architecture routing", () => {
  it("chooses handles from relative rectangle positions", () => {
    const left = { x: 0, y: 0, width: 200, height: 90 };
    const right = { x: 400, y: 10, width: 200, height: 90 };
    expect(chooseHandles(left, right)).toEqual({ source: "right", target: "left" });
    expect(chooseHandles(right, left)).toEqual({ source: "left", target: "right" });
    const below = { x: 10, y: 400, width: 200, height: 90 };
    expect(chooseHandles(left, below)).toEqual({ source: "bottom", target: "top" });
    expect(handleId("source", "top")).toBe("s-top");
    expect(handleId("target", "left")).toBe("t-left");
  });

  it("routes around an obstacle with clearance", () => {
    const obstacle: Rect = { x: 180, y: 20, width: 40, height: 60 };
    const points = buildRoute({ x: 0, y: 50 }, { x: 400, y: 50 }, "right", "left", [obstacle]);
    for (let i = 0; i < points.length - 1; i += 1) {
      expect(segmentClears(points[i], points[i + 1], obstacle)).toBe(true);
    }
    expect(points.some((p) => p.y <= obstacle.y - ROUTE_CLEARANCE + 0.001)).toBe(true);
  });

  it("renders rounded orthogonal paths", () => {
    const path = roundedOrthogonalPath([{ x: 0, y: 0 }, { x: 0, y: 40 }, { x: 40, y: 40 }]);
    expect(path.startsWith("M 0,0")).toBe(true);
    expect(path).toContain("Q");
    expect(path.endsWith("L 40,40")).toBe(true);
  });

  it("places the label on the longest segment", () => {
    const anchor = labelPoint([{ x: 0, y: 0 }, { x: 0, y: 100 }, { x: 20, y: 100 }]);
    expect(anchor).toEqual({ x: 0, y: 50 });
  });
});
