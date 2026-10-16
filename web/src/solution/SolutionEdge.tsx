import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

export type SolutionEdgeData = {
  kind: string;
  label: string;
};

export type SolutionFlowEdge = Edge<SolutionEdgeData, "solutionEdge">;

const KIND_COLORS: Record<string, string> = {
  member: "var(--discipline-solution)",
  external: "var(--color-muted)",
  relationship: "var(--color-muted)",
  connects_to: "var(--color-accent)",
  uses: "var(--discipline-information)",
};

export default function SolutionEdge({
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
}: EdgeProps<SolutionFlowEdge>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const color = KIND_COLORS[data?.kind ?? ""] ?? "var(--color-border-strong)";
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.4 : 1.5,
          strokeDasharray: data?.kind === "external" || data?.kind === "relationship" ? "5 4" : undefined,
        }}
        interactionWidth={18}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={`solution-edge-label kind-${data.kind}${selected ? " selected" : ""}`}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
