import React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { handleId, type FlowSide } from "./architectureRouting";
import type { ArchitectureOccurrenceNode } from "./ArchitectureOccurrenceNode";

const SIDES: { side: FlowSide; position: Position }[] = [
  { side: "top", position: Position.Top },
  { side: "right", position: Position.Right },
  { side: "bottom", position: Position.Bottom },
  { side: "left", position: Position.Left },
];

export default function ArchitectureBoundaryNode({ data, selected }: NodeProps<ArchitectureOccurrenceNode>) {
  return (
    <section className={`architecture-boundary${selected ? " selected" : ""}`} aria-label={`${data.label}, Solution Boundary`} data-object-id={data.objectId}>
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
      <header className="architecture-boundary-label">
        <span aria-hidden="true">▧</span>
        <strong>{data.label}</strong>
        <span className="boundary-type">Solution boundary</span>
      </header>
    </section>
  );
}
