import { useState, type FormEvent, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import {
  SOLUTION_COMPONENT_TYPES,
  type SolutionComponent,
  type SolutionDirection,
  type SolutionInterfaceKind,
} from "./solutionModel";

export type InterfaceDraft = {
  name: string;
  direction: SolutionDirection;
  interface_kind: SolutionInterfaceKind | "";
  protocol: string;
};

type Props = {
  component: SolutionComponent;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (
    componentId: string,
    patch: {
      name?: string;
      description?: string | null;
      responsibility?: string | null;
      component_type?: string | null;
      technology?: string | null;
    },
  ) => void;
  onDelete: (componentId: string) => void;
  onSelectInterface: (interfaceId: string) => void;
  onAddInterface: (draft: InterfaceDraft) => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

const EMPTY_DRAFT: InterfaceDraft = {
  name: "",
  direction: "provided",
  interface_kind: "",
  protocol: "",
};

export default function ComponentEditorPanel({
  component,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onSelectInterface,
  onAddInterface,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const [name, setName] = useState(component.name);
  const [description, setDescription] = useState(component.description ?? "");
  const [responsibility, setResponsibility] = useState(component.responsibility ?? "");
  const [componentType, setComponentType] = useState(component.component_type ?? "");
  const [technology, setTechnology] = useState(component.technology ?? "");
  const [draft, setDraft] = useState<InterfaceDraft>(EMPTY_DRAFT);

  const dirty =
    name !== component.name ||
    description !== (component.description ?? "") ||
    responsibility !== (component.responsibility ?? "") ||
    componentType !== (component.component_type ?? "") ||
    technology !== (component.technology ?? "");

  function submitInterface(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) return;
    onAddInterface({ ...draft, name: draft.name.trim() });
    setDraft(EMPTY_DRAFT);
  }

  const properties = (
    <>
      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Responsibility
        <textarea
          value={responsibility}
          disabled={!editable}
          placeholder="What is this component accountable for?"
          onChange={(event) => setResponsibility(event.target.value)}
        />
      </label>
      <label>
        Description
        <textarea value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <label>
        Component type
        <select value={componentType} disabled={!editable} onChange={(event) => setComponentType(event.target.value)}>
          <option value="">Unspecified</option>
          {SOLUTION_COMPONENT_TYPES.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </label>
      <label>
        Technology
        <input value={technology} disabled={!editable} onChange={(event) => setTechnology(event.target.value)} />
      </label>
      {editable && (
        <div className="solution-panel-actions">
          <button
            type="button"
            disabled={!dirty || busy || !name.trim()}
            onClick={() => onSave(component.object_id, {
              name,
              description,
              responsibility,
              component_type: componentType || null,
              technology,
            })}
          >
            {busy ? "Saving…" : "Save component"}
          </button>
          <button type="button" className="secondary-button architecture-danger" onClick={() => onDelete(component.object_id)}>
            Delete
          </button>
        </div>
      )}
    </>
  );

  const relationshipsPanel = (
    <section className="solution-interfaces-section">
      <div className="information-section-heading">
        <strong>Interfaces</strong>
        <span className="item-count">{component.interfaces.length}</span>
      </div>
      {component.interfaces.length === 0 ? (
        <p className="architecture-topbar-hint">No interfaces yet. Add provided or required interfaces below.</p>
      ) : (
        <ul className="solution-interface-list">
          {component.interfaces.map((ui) => (
            <li key={ui.object_id}>
              <button type="button" onClick={() => onSelectInterface(ui.object_id)}>
                <span>{ui.name}</span>
                <small>
                  <em className={`solution-direction direction-${ui.direction}`}>{ui.direction}</em>
                  {ui.operations.length} {ui.operations.length === 1 ? "operation" : "operations"}
                </small>
              </button>
            </li>
          ))}
        </ul>
      )}

      {editable && (
        <form className="solution-interface-form" onSubmit={submitInterface}>
          <p className="studio-menu-caption">New interface</p>
          <label>
            Name
            <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          </label>
          <label>
            Direction
            <select
              value={draft.direction}
              onChange={(event) => setDraft({ ...draft, direction: event.target.value as SolutionDirection })}
            >
              <option value="provided">Provided</option>
              <option value="required">Required</option>
            </select>
          </label>
          <label>
            Kind
            <select
              value={draft.interface_kind}
              onChange={(event) => setDraft({ ...draft, interface_kind: event.target.value as SolutionInterfaceKind | "" })}
            >
              <option value="">Unspecified</option>
              <option value="sync">Sync</option>
              <option value="async">Async</option>
            </select>
          </label>
          <label>
            Protocol
            <input value={draft.protocol} onChange={(event) => setDraft({ ...draft, protocol: event.target.value })} />
          </label>
          <button type="submit" disabled={busy || !draft.name.trim()}>Add interface</button>
        </form>
      )}
    </section>
  );

  return (
    <UnifiedInspector
      ariaLabel="Component details"
      eyebrow="COMPONENT"
      title={component.name}
      identifier={component.object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse component inspector"
      closeLabel="Close component details"
      onCollapse={onCollapse}
      onClose={onClose}
      defaultTab="relationships"
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", count: component.interfaces.length, content: relationshipsPanel },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
