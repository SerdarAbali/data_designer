import {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeChange,
  type NodeTypes,
  type Viewport,
} from "@xyflow/react";
import { useEffect, useState, type ReactNode } from "react";

type Props<NodeType extends Node, EdgeType extends Edge> = {
  ariaLabel: string;
  nodes: NodeType[];
  edges: EdgeType[];
  nodeTypes: NodeTypes;
  edgeTypes: EdgeTypes;
  draggable?: boolean;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
  onNodeClick?: (node: NodeType) => void;
  onPaneClick?: () => void;
  onNodeDragStop?: (nodeId: string, position: { x: number; y: number }) => void;
  toolbar?: ReactNode;
  emptyState?: ReactNode;
};

/**
 * Shared canvas for the Information projections. It is deliberately generic:
 * each view supplies its own node and edge renderers so the conceptual,
 * realization and lineage views are visually distinct rather than one generic
 * node renderer reused everywhere.
 */
export default function InformationProjectionCanvas<NodeType extends Node, EdgeType extends Edge>({
  ariaLabel,
  nodes,
  edges,
  nodeTypes,
  edgeTypes,
  draggable = false,
  defaultViewport,
  onViewportChange,
  onNodeClick,
  onPaneClick,
  onNodeDragStop,
  toolbar,
  emptyState,
}: Props<NodeType, EdgeType>) {
  const [flowNodes, setFlowNodes] = useState<NodeType[]>(nodes);

  useEffect(() => {
    setFlowNodes(nodes);
  }, [nodes]);

  if (nodes.length === 0 && emptyState) {
    return <div className="information-projection-empty">{emptyState}</div>;
  }

  return (
    <div className="architecture-canvas information-projection-canvas" aria-label={ariaLabel}>
      <ReactFlow<NodeType, EdgeType>
        nodes={flowNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={(changes: NodeChange<NodeType>[]) => {
          setFlowNodes((current) => applyNodeChanges(changes, current));
        }}
        onNodeClick={(_event, node) => onNodeClick?.(node)}
        onPaneClick={onPaneClick}
        onNodeDragStop={(_event, node) => onNodeDragStop?.(node.id, node.position)}
        defaultViewport={defaultViewport}
        onMoveEnd={(_event, viewport) => onViewportChange?.(viewport)}
        nodesDraggable={draggable}
        nodesConnectable={false}
        edgesFocusable={false}
        deleteKeyCode={null}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.8}
      >
        <Background color="var(--color-grid)" gap={20} size={1} />
        <Controls showInteractive={false} position="bottom-right" fitViewOptions={{ padding: 0.2, maxZoom: 1 }} />
        {toolbar && (
          <Panel position="top-left" className="information-canvas-toolbar">
            {toolbar}
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}

export const PROJECTION_MARKER = { type: MarkerType.ArrowClosed } as const;
