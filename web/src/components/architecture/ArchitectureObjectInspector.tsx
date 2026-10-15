import React from "react";
import type { ArchitectureObject } from "../../architectureTypes";
import { ARCHITECTURE_OBJECT_ICONS, type CanonicalSystem } from "../../architectureCanvasModel";
import type { SaveStatus } from "./ArchitectureTopBar";

type UpdatePayload = {
  name: string;
  description: string;
  owner?: string;
};

type Props = {
  object: ArchitectureObject | null;
  system: CanonicalSystem | null;
  systems: CanonicalSystem[];
  readOnly: boolean;
  onClose: () => void;
  onOpenCatalog?: () => void;
  onSave: (objectId: string, payload: UpdatePayload) => Promise<void>;
  onCollapse: () => void;
  occurrenceId: string;
  stateName: string;
  saveStatus: SaveStatus;
  relationships: { id: string; label: string }[];
  onSelectRelationship: (id: string) => void;
  onRemove?: () => void;
};

const LABELS: Record<ArchitectureObject["kind"], string> = {
  business_requirement: "Business Requirement",
  business_capability: "Business Capability",
  information_object: "Information Object",
  solution_boundary: "Solution Boundary",
  component: "Component",
  interface: "Interface",
};

export default function ArchitectureObjectInspector({
  object,
  system,
  systems,
  readOnly,
  onClose,
  onOpenCatalog,
  onSave,
  onCollapse,
  occurrenceId,
  stateName,
  saveStatus,
  relationships,
  onSelectRelationship,
  onRemove,
}: Props) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [owner, setOwner] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setName(object?.name ?? "");
    setDescription(object?.description ?? "");
    setOwner(object?.owner ?? "");
    setError("");
  }, [object?.id, object?.name, object?.description, object?.owner, object?.authoritative_system_id]);

  if (!object && !system) return null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!object) return;
    setSaving(true);
    setError("");
    try {
      await onSave(object.id, {
        name: name.trim(),
        description: description.trim(),
        ...(object.kind === "information_object"
          ? { owner: owner.trim() }
          : {}),
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update this architecture object.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="architecture-relationship-panel architecture-object-inspector" aria-label="Object details">
      <header>
        <div>
          <p className="eyebrow">OBJECT INSPECTOR</p>
          <h3>
            <span className="architecture-inspector-type-icon" aria-hidden="true">
              {object ? ARCHITECTURE_OBJECT_ICONS[object.kind] : "▣"}
            </span>
            {object ? LABELS[object.kind] : "System"}
          </h3>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Collapse object inspector" onClick={onCollapse}>›</button>
          <button
          type="button"
          className="secondary-button"
          aria-label="Close object inspector"
          onClick={onClose}
        >
          ✕
        </button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {readOnly ? "Read-only properties" : "Editable"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>
      <small className="studio-object-identifier" title={occurrenceId}>{object?.id ?? system?.id}</small>
      {system ? (
        <>
          <strong>{system.name}</strong>
          <p><strong>Kind:</strong> {system.kind}</p>
          {system.description && <p>{system.description}</p>}
          {onOpenCatalog && (
            <button type="button" className="secondary-button" onClick={onOpenCatalog}>
              Open catalog
            </button>
          )}
        </>
      ) : object ? (
        <form className="architecture-object-form" onSubmit={(event) => void submit(event)}>
          <label>
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={160}
              required
              disabled={readOnly || saving}
            />
          </label>
          <label>
            Description
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={500}
              rows={3}
              disabled={readOnly || saving}
            />
          </label>
          {object.kind === "information_object" && (
            <>
              <label>
                Owner
                <input
                  value={owner}
                  onChange={(event) => setOwner(event.target.value)}
                  maxLength={160}
                  required
                  disabled={readOnly || saving}
                />
              </label>
              <p>
                <strong>Authoritative system:</strong>{" "}
                {systems.find((item) => item.id === object.authoritative_system_id)?.name
                  ?? "Unavailable"}
              </p>
            </>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          {readOnly ? (
            <p className="architecture-topbar-hint">Properties shared with Current are read-only here.</p>
          ) : (
            <button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save object"}
            </button>
          )}
        </form>
      ) : null}
      <section className="studio-inspector-relationships">
        <h4>Relationships <span>{relationships.length}</span></h4>
        {relationships.length === 0 ? <p className="muted">No visible relationships.</p> : relationships.map((relationship) => (
          <button key={relationship.id} type="button" className="secondary-button" onClick={() => onSelectRelationship(relationship.id)}>{relationship.label}</button>
        ))}
      </section>
      {onRemove && <button type="button" className="secondary-button architecture-danger" onClick={onRemove}>Remove from this state</button>}
    </aside>
  );
}
