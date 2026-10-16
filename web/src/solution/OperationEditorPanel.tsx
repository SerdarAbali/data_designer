import { useState, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
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
  trace?: ReactNode;
};

const KIND_LABELS: Record<SolutionOperationKind, string> = {
  operation: "Operation",
  event: "Event",
  command: "Command",
  query: "Query",
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
  trace,
}: Props) {
  const [name, setName] = useState(operation.name);
  const [description, setDescription] = useState(operation.description ?? "");
  const [kind, setKind] = useState<SolutionOperationKind>(operation.operation_kind);

  const dirty = name !== operation.name || description !== (operation.description ?? "") || kind !== operation.operation_kind;

  const properties = (
    <>
      <button type="button" className="solution-back-button" onClick={onBack}>‹ {interfaceName}</button>
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
    </>
  );

  return (
    <UnifiedInspector
      ariaLabel="Operation details"
      eyebrow="OPERATION / EVENT"
      title={operation.name}
      identifier={operation.object_id}
      stateName={stateName}
      status={`${KIND_LABELS[operation.operation_kind]} · ${editable ? "Editable" : "Read-only"}`}
      saveStatus={saveStatus}
      collapseLabel="Collapse operation inspector"
      closeLabel="Close operation details"
      onCollapse={onCollapse}
      onClose={onClose}
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", content: <p className="architecture-topbar-hint">Operations connect an interface to its callers and events.</p> },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
