import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
  type NodeMouseHandler,
  type OnNodeDrag,
  type NodeTypes,
  type EdgeTypes,
  type Viewport,
} from "@xyflow/react";

import { withEdgeObstacles } from "../../components/architecture/edgeObstacles";

type Props<NodeType extends Node, EdgeType extends Edge> = {
  ariaLabel: string;
  nodes: NodeType[];
  edges: EdgeType[];
  nodeTypes: NodeTypes;
  edgeTypes: EdgeTypes;
  editable: boolean;
  onNodeClick: NodeMouseHandler<NodeType>;
  onNodeDragStop?: OnNodeDrag<NodeType>;
  onPaneClick?: () => void;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
  emptyState?: ReactNode;
  toolbar?: ReactNode;
};

export default function EnterpriseCanvas<NodeType extends Node, EdgeType extends Edge>({
  ariaLabel,
  nodes,
  edges,
  nodeTypes,
  edgeTypes,
  editable,
  onNodeClick,
  onNodeDragStop,
  onPaneClick,
  defaultViewport,
  onViewportChange,
  emptyState,
  toolbar,
}: Props<NodeType, EdgeType>) {
  const [localNodes, setLocalNodes] = useState<NodeType[]>(nodes);

  useEffect(() => {
    setLocalNodes(nodes);
  }, [nodes]);

  const handleNodesChange = useCallback((changes: NodeChange<NodeType>[]) => {
    setLocalNodes((current) => applyNodeChanges(changes, current));
  }, []);

  // Connectors route orthogonally around the other node boxes.
  const routedEdges = useMemo(
    () => withEdgeObstacles(localNodes, edges),
    [localNodes, edges],
  );

  return (
    <div className="enterprise-canvas" aria-label={ariaLabel}>
      <ReactFlow<NodeType, EdgeType>
        nodes={localNodes}
        edges={routedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        onPaneClick={onPaneClick}
        nodesConnectable={false}
        nodesDraggable={editable}
        deleteKeyCode={null}
        defaultViewport={defaultViewport}
        onMoveEnd={(_event, viewport) => onViewportChange?.(viewport)}
        fitView={!defaultViewport}
        fitViewOptions={{ padding: 0.25, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.8}
      >
        <Background color="var(--color-grid)" gap={20} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
        {toolbar && <Panel position="top-left" className="enterprise-canvas-toolbar">{toolbar}</Panel>}
      </ReactFlow>
      {nodes.length === 0 && emptyState && <div className="enterprise-canvas-empty">{emptyState}</div>}
    </div>
  );
}

export const ENTERPRISE_EDGE_DEFAULTS = {
  type: "enterpriseEdge" as const,
  markerEnd: { type: MarkerType.ArrowClosed },
};
