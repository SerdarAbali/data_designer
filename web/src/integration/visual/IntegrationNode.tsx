import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type IntegrationNodeTone = "system" | "runtime" | "solution" | "interface" | "contract";

export type IntegrationNodeData = {
  label: string;
  kind: string;
  detail?: string | null;
  meta?: string | null;
  badge?: string | null;
  tone: IntegrationNodeTone;
  mediated?: boolean;
};

export type IntegrationFlowNode = Node<IntegrationNodeData, "integrationNode">;

export default function IntegrationNode({ data, selected }: NodeProps<IntegrationFlowNode>) {
  return (
    <article
      className={`integration-topology-node tone-${data.tone}${selected ? " selected" : ""}${
        data.mediated ? " mediated" : ""
      }`}
      aria-label={`${data.kind} ${data.label}`}
      data-kind={data.tone}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <header>
        <span className="integration-topology-kind">{data.kind}</span>
        {data.badge && <em className="integration-topology-badge">{data.badge}</em>}
        {data.mediated && <em className="integration-topology-badge mediated">mediated</em>}
      </header>
      <strong title={data.label}>{data.label}</strong>
      {data.detail && <p>{data.detail}</p>}
      {data.meta && <footer>{data.meta}</footer>}
    </article>
  );
}
