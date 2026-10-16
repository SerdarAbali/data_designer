import { useMemo, type ReactNode } from "react";
import { MarkerType, type Connection, type Viewport } from "@xyflow/react";

import type { ArchitectureState } from "../architectureTypes";
import type { SolutionDesign } from "./solutionModel";
import { decompositionGraph, interfaceHandle, type Point } from "./solutionCanvasModel";
import SolutionCanvas from "./SolutionCanvas";
import SolutionEdge, { type SolutionFlowEdge } from "./SolutionEdge";
import SolutionBoundaryNode, { type SolutionBoundaryFlowNode } from "./nodes/SolutionBoundaryNode";
import SolutionComponentNode, {
  type SolutionComponentFlowNode,
} from "./nodes/SolutionComponentNode";
import SolutionRepositoryNode, {
  type SolutionRepositoryFlowNode,
} from "./nodes/SolutionRepositoryNode";
import SolutionSystemNode, { type SolutionSystemFlowNode } from "./nodes/SolutionSystemNode";

const nodeTypes = {
  solutionBoundary: SolutionBoundaryNode,
  solutionComponent: SolutionComponentNode,
  solutionRepository: SolutionRepositoryNode,
  solutionSystem: SolutionSystemNode,
};
const edgeTypes = { solutionEdge: SolutionEdge };

type FlowNode =
  | SolutionBoundaryFlowNode
  | SolutionComponentFlowNode
  | SolutionRepositoryFlowNode
  | SolutionSystemFlowNode;

type Props = {
  design: SolutionDesign;
  state: ArchitectureState | null;
  editable: boolean;
  selectedComponentId: string | null;
  selectedInterfaceId: string | null;
  selectedOperationId: string | null;
  selectedRepositoryId: string | null;
  onSelectComponent: (componentId: string) => void;
  onSelectInterface: (componentId: string, interfaceId: string) => void;
  onSelectOperation: (componentId: string, interfaceId: string, operationId: string) => void;
  onSelectRepository: (repositoryId: string) => void;
  onMoveComponent: (occurrenceId: string, position: Point) => void;
  onConnectInterfaces: (sourceInterfaceId: string, targetInterfaceId: string) => void;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
  toolbar?: ReactNode;
};

function interfaceIdFromHandle(handle: string | null | undefined): string | null {
  if (!handle || !handle.startsWith("iface-")) return null;
  return handle.slice("iface-".length);
}

export default function SolutionDecompositionView({
  design,
  state,
  editable,
  selectedComponentId,
  selectedInterfaceId,
  selectedOperationId,
  selectedRepositoryId,
  onSelectComponent,
  onSelectInterface,
  onSelectOperation,
  onSelectRepository,
  onMoveComponent,
  onConnectInterfaces,
  defaultViewport,
  onViewportChange,
  toolbar,
}: Props) {
  const graph = useMemo(() => decompositionGraph(design, state), [design, state]);

  const nodes = useMemo<FlowNode[]>(() => {
    const boundary: SolutionBoundaryFlowNode = {
      id: graph.boundary.id,
      type: "solutionBoundary",
      position: graph.boundary.position,
      draggable: false,
      selectable: false,
      zIndex: -1,
      style: { width: graph.boundary.width, height: graph.boundary.height },
      data: {
        label: graph.boundary.label,
        identifier: design.solution.solution_object_id,
        editable,
      },
    };
    const components: SolutionComponentFlowNode[] = graph.components.map((item) => ({
      id: item.key,
      type: "solutionComponent",
      position: item.position,
      draggable: editable,
      selected: item.component.object_id === selectedComponentId,
      data: {
        component: item.component,
        editable,
        selectedInterfaceId,
        selectedOperationId,
        onSelectInterface: (interfaceId: string) => onSelectInterface(item.component.object_id, interfaceId),
        onSelectOperation: (interfaceId: string, operationId: string) =>
          onSelectOperation(item.component.object_id, interfaceId, operationId),
      },
    }));
    const repositories: SolutionRepositoryFlowNode[] = graph.repositories.map((item) => ({
      id: item.key,
      type: "solutionRepository",
      position: item.position,
      draggable: false,
      selected: item.repository.object_id === selectedRepositoryId,
      data: { repository: item.repository, editable },
    }));
    const externals: SolutionSystemFlowNode[] = graph.externals.map((system) => ({
      id: system.key,
      type: "solutionSystem",
      position: system.position,
      draggable: false,
      data: {
        name: system.name,
        kind: system.kind,
        external: true,
        objectId: system.systemId,
        editable,
      },
    }));
    return [boundary, ...components, ...repositories, ...externals];
  }, [
    graph,
    editable,
    selectedComponentId,
    selectedInterfaceId,
    selectedOperationId,
    selectedRepositoryId,
    design.solution.solution_object_id,
    onSelectInterface,
    onSelectOperation,
  ]);

  const edges = useMemo<SolutionFlowEdge[]>(
    () =>
      graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle ?? undefined,
        targetHandle: edge.targetHandle ?? undefined,
        type: "solutionEdge" as const,
        markerEnd: { type: MarkerType.ArrowClosed },
        data: { kind: edge.kind, label: edge.label, sourceOffset: edge.sourceOffset, targetOffset: edge.targetOffset },
      })),
    [graph.edges],
  );

  return (
    <SolutionCanvas
      ariaLabel={`Decomposition view for ${design.solution.name}`}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      editable={editable}
      onNodeClick={(_event, node) => {
        if (node.type === "solutionComponent") {
          onSelectComponent((node as SolutionComponentFlowNode).data.component.object_id);
        } else if (node.type === "solutionRepository") {
          onSelectRepository((node as SolutionRepositoryFlowNode).data.repository.object_id);
        }
      }}
      onNodeDragStop={(_event, node) => {
        if (!editable || node.type !== "solutionComponent") return;
        onMoveComponent(node.id, { x: node.position.x, y: node.position.y });
      }}
      onConnect={(connection: Connection) => {
        const source = interfaceIdFromHandle(connection.sourceHandle);
        const target = interfaceIdFromHandle(connection.targetHandle);
        if (source && target) onConnectInterfaces(source, target);
      }}
      onPaneClick={() => undefined}
      emptyState={
        <>
          <h3>No components yet</h3>
          <p>Add a component to decompose the solution.</p>
        </>
      }
      showEmpty={graph.components.length === 0}
      defaultViewport={defaultViewport}
      onViewportChange={onViewportChange}
      toolbar={
        <>
          {toolbar}
          <span className="solution-canvas-count">
            {graph.components.length} components · {graph.repositories.length} repositories
          </span>
        </>
      }
    />
  );
}

export { interfaceHandle };
