import React from "react";
import {
  architectureFieldKey,
  traceFieldLineage,
  type ArchitectureLineageDirection,
  type ArchitectureLineageHop,
  type EnterpriseArchitectureIndex,
} from "../../enterpriseArchitectureIndex";
import { transformationSummary } from "../../mappingGraphModel";

type Props = {
  index: EnterpriseArchitectureIndex | null;
  loading?: boolean;
  onOpenContract: (contractId: string) => void;
};

type LineageView = "diagram" | "paths";

function systemName(index: EnterpriseArchitectureIndex, id: string): string {
  return index.systemsById.get(id)?.name ?? `Missing system (${id})`;
}

function objectName(index: EnterpriseArchitectureIndex, id: string): string {
  return index.objectsById.get(id)?.displayName ?? `Missing object (${id})`;
}

function fieldName(index: EnterpriseArchitectureIndex, id: string): string {
  const field = index.fieldsById.get(id);
  return field ? `${field.displayName} · ${field.dataType}` : `Missing field (${id})`;
}

function hopStatus(hop: ArchitectureLineageHop): string {
  if (hop.issues.some((item) => item.severity === "Error")) return "Error";
  if (hop.issues.some((item) => item.severity === "Warning")) return "Review";
  return hop.validation?.status ?? "Incomplete";
}

function endpointLabel(
  index: EnterpriseArchitectureIndex,
  endpoint: ArchitectureLineageHop["sender"],
): string {
  return `${objectName(index, endpoint.objectId)} · ${fieldName(index, endpoint.fieldId)}`;
}

function HopDetails({
  index,
  hop,
  onOpenContract,
}: {
  index: EnterpriseArchitectureIndex;
  hop: ArchitectureLineageHop;
  onOpenContract: (contractId: string) => void;
}) {
  const contract = index.contractsById.get(hop.contractId);
  return (
    <details className="lineage-hop-details">
      <summary>Hop details</summary>
      <dl>
        <dt>Contract</dt>
        <dd>{contract?.name ?? hop.contractId}</dd>
        <dt>Phase</dt>
        <dd>{hop.phase.replace("-", " ")}</dd>
        <dt>Transformations</dt>
        <dd>{transformationSummary(hop.transformations)}</dd>
        <dt>Types</dt>
        <dd>{hop.senderType} → {hop.receiverType}</dd>
        <dt>Validation</dt>
        <dd>{hop.validation?.status ?? (hop.issues.length ? "Review required" : "Incomplete")}</dd>
      </dl>
      {hop.validation?.issue && <p>{hop.validation.issue}</p>}
      {hop.issues.length > 0 && (
        <ul>
          {hop.issues.map((issue, issueIndex) => (
            <li key={`${issue.code}:${issueIndex}`}>{issue.message}</li>
          ))}
        </ul>
      )}
      <button
        type="button"
        className="secondary-button"
        onClick={() => onOpenContract(hop.contractId)}
        disabled={!contract}
      >
        Open contract
      </button>
    </details>
  );
}

export default function FieldLineageExplorer({ index, loading = false, onOpenContract }: Props) {
  const [query, setQuery] = React.useState("");
  const [selectedFieldKey, setSelectedFieldKey] = React.useState("");
  const [direction, setDirection] = React.useState<ArchitectureLineageDirection>("both");
  const [depth, setDepth] = React.useState(3);
  const [view, setView] = React.useState<LineageView>("diagram");

  const fields = React.useMemo(() => {
    if (!index || !query.trim()) return [];
    const term = query.trim().toLocaleLowerCase();
    return [...index.fieldsById.values()].filter((field) => {
      const object = index.objectsById.get(field.objectId);
      const system = index.systemsById.get(field.systemId);
      return [
        field.displayName,
        field.technicalName,
        field.id,
        object?.displayName ?? "",
        object?.technicalName ?? "",
        system?.name ?? "",
      ].some((part) => part.toLocaleLowerCase().includes(term));
    }).slice(0, 30);
  }, [index, query]);

  const selected = React.useMemo(() => {
    if (!index || !selectedFieldKey) return null;
    const [systemId, objectId, fieldId] = JSON.parse(selectedFieldKey) as [string, string, string];
    const field = index.fieldsById.get(fieldId);
    if (!field || field.systemId !== systemId || field.objectId !== objectId) return null;
    return { systemId, objectId, fieldId, field };
  }, [index, selectedFieldKey]);

  const trace = React.useMemo(() => {
    if (!index || !selected) return null;
    return traceFieldLineage(index, selected, direction, depth);
  }, [depth, direction, index, selected]);

  const laneSystemIds = React.useMemo(() => {
    if (!index || !trace) return [];
    const involved = new Set(trace.fields.map((field) => field.systemId));
    return [...index.systemsById.keys()].filter((systemId) => involved.has(systemId));
  }, [index, trace]);
  const contractById = index?.contractsById;

  return (
    <section className="field-lineage-explorer" aria-label="Field lineage explorer">
      <header className="field-lineage-header">
        <div>
          <p className="eyebrow">READ-ONLY FIELD LINEAGE</p>
          <h3>Trace a field across contracts</h3>
          <p>Lineage connects exact catalog field IDs through configured contract mappings.</p>
        </div>
        <span className={`lineage-index-state ${loading ? "loading" : index?.state ?? "failed"}`} role="status">
          {loading && !index ? "Index loading" : `Index ${index?.state ?? "unavailable"}`}
        </span>
      </header>

      <div className="lineage-controls">
        <label>
          Search fields
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Field, object, system, or field ID"
            aria-label="Search fields by field, object, system, or ID"
            disabled={!index}
          />
        </label>
        <label>
          Direction
          <select
            value={direction}
            onChange={(event) => setDirection(event.target.value as ArchitectureLineageDirection)}
          >
            <option value="upstream">Upstream</option>
            <option value="downstream">Downstream</option>
            <option value="both">Both</option>
          </select>
        </label>
        <label>
          Maximum depth
          <select value={depth} onChange={(event) => setDepth(Number(event.target.value))}>
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>{value} {value === 1 ? "hop" : "hops"}</option>
            ))}
          </select>
        </label>
      </div>

      {query.trim() && (
        <div className="lineage-search-results" role="listbox" aria-label="Matching catalog fields">
          {fields.length === 0 ? (
            <p>No matching fields.</p>
          ) : fields.map((field) => {
            const key = architectureFieldKey(field.systemId, field.objectId, field.id);
            const chosen = key === selectedFieldKey;
            return (
              <button
                type="button"
                role="option"
                aria-selected={chosen}
                className={chosen ? "selected" : ""}
                key={key}
                onClick={() => {
                  setSelectedFieldKey(key);
                  setQuery("");
                }}
              >
                <strong>{field.displayName}</strong>
                <span>{objectName(index!, field.objectId)} · {systemName(index!, field.systemId)}</span>
                <small>{field.technicalName} · {field.dataType} · {field.id}</small>
              </button>
            );
          })}
          {fields.length === 30 && <small>Showing first 30 matches. Refine your search.</small>}
        </div>
      )}

      {index && index.state !== "complete" && (
        <aside className="lineage-index-diagnostics" role="status">
          <strong>Some tenant data could not be indexed.</strong>
          <span>{index.loadDiagnostics.length} diagnostic{index.loadDiagnostics.length === 1 ? "" : "s"}; lineage may be incomplete.</span>
          {index.loadDiagnostics.slice(0, 5).map((diagnostic, itemIndex) => (
            <small key={`${diagnostic.code}:${diagnostic.systemId ?? diagnostic.objectId ?? diagnostic.contractId ?? ""}:${itemIndex}`}>
              {diagnostic.message}
            </small>
          ))}
        </aside>
      )}

      {loading && !index ? (
        <div className="lineage-empty" role="status">
          <strong>Building the tenant-wide field index…</strong>
          <span>The existing Landscape is loaded. Lineage search will be available when all catalog fields have been indexed.</span>
        </div>
      ) : !selected ? (
        <div className="lineage-empty">
          <strong>Select a catalog field to begin.</strong>
          <span>Search results use the field’s system, object, and field IDs; matching names are never used to join lineage.</span>
        </div>
      ) : (
        <>
          <div className="lineage-selected-field">
            <span>Selected field</span>
            <strong>{selected.field.displayName}</strong>
            <small>
              {systemName(index!, selected.systemId)} · {objectName(index!, selected.objectId)}
              {" · "}{selected.field.dataType} · {selected.field.id}
            </small>
          </div>
          <div className="lineage-view-tabs" role="tablist" aria-label="Field lineage view">
            <button
              type="button"
              role="tab"
              aria-selected={view === "diagram"}
              onClick={() => setView("diagram")}
            >
              Trace Diagram
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "paths"}
              onClick={() => setView("paths")}
            >
              Lineage Paths ({trace?.hops.length ?? 0})
            </button>
          </div>

          {!trace?.hops.length ? (
            <div className="lineage-empty">
              <strong>No mapped fields are reachable in this direction and depth.</strong>
              <span>Try Both or increase the maximum depth. The enterprise field graph is not rendered by default.</span>
            </div>
          ) : view === "diagram" ? (
            <div className="lineage-trace-view">
              <div className="lineage-system-lanes" style={{ "--lineage-lane-count": laneSystemIds.length } as React.CSSProperties}>
                {laneSystemIds.map((systemId) => {
                  const laneFields = trace.fields
                    .filter((item) => item.systemId === systemId)
                    .sort((left, right) => left.depth - right.depth);
                  return (
                    <section className="lineage-system-lane" key={systemId}>
                      <h4>{systemName(index!, systemId)}</h4>
                      <div className="lineage-lane-fields">
                        {laneFields.map((item) => {
                          const field = index!.fieldsById.get(item.fieldId)!;
                          return (
                            <article
                              className={item.key === trace.selectedFieldKey ? "lineage-field-chip selected" : "lineage-field-chip"}
                              key={item.key}
                            >
                              <strong>{field.displayName}</strong>
                              <span>{objectName(index!, field.objectId)}</span>
                              <small>{field.dataType} · depth {item.depth}</small>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  );
                })}
              </div>
              <h4 className="lineage-subheading">Reachable contract hops</h4>
              <ol className="lineage-hop-list">
                {trace.hops.map(({ hop, depth: hopDepth, traversalDirection }) => (
                  <li key={hop.id}>
                    <span className="lineage-hop-depth">Hop {hopDepth}</span>
                    <div className="lineage-hop-route">
                      {traversalDirection === "upstream" ? (
                        <span><small>{systemName(index!, hop.receiver.systemId)}</small>{endpointLabel(index!, hop.receiver)}</span>
                      ) : (
                        <span><small>{systemName(index!, hop.sender.systemId)}</small>{endpointLabel(index!, hop.sender)}</span>
                      )}
                      <span className="lineage-hop-arrow" aria-label={traversalDirection}>
                        {traversalDirection === "upstream" ? "←" : "→"}
                      </span>
                      {traversalDirection === "upstream" ? (
                        <span><small>{systemName(index!, hop.sender.systemId)}</small>{endpointLabel(index!, hop.sender)}</span>
                      ) : (
                        <span><small>{systemName(index!, hop.receiver.systemId)}</small>{endpointLabel(index!, hop.receiver)}</span>
                      )}
                    </div>
                    <div className="lineage-hop-meta">
                      <span>{contractById?.get(hop.contractId)?.name ?? hop.contractId}</span>
                      <span>{hop.phase.replace("-", " ")}</span>
                      <span>{transformationSummary(hop.transformations)}</span>
                      <span>{hopStatus(hop)}</span>
                    </div>
                    <HopDetails index={index!} hop={hop} onOpenContract={onOpenContract} />
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <div className="lineage-path-table-wrap">
              <table className="lineage-path-table">
                <thead>
                  <tr>
                    <th scope="col">Sender field</th>
                    <th scope="col">Receiver field</th>
                    <th scope="col">Contract / phase</th>
                    <th scope="col">Transformations</th>
                    <th scope="col">Types / validation</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.hops.map(({ hop, depth: hopDepth }) => (
                    <tr key={hop.id}>
                      <td>{endpointLabel(index!, hop.sender)}<small>{systemName(index!, hop.sender.systemId)}</small></td>
                      <td>{endpointLabel(index!, hop.receiver)}<small>{systemName(index!, hop.receiver.systemId)}</small></td>
                      <td>
                        {contractById?.get(hop.contractId)?.name ?? hop.contractId}
                        <small>{hop.phase.replace("-", " ")} · hop {hopDepth}</small>
                        <button type="button" onClick={() => onOpenContract(hop.contractId)} disabled={!contractById?.has(hop.contractId)}>
                          Open contract
                        </button>
                      </td>
                      <td>{transformationSummary(hop.transformations)}</td>
                      <td>
                        {hop.senderType} → {hop.receiverType}
                        <small>{hopStatus(hop)}{hop.validation?.issue ? ` · ${hop.validation.issue}` : ""}</small>
                        {hop.issues.map((issue, issueIndex) => (
                          <small key={`${issue.code}:${issueIndex}`}>{issue.message}</small>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
