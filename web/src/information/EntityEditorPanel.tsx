import { useState, type FormEvent, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
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
  relationships?: ReactNode;
  trace?: ReactNode;
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
  relationships,
  trace,
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

  const properties = (
    <>
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
    </>
  );

  return (
    <UnifiedInspector
      ariaLabel="Entity details"
      eyebrow="ENTITY"
      title={entity.name}
      identifier={entity.object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse entity inspector"
      closeLabel="Close entity details"
      onCollapse={onCollapse}
      onClose={onClose}
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", content: relationships ?? <p className="muted">No relationships.</p> },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
