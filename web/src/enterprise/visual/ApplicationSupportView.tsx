import { useMemo, useState } from "react";
import { MarkerType, type Viewport } from "@xyflow/react";

import type {
  ApplicationSupport,
  EnterpriseApplication,
  EnterpriseModel,
} from "../enterpriseModel";
import { applicationSupportGraph, applicationSupportMatrix } from "./enterpriseCanvasModel";
import EnterpriseCanvas from "./EnterpriseCanvas";
import EnterpriseEdge, { type EnterpriseFlowEdge } from "./EnterpriseEdge";
import EnterpriseObjectNode, { type EnterpriseObjectFlowNode } from "./EnterpriseObjectNode";
import EnterpriseApplicationNode, { type EnterpriseApplicationFlowNode } from "./EnterpriseApplicationNode";

const nodeTypes = { enterpriseObject: EnterpriseObjectNode, enterpriseApplication: EnterpriseApplicationNode };
const edgeTypes = { enterpriseEdge: EnterpriseEdge };

const KIND_LABELS: Record<string, string> = {
  goal: "Goal",
  requirement: "Requirement",
  capability: "Capability",
  process: "Process",
  principle: "Principle",
  role: "Role",
};

type Props = {
  model: EnterpriseModel;
  applicationSupport: ApplicationSupport;
  selectedObjectId: string | null;
  onSelectObject: (objectId: string) => void;
  onSelectApplication: (application: EnterpriseApplication) => void;
  defaultViewport?: Viewport;
  onViewportChange?: (viewport: Viewport) => void;
};

export default function ApplicationSupportView({
  model,
  applicationSupport,
  selectedObjectId,
  onSelectObject,
  onSelectApplication,
  defaultViewport,
  onViewportChange,
}: Props) {
  const [mode, setMode] = useState<"graph" | "matrix">("graph");
  const graph = useMemo(() => applicationSupportGraph(model), [model]);
  const matrix = useMemo(() => applicationSupportMatrix(applicationSupport), [applicationSupport]);

  const appById = useMemo(
    () => new Map(model.applications.map((app) => [app.object_id, app])),
    [model.applications],
  );

  const nodes = useMemo<(EnterpriseObjectFlowNode | EnterpriseApplicationFlowNode)[]>(
    () =>
      graph.nodes.map((node) => {
        if (node.kind === "application") {
          return {
            id: node.id,
            type: "enterpriseApplication" as const,
            position: node.position,
            draggable: false,
            data: { name: node.name, applicationKind: node.applicationKind ?? "system" },
          };
        }
        return {
          id: node.id,
          type: "enterpriseObject" as const,
          position: node.position,
          draggable: false,
          selected: node.id === selectedObjectId,
          data: {
            name: node.name,
            kind: node.kind,
            kindLabel: KIND_LABELS[node.kind] ?? node.kind,
            owner: null,
            description: node.description ?? null,
            processType: null,
            gap: null,
            editable: false,
          },
        } as EnterpriseObjectFlowNode;
      }),
    [graph.nodes, selectedObjectId],
  );

  const edges = useMemo<EnterpriseFlowEdge[]>(
    () =>
      graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "enterpriseEdge" as const,
        markerEnd: { type: MarkerType.ArrowClosed },
        data: { type: edge.type, label: edge.label },
      })),
    [graph.edges],
  );

  const columns = [
    ...matrix.capabilities.map((item) => ({ ...item, kind: "capability" as const })),
    ...matrix.processes.map((item) => ({ ...item, kind: "process" as const })),
    ...matrix.requirements.map((item) => ({ ...item, kind: "requirement" as const })),
  ];

  function supportsCell(applicationId: string, objectId: string, kind: string): boolean {
    if (kind === "requirement") return matrix.satisfied.get(applicationId)?.has(objectId) ?? false;
    return matrix.supported.get(applicationId)?.has(objectId) ?? false;
  }

  return (
    <div className="enterprise-app-support" aria-label="Application support map">
      <div className="enterprise-overlay-toggles" role="group" aria-label="Application support mode">
        <button
          type="button"
          className={mode === "graph" ? "active" : ""}
          aria-pressed={mode === "graph"}
          onClick={() => setMode("graph")}
        >
          Graph
        </button>
        <button
          type="button"
          className={mode === "matrix" ? "active" : ""}
          aria-pressed={mode === "matrix"}
          onClick={() => setMode("matrix")}
        >
          Matrix
        </button>
      </div>

      {mode === "graph" ? (
        <div className="enterprise-visual">
          <EnterpriseCanvas
            ariaLabel="Application support graph"
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            editable={false}
            onNodeClick={(_event, node) => {
              if (node.type === "enterpriseApplication") {
                const app = appById.get(node.id);
                if (app) onSelectApplication(app);
              } else {
                onSelectObject(node.id);
              }
            }}
            defaultViewport={defaultViewport}
            onViewportChange={onViewportChange}
            emptyState={
              <>
                <h3>No support relationships recorded</h3>
                <p>Link applications to capabilities, processes or requirements.</p>
              </>
            }
          />
        </div>
      ) : (
        <div className="enterprise-matrix">
          {matrix.applications.length === 0 ? (
            <p className="architecture-topbar-hint">No applications available.</p>
          ) : columns.length === 0 ? (
            <p className="architecture-topbar-hint">
              No capabilities, processes or requirements are linked to any application.
            </p>
          ) : (
            <table className="enterprise-matrix-table">
              <thead>
                <tr>
                  <th>Application</th>
                  {columns.map((column) => (
                    <th key={`${column.kind}-${column.object_id}`} title={column.kind}>
                      <button type="button" className="enterprise-link-endpoint" onClick={() => onSelectObject(column.object_id)}>
                        {column.name}
                        <small> · {column.kind}</small>
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.applications.map((application) => (
                  <tr key={application.object_id}>
                    <th scope="row">
                      <button type="button" className="enterprise-link-endpoint" onClick={() => onSelectApplication(application)}>
                        {application.name}
                        <small> · {application.kind}</small>
                      </button>
                    </th>
                    {columns.map((column) => (
                      <td key={`${column.kind}-${column.object_id}`}>
                        {supportsCell(application.object_id, column.object_id, column.kind) ? "✓" : ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
