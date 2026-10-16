import { MarkerType } from "@xyflow/react";
import { useMemo, useState } from "react";

import type { InformationLineage, InformationLineageNode } from "../informationModel";
import {
  LINEAGE_KIND_LABELS,
  filterLineage,
  lineageLayout,
  lineageNeighborhood,
} from "../informationViews";
import InformationProjectionCanvas from "./InformationProjectionCanvas";
import ProjectionEdge, { type ProjectionFlowEdge } from "./ProjectionEdge";
import ProjectionNode, { type ProjectionFlowNode, type ProjectionNodeTone } from "./ProjectionNode";

const nodeTypes = { informationProjection: ProjectionNode };
const edgeTypes = { informationProjectionEdge: ProjectionEdge };

const LINEAGE_TONES: Record<string, ProjectionNodeTone> = {
  information_entity: "logical",
  information_attribute: "attribute",
  catalog_system: "system",
  catalog_object: "catalog",
  catalog_field: "catalog",
  contract: "contract",
};

type Direction = "upstream" | "downstream" | "both";

type Props = {
  lineage: InformationLineage;
  selectedNodeId: string | null;
  onSelectNode: (node: InformationLineageNode | null) => void;
  onOpenCatalog: () => void;
  onOpenContract?: (contractId: string) => void;
};

export default function InformationLineageView({
  lineage,
  selectedNodeId,
  onSelectNode,
  onOpenCatalog,
  onOpenContract,
}: Props) {
  const [term, setTerm] = useState("");
  const [direction, setDirection] = useState<Direction>("both");
  const [highlight, setHighlight] = useState(false);

  const filtered = useMemo(() => filterLineage(lineage, term), [lineage, term]);
  const positions = useMemo(() => lineageLayout(filtered), [filtered]);
  const neighborhood = useMemo(
    () =>
      highlight && selectedNodeId
        ? lineageNeighborhood(lineage, selectedNodeId, direction)
        : null,
    [highlight, selectedNodeId, lineage, direction],
  );

  const unrealized = useMemo(() => {
    const realized = new Set(
      lineage.edges.filter((edge) => edge.relation === "realized as").map((edge) => edge.source),
    );
    return new Set(
      lineage.nodes
        .filter((node) => node.kind === "information_attribute" && !realized.has(node.id))
        .map((node) => node.id),
    );
  }, [lineage]);

  const focused = lineage.nodes.find((node) => node.id === selectedNodeId) ?? null;

  const nodes = useMemo<ProjectionFlowNode[]>(
    () =>
      filtered.nodes.map((node) => ({
        id: node.id,
        type: "informationProjection" as const,
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        selected: node.id === selectedNodeId,
        data: {
          label: node.name,
          kind: LINEAGE_KIND_LABELS[node.kind] ?? node.kind,
          detail: node.detail,
          meta: node.system_name ? `System: ${node.system_name}` : null,
          gap: unrealized.has(node.id),
          dimmed: neighborhood ? !neighborhood.has(node.id) : false,
          tone: LINEAGE_TONES[node.kind] ?? "catalog",
        },
      })),
    [filtered.nodes, positions, selectedNodeId, unrealized, neighborhood],
  );

  const edges = useMemo<ProjectionFlowEdge[]>(
    () =>
      filtered.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "informationProjectionEdge" as const,
        data: { relation: edge.relation },
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    [filtered.edges],
  );

  return (
    <div className="information-lineage-view">
      <InformationProjectionCanvas
        ariaLabel="Information lineage"
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(node) => onSelectNode(lineage.nodes.find((item) => item.id === node.id) ?? null)}
        onPaneClick={() => onSelectNode(null)}
        toolbar={
          <>
            <label className="information-lineage-filter">
              Filter
              <input
                type="search"
                value={term}
                placeholder="Entity or attribute"
                aria-label="Filter lineage by entity or attribute"
                onChange={(event) => setTerm(event.target.value)}
              />
            </label>
            <span className="information-canvas-count">
              {filtered.nodes.length} nodes · {filtered.edges.length} links
            </span>
          </>
        }
        emptyState={
          <>
            <h3>No proven lineage yet</h3>
            <p>
              Lineage appears once attributes are realized to catalog fields and used by contracts.
            </p>
          </>
        }
      />

      {focused && (
        <div className="information-lineage-focus" role="group" aria-label="Lineage focus">
          <span className="information-lineage-focus-name">
            <strong>{focused.name}</strong>
            <small>{LINEAGE_KIND_LABELS[focused.kind] ?? focused.kind}</small>
          </span>
          <span className="information-lineage-direction" role="group" aria-label="Traversal">
            {(["upstream", "downstream", "both"] as Direction[]).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={direction === value}
                onClick={() => setDirection(value)}
              >
                {value}
              </button>
            ))}
          </span>
          <button type="button" aria-pressed={highlight} onClick={() => setHighlight(!highlight)}>
            {highlight ? "Show all" : "Highlight path"}
          </button>
          {(focused.kind === "catalog_field" ||
            focused.kind === "catalog_system" ||
            focused.kind === "catalog_object") && (
            <button type="button" onClick={onOpenCatalog}>
              Open catalog
            </button>
          )}
          {focused.kind === "contract" && onOpenContract && focused.contract_id && (
            <button type="button" onClick={() => onOpenContract(focused.contract_id!)}>
              Open contract
            </button>
          )}
          <button type="button" onClick={() => onSelectNode(null)}>
            Clear
          </button>
        </div>
      )}

      {lineage.gaps.length > 0 && (
        <div className="information-lineage-gaps" role="status">
          <strong>Lineage ends</strong>
          <ul>
            {lineage.gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
