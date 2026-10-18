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
import { nodeRectMap } from "../../components/architecture/architectureRouting";

/** Minimum vertical gap kept between de-collided edge labels. */
const LABEL_MIN_GAP = 20;
/** Distance between distinct lanes for parallel edges sharing a node pair. */
const LANE_SPACING = 18;

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
  /** Hover handlers receive the node/edge itself, not the DOM event. */
  onNodeMouseEnter?: (node: NodeType) => void;
  onNodeMouseLeave?: () => void;
  onEdgeMouseEnter?: (edge: EdgeType) => void;
  onEdgeMouseLeave?: () => void;
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
  onNodeMouseEnter,
  onNodeMouseLeave,
  onEdgeMouseEnter,
  onEdgeMouseLeave,
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

  // Give parallel relationships sharing a node pair distinct lanes so their
  // labels stagger vertically instead of overlapping.
  const laneByEdgeId = useMemo(() => {
    const grouped = new Map<string, string[]>();
    for (const edge of edges) {
      const key = [edge.source, edge.target].sort().join("|");
      const list = grouped.get(key) ?? [];
      list.push(edge.id);
      grouped.set(key, list);
    }
    const out = new Map<string, number>();
    for (const ids of grouped.values()) {
      const center = (ids.length - 1) / 2;
      ids.forEach((id, index) => {
        out.set(id, (index - center) * LANE_SPACING);
      });
    }
    return out;
  }, [edges]);

  // Connectors route orthogonally around the other node boxes.
  const routedEdges = useMemo(() => {
    const base = withEdgeObstacles(localNodes, edges);
    return base.map((edge) => {
      const laneOffset = laneByEdgeId.get(edge.id) ?? 0;
      return {
        ...edge,
        data: {
          ...(((edge as unknown) as { data?: Record<string, unknown> }).data ?? {}),
          laneOffset,
        },
      } as EdgeType;
    });
  }, [localNodes, edges, laneByEdgeId]);

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
        onNodeMouseEnter={(_event, node) => onNodeMouseEnter?.(node)}
        onNodeMouseLeave={() => onNodeMouseLeave?.()}
        onEdgeMouseEnter={(_event, edge) => onEdgeMouseEnter?.(edge)}
        onEdgeMouseLeave={() => onEdgeMouseLeave?.()}
        onPaneClick={onPaneClick}
        nodesConnectable={false}
        nodesDraggable={editable}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
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
