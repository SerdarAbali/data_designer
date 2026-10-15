import { useCallback, useEffect, useMemo, useState } from "react";

import type { ArchitectureState } from "../architectureTypes";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import type { ScenarioPhase } from "../scenarioModel";
import IntegrationPropertiesPanel, {
  type IntegrationPropertiesDraft,
} from "./IntegrationPropertiesPanel";
import {
  CONFORMANCE_LABELS,
  CONFORMANCE_ORDER,
  fetchIntegrationConformance,
  fetchIntegrationContractDetail,
  fetchIntegrationLandscape,
  fetchIntegrationMessageFlow,
  PATTERN_LABELS,
  PHASE_LABELS,
  saveIntegrationSpec,
  STATUS_LABELS,
  type ConformanceStatus,
  type IntegrationConformance,
  type IntegrationContractDetail,
  type IntegrationContractSummary,
  type IntegrationLandscape,
  type IntegrationMessageFlow,
  type IntegrationScenarioStatus,
} from "./integrationDesignModel";
import { integrationLog } from "./integrationLog";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import { useWorkbenchNavigation } from "../workbench/WorkbenchNavigation";

type Props = {
  workspaceId: string;
  activeState: ArchitectureState | null;
  editable: boolean;
  saveStatus: SaveStatus;
  search?: string;
  onOpenIntegration?: (integrationId: string, phase?: ScenarioPhase | "scenarios") => void;
  onOpenCatalog?: () => void;
  onNavigateTrace?: (node: TraceObjectRef) => void;
};

type View = "landscape" | "contract" | "flow" | "mapping" | "scenarios" | "conformance";

const VIEWS: { id: View; label: string }[] = [
  { id: "landscape", label: "Landscape" },
  { id: "contract", label: "Interface & Contract" },
  { id: "flow", label: "Message Flow" },
  { id: "mapping", label: "Transformation & Mapping" },
  { id: "scenarios", label: "Scenario & Sequence" },
  { id: "conformance", label: "Test & Conformance" },
];

function coverageLabel(mapped: number, total: number): string {
  return `${mapped}/${total}`;
}

export default function IntegrationWorkbench({
  workspaceId,
  activeState,
  editable,
  saveStatus,
  search = "",
  onOpenIntegration,
  onOpenCatalog,
  onNavigateTrace,
}: Props) {
  const stateId = activeState?.id ?? "";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const [landscape, setLandscape] = useState<IntegrationLandscape | null>(null);
  const [view, setView] = useState<View>("landscape");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IntegrationContractDetail | null>(null);
  const [flow, setFlow] = useState<IntegrationMessageFlow | null>(null);
  const [conformance, setConformance] = useState<IntegrationConformance | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [propertiesOpen, setPropertiesOpen] = useState(false);
  const [propertiesError, setPropertiesError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const isEditable = editable && landscape?.state_type !== "current";

  const reloadLandscape = useCallback(async () => {
    if (!workspaceId || !stateId) {
      setLandscape(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const next = await fetchIntegrationLandscape(workspaceId, stateId);
      setLandscape(next);
    } catch (caught) {
      integrationLog.error("landscape load failed", caught);
      setError(caught instanceof Error ? caught.message : "Could not load the integration landscape.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, stateId]);

  useEffect(() => {
    void reloadLandscape();
  }, [reloadLandscape, refreshKey]);

  useEffect(() => {
    setSelectedId(null);
    setDetail(null);
    setFlow(null);
    setConformance(null);
    setPropertiesOpen(false);
  }, [stateId]);

  const loadContract = useCallback(
    async (integrationId: string) => {
      if (!workspaceId || !stateId) return;
      setBusy(true);
      setError("");
      try {
        const [nextDetail, nextFlow, nextConformance] = await Promise.all([
          fetchIntegrationContractDetail(workspaceId, integrationId, stateId),
          fetchIntegrationMessageFlow(workspaceId, integrationId, stateId),
          fetchIntegrationConformance(workspaceId, integrationId, stateId),
        ]);
        setDetail(nextDetail);
        setFlow(nextFlow);
        setConformance(nextConformance);
      } catch (caught) {
        integrationLog.error("contract load failed", caught);
        setError(caught instanceof Error ? caught.message : "Could not load the integration contract.");
      } finally {
        setBusy(false);
      }
    },
    [workspaceId, stateId],
  );

  function selectContract(integrationId: string, nextView: View = "contract") {
    integrationLog.info("contract selected", { integrationId, view: nextView });
    setSelectedId(integrationId);
    setPropertiesOpen(false);
    setView(nextView);
    void loadContract(integrationId);
  }

  // Trace navigation: open the destination contract once the landscape loads.
  useEffect(() => {
    if (!focus || focus.discipline !== "integration") return;
    if (focus.kind !== "contract_ref") {
      clearFocus(focus.nonce);
      return;
    }
    if (!landscape) return; // wait for the landscape before deciding
    if (landscape.contracts.some((contract) => contract.id === focus.objectId)) {
      selectContract(focus.objectId, "contract");
    }
    clearFocus(focus.nonce);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, landscape, clearFocus]);

  async function handleSaveProperties(draft: IntegrationPropertiesDraft) {
    if (!selectedId || !detail) return;
    setBusy(true);
    setPropertiesError("");
    try {
      await saveIntegrationSpec(selectedId, {
        expected_revision: detail.contract.revision,
        pattern: draft.pattern,
        implementation_status: draft.implementation_status,
        producer_interface_id: draft.producer_interface_id,
        consumer_interface_id: draft.consumer_interface_id,
        specification: draft.specification,
      });
      setPropertiesOpen(false);
      await reloadLandscape();
      await loadContract(selectedId);
    } catch (caught) {
      integrationLog.error("property save failed", caught);
      setPropertiesError(caught instanceof Error ? caught.message : "Could not save properties.");
    } finally {
      setBusy(false);
    }
  }

  const matches = useCallback(
    (value: string) => value.toLowerCase().includes(search.trim().toLowerCase()),
    [search],
  );

  const contracts = useMemo(
    () => (landscape?.contracts ?? []).filter((item) => matches(item.name)),
    [landscape, matches],
  );

  const selectedContract: IntegrationContractSummary | null = useMemo(
    () => landscape?.contracts.find((item) => item.id === selectedId) ?? detail?.contract ?? null,
    [landscape, selectedId, detail],
  );

  const scenarioGroups = useMemo(() => {
    const scenarios = conformance?.scenarios ?? [];
    const order: { key: string; label: string }[] = [
      { key: "happy_path", label: "Happy path" },
      { key: "alternative", label: "Alternative" },
      { key: "error", label: "Error" },
    ];
    return order
      .map((group) => ({
        ...group,
        items: scenarios.filter((item) => item.category === group.key).filter((item) => matches(item.name)),
      }))
      .filter((group) => group.items.length > 0);
  }, [conformance, matches]);

  function coverageBar(label: string, mapped: number, total: number) {
    const ratio = total === 0 ? 0 : Math.round((mapped / total) * 100);
    return (
      <div className="integration-coverage" key={label}>
        <div className="integration-coverage-head">
          <span>{label}</span>
          <strong>{coverageLabel(mapped, total)}</strong>
        </div>
        <div className="integration-coverage-track">
          <span style={{ width: `${ratio}%` }} />
        </div>
      </div>
    );
  }

  function renderLandscape() {
    if (contracts.length === 0) {
      return (
        <div className="landscape-empty">
          <span className="empty-icon">◇</span>
          <h3>No contracts yet</h3>
          <p>
            Create an integration contract in Mapping &amp; Tests, then return here to link interfaces
            and record its operating properties.
          </p>
          {onOpenIntegration && (
            <button type="button" onClick={() => onOpenIntegration("")}>
              Open Mapping &amp; Tests
            </button>
          )}
        </div>
      );
    }
    return (
      <div className="integration-cards">
        {contracts.map((contract) => (
          <article key={contract.id} className="integration-card">
            <div className="integration-card-head">
              <button
                type="button"
                className="integration-card-title"
                onClick={() => selectContract(contract.id)}
              >
                {contract.name}
              </button>
              <span className={`integration-badge integration-status-${contract.status}`}>
                {STATUS_LABELS[contract.status] ?? contract.status}
              </span>
            </div>
            <p className="integration-card-flow">
              {contract.source.system_name} · {contract.source.object_name} →{" "}
              {contract.target.system_name} · {contract.target.object_name}
            </p>
            <dl>
              <dt>Pattern</dt>
              <dd>{contract.pattern ? PATTERN_LABELS[contract.pattern] : "Unspecified"}</dd>
              <dt>Producer</dt>
              <dd>{contract.producer_interface?.name ?? "—"}</dd>
              <dt>Consumer</dt>
              <dd>{contract.consumer_interface?.name ?? "—"}</dd>
              <dt>Mapped target fields</dt>
              <dd>
                {contract.target_fields_mapped}/{contract.target_fields_total}
              </dd>
              <dt>Scenarios</dt>
              <dd>{contract.scenario_count}</dd>
            </dl>
            <div className="integration-card-actions">
              <button type="button" onClick={() => selectContract(contract.id, "contract")}>
                Interfaces
              </button>
              <button type="button" onClick={() => selectContract(contract.id, "flow")}>
                Flow
              </button>
              <button type="button" onClick={() => selectContract(contract.id, "conformance")}>
                Conformance
              </button>
            </div>
          </article>
        ))}
      </div>
    );
  }

  function renderInterfaceSummary(
    label: string,
    side: IntegrationContractDetail["source_interface"],
  ) {
    if (!side) {
      return (
        <div className="integration-side">
          <h4>{label}</h4>
          <p className="architecture-topbar-hint">No linked interface.</p>
        </div>
      );
    }
    return (
      <div className="integration-side">
        <h4>
          {label}: {side.name}
        </h4>
        <dl>
          <dt>Direction</dt>
          <dd>{side.direction ?? "—"}</dd>
          <dt>Kind</dt>
          <dd>{side.interface_kind ?? "—"}</dd>
          <dt>Protocol</dt>
          <dd>{side.protocol ?? "—"}</dd>
          <dt>Component</dt>
          <dd>{side.component_name ?? "—"}</dd>
        </dl>
        <strong className="integration-side-heading">Operations</strong>
        {side.operations.length === 0 ? (
          <p className="architecture-topbar-hint">No operations recorded.</p>
        ) : (
          <ul className="integration-operations">
            {side.operations.map((operation) => (
              <li key={operation.object_id}>
                {operation.name} <em>{operation.operation_kind}</em>
              </li>
            ))}
          </ul>
        )}
        <strong className="integration-side-heading">Contract phases</strong>
        <ul className="integration-operations">
          {(detail?.phases ?? []).map((phase) => (
            <li key={phase.phase}>
              {PHASE_LABELS[phase.phase]}{" "}
              <em>{phase.configured ? `${phase.node_count} nodes` : "not configured"}</em>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  function renderContract() {
    if (!detail) {
      return <p className="architecture-topbar-hint">Select a contract to inspect its interfaces.</p>;
    }
    return (
      <div className="integration-detail">
        <div className="integration-detail-head">
          <div>
            <h3>{detail.contract.name}</h3>
            <p className="architecture-topbar-hint">
              {detail.contract.interaction_type} · revision {detail.contract.revision}
            </p>
          </div>
          <button type="button" className="secondary-button" onClick={() => setPropertiesOpen(true)}>
            Properties
          </button>
        </div>
        <div className="integration-sides">
          {renderInterfaceSummary("Producer", detail.source_interface)}
          {renderInterfaceSummary("Consumer", detail.target_interface)}
        </div>
      </div>
    );
  }

  function renderFlow() {
    if (!flow) {
      return <p className="architecture-topbar-hint">Select a contract to view its message flow.</p>;
    }
    return (
      <div className="integration-flow">
        <div className="integration-detail-head">
          <div>
            <h3>{flow.contract.name}</h3>
            <p className="architecture-topbar-hint">
              {flow.contract.source.system_name} → {flow.contract.target.system_name} · revision{" "}
              {flow.contract.revision}
            </p>
          </div>
          <button type="button" className="secondary-button" onClick={() => setPropertiesOpen(true)}>
            Properties
          </button>
        </div>
        <dl className="integration-flow-meta">
          <dt>Routing</dt>
          <dd>{flow.routing || "—"}</dd>
        </dl>
        <div className="integration-phases">
          {flow.phases.map((phase) => (
            <article key={phase.phase} className="integration-phase">
              <div className="integration-card-head">
                <strong>{PHASE_LABELS[phase.phase]}</strong>
                <span className="integration-badge">{phase.configured ? "configured" : "empty"}</span>
              </div>
              <p className="architecture-topbar-hint">
                {phase.node_count} nodes · {phase.transformation_count} transformations ·{" "}
                {phase.mapped_target_count}/{phase.target_field_count} target fields mapped
              </p>
              {phase.transformations.length > 0 && (
                <ul className="integration-operations">
                  {phase.transformations.map((transformation) => (
                    <li key={transformation.node_id}>{transformation.label}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </div>
    );
  }

  function renderMapping() {
    if (!flow || !selectedContract) {
      return <p className="architecture-topbar-hint">Select a contract to review its transformations.</p>;
    }
    return (
      <div className="integration-mapping">
        <div className="integration-detail-head">
          <div>
            <h3>Transformation &amp; Mapping</h3>
            <p className="architecture-topbar-hint">
              Reuses the existing mapping, transformation and dry-run engine for{" "}
              {selectedContract.name} (revision {selectedContract.revision}).
            </p>
          </div>
          {onOpenIntegration && (
            <button
              type="button"
              className="primary-button"
              onClick={() => onOpenIntegration(selectedContract.id, "request")}
            >
              Open Mapping &amp; Tests
            </button>
          )}
        </div>
        <div className="integration-phases">
          {flow.phases.map((phase) => (
            <article key={phase.phase} className="integration-phase">
              <div className="integration-card-head">
                <strong>{PHASE_LABELS[phase.phase]}</strong>
                <span className="integration-badge">
                  {phase.mapped_target_count}/{phase.target_field_count} mapped
                </span>
              </div>
              {phase.transformations.length === 0 ? (
                <p className="architecture-topbar-hint">No transformations configured for this phase.</p>
              ) : (
                <ul className="integration-operations">
                  {phase.transformations.map((transformation) => (
                    <li key={transformation.node_id}>{transformation.label}</li>
                  ))}
                </ul>
              )}
              {phase.target_fields.length > 0 && (
                <p className="architecture-topbar-hint">
                  Target fields: {phase.target_fields.join(", ")}
                </p>
              )}
            </article>
          ))}
        </div>
      </div>
    );
  }

  function scenarioStatusBadge(scenario: IntegrationScenarioStatus) {
    return (
      <span className={`integration-badge integration-conformance-${scenario.status}`}>
        {CONFORMANCE_LABELS[scenario.status]}
      </span>
    );
  }

  function renderScenarios() {
    if (!conformance) {
      return <p className="architecture-topbar-hint">Select a contract to list its scenarios.</p>;
    }
    return (
      <div className="integration-scenarios">
        <div className="integration-detail-head">
          <div>
            <h3>Scenario &amp; Sequence</h3>
            <p className="architecture-topbar-hint">
              End-to-end, alternative and error paths recorded against {conformance.contract_name}.
            </p>
          </div>
          {onOpenIntegration && selectedId && (
            <button
              type="button"
              className="primary-button"
              onClick={() => onOpenIntegration(selectedId, "scenarios")}
            >
              Open sequence designer
            </button>
          )}
        </div>
        {scenarioGroups.length === 0 ? (
          <p className="architecture-topbar-hint">No scenarios reference this contract yet.</p>
        ) : (
          scenarioGroups.map((group) => (
            <section key={group.key} className="integration-scenario-group">
              <div className="information-section-heading">
                <strong>{group.label}</strong>
                <span className="item-count">{group.items.length}</span>
              </div>
              <ul className="integration-scenario-list">
                {group.items.map((scenario) => (
                  <li key={scenario.id}>
                    <span className="integration-scenario-name">{scenario.name}</span>
                    {scenarioStatusBadge(scenario)}
                    <span className="architecture-topbar-hint">
                      {scenario.step_count} step{scenario.step_count === 1 ? "" : "s"}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    );
  }

  function renderConformance() {
    if (!conformance) {
      return <p className="architecture-topbar-hint">Select a contract to review conformance.</p>;
    }
    const summary = conformance.summary ?? {};
    return (
      <div className="integration-conformance">
        <div className="integration-detail-head">
          <div>
            <h3>Test &amp; Conformance</h3>
            <p className="architecture-topbar-hint">
              {conformance.contract_name} · revision {conformance.revision}
            </p>
          </div>
          <button type="button" className="secondary-button" onClick={() => setPropertiesOpen(true)}>
            Properties
          </button>
        </div>

        <div className="integration-coverage-grid">
          {coverageBar(
            "Request mappings",
            conformance.request_coverage.mapped,
            conformance.request_coverage.total,
          )}
          {coverageBar(
            "Response mappings",
            conformance.response_coverage.mapped,
            conformance.response_coverage.total,
          )}
          {coverageBar(
            "Error mappings",
            conformance.error_coverage.mapped,
            conformance.error_coverage.total,
          )}
        </div>

        <div className="integration-summary-chips">
          {CONFORMANCE_ORDER.map((status) => (
            <span key={status} className={`integration-badge integration-conformance-${status}`}>
              {CONFORMANCE_LABELS[status as ConformanceStatus]}: {summary[status] ?? 0}
            </span>
          ))}
        </div>

        {conformance.scenarios.length === 0 ? (
          <p className="architecture-topbar-hint">No scenarios reference this contract yet.</p>
        ) : (
          <table className="integration-conformance-table">
            <thead>
              <tr>
                <th scope="col">Scenario</th>
                <th scope="col">Category</th>
                <th scope="col">Status</th>
                <th scope="col">Steps</th>
                <th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {conformance.scenarios.map((scenario) => (
                <tr key={scenario.id}>
                  <td>{scenario.name}</td>
                  <td>{scenario.category}</td>
                  <td>{scenarioStatusBadge(scenario)}</td>
                  <td>{scenario.step_count}</td>
                  <td>{scenario.message || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {onOpenIntegration && selectedId && (
          <button
            type="button"
            className="primary-button"
            onClick={() => onOpenIntegration(selectedId, "request")}
          >
            Open tests in Mapping &amp; Tests
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="integration-workbench">
      <div className="integration-toolbar">
        <span className="integration-toolbar-hint">
          {isEditable
            ? "Design interfaces, message flow and conformance for integration contracts."
            : "Current state is read-only. Duplicate it to record integration properties."}
        </span>
        {selectedContract && view !== "landscape" && (
          <span className="integration-toolbar-selected">
            Contract: <strong>{selectedContract.name}</strong>
          </span>
        )}
        {saveStatus === "error" && (
          <span className="integration-toolbar-error" role="status">
            Some canvas changes failed to save.
          </span>
        )}
        {onOpenCatalog && (
          <button type="button" className="secondary-button" onClick={onOpenCatalog}>
            Open catalog
          </button>
        )}
      </div>

      {error && (
        <div className="studio-canvas-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}

      <div className="integration-body">
        <nav className="integration-views" aria-label="Integration views">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              onClick={() => {
                integrationLog.info("view changed", { view: item.id });
                setView(item.id);
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="integration-content">
          {loading && !landscape ? (
            <div className="landscape-empty" role="status">
              Loading integration landscape…
            </div>
          ) : !landscape ? (
            <div className="landscape-empty">
              <span className="empty-icon">◇</span>
              <h3>No integration landscape available</h3>
              <p>Duplicate the current state into a candidate to design integrations.</p>
            </div>
          ) : view === "landscape" ? (
            renderLandscape()
          ) : (
            <>
              {busy && <p className="architecture-topbar-hint">Loading contract…</p>}
              {view === "contract" && renderContract()}
              {view === "flow" && renderFlow()}
              {view === "mapping" && renderMapping()}
              {view === "scenarios" && renderScenarios()}
              {view === "conformance" && renderConformance()}
            </>
          )}
        </div>

        {propertiesOpen && selectedContract && (
          <IntegrationPropertiesPanel
            contract={selectedContract}
            interfaces={landscape?.interfaces ?? []}
            editable={Boolean(isEditable)}
            busy={busy}
            error={propertiesError}
            workspaceId={workspaceId}
            stateId={stateId || null}
            onNavigateTrace={onNavigateTrace}
            onSave={(draft) => void handleSaveProperties(draft)}
            onClose={() => setPropertiesOpen(false)}
          />
        )}
      </div>
    </div>
  );
}
