import { useMemo, useState } from "react";

import {
  CONFORMANCE_LABELS,
  type IntegrationScenarioSequence,
  type IntegrationSequence,
} from "../integrationDesignModel";
import { SEQUENCE_CATEGORY_LABELS, sequenceGroups } from "../integrationViews";

type Props = {
  sequence: IntegrationSequence;
  loading: boolean;
  selectedScenarioId: string | null;
  onSelectScenario: (scenarioId: string) => void;
  onOpenScenarios: () => void;
};

function statusBadge(scenario: IntegrationScenarioSequence) {
  return (
    <span className={`integration-badge integration-conformance-${scenario.status}`}>
      {CONFORMANCE_LABELS[scenario.status]}
    </span>
  );
}

export default function IntegrationSequenceView({
  sequence,
  loading,
  selectedScenarioId,
  onSelectScenario,
  onOpenScenarios,
}: Props) {
  const groups = useMemo(() => sequenceGroups(sequence), [sequence]);
  const [localSelection, setLocalSelection] = useState<string | null>(null);
  const activeId = selectedScenarioId ?? localSelection ?? sequence.scenarios[0]?.id ?? null;
  const active = sequence.scenarios.find((item) => item.id === activeId) ?? sequence.scenarios[0] ?? null;

  function choose(id: string) {
    setLocalSelection(id);
    onSelectScenario(id);
  }

  if (loading) {
    return <p className="architecture-topbar-hint">Loading sequence…</p>;
  }
  if (sequence.scenarios.length === 0) {
    return (
      <div className="integration-sequence">
        <div className="integration-detail-head">
          <div>
            <h3>Scenario &amp; Sequence</h3>
            <p className="architecture-topbar-hint">
              No scenarios reference {sequence.contract_name} yet.
            </p>
          </div>
          <button type="button" className="primary-button" onClick={onOpenScenarios}>
            Open sequence designer
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="integration-sequence">
      <div className="integration-detail-head">
        <div>
          <h3>Scenario &amp; Sequence</h3>
          <p className="architecture-topbar-hint">
            Ordered interactions projected from the scenario documents stored against {sequence.contract_name} ·
            revision {sequence.revision}.
          </p>
        </div>
        <button type="button" className="primary-button" onClick={onOpenScenarios}>
          Open sequence designer
        </button>
      </div>

      <div className="integration-sequence-body">
        <nav className="integration-sequence-list" aria-label="Scenarios">
          {groups.map((group) => (
            <section key={group.key} className="integration-scenario-group">
              <div className="information-section-heading">
                <strong>{SEQUENCE_CATEGORY_LABELS[group.key] ?? group.label}</strong>
                <span className="item-count">{group.items.length}</span>
              </div>
              <ul>
                {group.items.map((scenario) => (
                  <li key={scenario.id}>
                    <button
                      type="button"
                      className={scenario.id === active?.id ? "active" : ""}
                      onClick={() => choose(scenario.id)}
                    >
                      <span className="integration-scenario-name">{scenario.name}</span>
                      {statusBadge(scenario)}
                      {scenario.outdated && <em className="integration-outdated">outdated</em>}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </nav>

        {active && (
          <article className="integration-sequence-diagram" aria-label={`Sequence ${active.name}`}>
            <header className="integration-sequence-head">
              <div>
                <strong>{active.name}</strong>
                <span className="architecture-topbar-hint">
                  {SEQUENCE_CATEGORY_LABELS[active.category] ?? active.category} · {active.step_count} step
                  {active.step_count === 1 ? "" : "s"} · r{active.revision}
                </span>
              </div>
              <div className="integration-sequence-head-badges">
                {statusBadge(active)}
                {active.outdated && <em className="integration-outdated">outdated</em>}
              </div>
            </header>

            <div className="integration-lifelines">
              {active.participants.map((participant) => (
                <div
                  key={participant.id}
                  className={`integration-lifeline${participant.is_runtime ? " is-runtime" : ""}`}
                >
                  <span>{participant.label}</span>
                  <em>{participant.kind}</em>
                </div>
              ))}
              {active.participants.length === 0 && (
                <p className="architecture-topbar-hint">This scenario records no participants.</p>
              )}
            </div>

            <ol className="integration-interactions">
              {active.interactions.map((interaction, index) => (
                <li key={interaction.id} className={interaction.contract_step ? "is-contract" : ""}>
                  <span className="integration-interaction-index">{index + 1}</span>
                  <span className="integration-interaction-label">{interaction.label}</span>
                  {interaction.phase && (
                    <span className="integration-phase-chip">{interaction.phase}</span>
                  )}
                  {(interaction.from_id || interaction.to_id) && (
                    <span className="integration-interaction-route">
                      {interaction.from_id ?? "?"} → {interaction.to_id ?? "?"}
                    </span>
                  )}
                </li>
              ))}
              {active.interactions.length === 0 && (
                <p className="architecture-topbar-hint">No interactions recorded.</p>
              )}
            </ol>
          </article>
        )}
      </div>
    </div>
  );
}
