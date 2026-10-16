import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type SolutionBoundaryNodeData = {
  label: string;
  identifier: string;
  editable: boolean;
};

export type SolutionBoundaryFlowNode = Node<SolutionBoundaryNodeData, "solutionBoundary">;

export default function SolutionBoundaryNode({ data, selected }: NodeProps<SolutionBoundaryFlowNode>) {
  return (
    <section
      className={`solution-boundary-node${selected ? " selected" : ""}`}
      aria-label={`Solution boundary ${data.label}`}
      data-object-id={data.identifier}
    >
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <header className="solution-boundary-node-label">
        <span className="solution-boundary-node-kind">SOLUTION</span>
        <strong>{data.label}</strong>
      </header>
    </section>
  );
}
