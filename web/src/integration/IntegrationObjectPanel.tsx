import { architectureFactLabel } from "../architectureFacts";
import EvidencePanel from "../components/architecture/EvidencePanel";
import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import {
  contractMediation,
  INTERACTION_TYPE_LABELS,
  PATTERN_LABELS,
  STATUS_LABELS,
  type IntegrationContractSummary,
  type IntegrationFactValue,
  type IntegrationInterfaceSummary,
} from "./integrationDesignModel";
import type { IntegrationTopologyNode } from "./integrationViews";

type Props = {
  node: IntegrationTopologyNode;
  workspaceId: string;
  stateId: string | null;
  interfaces: IntegrationInterfaceSummary[];
  contracts: IntegrationContractSummary[];
  onOpenContract: (contractId: string) => void;
  onOpenCatalog?: () => void;
  onNavigateTrace?: (node: TraceObjectRef) => void;
  onClose: () => void;
  /** Current is read-only, so evidence is display-only there. */
  readOnly?: boolean;
};

const KIND_LABELS: Record<IntegrationTopologyNode["kind"], string> = {
  system: "System",
  runtime: "Integration runtime",
  solution: "Solution component",
  interface: "Interface",
  contract: "Contract",
};

function fact(label: string, value: string | null | undefined) {
  return { label, value: value && value.length > 0 ? value : "—" };
}

/**
 * Effective fact label. When a Candidate/Target state overrides the canonical
 * baseline the difference is spelled out so the inspector never hides it.
 */
function factValueText(value: IntegrationFactValue): string {
  const effective = architectureFactLabel(value.value);
  if (!value.overridden) return effective;
  return `${effective} · override (baseline: ${architectureFactLabel(value.canonical)})`;
}

export default function IntegrationObjectPanel({
  node,
  workspaceId,
  stateId,
  interfaces,
  contracts,
  onOpenContract,
  onOpenCatalog,
  onNavigateTrace,
  onClose,
  readOnly = false,
}: Props) {
  const iface = node.kind === "interface" ? interfaces.find((item) => item.object_id === node.refId) : null;
  const contract = node.kind === "contract" ? contracts.find((item) => item.id === node.refId) : null;
  const linkedContracts =
    node.kind === "system" || node.kind === "runtime"
      ? contracts.filter(
          (item) => item.source.system_id === node.refId || item.target.system_id === node.refId,
        )
      : [];

  const mediation = contract ? contractMediation(contract) : null;

  const facts =
    node.kind === "interface" && iface
      ? [
          fact("Direction", iface.direction),
          fact("Style", iface.interface_kind),
          fact("Protocol", iface.protocol),
          fact("Technology", iface.technology),
          fact("Component", iface.component_name),
          fact("Operations", String(iface.operations.length)),
        ]
      : node.kind === "contract" && contract
        ? [
            fact("Interaction", INTERACTION_TYPE_LABELS[contract.interaction_type] ?? contract.interaction_type),
            fact("Pattern", contract.pattern ? PATTERN_LABELS[contract.pattern] ?? contract.pattern : null),
            fact("Implementation", contract.implementation_status),
            fact("Lifecycle stage", factValueText(contract.lifecycle_stage)),
            fact("Operational status", factValueText(contract.operational_status)),
            fact("Environment scope", factValueText(contract.environment_scope)),
            fact("Status", STATUS_LABELS[contract.status] ?? contract.status),
            fact("Revision", `r${contract.revision}`),
            fact("Business source", `${contract.source.system_name} · ${contract.source.object_name}`),
            // Mediation facts are only shown when a mediator is actually known,
            // so a direct Contract keeps exactly its previous presentation.
            ...(mediation && mediation.mediated
              ? [
                  fact(
                    "Mediator",
                    mediation.mediator
                      ? `${mediation.mediator.system_name}${mediation.explicit ? "" : " (inferred)"}`
                      : null,
                  ),
                  fact("Mediator responsibility", mediation.mediator?.responsibility),
                  fact(
                    "Mediation",
                    mediation.explicit ? "Explicit" : "Inferred · legacy endpoint heuristic",
                  ),
                ]
              : []),
            fact("Business target", `${contract.target.system_name} · ${contract.target.object_name}`),
          ]
        : [
            fact("Kind", node.subtitle),
            fact("Runtime", node.runtime ? "Yes" : "No"),
            fact("Linked contracts", linkedContracts.length > 0 ? String(linkedContracts.length) : null),
          ];

  const traceId = node.kind === "solution" ? null : node.refId;

  return (
    <aside className="integration-inspector" aria-label={`${KIND_LABELS[node.kind]} inspector`}>
      <header className="integration-inspector-head">
        <div>
          <p className="eyebrow">{KIND_LABELS[node.kind]}</p>
          <h4>{node.name}</h4>
        </div>
        <button type="button" className="secondary-button" aria-label="Close inspector" onClick={onClose}>
          ✕
        </button>
      </header>

      <dl className="integration-inspector-facts">
        {facts.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>

      {iface && iface.operations.length > 0 && (
        <div className="integration-inspector-section">
          <span className="integration-subheading">Operations</span>
          <ul className="integration-operations">
            {iface.operations.map((operation) => (
              <li key={operation.object_id}>
                {operation.name} <em>{operation.operation_kind}</em>
              </li>
            ))}
          </ul>
        </div>
      )}

      {linkedContracts.length > 0 && (
        <div className="integration-inspector-section">
          <span className="integration-subheading">Contracts</span>
          <ul className="integration-inspector-contracts">
            {linkedContracts.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => onOpenContract(item.id)}>
                  {item.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <section className="integration-inspector-facts">
        {contract && workspaceId && (
          <EvidencePanel
            workspaceId={workspaceId}
            stateId={stateId ?? null}
            targetKind="integration"
            targetId={contract.id}
            readOnly={readOnly}
          />
        )}
      </section>

      <div className="integration-inspector-actions">
        {contract && (
          <button type="button" className="primary-button" onClick={() => onOpenContract(contract.id)}>
            Open contract
          </button>
        )}
        {onOpenCatalog && node.kind !== "contract" && (
          <button type="button" className="secondary-button" onClick={onOpenCatalog}>
            Open catalog
          </button>
        )}
      </div>

      {traceId && (
        <ObjectTracePanel
          workspaceId={workspaceId}
          stateId={stateId}
          objectId={traceId}
          onNavigate={onNavigateTrace}
        />
      )}
    </aside>
  );
}
