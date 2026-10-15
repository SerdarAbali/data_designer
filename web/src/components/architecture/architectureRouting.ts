/**
 * Pure geometry helpers for obstacle-aware architecture connector routing.
 *
 * The router is intentionally dependency-free: connectors are routed as
 * orthogonal waypoint lists that clear node and boundary rectangles by a fixed
 * margin, and are then drawn with slightly rounded corners. Nothing here is
 * persisted — waypoints are recomputed on every render from live node geometry.
 */

export type Rect = { x: number; y: number; width: number; height: number };
export type Point = { x: number; y: number };
export type FlowSide = "top" | "right" | "bottom" | "left";

/** Clearance kept between a connector and any obstacle rectangle. */
export const ROUTE_CLEARANCE = 16;

/** Corner rounding radius for routed orthogonal paths. */
export const ROUTE_RADIUS = 12;

const OUTWARD: Record<FlowSide, Point> = {
  top: { x: 0, y: -1 },
  bottom: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

export function handleId(kind: "source" | "target", side: FlowSide): string {
  return `${kind === "source" ? "s" : "t"}-${side}`;
}

export function rectCenter(rect: Rect): Point {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

/**
 * Chooses the source and target box sides (all four sides are wired) from the
 * relative position of two rectangles so each connector takes the shorter side.
 */
export function chooseHandles(source: Rect, target: Rect): { source: FlowSide; target: FlowSide } {
  const a = rectCenter(source);
  const b = rectCenter(target);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? { source: "right", target: "left" }
      : { source: "left", target: "right" };
  }
  return dy >= 0
    ? { source: "bottom", target: "top" }
    : { source: "top", target: "bottom" };
}

function inflate(rect: Rect, clearance: number): Rect {
  return {
    x: rect.x - clearance,
    y: rect.y - clearance,
    width: rect.width + clearance * 2,
    height: rect.height + clearance * 2,
  };
}

function segmentHits(a: Point, b: Point, obstacles: Rect[], clearance: number): boolean {
  for (const raw of obstacles) {
    const rect = inflate(raw, clearance);
    const minX = rect.x;
    const maxX = rect.x + rect.width;
    const minY = rect.y;
    const maxY = rect.y + rect.height;
    if (a.x === b.x) {
      const overlapY = Math.min(Math.max(a.y, b.y), maxY) - Math.max(Math.min(a.y, b.y), minY);
      if (a.x > minX && a.x < maxX && overlapY > 0) return true;
    } else if (a.y === b.y) {
      const overlapX = Math.min(Math.max(a.x, b.x), maxX) - Math.max(Math.min(a.x, b.x), minX);
      if (a.y > minY && a.y < maxY && overlapX > 0) return true;
    } else {
      // Non-axis-aligned segment: fall back to a coarse sample.
      const steps = 8;
      for (let i = 0; i <= steps; i += 1) {
        const x = a.x + ((b.x - a.x) * i) / steps;
        const y = a.y + ((b.y - a.y) * i) / steps;
        if (x > minX && x < maxX && y > minY && y < maxY) return true;
      }
    }
  }
  return false;
}

function pathIsClear(points: Point[], obstacles: Rect[], clearance: number): boolean {
  for (let i = 0; i < points.length - 1; i += 1) {
    if (segmentHits(points[i], points[i + 1], obstacles, clearance)) return false;
  }
  return true;
}

function unique(values: number[]): number[] {
  const seen = new Set<number>();
  const out: number[] = [];
  for (const value of values) {
    const rounded = Math.round(value);
    if (!seen.has(rounded)) {
      seen.add(rounded);
      out.push(value);
    }
  }
  return out;
}

/**
 * Builds an orthogonal waypoint list from `source` to `target`. Parallel edges
 * receive a `laneOffset` so relationships sharing a pair stay distinguishable.
 */
export function buildRoute(
  source: Point,
  target: Point,
  sourceSide: FlowSide,
  targetSide: FlowSide,
  obstacles: Rect[],
  laneOffset = 0,
  clearance = ROUTE_CLEARANCE,
): Point[] {
  const sDir = OUTWARD[sourceSide];
  const tDir = OUTWARD[targetSide];
  const sExit = { x: source.x + sDir.x * clearance, y: source.y + sDir.y * clearance };
  const tExit = { x: target.x + tDir.x * clearance, y: target.y + tDir.y * clearance };
  const sHorizontal = sourceSide === "left" || sourceSide === "right";
  const tHorizontal = targetSide === "left" || targetSide === "right";

  if (sHorizontal && tHorizontal) {
    const minY = Math.min(...obstacles.map((o) => o.y), source.y, target.y);
    const maxY = Math.max(...obstacles.map((o) => o.y + o.height), source.y, target.y);
    const lanes = unique([
      (source.y + target.y) / 2 + laneOffset,
      minY - clearance - Math.abs(laneOffset),
      maxY + clearance + Math.abs(laneOffset),
    ]);
    for (const lane of lanes) {
      const points = [
        source,
        { x: sExit.x, y: source.y },
        { x: sExit.x, y: lane },
        { x: tExit.x, y: lane },
        { x: tExit.x, y: target.y },
        target,
      ];
      if (pathIsClear(points, obstacles, clearance)) return points;
    }
    return [
      source,
      { x: sExit.x, y: source.y },
      { x: sExit.x, y: lanes[lanes.length - 1] },
      { x: tExit.x, y: lanes[lanes.length - 1] },
      { x: tExit.x, y: target.y },
      target,
    ];
  }

  if (!sHorizontal && !tHorizontal) {
    const minX = Math.min(...obstacles.map((o) => o.x), source.x, target.x);
    const maxX = Math.max(...obstacles.map((o) => o.x + o.width), source.x, target.x);
    const lanes = unique([
      (source.x + target.x) / 2 + laneOffset,
      minX - clearance - Math.abs(laneOffset),
      maxX + clearance + Math.abs(laneOffset),
    ]);
    for (const lane of lanes) {
      const points = [
        source,
        { x: source.x, y: sExit.y },
        { x: lane, y: sExit.y },
        { x: lane, y: tExit.y },
        { x: target.x, y: tExit.y },
        target,
      ];
      if (pathIsClear(points, obstacles, clearance)) return points;
    }
    return [
      source,
      { x: source.x, y: sExit.y },
      { x: lanes[lanes.length - 1], y: sExit.y },
      { x: lanes[lanes.length - 1], y: tExit.y },
      { x: target.x, y: tExit.y },
      target,
    ];
  }

  // Mixed orientation: a single corner joins the two exit directions.
  const corner = sHorizontal
    ? { x: sExit.x, y: tExit.y }
    : { x: tExit.x, y: sExit.y };
  const points = [
    source,
    sHorizontal ? { x: sExit.x, y: source.y } : { x: source.x, y: sExit.y },
    corner,
    sHorizontal ? { x: target.x, y: tExit.y } : { x: tExit.x, y: target.y },
    target,
  ];
  return points;
}

/** Renders an orthogonal waypoint list as an SVG path with rounded corners. */
export function roundedOrthogonalPath(points: Point[], radius = ROUTE_RADIUS): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x},${points[0].y}`;
  const parts: string[] = [`M ${points[0].x},${points[0].y}`];
  for (let i = 1; i < points.length - 1; i += 1) {
    const prev = points[i - 1];
    const corner = points[i];
    const next = points[i + 1];
    const inLength = Math.hypot(corner.x - prev.x, corner.y - prev.y);
    const outLength = Math.hypot(next.x - corner.x, next.y - corner.y);
    const r = Math.min(radius, inLength / 2, outLength / 2);
    const entry = {
      x: corner.x - Math.sign(corner.x - prev.x) * r,
      y: corner.y - Math.sign(corner.y - prev.y) * r,
    };
    const exit = {
      x: corner.x + Math.sign(next.x - corner.x) * r,
      y: corner.y + Math.sign(next.y - corner.y) * r,
    };
    parts.push(`L ${entry.x},${entry.y}`);
    parts.push(`Q ${corner.x},${corner.y} ${exit.x},${exit.y}`);
  }
  const last = points[points.length - 1];
  parts.push(`L ${last.x},${last.y}`);
  return parts.join(" ");
}

/** Picks a point near the middle of the longest segment for the edge label. */
export function labelPoint(points: Point[]): Point {
  if (points.length === 0) return { x: 0, y: 0 };
  if (points.length === 1) return points[0];
  let best = 0;
  let bestLength = -1;
  for (let i = 0; i < points.length - 1; i += 1) {
    const length = Math.hypot(
      points[i + 1].x - points[i].x,
      points[i + 1].y - points[i].y,
    );
    if (length > bestLength) {
      bestLength = length;
      best = i;
    }
  }
  return {
    x: (points[best].x + points[best + 1].x) / 2,
    y: (points[best].y + points[best + 1].y) / 2,
  };
}
