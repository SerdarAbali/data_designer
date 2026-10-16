import type { SolutionDesign } from "./solutionModel";
import { trustGroups } from "./solutionCanvasModel";

type Props = {
  design: SolutionDesign;
  editable: boolean;
  selectedTrustId: string | null;
  selectedComponentId: string | null;
  onSelectTrust: (trustId: string) => void;
  onSelectComponent: (componentId: string) => void;
  onAddTrustBoundary: () => void;
};

export default function SolutionTrustView({
  design,
  editable,
  selectedTrustId,
  selectedComponentId,
  onSelectTrust,
  onSelectComponent,
  onAddTrustBoundary,
}: Props) {
  const groups = trustGroups(design);

  return (
    <div className="solution-trust" aria-label={`Trust boundaries for ${design.solution.name}`}>
      {groups.length === 0 ? (
        <div className="solution-container-empty" role="status">
          <span className="empty-icon">⛨</span>
          <h3>No trust boundaries yet</h3>
          <p>Add a trust boundary and place components or systems inside it.</p>
          {editable && (
            <button type="button" onClick={onAddTrustBoundary}>+ Add trust boundary</button>
          )}
        </div>
      ) : (
        <div className="solution-trust-grid">
          {groups.map((group) => (
            <section
              key={group.key}
              className={`solution-trust-node${group.boundary.object_id === selectedTrustId ? " selected" : ""}`}
              aria-label={`Trust boundary ${group.boundary.name}`}
            >
              <header>
                <button type="button" className="solution-container-title" onClick={() => onSelectTrust(group.boundary.object_id)}>
                  <span aria-hidden="true">⛨</span>
                  <strong>{group.boundary.name}</strong>
                </button>
                {group.boundary.security_level && <em className="solution-security-badge">{group.boundary.security_level}</em>}
              </header>

              <div className="solution-container-members">
                {group.components.length === 0 && group.systems.length === 0 ? (
                  <p className="architecture-topbar-hint">Nothing placed inside this boundary yet.</p>
                ) : (
                  <>
                    {group.components.map((component) => (
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
                    {group.systems.map((system) => (
                      <span key={system.systemId} className="solution-member-chip system">
                        <span aria-hidden="true">▧</span>
                        {system.name}
                        <small>{system.kind}</small>
                      </span>
                    ))}
                  </>
                )}
              </div>

              {group.crossings.length > 0 && (
                <div className="solution-trust-crossings">
                  <span className="solution-container-caption">Crosses boundary</span>
                  {group.crossings.map((crossing) => (
                    <span key={crossing.interface.object_id} className="solution-crossing-chip">
                      <span aria-hidden="true">⇄</span>
                      {crossing.interface.name}
                      {crossing.component && <small>{crossing.component.name}</small>}
                    </span>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
