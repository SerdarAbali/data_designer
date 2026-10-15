import React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { ArchitectureOccurrenceNode } from "./ArchitectureOccurrenceNode";

export default function ArchitectureBoundaryNode({ data, selected }: NodeProps<ArchitectureOccurrenceNode>) {
  return (
    <section className={`architecture-boundary${selected ? " selected" : ""}`} aria-label={`${data.label}, Solution Boundary`} data-object-id={data.objectId}>
      <Handle type="target" position={Position.Left} isConnectable={data.editable} />
      <header className="architecture-boundary-label">
        <span aria-hidden="true">▧</span>
        <strong>{data.label}</strong>
        <span className="boundary-type">Solution boundary</span>
      </header>
      <Handle type="source" position={Position.Right} isConnectable={data.editable} />
    </section>
  );
}
