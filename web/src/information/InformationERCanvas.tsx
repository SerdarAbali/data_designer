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
import {
  CARDINALITY_OPTIONS,
  resolveRelationshipHandles,
  type InformationCardinality,
  type InformationModel,
  type InformationRelationship,
} from "./informationModel";

const nodeTypes = { informationEntity: InformationEntityNode };
const edgeTypes = { informationRelationship: InformationRelationshipEdge };

const ENTITY_HALF_WIDTH = 115;
const ENTITY_HALF_HEIGHT = 60;

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
  onConnect: (
    sourceObjectId: string,
    targetObjectId: string,
    sourceHandle: string | null,
    targetHandle: string | null,
  ) => void;
  onReconnectRelationship?: (args: {
    relationshipId: string;
    sourceObjectId: string;
    targetObjectId: string;
    sourceHandle: string | null;
    targetHandle: string | null;
  }) => void;
  onMoveEntity: (occurrenceId: string, position: { x: number; y: number }) => void;
  onPendingCardinalityChange: (cardinality: InformationCardinality) => void;
  onArrange?: (direction: "ltr" | "ttb") => void;
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
  onReconnectRelationship,
  onMoveEntity,
  onPendingCardinalityChange,
  onArrange,
}: Props) {
  const [nodes, setNodes] = useState<InformationEntityFlowNode[]>([]);

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
    () => {
      // Parallel relationships share an unordered pair key so they can be
      // routed on distinct lanes while each keeps its own id and direction.
      const grouped = new Map<string, InformationRelationship[]>();
      for (const relationship of model.relationships) {
        const key = [relationship.source_object_id, relationship.target_object_id].sort().join("|");
        const list = grouped.get(key) ?? [];
        list.push(relationship);
        grouped.set(key, list);
      }
      const laneByRelationship = new Map<string, { laneIndex: number; laneCount: number }>();
      for (const list of grouped.values()) {
        list.forEach((relationship, index) =>
          laneByRelationship.set(relationship.id, { laneIndex: index, laneCount: list.length }));
      }

      const centerByOccurrence = new Map(nodes.map((node) => [
        node.id,
        { x: node.position.x + ENTITY_HALF_WIDTH, y: node.position.y + ENTITY_HALF_HEIGHT },
      ]));

      return model.relationships.flatMap((relationship) => {
        const source = model.entities.find((entity) => entity.object_id === relationship.source_object_id);
        const target = model.entities.find((entity) => entity.object_id === relationship.target_object_id);
        if (!source || !target) return [];
        const sourceCenter = centerByOccurrence.get(source.occurrence_id)
          ?? { x: source.position.x + ENTITY_HALF_WIDTH, y: source.position.y + ENTITY_HALF_HEIGHT };
        const targetCenter = centerByOccurrence.get(target.occurrence_id)
          ?? { x: target.position.x + ENTITY_HALF_WIDTH, y: target.position.y + ENTITY_HALF_HEIGHT };
        const handles = resolveRelationshipHandles(relationship, sourceCenter, targetCenter);
        const lane = laneByRelationship.get(relationship.id) ?? { laneIndex: 0, laneCount: 1 };
        return [{
          id: relationship.id,
          source: source.occurrence_id,
          target: target.occurrence_id,
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          type: "informationRelationship" as const,
          selected: relationship.id === selectedRelationshipId,
          data: { relationship, ...lane },
        }];
      });
    },
    [model.relationships, model.entities, nodes, selectedRelationshipId],
  );

  function handleConnect(connection: Connection) {
    if (!editable || !connection.source || !connection.target) return;
    const sourceEntity = model.entities.find((entity) => entity.occurrence_id === connection.source);
    const targetEntity = model.entities.find((entity) => entity.occurrence_id === connection.target);
    if (!sourceEntity || !targetEntity || sourceEntity.object_id === targetEntity.object_id) return;
    onConnect(
      sourceEntity.object_id,
      targetEntity.object_id,
      connection.sourceHandle ?? null,
      connection.targetHandle ?? null,
    );
  }

  function handleReconnect(oldEdge: InformationRelationshipFlowEdge, connection: Connection) {
    if (!editable || !onReconnectRelationship) return;
    if (!connection.source || !connection.target) return;
    const sourceEntity = model.entities.find((entity) => entity.occurrence_id === connection.source);
    const targetEntity = model.entities.find((entity) => entity.occurrence_id === connection.target);
    if (!sourceEntity || !targetEntity || sourceEntity.object_id === targetEntity.object_id) return;
    onReconnectRelationship({
      relationshipId: oldEdge.id,
      sourceObjectId: sourceEntity.object_id,
      targetObjectId: targetEntity.object_id,
      sourceHandle: connection.sourceHandle ?? null,
      targetHandle: connection.targetHandle ?? null,
    });
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
        onReconnect={handleReconnect}
        onPaneClick={onPaneClick}
        nodesConnectable={editable}
        nodesDraggable={editable}
        edgesReconnectable={editable}
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
          {onArrange && (
            <span className="information-canvas-arrange" role="group" aria-label="Automatic arrangement">
              <button type="button" disabled={!editable} onClick={() => onArrange("ltr")}>
                Left → right
              </button>
              <button type="button" disabled={!editable} onClick={() => onArrange("ttb")}>
                Top → bottom
              </button>
            </span>
          )}
        </Panel>
      </ReactFlow>
    </div>
  );
}
