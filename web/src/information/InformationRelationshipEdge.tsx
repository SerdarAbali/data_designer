import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

import { cardinalityNotation, type InformationRelationship } from "./informationModel";

export type InformationRelationshipEdgeData = { relationship: InformationRelationship };
export type InformationRelationshipFlowEdge = Edge<
  InformationRelationshipEdgeData,
  "informationRelationship"
>;

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
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const relationship = data?.relationship;
  const notation = relationship ? cardinalityNotation(relationship.cardinality) : null;
  return (
    <>
      <BaseEdge
        id={relationship?.id ?? "edge"}
        path={edgePath}
        style={{ stroke: "var(--discipline-information, #6c5ce7)", strokeWidth: selected ? 2.2 : 1.4 }}
      />
      <EdgeLabelRenderer>
        <div
          className="information-edge-label"
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        >
          <span className="information-edge-end">{notation?.source}</span>
          <span className="information-edge-name">{relationship?.name || "\u2192"}</span>
          <span className="information-edge-end">{notation?.target}</span>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
