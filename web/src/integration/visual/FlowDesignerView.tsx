import type {
  FlowPhaseName,
  IntegrationMessageFlow,
} from "../integrationDesignModel";
import { PHASE_LABELS } from "../../architecturePhases";
import {
  FLOW_ROLE_LABELS,
  flowStages,
  phaseDirection,
  type FlowStage,
} from "../integrationViews";

const PHASE_ORDER: FlowPhaseName[] = [
  "request",
  "success-response",
  "async-response",
  "error-response",
];

const STAGE_ROLE_LABELS: Record<FlowStage["role"], string> = {
  system: "System",
  interface: "Interface",
  channel: "Channel",
  runtime: "Runtime",
  validation: "Validation",
  routing: "Routing decision",
  transformation: "Transformation",
  constant: "Constant",
  metadata: "Metadata",
};

type Props = {
  flow: IntegrationMessageFlow;
  selectedPhase: FlowPhaseName;
  onSelectPhase: (phase: FlowPhaseName) => void;
  onSelectStage: (stage: FlowStage, phase: FlowPhaseName) => void;
  onOpenContract: (contractId: string) => void;
  onOpenMapping: (phase: FlowPhaseName) => void;
};

export default function FlowDesignerView({
  flow,
  selectedPhase,
  onSelectPhase,
  onSelectStage,
  onOpenContract,
  onOpenMapping,
}: Props) {
  const phases = PHASE_ORDER.map((phase) =>
    flow.phases.find((item) => item.phase === phase),
  ).filter((item): item is IntegrationMessageFlow["phases"][number] => Boolean(item));

  if (phases.length === 0) {
    return (
      <section className="integration-flow" aria-label="Message flow">
        <p className="integration-empty-note">
          This contract has no configured request, response or error graphs yet.
        </p>
      </section>
    );
  }

  const active = phases.find((item) => item.phase === selectedPhase) ?? phases[0];

  return (
    <section className="integration-flow" aria-label="Message flow">
      <div className="integration-flow-tabs" role="tablist" aria-label="Contract phases">
        {phases.map((phase) => (
          <button
            key={phase.phase}
            type="button"
            role="tab"
            aria-selected={phase.phase === active.phase}
            className={phase.phase === active.phase ? "active" : ""}
            onClick={() => onSelectPhase(phase.phase)}
          >
            {PHASE_LABELS[phase.phase]}
            {!phase.configured && <em className="integration-flow-tab-warning">unconfigured</em>}
          </button>
        ))}
      </div>

      {phases.map((phase) => {
        const stages = flowStages(flow, phase);
        const direction = phaseDirection(phase.phase);
        return (
          <article key={phase.phase} className="integration-flow-lane" hidden={phase.phase !== active.phase}>
            <header className="integration-flow-lane-head">
              <div>
                <strong>{PHASE_LABELS[phase.phase]}</strong>
                <span className="integration-flow-direction">
                  {direction === "request" ? "outbound request" : "return path"}
                </span>
              </div>
              <div className="integration-flow-lane-meta">
                <span>{phase.transformation_count} transformation{phase.transformation_count === 1 ? "" : "s"}</span>
                <span>
                  {phase.mapped_target_count}/{phase.target_field_count} target fields mapped
                </span>
                {phase.unmapped_required_fields.length > 0 && (
                  <span className="integration-flow-gap">
                    {phase.unmapped_required_fields.length} required unmapped
                  </span>
                )}
                <button type="button" onClick={() => onOpenMapping(phase.phase)}>
                  Open Mapping &amp; Tests
                </button>
              </div>
            </header>

            {!phase.configured ? (
              <p className="integration-flow-incomplete" role="status">
                No graph is configured for this phase yet. Stages appear once mappings exist.
              </p>
            ) : (
              <div className="integration-flow-stages" role="list" aria-label={`${PHASE_LABELS[phase.phase]} stages`}>
                {stages.map((stage, index) => (
                  <div key={`${stage.id}-${index}`} className="integration-flow-step" role="listitem">
                    {index > 0 && <span className="integration-flow-arrow" aria-hidden="true">→</span>}
                    <button
                      type="button"
                      className={`integration-flow-stage tone-${stage.role}${stage.metadata ? " is-metadata" : ""}${
                        stage.configured ? "" : " is-unconfigured"
                      }`}
                      onClick={() => onSelectStage(stage, phase.phase)}
                    >
                      <span className="integration-flow-stage-role">
                        {stage.metadata ? `${STAGE_ROLE_LABELS[stage.role]} · metadata` : STAGE_ROLE_LABELS[stage.role]}
                      </span>
                      <strong>{stage.label}</strong>
                      {stage.detail && <span className="integration-flow-stage-detail">{stage.detail}</span>}
                      {!stage.configured && <em className="integration-flow-stage-warning">Not configured</em>}
                    </button>
                  </div>
                ))}
              </div>
            )}

            {phase.unmapped_required_fields.length > 0 && (
              <p className="integration-flow-unmapped">
                Unmapped required target fields: {phase.unmapped_required_fields.join(", ")}
              </p>
            )}
          </article>
        );
      })}

      <div className="integration-flow-footer">
        <span>
          Flow stages are projections of the stored graphs and contract specification; nothing is fabricated.
        </span>
        <button type="button" onClick={() => onOpenContract(flow.contract.id)}>
          Open contract in Mapping &amp; Tests
        </button>
      </div>
      <p className="integration-flow-hint">
        Roles: {Object.values(FLOW_ROLE_LABELS).join(" · ")}
      </p>
    </section>
  );
}
