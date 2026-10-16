import { useState, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import type { SolutionDesign, SolutionTrustBoundary } from "./solutionModel";

type Props = {
  design: SolutionDesign;
  boundary: SolutionTrustBoundary;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (
    trustId: string,
    patch: { name?: string; description?: string | null; security_level?: string | null },
  ) => void;
  onDelete: (trustId: string) => void;
  onContain: (sourceObjectId: string, trustId: string | null) => void;
  onCross: (interfaceId: string, trustId: string | null) => void;
  onSelectComponent: (componentId: string) => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

export default function TrustBoundaryEditorPanel({
  design,
  boundary,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onContain,
  onCross,
  onSelectComponent,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const [name, setName] = useState(boundary.name);
  const [securityLevel, setSecurityLevel] = useState(boundary.security_level ?? "");
  const [description, setDescription] = useState(boundary.description ?? "");

  const dirty =
    name !== boundary.name ||
    securityLevel !== (boundary.security_level ?? "") ||
    description !== (boundary.description ?? "");

  const contained = new Set(
    design.links
      .filter((link) => link.relationship_type === "contained_in" && link.target_object_id === boundary.object_id)
      .map((link) => link.source_object_id),
  );
  const crossing = new Set(
    design.links
      .filter((link) => link.relationship_type === "crosses" && link.target_object_id === boundary.object_id)
      .map((link) => link.source_object_id),
  );
  const interfaces = design.components.flatMap((component) =>
    component.interfaces.map((ui) => ({ ui, component })),
  );
  const systems = [...design.solution.members, ...design.solution.external_systems];

  const properties = (
    <>
      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Security level
        <input value={securityLevel} disabled={!editable} placeholder="public, private, restricted…" onChange={(event) => setSecurityLevel(event.target.value)} />
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
            onClick={() => onSave(boundary.object_id, { name, description, security_level: securityLevel })}
          >
            {busy ? "Saving…" : "Save boundary"}
          </button>
          <button type="button" className="secondary-button architecture-danger" onClick={() => onDelete(boundary.object_id)}>
            Delete
          </button>
        </div>
      )}
    </>
  );

  const relationships = (
    <>
      <section className="solution-interfaces-section">
        <div className="information-section-heading">
          <strong>Inside this boundary</strong>
          <span className="item-count">{contained.size}</span>
        </div>
        <ul className="solution-member-list">
          {design.components.map((component) => {
            const inside = contained.has(component.object_id);
            return (
              <li key={component.object_id} className={inside ? "selected" : ""}>
                <button type="button" className="solution-member-select" onClick={() => onSelectComponent(component.object_id)}>
                  <span aria-hidden="true">▣</span> {component.name}
                </button>
                {editable && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => onContain(component.object_id, inside ? null : boundary.object_id)}
                  >
                    {inside ? "Remove" : "Place"}
                  </button>
                )}
              </li>
            );
          })}
          {systems.map((system) => {
            const inside = contained.has(system.system_id);
            return (
              <li key={system.system_id} className={inside ? "selected" : ""}>
                <span><span aria-hidden="true">▧</span> {system.name}</span>
                {editable && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => onContain(system.system_id, inside ? null : boundary.object_id)}
                  >
                    {inside ? "Remove" : "Place"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </section>
      <section className="solution-interfaces-section">
        <div className="information-section-heading">
          <strong>Crossing flows</strong>
          <span className="item-count">{crossing.size}</span>
        </div>
        <ul className="solution-member-list">
          {interfaces.map(({ ui, component }) => {
            const crosses = crossing.has(ui.object_id);
            return (
              <li key={ui.object_id} className={crosses ? "selected" : ""}>
                <span>
                  <em className={`solution-direction direction-${ui.direction}`}>{ui.direction}</em> {ui.name}
                  <small> · {component.name}</small>
                </span>
                {editable && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => onCross(ui.object_id, crosses ? null : boundary.object_id)}
                  >
                    {crosses ? "Clear" : "Cross"}
                  </button>
                )}
              </li>
            );
          })}
          {interfaces.length === 0 && <p className="architecture-topbar-hint">No interfaces yet.</p>}
        </ul>
      </section>
    </>
  );

  return (
    <UnifiedInspector
      ariaLabel="Trust boundary details"
      eyebrow="TRUST BOUNDARY"
      title={boundary.name}
      identifier={boundary.object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse trust boundary inspector"
      closeLabel="Close trust boundary details"
      onCollapse={onCollapse}
      onClose={onClose}
      defaultTab="relationships"
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", count: contained.size + crossing.size, content: relationships },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
