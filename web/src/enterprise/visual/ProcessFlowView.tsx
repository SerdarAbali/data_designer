import type {
  EnterpriseImpact,
  EnterpriseModel,
  ProcessImpact,
} from "../enterpriseModel";
import { processFlows } from "./enterpriseCanvasModel";

type Props = {
  model: EnterpriseModel;
  processImpact: ProcessImpact;
  impact: EnterpriseImpact | null;
  selectedObjectId: string | null;
  onSelectObject: (objectId: string) => void;
};

const CHANGE_LABELS: Record<string, string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  reused: "Reused",
};

export default function ProcessFlowView({
  model,
  processImpact,
  impact,
  selectedObjectId,
  onSelectObject,
}: Props) {
  const flows = processFlows(model, processImpact, impact);

  return (
    <div className="enterprise-process-view" aria-label="Process and value-stream view">
      {flows.length === 0 ? (
        <p className="architecture-topbar-hint">No processes recorded yet.</p>
      ) : (
        <div className="enterprise-process-flows">
          {flows.map((flow) => (
            <section key={flow.process.object_id} className="enterprise-process-flow">
              <header className="enterprise-card-head">
                <button
                  type="button"
                  className="enterprise-card-title"
                  onClick={() => onSelectObject(flow.process.object_id)}
                >
                  {flow.process.name}
                </button>
                {flow.process.process_type === "value_stream" && (
                  <span className="enterprise-badge">value stream</span>
                )}
                {flow.impacted && (
                  <span className="enterprise-badge enterprise-badge-warn">impacted</span>
                )}
                {flow.change && (
                  <span className={`enterprise-badge change-${flow.change}`}>
                    {CHANGE_LABELS[flow.change] ?? flow.change}
                  </span>
                )}
              </header>

              <div className="enterprise-process-row">
                <div className="enterprise-process-column">
                  <span className="enterprise-process-column-label">Capabilities</span>
                  {flow.capabilities.map((capability) => (
                    <button
                      key={capability.object_id}
                      type="button"
                      className={`enterprise-flow-chip${capability.object_id === selectedObjectId ? " selected" : ""}`}
                      onClick={() => onSelectObject(capability.object_id)}
                    >
                      {capability.name}
                    </button>
                  ))}
                  {flow.capabilities.length === 0 && (
                    <em className="enterprise-flow-missing">no linked capability</em>
                  )}
                </div>
                <span className="enterprise-flow-arrow" aria-hidden="true">→</span>
                <div className="enterprise-process-column enterprise-process-node">
                  <span className="enterprise-process-column-label">Process</span>
                  <button
                    type="button"
                    className="enterprise-flow-chip enterprise-flow-chip-primary"
                    onClick={() => onSelectObject(flow.process.object_id)}
                  >
                    {flow.process.name}
                  </button>
                </div>
                <span className="enterprise-flow-arrow" aria-hidden="true">→</span>
                <div className="enterprise-process-column">
                  <span className="enterprise-process-column-label">Supporting applications</span>
                  {flow.applications.map((application) => (
                    <span key={application.object_id} className="enterprise-flow-chip application">
                      {application.name}
                    </span>
                  ))}
                  {flow.applications.length === 0 && (
                    <em className="enterprise-flow-missing">no supporting system</em>
                  )}
                </div>
              </div>

              <div className="enterprise-process-meta">
                {flow.requirements.length > 0 && (
                  <span className="enterprise-process-meta-group">
                    <strong>Requirements</strong>
                    {flow.requirements.map((requirement) => (
                      <button
                        key={requirement.object_id}
                        type="button"
                        className="enterprise-link-endpoint"
                        onClick={() => onSelectObject(requirement.object_id)}
                      >
                        {requirement.name}
                      </button>
                    ))}
                  </span>
                )}
                {flow.owner && (
                  <span className="enterprise-process-meta-group">
                    <strong>Owner</strong>
                    <button
                      type="button"
                      className="enterprise-link-endpoint"
                      onClick={() => onSelectObject(flow.owner!.object_id)}
                    >
                      {flow.owner.name}
                    </button>
                  </span>
                )}
                {flow.governedBy.length > 0 && (
                  <span className="enterprise-process-meta-group">
                    <strong>Governed by</strong>
                    {flow.governedBy.map((principle) => (
                      <button
                        key={principle.object_id}
                        type="button"
                        className="enterprise-link-endpoint"
                        onClick={() => onSelectObject(principle.object_id)}
                      >
                        {principle.name}
                      </button>
                    ))}
                  </span>
                )}
              </div>

              <p className="enterprise-flow-note" role="note">
                Ordered process steps are not modeled. This flow reflects the stored
                capability, application, role and governance relationships only.
              </p>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
