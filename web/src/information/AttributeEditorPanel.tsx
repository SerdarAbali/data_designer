import { useState } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import { DATA_TYPE_OPTIONS, type InformationAttribute } from "./informationModel";
import RealizationPanel from "./RealizationPanel";

type Props = {
  entityName: string;
  attribute: InformationAttribute;
  editable: boolean;
  stateId: string;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onChange: (attributeId: string, patch: Record<string, unknown>) => void;
  onDelete: (attributeId: string) => void;
  onRealize: (attributeId: string, fieldId: string | null) => void;
  onClose: () => void;
  onBack: () => void;
  onCollapse: () => void;
};

export default function AttributeEditorPanel({
  entityName,
  attribute,
  editable,
  stateId,
  stateName,
  saveStatus,
  busy,
  onChange,
  onDelete,
  onRealize,
  onClose,
  onBack,
  onCollapse,
}: Props) {
  const [name, setName] = useState(attribute.name);
  const [dataType, setDataType] = useState(attribute.data_type);
  const [required, setRequired] = useState(attribute.required);
  const [nullable, setNullable] = useState(attribute.nullable);
  const [isKey, setIsKey] = useState(attribute.is_key);
  const [isIdentifier, setIsIdentifier] = useState(attribute.is_identifier);
  const [definition, setDefinition] = useState(attribute.definition ?? "");

  const dirty =
    name !== attribute.name ||
    dataType !== attribute.data_type ||
    required !== attribute.required ||
    nullable !== attribute.nullable ||
    isKey !== attribute.is_key ||
    isIdentifier !== attribute.is_identifier ||
    definition !== (attribute.definition ?? "");

  return (
    <aside className="architecture-relationship-panel information-panel" aria-label="Attribute details">
      <header>
        <div>
          <p className="eyebrow">ATTRIBUTE</p>
          <h3>{attribute.name}</h3>
          <small>{entityName}</small>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Back to entity" onClick={onBack}>←</button>
          <button type="button" className="secondary-button" aria-label="Collapse attribute inspector" onClick={onCollapse}>›</button>
          <button type="button" className="secondary-button" aria-label="Close attribute details" onClick={onClose}>✕</button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {editable ? "Editable" : "Read-only"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>

      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Data type
        <input
          list="information-data-types"
          value={dataType}
          disabled={!editable}
          onChange={(event) => setDataType(event.target.value)}
        />
        <datalist id="information-data-types">
          {DATA_TYPE_OPTIONS.map((option) => <option key={option} value={option} />)}
        </datalist>
      </label>
      <label className="information-checkbox">
        <input type="checkbox" checked={required} disabled={!editable} onChange={(event) => setRequired(event.target.checked)} />
        Required
      </label>
      <label className="information-checkbox">
        <input type="checkbox" checked={nullable} disabled={!editable} onChange={(event) => setNullable(event.target.checked)} />
        Nullable
      </label>
      <label className="information-checkbox">
        <input type="checkbox" checked={isIdentifier} disabled={!editable} onChange={(event) => setIsIdentifier(event.target.checked)} />
        Identifier (primary key)
      </label>
      <label className="information-checkbox">
        <input type="checkbox" checked={isKey} disabled={!editable} onChange={(event) => setIsKey(event.target.checked)} />
        Unique key
      </label>
      <label>
        Definition
        <textarea value={definition} disabled={!editable} onChange={(event) => setDefinition(event.target.value)} />
      </label>
      {editable && (
        <button
          type="button"
          disabled={!dirty || busy || !name.trim()}
          onClick={() => onChange(attribute.object_id, {
            name,
            data_type: dataType,
            required,
            nullable,
            is_key: isKey,
            is_identifier: isIdentifier,
            definition: definition || null,
          })}
        >
          {busy ? "Saving…" : "Save attribute"}
        </button>
      )}

      <RealizationPanel
        attribute={attribute}
        editable={editable}
        busy={busy}
        stateId={stateId}
        onRealize={onRealize}
      />

      {editable && (
        <button type="button" className="secondary-button architecture-danger" disabled={busy} onClick={() => onDelete(attribute.object_id)}>
          Delete attribute
        </button>
      )}
    </aside>
  );
}
