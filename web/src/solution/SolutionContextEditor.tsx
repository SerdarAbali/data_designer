import { useEffect, useState, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import type { SolutionDesign } from "./solutionModel";

type CatalogSystem = { id: string; name: string; kind: string };

type Props = {
  design: SolutionDesign;
  systems: CatalogSystem[];
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  selectedSystemId: string | null;
  onSave: (patch: { name?: string; owner?: string | null; description?: string | null }) => void;
  onAddMember: (systemId: string) => void;
  onRemoveMember: (systemId: string) => void;
  onSelectSystem: (systemId: string) => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

export default function SolutionContextEditor({
  design,
  systems,
  editable,
  stateName,
  saveStatus,
  busy,
  selectedSystemId,
  onSave,
  onAddMember,
  onRemoveMember,
  onSelectSystem,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const [name, setName] = useState(design.solution.name);
  const [owner, setOwner] = useState(design.solution.owner ?? "");
  const [description, setDescription] = useState(design.solution.description ?? "");
  const [memberToAdd, setMemberToAdd] = useState("");

  useEffect(() => {
    setName(design.solution.name);
    setOwner(design.solution.owner ?? "");
    setDescription(design.solution.description ?? "");
  }, [design.solution]);

  const dirty =
    name !== design.solution.name ||
    owner !== (design.solution.owner ?? "") ||
    description !== (design.solution.description ?? "");

  const memberIds = new Set(design.solution.members.map((member) => member.system_id));
  const available = systems.filter((system) => !memberIds.has(system.id));

  const properties = (
    <>
      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Owner
        <input value={owner} disabled={!editable} placeholder="Optional" onChange={(event) => setOwner(event.target.value)} />
      </label>
      <label>
        Description
        <textarea value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} />
      </label>
      {editable && (
        <div className="solution-panel-actions">
          <button type="button" disabled={!dirty || busy || !name.trim()} onClick={() => onSave({ name, owner, description })}>
            {busy ? "Saving…" : "Save solution"}
          </button>
        </div>
      )}
    </>
  );

  const relationships = (
    <section className="solution-members">
      <div className="information-section-heading">
        <strong>Member systems</strong>
        <span className="item-count">{design.solution.members.length}</span>
      </div>
      {design.solution.members.length === 0 ? (
        <p className="architecture-topbar-hint">No member systems yet.</p>
      ) : (
        <ul className="solution-member-list">
          {design.solution.members.map((member) => (
            <li key={member.system_id} className={member.system_id === selectedSystemId ? "selected" : ""}>
              <button type="button" className="solution-member-select" onClick={() => onSelectSystem(member.system_id)}>
                <span>{member.name}</span>
                <small>{member.kind}</small>
              </button>
              {editable && (
                <button type="button" className="secondary-button" onClick={() => onRemoveMember(member.system_id)}>Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {design.solution.external_systems.length > 0 && (
        <div className="solution-external">
          <strong>External systems on the canvas</strong>
          <ul>
            {design.solution.external_systems.map((system) => (
              <li key={system.system_id} className={system.system_id === selectedSystemId ? "selected" : ""}>
                <button type="button" className="solution-member-select" onClick={() => onSelectSystem(system.system_id)}>
                  {system.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {editable && (
        <div className="solution-member-add">
          <select
            aria-label="Add a member system"
            value={memberToAdd}
            onChange={(event) => setMemberToAdd(event.target.value)}
          >
            <option value="">Add a system…</option>
            {available.map((system) => (
              <option key={system.id} value={system.id}>{system.name}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !memberToAdd}
            onClick={() => {
              onAddMember(memberToAdd);
              setMemberToAdd("");
            }}
          >
            Add member
          </button>
        </div>
      )}
    </section>
  );

  return (
    <UnifiedInspector
      ariaLabel="Solution context"
      eyebrow="SOLUTION"
      title={design.solution.name}
      identifier={design.solution.solution_object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse solution inspector"
      closeLabel="Close solution context"
      onCollapse={onCollapse}
      onClose={onClose}
      defaultTab="relationships"
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Membership", count: design.solution.members.length, content: relationships },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
