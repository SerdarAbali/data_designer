import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

export type ProjectionEdgeData = {
  relation: string;
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
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
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
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {relation}
          </span>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
