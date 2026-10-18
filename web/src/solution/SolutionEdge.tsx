import {
  BaseEdge,
  EdgeLabelRenderer,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

import {
  buildRoute,
  estimateLabelSize,
  labelAnchor,
  labelObstacles,
  roundedOrthogonalPath,
  toFlowSide,
  type Rect,
} from "../components/architecture/architectureRouting";

export type SolutionEdgeData = {
  kind: string;
  label: string;
  sourceOffset?: { x: number; y: number };
  targetOffset?: { x: number; y: number };
  /** Dimmed while another connection on the canvas is being traced. */
  dimmed?: boolean;
  /** The connection the pointer is on: drawn heavier so it reads as the path. */
  emphasized?: boolean;
  /** Corridor lane, so connectors sharing a corridor do not overlap. */
  laneShift?: number;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
};

export type SolutionFlowEdge = Edge<SolutionEdgeData, "solutionEdge">;

const KIND_COLORS: Record<string, string> = {
  member: "var(--discipline-solution)",
  external: "var(--color-muted)",
  relationship: "var(--color-muted)",
  connects_to: "var(--color-accent)",
  uses: "var(--discipline-information)",
};

export default function SolutionEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
  data,
}: EdgeProps<SolutionFlowEdge>) {
  const sourceOffset = data?.sourceOffset ?? { x: 0, y: 0 };
  const targetOffset = data?.targetOffset ?? { x: 0, y: 0 };
  const points = buildRoute(
    { x: sourceX + sourceOffset.x, y: sourceY + sourceOffset.y },
    { x: targetX + targetOffset.x, y: targetY + targetOffset.y },
    toFlowSide(sourcePosition),
    toFlowSide(targetPosition),
    data?.obstacles ?? [],
    0,
    undefined,
    { source: data?.sourceRect, target: data?.targetRect },
    data?.laneShift ?? 0,
  );
  const path = roundedOrthogonalPath(points);
  const label = data?.label ?? "";
  const anchor = labelAnchor(
    points,
    labelObstacles(data?.obstacles, data?.sourceRect, data?.targetRect),
    estimateLabelSize(label),
  );
  const color = KIND_COLORS[data?.kind ?? ""] ?? "var(--color-border-strong)";
  const emphasized = selected || data?.emphasized === true;
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: emphasized ? 2.4 : 1.5,
          strokeDasharray: data?.kind === "external" || data?.kind === "relationship" ? "5 4" : undefined,
          opacity: data?.dimmed ? 0.14 : 1,
        }}
        interactionWidth={18}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={`solution-edge-label kind-${data.kind}${emphasized ? " selected" : ""}${
              data?.dimmed ? " dimmed" : ""
            }`}
            style={{ transform: `translate(-50%, -50%) translate(${anchor.x}px, ${anchor.y}px)` }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
