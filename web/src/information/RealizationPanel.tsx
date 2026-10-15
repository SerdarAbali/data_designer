import { useEffect, useState } from "react";

import { api, list } from "./api";
import type { InformationAttribute } from "./informationModel";

type System = { id: string; name: string };
type CatalogObject = { id: string; name: string; label: string };
type CatalogField = { id: string; name: string; label: string; data_type: string };

type Props = {
  attribute: InformationAttribute;
  editable: boolean;
  busy: boolean;
  stateId: string;
  onRealize: (attributeId: string, fieldId: string | null) => void;
};

export default function RealizationPanel({ attribute, editable, busy, onRealize }: Props) {
  const [systems, setSystems] = useState<System[]>([]);
  const [systemId, setSystemId] = useState("");
  const [objects, setObjects] = useState<CatalogObject[]>([]);
  const [objectId, setObjectId] = useState("");
  const [fields, setFields] = useState<CatalogField[]>([]);
  const [pickerError, setPickerError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void list<System>("/api/catalog/systems")
      .then((records) => {
        if (!cancelled) setSystems(records);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setPickerError(caught instanceof Error ? caught.message : "Could not load systems.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!systemId) {
      setObjects([]);
      return;
    }
    let cancelled = false;
    void list<CatalogObject>(`/api/catalog/systems/${systemId}/objects`)
      .then((records) => {
        if (!cancelled) setObjects(records);
      })
      .catch(() => {
        if (!cancelled) setObjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, [systemId]);

  useEffect(() => {
    if (!objectId) {
      setFields([]);
      return;
    }
    let cancelled = false;
    void list<CatalogField>(`/api/catalog/objects/${objectId}/fields`)
      .then((records) => {
        if (!cancelled) setFields(records);
      })
      .catch(() => {
        if (!cancelled) setFields([]);
      });
    return () => {
      cancelled = true;
    };
  }, [objectId]);

  const current = attribute.realization;

  return (
    <section className="information-realization">
      <div className="information-section-heading">
        <strong>Catalog realization</strong>
      </div>
      {current?.catalog_field_id ? (
        <p className="information-realization-current">
          <span>{current.catalog_object_name ?? "Catalog object"}</span>
          <span> → </span>
          <strong>{current.catalog_field_name ?? "field"}</strong>
        </p>
      ) : (
        <p className="architecture-topbar-hint">This attribute is not mapped to a catalog field yet.</p>
      )}

      {editable && (
        <>
          <label>
            System
            <select value={systemId} onChange={(event) => { setSystemId(event.target.value); setObjectId(""); }}>
              <option value="">Choose a system…</option>
              {systems.map((system) => <option key={system.id} value={system.id}>{system.name}</option>)}
            </select>
          </label>
          {systemId && (
            <label>
              Object
              <select value={objectId} onChange={(event) => setObjectId(event.target.value)}>
                <option value="">Choose an object…</option>
                {objects.map((object) => <option key={object.id} value={object.id}>{object.label || object.name}</option>)}
              </select>
            </label>
          )}
          {objectId && (
            <label>
              Field
              <select
                value=""
                disabled={busy}
                onChange={(event) => {
                  if (event.target.value) onRealize(attribute.object_id, event.target.value);
                }}
              >
                <option value="">Choose a field…</option>
                {fields.map((field) => <option key={field.id} value={field.id}>{field.name} · {field.data_type}</option>)}
              </select>
            </label>
          )}
          {current?.catalog_field_id && (
            <button type="button" className="secondary-button" disabled={busy} onClick={() => onRealize(attribute.object_id, null)}>
              Clear mapping
            </button>
          )}
        </>
      )}
      {pickerError && <p className="studio-topbar-hint">{pickerError}</p>}
    </section>
  );
}
