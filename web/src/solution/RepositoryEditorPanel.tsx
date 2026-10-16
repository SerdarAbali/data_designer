import { useState, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import type { SolutionDesign, SolutionRepository } from "./solutionModel";

type Props = {
  design: SolutionDesign;
  repository: SolutionRepository;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (
    repositoryId: string,
    patch: {
      name?: string;
      description?: string | null;
      owner?: string | null;
      repository_type?: string | null;
      technology?: string | null;
    },
  ) => void;
  onDelete: (repositoryId: string) => void;
  onLinkComponent: (componentId: string, repositoryId: string | null) => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

export default function RepositoryEditorPanel({
  design,
  repository,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onLinkComponent,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const [name, setName] = useState(repository.name);
  const [owner, setOwner] = useState(repository.owner ?? "");
  const [repositoryType, setRepositoryType] = useState(repository.repository_type ?? "");
  const [technology, setTechnology] = useState(repository.technology ?? "");
  const [description, setDescription] = useState(repository.description ?? "");

  const dirty =
    name !== repository.name ||
    owner !== (repository.owner ?? "") ||
    repositoryType !== (repository.repository_type ?? "") ||
    technology !== (repository.technology ?? "") ||
    description !== (repository.description ?? "");

  const componentByInterface = new Map<string, string>();
  for (const component of design.components) {
    for (const ui of component.interfaces) componentByInterface.set(ui.object_id, component.object_id);
  }
  const usingComponents = new Set(
    design.links
      .filter((link) => link.relationship_type === "uses_repository" && link.target_object_id === repository.object_id)
      .map((link) => componentByInterface.get(link.source_object_id) ?? link.source_object_id),
  );

  const properties = (
    <>
      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Type
        <input value={repositoryType} disabled={!editable} placeholder="relational, document…" onChange={(event) => setRepositoryType(event.target.value)} />
      </label>
      <label>
        Technology
        <input value={technology} disabled={!editable} placeholder="PostgreSQL…" onChange={(event) => setTechnology(event.target.value)} />
      </label>
      <label>
        Owner
        <input value={owner} disabled={!editable} onChange={(event) => setOwner(event.target.value)} />
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
            onClick={() => onSave(repository.object_id, {
              name,
              description,
              owner,
              repository_type: repositoryType || null,
              technology,
            })}
          >
            {busy ? "Saving…" : "Save repository"}
          </button>
          <button type="button" className="secondary-button architecture-danger" onClick={() => onDelete(repository.object_id)}>
            Delete
          </button>
        </div>
      )}
    </>
  );

  const relationships = (
    <>
      <div className="information-section-heading">
        <strong>Used by components</strong>
        <span className="item-count">{usingComponents.size}</span>
      </div>
      <ul className="solution-member-list">
        {design.components.map((component) => {
          const linked = usingComponents.has(component.object_id);
          return (
            <li key={component.object_id} className={linked ? "selected" : ""}>
              <span>{component.name}</span>
              {editable && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onLinkComponent(component.object_id, linked ? null : repository.object_id)}
                >
                  {linked ? "Detach" : "Use"}
                </button>
              )}
            </li>
          );
        })}
        {design.components.length === 0 && <p className="architecture-topbar-hint">No components yet.</p>}
      </ul>
    </>
  );

  return (
    <UnifiedInspector
      ariaLabel="Repository details"
      eyebrow="DATA REPOSITORY"
      title={repository.name}
      identifier={repository.object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse repository inspector"
      closeLabel="Close repository details"
      onCollapse={onCollapse}
      onClose={onClose}
      defaultTab="relationships"
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", count: usingComponents.size, content: relationships },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
