import {
  BaseEdge,
  EdgeLabelRenderer,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

import {
  buildRoute,
  labelPoint,
  roundedOrthogonalPath,
  toFlowSide,
  type Rect,
} from "../components/architecture/architectureRouting";

export type SolutionEdgeData = {
  kind: string;
  label: string;
  sourceOffset?: { x: number; y: number };
  targetOffset?: { x: number; y: number };
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
  );
  const path = roundedOrthogonalPath(points);
  const anchor = labelPoint(points);
  const color = KIND_COLORS[data?.kind ?? ""] ?? "var(--color-border-strong)";
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.4 : 1.5,
          strokeDasharray: data?.kind === "external" || data?.kind === "relationship" ? "5 4" : undefined,
        }}
        interactionWidth={18}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={`solution-edge-label kind-${data.kind}${selected ? " selected" : ""}`}
            style={{ transform: `translate(-50%, -50%) translate(${anchor.x}px, ${anchor.y}px)` }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
