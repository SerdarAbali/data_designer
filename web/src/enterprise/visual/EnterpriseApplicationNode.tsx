import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type EnterpriseApplicationNodeData = {
  name: string;
  applicationKind: string;
};

export type EnterpriseApplicationFlowNode = Node<EnterpriseApplicationNodeData, "enterpriseApplication">;

export default function EnterpriseApplicationNode({ data, selected }: NodeProps<EnterpriseApplicationFlowNode>) {
  return (
    <article
      className={`enterprise-application-node${selected ? " selected" : ""}`}
      aria-label={`Application ${data.name}`}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <header>
        <span className="enterprise-node-kind">Application</span>
        <em className="enterprise-node-badge">{data.applicationKind}</em>
      </header>
      <strong title={data.name}>{data.name}</strong>
    </article>
  );
}
