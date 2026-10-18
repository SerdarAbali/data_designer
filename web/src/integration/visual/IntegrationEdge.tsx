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

export type IntegrationEdgeData = {
  relation: string;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
  /** Corridor lane, so connectors sharing a corridor do not overlap. */
  laneShift?: number;
};

export type IntegrationFlowEdge = Edge<IntegrationEdgeData, "integrationEdge">;

const RELATION_COLORS: Record<string, string> = {
  provides: "var(--discipline-integration)",
  requires: "var(--discipline-solution)",
  invokes: "var(--discipline-integration)",
  publishes: "var(--color-warning, #b0703a)",
  "sends file": "var(--color-warning, #b0703a)",
  delivers: "var(--discipline-integration)",
  consumes: "var(--discipline-solution)",
  produces: "var(--discipline-integration)",
  "mediated by": "var(--color-warning, #b0703a)",
  exposes: "var(--discipline-solution)",
};

export default function IntegrationEdge({
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
}: EdgeProps<IntegrationFlowEdge>) {
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
  const color = RELATION_COLORS[relation] ?? "var(--discipline-integration)";
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
            className="integration-projection-edge-label"
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
