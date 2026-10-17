import { describe, expect, it } from "vitest";

import {
  buildRoute,
  chooseHandles,
  handleId,
  labelPoint,
  nodeRectMap,
  obstaclesForEdge,
  ROUTE_CLEARANCE,
  roundedOrthogonalPath,
  simplifyPoints,
  type Rect,
} from "./architectureRouting";
import { withEdgeObstacles } from "./edgeObstacles";

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

  it("collapses duplicate and collinear waypoints", () => {
    const simplified = simplifyPoints([
      { x: 0, y: 0 },
      { x: 0, y: 0 },
      { x: 50, y: 0 },
      { x: 100, y: 0 },
    ]);
    expect(simplified).toEqual([{ x: 0, y: 0 }, { x: 100, y: 0 }]);
  });

  it("loops an edge whose handles face away from each other around its boxes", () => {
    const source: Rect = { x: 0, y: 0, width: 120, height: 160 };
    const target: Rect = { x: 400, y: 40, width: 140, height: 160 };
    // Required port on the left (0,60) meeting a provided port on the right
    // (540,120): the target sits to the right, so the handles face away.
    const points = simplifyPoints(
      buildRoute(
        { x: source.x, y: 60 },
        { x: target.x + target.width, y: 120 },
        "left",
        "right",
        [],
        0,
        undefined,
        { source, target },
      ),
    );
    const last = points.length - 1;
    for (let i = 0; i < last; i += 1) {
      if (i === 0 || i === last - 1) continue; // stubs touch their own box
      expect(segmentClears(points[i], points[i + 1], source)).toBe(true);
      expect(segmentClears(points[i], points[i + 1], target)).toBe(true);
    }
    // The long run must clear the boxes above or below, not cut through them.
    expect(points.some((p) => p.y < source.y || p.y > source.y + source.height)).toBe(true);
  });

  it("excludes the endpoints and enclosing containers from edge obstacles", () => {
    const rects = nodeRectMap([
      { id: "a", position: { x: 0, y: 0 }, width: 100, height: 80 },
      { id: "b", position: { x: 300, y: 40 }, width: 100, height: 80 },
      { id: "panel", position: { x: -40, y: -40 }, width: 520, height: 260 },
      { id: "between", position: { x: 150, y: 0 }, width: 80, height: 80 },
    ]);
    const obstacles = obstaclesForEdge(rects, "a", "b");
    expect(obstacles).toHaveLength(1);
    expect(obstacles[0]).toEqual({ x: 150, y: 0, width: 80, height: 80 });
  });

  it("injects obstacle and endpoint rectangles into edge data", () => {
    const nodes = [
      { id: "a", position: { x: 0, y: 0 }, width: 100, height: 80 },
      { id: "b", position: { x: 300, y: 0 }, width: 100, height: 80 },
      { id: "between", position: { x: 150, y: 0 }, width: 60, height: 60 },
    ];
    const edges = [{ source: "a", target: "b", data: { marker: "keep" } as Record<string, unknown> }];
    const [edge] = withEdgeObstacles(nodes, edges);
    const data = edge.data as Record<string, unknown>;
    expect(data.marker).toBe("keep");
    expect(data.obstacles).toEqual([{ x: 150, y: 0, width: 60, height: 60 }]);
    expect(data.sourceRect).toEqual({ x: 0, y: 0, width: 100, height: 80 });
    expect(data.targetRect).toEqual({ x: 300, y: 0, width: 100, height: 80 });
  });
});
