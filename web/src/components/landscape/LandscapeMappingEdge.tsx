import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  Position,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

type MappingEdge = Edge<{
  integrationId: string;
  contractIds?: string[];
  laneIndex?: number;
  laneCount?: number;
  obstacles?: { systemId: string; x: number; y: number; width: number; height: number }[];
  sourceSystemId?: string;
  targetSystemId?: string;
  dimmed?: boolean;
  sampleRows: number;
  status: "draft" | "attention" | "healthy" | "valid" | "warnings" | "errors" | "incomplete";
  sourceFieldId?: string;
  targetFieldId?: string;
  transformations?: string[];
}>;

export default function LandscapeMappingEdge({
  id,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  sourceHandleId,
  targetHandleId,
  data,
  markerEnd,
  markerStart,
  style,
  label,
  selected,
}: EdgeProps<MappingEdge>) {
  const pathOptions = {
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  };
  const isParallelContractEdge = (data?.laneCount ?? 0) > 1;
  const laneOffset = isParallelContractEdge
    ? ((data?.laneIndex ?? 0) - ((data?.laneCount ?? 1) - 1) / 2) * 34
    : 0;
  const isFieldToCollapsedSystem =
    sourceHandleId?.startsWith("out:") && targetHandleId === "system-in";
  const [defaultPath, defaultLabelX, defaultLabelY] = getSmoothStepPath({
    ...pathOptions,
    borderRadius: 16,
    offset: 18,
  });
  const minX = Math.min(sourceX, targetX);
  const maxX = Math.max(sourceX, targetX);
  const minY = Math.min(sourceY, targetY);
  const maxY = Math.max(sourceY, targetY);
  const reverseAcrossPair = sourcePosition === Position.Right
    && targetPosition === Position.Left
    && sourceX >= targetX;
  const blocked = reverseAcrossPair || (data?.obstacles ?? []).some((obstacle) =>
    obstacle.systemId !== data?.sourceSystemId
    && obstacle.systemId !== data?.targetSystemId
    && obstacle.x < maxX
    && obstacle.x + obstacle.width > minX
    && obstacle.y < maxY + 12
    && obstacle.y + obstacle.height > minY - 12);
  const routeTop = Math.min(...(data?.obstacles ?? []).map((item) => item.y), minY) - 50;
  const routeBottom = Math.max(...(data?.obstacles ?? []).map((item) => item.y + item.height), maxY) + 50;
  const routeY = Math.abs((sourceY + targetY) / 2 - routeTop)
    <= Math.abs(routeBottom - (sourceY + targetY) / 2)
    ? routeTop - Math.abs(laneOffset)
    : routeBottom + Math.abs(laneOffset);
  const sourceExitX = sourceX + (sourcePosition === Position.Left ? -28 : 28);
  const targetEntryX = targetX + (targetPosition === Position.Left ? -28 : 28);
  const routedPath = `M ${sourceX},${sourceY} L ${sourceExitX},${sourceY} L ${sourceExitX},${routeY} L ${targetEntryX},${routeY} L ${targetEntryX},${targetY} L ${targetX},${targetY}`;
  const path = blocked
    ? routedPath
    : isParallelContractEdge
    ? `M ${sourceX},${sourceY} C ${sourceX + (targetX - sourceX) * 0.34},${sourceY + laneOffset} ${targetX - (targetX - sourceX) * 0.34},${targetY + laneOffset} ${targetX},${targetY}`
    : defaultPath;
  const labelX = (sourceX + targetX) / 2;
  const labelY = blocked ? routeY : (sourceY + targetY) / 2 + laneOffset;
  const labelPosition = blocked || isParallelContractEdge
    ? { x: labelX, y: labelY }
    : { x: defaultLabelX, y: defaultLabelY };

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        markerStart={markerStart}
        style={style}
        interactionWidth={24}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            className={`landscape-edge-label${selected ? " selected" : ""}`}
            style={{
              position: "absolute",
              left: isFieldToCollapsedSystem && !blocked ? defaultLabelX : labelPosition.x,
              top: isFieldToCollapsedSystem && !blocked ? defaultLabelY : labelPosition.y,
              transform: "translate(-50%, -50%)",
              pointerEvents: "none",
              opacity: data?.dimmed ? 0.14 : 1,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
