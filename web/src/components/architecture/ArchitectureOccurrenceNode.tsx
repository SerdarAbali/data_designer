import React from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { handleId, type FlowSide } from "./architectureRouting";

const SIDES: { side: FlowSide; position: Position }[] = [
  { side: "top", position: Position.Top },
  { side: "right", position: Position.Right },
  { side: "bottom", position: Position.Bottom },
  { side: "left", position: Position.Left },
];

export type ArchitectureOccurrenceNodeData = {
  occurrenceId: string;
  objectId: string;
  label: string;
  kind: string;
  icon: string;
  color: string;
  missing: boolean;
  overridden: boolean;
  editable: boolean;
  stateType: string;
  description?: string;
  onRemove?: (occurrenceId: string) => void;
};

export type ArchitectureOccurrenceNode = Node<ArchitectureOccurrenceNodeData, "occurrence" | "boundary">;

export default function ArchitectureOccurrenceNodeCard({
  data,
  selected,
}: NodeProps<ArchitectureOccurrenceNode>) {
  return (
    <article
      className={`architecture-node${selected ? " selected" : ""}${data.missing ? " missing" : ""}`}
      style={{ borderLeftColor: data.color }}
      aria-label={`${data.label}, ${data.kind || "System"}`}
      data-occurrence-id={data.occurrenceId}
      data-object-id={data.objectId}
    >
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`t-${side}`}
          id={handleId("target", side)}
          type="target"
          position={position}
          isConnectable={data.editable}
        />
      ))}
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`s-${side}`}
          id={handleId("source", side)}
          type="source"
          position={position}
          isConnectable={data.editable}
        />
      ))}
      <header>
        <span className="architecture-node-icon" style={{ color: data.color }} aria-hidden="true">
          {data.icon || data.label.slice(0, 1).toUpperCase()}
        </span>
        <span className="architecture-node-id" title={data.objectId}>{data.objectId.slice(0, 8)}</span>
        {data.missing && <span className="architecture-node-badge unresolved">Unresolved</span>}
        {data.overridden && <span className="architecture-node-badge overridden">Changed</span>}
        {selected && data.editable && data.onRemove && (
          <button
            type="button"
            className="architecture-node-remove nodrag nopan"
            aria-label={`Remove ${data.label} from this state`}
            title="Remove from this state (the canonical system is kept)"
            onClick={(event) => {
              event.stopPropagation();
              data.onRemove?.(data.occurrenceId);
            }}
          >
            ✕
          </button>
        )}
      </header>
      <strong className="architecture-node-name" title={data.label}>{data.label}</strong>
      <small title={data.description}>{data.missing ? "Canonical object unavailable" : data.description || data.kind || "System"}</small>
    </article>
  );
}
