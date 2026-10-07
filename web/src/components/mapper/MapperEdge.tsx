import React from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  Position,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

type MapperEdgeData = {
  direction?: "outbound" | "inbound";
  routeOffset?: number;
  straightWhenAligned?: boolean;
  phase?: "request" | "success-response" | "error-response" | "async-response";
  sampleRows?: number;
  status?: "draft" | "attention" | "healthy";
  validationStatus?: "Valid" | "Warning" | "Error" | "Unmapped";
  validationIssue?: string;
  onIssueHover?: (active: boolean) => void;
  onIssueSelect?: () => void;
};

type MapperEdgeType = Edge<MapperEdgeData>;

const OUTBOUND_COLOR = "#2563eb";
const INBOUND_COLOR = "#10b981";
const ERROR_RESPONSE_COLOR = "#b84c4c";

export function mapperEdgePath(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  sourcePosition: Position = Position.Right,
  targetPosition: Position = Position.Left,
  offset = 12,
  straightWhenAligned = false,
): [string, number, number] {
  if (straightWhenAligned && Math.abs(sourceY - targetY) <= 2) {
    return [`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`, (sourceX + targetX) / 2, sourceY];
  }
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
    offset: Math.max(12, offset),
  });
  return [path, labelX, labelY];
}

export function edgeAnimationClassName(): string {
  return "mapper-edge-animated mapper-edge-outbound";
}

export default function MapperEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  markerEnd,
  markerStart,
  style,
  label,
  selected,
  sourcePosition,
  targetPosition,
}: EdgeProps<MapperEdgeType>) {
  const edgePhase = data?.phase ?? "request";
  const isResponsePhase = edgePhase !== "request";
  const isErrorResponse = edgePhase === "error-response";
  const [path, labelX, labelY] = mapperEdgePath(
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition ?? Position.Right,
    targetPosition ?? Position.Left,
    data?.routeOffset ?? 12,
    data?.straightWhenAligned,
  );

  const edgeColor = isErrorResponse
    ? ERROR_RESPONSE_COLOR
    : isResponsePhase
      ? INBOUND_COLOR
      : OUTBOUND_COLOR;

  const edgeStyle: React.CSSProperties = {
    ...style,
    stroke: edgeColor,
    strokeWidth: selected ? 2.5 : 2,
    strokeDasharray: "5 5",
    filter: selected ? "drop-shadow(0 0 4px rgba(0,0,0,0.2))" : "none",
  };
  const validationStatus = data?.validationStatus;
  const showValidationIssue = validationStatus === "Warning" || validationStatus === "Error";
  const validationLabel = validationStatus === "Error" ? "Issue" : "Warning";

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        markerStart={markerStart}
        style={edgeStyle}
        className={edgeAnimationClassName()}
        interactionWidth={24}
      />

      {label && (
        <EdgeLabelRenderer>
          <div
            className={`mapper-edge-label${selected ? " selected" : ""}`}
            style={{
              position: "absolute",
              left: labelX,
              top: labelY,
              transform: "translate(-50%, -50%)",
              pointerEvents: "none",
              background: "white",
              padding: "2px 6px",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: "500",
              color: edgeColor,
              border: `1px solid ${edgeColor}`,
              opacity: 0.9,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
      {showValidationIssue && (
        <EdgeLabelRenderer>
          <button
            type="button"
            className={`mapper-edge-issue mapper-edge-issue-${validationStatus === "Error" ? "error" : "warning"}`}
            style={{
              position: "absolute",
              left: labelX,
              top: labelY - 28,
              transform: "translate(-50%, -50%)",
              zIndex: 20,
              pointerEvents: "all",
            }}
            aria-label={`${validationLabel}: ${data?.validationIssue ?? ""}`}
            title={data?.validationIssue ?? validationLabel}
            onMouseDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
            onMouseEnter={() => data?.onIssueHover?.(true)}
            onMouseLeave={() => data?.onIssueHover?.(false)}
            onFocus={() => data?.onIssueHover?.(true)}
            onBlur={() => data?.onIssueHover?.(false)}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              data?.onIssueSelect?.();
            }}
          >
            <span aria-hidden="true">{validationStatus === "Error" ? "⨯" : "!"}</span>
            {validationLabel}
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
