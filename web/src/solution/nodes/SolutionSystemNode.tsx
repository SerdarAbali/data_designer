import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type SolutionSystemNodeData = {
  name: string;
  kind: string;
  external: boolean;
  objectId: string;
  editable: boolean;
};

export type SolutionSystemFlowNode = Node<SolutionSystemNodeData, "solutionSystem">;

export default function SolutionSystemNode({ data, selected }: NodeProps<SolutionSystemFlowNode>) {
  return (
    <article
      className={`solution-system-node${data.external ? " external" : ""}${selected ? " selected" : ""}`}
      aria-label={`${data.external ? "External system" : "Member system"} ${data.name}`}
      data-object-id={data.objectId}
    >
      <Handle type="target" position={Position.Top} isConnectable={data.editable} />
      <Handle type="source" position={Position.Bottom} isConnectable={data.editable} />
      <Handle type="target" position={Position.Right} isConnectable={data.editable} />
      <Handle type="source" position={Position.Left} isConnectable={data.editable} />
      <header>
        <span className="solution-system-node-icon" aria-hidden="true">{data.external ? "◇" : "▧"}</span>
        <strong title={data.name}>{data.name}</strong>
      </header>
      <small>{data.external ? "external" : "member"} · {data.kind}</small>
    </article>
  );
}
