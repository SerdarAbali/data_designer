import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type ProjectionNodeTone =
  | "concept"
  | "logical"
  | "attribute"
  | "catalog"
  | "contract"
  | "system";

export type ProjectionNodeData = {
  label: string;
  kind: string;
  detail?: string | null;
  meta?: string | null;
  badge?: string | null;
  gap?: boolean;
  dimmed?: boolean;
  tone: ProjectionNodeTone;
};

export type ProjectionFlowNode = Node<ProjectionNodeData, "informationProjection">;

export default function ProjectionNode({ data, selected }: NodeProps<ProjectionFlowNode>) {
  return (
    <article
      className={`information-projection-node tone-${data.tone}${selected ? " selected" : ""}${
        data.gap ? " has-gap" : ""
      }${data.dimmed ? " dimmed" : ""}`}
      aria-label={`${data.kind} ${data.label}`}
      data-kind={data.tone}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <header>
        <span className="information-projection-kind">{data.kind}</span>
        {data.badge && <em className="information-projection-badge">{data.badge}</em>}
        {data.gap && <em className="information-projection-badge gap">gap</em>}
      </header>
      <strong title={data.label}>{data.label}</strong>
      {data.detail && <p>{data.detail}</p>}
      {data.meta && <footer>{data.meta}</footer>}
    </article>
  );
}
