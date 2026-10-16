import {
  INTERACTION_TYPE_LABELS,
  PATTERN_LABELS,
  STATUS_LABELS,
  type IntegrationContractDetail,
  type IntegrationInterfaceSummary,
  type IntegrationMessageFlow,
} from "../integrationDesignModel";
import { CHANNEL_LABELS } from "../integrationViews";

const OPERATION_KIND_LABELS: Record<string, string> = {
  operation: "Operation",
  event: "Event",
  command: "Command",
  query: "Query",
};

const PHASE_RANGES: { key: "has_request_graph" | "has_response_graph" | "has_error_graph"; label: string }[] = [
  { key: "has_request_graph", label: "Request" },
  { key: "has_response_graph", label: "Response" },
  { key: "has_error_graph", label: "Error" },
];

function InterfaceCard({
  iface,
  role,
  onSelect,
}: {
  iface: IntegrationInterfaceSummary | null;
  role: "Producer" | "Consumer";
  onSelect: (objectId: string) => void;
}) {
  if (!iface) {
    return (
      <article className="integration-interface-card is-empty" aria-label={`${role} interface`}>
        <header>
          <span className="integration-interface-role">{role}</span>
        </header>
        <p className="integration-empty-note">No {role.toLowerCase()} interface linked yet.</p>
      </article>
    );
  }
  return (
    <article className="integration-interface-card" aria-label={`${role} interface ${iface.name}`}>
      <header>
        <span className="integration-interface-role">{role}</span>
        <button type="button" onClick={() => onSelect(iface.object_id)}>
          Inspect
        </button>
      </header>
      <strong>{iface.name}</strong>
      <dl className="integration-interface-facts">
        <div>
          <dt>Direction</dt>
          <dd>{iface.direction ?? "Not set"}</dd>
        </div>
        <div>
          <dt>Style</dt>
          <dd>{iface.interface_kind ?? "Not set"}</dd>
        </div>
        <div>
          <dt>Protocol</dt>
          <dd>{iface.protocol ?? "Not set"}</dd>
        </div>
        <div>
          <dt>Technology</dt>
          <dd>{iface.technology ?? "Not set"}</dd>
        </div>
        <div>
          <dt>Component</dt>
          <dd>{iface.component_name ?? "Unassigned"}</dd>
        </div>
      </dl>
      <div className="integration-interface-operations">
        <span className="integration-subheading">
          Operations, commands, queries &amp; events ({iface.operations.length})
        </span>
        {iface.operations.length === 0 ? (
          <p className="integration-empty-note">No operations are modelled on this interface.</p>
        ) : (
          <ul>
            {iface.operations.map((operation) => (
              <li key={operation.object_id}>
                <em>{OPERATION_KIND_LABELS[operation.operation_kind] ?? operation.operation_kind}</em>
                <span>{operation.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

type Props = {
  detail: IntegrationContractDetail;
  flow: IntegrationMessageFlow;
  onSelectInterface: (objectId: string) => void;
  onSelectSystem: (systemId: string) => void;
  onOpenContract: (contractId: string) => void;
  onOpenMapping: (phase: IntegrationMessageFlow["phases"][number]["phase"]) => void;
};

export default function InterfaceChannelView({
  detail,
  flow,
  onSelectInterface,
  onSelectSystem,
  onOpenContract,
  onOpenMapping,
}: Props) {
  const contract = detail.contract;
  const mediated = Boolean(contract.source.is_runtime || contract.target.is_runtime);

  return (
    <section className="integration-interface-view" aria-label="Interface and channel architecture">
      <div className="integration-interface-systems">
        <button type="button" onClick={() => onSelectSystem(contract.source.system_id)}>
          <span>Producer system</span>
          <strong>{contract.source.system_name}</strong>
          <em>{contract.source.object_name}</em>
        </button>
        <span className="integration-interface-connector" aria-hidden="true">→</span>
        <button type="button" onClick={() => onSelectSystem(contract.target.system_id)}>
          <span>Consumer system</span>
          <strong>{contract.target.system_name}</strong>
          <em>{contract.target.object_name}</em>
        </button>
      </div>

      <div className="integration-interface-grid">
        <InterfaceCard iface={detail.source_interface} role="Producer" onSelect={onSelectInterface} />

        <div className="integration-contract-bridge">
          <div className="integration-bridge-node">
            <span className="integration-bridge-label">Contract</span>
            <button type="button" onClick={() => onOpenContract(contract.id)}>
              <strong>{contract.name}</strong>
            </button>
            <dl>
              <div>
                <dt>Interaction</dt>
                <dd>{INTERACTION_TYPE_LABELS[contract.interaction_type] ?? contract.interaction_type}</dd>
              </div>
              <div>
                <dt>Pattern</dt>
                <dd>{contract.pattern ? PATTERN_LABELS[contract.pattern] ?? contract.pattern : "Unspecified"}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{STATUS_LABELS[contract.status] ?? contract.status}</dd>
              </div>
              <div>
                <dt>Channel</dt>
                <dd>{flow.channel_kind ? CHANNEL_LABELS[flow.channel_kind] : "Not configured"}</dd>
              </div>
              <div>
                <dt>Runtime</dt>
                <dd>{mediated ? "Mediated by Integration Runtime" : "Direct connection"}</dd>
              </div>
              <div>
                <dt>Revision</dt>
                <dd>r{contract.revision}</dd>
              </div>
            </dl>
            <div className="integration-bridge-phases">
              {PHASE_RANGES.map((phase) => (
                <span
                  key={phase.key}
                  className={`integration-phase-chip${contract[phase.key] ? "" : " is-empty"}`}
                >
                  {phase.label}
                </span>
              ))}
            </div>
          </div>
        </div>

        <InterfaceCard iface={detail.target_interface} role="Consumer" onSelect={onSelectInterface} />
      </div>

      <div className="integration-interface-phases">
        <span className="integration-subheading">Contract phases</span>
        <div className="integration-phase-grid">
          {detail.phases.map((phase) => (
            <button
              key={phase.phase}
              type="button"
              className={`integration-phase-card${phase.configured ? "" : " is-empty"}`}
              onClick={() => onOpenMapping(phase.phase)}
            >
              <strong>{phase.phase.replace("-", " ")}</strong>
              {phase.configured ? (
                <span>
                  {phase.mapped_target_count}/{phase.target_field_count} mapped ·{" "}
                  {phase.transformation_count} transformation{phase.transformation_count === 1 ? "" : "s"}
                </span>
              ) : (
                <span>No graph configured yet</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
