import { useState, type FormEvent } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import type {
  SolutionDirection,
  SolutionInterface,
  SolutionInterfaceKind,
  SolutionOperationKind,
} from "./solutionModel";

type OperationDraft = { name: string; operation_kind: SolutionOperationKind };

type Props = {
  componentName: string;
  interfaceDetail: SolutionInterface;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (
    interfaceId: string,
    patch: {
      name?: string;
      description?: string | null;
      direction?: SolutionDirection;
      interface_kind?: SolutionInterfaceKind | null;
      protocol?: string | null;
      technology?: string | null;
    },
  ) => void;
  onDelete: (interfaceId: string) => void;
  onSelectOperation: (operationId: string) => void;
  onAddOperation: (draft: OperationDraft) => void;
  onBack: () => void;
  onClose: () => void;
  onCollapse: () => void;
};

const EMPTY_DRAFT: OperationDraft = { name: "", operation_kind: "operation" };

export default function InterfaceEditorPanel({
  componentName,
  interfaceDetail,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onSelectOperation,
  onAddOperation,
  onBack,
  onClose,
  onCollapse,
}: Props) {
  const [name, setName] = useState(interfaceDetail.name);
  const [description, setDescription] = useState(interfaceDetail.description ?? "");
  const [direction, setDirection] = useState<SolutionDirection>(interfaceDetail.direction);
  const [kind, setKind] = useState<SolutionInterfaceKind | "">(interfaceDetail.interface_kind ?? "");
  const [protocol, setProtocol] = useState(interfaceDetail.protocol ?? "");
  const [technology, setTechnology] = useState(interfaceDetail.technology ?? "");
  const [draft, setDraft] = useState<OperationDraft>(EMPTY_DRAFT);

  const dirty =
    name !== interfaceDetail.name ||
    description !== (interfaceDetail.description ?? "") ||
    direction !== interfaceDetail.direction ||
    kind !== (interfaceDetail.interface_kind ?? "") ||
    protocol !== (interfaceDetail.protocol ?? "") ||
    technology !== (interfaceDetail.technology ?? "");

  function submitOperation(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) return;
    onAddOperation({ ...draft, name: draft.name.trim() });
    setDraft(EMPTY_DRAFT);
  }

  return (
    <aside className="architecture-relationship-panel solution-panel" aria-label="Interface details">
      <header>
        <div>
          <button type="button" className="solution-back-button" onClick={onBack}>‹ {componentName}</button>
          <p className="eyebrow">INTERFACE</p>
          <h3>{interfaceDetail.name}</h3>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Collapse interface inspector" onClick={onCollapse}>›</button>
          <button type="button" className="secondary-button" aria-label="Close interface details" onClick={onClose}>✕</button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {editable ? "Editable" : "Read-only"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>

      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Direction
        <select value={direction} disabled={!editable} onChange={(event) => setDirection(event.target.value as SolutionDirection)}>
          <option value="provided">Provided</option>
          <option value="required">Required</option>
        </select>
      </label>
      <label>
        Kind
        <select value={kind} disabled={!editable} onChange={(event) => setKind(event.target.value as SolutionInterfaceKind | "")}>
          <option value="">Unspecified</option>
          <option value="sync">Sync</option>
          <option value="async">Async</option>
        </select>
      </label>
      <label>
        Protocol
        <input value={protocol} disabled={!editable} onChange={(event) => setProtocol(event.target.value)} />
      </label>
      <label>
        Technology
        <input value={technology} disabled={!editable} onChange={(event) => setTechnology(event.target.value)} />
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
            onClick={() => onSave(interfaceDetail.object_id, {
              name,
              description,
              direction,
              interface_kind: kind || null,
              protocol,
              technology,
            })}
          >
            {busy ? "Saving…" : "Save interface"}
          </button>
          <button type="button" className="secondary-button architecture-danger" onClick={() => onDelete(interfaceDetail.object_id)}>
            Delete
          </button>
        </div>
      )}

      <section className="solution-operations-section">
        <div className="information-section-heading">
          <strong>Operations &amp; events</strong>
          <span className="item-count">{interfaceDetail.operations.length}</span>
        </div>
        {interfaceDetail.operations.length === 0 ? (
          <p className="architecture-topbar-hint">No operations yet.</p>
        ) : (
          <ul className="solution-operation-list">
            {interfaceDetail.operations.map((operation) => (
              <li key={operation.object_id}>
                <button type="button" onClick={() => onSelectOperation(operation.object_id)}>
                  <span>{operation.name}</span>
                  <small>{operation.operation_kind}</small>
                </button>
              </li>
            ))}
          </ul>
        )}

        {editable && (
          <form className="solution-operation-form" onSubmit={submitOperation}>
            <p className="studio-menu-caption">New operation or event</p>
            <label>
              Name
              <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label>
              Kind
              <select
                value={draft.operation_kind}
                onChange={(event) => setDraft({ ...draft, operation_kind: event.target.value as SolutionOperationKind })}
              >
                <option value="operation">Operation</option>
                <option value="event">Event</option>
                <option value="command">Command</option>
                <option value="query">Query</option>
              </select>
            </label>
            <button type="submit" disabled={busy || !draft.name.trim()}>Add operation</button>
          </form>
        )}
      </section>
    </aside>
  );
}
