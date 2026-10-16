import {
  Background,
  Controls,
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
  onNodeDoubleClick?: (node: NodeType) => void;
  onPaneClick?: () => void;
  onNodeDragStop?: (nodeId: string, position: { x: number; y: number }) => void;
  toolbar?: ReactNode;
  emptyState?: ReactNode;
};

/**
 * Shared React Flow canvas for the Integration visual projections. Each view
 * supplies its own node and edge renderers so the topology, the flow lanes and
 * the sequence read as distinct diagrams rather than one generic renderer.
 */
export default function IntegrationCanvas<NodeType extends Node, EdgeType extends Edge>({
  ariaLabel,
  nodes,
  edges,
  nodeTypes,
  edgeTypes,
  draggable = false,
  defaultViewport,
  onViewportChange,
  onNodeClick,
  onNodeDoubleClick,
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
    return <div className="integration-projection-empty">{emptyState}</div>;
  }

  return (
    <div className="architecture-canvas integration-projection-canvas" aria-label={ariaLabel}>
      <ReactFlow<NodeType, EdgeType>
        nodes={flowNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={(changes: NodeChange<NodeType>[]) => {
          setFlowNodes((current) => applyNodeChanges(changes, current));
        }}
        onNodeClick={(_event, node) => onNodeClick?.(node)}
        onNodeDoubleClick={(_event, node) => onNodeDoubleClick?.(node)}
        onPaneClick={onPaneClick}
        onNodeDragStop={(_event, node) => onNodeDragStop?.(node.id, node.position)}
        defaultViewport={defaultViewport}
        onMoveEnd={(_event, viewport) => onViewportChange?.(viewport)}
        nodesDraggable={draggable}
        nodesConnectable={false}
        edgesFocusable={false}
        deleteKeyCode={null}
        fitView={!defaultViewport}
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.8}
      >
        <Background color="var(--color-grid)" gap={20} size={1} />
        <Controls
          showInteractive={false}
          position="bottom-right"
          fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        />
        {toolbar && (
          <Panel position="top-left" className="integration-canvas-toolbar">
            {toolbar}
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}
