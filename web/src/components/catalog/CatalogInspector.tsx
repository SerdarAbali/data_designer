import type { FormEvent, ReactNode } from "react";
import type { InspectorTab } from "./InspectorTabs";
import InspectorTabs from "./InspectorTabs";

export type InspectorSystem = {
  id: string;
  name: string;
  kind: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  position: { x: number; y: number } | null;
  metadata: Record<string, unknown>;
};

export type InspectorObject = {
  id: string;
  system_id: string;
  name: string;
  label: string;
  description: string | null;
  external_identifier: string | null;
  position: number;
  metadata: Record<string, unknown>;
};

export type InspectorField = {
  id: string;
  object_id: string;
  name: string;
  label: string;
  description: string | null;
  data_type: string;
  required: boolean;
  nullable: boolean;
  default_value: unknown;
  external_identifier: string | null;
  position: number;
  origin: string;
  metadata: Record<string, unknown>;
};

type Props = {
  system: InspectorSystem | null;
  object: InspectorObject | null;
  field: InspectorField | null;
  objects: InspectorObject[];
  fields: InspectorField[];
  fieldCounts: Record<string, number>;
  loadingObjects: boolean;
  loadingFields: boolean;
  saving: boolean;
  tab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  onSaveSystem: (event: FormEvent<HTMLFormElement>) => void;
  onSaveObject: (event: FormEvent<HTMLFormElement>) => void;
  onSaveField: (event: FormEvent<HTMLFormElement>) => void;
  onCreateObject: (event: FormEvent<HTMLFormElement>) => void;
  onCreateField: (event: FormEvent<HTMLFormElement>) => void;
  onSelectObject: (id: string) => void;
  onSelectField: (id: string) => void;
  onAddObject: () => void;
  onAddField: () => void;
  modal: "object" | "field" | null;
  onCloseModal: () => void;
  onArchive: (kind: "system" | "object" | "field") => void;
};

function jsonText(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

function Modal({
  title,
  saving,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  saving: boolean;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}) {
  return (
    <div className="catalog-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="catalog-modal" role="dialog" aria-modal="true" aria-labelledby="catalog-modal-title">
        <header>
          <div>
            <p className="eyebrow">CATALOG</p>
            <h2 id="catalog-modal-title">{title}</h2>
          </div>
          <button type="button" className="secondary-button" onClick={onClose} aria-label="Close">×</button>
        </header>
        <form className="editor-form" onSubmit={onSubmit}>
          {children}
          <div className="catalog-modal-actions">
            <button type="button" className="secondary-button" onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" disabled={saving}>{saving ? "Saving…" : title}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function CatalogInspector(props: Props) {
  const {
    system, object, field, objects, fields, fieldCounts, loadingObjects, loadingFields,
    saving, tab, onTabChange, onSaveSystem, onSaveObject, onSaveField, onCreateObject,
    onCreateField, onSelectObject, onSelectField, onAddObject, onAddField, onArchive,
  } = props;

  if (field) {
    return (
      <section className="catalog-panel entity-inspector" aria-labelledby="field-inspector-title">
        <div className="panel-heading">
          <div><p className="eyebrow">FIELD CONFIGURATION</p><h2 id="field-inspector-title">{field.label}</h2></div>
          <button type="button" className="danger-button" onClick={() => onArchive("field")} disabled={saving}>Archive field</button>
        </div>
        <form className="editor-form" onSubmit={onSaveField}>
          <div className="form-row">
            <label>Name<input name="name" required maxLength={160} defaultValue={field.name} /></label>
            <label>Label<input name="label" required maxLength={160} defaultValue={field.label} /></label>
          </div>
          <div className="form-row">
            <label>Data type<input name="data_type" required maxLength={100} defaultValue={field.data_type} /></label>
            <label>Position<input name="position" type="number" min={0} defaultValue={field.position} /></label>
          </div>
          <div className="check-row">
            <label><input name="required" type="checkbox" defaultChecked={field.required} /> Required</label>
            <label><input name="nullable" type="checkbox" defaultChecked={field.nullable} /> Nullable</label>
          </div>
          <div className="form-row">
            <label>Default value (JSON)<input name="default_value" defaultValue={field.default_value == null ? "" : JSON.stringify(field.default_value)} /></label>
            <label>External identifier<input name="external_identifier" defaultValue={field.external_identifier ?? ""} /></label>
          </div>
          <label>Description<textarea name="description" rows={3} defaultValue={field.description ?? ""} /></label>
          <div className="form-row">
            <label>Origin<input name="origin" defaultValue={field.origin} /></label>
            <label>Metadata (JSON)<textarea name="metadata" rows={3} defaultValue={jsonText(field.metadata)} /></label>
          </div>
          <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save field"}</button>
        </form>
      </section>
    );
  }

  if (object) {
    return (
      <>
        <section className="catalog-panel entity-inspector" aria-labelledby="object-inspector-title">
          <div className="panel-heading">
            <div><p className="eyebrow">OBJECT DESIGNER</p><h2 id="object-inspector-title">{object.label}</h2></div>
            <div className="entity-actions">
              <button type="button" onClick={onAddField}>＋ Add field</button>
              <button type="button" className="danger-button" onClick={() => onArchive("object")} disabled={saving}>Archive object</button>
            </div>
          </div>
          <form className="editor-form entity-form" onSubmit={onSaveObject}>
            <InspectorTabs value={tab} onChange={onTabChange} />
            <div className="inspector-tab-panel" hidden={tab !== "general"}>
              <div className="form-row">
                <label>Name<input name="name" required maxLength={160} defaultValue={object.name} /></label>
                <label>Label<input name="label" required maxLength={160} defaultValue={object.label} /></label>
              </div>
              <label>Description<textarea name="description" rows={2} defaultValue={object.description ?? ""} /></label>
            </div>
            <div className="inspector-tab-panel" hidden={tab !== "schema"}>
              <div className="form-row">
                <label>External identifier<input name="external_identifier" defaultValue={object.external_identifier ?? ""} /></label>
                <label>Position<input name="position" type="number" min={0} defaultValue={object.position} /></label>
              </div>
            </div>
            <div className="inspector-tab-panel" hidden={tab !== "metadata"}>
              <label>Metadata (JSON)<textarea name="metadata" rows={5} defaultValue={jsonText(object.metadata)} /></label>
            </div>
            <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save object"}</button>
          </form>
        </section>
        <section className="catalog-panel entity-table-panel" aria-labelledby="object-fields-title">
          <header className="entity-table-heading">
            <div><p className="eyebrow">OBJECT SCHEMA</p><h3 id="object-fields-title">Fields</h3></div>
            <span className="item-count">{fields.length}</span>
          </header>
          {loadingFields ? <p className="muted" role="status">Loading fields…</p> : fields.length === 0 ? (
            <p className="empty-state">No fields yet. Add the first field to this object.</p>
          ) : (
            <div className="catalog-table-wrap">
              <table className="catalog-table">
                <thead><tr><th>Name</th><th>Data type</th><th>Label</th><th>Required / Nullable</th><th>Actions</th></tr></thead>
                <tbody>{fields.map((item) => (
                  <tr key={item.id}>
                    <td><code>{item.name}</code></td><td><span className="field-type">{item.data_type}</span></td>
                    <td>{item.label}</td><td>{item.required ? "Required" : "—"} / {item.nullable ? "Nullable" : "Not null"}</td>
                    <td><button type="button" className="quiet-button" onClick={() => onSelectField(item.id)}>Edit</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>
        {props.modal === "field" && (
          <Modal title="Add field" saving={saving} onClose={props.onCloseModal} onSubmit={onCreateField}>
            <div className="form-row">
              <label>Field name<input name="name" required maxLength={160} placeholder="phone_number" /></label>
              <label>Label<input name="label" maxLength={160} placeholder="Phone number" /></label>
            </div>
            <label>Data type<input name="data_type" required maxLength={100} placeholder="string" /></label>
            <label>Description<textarea name="description" rows={2} /></label>
            <div className="check-row">
              <label><input name="required" type="checkbox" /> Required</label>
              <label><input name="nullable" type="checkbox" defaultChecked /> Nullable</label>
            </div>
          </Modal>
        )}
      </>
    );
  }

  if (system) {
    return (
      <>
        <section className="catalog-panel entity-inspector" aria-labelledby="system-inspector-title">
          <div className="panel-heading">
            <div><p className="eyebrow">SYSTEM DESIGNER</p><h2 id="system-inspector-title">{system.name}</h2></div>
            <div className="entity-actions">
              <button type="button" onClick={onAddObject}>＋ Add object</button>
              <button type="button" className="danger-button" onClick={() => onArchive("system")} disabled={saving}>Archive system</button>
            </div>
          </div>
          <form className="editor-form entity-form" onSubmit={onSaveSystem}>
            <InspectorTabs value={tab} onChange={onTabChange} includeSchema={false} />
            <div className="inspector-tab-panel" hidden={tab !== "general"}>
              <div className="form-row">
                <label>System name<input name="name" required maxLength={160} defaultValue={system.name} /></label>
                <label>Kind<input name="kind" required maxLength={100} defaultValue={system.kind} /></label>
              </div>
              <label>Description<textarea name="description" rows={2} defaultValue={system.description ?? ""} /></label>
              <div className="form-row">
                <label>Icon<input name="icon" maxLength={100} defaultValue={system.icon ?? ""} /></label>
                <label>Color<input name="color" maxLength={40} defaultValue={system.color ?? ""} /></label>
                <label>Position X<input name="x" type="number" defaultValue={system.position?.x ?? 0} /></label>
                <label>Position Y<input name="y" type="number" defaultValue={system.position?.y ?? 0} /></label>
              </div>
            </div>
            <div className="inspector-tab-panel" hidden={tab !== "metadata"}>
              <label>Raw metadata JSON<textarea name="metadata" rows={6} spellCheck={false} defaultValue={jsonText(system.metadata)} /></label>
            </div>
            <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save system"}</button>
          </form>
        </section>
        <section className="catalog-panel entity-table-panel" aria-labelledby="system-objects-title">
          <header className="entity-table-heading">
            <div><p className="eyebrow">SYSTEM CONTENTS</p><h3 id="system-objects-title">Objects</h3></div>
            <span className="item-count">{objects.filter((item) => item.system_id === system.id).length}</span>
          </header>
          {loadingObjects ? <p className="muted" role="status">Loading objects…</p> : objects.filter((item) => item.system_id === system.id).length === 0 ? (
            <p className="empty-state">This system has no objects. Add an object to define its schema.</p>
          ) : (
            <div className="catalog-table-wrap">
              <table className="catalog-table">
                <thead><tr><th>Name</th><th>Label</th><th>Field count</th><th>Actions</th></tr></thead>
                <tbody>{objects.filter((item) => item.system_id === system.id).map((item) => (
                  <tr key={item.id}>
                    <td><code>{item.name}</code></td><td>{item.label}</td><td>{fieldCounts[item.id] ?? 0}</td>
                    <td><button type="button" className="quiet-button" onClick={() => onSelectObject(item.id)}>Open object</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>
        {props.modal === "object" && (
          <Modal title="Add object" saving={saving} onClose={props.onCloseModal} onSubmit={onCreateObject}>
            <div className="form-row">
              <label>Name<input name="name" required maxLength={160} placeholder="Customer" /></label>
              <label>Label<input name="label" maxLength={160} placeholder="Customer" /></label>
            </div>
            <label>Description<textarea name="description" rows={2} /></label>
            <label>Metadata (JSON)<textarea name="metadata" rows={3} defaultValue="{}" /></label>
          </Modal>
        )}
      </>
    );
  }

  return (
    <section className="catalog-panel empty-workspace">
      <span className="empty-icon">◇</span>
      <h2>Select a system, object, or field</h2>
      <p>Choose an entity from the catalog tree to inspect and edit its details.</p>
    </section>
  );
}
