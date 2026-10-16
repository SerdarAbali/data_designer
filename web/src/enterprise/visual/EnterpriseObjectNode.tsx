import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type EnterpriseObjectNodeData = {
  name: string;
  kind: string;
  kindLabel: string;
  owner: string | null;
  description?: string | null;
  processType: string | null;
  gap: string | null;
  editable: boolean;
};

export type EnterpriseObjectFlowNode = Node<EnterpriseObjectNodeData, "enterpriseObject">;

export default function EnterpriseObjectNode({ data, selected }: NodeProps<EnterpriseObjectFlowNode>) {
  return (
    <article
      className={`enterprise-node${selected ? " selected" : ""}${data.gap ? " has-gap" : ""}`}
      aria-label={`${data.kindLabel} ${data.name}`}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <header>
        <span className="enterprise-node-kind">{data.kindLabel}</span>
        {data.processType === "value_stream" && <em className="enterprise-node-badge">value stream</em>}
        {data.gap && <em className="enterprise-node-badge enterprise-node-gap">{data.gap}</em>}
      </header>
      <strong title={data.name}>{data.name}</strong>
      {data.description && (
        <small className="enterprise-node-description" title={data.description}>
          {data.description}
        </small>
      )}
      {data.owner && <small>{data.owner}</small>}
    </article>
  );
}
