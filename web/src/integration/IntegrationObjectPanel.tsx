import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import {
  INTERACTION_TYPE_LABELS,
  PATTERN_LABELS,
  STATUS_LABELS,
  type IntegrationContractSummary,
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
}: Props) {
  const iface = node.kind === "interface" ? interfaces.find((item) => item.object_id === node.refId) : null;
  const contract = node.kind === "contract" ? contracts.find((item) => item.id === node.refId) : null;
  const linkedContracts =
    node.kind === "system" || node.kind === "runtime"
      ? contracts.filter(
          (item) => item.source.system_id === node.refId || item.target.system_id === node.refId,
        )
      : [];

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
            fact("Status", STATUS_LABELS[contract.status] ?? contract.status),
            fact("Revision", `r${contract.revision}`),
            fact("Source", `${contract.source.system_name} · ${contract.source.object_name}`),
            fact("Target", `${contract.target.system_name} · ${contract.target.object_name}`),
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
