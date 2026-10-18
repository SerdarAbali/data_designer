import React from "react";
import {
  ARCHITECTURE_FACT_KEYS,
  ARCHITECTURE_FACT_LABELS,
  architectureFactLabel,
  factDiffersFromCanonical,
  type ArchitectureFactKey,
} from "../../architectureFacts";
import type { ArchitectureObject } from "../../architectureTypes";
import { ARCHITECTURE_OBJECT_ICONS, type CanonicalSystem } from "../../architectureCanvasModel";
import type { TraceObjectRef } from "../../workbench/workbenchTypes";
import EvidencePanel from "./EvidencePanel";
import ObjectTracePanel from "./ObjectTracePanel";
import UnifiedInspector from "../inspector/UnifiedInspector";
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
  workspaceId?: string;
  stateId?: string | null;
  /** Candidate/Target scalar overrides for the selected occurrence, if any. */
  overrides?: Record<string, unknown>;
  onNavigateTrace?: (node: TraceObjectRef) => void;
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
  workspaceId,
  stateId,
  overrides,
  onNavigateTrace,
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

  const dirty = Boolean(object) && (
    name !== (object?.name ?? "") ||
    description !== (object?.description ?? "") ||
    (object?.kind === "information_object" && owner !== (object?.owner ?? ""))
  );

  function resetForm() {
    setName(object?.name ?? "");
    setDescription(object?.description ?? "");
    setOwner(object?.owner ?? "");
    setError("");
  }

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

  const systemFacts = system
    ? ARCHITECTURE_FACT_KEYS.map((key: ArchitectureFactKey) => {
        const canonicalRaw = (system as unknown as Record<string, unknown>)[key];
        const canonical = typeof canonicalRaw === "string" ? canonicalRaw : null;
        const overrideRaw = overrides?.[key];
        const override = typeof overrideRaw === "string" ? overrideRaw : null;
        return {
          key,
          label: ARCHITECTURE_FACT_LABELS[key],
          effective: override ?? canonical,
          canonical,
          differs: factDiffersFromCanonical(override, canonical),
        };
      })
    : [];

  const properties = system ? (
    <>
      <section className="inspector-section">
        <h4 className="inspector-section-title">System</h4>
        <strong>{system.name}</strong>
        <p className="inspector-readonly-value">
          <strong>Kind:</strong> {system.kind}
        </p>
        {system.description && <p className="inspector-field-help">{system.description}</p>}
        <div className="inspector-facts">
          {systemFacts.map((item) => (
            <p key={item.key} className="inspector-readonly-value">
              <strong>{item.label}:</strong> {architectureFactLabel(item.effective)}
              {item.differs && (
                <em className="inspector-fact-override">
                  {" "}
                  override (baseline: {architectureFactLabel(item.canonical)})
                </em>
              )}
            </p>
          ))}
        </div>
      </section>
    </>
  ) : object ? (
    <form id="architecture-object-inspector-form" className="architecture-object-form" onSubmit={(event) => void submit(event)}>
      <label className="inspector-field-label">
        Name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={160}
          required
          disabled={readOnly || saving}
        />
      </label>
      <label className="inspector-field-label">
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
          <label className="inspector-field-label">
            Owner
            <input
              value={owner}
              onChange={(event) => setOwner(event.target.value)}
              maxLength={160}
              required
              disabled={readOnly || saving}
            />
          </label>
          <p className="inspector-field-help">
            <strong>Authoritative system:</strong>{" "}
            {systems.find((item) => item.id === object.authoritative_system_id)?.name
              ?? "Unavailable"}
          </p>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {readOnly ? (
        <p className="inspector-field-help">Properties shared with Current are read-only here.</p>
      ) : null}
    </form>
  ) : null;

  const relationshipsPanel = (
    <section className="inspector-section">
      <div className="information-section-heading">
        <strong>Relationships</strong>
        <span className="item-count">{relationships.length}</span>
      </div>
      {relationships.length === 0 ? (
        <div className="inspector-empty">No visible relationships.</div>
      ) : (
        <ul className="inspector-relationship-list">
          {relationships.map((relationship) => (
            <li key={relationship.id}>
              <button
                type="button"
                className="inspector-relationship-item"
                onClick={() => onSelectRelationship(relationship.id)}
              >
                {relationship.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  const traceability = workspaceId && (object || system) ? (
    <ObjectTracePanel
      workspaceId={workspaceId}
      stateId={stateId ?? null}
      objectId={object?.id ?? system?.id ?? null}
      onNavigate={onNavigateTrace}
    />
  ) : (
    <div className="inspector-empty">Traceability is unavailable for this object.</div>
  );

  const evidencePanel =
    workspaceId && object ? (
      <EvidencePanel
        workspaceId={workspaceId}
        stateId={stateId ?? null}
        targetKind="architecture_object"
        targetId={object.id}
        readOnly={readOnly}
      />
    ) : (
      <div className="inspector-empty">
        {system
          ? "Evidence attaches to architecture objects, relationships, contracts and solution members."
          : "Evidence is unavailable for this object."}
      </div>
    );

  const manageItems = (
    <>
      {onOpenCatalog && (
        <button type="button" className="more-menu-item" onClick={onOpenCatalog}>
          Open related Catalog object
        </button>
      )}
      {onRemove && !readOnly && (
        <>
          <hr className="more-menu-separator" />
          <button
            type="button"
            className="more-menu-item more-menu-item--danger"
            onClick={() => {
              if (window.confirm("Remove this object from the current state? This does not delete the catalog object.")) {
                onRemove();
              }
            }}
          >
            Remove from this state
          </button>
        </>
      )}
    </>
  );

  return (
    <UnifiedInspector
      ariaLabel="Object details"
      eyebrow="OBJECT INSPECTOR"
      title={(
        <>
          <span className="architecture-inspector-type-icon" aria-hidden="true">
            {object ? ARCHITECTURE_OBJECT_ICONS[object.kind] : "▣"}
          </span>
          {object ? LABELS[object.kind] : "System"}
        </>
      )}
      identifier={object?.id ?? system?.id}
      stateName={stateName}
      status={readOnly ? "Read-only properties" : "Editable"}
      saveStatus={saveStatus}
      collapseLabel="Collapse object inspector"
      closeLabel="Close object inspector"
      onCollapse={onCollapse}
      onClose={onClose}
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", count: relationships.length, content: relationshipsPanel },
        { id: "evidence", label: "Evidence", content: evidencePanel },
        { id: "traceability", label: "Traceability", content: traceability },
      ]}
      manageMenu={manageItems}
      footer={!readOnly && object ? (
        <div className="inspector-form-actions">
          {dirty && (
            <button type="button" className="btn btn--secondary" onClick={resetForm} disabled={saving}>
              Reset
            </button>
          )}
          <button
            type="submit"
            form="architecture-object-inspector-form"
            className="btn btn--primary"
            disabled={!dirty || saving || !name.trim()}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      ) : undefined}
    />
  );
}
