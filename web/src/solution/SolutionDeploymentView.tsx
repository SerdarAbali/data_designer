import type { SolutionDesign } from "./solutionModel";
import { deploymentGroups, unassignedComponents } from "./solutionCanvasModel";

type Props = {
  design: SolutionDesign;
  editable: boolean;
  selectedDeploymentId: string | null;
  selectedComponentId: string | null;
  onSelectDeployment: (deploymentId: string) => void;
  onSelectComponent: (componentId: string) => void;
  onAddDeploymentNode: () => void;
  onAssignComponent: (componentId: string, deploymentId: string | null) => void;
};

export default function SolutionDeploymentView({
  design,
  editable,
  selectedDeploymentId,
  selectedComponentId,
  onSelectDeployment,
  onSelectComponent,
  onAddDeploymentNode,
  onAssignComponent,
}: Props) {
  const groups = deploymentGroups(design);
  const unassigned = unassignedComponents(design);

  return (
    <div className="solution-deployment" aria-label={`Deployment view for ${design.solution.name}`}>
      {groups.length === 0 ? (
        <div className="solution-container-empty" role="status">
          <span className="empty-icon">▦</span>
          <h3>No deployment nodes yet</h3>
          <p>Add a deployment node to allocate components to runtime infrastructure.</p>
          {editable && (
            <button type="button" onClick={onAddDeploymentNode}>+ Add deployment node</button>
          )}
        </div>
      ) : (
        <div className="solution-deployment-grid">
          {groups.map((group) => (
            <section
              key={group.key}
              className={`solution-deployment-node${group.node.object_id === selectedDeploymentId ? " selected" : ""}`}
              aria-label={`Deployment node ${group.node.name}`}
            >
              <header>
                <button type="button" className="solution-container-title" onClick={() => onSelectDeployment(group.node.object_id)}>
                  <span aria-hidden="true">▦</span>
                  <strong>{group.node.name}</strong>
                </button>
                <span className="solution-container-badges">
                  {group.node.environment && <em>{group.node.environment}</em>}
                  {group.node.hosting && <em>{group.node.hosting}</em>}
                  {group.node.technology && <em>{group.node.technology}</em>}
                </span>
              </header>
              <div className="solution-container-members">
                {group.components.length === 0 ? (
                  <p className="architecture-topbar-hint">No components deployed to this node.</p>
                ) : (
                  group.components.map((component) => (
                    <div key={component.object_id} className="solution-container-member">
                      <button
                        type="button"
                        className={`solution-member-chip${component.object_id === selectedComponentId ? " selected" : ""}`}
                        onClick={() => onSelectComponent(component.object_id)}
                      >
                        <span aria-hidden="true">▣</span>
                        {component.name}
                        {component.component_type && <small>{component.component_type}</small>}
                      </button>
                      {editable && (
                        <button
                          type="button"
                          className="solution-member-remove"
                          aria-label={`Unassign ${component.name}`}
                          onClick={() => onAssignComponent(component.object_id, null)}
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
              {group.repositories.length > 0 && (
                <div className="solution-container-repos">
                  <span className="solution-container-caption">Data stores</span>
                  {group.repositories.map((repository) => (
                    <span key={repository.object_id} className="solution-repo-chip">⛁ {repository.name}</span>
                  ))}
                </div>
              )}
              {editable && unassigned.length > 0 && (
                <label className="solution-container-assign">
                  Deploy component
                  <select
                    aria-label={`Deploy a component on ${group.node.name}`}
                    defaultValue=""
                    onChange={(event) => {
                      if (event.target.value) onAssignComponent(event.target.value, group.node.object_id);
                    }}
                  >
                    <option value="">Add component…</option>
                    {unassigned.map((component) => (
                      <option key={component.object_id} value={component.object_id}>{component.name}</option>
                    ))}
                  </select>
                </label>
              )}
            </section>
          ))}
        </div>
      )}

      {groups.length > 0 && unassigned.length > 0 && (
        <section className="solution-deployment-unassigned" aria-label="Unassigned components">
          <header>
            <span aria-hidden="true">◌</span>
            <strong>Unassigned components</strong>
          </header>
          <div className="solution-container-members">
            {unassigned.map((component) => (
              <button
                key={component.object_id}
                type="button"
                className={`solution-member-chip${component.object_id === selectedComponentId ? " selected" : ""}`}
                onClick={() => onSelectComponent(component.object_id)}
              >
                <span aria-hidden="true">▣</span>
                {component.name}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
