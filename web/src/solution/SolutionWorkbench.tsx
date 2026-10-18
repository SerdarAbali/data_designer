import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Viewport } from "@xyflow/react";

import { moveOccurrence } from "../architectureCanvasModel";
import type { ArchitectureState } from "../architectureTypes";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import { useWorkbenchNavigation } from "../workbench/WorkbenchNavigation";
import ComponentEditorPanel, { type InterfaceDraft } from "./ComponentEditorPanel";
import DeploymentEditorPanel from "./DeploymentEditorPanel";
import InterfaceEditorPanel from "./InterfaceEditorPanel";
import OperationEditorPanel from "./OperationEditorPanel";
import RepositoryEditorPanel from "./RepositoryEditorPanel";
import TrustBoundaryEditorPanel from "./TrustBoundaryEditorPanel";
import SolutionBreadcrumb, { type BreadcrumbStep } from "./SolutionBreadcrumb";
import SolutionContextEditor from "./SolutionContextEditor";
import { solutionLog } from "./solutionLog";
import {
  addSolutionMember,
  fetchSolutionLandscape,
  createComponent,
  createDeploymentNode,
  createInterface,
  createOperation,
  createRepository,
  createSolution,
  createTrustBoundary,
  deleteComponent,
  deleteDeploymentNode,
  deleteInterface,
  deleteOperation,
  deleteRepository,
  deleteTrustBoundary,
  fetchSolutionDesign,
  linkComponentDeployment,
  linkComponentRepository,
  linkInterfaceConnection,
  linkInterfaceTrustBoundary,
  linkTrustBoundaryContainment,
  listSolutions,
  removeSolutionMember,
  updateComponent,
  updateDeploymentNode,
  updateInterface,
  updateOperation,
  updateRepository,
  updateSolution,
  updateTrustBoundary,
  type SolutionDesign,
  type SolutionOperation,
  type SolutionLandscape,
  type SolutionSummary,
} from "./solutionModel";
import SolutionContextView from "./SolutionContextView";
import SolutionLandscapeInspector from "./SolutionLandscapeInspector";
import SolutionLandscapeView from "./SolutionLandscapeView";
import SolutionDecompositionView from "./SolutionDecompositionView";
import SolutionDeploymentView from "./SolutionDeploymentView";
import SolutionInteractionView from "./SolutionInteractionView";
import SolutionTrustView from "./SolutionTrustView";
import { contextGraph, decompositionGraph, type Point } from "./solutionCanvasModel";

type Props = {
  workspaceId: string;
  activeState: ArchitectureState | null;
  editable: boolean;
  saveStatus: SaveStatus;
  search?: string;
  onAdoptState?: (state: ArchitectureState) => void;
  mutateActive?: (mutate: (state: ArchitectureState) => ArchitectureState) => void;
  onReloadStates?: () => void;
  onOpenCatalog?: () => void;
  onNavigateTrace?: (node: TraceObjectRef) => void;
  onOpenIntegration?: (integrationId: string) => void;
};

type View =
  | "landscape"
  | "context"
  | "decomposition"
  | "deployment"
  | "trust"
  | "interaction";

type CatalogSystem = { id: string; name: string; kind: string };

type Selection =
  | { kind: "solution" }
  | { kind: "component"; componentId: string }
  | { kind: "interface"; componentId: string; interfaceId: string }
  | { kind: "operation"; componentId: string; interfaceId: string; operationId: string }
  | { kind: "repository"; repositoryId: string }
  | { kind: "deployment"; deploymentId: string }
  | { kind: "trust"; trustId: string };

const VIEWS: { id: View; label: string }[] = [
  { id: "landscape", label: "Landscape" },
  { id: "context", label: "Context" },
  { id: "decomposition", label: "Decomposition" },
  { id: "deployment", label: "Deployment" },
  { id: "trust", label: "Trust boundaries" },
  { id: "interaction", label: "Interaction" },
];

export default function SolutionWorkbench({
  workspaceId,
  activeState,
  editable,
  saveStatus,
  search = "",
  mutateActive,
  onReloadStates,
  onOpenCatalog,
  onNavigateTrace,
  onOpenIntegration,
}: Props) {
  const stateId = activeState?.id ?? "";
  const stateType = activeState?.state_type ?? "current";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const [solutions, setSolutions] = useState<SolutionSummary[]>([]);
  const [selectedSolutionId, setSelectedSolutionId] = useState<string | null>(null);
  const [design, setDesign] = useState<SolutionDesign | null>(null);
  const [view, setView] = useState<View>("context");
  const [landscape, setLandscape] = useState<SolutionLandscape | null>(null);
  const [landscapeLoading, setLandscapeLoading] = useState(false);
  const [landscapeKey, setLandscapeKey] = useState(0);
  const [landscapeNodeId, setLandscapeNodeId] = useState<string | null>(null);
  const [landscapeEdgeId, setLandscapeEdgeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [selection, setSelection] = useState<Selection>({ kind: "solution" });
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [systems, setSystems] = useState<CatalogSystem[]>([]);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const viewportRef = useRef<Record<string, Viewport>>({});
  const viewportKey = `${selectedSolutionId ?? ""}:${view}`;

  const isEditable = editable && design?.editable === true;
  const landscapeEditable = editable && landscape?.editable === true;

  const reloadLandscape = useCallback(async () => {
    if (!workspaceId || !stateId) {
      setLandscape(null);
      return;
    }
    setLandscapeLoading(true);
    try {
      setLandscape(await fetchSolutionLandscape(workspaceId, stateId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the solution landscape.");
    } finally {
      setLandscapeLoading(false);
    }
  }, [workspaceId, stateId]);

  useEffect(() => {
    void reloadLandscape();
  }, [reloadLandscape, landscapeKey]);

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
    setSelection({ kind: "solution" });
    setSelectedSystemId(null);
    setInspectorCollapsed(false);
    void reloadDesign(selectedSolutionId);
  }, [reloadDesign, selectedSolutionId]);

  // A state change never carries the previous state's Landscape selection over,
  // but it does preserve the selected architecture state itself.
  useEffect(() => {
    setLandscapeNodeId(null);
    setLandscapeEdgeId(null);
  }, [stateId]);

  const openSolutionFromLandscape = useCallback((solutionObjectId: string) => {
    setSelectedSolutionId(solutionObjectId);
    setLandscapeNodeId(solutionObjectId);
    setLandscapeEdgeId(null);
    setView("context");
    setSelection({ kind: "solution" });
    setInspectorCollapsed(false);
  }, []);

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

  const selectedComponent = useMemo(() => {
    if (!design) return null;
    if (selection.kind === "component" || selection.kind === "interface" || selection.kind === "operation") {
      return design.components.find((component) => component.object_id === selection.componentId) ?? null;
    }
    return null;
  }, [design, selection]);

  const selectedInterface = useMemo(() => {
    if (!selectedComponent) return null;
    if (selection.kind === "interface" || selection.kind === "operation") {
      return selectedComponent.interfaces.find((ui) => ui.object_id === selection.interfaceId) ?? null;
    }
    return null;
  }, [selectedComponent, selection]);

  const selectedOperation = useMemo(() => {
    if (!selectedInterface) return null;
    if (selection.kind === "operation") {
      return selectedInterface.operations.find((operation) => operation.object_id === selection.operationId) ?? null;
    }
    return null;
  }, [selectedInterface, selection]);

  const selectedRepository = useMemo(() => {
    if (!design || selection.kind !== "repository") return null;
    return design.repositories.find((repository) => repository.object_id === selection.repositoryId) ?? null;
  }, [design, selection]);

  const selectedDeployment = useMemo(() => {
    if (!design || selection.kind !== "deployment") return null;
    return design.deployment_nodes.find((node) => node.object_id === selection.deploymentId) ?? null;
  }, [design, selection]);

  const selectedTrust = useMemo(() => {
    if (!design || selection.kind !== "trust") return null;
    return design.trust_boundaries.find((boundary) => boundary.object_id === selection.trustId) ?? null;
  }, [design, selection]);

  // Trace navigation: reveal the destination solution object inside the design.
  useEffect(() => {
    if (!focus || focus.discipline !== "solution") return;
    if (focus.kind === "solution_boundary") {
      if (solutions.length === 0) return;
      if (solutions.some((solution) => solution.object_id === focus.objectId)) {
        setSelectedSolutionId(focus.objectId);
        setSelection({ kind: "solution" });
      }
      clearFocus(focus.nonce);
      return;
    }
    if (!design) return;
    const component = design.components.find((item) => item.object_id === focus.objectId);
    if (component) {
      setView("decomposition");
      setSelection({ kind: "component", componentId: component.object_id });
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
        setView("decomposition");
        setSelection(
          focus.kind === "interface_operation"
            ? { kind: "operation", componentId: owner.object_id, interfaceId: ui?.object_id ?? "", operationId: focus.objectId }
            : { kind: "interface", componentId: owner.object_id, interfaceId: ui?.object_id ?? "" },
        );
        setInspectorCollapsed(false);
      } else if (focus.kind === "data_repository") {
        setView("decomposition");
        setSelection({ kind: "repository", repositoryId: focus.objectId });
      } else if (focus.kind === "deployment_node") {
        setView("deployment");
        setSelection({ kind: "deployment", deploymentId: focus.objectId });
      } else if (focus.kind === "trust_boundary") {
        setView("trust");
        setSelection({ kind: "trust", trustId: focus.objectId });
      }
    }
    clearFocus(focus.nonce);
  }, [focus, design, solutions, clearFocus]);

  function nextComponentPosition() {
    const components = design?.components ?? [];
    if (components.length === 0) return { x: 160, y: 120 };
    return { x: 160 + 40 * components.length, y: 120 + 60 * components.length };
  }

  function selectComponent(componentId: string) {
    setSelection({ kind: "component", componentId });
    setInspectorCollapsed(false);
  }

  function selectInterface(componentId: string, interfaceId: string) {
    setSelection({ kind: "interface", componentId, interfaceId });
    setInspectorCollapsed(false);
  }

  function selectOperation(componentId: string, interfaceId: string, operationId: string) {
    setSelection({ kind: "operation", componentId, interfaceId, operationId });
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
      onReloadStates?.();
      return created;
    });
  }

  async function handleCreateComponent() {
    if (!design) return;
    await run(async () => {
      const created = await createComponent(workspaceId, design.solution.solution_object_id, {
        state_id: stateId,
        name: `New component ${design.components.length + 1}`,
        position: nextComponentPosition(),
      });
      setView("decomposition");
      return created;
    });
  }

  const moveOccurrenceTo = useCallback(
    (occurrenceId: string, position: Point) => {
      if (!occurrenceId || !mutateActive) return;
      mutateActive((state) => moveOccurrence(state, occurrenceId, position));
    },
    [mutateActive],
  );

  // Recomputes the current view's layout and persists the new positions. Current
  // (read-only) states never reach here because the action is disabled.
  const handleAutoArrange = useCallback(() => {
    if (!design || !isEditable || !mutateActive) return;
    if (view === "context") {
      const graph = contextGraph(design, activeState, { auto: true });
      const moves = graph.systems.filter((system) => system.occurrenceId);
      if (moves.length === 0) return;
      mutateActive((state) =>
        moves.reduce((next, move) => moveOccurrence(next, move.occurrenceId, move.position), state),
      );
      return;
    }
    if (view === "decomposition") {
      const graph = decompositionGraph(design, activeState, { auto: true });
      const positionByObject = new Map(
        graph.components.map((item) => [item.component.object_id, item.position]),
      );
      setDesign((current) =>
        current
          ? {
              ...current,
              components: current.components.map((component) => {
                const position = positionByObject.get(component.object_id);
                return position ? { ...component, position } : component;
              }),
            }
          : current,
      );
      const moves = graph.components.filter((item) => item.occurrenceId);
      if (moves.length === 0) return;
      mutateActive((state) =>
        moves.reduce((next, move) => moveOccurrence(next, move.occurrenceId, move.position), state),
      );
    }
  }, [design, isEditable, mutateActive, view, activeState]);

  const changeMembership = useCallback(
    (action: () => Promise<SolutionDesign>) => {
      void run(async () => {
        const next = await action();
        onReloadStates?.();
        return next;
      });
    },
    [run, onReloadStates],
  );

  const breadcrumb: BreadcrumbStep[] = useMemo(() => {
    const steps: BreadcrumbStep[] = [];
    if (design) steps.push({ id: design.solution.solution_object_id, label: design.solution.name, kind: "solution" });
    if (selectedComponent) steps.push({ id: selectedComponent.object_id, label: selectedComponent.name, kind: "component" });
    if (selectedInterface) steps.push({ id: selectedInterface.object_id, label: selectedInterface.name, kind: "interface" });
    if (selectedOperation) steps.push({ id: selectedOperation.object_id, label: selectedOperation.name, kind: "operation" });
    if (selectedRepository) steps.push({ id: selectedRepository.object_id, label: selectedRepository.name, kind: "component" });
    if (selectedDeployment) steps.push({ id: selectedDeployment.object_id, label: selectedDeployment.name, kind: "component" });
    if (selectedTrust) steps.push({ id: selectedTrust.object_id, label: selectedTrust.name, kind: "component" });
    return steps;
  }, [design, selectedComponent, selectedInterface, selectedOperation, selectedRepository, selectedDeployment, selectedTrust]);

  function handleBreadcrumb(step: BreadcrumbStep) {
    if (!design) return;
    if (step.id === design.solution.solution_object_id) setSelection({ kind: "solution" });
    else if (selectedOperation?.object_id === step.id) setSelection({ kind: "interface", componentId: selectedComponent!.object_id, interfaceId: selectedInterface!.object_id });
    else if (selectedInterface?.object_id === step.id) setSelection({ kind: "component", componentId: selectedComponent!.object_id });
    else if (selectedComponent?.object_id === step.id) setSelection({ kind: "component", componentId: step.id });
    else if (selectedRepository?.object_id === step.id) setSelection({ kind: "repository", repositoryId: step.id });
    else if (selectedDeployment?.object_id === step.id) setSelection({ kind: "deployment", deploymentId: step.id });
    else if (selectedTrust?.object_id === step.id) setSelection({ kind: "trust", trustId: step.id });
  }

  const tracePanel = (objectId: string) => (
    <ObjectTracePanel
      workspaceId={workspaceId}
      stateId={stateId || null}
      objectId={objectId}
      onNavigate={onNavigateTrace}
    />
  );

  const showInspector = Boolean(design) && !inspectorCollapsed;

  const toolbarAddMenu = (
    <div className="studio-menu solution-add-menu">
      <button
        type="button"
        className="studio-add-menu"
        disabled={!isEditable || busy || !design}
        aria-expanded={addMenuOpen}
        onClick={() => setAddMenuOpen((open) => !open)}
      >
        + Add object
      </button>
      {addMenuOpen && (
        <div className="studio-menu-panel" role="menu">
          <button type="button" role="menuitem" onClick={() => { setAddMenuOpen(false); void handleCreateComponent(); }}>
            Component<small>Add a component to the solution</small>
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={!selectedComponent}
            onClick={() => {
              setAddMenuOpen(false);
              if (!selectedComponent) return;
              void run(() => createInterface(workspaceId, selectedComponent.object_id, {
                state_id: stateId, name: "New interface", direction: "provided",
              }));
            }}
          >
            Interface<small>Requires a selected component</small>
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={!selectedInterface}
            onClick={() => {
              setAddMenuOpen(false);
              if (!selectedInterface) return;
              void run(() => createOperation(workspaceId, selectedInterface.object_id, {
                state_id: stateId, name: "New operation", operation_kind: "operation",
              }));
            }}
          >
            Operation / event<small>Requires a selected interface</small>
          </button>
          <hr />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setAddMenuOpen(false);
              if (!design) return;
              void run(() => createRepository(workspaceId, design.solution.solution_object_id, { state_id: stateId, name: "New repository" }));
            }}
          >
            Data repository<small>Render inside the decomposition</small>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setAddMenuOpen(false);
              if (!design) return;
              void run(() => createDeploymentNode(workspaceId, design.solution.solution_object_id, { state_id: stateId, name: "New deployment node" }));
            }}
          >
            Deployment node<small>Host components at runtime</small>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setAddMenuOpen(false);
              if (!design) return;
              void run(() => createTrustBoundary(workspaceId, design.solution.solution_object_id, { state_id: stateId, name: "New trust boundary" }));
            }}
          >
            Trust boundary<small>Group objects by security zone</small>
          </button>
        </div>
      )}
    </div>
  );

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
        {design && toolbarAddMenu}
        {(view === "context" || view === "decomposition") && design && (
          <button
            type="button"
            className="secondary-button solution-auto-arrange"
            disabled={!isEditable || busy}
            title={isEditable ? "Recompute and save the layout for this view" : "Current state is read-only"}
            onClick={() => handleAutoArrange()}
          >
            Auto arrange
          </button>
        )}
        {onOpenCatalog && <button type="button" className="btn btn--secondary" onClick={onOpenCatalog}>Open catalog</button>}
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

        <div className={`solution-content${view === "landscape" || view === "context" || view === "decomposition" ? " solution-content-canvas" : ""}`}>
          {view === "landscape" ? (
            landscapeLoading && !landscape ? (
              <div className="landscape-empty" role="status">Loading solution landscape…</div>
            ) : !landscape ? (
              <div className="landscape-empty">
                <span className="empty-icon">◇</span>
                <h3>No solution landscape available</h3>
                <p>Duplicate the current state into a candidate to model solutions.</p>
              </div>
            ) : (
              <SolutionLandscapeView
                key={stateId}
                landscape={landscape}
                stateName={activeState?.name ?? ""}
                selectedNodeId={landscapeNodeId}
                selectedEdgeId={landscapeEdgeId}
                onSelectNode={(solutionObjectId) => {
                  setLandscapeNodeId(solutionObjectId || null);
                  setLandscapeEdgeId(null);
                  setInspectorCollapsed(false);
                }}
                onSelectEdge={(relationshipId) => {
                  setLandscapeEdgeId(relationshipId);
                  setLandscapeNodeId(null);
                  setInspectorCollapsed(false);
                }}
                onOpenSolution={openSolutionFromLandscape}
                toolbar={
                  <span className="solution-canvas-legend">
                    {landscape.solutions.length} solution
                    {landscape.solutions.length === 1 ? "" : "s"} ·{" "}
                    {landscape.relationships.length} relationship
                    {landscape.relationships.length === 1 ? "" : "s"}
                  </span>
                }
              />
            )
          ) : loading && !design ? (
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
                <SolutionContextView
                  design={design}
                  state={activeState}
                  editable={isEditable}
                  selectedSystemId={selectedSystemId}
                  onSelectSystem={(systemId) => {
                    setSelectedSystemId(systemId);
                    setSelection({ kind: "solution" });
                  }}
                  onSelectSolution={() => setSelection({ kind: "solution" })}
                  onMoveSystem={moveOccurrenceTo}
                  defaultViewport={viewportRef.current[viewportKey]}
                  onViewportChange={(viewport) => { viewportRef.current[viewportKey] = viewport; }}
                />
              )}
              {view === "decomposition" && (
                <SolutionDecompositionView
                  design={design}
                  state={activeState}
                  editable={isEditable}
                  selectedComponentId={selectedComponent?.object_id ?? null}
                  selectedInterfaceId={selectedInterface?.object_id ?? null}
                  selectedOperationId={selectedOperation?.object_id ?? null}
                  selectedRepositoryId={selectedRepository?.object_id ?? null}
                  onSelectComponent={selectComponent}
                  onSelectInterface={selectInterface}
                  onSelectOperation={selectOperation}
                  onSelectRepository={(repositoryId) => { setSelection({ kind: "repository", repositoryId }); setInspectorCollapsed(false); }}
                  onMoveComponent={(occurrenceId, position) => {
                    setDesign((current) => current
                      ? { ...current, components: current.components.map((component) => component.occurrence_id === occurrenceId ? { ...component, position } : component) }
                      : current);
                    moveOccurrenceTo(occurrenceId, position);
                  }}
                  onConnectInterfaces={(sourceInterfaceId, targetInterfaceId) =>
                    void run(() => linkInterfaceConnection(workspaceId, sourceInterfaceId, { state_id: stateId, target_object_id: targetInterfaceId }))
                  }
                  defaultViewport={viewportRef.current[viewportKey]}
                  onViewportChange={(viewport) => { viewportRef.current[viewportKey] = viewport; }}
                />
              )}
              {view === "deployment" && (
                <SolutionDeploymentView
                  design={design}
                  editable={isEditable}
                  selectedDeploymentId={selectedDeployment?.object_id ?? null}
                  selectedComponentId={selectedComponent?.object_id ?? null}
                  onSelectDeployment={(deploymentId) => { setSelection({ kind: "deployment", deploymentId }); setInspectorCollapsed(false); }}
                  onSelectComponent={selectComponent}
                  onAddDeploymentNode={() => void run(() => createDeploymentNode(workspaceId, design.solution.solution_object_id, { state_id: stateId, name: "New deployment node" }))}
                  onAssignComponent={(componentId, deploymentId) =>
                    void run(() => linkComponentDeployment(workspaceId, componentId, { state_id: stateId, target_object_id: deploymentId }))
                  }
                />
              )}
              {view === "trust" && (
                <SolutionTrustView
                  design={design}
                  editable={isEditable}
                  selectedTrustId={selectedTrust?.object_id ?? null}
                  selectedComponentId={selectedComponent?.object_id ?? null}
                  onSelectTrust={(trustId) => { setSelection({ kind: "trust", trustId }); setInspectorCollapsed(false); }}
                  onSelectComponent={selectComponent}
                  onAddTrustBoundary={() => void run(() => createTrustBoundary(workspaceId, design.solution.solution_object_id, { state_id: stateId, name: "New trust boundary" }))}
                />
              )}
              {view === "interaction" && (
                <SolutionInteractionView
                  design={design}
                  editable={isEditable}
                  selectedOperationId={selectedOperation?.object_id ?? null}
                  selectedInterfaceId={selectedInterface?.object_id ?? null}
                  onSelectOperation={selectOperation}
                  onSelectInterface={selectInterface}
                  onAddComponent={() => void handleCreateComponent()}
                />
              )}
            </>
          )}
        </div>

        {inspectorCollapsed && design && (
          <button type="button" className="studio-reopen-inspector" onClick={() => setInspectorCollapsed(false)}>Open inspector</button>
        )}

        {!inspectorCollapsed && view === "landscape" && landscape && (
          <SolutionLandscapeInspector
            landscape={landscape}
            workspaceId={workspaceId}
            stateId={stateId}
            stateName={activeState?.name ?? ""}
            selectedNodeId={landscapeNodeId}
            selectedEdgeId={landscapeEdgeId}
            busy={busy || landscapeLoading}
            onSelectNode={(solutionObjectId) => {
              setLandscapeNodeId(solutionObjectId || null);
              setLandscapeEdgeId(null);
            }}
            onSelectEdge={(relationshipId) => {
              setLandscapeEdgeId(relationshipId);
              setLandscapeNodeId(null);
            }}
            onOpenSolution={openSolutionFromLandscape}
            onOpenContract={(contractId) => onOpenIntegration?.(contractId)}
            onChanged={() => setLandscapeKey((current) => current + 1)}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={
              landscapeNodeId
                ? tracePanel(landscapeNodeId)
                : <p className="muted">Select a solution to see its traceability.</p>
            }
          />
        )}

        {!inspectorCollapsed && view !== "landscape" && design && selection.kind === "solution" && (
          <SolutionContextEditor
            design={design}
            systems={systems}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            selectedSystemId={selectedSystemId}
            onSave={(patch) => void run(() => updateSolution(workspaceId, design.solution.solution_object_id, stateId, patch))}
            onAddMember={(systemId) => changeMembership(() => addSolutionMember(workspaceId, design.solution.solution_object_id, { state_id: stateId, system_id: systemId }))}
            onRemoveMember={(systemId) => changeMembership(() => removeSolutionMember(workspaceId, design.solution.solution_object_id, systemId, stateId))}
            onSelectSystem={setSelectedSystemId}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(design.solution.solution_object_id)}
            workspaceId={workspaceId}
            stateId={stateId}
            onOpenContract={onOpenIntegration}
          />
        )}

        {!inspectorCollapsed && design && selection.kind === "operation" && selectedOperation && selectedInterface && selectedComponent && (
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
                setSelection({ kind: "interface", componentId: selectedComponent.object_id, interfaceId: selectedInterface.object_id });
                return next;
              });
            }}
            onBack={() => setSelection({ kind: "interface", componentId: selectedComponent.object_id, interfaceId: selectedInterface.object_id })}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(selectedOperation.object_id)}
          />
        )}

        {!inspectorCollapsed && design && selection.kind === "interface" && selectedInterface && selectedComponent && (
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
                setSelection({ kind: "component", componentId: selectedComponent.object_id });
                return next;
              });
            }}
            onSelectOperation={(operationId) => selectOperation(selectedComponent.object_id, selectedInterface.object_id, operationId)}
            onAddOperation={(draft: { name: string; operation_kind: SolutionOperation["operation_kind"] }) =>
              void run(() => createOperation(workspaceId, selectedInterface.object_id, { ...draft, state_id: stateId }))}
            onBack={() => setSelection({ kind: "component", componentId: selectedComponent.object_id })}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(selectedInterface.object_id)}
          />
        )}

        {!inspectorCollapsed && design && selection.kind === "component" && selectedComponent && (
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
                setSelection({ kind: "solution" });
                return next;
              });
            }}
            onSelectInterface={(interfaceId) => selectInterface(selectedComponent.object_id, interfaceId)}
            onAddInterface={(draft: InterfaceDraft) => void run(() => createInterface(workspaceId, selectedComponent.object_id, {
              ...draft,
              interface_kind: draft.interface_kind || null,
              state_id: stateId,
            }))}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(selectedComponent.object_id)}
          />
        )}

        {!inspectorCollapsed && design && selection.kind === "repository" && selectedRepository && (
          <RepositoryEditorPanel
            key={selectedRepository.object_id}
            design={design}
            repository={selectedRepository}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(repositoryId, patch) => void run(() => updateRepository(workspaceId, repositoryId, { ...patch, state_id: stateId }))}
            onDelete={(repositoryId) => {
              if (!window.confirm("Delete this repository and its links?")) return;
              void run(async () => {
                const next = await deleteRepository(workspaceId, repositoryId, stateId);
                setSelection({ kind: "solution" });
                return next;
              });
            }}
            onLinkComponent={(componentId, repositoryId) =>
              void run(() => linkComponentRepository(workspaceId, componentId, { state_id: stateId, target_object_id: repositoryId }))
            }
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(selectedRepository.object_id)}
          />
        )}

        {!inspectorCollapsed && design && selection.kind === "deployment" && selectedDeployment && (
          <DeploymentEditorPanel
            key={selectedDeployment.object_id}
            design={design}
            node={selectedDeployment}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(deploymentId, patch) => void run(() => updateDeploymentNode(workspaceId, deploymentId, { ...patch, state_id: stateId }))}
            onDelete={(deploymentId) => {
              if (!window.confirm("Delete this deployment node?")) return;
              void run(async () => {
                const next = await deleteDeploymentNode(workspaceId, deploymentId, stateId);
                setSelection({ kind: "solution" });
                return next;
              });
            }}
            onAssignComponent={(componentId, deploymentId) => void run(() => linkComponentDeployment(workspaceId, componentId, { state_id: stateId, target_object_id: deploymentId }))}
            onSelectComponent={selectComponent}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(selectedDeployment.object_id)}
          />
        )}

        {!inspectorCollapsed && design && selection.kind === "trust" && selectedTrust && (
          <TrustBoundaryEditorPanel
            key={selectedTrust.object_id}
            design={design}
            boundary={selectedTrust}
            editable={isEditable}
            stateName={activeState?.name ?? ""}
            saveStatus={saveStatus}
            busy={busy}
            onSave={(trustId, patch) => void run(() => updateTrustBoundary(workspaceId, trustId, { ...patch, state_id: stateId }))}
            onDelete={(trustId) => {
              if (!window.confirm("Delete this trust boundary?")) return;
              void run(async () => {
                const next = await deleteTrustBoundary(workspaceId, trustId, stateId);
                setSelection({ kind: "solution" });
                return next;
              });
            }}
            onContain={(sourceObjectId, trustId) => void run(() => linkTrustBoundaryContainment(workspaceId, sourceObjectId, { state_id: stateId, target_object_id: trustId }))}
            onCross={(interfaceId, trustId) => void run(() => linkInterfaceTrustBoundary(workspaceId, interfaceId, { state_id: stateId, target_object_id: trustId }))}
            onSelectComponent={selectComponent}
            onClose={() => setInspectorCollapsed(true)}
            onCollapse={() => setInspectorCollapsed(true)}
            trace={tracePanel(selectedTrust.object_id)}
          />
        )}
      </div>
    </div>
  );
}
