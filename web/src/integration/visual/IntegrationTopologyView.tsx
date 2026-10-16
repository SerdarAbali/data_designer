import { MarkerType, type Viewport } from "@xyflow/react";
import { useMemo } from "react";

import {
  PATTERN_LABELS,
  STATUS_LABELS,
  type IntegrationContractSummary,
  type IntegrationLandscape,
} from "../integrationDesignModel";
import {
  integrationTopology,
  layeredLayout,
  resilienceItems,
  RESPONSIBILITY_LABELS,
  RESILIENCE_NOTE,
  type IntegrationTopologyNode,
} from "../integrationViews";
import IntegrationCanvas from "./IntegrationCanvas";
import IntegrationEdge, { type IntegrationFlowEdge } from "./IntegrationEdge";
import IntegrationNode, { type IntegrationFlowNode, type IntegrationNodeTone } from "./IntegrationNode";

const nodeTypes = { integrationNode: IntegrationNode };
const edgeTypes = { integrationEdge: IntegrationEdge };

const KIND_LABELS: Record<string, string> = {
  system: "System",
  runtime: "Runtime",
  solution: "Component",
  interface: "Interface",
  contract: "Contract",
};

const TONES: Record<string, IntegrationNodeTone> = {
  system: "system",
  runtime: "runtime",
  solution: "solution",
  interface: "interface",
  contract: "contract",
};

type Props = {
  landscape: IntegrationLandscape;
  selectedRefId: string | null;
  onSelectNode: (node: IntegrationTopologyNode) => void;
  onOpenContract: (contractId: string) => void;
  onOpenCatalog?: () => void;
  manualPositions: Record<string, { x: number; y: number }>;
  onMoveNode: (id: string, position: { x: number; y: number }) => void;
  onArrange: () => void;
  showResilience: boolean;
  onToggleResilience: () => void;
  viewport?: Viewport;
  onViewportChange: (viewport: Viewport) => void;
};

function detailFor(node: IntegrationTopologyNode): string | null {
  if (node.kind === "contract") {
    return node.pattern ? PATTERN_LABELS[node.pattern as keyof typeof PATTERN_LABELS] ?? node.pattern : null;
  }
  if (node.kind === "system") return node.subtitle;
  if (node.kind === "runtime") return "Integration runtime";
  if (node.kind === "interface") return node.detail;
  return node.subtitle;
}

export default function IntegrationTopologyView({
  landscape,
  selectedRefId,
  onSelectNode,
  onOpenContract,
  onOpenCatalog,
  manualPositions,
  onMoveNode,
  onArrange,
  showResilience,
  onToggleResilience,
  viewport,
  onViewportChange,
}: Props) {
  const topology = useMemo(() => integrationTopology(landscape), [landscape]);
  const positions = useMemo(
    () =>
      layeredLayout(
        topology.nodes.map((node) => node.id),
        topology.edges.map((edge) => ({ source: edge.source, target: edge.target })),
        300,
        120,
      ),
    [topology],
  );

  const nodeById = useMemo(
    () => new Map(topology.nodes.map((node) => [node.id, node])),
    [topology.nodes],
  );

  const nodes = useMemo<IntegrationFlowNode[]>(
    () =>
      topology.nodes.map((node) => {
        const manual = manualPositions[node.id];
        return {
          id: node.id,
          type: "integrationNode" as const,
          position: manual ?? positions.get(node.id) ?? { x: 0, y: 0 },
          selected: node.refId === selectedRefId,
          data: {
            label: node.name,
            kind: KIND_LABELS[node.kind] ?? node.kind,
            detail: detailFor(node),
            meta: node.kind === "contract" && node.status ? STATUS_LABELS[node.status] ?? node.status : null,
            badge: node.kind === "interface" ? node.badge : null,
            tone: TONES[node.kind] ?? "system",
            mediated: node.mediated,
          },
        };
      }),
    [topology.nodes, manualPositions, positions, selectedRefId],
  );

  const edges = useMemo<IntegrationFlowEdge[]>(
    () =>
      topology.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "integrationEdge" as const,
        markerEnd: { type: MarkerType.ArrowClosed },
        data: { relation: edge.relation },
      })),
    [topology.edges],
  );

  const contracts = useMemo(
    () => new Map(landscape.contracts.map((contract) => [contract.id, contract])),
    [landscape.contracts],
  );

  return (
    <div className="integration-topology-view">
      <IntegrationCanvas
        ariaLabel="Integration landscape topology"
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        draggable
        defaultViewport={viewport}
        onViewportChange={onViewportChange}
        onNodeClick={(node) => {
          const topologyNode = nodeById.get(node.id);
          if (topologyNode) onSelectNode(topologyNode);
        }}
        onNodeDoubleClick={(node) => {
          const topologyNode = nodeById.get(node.id);
          if (topologyNode?.kind === "contract") onOpenContract(topologyNode.refId);
        }}
        onNodeDragStop={onMoveNode}
        toolbar={
          <>
            <span className="integration-canvas-legend" role="group" aria-label="Node legend">
              {(["system", "runtime", "solution", "interface", "contract"] as const).map((tone) => (
                <span key={tone} className={`integration-legend-item tone-${tone}`}>
                  {KIND_LABELS[tone]}
                </span>
              ))}
            </span>
            <span className="integration-canvas-count">
              {topology.nodes.length} nodes · {topology.edges.length} links
            </span>
            <button type="button" onClick={onArrange}>
              Auto arrange
            </button>
            <button type="button" aria-pressed={showResilience} onClick={onToggleResilience}>
              {showResilience ? "Hide resilience" : "Resilience overlay"}
            </button>
            {onOpenCatalog && (
              <button type="button" onClick={onOpenCatalog}>
                Open catalog
              </button>
            )}
          </>
        }
        emptyState={
          <>
            <h3>No integration landscape yet</h3>
            <p>
              Create an integration contract in Mapping &amp; Tests, then return here to link
              interfaces and record its operating properties.
            </p>
          </>
        }
      />

      {showResilience && (
        <ResilienceOverlay contracts={landscape.contracts} byId={contracts} />
      )}

      {onOpenCatalog && topology.nodes.length > 0 && (
        <p className="integration-topology-hint">
          Double-click a contract to open it in Mapping &amp; Tests. Select any node to inspect it.
        </p>
      )}
    </div>
  );
}

function ResilienceOverlay({
  contracts,
  byId,
}: {
  contracts: IntegrationContractSummary[];
  byId: Map<string, IntegrationContractSummary>;
}) {
  if (contracts.length === 0) return null;
  return (
    <section className="integration-resilience" aria-label="Architecture resilience">
      <header>
        <strong>Architecture resilience</strong>
        <span className="integration-resilience-note">{RESILIENCE_NOTE}</span>
      </header>
      <div className="integration-resilience-grid">
        {contracts.map((contract) => (
          <article key={contract.id} className="integration-resilience-card">
            <div className="integration-card-head">
              <strong>{byId.get(contract.id)?.name ?? contract.name}</strong>
              <span className="integration-badge">
                {contract.pattern ? PATTERN_LABELS[contract.pattern] ?? contract.pattern : "Unspecified"}
              </span>
            </div>
            <dl className="integration-resilience-list">
              {resilienceItems(contract).map((item) => (
                <div key={item.key} className={`integration-resilience-row${item.configured ? "" : " muted"}`}>
                  <dt>{item.label}</dt>
                  <dd>
                    <span>{item.value}</span>
                    <em>{RESPONSIBILITY_LABELS[item.responsibility]}</em>
                  </dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
