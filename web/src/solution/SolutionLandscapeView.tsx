import { useMemo, type ReactNode } from "react";
import { MarkerType, type Viewport } from "@xyflow/react";

import SolutionCanvas from "./SolutionCanvas";
import SolutionEdge, { type SolutionFlowEdge } from "./SolutionEdge";
import SolutionLandscapeNode, {
  type SolutionLandscapeFlowNode,
} from "./nodes/SolutionLandscapeNode";
import {
  contractRoleSummary,
  isSymmetricRelationship,
  landscapeLayout,
  nodeWarnings,
  relationshipLabel,
} from "./solutionLandscapeModel";
import type { SolutionLandscape } from "./solutionModel";

const nodeTypes = { solutionLandscape: SolutionLandscapeNode };
const edgeTypes = { solutionEdge: SolutionEdge };
const NODE_WIDTH = 260;
const NODE_HEIGHT = 180;

type Props = {
  landscape: SolutionLandscape;
  stateName: string;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (solutionObjectId: string) => void;
  onOpenSolution: (solutionObjectId: string) => void;
  onSelectEdge: (relationshipId: string) => void;
  toolbar?: ReactNode;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
};

/**
 * The Solution Landscape canvas. Solution Boundaries are the only nodes; their
 * Contracts appear as summaries in the inspector rather than as graph nodes.
 * Positions come from a pure grid layout, so auto arrangement is deterministic.
 */
export default function SolutionLandscapeView({
  landscape,
  stateName,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onOpenSolution,
  onSelectEdge,
  toolbar,
  defaultViewport,
  onViewportChange,
}: Props) {
  const positions = useMemo(
    () => landscapeLayout(landscape.solutions.map((item) => item.solution_object_id)),
    [landscape.solutions],
  );

  const nodes = useMemo<SolutionLandscapeFlowNode[]>(
    () =>
      landscape.solutions.map((solution) => ({
        id: `solution:${solution.solution_object_id}`,
        type: "solutionLandscape" as const,
        position: positions.get(solution.solution_object_id) ?? { x: 0, y: 0 },
        draggable: false,
        selected: solution.solution_object_id === selectedNodeId,
        style: { width: NODE_WIDTH, minHeight: NODE_HEIGHT },
        data: {
          name: solution.name,
          owner: solution.owner,
          lifecycle: solution.lifecycle_stage,
          operational: solution.operational_status,
          componentCount: solution.component_count,
          memberCount: solution.member_count,
          contractRoleSummary: contractRoleSummary(solution),
          evidenceCount: solution.evidence_count,
          warningCount: nodeWarnings(landscape, solution.solution_object_id).length,
          stateName,
          objectId: solution.solution_object_id,
          editable: false,
        },
      })),
    [landscape, positions, selectedNodeId, stateName],
  );

  const edges = useMemo<SolutionFlowEdge[]>(
    () =>
      landscape.relationships.map((relationship) => ({
        id: relationship.id,
        source: `solution:${relationship.source_object_id}`,
        target: `solution:${relationship.target_object_id}`,
        type: "solutionEdge" as const,
        selected: relationship.id === selectedEdgeId,
        markerStart: isSymmetricRelationship(relationship.relationship_type)
          ? { type: MarkerType.ArrowClosed }
          : undefined,
        markerEnd: { type: MarkerType.ArrowClosed },
        label: relationshipLabel(relationship.relationship_type),
        data: {
          kind: relationship.relationship_type,
          label: relationshipLabel(relationship.relationship_type),
        },
      })),
    [landscape.relationships, selectedEdgeId],
  );

  const nodeById = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])),
    [nodes],
  );

  return (
    <SolutionCanvas
      ariaLabel="Solution landscape"
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      editable={false}
      onNodeClick={(_event, node) => {
        const found = nodeById.get(node.id);
        if (found) onSelectNode(found.data.objectId);
      }}
      onNodeDoubleClick={(_event, node) => {
        const found = nodeById.get(node.id);
        if (found) onOpenSolution(found.data.objectId);
      }}
      onEdgeClick={(_event, edge) => onSelectEdge(edge.id)}
      onNodeDragStop={() => undefined}
      onPaneClick={() => onSelectNode("")}
      emptyState={
        <>
          <h3>No solutions in this state</h3>
          <p>
            Create a solution in Context, then return here to see ownership, dependencies and
            contract associations across the portfolio.
          </p>
        </>
      }
      showEmpty={landscape.solutions.length === 0}
      defaultViewport={defaultViewport}
      onViewportChange={onViewportChange}
      toolbar={toolbar}
    />
  );
}
