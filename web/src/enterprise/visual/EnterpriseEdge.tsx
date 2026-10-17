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

export type EnterpriseEdgeData = {
  type: string;
  label: string;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
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
  );
  const path = roundedOrthogonalPath(points);
  const anchor = labelPoint(points);
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
        style={{ stroke: color, strokeWidth: selected ? 2.2 : 1.4 }}
        interactionWidth={18}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={`enterprise-edge-label${selected ? " selected" : ""}`}
            style={{ transform: `translate(-50%, -50%) translate(${anchor.x}px, ${anchor.y}px)` }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
