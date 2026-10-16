import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { handleId, type FlowSide } from "../../components/architecture/architectureRouting";

export type SolutionSystemNodeData = {
  name: string;
  kind: string;
  external: boolean;
  objectId: string;
  editable: boolean;
};

export type SolutionSystemFlowNode = Node<SolutionSystemNodeData, "solutionSystem">;

const SIDES: { side: FlowSide; position: Position }[] = [
  { side: "top", position: Position.Top },
  { side: "right", position: Position.Right },
  { side: "bottom", position: Position.Bottom },
  { side: "left", position: Position.Left },
];

export default function SolutionSystemNode({ data, selected }: NodeProps<SolutionSystemFlowNode>) {
  return (
    <article
      className={`solution-system-node${data.external ? " external" : ""}${selected ? " selected" : ""}`}
      aria-label={`${data.external ? "External system" : "Member system"} ${data.name}`}
      data-object-id={data.objectId}
    >
      {SIDES.map(({ side, position }) => (
        <Handle key={`t-${side}`} id={handleId("target", side)} type="target" position={position} isConnectable={data.editable} />
      ))}
      {SIDES.map(({ side, position }) => (
        <Handle key={`s-${side}`} id={handleId("source", side)} type="source" position={position} isConnectable={data.editable} />
      ))}
      <header>
        <span className="solution-system-node-icon" aria-hidden="true">{data.external ? "◇" : "▧"}</span>
        <strong title={data.name}>{data.name}</strong>
      </header>
      <small>{data.external ? "external" : "member"} · {data.kind}</small>
    </article>
  );
}
