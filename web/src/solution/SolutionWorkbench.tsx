import { useCallback, useEffect, useMemo, useState } from "react";

import type { ArchitectureState } from "../architectureTypes";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import { useWorkbenchNavigation } from "../workbench/WorkbenchNavigation";
import ComponentEditorPanel, { type InterfaceDraft } from "./ComponentEditorPanel";
import InterfaceEditorPanel from "./InterfaceEditorPanel";
import OperationEditorPanel from "./OperationEditorPanel";
import SolutionBreadcrumb, { type BreadcrumbStep } from "./SolutionBreadcrumb";
import {
  addSolutionMember,
  createComponent,
  createDeploymentNode,
  createInterface,
  createOperation,
  createRepository,
  createSolution,
  createTrustBoundary,
  deleteComponent,
  deleteInterface,
  deleteOperation,
  fetchSolutionDesign,
  linkComponentDeployment,
  linkComponentRepository,
  linkInterfaceTrustBoundary,
  listSolutions,
  removeSolutionMember,
  updateComponent,
  updateInterface,
  updateOperation,
  updateSolution,
  type SolutionComponent,
  type SolutionDesign,
  type SolutionInterface,
  type SolutionOperation,
  type SolutionSummary,
} from "./solutionModel";
import SolutionSequenceView from "./SolutionSequenceView";
import { solutionLog } from "./solutionLog";

type Props = {
  workspaceId: string;
  activeState: ArchitectureState | null;
  editable: boolean;
  saveStatus: SaveStatus;
  search?: string;
  onAdoptState?: (state: ArchitectureState) => void;
  mutateActive?: (mutate: (state: ArchitectureState) => ArchitectureState) => void;
  onOpenCatalog?: () => void;
  onNavigateTrace?: (node: TraceObjectRef) => void;
};

type View = "context" | "components" | "repositories" | "deployment" | "trust" | "sequence";

type CatalogSystem = { id: string; name: string; kind: string };

const VIEWS: { id: View; label: string }[] = [
  { id: "context", label: "Context" },
  { id: "components", label: "Decomposition" },
  { id: "repositories", label: "Repositories" },
  { id: "deployment", label: "Deployment" },
  { id: "trust", label: "Trust boundaries" },
  { id: "sequence", label: "Interaction" },
];

export default function SolutionWorkbench({
  workspaceId,
  activeState,
  editable,
  saveStatus,
  search = "",
  onOpenCatalog,
  onNavigateTrace,
}: Props) {
  const stateId = activeState?.id ?? "";
  const stateType = activeState?.state_type ?? "current";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const [solutions, setSolutions] = useState<SolutionSummary[]>([]);
  const [selectedSolutionId, setSelectedSolutionId] = useState<string | null>(null);
  const [design, setDesign] = useState<SolutionDesign | null>(null);
  const [view, setView] = useState<View>("context");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [selectedInterfaceId, setSelectedInterfaceId] = useState<string | null>(null);
  const [selectedOperationId, setSelectedOperationId] = useState<string | null>(null);
  const [systems, setSystems] = useState<CatalogSystem[]>([]);

  const isEditable = editable && design?.state_type !== "current";

  const reloadList = useCallback(async () => {
    if (!workspaceId || !stateId) {
      setSolutions([]);
      return;
    }
    try {
      const next = await listSolutions(workspaceId, stateId);
      setSolutions(next);
      setSelectedSolutionId((current) => {
        if (current && next.some((solution) => solution.object_id === current)) return current;
        return next[0]?.object_id ?? null;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load solutions.");
    }
  }, [workspaceId, stateId]);

  const reloadDesign = useCallback(async (solutionId: string | null) => {
    if (!workspaceId || !stateId || !solutionId) {
      setDesign(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const next = await fetchSolutionDesign(workspaceId, solutionId, stateId);
      setDesign(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the solution design.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, stateId]);

  useEffect(() => {
    void reloadList();
  }, [reloadList]);

  useEffect(() => {
    setSelectedComponentId(null);
    setSelectedInterfaceId(null);
    setSelectedOperationId(null);
    setInspectorCollapsed(false);
    void reloadDesign(selectedSolutionId);
  }, [reloadDesign, selectedSolutionId]);

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId) return;
    fetch(`/api/catalog/systems?limit=500&offset=0`)
      .then((response) => (response.ok ? response.json() : []))
      .then((page: CatalogSystem[]) => {
        if (!cancelled) setSystems(Array.isArray(page) ? page : []);
      })
      .catch((caught) => solutionLog.error("load catalog systems failed", caught));
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const run = useCallback(
    async (operation: () => Promise<SolutionDesign | void>) => {
      setBusy(true);
      setError("");
      try {
        const result = await operation();
        if (result) setDesign(result);
        else await reloadDesign(selectedSolutionId);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "The change could not be saved.";
        setError(message);
        solutionLog.error("mutation failed", message);
      } finally {
        setBusy(false);
      }
    },
    [reloadDesign, selectedSolutionId],
  );

  const selectedComponent = useMemo(
    () => design?.components.find((component) => component.object_id === selectedComponentId) ?? null,
    [design, selectedComponentId],
  );
  const selectedInterface = useMemo(
    () => selectedComponent?.interfaces.find((ui) => ui.object_id === selectedInterfaceId) ?? null,
    [selectedComponent, selectedInterfaceId],
  );
  const selectedOperation = useMemo(
    () => selectedInterface?.operations.find((operation) => operation.object_id === selectedOperationId) ?? null,
    [selectedInterface, selectedOperationId],
  );

  // Trace navigation: reveal the destination solution object inside the design.
  useEffect(() => {
    if (!focus || focus.discipline !== "solution") return;
    if (focus.kind === "solution_boundary") {
      if (solutions.length === 0) return; // wait for the solution list to load
      if (solutions.some((solution) => solution.object_id === focus.objectId)) {
        setSelectedSolutionId(focus.objectId);
      }
      clearFocus(focus.nonce);
      return;
    }
    if (!design) return; // wait for the design before deciding
    const component = design.components.find((item) => item.object_id === focus.objectId);
    if (component) {
      setView("components");
      setSelectedComponentId(component.object_id);
      setSelectedInterfaceId(null);
      setSelectedOperationId(null);
      setInspectorCollapsed(false);
    } else {
      const owner = design.components.find((item) =>
        item.interfaces.some(
          (ui) =>
            ui.object_id === focus.objectId ||
            ui.operations.some((operation) => operation.object_id === focus.objectId),
        ),
      );
      if (owner) {
        const ui = owner.interfaces.find(
          (candidate) =>
            candidate.object_id === focus.objectId ||
            candidate.operations.some((operation) => operation.object_id === focus.objectId),
        );
        setView("components");
        setSelectedComponentId(owner.object_id);
        setSelectedInterfaceId(ui?.object_id ?? null);
        setSelectedOperationId(focus.kind === "interface_operation" ? focus.objectId : null);
        setInspectorCollapsed(false);
      } else if (focus.kind === "data_repository") {
        setView("repositories");
      } else if (focus.kind === "deployment_node") {
        setView("deployment");
      } else if (focus.kind === "trust_boundary") {
        setView("trust");
      }
    }
    clearFocus(focus.nonce);
  }, [focus, design, solutions, clearFocus]);

  const visibleComponents = useMemo(() => {
    if (!design) return [];
    const term = search.trim().toLowerCase();
    if (!term) return design.components;
    return design.components.filter((component) =>
      component.name.toLowerCase().includes(term) ||
      (component.responsibility ?? "").toLowerCase().includes(term) ||
      component.interfaces.some((ui) => ui.name.toLowerCase().includes(term)),
    );
  }, [design, search]);

  function nextComponentPosition() {
    const components = design?.components ?? [];
    if (components.length === 0) return { x: 160, y: 120 };
    return { x: 160 + 40 * components.length, y: 120 + 60 * components.length };
  }

  function handleSelectComponent(componentId: string) {
    setSelectedComponentId(componentId);
    setSelectedInterfaceId(null);
    setSelectedOperationId(null);
    setInspectorCollapsed(false);
  }

  function handleSelectInterface(interfaceId: string) {
    setSelectedInterfaceId(interfaceId);
    setSelectedOperationId(null);
    setInspectorCollapsed(false);
  }

  async function handleCreateSolution() {
    if (!stateId) return;
    const name = window.prompt("Solution name", "New Solution");
    if (!name) return;
    await run(async () => {
      const created = await createSolution(workspaceId, { state_id: stateId, name, position: { x: 80, y: 80 } });
      setSelectedSolutionId(created.solution.solution_object_id);
      await reloadList();
      return created;
    });
  }

  async function handleCreateComponent() {
    if (!design) return;
    await run(async () => {
      const created = await createComponent(workspaceId, design.solution.solution_object_id, {
        state_id: stateId,
        name: "New component",
        position: nextComponentPosition(),
      });
      const component = created.components.find((item) => item.name === "New component");
      if (component) setSelectedComponentId(component.object_id);
      setView("components");
      return created;
    });
  }

  const breadcrumb: BreadcrumbStep[] = useMemo(() => {
    const steps: BreadcrumbStep[] = [];
    if (design) steps.push({ id: design.solution.solution_object_id, label: design.solution.name, kind: "solution" });
    if (selectedComponent) steps.push({ id: selectedComponent.object_id, label: selectedComponent.name, kind: "component" });
    if (selectedInterface) steps.push({ id: selectedInterface.object_id, label: selectedInterface.name, kind: "interface" });
    if (selectedOperation) steps.push({ id: selectedOperation.object_id, label: selectedOperation.name, kind: "operation" });
    return steps;
  }, [design, selectedComponent, selectedInterface, selectedOperation]);

  function handleBreadcrumb(step: BreadcrumbStep) {
    if (step.kind === "solution") {
      setSelectedComponentId(null);
      setSelectedInterfaceId(null);
      setSelectedOperationId(null);
    } else if (step.kind === "component") {
      setSelectedInterfaceId(null);
      setSelectedOperationId(null);
    } else if (step.kind === "interface") {
      setSelectedOperationId(null);
    }
  }

  const showInspector = Boolean(selectedComponent) && !inspectorCollapsed;

  return (
    <div className={`solution-workbench${showInspector ? " has-panel" : ""}`}>
      <div className="solution-toolbar">
        <select
          aria-label="Select solution"
          className="solution-picker"
          value={selectedSolutionId ?? ""}
          onChange={(event) => setSelectedSolutionId(event.target.value || null)}
        >
          {solutions.length === 0 && <option value="">No solutions in this state</option>}
          {solutions.map((solution) => (
            <option key={solution.object_id} value={solution.object_id}>
              {solution.name}
            </option>
          ))}
        </select>
        <button type="button" className="studio-add-menu" disabled={!isEditable || busy || !stateId} onClick={() => void handleCreateSolution()}>
          + New solution
        </button>
        <button type="button" className="studio-add-menu" disabled={!isEditable || busy || !design} onClick={() => void handleCreateComponent()}>
          + New component
        </button>
        <span className="solution-toolbar-hint">
          {isEditable ? "Model components, interfaces, operations and their links." : "Current state is read-only. Duplicate it to model changes."}
        </span>
        {onOpenCatalog && <button type="button" className="secondary-button" onClick={onOpenCatalog}>Open catalog</button>}
      </div>

      {error && (
        <div className="studio-canvas-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss error">×</button>
        </div>
      )}

      {design && <SolutionBreadcrumb steps={breadcrumb} onNavigate={handleBreadcrumb} />}

      <div className="solution-body">
        <nav className="solution-views" aria-label="Solution views">
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

        <div className="solution-content">
          {loading && !design ? (
            <div className="landscape-empty" role="status">Loading solution design…</div>
          ) : !design ? (
            <div className="landscape-empty">
              <span className="empty-icon">◇</span>
              <h3>No solution selected</h3>
              <p>{isEditable ? "Create a solution to start modelling." : "Duplicate the current state into a candidate to add solutions."}</p>
              {isEditable && <button type="button" onClick={() => void handleCreateSolution()}>+ New solution</button>}
            </div>
          ) : (
            <>
              {view === "context" && (
                <SolutionContextPanel
                  design={design}
                  systems={systems}
                  editable={isEditable}
                  busy={busy}
                  onSave={(patch) => void run(() => updateSolution(workspaceId, design.solution.solution_object_id, stateId, patch))}
                  onAddMember={(systemId) => void run(() => addSolutionMember(workspaceId, design.solution.solution_object_id, { state_id: stateId, system_id: systemId }))}
                  onRemoveMember={(systemId) => void run(() => removeSolutionMember(workspaceId, design.solution.solution_object_id, systemId, stateId))}
                />
              )}

              {view === "components" && (
                <div className="solution-components">
                  {visibleComponents.length === 0 ? (
                    <p className="architecture-topbar-hint">No components match. Add one to decompose the solution.</p>
                  ) : (
                    <ul className="solution-component-grid">
                      {visibleComponents.map((component) => (
                        <li key={component.object_id}>
                          <button
                            type="button"
                            className={`solution-component-card${component.object_id === selectedComponentId ? " selected" : ""}`}
                            onClick={() => handleSelectComponent(component.object_id)}
                          >
                            <strong>{component.name}</strong>
                            {component.component_type && <em>{component.component_type}</em>}
                            <span>{component.responsibility ?? "No responsibility recorded."}</span>
                            <small>
                              <b className="direction-provided">{component.interfaces.filter((ui) => ui.direction === "provided").length} provided</b>
                              <b className="direction-required">{component.interfaces.filter((ui) => ui.direction === "required").length} required</b>
                            </small>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {view === "repositories" && (
                <SolutionResourcePanel
                  title="Data repositories"
                  items={design.repositories.map((repository) => ({
                    id: repository.object_id,
                    name: repository.name,
                    meta: [repository.repository_type, repository.technology, repository.owner].filter(Boolean).join(" · "),
                  }))}
                  components={design.components}
                  links={design.links}
                  relationshipType="uses_repository"
                  editable={isEditable}
                  busy={busy}
                  onCreate={(name) => void run(() => createRepository(workspaceId, design.solution.solution_object_id, { state_id: stateId, name }))}
                  onLink={(componentId, targetId) => void run(() => linkComponentRepository(workspaceId, componentId, { state_id: stateId, target_object_id: targetId }))}
                />
              )}

              {view === "deployment" && (
                <SolutionResourcePanel
                  title="Deployment nodes"
                  items={design.deployment_nodes.map((node) => ({
                    id: node.object_id,
                    name: node.name,
                    meta: [node.environment, node.hosting, node.technology].filter(Boolean).join(" · "),
                  }))}
                  components={design.components}
                  links={design.links}
                  relationshipType="deployed_on"
                  editable={isEditable}
                  busy={busy}
                  onCreate={(name) => void run(() => createDeploymentNode(workspaceId, design.solution.solution_object_id, { state_id: stateId, name }))}
                  onLink={(componentId, targetId) => void run(() => linkComponentDeployment(workspaceId, componentId, { state_id: stateId, target_object_id: targetId }))}
                />
              )}

              {view === "trust" && (
                <SolutionTrustPanel
                  design={design}
                  editable={isEditable}
                  busy={busy}
                  onCreate={(name) => void run(() => createTrustBoundary(workspaceId, design.solution.solution_object_id, { state_id: stateId, name }))}
                  onLink={(interfaceId, targetId) => void run(() => linkInterfaceTrustBoundary(workspaceId, interfaceId, { state_id: stateId, target_object_id: targetId }))}
                />
              )}

              {view === "sequence" && (
                <SolutionSequenceView solutionName={design.solution.name} components={design.components} />
              )}
            </>
          )}
        </div>

        {inspectorCollapsed && selectedComponent && (
          <button type="button" className="studio-reopen-inspector" onClick={() => setInspectorCollapsed(false)}>Open inspector</button>
        )}

        {!inspectorCollapsed && selectedComponent && selectedInterface && selectedOperation && (
          <OperationEditorPanel
            key={selectedOperation.object_id}
            interfaceName={selectedInterface.name}
            operation={selectedOperation}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(operationId, patch) => void run(() => updateOperation(workspaceId, operationId, { ...patch, state_id: stateId }))}
            onDelete={(operationId) => {
              if (!window.confirm("Delete this operation?")) return;
              void run(async () => {
                const next = await deleteOperation(workspaceId, operationId, stateId);
                setSelectedOperationId(null);
                return next;
              });
            }}
            onBack={() => setSelectedOperationId(null)}
            onClose={() => { setSelectedOperationId(null); setSelectedInterfaceId(null); }}
            onCollapse={() => setInspectorCollapsed(true)}
          />
        )}

        {!inspectorCollapsed && selectedComponent && selectedInterface && !selectedOperation && (
          <InterfaceEditorPanel
            key={selectedInterface.object_id}
            componentName={selectedComponent.name}
            interfaceDetail={selectedInterface}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(interfaceId, patch) => void run(() => updateInterface(workspaceId, interfaceId, { ...patch, state_id: stateId }))}
            onDelete={(interfaceId) => {
              if (!window.confirm("Delete this interface and its operations?")) return;
              void run(async () => {
                const next = await deleteInterface(workspaceId, interfaceId, stateId);
                setSelectedInterfaceId(null);
                return next;
              });
            }}
            onSelectOperation={(operationId) => { setSelectedOperationId(operationId); setInspectorCollapsed(false); }}
            onAddOperation={(draft) => void run(() => createOperation(workspaceId, selectedInterface.object_id, { ...draft, state_id: stateId }))}
            onBack={() => setSelectedInterfaceId(null)}
            onClose={() => { setSelectedInterfaceId(null); setSelectedComponentId(null); }}
            onCollapse={() => setInspectorCollapsed(true)}
          />
        )}

        {!inspectorCollapsed && selectedComponent && !selectedInterface && (
          <ComponentEditorPanel
            key={selectedComponent.object_id}
            component={selectedComponent}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(componentId, patch) => void run(() => updateComponent(workspaceId, componentId, { ...patch, state_id: stateId }))}
            onDelete={(componentId) => {
              if (!window.confirm("Delete this component, its interfaces and operations?")) return;
              void run(async () => {
                const next = await deleteComponent(workspaceId, componentId, stateId);
                setSelectedComponentId(null);
                return next;
              });
            }}
            onSelectInterface={(interfaceId) => handleSelectInterface(interfaceId)}
            onAddInterface={(draft: InterfaceDraft) => void run(() => createInterface(workspaceId, selectedComponent.object_id, {
              ...draft,
              interface_kind: draft.interface_kind || null,
              state_id: stateId,
            }))}
            onClose={() => setSelectedComponentId(null)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={(
              <ObjectTracePanel
                workspaceId={workspaceId}
                stateId={stateId || null}
                objectId={selectedComponent.object_id}
                onNavigate={onNavigateTrace}
              />
            )}
          />
        )}

      </div>
    </div>
  );
}

type ContextProps = {
  design: SolutionDesign;
  systems: CatalogSystem[];
  editable: boolean;
  busy: boolean;
  onSave: (patch: { name?: string; owner?: string | null; description?: string | null }) => void;
  onAddMember: (systemId: string) => void;
  onRemoveMember: (systemId: string) => void;
};

function SolutionContextPanel({ design, systems, editable, busy, onSave, onAddMember, onRemoveMember }: ContextProps) {
  const [name, setName] = useState(design.solution.name);
  const [owner, setOwner] = useState(design.solution.owner ?? "");
  const [description, setDescription] = useState(design.solution.description ?? "");
  const [memberToAdd, setMemberToAdd] = useState("");

  useEffect(() => {
    setName(design.solution.name);
    setOwner(design.solution.owner ?? "");
    setDescription(design.solution.description ?? "");
  }, [design.solution]);

  const memberIds = new Set(design.solution.members.map((member) => member.system_id));
  const available = systems.filter((system) => !memberIds.has(system.id));

  return (
    <div className="solution-context">
      <article className="solution-context-card">
        <p className="eyebrow">SOLUTION</p>
        <label>
          Name
          <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          Owner
          <input value={owner} disabled={!editable} placeholder="Optional" onChange={(event) => setOwner(event.target.value)} />
        </label>
        <label>
          Description
          <textarea value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} />
        </label>
        {editable && (
          <button type="button" disabled={busy} onClick={() => onSave({ name, owner, description })}>
            {busy ? "Saving…" : "Save context"}
          </button>
        )}
      </article>

      <section className="solution-members">
        <div className="information-section-heading">
          <strong>Member systems</strong>
          <span className="item-count">{design.solution.members.length}</span>
        </div>
        {design.solution.members.length === 0 ? (
          <p className="architecture-topbar-hint">No member systems yet.</p>
        ) : (
          <ul className="solution-member-list">
            {design.solution.members.map((member) => (
              <li key={member.system_id}>
                <span>{member.name}</span>
                <small>{member.kind}</small>
                {editable && (
                  <button type="button" className="secondary-button" onClick={() => onRemoveMember(member.system_id)}>Remove</button>
                )}
              </li>
            ))}
          </ul>
        )}
        {editable && (
          <div className="solution-member-add">
            <select value={memberToAdd} onChange={(event) => setMemberToAdd(event.target.value)}>
              <option value="">Add a system…</option>
              {available.map((system) => (
                <option key={system.id} value={system.id}>{system.name}</option>
              ))}
            </select>
            <button
              type="button"
              disabled={busy || !memberToAdd}
              onClick={() => {
                onAddMember(memberToAdd);
                setMemberToAdd("");
              }}
            >
              Add member
            </button>
          </div>
        )}

        {design.solution.external_systems.length > 0 && (
          <div className="solution-external">
            <strong>External systems on the canvas</strong>
            <ul>
              {design.solution.external_systems.map((system) => (
                <li key={system.system_id}>{system.name}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

type ResourcePanelProps = {
  title: string;
  items: { id: string; name: string; meta: string }[];
  components: SolutionComponent[];
  links: SolutionDesign["links"];
  relationshipType: string;
  editable: boolean;
  busy: boolean;
  onCreate: (name: string) => void;
  onLink: (componentId: string, targetId: string | null) => void;
};

function SolutionResourcePanel({
  title,
  items,
  components,
  links,
  relationshipType,
  editable,
  busy,
  onCreate,
  onLink,
}: ResourcePanelProps) {
  const [draftName, setDraftName] = useState("");
  return (
    <div className="solution-resource">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="architecture-topbar-hint">Nothing recorded yet.</p>
      ) : (
        <ul className="solution-resource-list">
          {items.map((item) => {
            const connected = links
              .filter((link) => link.relationship_type === relationshipType && link.target_object_id === item.id)
              .map((link) => link.source_object_id);
            return (
              <li key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  {item.meta && <small>{item.meta}</small>}
                </div>
                <div className="solution-resource-links">
                  {connected.length > 0 && (
                    <span className="solution-link-chips">
                      {connected
                        .map((componentId) => components.find((component) => component.object_id === componentId)?.name)
                        .filter(Boolean)
                        .join(", ")}
                    </span>
                  )}
                  {editable && (
                    <select
                      aria-label={`Connect component to ${item.name}`}
                      defaultValue=""
                      onChange={(event) => {
                        if (event.target.value) onLink(event.target.value, item.id);
                      }}
                    >
                      <option value="">Connect component…</option>
                      {components.map((component) => (
                        <option key={component.object_id} value={component.object_id}>{component.name}</option>
                      ))}
                    </select>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {editable && (
        <div className="solution-resource-add">
          <input
            value={draftName}
            placeholder={`New ${title.toLowerCase().replace(/s$/, "")}`}
            onChange={(event) => setDraftName(event.target.value)}
          />
          <button
            type="button"
            disabled={busy || !draftName.trim()}
            onClick={() => {
              onCreate(draftName.trim());
              setDraftName("");
            }}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

type TrustPanelProps = {
  design: SolutionDesign;
  editable: boolean;
  busy: boolean;
  onCreate: (name: string) => void;
  onLink: (interfaceId: string, targetId: string | null) => void;
};

function SolutionTrustPanel({ design, editable, busy, onCreate, onLink }: TrustPanelProps) {
  const [draftName, setDraftName] = useState("");
  const interfaces = design.components.flatMap((component) => component.interfaces);
  return (
    <div className="solution-resource">
      <h3>Trust boundaries</h3>
      {design.trust_boundaries.length === 0 ? (
        <p className="architecture-topbar-hint">Nothing recorded yet.</p>
      ) : (
        <ul className="solution-resource-list">
          {design.trust_boundaries.map((boundary) => {
            const connected = design.links
              .filter((link) => link.relationship_type === "crosses" && link.target_object_id === boundary.object_id)
              .map((link) => link.source_object_id);
            return (
              <li key={boundary.object_id}>
                <div>
                  <strong>{boundary.name}</strong>
                  {boundary.security_level && <small>{boundary.security_level}</small>}
                </div>
                <div className="solution-resource-links">
                  {connected.length > 0 && (
                    <span className="solution-link-chips">
                      {connected
                        .map((interfaceId) => interfaces.find((ui) => ui.object_id === interfaceId)?.name)
                        .filter(Boolean)
                        .join(", ")}
                    </span>
                  )}
                  {editable && (
                    <select
                      aria-label={`Cross interface over ${boundary.name}`}
                      defaultValue=""
                      onChange={(event) => {
                        if (event.target.value) onLink(event.target.value, boundary.object_id);
                      }}
                    >
                      <option value="">Cross interface…</option>
                      {interfaces.map((ui) => (
                        <option key={ui.object_id} value={ui.object_id}>{ui.name}</option>
                      ))}
                    </select>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {editable && (
        <div className="solution-resource-add">
          <input value={draftName} placeholder="New trust boundary" onChange={(event) => setDraftName(event.target.value)} />
          <button
            type="button"
            disabled={busy || !draftName.trim()}
            onClick={() => {
              onCreate(draftName.trim());
              setDraftName("");
            }}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}
