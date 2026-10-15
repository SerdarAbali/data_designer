import { useState } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import type { SolutionOperation, SolutionOperationKind } from "./solutionModel";

type Props = {
  interfaceName: string;
  operation: SolutionOperation;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (operationId: string, patch: { name?: string; description?: string | null; operation_kind?: SolutionOperationKind }) => void;
  onDelete: (operationId: string) => void;
  onBack: () => void;
  onClose: () => void;
  onCollapse: () => void;
};

export default function OperationEditorPanel({
  interfaceName,
  operation,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onBack,
  onClose,
  onCollapse,
}: Props) {
  const [name, setName] = useState(operation.name);
  const [description, setDescription] = useState(operation.description ?? "");
  const [kind, setKind] = useState<SolutionOperationKind>(operation.operation_kind);

  const dirty = name !== operation.name || description !== (operation.description ?? "") || kind !== operation.operation_kind;

  return (
    <aside className="architecture-relationship-panel solution-panel" aria-label="Operation details">
      <header>
        <div>
          <button type="button" className="solution-back-button" onClick={onBack}>‹ {interfaceName}</button>
          <p className="eyebrow">OPERATION / EVENT</p>
          <h3>{operation.name}</h3>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Collapse operation inspector" onClick={onCollapse}>›</button>
          <button type="button" className="secondary-button" aria-label="Close operation details" onClick={onClose}>✕</button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {editable ? "Editable" : "Read-only"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>

      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Kind
        <select value={kind} disabled={!editable} onChange={(event) => setKind(event.target.value as SolutionOperationKind)}>
          <option value="operation">Operation</option>
          <option value="event">Event</option>
          <option value="command">Command</option>
          <option value="query">Query</option>
        </select>
      </label>
      <label>
        Description
        <textarea value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} />
      </label>
      {editable && (
        <div className="solution-panel-actions">
          <button
            type="button"
            disabled={!dirty || busy || !name.trim()}
            onClick={() => onSave(operation.object_id, { name, description, operation_kind: kind })}
          >
            {busy ? "Saving…" : "Save operation"}
          </button>
          <button type="button" className="secondary-button architecture-danger" onClick={() => onDelete(operation.object_id)}>
            Delete
          </button>
        </div>
      )}
    </aside>
  );
}
