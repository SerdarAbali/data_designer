import {
  Background,
  Controls,
  Panel,
  ReactFlow,
  applyNodeChanges,
  type Connection,
  type NodeChange,
} from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";

import InformationEntityNode, { type InformationEntityFlowNode } from "./InformationEntityNode";
import InformationRelationshipEdge, {
  type InformationRelationshipFlowEdge,
} from "./InformationRelationshipEdge";
import { CARDINALITY_OPTIONS, type InformationCardinality, type InformationModel } from "./informationModel";

const nodeTypes = { informationEntity: InformationEntityNode };
const edgeTypes = { informationRelationship: InformationRelationshipEdge };

type Props = {
  model: InformationModel;
  editable: boolean;
  selectedEntityId: string | null;
  selectedAttributeId: string | null;
  selectedRelationshipId: string | null;
  pendingCardinality: InformationCardinality;
  onSelectEntity: (occurrenceId: string) => void;
  onSelectAttribute: (attributeId: string) => void;
  onSelectRelationship: (relationshipId: string) => void;
  onPaneClick: () => void;
  onConnect: (sourceObjectId: string, targetObjectId: string) => void;
  onMoveEntity: (occurrenceId: string, position: { x: number; y: number }) => void;
  onPendingCardinalityChange: (cardinality: InformationCardinality) => void;
};

export default function InformationERCanvas({
  model,
  editable,
  selectedEntityId,
  selectedAttributeId,
  selectedRelationshipId,
  pendingCardinality,
  onSelectEntity,
  onSelectAttribute,
  onSelectRelationship,
  onPaneClick,
  onConnect,
  onMoveEntity,
  onPendingCardinalityChange,
}: Props) {
  const [nodes, setNodes] = useState<InformationEntityFlowNode[]>([]);

  const occurrenceByObject = useMemo(
    () => new Map(model.entities.map((entity) => [entity.object_id, entity.occurrence_id])),
    [model.entities],
  );

  useEffect(() => {
    setNodes(model.entities.map((entity) => ({
      id: entity.occurrence_id,
      type: "informationEntity" as const,
      position: entity.position,
      selected: entity.occurrence_id === selectedEntityId,
      data: {
        entity,
        editable,
        selectedAttributeId,
        onSelectAttribute,
      },
    })));
  }, [model.entities, editable, selectedEntityId, selectedAttributeId, onSelectAttribute]);

  const edges = useMemo<InformationRelationshipFlowEdge[]>(
    () => model.relationships.flatMap((relationship) => {
      const source = occurrenceByObject.get(relationship.source_object_id);
      const target = occurrenceByObject.get(relationship.target_object_id);
      if (!source || !target) return [];
      return [{
        id: relationship.id,
        source,
        target,
        type: "informationRelationship" as const,
        selected: relationship.id === selectedRelationshipId,
        data: { relationship },
      }];
    }),
    [model.relationships, occurrenceByObject, selectedRelationshipId],
  );

  function handleConnect(connection: Connection) {
    if (!editable || !connection.source || !connection.target) return;
    const sourceEntity = model.entities.find((entity) => entity.occurrence_id === connection.source);
    const targetEntity = model.entities.find((entity) => entity.occurrence_id === connection.target);
    if (!sourceEntity || !targetEntity || sourceEntity.object_id === targetEntity.object_id) return;
    onConnect(sourceEntity.object_id, targetEntity.object_id);
  }

  return (
    <div className="architecture-canvas information-canvas" aria-label="Information model canvas">
      <ReactFlow<InformationEntityFlowNode, InformationRelationshipFlowEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={(changes: NodeChange<InformationEntityFlowNode>[]) => {
          setNodes((current) => applyNodeChanges(changes, current));
        }}
        onNodeDragStop={(_event, node) => {
          if (!editable) return;
          onMoveEntity(node.id, { x: node.position.x, y: node.position.y });
        }}
        onNodeClick={(_event, node) => onSelectEntity(node.id)}
        onEdgeClick={(_event, edge) => onSelectRelationship(edge.id)}
        onConnect={handleConnect}
        onPaneClick={onPaneClick}
        nodesConnectable={editable}
        nodesDraggable={editable}
        deleteKeyCode={null}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.8}
      >
        <Background color="var(--color-grid)" gap={20} size={1} />
        <Controls showInteractive={false} position="bottom-right" fitViewOptions={{ padding: 0.2, maxZoom: 1 }} />
        <Panel position="top-left" className="information-canvas-toolbar">
          <label>
            New relationship
            <select
              aria-label="Cardinality for new relationships"
              value={pendingCardinality}
              disabled={!editable}
              onChange={(event) => onPendingCardinalityChange(event.target.value as InformationCardinality)}
            >
              {CARDINALITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <span className="information-canvas-count">
            {model.entities.length} entities · {model.relationships.length} relationships
          </span>
        </Panel>
      </ReactFlow>
    </div>
  );
}
