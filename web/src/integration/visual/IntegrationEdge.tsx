import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

export type IntegrationEdgeData = {
  relation: string;
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
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const relation = data?.relation ?? "";
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
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {relation}
          </span>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
