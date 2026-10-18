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
 * The endpoint node boxes of an edge. When supplied, the connector's long run
 * is kept clear of the source and target boxes as well as the other nodes, so
 * an edge whose handles face *away* from one another (a required port on the
 * left meeting a provided port on the right) loops around its endpoints
 * instead of disappearing behind them.
 */
export type EndpointBounds = { source?: Rect; target?: Rect };

/**
 * Checks that no segment of a route crosses a blocker. The first and last
 * segments are the short stubs that leave/enter a handle, so they are only
 * checked against the *other* nodes — they legitimately touch their own box.
 */
function routeIsClear(
  points: Point[],
  obstacles: Rect[],
  blockers: Rect[],
  clearance: number,
): boolean {
  const lastSegment = points.length - 2;
  for (let i = 0; i <= lastSegment; i += 1) {
    const isStub = i === 0 || i === lastSegment;
    if (segmentHits(points[i], points[i + 1], isStub ? obstacles : blockers, clearance)) {
      return false;
    }
  }
  return true;
}

/**
 * Builds an orthogonal waypoint list from `source` to `target`. Parallel edges
 * receive a `laneOffset` so relationships sharing a pair stay distinguishable,
 * and `laneShift` moves the connector's bend inside its corridor so connectors
 * that share a corridor (but not a handle) stop stacking on the same line.
 */
export function buildRoute(
  source: Point,
  target: Point,
  sourceSide: FlowSide,
  targetSide: FlowSide,
  obstacles: Rect[],
  laneOffset = 0,
  clearance = ROUTE_CLEARANCE,
  endpointBounds?: EndpointBounds,
  laneShift = 0,
): Point[] {
  const sDir = OUTWARD[sourceSide];
  const tDir = OUTWARD[targetSide];
  const sExit = { x: source.x + sDir.x * clearance, y: source.y + sDir.y * clearance };
  const tExit = { x: target.x + tDir.x * clearance, y: target.y + tDir.y * clearance };
  const sHorizontal = sourceSide === "left" || sourceSide === "right";
  const tHorizontal = targetSide === "left" || targetSide === "right";
  const offset = Math.abs(laneOffset);

  const blockers: Rect[] = endpointBounds
    ? [
        ...obstacles,
        ...(endpointBounds.source ? [endpointBounds.source] : []),
        ...(endpointBounds.target ? [endpointBounds.target] : []),
      ]
    : obstacles;

  if (sHorizontal && tHorizontal) {
    const sourceRect = endpointBounds?.source;
    const targetRect = endpointBounds?.target;
    // The bend may be pushed into the corridor so two connectors sharing it do
    // not draw their jogs on top of each other. Clamped inside the corridor so
    // the run can never reverse.
    const span = tExit.x - sExit.x;
    const limit = Math.max(0, span / 2 - clearance);
    const shift = Math.max(-limit, Math.min(laneShift, limit));
    const sJog = sExit.x + shift;
    const tJog = tExit.x - shift;
    // Preferred shape: a single bend at the midpoint. The lane variants below
    // bend twice, so when the two handles sit at almost the same height their
    // two opposing micro-steps read as a wavy connector. One bend keeps the
    // same handles and stays clear of the same boxes.
    const midX = (sExit.x + tExit.x) / 2 + shift;
    if (tJog > sJog) {
      const stepPoints: Point[] = [
        source,
        { x: sExit.x, y: source.y },
        { x: midX, y: source.y },
        { x: midX, y: target.y },
        { x: tExit.x, y: target.y },
        target,
      ];
      if (routeIsClear(stepPoints, obstacles, blockers, clearance)) return stepPoints;
    }
    const laneCandidates = [
      (source.y + target.y) / 2 + laneOffset,
      Math.min(source.y, target.y) - clearance - offset,
      Math.max(source.y, target.y) + clearance + offset,
      sourceRect ? sourceRect.y - clearance - offset : source.y - clearance - offset,
      sourceRect
        ? sourceRect.y + sourceRect.height + clearance + offset
        : source.y + clearance + offset,
      targetRect ? targetRect.y - clearance - offset : target.y - clearance - offset,
      targetRect
        ? targetRect.y + targetRect.height + clearance + offset
        : target.y + clearance + offset,
      Math.min(...obstacles.map((o) => o.y), source.y, target.y) - clearance - offset,
      Math.max(...obstacles.map((o) => o.y + o.height), source.y, target.y) +
        clearance +
        offset,
    ];
    const lanes = unique(laneCandidates);
    const build = (lane: number): Point[] => [
      source,
      { x: sJog, y: source.y },
      { x: sJog, y: lane },
      { x: tJog, y: lane },
      { x: tJog, y: target.y },
      target,
    ];
    for (const lane of lanes) {
      const points = build(lane);
      if (routeIsClear(points, obstacles, blockers, clearance)) return points;
    }
    return build(lanes[lanes.length - 1]);
  }

  if (!sHorizontal && !tHorizontal) {
    const sourceRect = endpointBounds?.source;
    const targetRect = endpointBounds?.target;
    const span = tExit.y - sExit.y;
    const limit = Math.max(0, span / 2 - clearance);
    const shift = Math.max(-limit, Math.min(laneShift, limit));
    const sJog = sExit.y + shift;
    const tJog = tExit.y - shift;
    // Mirrors the horizontal case: one bend instead of two.
    const midY = (sExit.y + tExit.y) / 2 + shift;
    if (tJog > sJog) {
      const stepPoints: Point[] = [
        source,
        { x: source.x, y: sExit.y },
        { x: source.x, y: midY },
        { x: target.x, y: midY },
        { x: target.x, y: tExit.y },
        target,
      ];
      if (routeIsClear(stepPoints, obstacles, blockers, clearance)) return stepPoints;
    }
    const laneCandidates = [
      (source.x + target.x) / 2 + laneOffset,
      Math.min(source.x, target.x) - clearance - offset,
      Math.max(source.x, target.x) + clearance + offset,
      sourceRect ? sourceRect.x - clearance - offset : source.x - clearance - offset,
      sourceRect
        ? sourceRect.x + sourceRect.width + clearance + offset
        : source.x + clearance + offset,
      targetRect ? targetRect.x - clearance - offset : target.x - clearance - offset,
      targetRect
        ? targetRect.x + targetRect.width + clearance + offset
        : target.x + clearance + offset,
      Math.min(...obstacles.map((o) => o.x), source.x, target.x) - clearance - offset,
      Math.max(...obstacles.map((o) => o.x + o.width), source.x, target.x) +
        clearance +
        offset,
    ];
    const lanes = unique(laneCandidates);
    const build = (lane: number): Point[] => [
      source,
      { x: source.x, y: sExit.y },
      { x: lane, y: sJog },
      { x: lane, y: tJog },
      { x: target.x, y: tExit.y },
      target,
    ];
    for (const lane of lanes) {
      const points = build(lane);
      if (routeIsClear(points, obstacles, blockers, clearance)) return points;
    }
    return build(lanes[lanes.length - 1]);
  }

  // Mixed orientation: a corner joins the two exit directions. Try both corner
  // placements and keep the one that clears the surrounding boxes.
  const first = sHorizontal
    ? { x: sExit.x, y: tExit.y }
    : { x: tExit.x, y: sExit.y };
  const second = sHorizontal
    ? { x: tExit.x, y: source.y }
    : { x: sExit.x, y: target.y };
  const sExitPoint = sHorizontal
    ? { x: sExit.x, y: source.y }
    : { x: source.x, y: sExit.y };
  const tExitPoint = sHorizontal
    ? { x: target.x, y: tExit.y }
    : { x: tExit.x, y: target.y };
  for (const corner of [first, second]) {
    const points = [source, sExitPoint, corner, tExitPoint, target];
    if (routeIsClear(points, obstacles, blockers, clearance)) return points;
  }
  return [source, sExitPoint, first, tExitPoint, target];
}

/**
 * Drops duplicate points and collinear midpoints so a straight run renders as a
 * single segment instead of a chain of degenerate corners.
 */
export function simplifyPoints(points: Point[]): Point[] {
  const deduped: Point[] = [];
  for (const point of points) {
    const last = deduped[deduped.length - 1];
    if (last && Math.abs(last.x - point.x) < 0.5 && Math.abs(last.y - point.y) < 0.5) continue;
    deduped.push(point);
  }
  const out: Point[] = [];
  for (let i = 0; i < deduped.length; i += 1) {
    if (i > 0 && i < deduped.length - 1) {
      const a = deduped[i - 1];
      const b = deduped[i];
      const c = deduped[i + 1];
      const cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
      if (Math.abs(cross) < 0.5) continue;
    }
    out.push(deduped[i]);
  }
  return out;
}

/** Renders an orthogonal waypoint list as an SVG path with rounded corners. */
export function roundedOrthogonalPath(points: Point[], radius = ROUTE_RADIUS): string {
  const path = simplifyPoints(points);
  if (path.length === 0) return "";
  if (path.length === 1) return `M ${path[0].x},${path[0].y}`;
  const parts: string[] = [`M ${path[0].x},${path[0].y}`];
  for (let i = 1; i < path.length - 1; i += 1) {
    const prev = path[i - 1];
    const corner = path[i];
    const next = path[i + 1];
    const inLength = Math.hypot(corner.x - prev.x, corner.y - prev.y);
    const outLength = Math.hypot(next.x - corner.x, next.y - corner.y);
    const r = Math.min(radius, inLength / 2, outLength / 2);
    // Step along the real segment directions. Using the sign of each axis
    // instead would push the curve ends diagonally whenever a segment is only
    // *nearly* axis-aligned — which happens as soon as a sub-pixel handle
    // offset survives de-duplication — and that draws a rounded bulge where the
    // connector should simply run straight.
    const entry = inLength > 0
      ? {
        x: corner.x - ((corner.x - prev.x) / inLength) * r,
        y: corner.y - ((corner.y - prev.y) / inLength) * r,
      }
      : corner;
    const exit = outLength > 0
      ? {
        x: corner.x + ((next.x - corner.x) / outLength) * r,
        y: corner.y + ((next.y - corner.y) / outLength) * r,
      }
      : corner;
    parts.push(`L ${entry.x},${entry.y}`);
    parts.push(`Q ${corner.x},${corner.y} ${exit.x},${exit.y}`);
  }
  const last = path[path.length - 1];
  parts.push(`L ${last.x},${last.y}`);
  return parts.join(" ");
}

/** Picks a point near the middle of the longest segment for the edge label. */
export function labelPoint(points: Point[]): Point {
  const path = simplifyPoints(points);
  if (path.length === 0) return { x: 0, y: 0 };
  if (path.length === 1) return path[0];
  let best = 0;
  let bestLength = -1;
  for (let i = 0; i < path.length - 1; i += 1) {
    const length = Math.hypot(
      path[i + 1].x - path[i].x,
      path[i + 1].y - path[i].y,
    );
    if (length > bestLength) {
      bestLength = length;
      best = i;
    }
  }
  return {
    x: (path[best].x + path[best + 1].x) / 2,
    y: (path[best].y + path[best + 1].y) / 2,
  };
}

/** Clearance kept between an edge label box and every node rectangle. */
export const LABEL_CLEARANCE = 8;

/**
 * The rectangles a label must stay clear of: the other nodes plus the edge's own
 * endpoint boxes (a label on a handle would sit on top of its own node).
 */
export function labelObstacles(
  obstacles: Rect[] = [],
  sourceRect?: Rect,
  targetRect?: Rect,
): Rect[] {
  return [
    ...obstacles,
    ...(sourceRect ? [sourceRect] : []),
    ...(targetRect ? [targetRect] : []),
  ];
}

/** Rough rendered size of an edge label, used to keep labels off the nodes. */
export function estimateLabelSize(
  text: string,
  fontSize = 10,
): { width: number; height: number } {
  return {
    width: Math.max(28, text.length * fontSize * 0.56 + 16),
    height: fontSize + 8,
  };
}

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

/**
 * Places an edge label on the routed polyline. The longest segment's midpoint is
 * preferred, but the anchor slides along the path whenever that point would put
 * the label behind a node. Deterministic: candidates are walked longest-segment
 * first, then midpoint before the two shoulder positions.
 */
export function labelAnchor(
  points: Point[],
  obstacles: Rect[] = [],
  size: { width: number; height: number } = { width: 0, height: 0 },
  clearance = LABEL_CLEARANCE,
): Point {
  const path = simplifyPoints(points);
  if (path.length === 0) return { x: 0, y: 0 };
  if (path.length === 1) return path[0];
  const candidates: { point: Point; length: number }[] = [];
  for (let i = 0; i < path.length - 1; i += 1) {
    const length = Math.hypot(path[i + 1].x - path[i].x, path[i + 1].y - path[i].y);
    if (length <= 0) continue;
    for (const ratio of [0.5, 0.35, 0.65]) {
      candidates.push({
        point: {
          x: path[i].x + (path[i + 1].x - path[i].x) * ratio,
          y: path[i].y + (path[i + 1].y - path[i].y) * ratio,
        },
        length,
      });
    }
  }
  candidates.sort((a, b) => b.length - a.length);
  const fallback = candidates[0]?.point ?? labelPoint(points);
  if (obstacles.length === 0 || size.width <= 0) return fallback;
  for (const candidate of candidates) {
    const box: Rect = {
      x: candidate.point.x - size.width / 2 - clearance,
      y: candidate.point.y - size.height / 2 - clearance,
      width: size.width + clearance * 2,
      height: size.height + clearance * 2,
    };
    if (!obstacles.some((rect) => rectsOverlap(box, rect))) return candidate.point;
  }
  return fallback;
}

/** A flow-node's position and measured/declared size, for obstacle routing. */
export type RectLikeNode = {
  id: string;
  position: { x: number; y: number };
  width?: number | null;
  height?: number | null;
  measured?: { width?: number; height?: number };
  style?: { width?: number | string; height?: number | string };
};

/** Fallbacks used before React Flow has measured a node. */
export const DEFAULT_EDGE_NODE_WIDTH = 220;
export const DEFAULT_EDGE_NODE_HEIGHT = 120;

/** Maps a React Flow handle position to a routing side. */
export function toFlowSide(position: string | undefined): FlowSide {
  return position === "left" || position === "top" || position === "bottom" ? position : "right";
}

function rectForNode(
  node: RectLikeNode,
  fallbackWidth: number,
  fallbackHeight: number,
): Rect {
  const styleWidth = typeof node.style?.width === "number" ? node.style.width : undefined;
  const styleHeight = typeof node.style?.height === "number" ? node.style.height : undefined;
  return {
    x: node.position.x,
    y: node.position.y,
    width: node.measured?.width ?? node.width ?? styleWidth ?? fallbackWidth,
    height: node.measured?.height ?? node.height ?? styleHeight ?? fallbackHeight,
  };
}

/** Rectangles for every node, keyed by node id, for obstacle-aware routing. */
export function nodeRectMap(
  nodes: RectLikeNode[],
  fallbackWidth = DEFAULT_EDGE_NODE_WIDTH,
  fallbackHeight = DEFAULT_EDGE_NODE_HEIGHT,
): Map<string, Rect> {
  const map = new Map<string, Rect>();
  for (const node of nodes) {
    map.set(node.id, rectForNode(node, fallbackWidth, fallbackHeight));
  }
  return map;
}

function rectContains(outer: Rect, inner: Rect): boolean {
  return (
    outer.x <= inner.x &&
    outer.y <= inner.y &&
    outer.x + outer.width >= inner.x + inner.width &&
    outer.y + outer.height >= inner.y + inner.height
  );
}

/**
 * Obstacle rectangles for one edge: every node except its own endpoints, minus
 * container nodes (boundaries and panels) that fully enclose both endpoints —
 * otherwise a solution boundary would be treated as an obstacle and every
 * connector would route around the whole canvas.
 */
export function obstaclesForEdge(
  rects: Map<string, Rect>,
  sourceId: string | null | undefined,
  targetId: string | null | undefined,
): Rect[] {
  const source = sourceId ? rects.get(sourceId) : undefined;
  const target = targetId ? rects.get(targetId) : undefined;
  const obstacles: Rect[] = [];
  for (const [id, rect] of rects) {
    if (id === sourceId || id === targetId) continue;
    if (source && target && rectContains(rect, source) && rectContains(rect, target)) continue;
    obstacles.push(rect);
  }
  return obstacles;
}
