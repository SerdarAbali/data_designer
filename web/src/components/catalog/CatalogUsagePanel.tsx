import { useEffect, useState } from "react";

import { api } from "../../apiClient";
import {
  fetchObjectUsages,
  traceKindLabel,
  traceRelationshipLabel,
  type ObjectTrace,
  type TraceObjectRef,
} from "../../workbench/workbenchTypes";

type Props = {
  workspaceId: string;
  kind: "system" | "object" | "field";
  itemId: string;
  itemName: string;
  mode?: "usage" | "relationships";
};

type StateRow = { id: string; state_type: string };
type InformationModelLite = {
  entities: {
    attributes: {
      object_id: string;
      realization: { catalog_object_id: string | null; catalog_field_id: string | null } | null;
    }[];
  }[];
};

function dedupe(items: TraceObjectRef[]): TraceObjectRef[] {
  return [...new Map(items.map((item) => [item.id, item])).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Reads existing traceability (usages) for a catalog item so the Catalog Usage
 * tab can show where the item is referenced across workbenches, states and
 * contracts. Catalog systems are traceable directly; objects and fields resolve
 * through the information attributes that realize them.
 */
export default function CatalogUsagePanel({ workspaceId, kind, itemId, itemName, mode = "usage" }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [groups, setGroups] = useState<{ label: string; objects: TraceObjectRef[] }[]>([]);
  const [relationships, setRelationships] = useState<{ label: string; objects: TraceObjectRef[] }[]>([]);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId || !itemId) return;
    setLoading(true);
    setError("");
    setGroups([]);
    setRelationships([]);
    setDisciplines([]);
    setEmpty(false);
    void (async () => {
      try {
        const states = await api<StateRow[]>(`/api/workspaces/${workspaceId}/states`);
        const state = states.find((row) => row.state_type === "current") ?? states[0];
        if (!state) {
          if (!cancelled) setEmpty(true);
          return;
        }
        const targets: string[] = [];
        if (kind === "system") {
          targets.push(itemId);
        } else {
          const model = await api<InformationModelLite>(
            `/api/workspaces/${workspaceId}/information/model?state_id=${encodeURIComponent(state.id)}`,
          );
          const attributes = model.entities.flatMap((entity) => entity.attributes);
          for (const attribute of attributes) {
            const realization = attribute.realization;
            if (!realization) continue;
            const match = kind === "field"
              ? realization.catalog_field_id === itemId
              : realization.catalog_object_id === itemId;
            if (match) targets.push(attribute.object_id);
          }
        }
        const unique = [...new Set(targets)].slice(0, 8);
        if (unique.length === 0) {
          if (!cancelled) setEmpty(true);
          return;
        }
        const traces = (await Promise.all(
          unique.map((id) => fetchObjectUsages(workspaceId, state.id, id).catch(() => null)),
        )).filter((trace): trace is ObjectTrace => Boolean(trace));

        const groupMap = new Map<string, TraceObjectRef[]>();
        const relationshipMap = new Map<string, TraceObjectRef[]>();
        const disciplineSet = new Set<string>();
        for (const trace of traces) {
          for (const discipline of trace.disciplines) disciplineSet.add(discipline);
          for (const group of trace.groups) {
            groupMap.set(group.label, [...(groupMap.get(group.label) ?? []), ...group.objects]);
          }
          for (const neighbor of [...trace.outgoing, ...trace.incoming]) {
            const key = `${neighbor.direction === "outgoing" ? "→" : "←"} ${
              traceRelationshipLabel(neighbor.relationship_type)
            }`;
            relationshipMap.set(key, [...(relationshipMap.get(key) ?? []), neighbor.object]);
          }
        }
        if (cancelled) return;
        const toGroups = (map: Map<string, TraceObjectRef[]>) => [...map.entries()]
          .map(([label, objects]) => ({ label, objects: dedupe(objects) }))
          .sort((a, b) => a.label.localeCompare(b.label));
        setGroups(toGroups(groupMap));
        setRelationships(toGroups(relationshipMap));
        setDisciplines([...disciplineSet].sort());
        if (groupMap.size === 0 && relationshipMap.size === 0) setEmpty(true);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load usage.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, kind, itemId]);

  const rows = mode === "relationships" ? relationships : groups;

  return (
    <section className="catalog-usage" aria-label={`Usage of ${itemName}`}>
      {loading && <p className="muted" role="status">Loading usage…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && empty && (
        <p className="architecture-topbar-hint">
          {mode === "relationships"
            ? `No architecture relationships reference ${itemName} yet.`
            : `${itemName} is not referenced by any architecture object, contract or test yet.`}
        </p>
      )}
      {!loading && !error && !empty && (
        <>
          {disciplines.length > 0 && (
            <p className="catalog-usage-disciplines">
              Used in: {disciplines.map((discipline) => discipline).join(", ")}
            </p>
          )}
          {rows.map((group) => (
            <div key={group.label} className="catalog-usage-group">
              <p className="catalog-usage-label">{group.label}</p>
              <ul>
                {group.objects.map((node) => (
                  <li key={node.id}>
                    <span>{node.name}</span>
                    <span className="trace-kind-tag">{traceKindLabel(node.kind)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </section>
  );
}
