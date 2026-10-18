import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { architectureFactLabel } from "../../architectureFacts";
import { handleId, type FlowSide } from "../../components/architecture/architectureRouting";

export type SolutionLandscapeNodeData = {
  name: string;
  owner: string | null;
  lifecycle: string | null;
  operational: string | null;
  componentCount: number;
  memberCount: number;
  contractRoleSummary: string;
  evidenceCount: number;
  warningCount: number;
  stateName: string;
  objectId: string;
  editable: boolean;
};

export type SolutionLandscapeFlowNode = Node<SolutionLandscapeNodeData, "solutionLandscape">;

const SIDES: { side: FlowSide; position: Position }[] = [
  { side: "top", position: Position.Top },
  { side: "right", position: Position.Right },
  { side: "bottom", position: Position.Bottom },
  { side: "left", position: Position.Left },
];

export default function SolutionLandscapeNode({
  data,
  selected,
}: NodeProps<SolutionLandscapeFlowNode>) {
  return (
    <article
      className={`solution-landscape-node${selected ? " selected" : ""}`}
      aria-label={`Solution ${data.name}`}
      data-object-id={data.objectId}
    >
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`t-${side}`}
          id={handleId("target", side)}
          type="target"
          position={position}
          isConnectable={false}
        />
      ))}
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`s-${side}`}
          id={handleId("source", side)}
          type="source"
          position={position}
          isConnectable={false}
        />
      ))}
      <header>
        <strong title={data.name}>{data.name}</strong>
        {data.warningCount > 0 && (
          <span className="solution-landscape-warning" title="Unavailable reference">
            ⚠ {data.warningCount} unavailable
          </span>
        )}
      </header>
      <small className="solution-landscape-owner">
        Owner: {data.owner && data.owner.length > 0 ? data.owner : "Unspecified"}
      </small>
      <dl className="solution-landscape-node-facts">
        <div>
          <dt>Lifecycle</dt>
          <dd>{architectureFactLabel(data.lifecycle)}</dd>
        </div>
        <div>
          <dt>Operational</dt>
          <dd>{architectureFactLabel(data.operational)}</dd>
        </div>
        <div>
          <dt>Components</dt>
          <dd>{data.componentCount}</dd>
        </div>
        <div>
          <dt>Member systems</dt>
          <dd>{data.memberCount}</dd>
        </div>
        <div>
          <dt>Contracts</dt>
          <dd>{data.contractRoleSummary}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{data.evidenceCount}</dd>
        </div>
      </dl>
      <small className="solution-landscape-state">{data.stateName}</small>
    </article>
  );
}
