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
} from "../../components/architecture/architectureRouting";

export type ProjectionEdgeData = {
  relation: string;
  /** Dimmed while another connection on the canvas is being traced. */
  dimmed?: boolean;
  /** The connection the pointer is on: drawn heavier so it reads as the path. */
  emphasized?: boolean;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
  /** Corridor lane, so connectors sharing a corridor do not overlap. */
  laneShift?: number;
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
    data?.laneShift ?? 0,
  );
  const path = roundedOrthogonalPath(points);
  const relation = data?.relation ?? "";
  const anchor = labelAnchor(
    points,
    labelObstacles(data?.obstacles, data?.sourceRect, data?.targetRect),
    estimateLabelSize(relation, 9),
  );
  const color = RELATION_COLORS[relation] ?? "var(--discipline-information)";
  const emphasized = selected || data?.emphasized === true;
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: emphasized ? 2.2 : 1.4,
          opacity: data?.dimmed ? 0.12 : 1,
        }}
        interactionWidth={18}
      />
      {relation && (
        <EdgeLabelRenderer>
          <span
            className={`information-projection-edge-label${emphasized ? " chosen" : ""}${
              data?.dimmed ? " dimmed" : ""
            }`}
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
