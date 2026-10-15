import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  Position,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

import { cardinalityNotation, type InformationRelationship } from "./informationModel";

export type InformationRelationshipEdgeData = {
  relationship: InformationRelationship;
  laneIndex?: number;
  laneCount?: number;
};

export type InformationRelationshipFlowEdge = Edge<
  InformationRelationshipEdgeData,
  "informationRelationship"
>;

const EDGE_COLOR = "var(--discipline-information, #368c86)";

/** Direction the connector leaves the entity box for a given handle side. */
function outward(position: Position): { x: number; y: number } {
  switch (position) {
    case Position.Left:
      return { x: -1, y: 0 };
    case Position.Top:
      return { x: 0, y: -1 };
    case Position.Bottom:
      return { x: 0, y: 1 };
    case Position.Right:
    default:
      return { x: 1, y: 0 };
  }
}

function crowFootRotation(position: Position): number {
  switch (position) {
    case Position.Left:
      return 180;
    case Position.Top:
      return 270;
    case Position.Bottom:
      return 90;
    case Position.Right:
    default:
      return 0;
  }
}

/**
 * A crow's-foot cardinality marker opened toward the connector, drawn with the
 * existing label-renderer so structural entity relationships stay arrow-free.
 */
function CrowFoot({ x, y, position }: { x: number; y: number; position: Position }) {
  return (
    <svg
      className="information-crowfoot"
      width="18"
      height="18"
      viewBox="0 0 18 18"
      aria-hidden="true"
      style={{
        transform: `translate(-50%, -50%) translate(${x}px, ${y}px) rotate(${crowFootRotation(position)}deg)`,
      }}
    >
      <line x1="2" y1="9" x2="15" y2="9" stroke={EDGE_COLOR} strokeWidth="1.4" />
      <line x1="2" y1="9" x2="15" y2="3.5" stroke={EDGE_COLOR} strokeWidth="1.4" />
      <line x1="2" y1="9" x2="15" y2="14.5" stroke={EDGE_COLOR} strokeWidth="1.4" />
    </svg>
  );
}

export default function InformationRelationshipEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  selected,
  data,
}: EdgeProps<InformationRelationshipFlowEdge>) {
  const laneCount = data?.laneCount ?? 1;
  const laneOffset = laneCount > 1
    ? ((data?.laneIndex ?? 0) - (laneCount - 1) / 2) * 18
    : 0;
  const horizontal =
    sourcePosition === Position.Left || sourcePosition === Position.Right;
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 16,
    offset: 20,
    centerX: horizontal ? undefined : (sourceX + targetX) / 2 + laneOffset,
    centerY: horizontal ? (sourceY + targetY) / 2 + laneOffset : undefined,
  });

  const relationship = data?.relationship;
  const notation = relationship
    ? cardinalityNotation(
        relationship.cardinality,
        relationship.source_optional,
        relationship.target_optional,
      )
    : null;

  const sourceDir = outward(sourcePosition);
  const targetDir = outward(targetPosition);

  return (
    <>
      <BaseEdge
        id={relationship?.id ?? "edge"}
        path={edgePath}
        style={{ stroke: EDGE_COLOR, strokeWidth: selected ? 2.2 : 1.4 }}
      />
      {relationship && notation && (
        <EdgeLabelRenderer>
          {notation.source.includes("*") && (
            <CrowFoot
              x={sourceX + sourceDir.x * 9}
              y={sourceY + sourceDir.y * 9}
              position={sourcePosition}
            />
          )}
          <div
            className="information-edge-endpoint"
            style={{
              transform: `translate(-50%, -50%) translate(${sourceX + sourceDir.x * 26}px, ${
                sourceY + sourceDir.y * 26
              }px)`,
            }}
          >
            {notation.source}
          </div>
          {notation.target.includes("*") && (
            <CrowFoot
              x={targetX + targetDir.x * 9}
              y={targetY + targetDir.y * 9}
              position={targetPosition}
            />
          )}
          <div
            className="information-edge-endpoint"
            style={{
              transform: `translate(-50%, -50%) translate(${targetX + targetDir.x * 26}px, ${
                targetY + targetDir.y * 26
              }px)`,
            }}
          >
            {notation.target}
          </div>
          <div
            className="information-edge-label"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            <span className="information-edge-name">
              {relationship.name || "relates to"}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
