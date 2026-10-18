import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import type { FlowSide } from "../../components/architecture/architectureRouting";
import type { SolutionComponent, SolutionInterface } from "../solutionModel";
import { interfaceHandle } from "../solutionCanvasModel";

export type SolutionComponentNodeData = {
  component: SolutionComponent;
  editable: boolean;
  selectedInterfaceId: string | null;
  selectedOperationId: string | null;
  /** Side each interface port sits on, chosen so connectors run straight across. */
  portSides?: Record<string, FlowSide>;
  onSelectInterface: (interfaceId: string) => void;
  onSelectOperation: (interfaceId: string, operationId: string) => void;
};

export type SolutionComponentFlowNode = Node<SolutionComponentNodeData, "solutionComponent">;

function InterfacePort({
  ui,
  side,
  portSide,
  selectedInterfaceId,
  selectedOperationId,
  onSelectInterface,
  onSelectOperation,
}: {
  ui: SolutionInterface;
  side: "provided" | "required";
  portSide: FlowSide;
  selectedInterfaceId: string | null;
  selectedOperationId: string | null;
  onSelectInterface: (interfaceId: string) => void;
  onSelectOperation: (interfaceId: string, operationId: string) => void;
}) {
  return (
    <li className={`solution-port solution-port-${side}${ui.object_id === selectedInterfaceId ? " selected" : ""}`}>
      <Handle
        type={side === "required" ? "source" : "target"}
        id={interfaceHandle(ui.object_id)}
        position={portSide === "left" ? Position.Left : Position.Right}
        className={`solution-port-handle solution-port-handle-${side}`}
      />
      <button
        type="button"
        className="nodrag nopan solution-port-head"
        title={ui.description ?? ui.name}
        aria-label={`${side} interface ${ui.name}`}
        onClick={(event) => {
          event.stopPropagation();
          onSelectInterface(ui.object_id);
        }}
      >
        <span className={`solution-direction direction-${side}`}>{side}</span>
        <span className="solution-port-name">{ui.name}</span>
        {ui.protocol && <small>{ui.protocol}</small>}
      </button>
      {ui.operations.length > 0 && (
        <ul className="solution-port-operations">
          {ui.operations.map((operation) => (
            <li key={operation.object_id}>
              <button
                type="button"
                className={`nodrag nopan${operation.object_id === selectedOperationId ? " selected" : ""}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectOperation(ui.object_id, operation.object_id);
                }}
              >
                <span className={`solution-op-kind kind-${operation.operation_kind}`}>{operation.operation_kind}</span>
                {operation.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function SolutionComponentNode({ data, selected }: NodeProps<SolutionComponentFlowNode>) {
  const { component, editable, selectedInterfaceId, selectedOperationId, portSides } = data;
  return (
    <article
      className={`solution-component-node${selected ? " selected" : ""}`}
      aria-label={`Component ${component.name}`}
      data-object-id={component.object_id}
      data-occurrence-id={component.occurrence_id}
    >
      <Handle type="target" position={Position.Top} isConnectable={editable} />
      <Handle type="source" position={Position.Bottom} isConnectable={editable} />
      <header>
        <span className="solution-component-node-icon" aria-hidden="true">▣</span>
        <strong title={component.name}>{component.name}</strong>
        {component.component_type && <em>{component.component_type}</em>}
      </header>
      {component.responsibility && (
        <p className="solution-component-node-responsibility">{component.responsibility}</p>
      )}
      <dl className="solution-component-node-meta">
        <div>
          <dt className="direction-provided">provided</dt>
          <dd>{component.interfaces.filter((ui) => ui.direction === "provided").length}</dd>
        </div>
        <div>
          <dt className="direction-required">required</dt>
          <dd>{component.interfaces.filter((ui) => ui.direction === "required").length}</dd>
        </div>
      </dl>
      <ul className="solution-port-list">
        {component.interfaces.map((ui) => (
          <InterfacePort
            key={ui.object_id}
            ui={ui}
            side={ui.direction}
            portSide={portSides?.[ui.object_id] ?? (ui.direction === "required" ? "left" : "right")}
            selectedInterfaceId={selectedInterfaceId}
            selectedOperationId={selectedOperationId}
            onSelectInterface={data.onSelectInterface}
            onSelectOperation={data.onSelectOperation}
          />
        ))}
      </ul>
    </article>
  );
}
