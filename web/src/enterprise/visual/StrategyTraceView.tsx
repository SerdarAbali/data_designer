import { useMemo, type ReactNode } from "react";
import { MarkerType, type Viewport } from "@xyflow/react";

import type { ArchitectureState } from "../../architectureTypes";
import { useHoverFocus } from "../../components/architecture/useHoverFocus";
import type {
  EnterpriseApplication,
  EnterpriseModel,
  StrategyTrace,
} from "../enterpriseModel";
import {
  strategyTraceGraph,
  type EnterpriseTraceNode,
  type Point,
} from "./enterpriseCanvasModel";
import EnterpriseCanvas from "./EnterpriseCanvas";
import EnterpriseEdge, { type EnterpriseFlowEdge } from "./EnterpriseEdge";
import EnterpriseObjectNode, { type EnterpriseObjectFlowNode } from "./EnterpriseObjectNode";
import EnterpriseApplicationNode, { type EnterpriseApplicationFlowNode } from "./EnterpriseApplicationNode";

const nodeTypes = { enterpriseObject: EnterpriseObjectNode, enterpriseApplication: EnterpriseApplicationNode };
const edgeTypes = { enterpriseEdge: EnterpriseEdge };

type TraceFlowNode = EnterpriseObjectFlowNode | EnterpriseApplicationFlowNode;

type Props = {
  model: EnterpriseModel;
  strategyTrace: StrategyTrace;
  state: ArchitectureState | null;
  editable: boolean;
  selectedObjectId: string | null;
  onSelectObject: (objectId: string) => void;
  onSelectApplication: (application: EnterpriseApplication) => void;
  onMoveObject: (occurrenceId: string, position: Point) => void;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
  toolbar?: ReactNode;
};

const KIND_LABELS: Record<string, string> = {
  goal: "Goal",
  requirement: "Requirement",
  capability: "Capability",
  process: "Process",
  principle: "Principle",
  role: "Role",
};

export default function StrategyTraceView({
  model,
  strategyTrace,
  state,
  editable,
  selectedObjectId,
  onSelectObject,
  onSelectApplication,
  onMoveObject,
  defaultViewport,
  onViewportChange,
  toolbar,
}: Props) {
  const graph = useMemo(
    () => strategyTraceGraph(model, strategyTrace, state),
    [model, strategyTrace, state],
  );

  // Dim everything that is not part of the connection under the pointer, so a
  // trace can be followed without moving the canvas.
  const focusableEdges = useMemo(
    () => graph.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })),
    [graph.edges],
  );
  const hover = useHoverFocus(focusableEdges);
  const focus = hover.focus;

  const occById = useMemo(() => {
    const map = new Map<string, string>();
    for (const node of graph.nodes) map.set(node.id, node.occurrenceId);
    return map;
  }, [graph.nodes]);

  const appById = useMemo(
    () => new Map(model.applications.map((app) => [app.object_id, app])),
    [model.applications],
  );

  const nodes = useMemo<TraceFlowNode[]>(
    () =>
      graph.nodes.map((node: EnterpriseTraceNode) => {
        if (node.kind === "application") {
          return {
            id: node.id,
            type: "enterpriseApplication" as const,
            position: node.position,
            draggable: false,
            className: focus && !focus.nodes.has(node.id) ? "dimmed" : undefined,
            data: { name: node.name, applicationKind: node.applicationKind ?? "system" },
          };
        }
        return {
          id: node.id,
          type: "enterpriseObject" as const,
          position: node.position,
          draggable: editable && Boolean(node.occurrenceId),
          selected: node.objectId === selectedObjectId,
          className: focus && !focus.nodes.has(node.id) ? "dimmed" : undefined,
          data: {
            name: node.name,
            kind: node.kind,
            kindLabel: KIND_LABELS[node.kind] ?? node.kind,
            owner: node.owner ?? null,
            description: node.description ?? null,
            processType: node.processType,
            gap: node.gap,
            editable,
          },
        } as EnterpriseObjectFlowNode;
      }),
    [graph.nodes, focus, editable, selectedObjectId],
  );

  const edges = useMemo<EnterpriseFlowEdge[]>(
    () =>
      graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "enterpriseEdge" as const,
        markerEnd: { type: MarkerType.ArrowClosed },
        data: {
          type: edge.type,
          label: edge.label,
          emphasized: hover.target.edge === edge.id,
          dimmed: focus ? !focus.edges.has(edge.id) : false,
        },
      })),
    [graph.edges, focus, hover.target.edge],
  );

  return (
    <div className="enterprise-visual" aria-label="Strategy trace">
      <EnterpriseCanvas
        ariaLabel="Strategy trace diagram"
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        editable={editable}
        onNodeClick={(_event, node) => {
          if (node.type === "enterpriseApplication") {
            const app = appById.get(node.id);
            if (app) onSelectApplication(app);
          } else {
            onSelectObject(node.id);
          }
        }}
        onNodeMouseEnter={hover.onNodeEnter}
        onNodeMouseLeave={hover.onLeave}
        onEdgeMouseEnter={hover.onEdgeEnter}
        onEdgeMouseLeave={hover.onLeave}
        onNodeDragStop={(_event, node) => {
          if (!editable || node.type !== "enterpriseObject") return;
          const occurrenceId = occById.get(node.id);
          if (occurrenceId) onMoveObject(occurrenceId, { x: node.position.x, y: node.position.y });
        }}
        defaultViewport={defaultViewport}
        onViewportChange={onViewportChange}
        emptyState={
          <>
            <h3>No goals recorded yet</h3>
            <p>Add a goal to begin the strategy-to-execution trace.</p>
          </>
        }
        toolbar={toolbar}
      />
      {graph.gaps.length > 0 && (
        <section className="enterprise-gaps-block enterprise-visual-gaps">
          <strong>Trace gaps</strong>
          <ul>
            {graph.gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
