import React from "react";
import { transformationLabel } from "../../mappingGraphModel";

type CatalogField = {
  id: string;
  name: string;
  data_type: string;
};

type GraphNode = {
  id: string;
  type: string;
  config: Record<string, unknown>;
};

type GraphEdge = {
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
};

type Integration = {
  id: string;
  name: string;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  response_graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  interaction_type: "ONE_WAY" | "REQUEST_RESPONSE" | "ASYNC_CALLBACK";
};

type SimulationRow = {
  outcome: string;
  targetValues: Record<string, unknown>;
  errors: { nodeId: string | null }[];
};
type SimulationResult = {
  summary: { total: number; ok: number; skipped: number; failed: number };
  responseSummary: { total: number; ok: number; skipped: number; failed: number };
  rows: SimulationRow[];
  requestOutcomes: SimulationRow[];
  responseOutcomes: SimulationRow[];
};

type MappingRow = {
  source?: CatalogField;
  target: CatalogField;
  transformations: { id: string; label: string }[];
};

type Props = {
  integration: Integration;
  sourceSystemName: string;
  targetSystemName: string;
  sourceFields: CatalogField[];
  targetFields: CatalogField[];
  simulation: SimulationResult | null;
  loading: boolean;
  error: string;
  onClose: () => void;
  onOpenMapper: () => void;
};

function nodeLabel(node: GraphNode): string {
  return transformationLabel(node.type, node.config);
}

function collectMappings(
  graph: Integration["graph"],
  sourceFields: CatalogField[],
  targetFields: CatalogField[],
): MappingRow[] {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, GraphEdge[]>();
  for (const edge of edges) {
    const list = incoming.get(edge.targetNodeId) ?? [];
    list.push(edge);
    incoming.set(edge.targetNodeId, list);
  }

  function walk(
    nodeId: string,
    outputPortId: string,
    visited: Set<string>,
  ): { sourceId: string; transformations: { id: string; label: string }[] }[] {
    const node = nodeById.get(nodeId);
    if (!node || visited.has(nodeId)) return [];
    if (node.type === "source" && outputPortId.startsWith("field:")) {
      return [{ sourceId: outputPortId.slice("field:".length), transformations: [] }];
    }
    if (node.type === "source" || node.type === "target") return [];

    const nextVisited = new Set(visited).add(nodeId);
    const upstream = (incoming.get(nodeId) ?? []).flatMap((edge) =>
      walk(edge.sourceNodeId, edge.sourcePortId, nextVisited),
    );
    return upstream.map((path) => ({
      sourceId: path.sourceId,
      transformations: [...path.transformations, { id: node.id, label: nodeLabel(node) }],
    }));
  }

  const targetNode = nodes.find((node) => node.type === "target");
  if (!targetNode) return targetFields.map((target) => ({ target, transformations: [] }));

  const sourceById = new Map(sourceFields.map((field) => [field.id, field]));
  const rows: MappingRow[] = [];
  const mappedTargetIds = new Set<string>();
  for (const target of targetFields) {
    const paths = (incoming.get(targetNode.id) ?? [])
      .filter((edge) => edge.targetPortId === `field:${target.id}`)
      .flatMap((edge) => walk(edge.sourceNodeId, edge.sourcePortId, new Set()));
    for (const path of paths) {
      rows.push({
        source: sourceById.get(path.sourceId),
        target,
        transformations: path.transformations,
      });
      mappedTargetIds.add(target.id);
    }
    if (paths.length === 0) rows.push({ target, transformations: [] });
  }
  return rows.filter((row) => !row.source || mappedTargetIds.has(row.target.id));
}

function healthFor(
  row: MappingRow,
  simulation: SimulationResult | null,
  error: string,
  response: boolean,
): "OK" | "Error" | "No data" {
  if (!row.source) return "No data";
  if (error) return "Error";
  const summary = response ? simulation?.responseSummary : simulation?.summary;
  const outcomes = response
    ? simulation?.responseOutcomes ?? []
    : simulation?.requestOutcomes ?? [];
  if (!simulation || summary?.total === 0) return "No data";
  const nodeIds = new Set(row.transformations.map((item) => item.id));
  const hasRelevantFailure = outcomes.some((result) =>
    result.errors.some((error) => error.nodeId !== null && nodeIds.has(error.nodeId)),
  );
  const hasOutput = outcomes.some((result) =>
    Object.hasOwn(result.targetValues, row.target.id),
  );
  return hasRelevantFailure || !hasOutput ? "Error" : "OK";
}

export default function FieldMappingDrawer({
  integration,
  sourceSystemName,
  targetSystemName,
  sourceFields,
  targetFields,
  simulation,
  loading,
  error,
  onClose,
  onOpenMapper,
}: Props) {
  const drawerRef = React.useRef<HTMLElement>(null);
  const [expanded, setExpanded] = React.useState(false);
  const mappings = React.useMemo(
    () => collectMappings(integration.graph, sourceFields, targetFields),
    [integration.graph, sourceFields, targetFields],
  );
  const responseMappings = React.useMemo(
    () => collectMappings(integration.response_graph, targetFields, sourceFields),
    [integration.response_graph, sourceFields, targetFields],
  );
  const renderTable = (
    title: string,
    rows: MappingRow[],
    response: boolean,
  ) => (
    <section className="landscape-mapping-phase" aria-label={title}>
      <h3>{title}</h3>
      <div className="landscape-mapping-table-wrap">
        <table className="landscape-mapping-table">
          <thead>
            <tr>
              <th scope="col">Source field</th>
              <th scope="col">Transformation</th>
              <th scope="col">Target field</th>
              <th scope="col">Sample test result</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const health = healthFor(row, simulation, error, response);
              return (
                <tr key={`${row.target.id}:${row.source?.id ?? "unmapped"}:${index}`}>
                  <td>
                    {row.source ? (
                      <><strong>{row.source.name}</strong><small>{row.source.data_type}</small></>
                    ) : <span className="landscape-unmapped">Not mapped</span>}
                  </td>
                  <td>
                    {row.transformations.length
                      ? row.transformations.map((item) => item.label).join(" → ")
                      : row.source ? "Direct Edge" : "—"}
                  </td>
                  <td><strong>{row.target.name}</strong><small>{row.target.data_type}</small></td>
                  <td>
                    <span className={`landscape-mapping-health ${health.toLowerCase().replace(" ", "-")}`}>
                      {health}
                    </span>
                  </td>
                </tr>
              );
            })}
            {!rows.length && (
              <tr><td colSpan={4} className="landscape-mapping-empty">No fields are available for this mapping.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !drawerRef.current?.contains(event.target)) onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [onClose]);

  return (
    <section
      ref={drawerRef}
      className={`landscape-mapping-drawer${expanded ? " expanded" : ""}`}
      aria-label="Contract field mapping matrix"
      aria-live="polite"
    >
      <header className="landscape-mapping-header">
        <button
          type="button"
          className="landscape-drawer-toggle"
          aria-label={expanded ? "Reduce mapping drawer height" : "Expand mapping drawer height"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "⌄" : "⌃"}
        </button>
        <div className="landscape-mapping-title">
          <strong>
            {sourceSystemName} {integration.interaction_type === "ONE_WAY" ? "→" : "↔"} {targetSystemName}
          </strong>
          <small>
            {integration.name} · {mappings.filter((row) => row.source).length} request mappings
            {integration.interaction_type !== "ONE_WAY"
              ? ` · ${responseMappings.filter((row) => row.source).length} response mappings`
              : ""}
          </small>
        </div>
        <button type="button" className="secondary-button" onClick={onOpenMapper}>
          Open Contract Designer ↗
        </button>
        <button type="button" className="landscape-drawer-close" aria-label="Close mapping drawer" onClick={onClose}>
          ×
        </button>
      </header>
      <div className="landscape-mapping-content">
        {error && <p className="landscape-mapping-error" role="alert">{error}</p>}
        {loading ? (
          <p className="landscape-mapping-loading" role="status">Loading field mappings and sample test results…</p>
        ) : (
          <>
            {renderTable("Request Mappings", mappings, false)}
            {integration.interaction_type !== "ONE_WAY"
              && renderTable("Response Return Mappings", responseMappings, true)}
          </>
        )}
      </div>
    </section>
  );
}
