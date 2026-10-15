import { useCallback, useEffect, useMemo, useState } from "react";

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
  type EnterpriseImpact,
  type EnterpriseLinkType,
  type EnterpriseModel,
  type EnterpriseObject,
  type EnterpriseObjectType,
  type ProcessImpact,
  type StrategyTrace,
} from "./enterpriseModel";
import { enterpriseLog } from "./enterpriseLog";

type Props = {
  workspaceId: string;
  activeState: ArchitectureState | null;
  editable: boolean;
  saveStatus: SaveStatus;
  search?: string;
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
  onOpenCatalog,
  onNavigateTrace,
}: Props) {
  const stateId = activeState?.id ?? "";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const [model, setModel] = useState<EnterpriseModel | null>(null);
  const [view, setView] = useState<View>("objects");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const [newKind, setNewKind] = useState<EnterpriseObjectType>("goal");
  const [newName, setNewName] = useState("");

  const [capabilityMap, setCapabilityMap] = useState<CapabilityMap | null>(null);
  const [processImpact, setProcessImpact] = useState<ProcessImpact | null>(null);
  const [strategyTrace, setStrategyTrace] = useState<StrategyTrace | null>(null);
  const [applicationSupport, setApplicationSupport] = useState<ApplicationSupport | null>(null);
  const [impact, setImpact] = useState<EnterpriseImpact | null>(null);

  const isEditable = editable && model?.state_type !== "current";

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
      <div className="enterprise-toolbar">
        <span className="enterprise-title">Enterprise</span>
        <select
          aria-label="New object type"
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
        <input
          aria-label="New object name"
          value={newName}
          disabled={!isEditable || busy}
          placeholder="New object name"
          onChange={(event) => setNewName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && newName.trim()) handleCreateObject();
          }}
        />
        <button
          type="button"
          className="studio-add-menu"
          disabled={!isEditable || busy || !newName.trim()}
          onClick={handleCreateObject}
        >
          + Add object
        </button>
        <span className="enterprise-toolbar-hint">
          {isEditable
            ? "Author goals, capabilities, processes, principles and roles."
            : "Current state is read-only. Duplicate it to model changes."}
        </span>
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

      <div className="enterprise-body">
        <nav className="enterprise-views" aria-label="Enterprise views">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="enterprise-content">
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
                    <p className="architecture-topbar-hint">
                      No objects match. Add goals, capabilities and processes to get started.
                    </p>
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
                              >
                                <strong>{object.name}</strong>
                                {object.owner && <em>{object.owner}</em>}
                                <span>{object.description ?? "No description recorded."}</span>
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
                <div className="enterprise-cards">
                  {capabilityMap.capabilities.filter((entry) => matches(entry.capability.name))
                    .length === 0 ? (
                    <p className="architecture-topbar-hint">No capabilities recorded yet.</p>
                  ) : (
                    capabilityMap.capabilities
                      .filter((entry) => matches(entry.capability.name))
                      .map((entry) => (
                        <article key={entry.capability.object_id} className="enterprise-card">
                          <button
                            type="button"
                            className="enterprise-card-title"
                            onClick={() => selectObject(entry.capability.object_id)}
                          >
                            {entry.capability.name}
                          </button>
                          <dl>
                            <dt>Processes</dt>
                            <dd>{entry.processes.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Applications</dt>
                            <dd>{entry.applications.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Principles</dt>
                            <dd>{entry.principles.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Owner</dt>
                            <dd>{entry.owner_role?.name ?? "—"}</dd>
                          </dl>
                        </article>
                      ))
                  )}
                </div>
              )}

              {view === "process" && processImpact && (
                <div className="enterprise-cards">
                  {processImpact.processes.length === 0 ? (
                    <p className="architecture-topbar-hint">No processes recorded yet.</p>
                  ) : (
                    processImpact.processes
                      .filter((entry) => matches(entry.process.name))
                      .map((entry) => (
                        <article key={entry.process.object_id} className="enterprise-card">
                          <div className="enterprise-card-head">
                            <button
                              type="button"
                              className="enterprise-card-title"
                              onClick={() => selectObject(entry.process.object_id)}
                            >
                              {entry.process.name}
                            </button>
                            {entry.process.process_type === "value_stream" && (
                              <span className="enterprise-badge">value stream</span>
                            )}
                            {entry.impacted && (
                              <span className="enterprise-badge enterprise-badge-warn">impacted</span>
                            )}
                          </div>
                          <dl>
                            <dt>Capabilities</dt>
                            <dd>{entry.capabilities.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Applications</dt>
                            <dd>{entry.applications.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Requirements</dt>
                            <dd>{entry.requirements.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Governed by</dt>
                            <dd>{entry.governed_by.map((item) => item.name).join(", ") || "—"}</dd>
                          </dl>
                        </article>
                      ))
                  )}
                </div>
              )}

              {view === "strategy" && strategyTrace && (
                <div className="enterprise-strategy">
                  {strategyTrace.chains.filter((chain) => matches(chain.goal.name)).length === 0 ? (
                    <p className="architecture-topbar-hint">No goals recorded yet.</p>
                  ) : (
                    strategyTrace.chains
                      .filter((chain) => matches(chain.goal.name))
                      .map((chain) => (
                        <article key={chain.goal.object_id} className="enterprise-trace">
                          <div className="enterprise-card-head">
                            <button
                              type="button"
                              className="enterprise-card-title"
                              onClick={() => selectObject(chain.goal.object_id)}
                            >
                              {chain.goal.name}
                            </button>
                            <span className="enterprise-badge">goal</span>
                          </div>
                          {chain.steps.length === 0 ? (
                            <p className="architecture-topbar-hint">No linked requirements.</p>
                          ) : (
                            <ol className="enterprise-trace-steps">
                              {chain.steps.map((step) => (
                                <li key={step.requirement.object_id}>
                                  <div className="enterprise-trace-row">
                                    <span className="enterprise-trace-label">Requirement</span>
                                    <button
                                      type="button"
                                      className="enterprise-link-endpoint"
                                      onClick={() => selectObject(step.requirement.object_id)}
                                    >
                                      {step.requirement.name}
                                    </button>
                                  </div>
                                  <div className="enterprise-trace-row">
                                    <span className="enterprise-trace-label">Capabilities</span>
                                    <span>{step.capabilities.map((item) => item.name).join(", ") || "—"}</span>
                                  </div>
                                  <div className="enterprise-trace-row">
                                    <span className="enterprise-trace-label">Processes</span>
                                    <span>{step.processes.map((item) => item.name).join(", ") || "—"}</span>
                                  </div>
                                  <div className="enterprise-trace-row">
                                    <span className="enterprise-trace-label">Applications</span>
                                    <span>{step.applications.map((item) => item.name).join(", ") || "—"}</span>
                                  </div>
                                </li>
                              ))}
                            </ol>
                          )}
                          {chain.gaps.length > 0 && (
                            <ul className="enterprise-gaps">
                              {chain.gaps.map((gap) => (
                                <li key={gap}>{gap}</li>
                              ))}
                            </ul>
                          )}
                        </article>
                      ))
                  )}
                  {strategyTrace.unlinked_requirements.length > 0 && (
                    <section className="enterprise-gaps-block">
                      <strong>Unlinked requirements</strong>
                      <ul>
                        {strategyTrace.unlinked_requirements.map((item) => (
                          <li key={item.object_id}>{item.name}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {strategyTrace.gaps.length > 0 && (
                    <section className="enterprise-gaps-block">
                      <strong>Trace gaps</strong>
                      <ul>
                        {strategyTrace.gaps.map((gap) => (
                          <li key={gap}>{gap}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                </div>
              )}

              {view === "application" && applicationSupport && (
                <div className="enterprise-cards">
                  {applicationSupport.applications.filter((entry) => matches(entry.application.name))
                    .length === 0 ? (
                    <p className="architecture-topbar-hint">No applications available.</p>
                  ) : (
                    applicationSupport.applications
                      .filter((entry) => matches(entry.application.name))
                      .map((entry) => (
                        <article key={entry.application.object_id} className="enterprise-card">
                          <div className="enterprise-card-head">
                            <span className="enterprise-card-title-static">
                              {entry.application.name}
                            </span>
                            <span className="enterprise-badge">{entry.application.kind}</span>
                          </div>
                          <dl>
                            <dt>Supports capabilities</dt>
                            <dd>{entry.capabilities.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Supports processes</dt>
                            <dd>{entry.processes.map((item) => item.name).join(", ") || "—"}</dd>
                            <dt>Satisfies requirements</dt>
                            <dd>{entry.requirements.map((item) => item.name).join(", ") || "—"}</dd>
                          </dl>
                        </article>
                      ))
                  )}
                </div>
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
