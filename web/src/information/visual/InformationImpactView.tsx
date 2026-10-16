import { useMemo, useState } from "react";

import type {
  InformationChangeType,
  InformationImpact,
  InformationImpactChange,
} from "../informationModel";
import {
  CHANGE_LABELS,
  CHANGE_ORDER,
  OBJECT_TYPE_LABELS,
  filterImpactChanges,
  impactObjectTypes,
} from "../informationViews";

type Props = {
  impact: InformationImpact;
  selectedObjectId: string | null;
  onSelectChange: (change: InformationImpactChange) => void;
};

export default function InformationImpactView({ impact, selectedObjectId, onSelectChange }: Props) {
  const [change, setChange] = useState<InformationChangeType | "all">("all");
  const [objectType, setObjectType] = useState<string>("all");

  const visible = useMemo(
    () => filterImpactChanges(impact.changes, { change, objectType }),
    [impact.changes, change, objectType],
  );

  if (!impact.supported) {
    return (
      <section className="information-impact" aria-label="Current vs candidate impact">
        <div className="information-impact-unsupported" role="status">
          <h3>Comparison unavailable</h3>
          <p>
            {impact.unresolved[0] ??
              "The current state model cannot derive a comparison for this selection."}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="information-impact" aria-label="Current vs candidate impact">
      <header className="information-impact-toolbar">
        <label>
          Change
          <select
            aria-label="Filter by change type"
            value={change}
            onChange={(event) => setChange(event.target.value as InformationChangeType | "all")}
          >
            <option value="all">All changes</option>
            {CHANGE_ORDER.map((value) => (
              <option key={value} value={value}>
                {CHANGE_LABELS[value]} ({impact.summary[value] ?? 0})
              </option>
            ))}
          </select>
        </label>
        <label>
          Object
          <select
            aria-label="Filter by object type"
            value={objectType}
            onChange={(event) => setObjectType(event.target.value)}
          >
            <option value="all">All objects</option>
            {impactObjectTypes(impact.changes).map((value) => (
              <option key={value} value={value}>
                {OBJECT_TYPE_LABELS[value] ?? value}
              </option>
            ))}
          </select>
        </label>
        <span className="information-canvas-count">
          {impact.changes.length} changes vs Current
        </span>
      </header>

      {impact.unresolved.length > 0 && (
        <div className="information-impact-unresolved" role="status">
          <strong>Unresolved mappings</strong>
          <ul>
            {impact.unresolved.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="information-impact-groups">
        {CHANGE_ORDER.map((value) => {
          const items = visible.filter((item) => item.change === value);
          if (items.length === 0) return null;
          return (
            <article key={value} className={`information-impact-group change-${value}`}>
              <h3>
                {CHANGE_LABELS[value]} <small>{items.length}</small>
              </h3>
              <ul>
                {items.map((item) => (
                  <li key={`${item.object_type}:${item.object_id}:${item.change}`}>
                    <button
                      type="button"
                      className={item.object_id === selectedObjectId ? "selected" : ""}
                      data-change={item.change}
                      data-object-type={item.object_type}
                      onClick={() => onSelectChange(item)}
                    >
                      <span className="information-impact-head">
                        <span className="information-impact-name">
                          {item.entity_name ? `${item.entity_name}.` : ""}
                          {item.name}
                        </span>
                        <span className={`information-impact-change change-${item.change}`}>
                          {CHANGE_LABELS[item.change]}
                        </span>
                      </span>
                      <span className="information-impact-type">
                        {OBJECT_TYPE_LABELS[item.object_type] ?? item.object_type}
                      </span>
                      {item.changed_fields.length > 0 && (
                        <small className="information-impact-reason">
                          {item.changed_fields.join(", ")}
                        </small>
                      )}
                      {item.reason && (
                        <small className="information-impact-reason">{item.reason}</small>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
        {visible.length === 0 && (
          <p className="information-projection-empty">No changes match the current filters.</p>
        )}
      </div>
    </section>
  );
}
