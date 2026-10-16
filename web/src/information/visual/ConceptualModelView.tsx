import { MarkerType } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { InformationConceptual } from "../informationModel";
import { conceptualLayout, type InformationLayoutPoint } from "../informationViews";
import InformationProjectionCanvas from "./InformationProjectionCanvas";
import ProjectionEdge, { type ProjectionFlowEdge } from "./ProjectionEdge";
import ProjectionNode, { type ProjectionFlowNode } from "./ProjectionNode";

const nodeTypes = { informationProjection: ProjectionNode };
const edgeTypes = { informationProjectionEdge: ProjectionEdge };

/** Manual concept layout persists per state for the session. */
const layoutStore = new Map<string, Record<string, InformationLayoutPoint>>();

export function resetConceptualLayout(stateId: string): void {
  layoutStore.delete(stateId);
}

type Props = {
  conceptual: InformationConceptual;
  stateId: string;
  selectedObjectId: string | null;
  onSelectConcept: (objectId: string) => void;
};

export default function ConceptualModelView({
  conceptual,
  stateId,
  selectedObjectId,
  onSelectConcept,
}: Props) {
  const { positions, edges: layoutEdges } = useMemo(
    () => conceptualLayout(conceptual),
    [conceptual],
  );
  const [manual, setManual] = useState<Record<string, InformationLayoutPoint>>(
    () => layoutStore.get(stateId) ?? {},
  );

  useEffect(() => {
    setManual(layoutStore.get(stateId) ?? {});
  }, [stateId]);

  const nodes = useMemo<ProjectionFlowNode[]>(
    () =>
      conceptual.concepts.map((concept) => ({
        id: concept.object_id,
        type: "informationProjection" as const,
        position: manual[concept.object_id] ?? positions.get(concept.object_id) ?? { x: 0, y: 0 },
        selected: concept.object_id === selectedObjectId,
        data: {
          label: concept.name,
          kind: "Concept",
          detail: concept.description,
          meta: concept.owner ? `Owner: ${concept.owner}` : null,
          tone: "concept" as const,
        },
      })),
    [conceptual.concepts, positions, manual, selectedObjectId],
  );

  const edges = useMemo<ProjectionFlowEdge[]>(
    () =>
      layoutEdges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "informationProjectionEdge" as const,
        data: { relation: edge.label },
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    [layoutEdges],
  );

  const arrange = useCallback(() => {
    resetConceptualLayout(stateId);
    setManual({});
  }, [stateId]);

  return (
    <InformationProjectionCanvas
      ariaLabel="Conceptual information model"
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      draggable
      onNodeClick={(node) => onSelectConcept(node.id)}
      onNodeDragStop={(id, position) => {
        setManual((current) => {
          const next = { ...current, [id]: position };
          layoutStore.set(stateId, next);
          return next;
        });
      }}
      toolbar={
        <>
          <span className="information-canvas-count">
            {conceptual.concepts.length} concepts · {conceptual.relationships.length} relationships
          </span>
          <button type="button" onClick={arrange}>
            Auto arrange
          </button>
          <span className="information-projection-hint">
            Business concepts only — no fields, types or schemas.
          </span>
        </>
      }
      emptyState={
        <>
          <h3>No business concepts yet</h3>
          <p>Concepts are derived from the entities in this state.</p>
        </>
      }
    />
  );
}
