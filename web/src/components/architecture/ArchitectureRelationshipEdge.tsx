import {
  BaseEdge,
  EdgeLabelRenderer,
  Position,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

import type { ResolvedRelationship } from "../../architectureCanvasModel";
import {
  buildRoute,
  labelPoint,
  roundedOrthogonalPath,
  type FlowSide,
  type Rect,
} from "./architectureRouting";

export type ArchitectureRelationshipEdgeData = {
  relationship: ResolvedRelationship;
  obstacles: Rect[];
  laneIndex: number;
  laneCount: number;
  sourceId: string;
  targetId: string;
  dimmed?: boolean;
};

export type ArchitectureRelationshipFlowEdge = Edge<
  ArchitectureRelationshipEdgeData,
  "architectureRelationship"
>;

function toSide(position: Position): FlowSide {
  switch (position) {
    case Position.Top:
      return "top";
    case Position.Bottom:
      return "bottom";
    case Position.Left:
      return "left";
    case Position.Right:
    default:
      return "right";
  }
}

export default function ArchitectureRelationshipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  label,
  selected,
  data,
}: EdgeProps<ArchitectureRelationshipFlowEdge>) {
  const laneCount = data?.laneCount ?? 1;
  const laneOffset = laneCount > 1
    ? ((data?.laneIndex ?? 0) - (laneCount - 1) / 2) * 18
    : 0;
  const obstacles = data?.obstacles ?? [];

  const points = buildRoute(
    { x: sourceX, y: sourceY },
    { x: targetX, y: targetY },
    toSide(sourcePosition),
    toSide(targetPosition),
    obstacles,
    laneOffset,
  );
  const path = roundedOrthogonalPath(points);
  const anchor = labelPoint(points);

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={style}
        interactionWidth={20}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            className={`architecture-edge-label${selected ? " selected" : ""}`}
            style={{
              transform: `translate(-50%, -50%) translate(${anchor.x}px, ${anchor.y}px)`,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
