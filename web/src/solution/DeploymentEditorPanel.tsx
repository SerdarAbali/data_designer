import { useState, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import type { SolutionDeploymentNode, SolutionDesign } from "./solutionModel";

type Props = {
  design: SolutionDesign;
  node: SolutionDeploymentNode;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (
    deploymentId: string,
    patch: {
      name?: string;
      description?: string | null;
      technology?: string | null;
      environment?: string | null;
      hosting?: string | null;
    },
  ) => void;
  onDelete: (deploymentId: string) => void;
  onAssignComponent: (componentId: string, deploymentId: string | null) => void;
  onSelectComponent: (componentId: string) => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

export default function DeploymentEditorPanel({
  design,
  node,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onAssignComponent,
  onSelectComponent,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const [name, setName] = useState(node.name);
  const [environment, setEnvironment] = useState(node.environment ?? "");
  const [hosting, setHosting] = useState(node.hosting ?? "");
  const [technology, setTechnology] = useState(node.technology ?? "");
  const [description, setDescription] = useState(node.description ?? "");

  const dirty =
    name !== node.name ||
    environment !== (node.environment ?? "") ||
    hosting !== (node.hosting ?? "") ||
    technology !== (node.technology ?? "") ||
    description !== (node.description ?? "");

  const assigned = new Set(
    design.links
      .filter((link) => link.relationship_type === "deployed_on" && link.target_object_id === node.object_id)
      .map((link) => link.source_object_id),
  );

  const properties = (
    <>
      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Environment
        <input value={environment} disabled={!editable} placeholder="production, staging…" onChange={(event) => setEnvironment(event.target.value)} />
      </label>
      <label>
        Hosting
        <input value={hosting} disabled={!editable} placeholder="cloud, on-premise…" onChange={(event) => setHosting(event.target.value)} />
      </label>
      <label>
        Runtime / technology
        <input value={technology} disabled={!editable} placeholder="Kubernetes, VM…" onChange={(event) => setTechnology(event.target.value)} />
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
            onClick={() => onSave(node.object_id, {
              name,
              description,
              technology,
              environment,
              hosting,
            })}
          >
            {busy ? "Saving…" : "Save node"}
          </button>
          <button type="button" className="secondary-button architecture-danger" onClick={() => onDelete(node.object_id)}>
            Delete
          </button>
        </div>
      )}
    </>
  );

  const relationships = (
    <>
      <div className="information-section-heading">
        <strong>Deployed components</strong>
        <span className="item-count">{assigned.size}</span>
      </div>
      <ul className="solution-member-list">
        {design.components.map((component) => {
          const linked = assigned.has(component.object_id);
          return (
            <li key={component.object_id} className={linked ? "selected" : ""}>
              <button type="button" className="solution-member-select" onClick={() => onSelectComponent(component.object_id)}>
                {component.name}
              </button>
              {editable && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onAssignComponent(component.object_id, linked ? null : node.object_id)}
                >
                  {linked ? "Remove" : "Deploy"}
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
      ariaLabel="Deployment node details"
      eyebrow="DEPLOYMENT NODE"
      title={node.name}
      identifier={node.object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse deployment inspector"
      closeLabel="Close deployment details"
      onCollapse={onCollapse}
      onClose={onClose}
      defaultTab="relationships"
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Allocation", count: assigned.size, content: relationships },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}
