import React from "react";
import {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  applyNodeChanges,
  type Connection,
  type NodeChange,
} from "@xyflow/react";
import ArchitectureTopBar, { type SaveStatus } from "./components/architecture/ArchitectureTopBar";
import ArchitectureOccurrenceNodeCard, {
  type ArchitectureOccurrenceNode,
} from "./components/architecture/ArchitectureOccurrenceNode";
import ArchitectureDisciplineTabs from "./components/architecture/ArchitectureDisciplineTabs";
import ArchitectureBoundaryNode from "./components/architecture/ArchitectureBoundaryNode";
import ArchitectureRelationshipEdge, {
  type ArchitectureRelationshipFlowEdge,
} from "./components/architecture/ArchitectureRelationshipEdge";
import {
  chooseHandles,
  handleId,
  type Rect,
} from "./components/architecture/architectureRouting";
import { type NavigationGuard } from "./contextSaveQueue";
import StudioMenu from "./components/architecture/StudioMenu";
import ArchitectureObjectDialog, {
  type ArchitectureObjectDraft,
} from "./components/architecture/ArchitectureObjectDialog";
import ArchitectureObjectInspector from "./components/architecture/ArchitectureObjectInspector";
import EnterpriseWorkbench from "./enterprise/EnterpriseWorkbench";
import InformationWorkbench from "./information/InformationWorkbench";
import IntegrationWorkbench from "./integration/IntegrationWorkbench";
import SolutionWorkbench from "./solution/SolutionWorkbench";
import {
  SEMANTIC_RELATIONSHIP_TYPES,
  type ArchitectureDiscipline,
  type ArchitectureObjectKind,
  type ArchitectureState,
  type ArchitectureObject,
  type SemanticRelationshipType,
  type WorkspaceInfo,
} from "./architectureTypes";
import type { TraceObjectRef } from "./workbench/workbenchTypes";
import { api } from "./apiClient";
import {
  useArchitectureModel,
  type GraphDocument,
  type Integration,
} from "./workbench/useArchitectureModel";
import {
  WorkbenchNavigationProvider,
  useWorkbenchNavigation,
} from "./workbench/WorkbenchNavigation";
import {
  addOccurrence,
  addRelationship,
  moveOccurrence,
  nextFreePosition,
  removeOccurrence,
  removeRelationship,
  resolveOccurrence,
  resolveRelationships,
  updateRelationship,
  solutionBoundaryGeometry,
  type CanonicalSystem,
  type ResolvedRelationship,
  type BoundaryGeometry,
  projectStateNodes,
} from "./architectureCanvasModel";
import type { ScenarioPhase } from "./scenarioModel";

type TestStatus = "passing" | "failing" | "untested" | "error";

type IntegrationHealth = {
  revision: number;
  mapped: number;
  total: number;
  test: TestStatus;
  coverageError?: string;
};

const TEST_LABEL: Record<TestStatus, string> = {
  passing: "✓ tests pass",
  failing: "✕ tests fail",
  untested: "no tests",
  error: "tests unavailable",
};

const TEST_COLOR: Record<TestStatus, string> = {
  passing: "var(--color-healthy)",
  failing: "var(--color-danger)",
  untested: "var(--color-integration)",
  error: "var(--color-attention)",
};

function mappedTargetFieldIds(graph: GraphDocument): Set<string> {
  const targetNodes = new Set(graph.nodes.filter((node) => node.type === "target").map((node) => node.id));
  const mapped = new Set<string>();
  for (const edge of graph.edges) {
    if (targetNodes.has(edge.targetNodeId) && edge.targetPortId.startsWith("field:")) {
      mapped.add(edge.targetPortId.slice(6));
    }
  }
  return mapped;
}

type Props = {
  workspace: WorkspaceInfo | null;
  onOpenIntegration: (integrationId: string, phase?: ScenarioPhase | "scenarios") => void;
  onAddIntegration: (systemId: string) => void;
  onOpenCatalog: () => void;
  search?: string;
  registerNavigationGuard?: (guard: NavigationGuard) => void;
  visible?: boolean;
  refreshToken?: number;
  highlightObjectIds?: string[];
  onAssistantScopeChange?: (scope: {
    discipline: string;
    workbenchView: string;
    stateId: string | null;
    selectionIds: string[];
  }) => void;
};

type RelationshipEdge = ArchitectureRelationshipFlowEdge;

const nodeTypes = { occurrence: ArchitectureOccurrenceNodeCard, boundary: ArchitectureBoundaryNode };
const edgeTypes = { architectureRelationship: ArchitectureRelationshipEdge };

const DEFAULT_NODE_WIDTH = 220;
const DEFAULT_NODE_HEIGHT = 90;

// crypto.randomUUID is only available in secure contexts (HTTPS or localhost).
function newId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function activeStateStorageKey(workspaceId: string) {
  return `dd_active_state_id:${workspaceId}`;
}

function activeDisciplineStorageKey(workspaceId: string) {
  return `dd_active_discipline:${workspaceId}`;
}

function readStoredStateId(workspaceId: string): string {
  try {
    return sessionStorage.getItem(activeStateStorageKey(workspaceId)) ?? "";
  } catch {
    return "";
  }
}

function readStoredDiscipline(
  workspaceId: string,
  enabled: ArchitectureDiscipline[],
): ArchitectureDiscipline {
  try {
    const stored = sessionStorage.getItem(activeDisciplineStorageKey(workspaceId));
    const matching = enabled.find((discipline) => discipline === stored);
    if (matching) return matching;
  } catch {
    return enabled[0] ?? "integration";
  }
  return enabled[0] ?? "integration";
}

function uniqueCandidateName(states: ArchitectureState[]): string {
  const names = new Set(states.map((state) => state.name));
  if (!names.has("Candidate Design")) return "Candidate Design";
  let index = 2;
  while (names.has(`Candidate Design ${index}`)) index += 1;
  return `Candidate Design ${index}`;
}

export default function ArchitectureCanvas(props: Props) {
  return (
    <WorkbenchNavigationProvider>
      <ReactFlowProvider>
        <ArchitectureCanvasInner {...props} />
      </ReactFlowProvider>
    </WorkbenchNavigationProvider>
  );
}

function ArchitectureCanvasInner({ workspace, onOpenIntegration, onAddIntegration, onOpenCatalog, search = "", registerNavigationGuard, visible = true, refreshToken, highlightObjectIds, onAssistantScopeChange }: Props) {
  const flow = useReactFlow<ArchitectureOccurrenceNode, RelationshipEdge>();
  const { requestFocus } = useWorkbenchNavigation();
  const canvasElement = React.useRef<HTMLDivElement>(null);
  const [inspectorCollapsed, setInspectorCollapsed] = React.useState(false);
  const [panMode, setPanMode] = React.useState(false);
  const [linkContractOpen, setLinkContractOpen] = React.useState(false);
  const [linkContractId, setLinkContractId] = React.useState("");
  const [integrationOverview, setIntegrationOverview] = React.useState(false);
  const workspaceId = workspace?.id ?? "";
  const [activeDiscipline, setActiveDiscipline] = React.useState<ArchitectureDiscipline>(
    () => workspace ? readStoredDiscipline(workspace.id, workspace.disciplines) : "integration",
  );
  const [duplicating, setDuplicating] = React.useState(false);
  const [relationshipType, setRelationshipType] = React.useState<SemanticRelationshipType>("Uses");
  const [selectedEdgeId, setSelectedEdgeId] = React.useState<string | null>(null);
  const [nodes, setNodes] = React.useState<ArchitectureOccurrenceNode[]>([]);
  const [addOpen, setAddOpen] = React.useState(false);
  const [objectKindToAdd, setObjectKindToAdd] = React.useState<ArchitectureObjectKind | null>(null);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = React.useState<string | null>(null);
  const [health, setHealth] = React.useState<Record<string, IntegrationHealth>>({});

  const viewportByState = React.useRef(new Map<string, { x: number; y: number; zoom: number }>());
  const {
    systems,
    setSystems,
    architectureObjects,
    setArchitectureObjects,
    integrations,
    setIntegrations,
    states,
    statesRef,
    setStates,
    activeStateId,
    setActiveStateId,
    loading,
    error,
    setError,
    saveStatus,
    setSaveStatus,
    saveQueue,
    dirtyStates,
    activeState,
    currentState,
    editable,
    systemsById,
    architectureObjectsById,
    integrationsById,
    load,
    waitForSaves,
    commit,
    adoptState,
    mutateActive,
  } = useArchitectureModel({ workspaceId, registerNavigationGuard });

  // Reset canvas-only selection when the workspace changes; the shared model
  // hook resets its own data as part of loading.
  React.useEffect(() => {
    setSelectedEdgeId(null);
    setSelectedOccurrenceId(null);
    setHealth({});
    setAddOpen(false);
    setObjectKindToAdd(null);
  }, [workspaceId]);

  const wasVisible = React.useRef(visible);
  React.useEffect(() => {
    if (visible && !wasVisible.current) {
      void load();
      const viewport = viewportByState.current.get(activeStateId);
      if (viewport) void flow.setViewport(viewport);
    } else if (!visible && wasVisible.current && activeStateId) {
      viewportByState.current.set(activeStateId, flow.getViewport());
    }
    wasVisible.current = visible;
  }, [visible, activeStateId, load, flow]);

  // Reload architecture data when the workspace asks for a refresh (after an
  // assistant apply/undo) without remounting or losing the viewport.
  const lastRefreshToken = React.useRef(refreshToken);
  React.useEffect(() => {
    if (refreshToken === undefined || refreshToken === lastRefreshToken.current) return;
    lastRefreshToken.current = refreshToken;
    void load();
  }, [refreshToken, load]);

  React.useEffect(() => {
    if (!workspaceId || !workspace?.disciplines.length) return;
    const nextDiscipline = readStoredDiscipline(workspaceId, workspace.disciplines);
    setActiveDiscipline(nextDiscipline);
  }, [workspaceId, workspace?.disciplines]);

  React.useEffect(() => {
    if (!workspaceId || !workspace?.disciplines.includes(activeDiscipline)) return;
    try {
      sessionStorage.setItem(activeDisciplineStorageKey(workspaceId), activeDiscipline);
    } catch {
      /* storage unavailable */
    }
  }, [workspaceId, workspace?.disciplines, activeDiscipline]);

  const handleRemoveOccurrence = React.useCallback((occurrenceId: string) => {
    setSelectedEdgeId(null);
    setSelectedOccurrenceId(null);
    mutateActive((state) => removeOccurrence(state, occurrenceId));
  }, [mutateActive]);

  const projectedStateNodes = React.useMemo(
    () => projectStateNodes(activeState, activeDiscipline, architectureObjectsById),
    [activeDiscipline, activeState, architectureObjectsById],
  );
  const visibleStateNodes = projectedStateNodes;
  const boundaryGeometry = React.useMemo(() => activeState
    ? solutionBoundaryGeometry({ ...activeState, nodes: visibleStateNodes }, architectureObjectsById)
    : new Map<string, BoundaryGeometry>(), [activeState, visibleStateNodes, architectureObjectsById]);

  React.useEffect(() => {
    if (!activeState) {
      setNodes([]);
      return;
    }
    const applyOverrides = activeState.state_type !== "current";
    const highlight =
      highlightObjectIds && highlightObjectIds.length > 0 ? new Set(highlightObjectIds) : null;
    setNodes(() =>
      visibleStateNodes.map((occurrence) => {
        const resolved = resolveOccurrence(
          occurrence,
          systemsById,
          applyOverrides,
          architectureObjectsById,
        );
        return {
          id: occurrence.occurrence_id,
          type: boundaryGeometry.has(occurrence.occurrence_id) ? "boundary" : "occurrence",
          position: boundaryGeometry.get(occurrence.occurrence_id)?.position ?? occurrence.position,
          className:
            highlight && highlight.has(String(resolved.objectId))
              ? "architecture-node-highlighted"
              : undefined,
          ...(boundaryGeometry.has(occurrence.occurrence_id) ? {
            style: {
              width: boundaryGeometry.get(occurrence.occurrence_id)?.width,
              height: boundaryGeometry.get(occurrence.occurrence_id)?.height,
            },
            zIndex: -1,
            dragHandle: ".architecture-boundary-label",
          } : {}),
          selected: occurrence.occurrence_id === selectedOccurrenceId,
          data: {
            occurrenceId: resolved.occurrenceId,
            objectId: resolved.objectId,
            label: resolved.name,
            kind: resolved.kind,
            icon: resolved.icon,
            color: resolved.color,
            missing: resolved.missing,
            overridden: resolved.overridden,
            editable,
            stateType: activeState.state_type,
            description: resolved.description,
            onRemove: editable ? handleRemoveOccurrence : undefined,
          },
        };
      }),
    );
  }, [
    activeState,
    activeDiscipline,
    architectureObjectsById,
    editable,
    handleRemoveOccurrence,
    highlightObjectIds,
    selectedOccurrenceId,
    systemsById,
    visibleStateNodes,
    boundaryGeometry,
  ]);

  const relationships = React.useMemo(
    () => (activeState ? resolveRelationships(activeState, visibleStateNodes) : []),
    [activeState, visibleStateNodes],
  );

  const healthRef = React.useRef(health);
  healthRef.current = health;
  React.useEffect(() => {
    const pending = relationships
      .map((relationship) => relationship.integrationId && integrationsById.get(relationship.integrationId))
      .filter((integration): integration is Integration =>
        Boolean(integration) && healthRef.current[(integration as Integration).id]?.revision !== (integration as Integration).revision);
    const unique = [...new Map(pending.map((integration) => [integration.id, integration])).values()];
    if (unique.length === 0) return;
    let cancelled = false;
    void Promise.all(unique.map(async (integration): Promise<[string, IntegrationHealth]> => {
      const mappedIds = mappedTargetFieldIds(integration.graph);
      let total = 0;
      let mapped = 0;
      let coverageError: string | undefined;
      try {
        const fields = await api<{ id: string }[]>(`/api/catalog/objects/${integration.target_object_id}/fields`);
        total = fields.length;
        mapped = fields.filter((field) => mappedIds.has(field.id)).length;
      } catch (caught) {
        coverageError = caught instanceof Error ? caught.message : "Could not load target fields.";
      }
      let test: TestStatus = "untested";
      if (integration.sample_rows.length > 0) {
        try {
          const result = await api<{
            summary: { failed?: number };
            responseSummary?: { failed?: number };
          }>(`/api/integrations/${integration.id}/dry-run`, {
            method: "POST",
            body: JSON.stringify({ expected_revision: integration.revision }),
          });
          test = (result.summary.failed ?? 0) + (result.responseSummary?.failed ?? 0) > 0 ? "failing" : "passing";
        } catch {
          test = "error";
        }
      }
      return [integration.id, { revision: integration.revision, mapped, total, test, coverageError }];
    })).then((entries) => {
      if (!cancelled) setHealth((previous) => ({ ...previous, ...Object.fromEntries(entries) }));
    });
    return () => {
      cancelled = true;
    };
  }, [integrationsById, relationships]);

  const nodeRects = React.useMemo(() => {
    const map = new Map<string, Rect>();
    for (const node of nodes) {
      const styleWidth = typeof node.style?.width === "number" ? node.style.width : undefined;
      const styleHeight = typeof node.style?.height === "number" ? node.style.height : undefined;
      map.set(node.id, {
        x: node.position.x,
        y: node.position.y,
        width: node.measured?.width ?? node.width ?? styleWidth ?? DEFAULT_NODE_WIDTH,
        height: node.measured?.height ?? node.height ?? styleHeight ?? DEFAULT_NODE_HEIGHT,
      });
    }
    return map;
  }, [nodes]);

  const edges = React.useMemo<RelationshipEdge[]>(() => {
    const visible = relationships.filter((relationship) =>
      !(boundaryGeometry.has(relationship.sourceOccurrenceId) && relationship.type.toLowerCase() === "contains"),
    );
    // Group edges that share a node pair so parallel relationships route on
    // distinct lanes while each keeps its own id, direction and semantics.
    const grouped = new Map<string, ResolvedRelationship[]>();
    for (const relationship of visible) {
      const key = [relationship.sourceOccurrenceId, relationship.targetOccurrenceId].sort().join("|");
      const list = grouped.get(key) ?? [];
      list.push(relationship);
      grouped.set(key, list);
    }
    const laneByRelationship = new Map<string, { laneIndex: number; laneCount: number }>();
    for (const list of grouped.values()) {
      list.forEach((relationship, index) =>
        laneByRelationship.set(relationship.id, { laneIndex: index, laneCount: list.length }));
    }

    return visible.map((relationship) => {
      const selected = relationship.id === selectedEdgeId;
      const integrationHealth = relationship.integrationId ? health[relationship.integrationId] : undefined;
      const color = !relationship.integrationId
        ? "#8a97a6"
        : TEST_COLOR[integrationHealth?.test ?? "untested"];
      const integrationName = relationship.integrationId
        ? integrationsById.get(relationship.integrationId)?.name ?? relationship.name
        : relationship.name;
      const sourceRect = nodeRects.get(relationship.sourceOccurrenceId);
      const targetRect = nodeRects.get(relationship.targetOccurrenceId);
      const handles = sourceRect && targetRect
        ? chooseHandles(sourceRect, targetRect)
        : { source: "right" as const, target: "left" as const };
      const obstacles = [...nodeRects.entries()]
        .filter(([nodeId]) =>
          nodeId !== relationship.sourceOccurrenceId && nodeId !== relationship.targetOccurrenceId)
        .map(([, rect]) => rect);
      const lane = laneByRelationship.get(relationship.id) ?? { laneIndex: 0, laneCount: 1 };
      return {
        id: relationship.id,
        source: relationship.sourceOccurrenceId,
        target: relationship.targetOccurrenceId,
        sourceHandle: handleId("source", handles.source),
        targetHandle: handleId("target", handles.target),
        type: "architectureRelationship" as const,
        label: integrationName ? `${relationship.type.toLowerCase()} · ${integrationName}` : relationship.type.toLowerCase(),
        selected,
        data: {
          relationship,
          obstacles,
          laneIndex: lane.laneIndex,
          laneCount: lane.laneCount,
          sourceId: relationship.sourceOccurrenceId,
          targetId: relationship.targetOccurrenceId,
        },
        className: relationship.integrationId ? "architecture-edge integration" : "architecture-edge",
        style: {
          stroke: color,
          strokeWidth: selected ? 2 : 1.2,
          ...(relationship.integrationId ? {} : { strokeDasharray: "6 5" }),
        },
        markerEnd: { type: MarkerType.ArrowClosed, color },
      };
    });
  }, [health, integrationsById, relationships, selectedEdgeId, boundaryGeometry, nodeRects]);

  const selectedRelationship = relationships.find((rel) => rel.id === selectedEdgeId) ?? null;
  const selectedOccurrence = visibleStateNodes.find(
    (node) => node.occurrence_id === selectedOccurrenceId,
  ) ?? null;
  const selectedObject = selectedOccurrence
    ? architectureObjectsById.get(selectedOccurrence.object_id) ?? null
    : null;
  const selectedSystem = selectedOccurrence
    ? systemsById.get(selectedOccurrence.object_id) ?? null
    : null;

  // Publish the active discipline, workbench subview, state, and selection to the
  // workspace-level Assistant context. The canvas is the only source of truth:
  // the model never supplies or overrides this context.
  React.useEffect(() => {
    if (!onAssistantScopeChange) return;
    onAssistantScopeChange({
      discipline: activeDiscipline,
      workbenchView:
        activeDiscipline === "integration" && integrationOverview ? "canvas" : activeDiscipline,
      stateId: activeStateId || null,
      selectionIds: selectedOccurrence ? [selectedOccurrence.object_id] : [],
    });
  }, [
    onAssistantScopeChange,
    activeDiscipline,
    integrationOverview,
    activeStateId,
    selectedOccurrence,
  ]);

  function openRelationshipIntegration(relationship: ResolvedRelationship | null) {
    if (relationship?.integrationId) onOpenIntegration(relationship.integrationId);
  }

  function handleConnect(connection: Connection) {
    if (!editable || !connection.source || !connection.target) return;
    if (connection.source === connection.target) return;
    const id = `rel-${newId()}`;
    setSelectedEdgeId(id);
    mutateActive((state) => addRelationship(state, {
      id,
      source_id: connection.source,
      target_id: connection.target,
      type: relationshipType,
      name: null,
      integration_id: null,
      candidate_overrides: {},
      display_metadata: {},
    }));
  }

  async function handleDuplicateCurrent() {
    if (!workspaceId || !currentState) return;
    saveQueue.current.retry("duplicate-state");
    if (!await waitForSaves()) return;
    setDuplicating(true);
    setError("");
    try {
      const duplicate = await saveQueue.current.enqueue("duplicate-state", () => api<ArchitectureState>(
        `/api/workspaces/${workspaceId}/states/${currentState.id}/duplicate`,
        {
          method: "POST",
          body: JSON.stringify({
            target_name: uniqueCandidateName(statesRef.current),
            target_state_type: "candidate",
          }),
        },
      ));
      setStates((previous) => [...previous, duplicate]);
      setActiveStateId(duplicate.id);
      setSelectedEdgeId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not duplicate the current state.");
    } finally {
      setDuplicating(false);
    }
  }

  async function handleDeleteState() {
    if (!workspaceId || !activeState || !editable) return;
    if (!window.confirm(`Delete "${activeState.name}"? Canonical systems and the current state are not affected.`)) {
      return;
    }
    setError("");
    try {
      saveQueue.current.retry("delete-state");
      await saveQueue.current.flush();
      await saveQueue.current.enqueue("delete-state", () => api<void>(`/api/workspaces/${workspaceId}/states/${activeState.id}`, { method: "DELETE" }));
      setStates((previous) => previous.filter((state) => state.id !== activeState.id));
      setActiveStateId(currentState?.id ?? "");
      setSelectedEdgeId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete the state.");
    }
  }

  async function handleAddSystem(selection: { objectId: string } | { name: string; kind: string }) {
    if (!activeState) return;
    saveQueue.current.retry("add-system");
    await saveQueue.current.flush();
    await saveOperation("add-system", async () => {
      let objectId: string;
      if ("objectId" in selection) {
        objectId = selection.objectId;
      } else {
        const created = await api<CanonicalSystem>("/api/catalog/systems", {
          method: "POST",
          body: JSON.stringify({ name: selection.name, kind: selection.kind || "application" }),
        });
        setSystems((previous) => [...previous, created]);
        objectId = created.id;
      }
      mutateActive((state) =>
        addOccurrence(state, objectId, nextFreePosition(state), `occ-${newId()}`));
    });
    await saveQueue.current.flush();
    setAddOpen(false);
  }

  async function saveOperation<T>(key: string, operation: () => Promise<T>): Promise<T> {
    setSaveStatus("saving");
    try {
      return await saveQueue.current.enqueue(key, operation);
    } catch (caught) {
      setSaveStatus("error");
      setError(caught instanceof Error ? caught.message : "Could not save the change.");
      throw caught;
    }
  }

  async function handleCreateArchitectureObject(draft: ArchitectureObjectDraft) {
    if (!workspaceId || !activeState || !editable) return;
    saveQueue.current.retry("create-object");
    await saveQueue.current.flush();
    setSaveStatus("saving");
    const created = await saveOperation("create-object", () => api<{
      object: ArchitectureObject;
      state: ArchitectureState;
    }>(`/api/workspaces/${workspaceId}/architecture-objects`, {
      method: "POST",
      body: JSON.stringify({
        ...draft,
        related_system_id: draft.relatedSystemId,
        authoritative_system_id: draft.authoritativeSystemId,
        state_id: activeState.id,
        position: nextFreePosition(statesRef.current.find((state) => state.id === activeState.id) ?? activeState),
      }),
    }));
    setArchitectureObjects((previous) => [...previous, created.object]);
    statesRef.current = statesRef.current.map((state) =>
      state.id === created.state.id ? created.state : state);
    setStates((previous) => previous.map((state) =>
      state.id === created.state.id ? created.state : state));
    setSelectedOccurrenceId(
      created.state.nodes.find((node) => node.object_id === created.object.id)?.occurrence_id ?? null,
    );
    setSelectedEdgeId(null);
    setObjectKindToAdd(null);
    await saveQueue.current.flush();
    setSaveStatus("saved");
    setError("");
  }

  async function handleUpdateArchitectureObject(
    objectId: string,
    patch: { name: string; description: string; owner?: string },
  ) {
    setSaveStatus("saving");
    const saved = await saveOperation(objectId, () => api<ArchitectureObject>(
      `/api/workspaces/${workspaceId}/architecture-objects/${objectId}`,
      {
        method: "PATCH",
        body: JSON.stringify(patch),
      },
    ));
    setArchitectureObjects((previous) => previous.map((object) =>
      object.id === saved.id ? saved : object));
    await saveQueue.current.flush();
    setSaveStatus("saved");
  }

  async function selectState(stateId: string) {
    if (!await waitForSaves()) return;
    if (activeStateId) viewportByState.current.set(activeStateId, flow.getViewport());
    setActiveStateId(stateId);
    setSelectedEdgeId(null);
    setSelectedOccurrenceId(null);
    const viewport = viewportByState.current.get(stateId);
    if (viewport) void flow.setViewport(viewport);
  }

  const searchMatches = visibleStateNodes.filter((node) => {
    const resolved = resolveOccurrence(node, systemsById, editable, architectureObjectsById);
    return search.trim() && `${resolved.name} ${resolved.kind} ${resolved.objectId}`.toLowerCase().includes(search.trim().toLowerCase());
  });

  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await canvasElement.current?.requestFullscreen();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Fullscreen is unavailable.");
    }
  }

  if (!workspace) {
    return <div className="landscape-empty" role="status">Loading workspace…</div>;
  }

  const informationMode = activeDiscipline === "information";
  const solutionMode = activeDiscipline === "solution";
  const enterpriseMode = activeDiscipline === "enterprise";
  const integrationMode = activeDiscipline === "integration";
  const workbenchMode =
    informationMode || solutionMode || enterpriseMode || (integrationMode && !integrationOverview);
  const onCanvasObjectIds = new Set(activeState?.nodes.map((node) => node.object_id) ?? []);
  // The only remaining generic-canvas palette entry is the Solution interface on
  // the integration overview; the four discipline workbenches own their own editors.
  const paletteKinds: ArchitectureObjectKind[] = workspace.disciplines.includes("solution")
    ? ["interface"]
    : [];
  const paletteLabels: Partial<Record<ArchitectureObjectKind, string>> = { interface: "Interface" };

  function handleNavigateTrace(node: TraceObjectRef) {
    // Ask the destination workbench to select and reveal the object; the
    // discipline switch below mounts that workbench, which then consumes the
    // focus request once its model has loaded.
    requestFocus(node);
    const discipline = node.discipline as ArchitectureDiscipline | null;
    if (discipline && workspace?.disciplines.includes(discipline) && discipline !== activeDiscipline) {
      setActiveDiscipline(discipline);
      setSelectedEdgeId(null);
      setSelectedOccurrenceId(null);
    }
    const occurrence = activeState?.nodes.find((item) => item.object_id === node.id);
    if (occurrence) {
      setSelectedOccurrenceId(occurrence.occurrence_id);
      setInspectorCollapsed(false);
    }
  }

  return (
    <section className="architecture-canvas-workspace">
      <ArchitectureTopBar
        states={states}
        activeStateId={activeStateId}
        onSelectState={(stateId) => void selectState(stateId)}
        disciplines={<ArchitectureDisciplineTabs
          disciplines={workspace.disciplines}
          activeDiscipline={activeDiscipline}
          onSelect={(discipline) => {
            void waitForSaves().then((allowed) => {
              if (!allowed) return;
              setActiveDiscipline(discipline);
              setSelectedEdgeId(null);
              setSelectedOccurrenceId(null);
            });
          }}
        />}
        addMenu={workbenchMode ? null : <StudioMenu label="+ Add Object" disabled={!editable || loading} className="studio-add-menu">
          <p className="studio-menu-caption">{activeDiscipline} objects</p>
          {paletteKinds.map((kind) => <button key={kind} type="button" onClick={() => setObjectKindToAdd(kind)}>{paletteLabels[kind]}</button>)}
          <button type="button" onClick={() => setAddOpen(true)}>Existing system</button>
          {activeDiscipline === "integration" && <>
            <button type="button" onClick={() => {
              setPanMode(false);
              setError("");
              setRelationshipType("Uses");
            }}>Integration relationship <small>Drag between object handles</small></button>
            <button type="button" onClick={() => {
              setLinkContractId(integrations[0]?.id ?? "");
              setLinkContractOpen(true);
            }}>Existing contract</button>
          </>}
        </StudioMenu>}
        options={<StudioMenu label="View options">
          {integrationMode && (
            <button type="button" onClick={() => setIntegrationOverview((value) => !value)}>
              {integrationOverview ? "Integration designer" : "Architecture canvas"}
            </button>
          )}
          <button type="button" disabled={!currentState || duplicating} onClick={() => void handleDuplicateCurrent()}>{duplicating ? "Creating…" : "New candidate from Current"}</button>
          {editable && <button type="button" className="architecture-danger" onClick={() => void handleDeleteState()}>Delete {activeState?.state_type}</button>}
        </StudioMenu>}
        saveStatus={saveStatus}
      />
      {error && <div className="studio-canvas-error" role="alert">
        <span>{error}</span>
        {dirtyStates.current.size > 0 && <button type="button" onClick={() => {
          for (const id of dirtyStates.current) {
            const state = statesRef.current.find((item) => item.id === id);
            if (state) commit(state);
          }
        }}>Retry save</button>}
        {saveStatus !== "error" && <button type="button" onClick={() => setError("")} aria-label="Dismiss error">×</button>}
      </div>}
      {integrationMode && !integrationOverview ? (
        <IntegrationWorkbench
          workspaceId={workspaceId}
          activeState={activeState}
          editable={editable}
          saveStatus={saveStatus}
          search={search}
          onOpenIntegration={onOpenIntegration}
          onOpenCatalog={onOpenCatalog}
          onNavigateTrace={handleNavigateTrace}
        />
      ) : enterpriseMode ? (
        <EnterpriseWorkbench
          workspaceId={workspaceId}
          activeState={activeState}
          editable={editable}
          saveStatus={saveStatus}
          search={search}
          mutateActive={mutateActive}
          onReloadStates={() => void load()}
          onOpenCatalog={onOpenCatalog}
          onNavigateTrace={handleNavigateTrace}
        />
      ) : informationMode ? (
        <InformationWorkbench
          workspaceId={workspaceId}
          activeState={activeState}
          editable={editable}
          saveStatus={saveStatus}
          search={search}
          onAdoptState={adoptState}
          mutateActive={mutateActive}
          onOpenCatalog={onOpenCatalog}
          onNavigateTrace={handleNavigateTrace}
        />
      ) : solutionMode ? (
        <SolutionWorkbench
          workspaceId={workspaceId}
          activeState={activeState}
          editable={editable}
          saveStatus={saveStatus}
          search={search}
          onAdoptState={adoptState}
          mutateActive={mutateActive}
          onReloadStates={() => void load()}
          onOpenCatalog={onOpenCatalog}
          onNavigateTrace={handleNavigateTrace}
        />
      ) : loading && states.length === 0 ? (
        <div className="landscape-empty" role="status">Loading architecture states…</div>
      ) : activeState && activeState.nodes.length === 0 && !editable ? (
        <div className="landscape-empty">
          <span className="empty-icon">◇</span>
          <h3>No systems in this state yet</h3>
          <p>Create systems in the catalog, or duplicate this state into a candidate and add systems there.</p>
          <button type="button" onClick={onOpenCatalog}>Open catalog</button>
        </div>
      ) : (
        <div ref={canvasElement} className={`architecture-canvas-layout${!inspectorCollapsed && (selectedRelationship || selectedOccurrence) ? " has-panel" : ""}`}>
          <div className="architecture-canvas" aria-label="Architecture canvas">
            <ReactFlow<ArchitectureOccurrenceNode, RelationshipEdge>
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={(changes: NodeChange<ArchitectureOccurrenceNode>[]) => {
                setNodes((current) => applyNodeChanges(changes, current));
              }}
              onNodeDragStop={(_event, _node, dragged) => {
                if (!editable) return;
                mutateActive((state) => {
                  let next = state;
                  const moved = new Set<string>();
                  for (const node of dragged) {
                    const boundary = boundaryGeometry.get(node.id);
                    if (boundary) {
                      const dx = node.position.x - boundary.position.x;
                      const dy = node.position.y - boundary.position.y;
                      for (const id of [node.id, ...boundary.memberIds]) {
                        const original = state.nodes.find((item) => item.occurrence_id === id);
                        if (original && !moved.has(id)) {
                          next = moveOccurrence(next, id, { x: original.position.x + dx, y: original.position.y + dy });
                          moved.add(id);
                        }
                      }
                    } else if (!moved.has(node.id)) {
                      next = moveOccurrence(next, node.id, node.position);
                      moved.add(node.id);
                    }
                  }
                  return next;
                });
              }}
              onNodeClick={(_event, node) => {
                setSelectedOccurrenceId(node.id);
                setSelectedEdgeId(null);
                setInspectorCollapsed(false);
              }}
              onConnect={handleConnect}
              onEdgeClick={(_event, edge) => {
                setSelectedEdgeId(edge.id);
                setSelectedOccurrenceId(null);
                setInspectorCollapsed(false);
              }}
              onEdgeDoubleClick={(_event, edge) => openRelationshipIntegration(edge.data?.relationship ?? null)}
              onPaneClick={() => {
                setSelectedEdgeId(null);
                setSelectedOccurrenceId(null);
              }}
              nodesConnectable={editable && !panMode}
              nodesDraggable={editable && !panMode}
              panOnDrag={panMode ? true : [1, 2]}
              selectionOnDrag={!panMode}
              onMoveEnd={(_event, viewport) => { if (activeStateId) viewportByState.current.set(activeStateId, viewport); }}
              edgesFocusable
              deleteKeyCode={null}
              fitView
              fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
              minZoom={0.2}
              maxZoom={1.8}
            >
              <Background color="var(--color-grid)" gap={20} size={1} />
              <Panel position="top-left" className="studio-floating-tools">
                <button type="button" aria-label="Select objects" aria-pressed={!panMode} onClick={() => setPanMode(false)}>↖</button>
                <button type="button" aria-label="Pan canvas" aria-pressed={panMode} onClick={() => setPanMode(true)}>✥</button>
                {editable && <select aria-label="Relationship type for new connections" title="Drag from an object's handle to another object's handle" value={relationshipType} onChange={(event) => setRelationshipType(event.target.value as SemanticRelationshipType)}>
                  {SEMANTIC_RELATIONSHIP_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>}
              </Panel>
              <Controls showInteractive={false} position="bottom-right" fitViewOptions={{ padding: 0.2, maxZoom: 1 }}>
                <button type="button" className="react-flow__controls-button" aria-label="Fullscreen canvas" onClick={() => void fullscreen()}>⛶</button>
              </Controls>
              <Panel position="bottom-left" className="studio-canvas-meta">
                <span>{visibleStateNodes.length} objects · {relationships.length} relationships</span>
                <span>{activeDiscipline} · {activeState?.state_type}</span>
              </Panel>
              {search.trim() && <Panel position="top-left" className="studio-search-results">
                <strong>{searchMatches.length} matches</strong>
                {searchMatches.map((node) => <button key={node.occurrence_id} type="button" onClick={() => {
                  setSelectedOccurrenceId(node.occurrence_id);
                  setSelectedEdgeId(null);
                  setInspectorCollapsed(false);
                  void flow.fitView({ nodes: [{ id: node.occurrence_id }], maxZoom: 1.2, duration: 200 });
                }}>{resolveOccurrence(node, systemsById, editable, architectureObjectsById).name}</button>)}
              </Panel>}
            </ReactFlow>
          </div>
          {inspectorCollapsed && (selectedRelationship || selectedOccurrence) && <button type="button" className="studio-reopen-inspector" onClick={() => setInspectorCollapsed(false)}>Open inspector</button>}
          {!inspectorCollapsed && selectedRelationship && activeState && (
            <RelationshipPanel
              relationship={selectedRelationship}
              editable={editable}
              sourceLabel={nodes.find((node) => node.id === selectedRelationship.sourceOccurrenceId)?.data.label ?? "Source"}
              targetLabel={nodes.find((node) => node.id === selectedRelationship.targetOccurrenceId)?.data.label ?? "Target"}
              sourceObjectId={nodes.find((node) => node.id === selectedRelationship.sourceOccurrenceId)?.data.objectId ?? ""}
              targetObjectId={nodes.find((node) => node.id === selectedRelationship.targetOccurrenceId)?.data.objectId ?? ""}
              systems={systems}
              integrations={integrations}
              health={selectedRelationship.integrationId ? health[selectedRelationship.integrationId] ?? null : null}
              integrationName={selectedRelationship.integrationId
                ? integrationsById.get(selectedRelationship.integrationId)?.name ?? null
                : null}
              onClose={() => setSelectedEdgeId(null)}
              onCollapse={() => setInspectorCollapsed(true)}
              stateName={activeState.name}
              saveStatus={saveStatus}
              onOpenIntegration={() => openRelationshipIntegration(selectedRelationship)}
              onCreateIntegration={(systemId) => onAddIntegration(systemId)}
              onChange={(patch) => mutateActive((state) => updateRelationship(state, selectedRelationship.id, patch))}
              onRemove={() => {
                setSelectedEdgeId(null);
                mutateActive((state) => removeRelationship(state, selectedRelationship.id));
              }}
            />
          )}
          {!inspectorCollapsed && selectedOccurrence && (
            <ArchitectureObjectInspector
              object={selectedObject}
              system={selectedSystem}
              systems={systems}
              key={selectedOccurrence.occurrence_id}
              readOnly={!editable || Boolean(currentState?.nodes.some((node) => node.object_id === selectedObject?.id))}
              onClose={() => setSelectedOccurrenceId(null)}
              onCollapse={() => setInspectorCollapsed(true)}
              occurrenceId={selectedOccurrence.occurrence_id}
              stateName={activeState?.name ?? ""}
              saveStatus={saveStatus}
              relationships={relationships.filter((rel) => rel.sourceOccurrenceId === selectedOccurrenceId || rel.targetOccurrenceId === selectedOccurrenceId).map((rel) => ({
                id: rel.id,
                label: `${rel.type.toLowerCase()} · ${nodes.find((node) => node.id === (rel.sourceOccurrenceId === selectedOccurrenceId ? rel.targetOccurrenceId : rel.sourceOccurrenceId))?.data.label ?? "Object"}`,
              }))}
              onSelectRelationship={(id) => {
                setSelectedEdgeId(id);
                setSelectedOccurrenceId(null);
              }}
              onRemove={editable ? () => handleRemoveOccurrence(selectedOccurrence.occurrence_id) : undefined}
              workspaceId={workspaceId}
              stateId={activeState?.id ?? null}
              onNavigateTrace={handleNavigateTrace}
              onOpenCatalog={
                workspace.disciplines.some((discipline) =>
                  discipline === "enterprise" || discipline === "information")
                  ? onOpenCatalog
                  : undefined
              }
              onSave={handleUpdateArchitectureObject}
            />
          )}
        </div>
      )}
      {addOpen && (
        <AddSystemDialog
          systems={systems}
          onCanvasObjectIds={onCanvasObjectIds}
          onCancel={() => setAddOpen(false)}
          onAdd={handleAddSystem}
        />
      )}
      {objectKindToAdd && (
        <ArchitectureObjectDialog
          kind={objectKindToAdd}
          discipline={activeDiscipline}
          systems={systems}
          onCancel={() => setObjectKindToAdd(null)}
          onCreate={handleCreateArchitectureObject}
        />
      )}
      {linkContractOpen && <div className="architecture-dialog-backdrop">
        <form className="architecture-dialog" role="dialog" aria-modal="true" aria-label="Link existing contract" onSubmit={(event) => {
          event.preventDefault();
          const integration = integrationsById.get(linkContractId);
          if (!integration) return;
          const id = `rel-${newId()}`;
          mutateActive((state) => {
            let next = state;
            for (const objectId of [integration.source_system_id, integration.target_system_id]) {
              if (!next.nodes.some((node) => node.object_id === objectId)) {
                next = addOccurrence(next, objectId, nextFreePosition(next), `occ-${newId()}`);
              }
            }
            return addRelationship(next, {
              id, source_id: integration.source_system_id, target_id: integration.target_system_id,
              type: "Consumes", name: integration.name, integration_id: integration.id,
            });
          });
          setLinkContractOpen(false);
          setSelectedEdgeId(id);
          setSelectedOccurrenceId(null);
          setInspectorCollapsed(false);
        }}>
          <h3>Link existing contract</h3>
          <p>Place the contract's systems and link their existing mapping and tests.</p>
          <label>Contract<select value={linkContractId} onChange={(event) => setLinkContractId(event.target.value)}>
            {integrations.map((integration) => <option key={integration.id} value={integration.id}>{integration.name}</option>)}
          </select></label>
          {!integrations.length && <p>No contracts exist in this workspace.</p>}
          <div className="architecture-dialog-actions"><button type="button" className="secondary-button" onClick={() => setLinkContractOpen(false)}>Cancel</button><button type="submit" disabled={!linkContractId}>Link contract</button></div>
        </form>
      </div>}
    </section>
  );
}

type RelationshipPanelProps = {
  relationship: ResolvedRelationship;
  editable: boolean;
  sourceLabel: string;
  targetLabel: string;
  sourceObjectId: string;
  targetObjectId: string;
  systems: CanonicalSystem[];
  integrations: Integration[];
  integrationName: string | null;
  health: IntegrationHealth | null;
  onClose: () => void;
  onCollapse: () => void;
  stateName: string;
  saveStatus: SaveStatus;
  onOpenIntegration: () => void;
  onCreateIntegration: (systemId: string) => void;
  onChange: (patch: { type?: string; integration_id?: string | null; name?: string | null }) => void;
  onRemove: () => void;
};

function RelationshipPanel({
  relationship,
  editable,
  sourceLabel,
  targetLabel,
  sourceObjectId,
  targetObjectId,
  systems,
  integrations,
  integrationName,
  health,
  onClose,
  onCollapse,
  stateName,
  saveStatus,
  onOpenIntegration,
  onCreateIntegration,
  onChange,
  onRemove,
}: RelationshipPanelProps) {
  const systemIds = new Set(systems.map((system) => system.id));
  const linkable = integrations.filter((integration) =>
    (integration.source_system_id === sourceObjectId && integration.target_system_id === targetObjectId)
    || (integration.source_system_id === targetObjectId && integration.target_system_id === sourceObjectId));
  return (
    <aside className="architecture-relationship-panel" aria-label="Relationship details">
      <header>
        <div>
          <p className="eyebrow">RELATIONSHIP</p>
          <h3>{sourceLabel} → {targetLabel}</h3>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label="Collapse relationship inspector" onClick={onCollapse}>›</button>
          <button type="button" className="secondary-button" aria-label="Close relationship details" onClick={onClose}>✕</button>
        </div>
      </header>
      <p className="studio-inspector-state">{stateName} · {editable ? "Editable" : "Read-only"} <span>{saveStatus === "idle" ? "" : saveStatus}</span></p>
      <small className="studio-object-identifier">{relationship.id}</small>
      {editable ? (
        <label>
          Type
          <select value={relationship.type} onChange={(event) => onChange({ type: event.target.value })}>
            {SEMANTIC_RELATIONSHIP_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
            {!SEMANTIC_RELATIONSHIP_TYPES.includes(relationship.type as SemanticRelationshipType) && (
              <option value={relationship.type}>{relationship.type}</option>
            )}
          </select>
        </label>
      ) : (
        <p><strong>Type:</strong> {relationship.type}</p>
      )}
      {relationship.integrationId ? (
        <section className="architecture-integration-link">
          <p><strong>Integration contract:</strong> {integrationName ?? relationship.name ?? "Linked contract"}</p>
          {health ? (
            <dl className="architecture-health">
              <div><dt>Mapping coverage</dt><dd>{health.coverageError ? `Unavailable: ${health.coverageError}` : `${health.mapped} / ${health.total} target fields`}</dd></div>
              <div>
                <dt>Latest test</dt>
                <dd className={`architecture-test ${health.test}`}>{TEST_LABEL[health.test]}</dd>
              </div>
            </dl>
          ) : (
            <p className="architecture-topbar-hint">Checking mapping and tests…</p>
          )}
          <button type="button" onClick={onOpenIntegration}>Open Mapping &amp; Tests</button>
          {editable && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => onChange({ integration_id: null, name: null })}
            >
              Unlink contract
            </button>
          )}
        </section>
      ) : (
        <section className="architecture-integration-link">
          <p>No integration contract is linked to this relationship.</p>
          {editable && linkable.length > 0 && (
            <label>
              Link existing contract
              <select
                value=""
                onChange={(event) => {
                  const integration = linkable.find((item) => item.id === event.target.value);
                  if (integration) onChange({ integration_id: integration.id, name: integration.name });
                }}
              >
                <option value="">Choose a contract…</option>
                {linkable.map((integration) => (
                  <option key={integration.id} value={integration.id}>{integration.name}</option>
                ))}
              </select>
            </label>
          )}
          {sourceObjectId && systemIds.has(sourceObjectId) && (
            <button type="button" className="secondary-button" onClick={() => onCreateIntegration(sourceObjectId)}>
              Create contract from {sourceLabel}
            </button>
          )}
        </section>
      )}
      {editable && (
        <button type="button" className="secondary-button architecture-danger" onClick={onRemove}>
          Remove relationship
        </button>
      )}
    </aside>
  );
}

type AddSystemDialogProps = {
  systems: CanonicalSystem[];
  onCanvasObjectIds: Set<string>;
  onCancel: () => void;
  onAdd: (selection: { objectId: string } | { name: string; kind: string }) => Promise<void>;
};

function AddSystemDialog({ systems, onCanvasObjectIds, onCancel, onAdd }: AddSystemDialogProps) {
  const [mode, setMode] = React.useState<"existing" | "new">("existing");
  const available = [...systems].sort((a, b) =>
    Number(onCanvasObjectIds.has(a.id)) - Number(onCanvasObjectIds.has(b.id)) || a.name.localeCompare(b.name));
  const [objectId, setObjectId] = React.useState(available[0]?.id ?? "");
  const [name, setName] = React.useState("");
  const [kind, setKind] = React.useState("application");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "existing" && !objectId) {
      setError("Choose a system.");
      return;
    }
    if (mode === "new" && !name.trim()) {
      setError("Enter a system name.");
      return;
    }
    setBusy(true);
    try {
      await onAdd(mode === "existing" ? { objectId } : { name: name.trim(), kind: kind.trim() });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add the system.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="architecture-dialog-backdrop" role="presentation" onClick={onCancel}>
      <form
        className="architecture-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="architecture-add-system-title"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => void submit(event)}
      >
        <h3 id="architecture-add-system-title">Add system to this state</h3>
        <div className="landscape-detail-switch" role="group" aria-label="System source">
          <button type="button" className={mode === "existing" ? "active" : ""} aria-pressed={mode === "existing"} onClick={() => setMode("existing")}>
            Existing system
          </button>
          <button type="button" className={mode === "new" ? "active" : ""} aria-pressed={mode === "new"} onClick={() => setMode("new")}>
            New canonical system
          </button>
        </div>
        {mode === "existing" ? (
          available.length === 0 ? (
            <p>No canonical systems exist yet. Create a new one instead.</p>
          ) : (
            <label>
              System
              <select value={objectId} onChange={(event) => setObjectId(event.target.value)}>
                {available.map((system) => (
                  <option key={system.id} value={system.id}>
                    {system.name}{onCanvasObjectIds.has(system.id) ? " (already placed)" : ""}
                  </option>
                ))}
              </select>
            </label>
          )
        ) : (
          <>
            <label>
              Name
              <input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} autoFocus />
            </label>
            <label>
              Kind
              <input value={kind} maxLength={120} onChange={(event) => setKind(event.target.value)} />
            </label>
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="architecture-dialog-actions">
          <button type="button" className="secondary-button" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="submit" disabled={busy}>{busy ? "Adding…" : "Add to canvas"}</button>
        </div>
      </form>
    </div>
  );
}
