import { useMemo, type ReactNode } from "react";
import { MarkerType, type Connection, type Viewport } from "@xyflow/react";

import type { ArchitectureState } from "../architectureTypes";
import type { SolutionDesign } from "./solutionModel";
import { contextGraph, type Point } from "./solutionCanvasModel";
import SolutionCanvas from "./SolutionCanvas";
import SolutionEdge, { type SolutionFlowEdge } from "./SolutionEdge";
import SolutionBoundaryNode, { type SolutionBoundaryFlowNode } from "./nodes/SolutionBoundaryNode";
import SolutionSystemNode, { type SolutionSystemFlowNode } from "./nodes/SolutionSystemNode";

const nodeTypes = { solutionBoundary: SolutionBoundaryNode, solutionSystem: SolutionSystemNode };
const edgeTypes = { solutionEdge: SolutionEdge };

type ContextFlowNode = SolutionBoundaryFlowNode | SolutionSystemFlowNode;

type Props = {
  design: SolutionDesign;
  state: ArchitectureState | null;
  editable: boolean;
  selectedSystemId: string | null;
  onSelectSystem: (systemId: string) => void;
  onSelectSolution: () => void;
  onMoveSystem: (occurrenceId: string, position: Point) => void;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
  toolbar?: ReactNode;
};

export default function SolutionContextView({
  design,
  state,
  editable,
  selectedSystemId,
  onSelectSystem,
  onSelectSolution,
  onMoveSystem,
  defaultViewport,
  onViewportChange,
  toolbar,
}: Props) {
  const graph = useMemo(() => contextGraph(design, state), [design, state]);

  const nodes = useMemo<ContextFlowNode[]>(() => {
    const boundary: SolutionBoundaryFlowNode = {
      id: graph.boundary.id,
      type: "solutionBoundary",
      position: graph.boundary.position,
      draggable: false,
      selectable: true,
      zIndex: -1,
      style: { width: graph.boundary.width, height: graph.boundary.height },
      data: {
        label: graph.boundary.label,
        identifier: design.solution.solution_object_id,
        editable,
      },
    };
    const systems: SolutionSystemFlowNode[] = graph.systems.map((system) => ({
      id: system.key,
      type: "solutionSystem",
      position: system.position,
      draggable: editable && Boolean(system.occurrenceId),
      selected: system.systemId === selectedSystemId,
      data: {
        name: system.name,
        kind: system.kind,
        external: system.external,
        objectId: system.systemId,
        editable,
      },
    }));
    return [boundary, ...systems];
  }, [graph, editable, selectedSystemId, design.solution.solution_object_id]);

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
      ariaLabel={`Context view for ${design.solution.name}`}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      editable={editable}
      onNodeClick={(_event, node) => {
        if (node.type === "solutionBoundary") {
          onSelectSolution();
          return;
        }
        if (node.type === "solutionSystem") {
          onSelectSystem((node as SolutionSystemFlowNode).data.objectId);
        }
      }}
      onNodeDragStop={(_event, node) => {
        if (!editable || node.type !== "solutionSystem") return;
        onMoveSystem(node.id, { x: node.position.x, y: node.position.y });
      }}
      onPaneClick={onSelectSolution}
      onConnect={(_connection: Connection) => undefined}
      emptyState={
        <>
          <h3>No systems on the canvas</h3>
          <p>Add member systems to place them inside the solution boundary.</p>
        </>
      }
      showEmpty={graph.systems.length === 0}
      defaultViewport={defaultViewport}
      onViewportChange={onViewportChange}
      toolbar={toolbar}
    />
  );
}
