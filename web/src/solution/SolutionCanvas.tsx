import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Background,
  Controls,
  Panel,
  ReactFlow,
  applyNodeChanges,
  MarkerType,
  type Connection,
  type Edge,
  type EdgeMouseHandler,
  type Node,
  type NodeChange,
  type NodeMouseHandler,
  type OnNodeDrag,
  type NodeTypes,
  type EdgeTypes,
  type Viewport,
} from "@xyflow/react";

type Props<NodeType extends Node, EdgeType extends Edge> = {
  ariaLabel: string;
  nodes: NodeType[];
  edges: EdgeType[];
  nodeTypes: NodeTypes;
  edgeTypes: EdgeTypes;
  editable: boolean;
  onNodeClick: NodeMouseHandler<NodeType>;
  onEdgeClick?: EdgeMouseHandler<EdgeType>;
  onNodeDragStop: OnNodeDrag<NodeType>;
  onConnect?: (connection: Connection) => void;
  onPaneClick?: () => void;
  emptyState?: ReactNode;
  showEmpty?: boolean;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
  toolbar?: ReactNode;
};

/**
 * Shared React Flow shell for the solution views. Node positions are held in
 * local state for smooth dragging and persisted by the parent on drag stop.
 */
export default function SolutionCanvas<NodeType extends Node, EdgeType extends Edge>({
  ariaLabel,
  nodes,
  edges,
  nodeTypes,
  edgeTypes,
  editable,
  onNodeClick,
  onEdgeClick,
  onNodeDragStop,
  onConnect,
  onPaneClick,
  emptyState,
  showEmpty,
  defaultViewport,
  onViewportChange,
  toolbar,
}: Props<NodeType, EdgeType>) {
  const [localNodes, setLocalNodes] = useState<NodeType[]>(nodes);

  useEffect(() => {
    setLocalNodes(nodes);
  }, [nodes]);

  const handleNodesChange = useCallback((changes: NodeChange<NodeType>[]) => {
    setLocalNodes((current) => applyNodeChanges(changes, current));
  }, []);

  return (
    <div className="solution-canvas" aria-label={ariaLabel}>
      <ReactFlow<NodeType, EdgeType>
        nodes={localNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onNodeDragStop={onNodeDragStop}
        onConnect={onConnect}
        onPaneClick={onPaneClick}
        nodesConnectable={editable}
        nodesDraggable={editable}
        deleteKeyCode={null}
        defaultViewport={defaultViewport}
        onMoveEnd={(_event, viewport) => onViewportChange?.(viewport)}
        fitView
        fitViewOptions={{ padding: 0.25, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.8}
      >
        <Background color="var(--color-grid)" gap={20} size={1} />
        <Controls showInteractive={false} position="bottom-right" fitViewOptions={{ padding: 0.25, maxZoom: 1 }} />
        {toolbar && <Panel position="top-left" className="solution-canvas-toolbar">{toolbar}</Panel>}
      </ReactFlow>
      {(showEmpty ?? nodes.length === 0) && emptyState && (
        <div className="solution-canvas-empty">{emptyState}</div>
      )}    </div>
  );
}

export const SOLUTION_EDGE_DEFAULTS = {
  type: "solutionEdge" as const,
  markerEnd: { type: MarkerType.ArrowClosed },
};
