import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Viewport } from "@xyflow/react";

import type { ArchitectureState } from "../architectureTypes";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import { useWorkbenchNavigation } from "../workbench/WorkbenchNavigation";
import EnterpriseObjectPanel from "./EnterpriseObjectPanel";
import {
  createEnterpriseLink,
  createEnterpriseObject,
  deleteEnterpriseLink,
  deleteEnterpriseObject,
  ENTERPRISE_LABELS,
  ENTERPRISE_OBJECT_TYPES,
  ENTERPRISE_PLURAL_LABELS,
  fetchApplicationSupport,
  fetchCapabilityMap,
  fetchEnterpriseImpact,
  fetchEnterpriseModel,
  fetchProcessImpact,
  fetchStrategyTrace,
  modelObjects,
  updateEnterpriseObject,
  type ApplicationSupport,
  type CapabilityMap,
  type EnterpriseApplication,
  type EnterpriseImpact,
  type EnterpriseLinkType,
  type EnterpriseModel,
  type EnterpriseObject,
  type EnterpriseObjectType,
  type ProcessImpact,
  type StrategyTrace,
} from "./enterpriseModel";
import { enterpriseLog } from "./enterpriseLog";
import ApplicationSupportView from "./visual/ApplicationSupportView";
import CapabilityMapView from "./visual/CapabilityMapView";
import ProcessFlowView from "./visual/ProcessFlowView";
import StrategyTraceView from "./visual/StrategyTraceView";
import { strategyTraceGraph, type Point } from "./visual/enterpriseCanvasModel";

type Props = {
  workspaceId: string;
  activeState: ArchitectureState | null;
  editable: boolean;
  saveStatus: SaveStatus;
  search?: string;
  mutateActive?: (mutate: (state: ArchitectureState) => ArchitectureState) => void;
  onReloadStates?: () => void;
  onOpenCatalog?: () => void;
  onNavigateTrace?: (node: TraceObjectRef) => void;
};

type View = "objects" | "capability" | "process" | "strategy" | "application" | "impact";

const VIEWS: { id: View; label: string }[] = [
  { id: "objects", label: "Objects" },
  { id: "capability", label: "Capability Map" },
  { id: "process", label: "Process Impact" },
  { id: "strategy", label: "Strategy Trace" },
  { id: "application", label: "Application Support" },
  { id: "impact", label: "Impact" },
];

const CHANGE_LABELS: Record<string, string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  reused: "Reused",
};

export default function EnterpriseWorkbench({
  workspaceId,
  activeState,
  editable,
  saveStatus,
  search = "",
  mutateActive,
  onReloadStates,
  onOpenCatalog,
  onNavigateTrace,
}: Props) {
  const stateId = activeState?.id ?? "";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const [model, setModel] = useState<EnterpriseModel | null>(null);
  const [view, setView] = useState<View>("strategy");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const viewportRef = useRef<Record<string, Viewport>>({});
  const viewportKey = `${stateId}:${view}`;

  const [newKind, setNewKind] = useState<EnterpriseObjectType>("goal");
  const [newName, setNewName] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const [capabilityMap, setCapabilityMap] = useState<CapabilityMap | null>(null);
  const [processImpact, setProcessImpact] = useState<ProcessImpact | null>(null);
  const [strategyTrace, setStrategyTrace] = useState<StrategyTrace | null>(null);
  const [applicationSupport, setApplicationSupport] = useState<ApplicationSupport | null>(null);
  const [impact, setImpact] = useState<EnterpriseImpact | null>(null);

  const isEditable = editable && model?.editable === true;

  const reloadModel = useCallback(async () => {
    if (!workspaceId || !stateId) {
      setModel(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const next = await fetchEnterpriseModel(workspaceId, stateId);
      setModel(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the enterprise model.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, stateId]);

  useEffect(() => {
    void reloadModel();
  }, [reloadModel]);

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId || !stateId) return;
    const load = async () => {
      try {
        if (view === "capability") {
          const next = await fetchCapabilityMap(workspaceId, stateId);
          if (!cancelled) setCapabilityMap(next);
        } else if (view === "process") {
          const next = await fetchProcessImpact(workspaceId, stateId);
          if (!cancelled) setProcessImpact(next);
        } else if (view === "strategy") {
          const next = await fetchStrategyTrace(workspaceId, stateId);
          if (!cancelled) setStrategyTrace(next);
        } else if (view === "application") {
          const next = await fetchApplicationSupport(workspaceId, stateId);
          if (!cancelled) setApplicationSupport(next);
        } else if (view === "impact") {
          const next = await fetchEnterpriseImpact(workspaceId, stateId);
          if (!cancelled) setImpact(next);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Could not load this view.");
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, stateId, view, refreshKey]);

  const run = useCallback(
    async (operation: () => Promise<EnterpriseModel | void>) => {
      setBusy(true);
      setError("");
      try {
        const result = await operation();
        if (result) setModel(result);
        else await reloadModel();
        setRefreshKey((value) => value + 1);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "The change could not be saved.";
        setError(message);
        enterpriseLog.error("mutation failed", message);
      } finally {
        setBusy(false);
      }
    },
    [reloadModel],
  );

  const objects = useMemo(() => (model ? modelObjects(model) : []), [model]);
  const selectedObject = useMemo(
    () => objects.find((object) => object.object_id === selectedObjectId) ?? null,
    [objects, selectedObjectId],
  );

  const term = search.trim().toLowerCase();
  const matches = useCallback(
    (name: string) => !term || name.toLowerCase().includes(term),
    [term],
  );

  const grouped = useMemo(() => {
    const result: { kind: EnterpriseObjectType; items: EnterpriseObject[] }[] = [];
    if (!model) return result;
    const groups: [EnterpriseObjectType, EnterpriseObject[]][] = [
      ["goal", model.goals],
      ["requirement", model.requirements],
      ["capability", model.capabilities],
      ["process", model.processes],
      ["principle", model.principles],
      ["role", model.roles],
    ];
    for (const [kind, items] of groups) {
      const filtered = items.filter((item) => matches(item.name));
      if (filtered.length > 0) result.push({ kind, items: filtered });
    }
    return result;
  }, [model, matches]);

  function selectObject(objectId: string) {
    setSelectedObjectId(objectId);
    setInspectorCollapsed(false);
  }

  function selectApplication(application: EnterpriseApplication) {
    if (!onNavigateTrace) return;
    const discipline = application.kind === "solution_boundary" ? "solution" : null;
    onNavigateTrace({
      id: application.object_id,
      kind: application.kind === "solution_boundary" ? "solution_boundary" : "system",
      name: application.name,
      description: application.description ?? null,
      discipline,
      state_membership: activeState?.state_type === "current" ? "current" : "candidate",
      external: false,
    });
  }

  // Moves an enterprise node and marks the layout as user-authored so it is not
  // re-laid-out on the next reload.
  const moveEnterpriseObject = useCallback(
    (occurrenceId: string, position: Point) => {
      if (!occurrenceId || !mutateActive) return;
      mutateActive((state) => ({
        ...state,
        nodes: state.nodes.map((node) =>
          node.occurrence_id === occurrenceId
            ? {
                ...node,
                position,
                display_metadata: { ...(node.display_metadata ?? {}), enterprise_manual: true },
              }
            : node,
        ),
      }));
    },
    [mutateActive],
  );

  const handleAutoArrange = useCallback(() => {
    if (!model || !strategyTrace || !isEditable || !mutateActive) return;
    if (view !== "strategy") return;
    const graph = strategyTraceGraph(model, strategyTrace, activeState, { forceAuto: true });
    const moves = graph.nodes
      .filter((node) => node.kind !== "application" && node.occurrenceId)
      .map((node) => ({ occurrenceId: node.occurrenceId, position: node.position }));
    if (moves.length === 0) return;
    mutateActive((state) => {
      let next = state;
      for (const move of moves) {
        next = {
          ...next,
          nodes: next.nodes.map((node) =>
            node.occurrence_id === move.occurrenceId
              ? {
                  ...node,
                  position: move.position,
                  display_metadata: { ...(node.display_metadata ?? {}), enterprise_manual: true },
                }
              : node,
          ),
        };
      }
      return next;
    });
  }, [model, strategyTrace, isEditable, mutateActive, view, activeState]);

  // Trace navigation: reveal the destination object once the model is loaded.
  useEffect(() => {
    if (!focus || focus.discipline !== "enterprise") return;
    if (objects.some((object) => object.object_id === focus.objectId)) {
      setView("objects");
      selectObject(focus.objectId);
    }
    clearFocus(focus.nonce);
  }, [focus, objects, clearFocus]);

  function handleCreateObject() {
    if (!model) return;
    const n = (model.goals.length + model.requirements.length + model.capabilities.length +
      model.processes.length + model.principles.length + model.roles.length);
    void run(() =>
      createEnterpriseObject(workspaceId, {
        state_id: stateId,
        kind: newKind,
        name: newName.trim(),
        position: { x: 80 + (n % 4) * 220, y: 80 + Math.floor(n / 4) * 140 },
      }),
    );
    setNewName("");
  }

  const showInspector = Boolean(selectedObject) && !inspectorCollapsed;

  return (
    <div className={`enterprise-workbench${showInspector ? " has-panel" : ""}`}>
      <div className="view-toolbar">
        <div className="view-toolbar-left">
          <div className="view-toolbar-title">
            <p className="eyebrow">Enterprise</p>
            <h2>Objects</h2>
          </div>
          <span className="view-toolbar-count">{objects.length}</span>
        </div>
        <div className="view-toolbar-right">
          {onOpenCatalog && (
            <button type="button" className="btn btn--secondary" onClick={onOpenCatalog}>
              Open catalog
            </button>
          )}
          <div className="creation-popover">
            <button
              type="button"
              className="btn btn--primary"
              aria-expanded={createOpen}
              aria-haspopup="dialog"
              disabled={!isEditable || busy}
              onClick={() => setCreateOpen((open) => !open)}
            >
              + New object
            </button>
            <section className="creation-panel" hidden={!createOpen} aria-label="Create enterprise object">
              <header>
                <h3>New object</h3>
                <button
                  type="button"
                  className="creation-close"
                  aria-label="Close creation popover"
                  onClick={() => setCreateOpen(false)}
                >
                  ✕
                </button>
              </header>
              <div className="creation-fields">
                <label>
                  Type
                  <select
                    value={newKind}
                    disabled={!isEditable || busy}
                    onChange={(event) => setNewKind(event.target.value as EnterpriseObjectType)}
                  >
                    {ENTERPRISE_OBJECT_TYPES.map((kind) => (
                      <option key={kind} value={kind}>
                        {ENTERPRISE_LABELS[kind]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Name
                  <input
                    value={newName}
                    disabled={!isEditable || busy}
                    placeholder="New object name"
                    onChange={(event) => setNewName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && newName.trim()) handleCreateObject();
                    }}
                  />
                </label>
              </div>
              <div className="creation-actions">
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={!isEditable || busy}
                  onClick={() => setCreateOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={!isEditable || busy || !newName.trim()}
                  onClick={handleCreateObject}
                >
                  Create
                </button>
              </div>
            </section>
          </div>
          <div className="more-menu">
            <button
              type="button"
              className="more-menu-trigger"
              aria-expanded={moreOpen}
              aria-label="More actions"
              onClick={() => setMoreOpen((open) => !open)}
            >
              More ⌄
            </button>
            <section className="more-menu-panel" hidden={!moreOpen} aria-label="More actions">
              {view === "strategy" && (
                <button
                  type="button"
                  className="more-menu-item"
                  disabled={!isEditable || busy || !strategyTrace}
                  title={isEditable ? "Recompute the strategy trace layout" : "Current state is read-only"}
                  onClick={() => handleAutoArrange()}
                >
                  Auto arrange
                </button>
              )}
            </section>
          </div>
        </div>
      </div>

      {error && (
        <div className="studio-canvas-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}

      <div className="enterprise-body">
        <nav className="enterprise-views tabs" aria-label="Enterprise views">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`tab${view === item.id ? " active" : ""}`}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className={`enterprise-content${view === "strategy" || view === "application" ? " canvas" : ""}`}>
          {loading && !model ? (
            <div className="landscape-empty" role="status">
              Loading enterprise model…
            </div>
          ) : !model ? (
            <div className="landscape-empty">
              <span className="empty-icon">◇</span>
              <h3>No enterprise model available</h3>
              <p>Duplicate the current state into a candidate to model strategy.</p>
            </div>
          ) : (
            <>
              {view === "objects" && (
                <div className="enterprise-objects">
                  {grouped.length === 0 ? (
                    <div className="empty-state empty-state--page" role="status">
                      <span className="empty-icon">◇</span>
                      <h3>No objects match</h3>
                      <p>Add goals, capabilities and processes to get started.</p>
                    </div>
                  ) : (
                    grouped.map((group) => (
                      <section key={group.kind} className="enterprise-group">
                        <div className="information-section-heading">
                          <strong>{ENTERPRISE_PLURAL_LABELS[group.kind] ?? ENTERPRISE_LABELS[group.kind] ?? group.kind}</strong>
                          <span className="item-count">{group.items.length}</span>
                        </div>
                        <ul className="enterprise-object-grid">
                          {group.items.map((object) => (
                            <li key={object.object_id}>
                              <button
                                type="button"
                                className={`enterprise-object-card${object.object_id === selectedObjectId ? " selected" : ""}`}
                                onClick={() => selectObject(object.object_id)}
                                title={object.name}
                              >
                                <em>{ENTERPRISE_LABELS[object.kind] ?? object.kind}</em>
                                <strong title={object.name}>{object.name}</strong>
                                <span>{object.description ?? "No description recorded."}</span>
                                {object.owner && <small>Owner: {object.owner}</small>}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))
                  )}
                </div>
              )}

              {view === "capability" && capabilityMap && (
                <CapabilityMapView
                  model={model}
                  capabilityMap={capabilityMap}
                  impact={impact}
                  selectedObjectId={selectedObjectId}
                  onSelectObject={selectObject}
                />
              )}

              {view === "process" && processImpact && (
                <ProcessFlowView
                  model={model}
                  processImpact={processImpact}
                  impact={impact}
                  selectedObjectId={selectedObjectId}
                  onSelectObject={selectObject}
                />
              )}

              {view === "strategy" && strategyTrace && (
                <StrategyTraceView
                  model={model}
                  strategyTrace={strategyTrace}
                  state={activeState}
                  editable={isEditable}
                  selectedObjectId={selectedObjectId}
                  onSelectObject={selectObject}
                  onSelectApplication={selectApplication}
                  onMoveObject={moveEnterpriseObject}
                  defaultViewport={viewportRef.current[viewportKey]}
                  onViewportChange={(viewport) => {
                    viewportRef.current[viewportKey] = viewport;
                  }}
                />
              )}

              {view === "application" && applicationSupport && (
                <ApplicationSupportView
                  model={model}
                  applicationSupport={applicationSupport}
                  selectedObjectId={selectedObjectId}
                  onSelectObject={selectObject}
                  onSelectApplication={selectApplication}
                  defaultViewport={viewportRef.current[viewportKey]}
                  onViewportChange={(viewport) => {
                    viewportRef.current[viewportKey] = viewport;
                  }}
                />
              )}

              {view === "impact" && impact && (
                <div className="enterprise-impact">
                  <section className="enterprise-impact-changes">
                    <div className="information-section-heading">
                      <strong>Current vs candidate changes</strong>
                      <span className="item-count">{impact.changes.length}</span>
                    </div>
                    {impact.changes.length === 0 ? (
                      <p className="architecture-topbar-hint">No differences recorded.</p>
                    ) : (
                      <ul className="enterprise-change-list">
                        {impact.changes.map((change) => (
                          <li key={`${change.object_id}-${change.change}`}>
                            <span className={`enterprise-badge change-${change.change}`}>
                              {CHANGE_LABELS[change.change] ?? change.change}
                            </span>
                            <button
                              type="button"
                              className="enterprise-link-endpoint"
                              onClick={() => selectObject(change.object_id)}
                            >
                              {change.name}
                            </button>
                            <small>{ENTERPRISE_LABELS[change.kind] ?? change.kind}</small>
                            {change.changed_fields && change.changed_fields.length > 0 && (
                              <small>fields: {change.changed_fields.join(", ")}</small>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  <section>
                    <strong>Affected applications</strong>
                    <p>{impact.affected_applications.map((item) => item.name).join(", ") || "—"}</p>
                  </section>
                  <section>
                    <strong>Affected capabilities</strong>
                    <p>{impact.affected_capabilities.map((item) => item.name).join(", ") || "—"}</p>
                  </section>
                  <section>
                    <strong>Affected processes</strong>
                    <p>{impact.affected_processes.map((item) => item.name).join(", ") || "—"}</p>
                  </section>

                  {(impact.unresolved_dependencies.length > 0 ||
                    impact.unresolved_constraints.length > 0 ||
                    impact.risks.length > 0 ||
                    impact.gaps.length > 0) && (
                    <section className="enterprise-gaps-block">
                      <strong>Unresolved dependencies, constraints, risks and gaps</strong>
                      <ul>
                        {impact.unresolved_dependencies.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                        {impact.unresolved_constraints.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                        {impact.risks.map((item) => (
                          <li key={item.object_id}>Risk: {item.name}</li>
                        ))}
                        {impact.gaps.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {inspectorCollapsed && selectedObject && (
          <button
            type="button"
            className="studio-reopen-inspector"
            onClick={() => setInspectorCollapsed(false)}
          >
            Open inspector
          </button>
        )}

        {!inspectorCollapsed && selectedObject && model && (
          <EnterpriseObjectPanel
            key={selectedObject.object_id}
            object={selectedObject}
            model={model}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(objectId, patch) =>
              void run(() =>
                updateEnterpriseObject(workspaceId, objectId, { state_id: stateId, ...patch }),
              )
            }
            onDelete={(objectId) => {
              if (!window.confirm("Delete this object and its relationships?")) return;
              void run(async () => {
                const next = await deleteEnterpriseObject(workspaceId, objectId, stateId);
                setSelectedObjectId(null);
                return next;
              });
            }}
            onCreateLink={(relationshipType: EnterpriseLinkType, sourceObjectId, targetObjectId) =>
              void run(() =>
                createEnterpriseLink(workspaceId, {
                  state_id: stateId,
                  relationship_type: relationshipType,
                  source_object_id: sourceObjectId,
                  target_object_id: targetObjectId,
                }),
              )
            }
            onDeleteLink={(linkId) =>
              void run(() => deleteEnterpriseLink(workspaceId, linkId, stateId))
            }
            onSelectObject={selectObject}
            onClose={() => setSelectedObjectId(null)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={(
              <ObjectTracePanel
                workspaceId={workspaceId}
                stateId={stateId || null}
                objectId={selectedObject.object_id}
                onNavigate={onNavigateTrace}
              />
            )}
          />
        )}
      </div>
    </div>
  );
}
