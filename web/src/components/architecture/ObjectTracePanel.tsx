import { useEffect, useState } from "react";

import {
  fetchObjectUsages,
  traceKindLabel,
  traceMembershipLabel,
  type ObjectTrace,
  type TraceObjectRef,
} from "../../workbench/workbenchTypes";
import TraceView from "./TraceView";

type Props = {
  workspaceId: string;
  stateId: string | null;
  objectId: string | null;
  onNavigate?: (node: TraceObjectRef) => void;
  onClose?: () => void;
};

export default function ObjectTracePanel({
  workspaceId,
  stateId,
  objectId,
  onNavigate,
  onClose,
}: Props) {
  const [trace, setTrace] = useState<ObjectTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showTrace, setShowTrace] = useState(false);

  useEffect(() => {
    setShowTrace(false);
  }, [objectId]);

  useEffect(() => {
    if (!stateId || !objectId) {
      setTrace(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchObjectUsages(workspaceId, stateId, objectId)
      .then((data) => {
        if (!cancelled) setTrace(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Trace failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, stateId, objectId]);

  if (!objectId) return null;

  return (
    <section className="object-trace-panel" aria-label="Object traceability">
      <header className="object-trace-header">
        <div>
          <p className="eyebrow">TRACEABILITY</p>
          <h4>Trace &amp; usages</h4>
        </div>
        {onClose && (
          <button type="button" className="secondary-button" aria-label="Close traceability" onClick={onClose}>
            ✕
          </button>
        )}
      </header>
      {loading && <p className="trace-status" role="status">Loading traceability…</p>}
      {error && <p className="trace-error" role="alert">{error}</p>}
      {!loading && !error && trace && (
        <>
          <p className="trace-summary">
            <span className={`trace-chip trace-kind-${trace.object.discipline ?? "cross"}`}>
              {traceKindLabel(trace.object.kind)}
            </span>
            <strong>{trace.object.name}</strong>
            <span className="trace-membership">{traceMembershipLabel(trace.object.state_membership)}</span>
          </p>
          {trace.disciplines.length > 0 && (
            <p className="trace-disciplines">
              Used by: {trace.disciplines.map((discipline) => discipline).join(", ")}
            </p>
          )}

          {trace.groups.length === 0 && <p className="muted">No linked objects yet.</p>}
          {trace.groups.map((group) => (
            <div key={group.label} className="trace-group">
              <p className="trace-group-label">{group.label}</p>
              <ul>
                {group.objects.map((node) => (
                  <li key={node.id}>
                    <button
                      type="button"
                      className="secondary-button trace-node-link"
                      onClick={() => onNavigate?.(node)}
                    >
                      {node.name}
                      <span className="trace-kind-tag">{traceKindLabel(node.kind)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {trace.physical_refs.length > 0 && (
            <div className="trace-group">
              <p className="trace-group-label">Physical implementation</p>
              <ul>
                {trace.physical_refs.map((node) => (
                  <li key={node.id}>
                    <span className="trace-static-node">
                      {node.name}
                      <span className="trace-kind-tag">{traceKindLabel(node.kind)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {trace.principles.length > 0 && (
            <div className="trace-group">
              <p className="trace-group-label">Governing principles</p>
              <ul>
                {trace.principles.map((node) => (
                  <li key={node.id}>
                    <span className="trace-static-node">{node.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {trace.tests.length > 0 && (
            <div className="trace-group">
              <p className="trace-group-label">Tests &amp; evidence</p>
              <ul>
                {trace.tests.map((node) => (
                  <li key={node.id}>
                    <span className="trace-static-node">{node.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            type="button"
            className="secondary-button"
            aria-expanded={showTrace}
            onClick={() => setShowTrace((value) => !value)}
          >
            {showTrace ? "Hide full trace" : "View full trace"}
          </button>
          {showTrace && stateId && (
            <TraceView
              workspaceId={workspaceId}
              stateId={stateId}
              objectId={objectId}
              onNavigate={onNavigate}
            />
          )}
          {trace.groups.length > 0 && (
            <p className="trace-footnote">
              Relationship kinds:{" "}
              {[...new Set(trace.groups.flatMap((group) => group.objects.map((node) => node.kind)))].length}{" "}
              object kinds linked. Derived edges are recomputed from canonical data.
            </p>
          )}
        </>
      )}
    </section>
  );
}
