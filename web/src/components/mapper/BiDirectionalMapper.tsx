import React from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Node,
  type Edge,
  type NodeChange,
  type EdgeChange,
  type Connection,
  type NodeTypes,
  type EdgeTypes,
  MarkerType,
} from "@xyflow/react";
import MapperEdge from "./MapperEdge";
import SystemNodeCard from "./SystemNodeCard";
import type { CatalogField, System } from "./types";

type BiDirectionalMapperProps = {
  sourceSystem: System;
  targetSystem: System;
  sourceFields: CatalogField[];
  targetFields: CatalogField[];
  onEdgesChange?: (edges: Edge[]) => void;
  onNodesChange?: (nodes: Node[]) => void;
  initialEdges?: Edge[];
};

export default function BiDirectionalMapper({
  sourceSystem,
  targetSystem,
  sourceFields,
  targetFields,
  onEdgesChange,
  onNodesChange,
  initialEdges = [],
}: BiDirectionalMapperProps) {
  // Initialize nodes for 2-node mapper
  const initialNodes: Node[] = [
    {
      id: `system-${sourceSystem.id}`,
      type: "system-card",
      data: {
        label: `${sourceSystem.name} (Source)`,
        systemId: sourceSystem.id,
        fields: sourceFields,
        isSource: true,
      },
      position: { x: 50, y: 200 },
      draggable: true,
    },
    {
      id: `system-${targetSystem.id}`,
      type: "system-card",
      data: {
        label: `${targetSystem.name} (Target)`,
        systemId: targetSystem.id,
        fields: targetFields,
        isTarget: true,
      },
      position: { x: 600, y: 200 },
      draggable: true,
    },
  ];

  const [nodes, setNodes] = React.useState<Node[]>(initialNodes);
  const [edges, setEdges] = React.useState<Edge[]>(
    initialEdges.map((edge) => ({
      ...edge,
      type: "mapper-edge",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#2563eb" },
      markerStart: undefined,
    }))
  );

  const handleNodesChange = (changes: NodeChange[]) => {
    const newNodes = applyNodeChanges(changes, nodes);
    setNodes(newNodes);
    onNodesChange?.(newNodes);
  };

  const handleEdgesChange = (changes: EdgeChange[]) => {
    const newEdges = applyEdgeChanges(changes, edges);
    setEdges(newEdges);
    onEdgesChange?.(newEdges);
  };

  const handleConnect = (connection: Connection) => {
    const newEdge: Edge = {
      id: `edge-${connection.source}-${connection.sourceHandle}-${connection.target}-${connection.targetHandle}`,
      source: connection.source!,
      target: connection.target!,
      sourceHandle: connection.sourceHandle,
      targetHandle: connection.targetHandle,
      type: "mapper-edge",
      // Determine direction based on handles
      data: {
        direction:
          connection.sourceHandle?.includes("output") ||
          connection.sourceHandle?.includes("response")
            ? "outbound"
            : "inbound",
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#2563eb" },
    };

    setEdges((current) => addEdge(newEdge, current));
    onEdgesChange?.([...edges, newEdge]);
  };

  const nodeTypes: NodeTypes = {
    "system-card": SystemNodeCard,
  };

  const edgeTypes: EdgeTypes = {
    "mapper-edge": MapperEdge,
  };

  return (
    <div style={{ width: "100%", height: "100vh" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        fitView
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#d5dee6" gap={18} size={1.2} variant={BackgroundVariant.Dots} />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}
