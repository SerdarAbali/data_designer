import {
  BaseEdge,
  EdgeLabelRenderer,
  Position,
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
import { cardinalityNotation, type InformationRelationship } from "./informationModel";

export type InformationRelationshipEdgeData = {
  relationship: InformationRelationship;
  laneIndex?: number;
  laneCount?: number;
  /** Node rectangles the connector routes around (injected by the canvas shell). */
  obstacles?: Rect[];
  sourceRect?: Rect;
  targetRect?: Rect;
};

export type InformationRelationshipFlowEdge = Edge<
  InformationRelationshipEdgeData,
  "informationRelationship"
>;

const EDGE_COLOR = "var(--discipline-information, #368c86)";

/** Distance from the handle centre to a cardinality label, outside the border. */
const ENDPOINT_LABEL_OFFSET = 32;

/** Distance from the handle centre to a crow's-foot marker, outside the border. */
const CROWFOOT_OFFSET = 10;

/** Minimum clearance kept between the relationship name and an endpoint label. */
const MIN_LABEL_GAP = 34;

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
  const points = buildRoute(
    { x: sourceX, y: sourceY },
    { x: targetX, y: targetY },
    toFlowSide(sourcePosition),
    toFlowSide(targetPosition),
    data?.obstacles ?? [],
    laneOffset,
    undefined,
    { source: data?.sourceRect, target: data?.targetRect },
  );
  const edgePath = roundedOrthogonalPath(points);
  const anchor = labelPoint(points);
  let labelX = anchor.x;
  let labelY = anchor.y;

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

  // Cardinality labels sit a fixed offset outside the border, per handle side.
  const sourceLabel = {
    x: sourceX + sourceDir.x * ENDPOINT_LABEL_OFFSET,
    y: sourceY + sourceDir.y * ENDPOINT_LABEL_OFFSET,
  };
  const targetLabel = {
    x: targetX + targetDir.x * ENDPOINT_LABEL_OFFSET,
    y: targetY + targetDir.y * ENDPOINT_LABEL_OFFSET,
  };

  // Keep the relationship name clear of both endpoint cardinality labels.
  let nameX = labelX;
  let nameY = labelY;
  const tooClose = (a: { x: number; y: number }, b: { x: number; y: number }) =>
    Math.hypot(a.x - b.x, a.y - b.y) < MIN_LABEL_GAP;
  if (tooClose({ x: nameX, y: nameY }, sourceLabel) || tooClose({ x: nameX, y: nameY }, targetLabel)) {
    nameX = (sourceLabel.x + targetLabel.x) / 2;
    nameY = (sourceLabel.y + targetLabel.y) / 2;
  }

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
              x={sourceX + sourceDir.x * CROWFOOT_OFFSET}
              y={sourceY + sourceDir.y * CROWFOOT_OFFSET}
              position={sourcePosition}
            />
          )}
          <div
            className="information-edge-endpoint"
            style={{
              transform: `translate(-50%, -50%) translate(${sourceLabel.x}px, ${sourceLabel.y}px)`,
            }}
          >
            {notation.source}
          </div>
          {notation.target.includes("*") && (
            <CrowFoot
              x={targetX + targetDir.x * CROWFOOT_OFFSET}
              y={targetY + targetDir.y * CROWFOOT_OFFSET}
              position={targetPosition}
            />
          )}
          <div
            className="information-edge-endpoint"
            style={{
              transform: `translate(-50%, -50%) translate(${targetLabel.x}px, ${targetLabel.y}px)`,
            }}
          >
            {notation.target}
          </div>
          <div
            className="information-edge-label"
            style={{ transform: `translate(-50%, -50%) translate(${nameX}px, ${nameY}px)` }}
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
