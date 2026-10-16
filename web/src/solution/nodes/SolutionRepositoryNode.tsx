import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import type { SolutionRepository } from "../solutionModel";

export type SolutionRepositoryNodeData = {
  repository: SolutionRepository;
  editable: boolean;
};

export type SolutionRepositoryFlowNode = Node<SolutionRepositoryNodeData, "solutionRepository">;

export default function SolutionRepositoryNode({ data, selected }: NodeProps<SolutionRepositoryFlowNode>) {
  const { repository } = data;
  return (
    <article
      className={`solution-repository-node${selected ? " selected" : ""}`}
      aria-label={`Repository ${repository.name}`}
      data-object-id={repository.object_id}
    >
      <Handle type="target" position={Position.Top} isConnectable={data.editable} />
      <Handle type="source" position={Position.Bottom} isConnectable={data.editable} />
      <header>
        <span className="solution-repository-node-icon" aria-hidden="true">⛁</span>
        <strong title={repository.name}>{repository.name}</strong>
      </header>
      <small>{[repository.repository_type, repository.technology].filter(Boolean).join(" · ") || "repository"}</small>
      {repository.owner && <small className="solution-repository-owner">owner · {repository.owner}</small>}
    </article>
  );
}
