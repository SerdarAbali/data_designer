import { useState, type FormEvent } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import { attributeSummary, keyBadge, type InformationAttribute, type InformationEntity } from "./informationModel";

export type AttributeDraft = {
  name: string;
  data_type: string;
  required: boolean;
  nullable: boolean;
  is_key: boolean;
  is_identifier: boolean;
  definition: string | null;
};

type Props = {
  entity: InformationEntity;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (
    entityId: string,
    patch: {
      name?: string;
      description?: string | null;
      owner?: string | null;
      steward?: string | null;
      classification?: string | null;
      sensitivity?: string | null;
    },
  ) => void;
  onSelectAttribute: (attributeId: string) => void;
  onAddAttribute: (draft: AttributeDraft) => void;
  onClose: () => void;
  onCollapse: () => void;
};

const EMPTY_DRAFT: AttributeDraft = {
  name: "",
  data_type: "string",
  required: false,
  nullable: true,
  is_key: false,
  is_identifier: false,
  definition: null,
};

export default function EntityEditorPanel({
  entity,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onSelectAttribute,
  onAddAttribute,
  onClose,
  onCollapse,
}: Props) {
  const [name, setName] = useState(entity.name);
  const [description, setDescription] = useState(entity.description ?? "");
  const [owner, setOwner] = useState(entity.owner ?? "");
  const [steward, setSteward] = useState(entity.steward ?? "");
  const [classification, setClassification] = useState(entity.classification ?? "");
  const [sensitivity, setSensitivity] = useState(entity.sensitivity ?? "");
  const [draft, setDraft] = useState<AttributeDraft>(EMPTY_DRAFT);

  const dirty =
    name !== entity.name ||
    description !== (entity.description ?? "") ||
    owner !== (entity.owner ?? "") ||
    steward !== (entity.steward ?? "") ||
    classification !== (entity.classification ?? "") ||
    sensitivity !== (entity.sensitivity ?? "");

  function submitAttribute(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) return;
    onAddAttribute({ ...draft, name: draft.name.trim() });
    setDraft(EMPTY_DRAFT);
  }

  return (
    <aside className="architecture-relationship-panel information-panel" aria-label="Entity details">
      <header>
        <div>
          <p className="eyebrow">ENTITY</p>
          <h3>{entity.name}</h3>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Collapse entity inspector" onClick={onCollapse}>›</button>
          <button type="button" className="secondary-button" aria-label="Close entity details" onClick={onClose}>✕</button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {editable ? "Editable" : "Read-only"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>

      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Description
        <textarea value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <label>
        Owner
        <input value={owner} disabled={!editable} placeholder="Optional" onChange={(event) => setOwner(event.target.value)} />
      </label>
      <label>
        Steward
        <input value={steward} disabled={!editable} placeholder="Optional" onChange={(event) => setSteward(event.target.value)} />
      </label>
      <p className="information-ownership-note">
        <strong>Authoritative system:</strong>{" "}
        {entity.authoritative_system_name ?? "Not set"}
      </p>
      <label>
        Classification
        <input
          value={classification}
          disabled={!editable}
          placeholder="e.g. public, internal, confidential"
          maxLength={100}
          onChange={(event) => setClassification(event.target.value)}
        />
      </label>
      <label>
        Sensitivity
        <input
          value={sensitivity}
          disabled={!editable}
          placeholder="e.g. low, medium, high"
          maxLength={40}
          onChange={(event) => setSensitivity(event.target.value)}
        />
      </label>
      {editable && (
        <button
          type="button"
          disabled={!dirty || busy || !name.trim()}
          onClick={() =>
            onSave(entity.object_id, {
              name,
              description,
              owner,
              steward,
              classification,
              sensitivity,
            })
          }
        >
          {busy ? "Saving…" : "Save entity"}
        </button>
      )}

      <section className="information-attributes-section">
        <div className="information-section-heading">
          <strong>Attributes</strong>
          <span className="item-count">{entity.attributes.length}</span>
        </div>
        {entity.attributes.length === 0 ? (
          <p className="architecture-topbar-hint">No attributes yet. Add the first one below.</p>
        ) : (
          <ul className="information-attribute-editor-list">
            {entity.attributes.map((attribute: InformationAttribute) => (
              <li key={attribute.object_id}>
                <button type="button" onClick={() => onSelectAttribute(attribute.object_id)}>
                  <span>{attribute.name}</span>
                  <small>
                    {keyBadge(attribute) && <em className="information-key-badge">{keyBadge(attribute)}</em>}
                    {attributeSummary(attribute)}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}

        {editable && (
          <form className="information-attribute-form" onSubmit={submitAttribute}>
            <p className="studio-menu-caption">New attribute</p>
            <label>
              Name
              <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label>
              Data type
              <input value={draft.data_type} onChange={(event) => setDraft({ ...draft, data_type: event.target.value })} />
            </label>
            <label className="information-checkbox">
              <input type="checkbox" checked={draft.required} onChange={(event) => setDraft({ ...draft, required: event.target.checked })} />
              Required
            </label>
            <label className="information-checkbox">
              <input type="checkbox" checked={draft.nullable} onChange={(event) => setDraft({ ...draft, nullable: event.target.checked })} />
              Nullable
            </label>
            <label className="information-checkbox">
              <input type="checkbox" checked={draft.is_identifier} onChange={(event) => setDraft({ ...draft, is_identifier: event.target.checked })} />
              Identifier (PK)
            </label>
            <label className="information-checkbox">
              <input type="checkbox" checked={draft.is_key} onChange={(event) => setDraft({ ...draft, is_key: event.target.checked })} />
              Unique key
            </label>
            <button type="submit" disabled={busy || !draft.name.trim()}>Add attribute</button>
          </form>
        )}
      </section>
    </aside>
  );
}
