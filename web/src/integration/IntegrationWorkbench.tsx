import { useCallback, useEffect, useMemo, useState } from "react";
import type { Viewport } from "@xyflow/react";

import type { ArchitectureState } from "../architectureTypes";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import type { ScenarioPhase } from "../scenarioModel";
import IntegrationObjectPanel from "./IntegrationObjectPanel";
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
  fetchIntegrationSequence,
  INTERACTION_TYPE_LABELS,
  PHASE_LABELS,
  saveIntegrationSpec,
  STATUS_LABELS,
  type ConformanceStatus,
  type FlowPhaseName,
  type IntegrationConformance,
  type IntegrationContractDetail,
  type IntegrationContractSummary,
  type IntegrationLandscape,
  type IntegrationMessageFlow,
  type IntegrationScenarioStatus,
  type IntegrationSequence,
} from "./integrationDesignModel";
import { integrationLog } from "./integrationLog";
import {
  INTEGRATION_VIEWS,
  integrationTopology,
  type FlowStage,
  type IntegrationTopologyNode,
  type IntegrationViewId,
} from "./integrationViews";
import FlowDesignerView from "./visual/FlowDesignerView";
import IntegrationSequenceView from "./visual/IntegrationSequenceView";
import IntegrationTopologyView from "./visual/IntegrationTopologyView";
import InterfaceChannelView from "./visual/InterfaceChannelView";
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

type View = IntegrationViewId;

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
  const [sequence, setSequence] = useState<IntegrationSequence | null>(null);
  const [sequenceLoading, setSequenceLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [propertiesOpen, setPropertiesOpen] = useState(false);
  const [propertiesError, setPropertiesError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  // Landscape visual state.
  const [selectedNode, setSelectedNode] = useState<IntegrationTopologyNode | null>(null);
  const [manualPositions, setManualPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [landscapeViewport, setLandscapeViewport] = useState<Viewport | undefined>(undefined);
  const [showResilience, setShowResilience] = useState(false);
  const [selectedPhase, setSelectedPhase] = useState<FlowPhaseName>("request");
  const [stageDetail, setStageDetail] = useState<{ stage: FlowStage; phase: FlowPhaseName } | null>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);

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
    setSequence(null);
    setPropertiesOpen(false);
    setSelectedNode(null);
    setManualPositions({});
    setLandscapeViewport(undefined);
    setSelectedPhase("request");
    setStageDetail(null);
    setSelectedScenarioId(null);
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
    setSelectedNode(null);
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

  // Lazily project sequences only when the Scenario & Sequence view is opened.
  useEffect(() => {
    if (view !== "scenarios" || !selectedId || !stateId) {
      setSequence(null);
      return;
    }
    let cancelled = false;
    setSequenceLoading(true);
    fetchIntegrationSequence(workspaceId, selectedId, stateId)
      .then((data) => {
        if (!cancelled) setSequence(data);
      })
      .catch((caught: unknown) => {
        integrationLog.error("sequence load failed", caught);
        if (!cancelled) setSequence(null);
      })
      .finally(() => {
        if (!cancelled) setSequenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view, selectedId, stateId, workspaceId, refreshKey]);

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

  const topologyLandscape = useMemo<IntegrationLandscape | null>(
    () => (landscape ? { ...landscape, contracts } : null),
    [landscape, contracts],
  );

  const topology = useMemo(
    () => (topologyLandscape ? integrationTopology(topologyLandscape) : { nodes: [], edges: [], mediatedContractIds: [] }),
    [topologyLandscape],
  );

  const nodesByRefId = useMemo(
    () => new Map(topology.nodes.map((node) => [node.refId, node])),
    [topology.nodes],
  );

  const selectedContract: IntegrationContractSummary | null = useMemo(
    () => landscape?.contracts.find((item) => item.id === selectedId) ?? detail?.contract ?? null,
    [landscape, selectedId, detail],
  );

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
    if (!topologyLandscape) return null;
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
      <IntegrationTopologyView
        key={stateId}
        landscape={topologyLandscape}
        selectedRefId={selectedNode?.refId ?? selectedId}
        onSelectNode={(node) => {
          setSelectedNode(node);
          if (node.kind === "contract") {
            setSelectedId(node.refId);
            void loadContract(node.refId);
          }
        }}
        onOpenContract={(contractId) => onOpenIntegration?.(contractId, "request")}
        onOpenCatalog={onOpenCatalog}
        manualPositions={manualPositions}
        onMoveNode={(id, position) =>
          setManualPositions((current) => ({ ...current, [id]: position }))
        }
        onArrange={() => setManualPositions({})}
        showResilience={showResilience}
        onToggleResilience={() => setShowResilience((value) => !value)}
        viewport={landscapeViewport}
        onViewportChange={setLandscapeViewport}
      />
    );
  }

  function renderContract() {
    if (!detail || !flow) {
      return <p className="architecture-topbar-hint">Select a contract to inspect its interfaces.</p>;
    }
    return (
      <div className="integration-detail">
        <div className="integration-detail-head">
          <div>
            <h3>{detail.contract.name}</h3>
            <p className="architecture-topbar-hint">
              {INTERACTION_TYPE_LABELS[detail.contract.interaction_type] ??
                detail.contract.interaction_type}{" "}
              · revision {detail.contract.revision}
            </p>
          </div>
        </div>
        <InterfaceChannelView
          detail={detail}
          flow={flow}
          onSelectInterface={(objectId) => {
            const node = nodesByRefId.get(objectId);
            if (node) setSelectedNode(node);
          }}
          onSelectSystem={(systemId) => {
            const node = nodesByRefId.get(systemId);
            if (node) setSelectedNode(node);
          }}
          onOpenContract={(contractId) => onOpenIntegration?.(contractId, "request")}
          onOpenMapping={(phase) => {
            if (selectedId) onOpenIntegration?.(selectedId, phase);
          }}
        />
      </div>
    );
  }

  function renderFlow() {
    if (!flow) {
      return <p className="architecture-topbar-hint">Select a contract to view its message flow.</p>;
    }
    return (
      <>
        <div className="integration-detail-head">
          <div>
            <h3>{flow.contract.name}</h3>
            <p className="architecture-topbar-hint">
              {flow.contract.source.system_name} → {flow.contract.target.system_name} ·{" "}
              {INTERACTION_TYPE_LABELS[flow.contract.interaction_type] ?? flow.contract.interaction_type} ·
              revision {flow.contract.revision}
            </p>
          </div>
        </div>
        <FlowDesignerView
          flow={flow}
          selectedPhase={selectedPhase}
          onSelectPhase={setSelectedPhase}
          onSelectStage={(stage, phase) => {
            setStageDetail({ stage, phase });
            const node = nodesByRefId.get(stage.id.replace(/^system:/, "").replace(/^interface:/, ""));
            if (node && (stage.role === "system" || stage.role === "runtime" || stage.role === "interface")) {
              setSelectedNode(node);
            }
          }}
          onOpenContract={(contractId) => onOpenIntegration?.(contractId, "request")}
          onOpenMapping={(phase) => {
            if (selectedId) onOpenIntegration?.(selectedId, phase);
          }}
        />
        {stageDetail && (
          <div className="integration-stage-detail" role="status">
            <strong>{stageDetail.stage.label}</strong>
            <span>{stageDetail.stage.detail ?? stageDetail.stage.role}</span>
            <em>
              {stageDetail.phase}
              {stageDetail.stage.metadata ? " · metadata only" : ""}
            </em>
            <button type="button" onClick={() => setStageDetail(null)}>
              Dismiss
            </button>
          </div>
        )}
      </>
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
                    <li key={transformation.node_id}>
                      <em>{transformation.role}</em> {transformation.label}
                    </li>
                  ))}
                </ul>
              )}
              {phase.target_fields.length > 0 && (
                <p className="architecture-topbar-hint">
                  Mapped target fields: {phase.target_fields.join(", ")}
                </p>
              )}
              {phase.unmapped_required_fields.length > 0 && (
                <p className="integration-flow-gap">
                  Unmapped required target fields: {phase.unmapped_required_fields.join(", ")}
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
    if (!selectedId) {
      return <p className="architecture-topbar-hint">Select a contract to view its sequence.</p>;
    }
    if (!sequence) {
      return (
        <p className="architecture-topbar-hint">
          {sequenceLoading ? "Loading sequence…" : "No sequence available for this contract."}
        </p>
      );
    }
    return (
      <IntegrationSequenceView
        sequence={sequence}
        loading={sequenceLoading}
        selectedScenarioId={selectedScenarioId}
        onSelectScenario={setSelectedScenarioId}
        onOpenScenarios={() => onOpenIntegration?.(selectedId, "scenarios")}
      />
    );
  }

  function renderConformance() {
    if (!conformance) {
      return <p className="architecture-topbar-hint">Select a contract to review conformance.</p>;
    }
    const summary = conformance.summary ?? {};
    const spec = selectedContract?.specification ?? {};
    const missing: string[] = [];
    if (selectedContract && !selectedContract.producer_interface) missing.push("Producer interface");
    if (selectedContract && !selectedContract.consumer_interface) missing.push("Consumer interface");
    if (conformance.request_coverage.mapped === 0) missing.push("Request mapping");
    if (conformance.scenarios.length === 0) missing.push("Scenario");
    if (!spec.retry || spec.retry.max_attempts === 0) missing.push("Resilience");
    return (
      <div className="integration-conformance">
        <div className="integration-detail-head">
          <div>
            <h3>Test &amp; Conformance</h3>
            <p className="architecture-topbar-hint">
              {conformance.contract_name} · revision {conformance.revision} ·{" "}
              {selectedContract ? STATUS_LABELS[selectedContract.implementation_status] ?? selectedContract.implementation_status : "—"}
            </p>
          </div>
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

        {missing.length > 0 && (
          <div className="integration-missing" role="status">
            <strong>Outstanding configuration</strong>
            <ul>
              {missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}

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

  function renderView() {
    switch (view) {
      case "landscape":
        return renderLandscape();
      case "contract":
        return renderContract();
      case "flow":
        return renderFlow();
      case "mapping":
        return renderMapping();
      case "scenarios":
        return renderScenarios();
      case "conformance":
        return renderConformance();
      default:
        return null;
    }
  }

  return (
    <div className="integration-workbench">
      <div className="integration-toolbar">
        <span className="integration-toolbar-hint">
          {isEditable
            ? "Design interfaces, message flow and conformance for integration contracts."
            : "Current state is read-only. Duplicate it to record integration properties."}
        </span>
        {landscape && (
          <label className="integration-contract-picker">
            <span className="integration-contract-picker-label">Contract</span>
            <select
              aria-label="Contract"
              value={selectedId ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                if (value === "__new__") {
                  integrationLog.info("create contract requested", {});
                  onOpenIntegration?.("");
                  return;
                }
                if (!value) {
                  integrationLog.info("contract cleared", {});
                  setSelectedId(null);
                  setDetail(null);
                  setFlow(null);
                  setConformance(null);
                  setSequence(null);
                  setPropertiesOpen(false);
                  setSelectedNode(null);
                  return;
                }
                selectContract(value, view === "landscape" ? "contract" : view);
              }}
            >
              <option value="">Select existing contract</option>
              {landscape.contracts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.source.system_name}→{item.target.system_name}
                </option>
              ))}
              {onOpenIntegration && <option value="__new__">Create contract…</option>}
            </select>
            {selectedContract && (
              <span className="integration-contract-context" title="Selected contract context">
                {selectedContract.source.system_name} · {selectedContract.source.object_name} →{" "}
                {selectedContract.target.system_name} · {selectedContract.target.object_name}
                {" · "}
                {selectedContract.interaction_type}
              </span>
            )}
          </label>
        )}
        {saveStatus === "error" && (
          <span className="integration-toolbar-error" role="status">
            Some canvas changes failed to save.
          </span>
        )}
        {selectedContract && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setSelectedNode(null);
              setPropertiesOpen(true);
            }}
          >
            Properties
          </button>
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
          {INTEGRATION_VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              title={item.description}
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
          ) : (
            <>
              {busy && <p className="architecture-topbar-hint">Loading contract…</p>}
              {renderView()}
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

        {!propertiesOpen && selectedNode && (
          <IntegrationObjectPanel
            node={selectedNode}
            workspaceId={workspaceId}
            stateId={stateId || null}
            interfaces={landscape?.interfaces ?? []}
            contracts={landscape?.contracts ?? []}
            onOpenContract={(contractId) => onOpenIntegration?.(contractId, "request")}
            onOpenCatalog={onOpenCatalog}
            onNavigateTrace={onNavigateTrace}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>
    </div>
  );
}
