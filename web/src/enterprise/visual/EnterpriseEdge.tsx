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

export type EnterpriseEdgeData = {
  type: string;
  label: string;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
  /** Corridor lane, so connectors sharing a corridor do not overlap. */
  laneShift?: number;
  /** Staggered vertical offset applied to parallel-edge labels so they don't stack. */
  laneOffset?: number;
  /** Dimmed while another connection on the canvas is being traced. */
  dimmed?: boolean;
  /** The connection the pointer is on: drawn heavier so it reads as the path. */
  emphasized?: boolean;
};

export type EnterpriseFlowEdge = Edge<EnterpriseEdgeData, "enterpriseEdge">;

export default function EnterpriseEdge({
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
}: EdgeProps<EnterpriseFlowEdge>) {
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
  const anchor = labelAnchor(
    points,
    labelObstacles(data?.obstacles, data?.sourceRect, data?.targetRect),
    estimateLabelSize(data?.label ?? ""),
  );
  const color =
    data?.type === "supports" || data?.type === "satisfies"
      ? "var(--discipline-solution)"
      : "var(--discipline-enterprise)";
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: selected || data?.emphasized ? 2.2 : 1.4,
          opacity: data?.dimmed ? 0.14 : 1,
        }}
        interactionWidth={18}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={`enterprise-edge-label${selected || data?.emphasized ? " selected" : ""}${
              data?.dimmed ? " dimmed" : ""
            }`}
            style={{
              transform: `translate(-50%, -50%) translate(${anchor.x}px, ${
                anchor.y + (data?.laneOffset ?? 0)
              }px)`,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
