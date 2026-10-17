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
} from "../../components/architecture/architectureRouting";

export type ProjectionEdgeData = {
  relation: string;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
};

export type ProjectionFlowEdge = Edge<ProjectionEdgeData, "informationProjectionEdge">;

const RELATION_COLORS: Record<string, string> = {
  "realized as": "var(--discipline-information)",
  "mapped by": "var(--discipline-integration)",
  "transformed by": "var(--discipline-integration)",
  "delivered to": "var(--discipline-solution)",
  "sourced from": "var(--color-muted)",
  "has attribute": "var(--color-border-strong)",
};

export default function ProjectionEdge({
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
}: EdgeProps<ProjectionFlowEdge>) {
  const points = buildRoute(
    { x: sourceX, y: sourceY },
    { x: targetX, y: targetY },
    toFlowSide(sourcePosition),
    toFlowSide(targetPosition),
    data?.obstacles ?? [],
    0,
    undefined,
    { source: data?.sourceRect, target: data?.targetRect },
  );
  const path = roundedOrthogonalPath(points);
  const anchor = labelPoint(points);
  const relation = data?.relation ?? "";
  const color = RELATION_COLORS[relation] ?? "var(--discipline-information)";
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{ stroke: color, strokeWidth: selected ? 2.2 : 1.4 }}
        interactionWidth={18}
      />
      {relation && (
        <EdgeLabelRenderer>
          <span
            className="information-projection-edge-label"
            data-relation={relation}
            style={{ transform: `translate(-50%, -50%) translate(${anchor.x}px, ${anchor.y}px)` }}
          >
            {relation}
          </span>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
