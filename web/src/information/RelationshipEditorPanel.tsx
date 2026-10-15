import { useState } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import {
  CARDINALITY_OPTIONS,
  cardinalityNotation,
  type InformationCardinality,
  type InformationRelationship,
} from "./informationModel";

type Props = {
  relationship: InformationRelationship;
  sourceLabel: string;
  targetLabel: string;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onChange: (relationshipId: string, patch: { cardinality?: InformationCardinality; name?: string | null }) => void;
  onDelete: (relationshipId: string) => void;
  onClose: () => void;
  onCollapse: () => void;
};

export default function RelationshipEditorPanel({
  relationship,
  sourceLabel,
  targetLabel,
  editable,
  stateName,
  saveStatus,
  busy,
  onChange,
  onDelete,
  onClose,
  onCollapse,
}: Props) {
  const [cardinality, setCardinality] = useState<InformationCardinality>(relationship.cardinality);
  const [name, setName] = useState(relationship.name ?? "");
  const notation = cardinalityNotation(relationship.cardinality);
  const dirty = cardinality !== relationship.cardinality || name !== (relationship.name ?? "");

  return (
    <aside className="architecture-relationship-panel information-panel" aria-label="Relationship details">
      <header>
        <div>
          <p className="eyebrow">RELATIONSHIP</p>
          <h3>{sourceLabel} → {targetLabel}</h3>
          <small>{notation.source} : {notation.target}</small>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Collapse relationship inspector" onClick={onCollapse}>›</button>
          <button type="button" className="secondary-button" aria-label="Close relationship details" onClick={onClose}>✕</button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {editable ? "Editable" : "Read-only"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>

      <label>
        Cardinality
        <select value={cardinality} disabled={!editable} onChange={(event) => setCardinality(event.target.value as InformationCardinality)}>
          {CARDINALITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label>
        Name
        <input value={name} disabled={!editable} placeholder="Optional verb" onChange={(event) => setName(event.target.value)} />
      </label>
      {editable && (
        <button
          type="button"
          disabled={!dirty || busy}
          onClick={() => onChange(relationship.id, { cardinality, name: name || null })}
        >
          {busy ? "Saving…" : "Save relationship"}
        </button>
      )}
      {editable && (
        <button type="button" className="secondary-button architecture-danger" disabled={busy} onClick={() => onDelete(relationship.id)}>
          Delete relationship
        </button>
      )}
    </aside>
  );
}
