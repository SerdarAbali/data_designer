import { useEffect, useMemo, useState } from "react";

import {
  fetchTrace,
  traceKindLabel,
  traceMembershipLabel,
  traceRelationshipLabel,
  type TraceDirection,
  type TraceObjectRef,
  type TraceResult,
} from "../../workbench/workbenchTypes";

type Props = {
  workspaceId: string;
  stateId: string;
  objectId: string;
  onNavigate?: (node: TraceObjectRef) => void;
};

export default function TraceView({ workspaceId, stateId, objectId, onNavigate }: Props) {
  const [direction, setDirection] = useState<TraceDirection>("both");
  const [depth, setDepth] = useState(3);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchTrace(workspaceId, stateId, objectId, direction, depth)
      .then((data) => {
        if (!cancelled) setResult(data);
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
  }, [workspaceId, stateId, objectId, direction, depth]);

  const byId = useMemo(() => {
    const map = new Map<string, TraceObjectRef>();
    for (const node of result?.nodes ?? []) map.set(node.id, node);
    return map;
  }, [result]);

  const grouped = useMemo(() => {
    const buckets = new Map<number, TraceObjectRef[]>();
    for (const node of result?.nodes ?? []) {
      const level = result?.depths[node.id] ?? 0;
      const bucket = buckets.get(level) ?? [];
      bucket.push(node);
      buckets.set(level, bucket);
    }
    return [...buckets.entries()].sort((a, b) => a[0] - b[0]);
  }, [result]);

  return (
    <div className="trace-view" aria-label="Trace chain">
      <div className="trace-controls">
        <label>
          Direction
          <select
            aria-label="Trace direction"
            value={direction}
            onChange={(event) => setDirection(event.target.value as TraceDirection)}
          >
            <option value="both">Both</option>
            <option value="outgoing">Downstream</option>
            <option value="incoming">Upstream</option>
          </select>
        </label>
        <label>
          Depth
          <input
            aria-label="Trace depth"
            type="number"
            min={1}
            max={8}
            value={depth}
            onChange={(event) => setDepth(Math.min(8, Math.max(1, Number(event.target.value) || 1)))}
          />
        </label>
      </div>
      {loading && <p className="trace-status" role="status">Tracing…</p>}
      {error && <p className="trace-error" role="alert">{error}</p>}
      {!loading && !error && result && (
        <>
          <ol className="trace-levels">
            {grouped.map(([level, nodes]) => (
              <li key={level}>
                <p className="trace-level-label">
                  {level === 0 ? "Focus" : `Hop ${level}`} <span>{nodes.length}</span>
                </p>
                <div className="trace-node-list">
                  {nodes.map((node) => (
                    <button
                      key={node.id}
                      type="button"
                      className="secondary-button trace-node"
                      onClick={() => onNavigate?.(node)}
                    >
                      <span className={`trace-chip trace-kind-${node.discipline ?? "cross"}`}>
                        {traceKindLabel(node.kind)}
                      </span>
                      <span className="trace-node-name">{node.name}</span>
                      <span className="trace-membership">{traceMembershipLabel(node.state_membership)}</span>
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ol>
          {result.edges.length > 0 && (
            <ul className="trace-edge-list">
              {result.edges.map((edge) => {
                const source = byId.get(edge.source_object_id);
                const target = byId.get(edge.target_object_id);
                return (
                  <li key={edge.id}>
                    <span>{source?.name ?? "?"}</span>
                    <span className="trace-edge-type">
                      {traceRelationshipLabel(edge.relationship_type)}
                      {edge.derived ? " (derived)" : ""}
                    </span>
                    <span>{target?.name ?? "?"}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
