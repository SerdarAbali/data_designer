import React from "react";
import {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  Panel,
  ReactFlow,
  useReactFlow,
  applyNodeChanges,
  type Edge,
} from "@xyflow/react";
import FieldMappingDrawer from "./components/landscape/FieldMappingDrawer";
import FieldLineageExplorer from "./components/landscape/FieldLineageExplorer";
import ScenarioWorkspace from "./components/scenarios/ScenarioWorkspace";
import type { ScenarioPhase } from "./scenarioModel";
import LandscapeMappingEdge from "./components/landscape/LandscapeMappingEdge";
import {
  createFailedEnterpriseArchitectureIndex,
  loadEnterpriseArchitectureIndex,
  type EnterpriseArchitectureIndex,
} from "./enterpriseArchitectureIndex";
import {
  deriveLandscapeMappingPaths,
  type LandscapeMappingPhase,
  type LandscapeMappingPath,
} from "./landscapeMappingModel";
import SystemLandscapeNodeCard, {
  type SystemLandscapeNode,
  type SystemLandscapeNodeData,
} from "./components/landscape/SystemLandscapeNode";
import { designStatusLabel, designValidationReason } from "./designLabels";

type System = {
  id: string;
  name: string;
  kind: string;
  icon: string | null;
  color: string | null;
  position: { x: number; y: number } | null;
};

type CatalogObject = {
  id: string;
  label: string;
};

type CatalogField = {
  id: string;
  name: string;
  label: string;
  data_type: string;
  required?: boolean;
  nullable?: boolean;
};

type GraphNode = {
  id: string;
  type: string;
  config: Record<string, unknown>;
  position?: { x: number; y: number };
};

type GraphEdge = {
  id: string;
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
};

type Integration = {
  id: string;
  source_system_id: string;
  source_object_id: string;
  target_system_id: string;
  target_object_id: string;
  name: string;
  graph: { version: number; nodes: GraphNode[]; edges: GraphEdge[] };
  response_graph: { version: number; nodes: GraphNode[]; edges: GraphEdge[] };
  error_response_graph?: { version: number; nodes: GraphNode[]; edges: GraphEdge[] };
  error_response_object_id?: string | null;
  interaction_type: "ONE_WAY" | "REQUEST_RESPONSE" | "ASYNC_CALLBACK";
  sample_rows: { rowId: string; values: Record<string, unknown> }[];
  revision: number;
};

type SimulationRow = {
  outcome: string;
  targetValues: Record<string, unknown>;
  errors: { nodeId: string | null }[];
};
type SimulationResult = {
  summary: { total: number; ok: number; skipped: number; failed: number };
  responseSummary: { total: number; ok: number; skipped: number; failed: number };
  rows: SimulationRow[];
  requestOutcomes: SimulationRow[];
  responseOutcomes: SimulationRow[];
};

type ArchitectureIntegration = {
  id: string;
  name: string;
  status: "draft" | "attention" | "healthy";
  reasons: string[];
  conflict_fields: { object_id: string; object_label: string; field_id: string; field_label: string }[];
  upstream: { id: string; name: string; status: "draft" | "attention" | "healthy" }[];
};

type ArchitectureConflict = {
  object_id: string;
  object_label: string;
  field_id: string;
  field_label: string;
  integrations: { id: string; name: string; status: "attention" }[];
};

type ArchitectureAnalysis = {
  integrations: ArchitectureIntegration[];
  conflicts: ArchitectureConflict[];
};

type LandscapeNode = SystemLandscapeNode;
type LandscapeEdge = Edge<{
  integrationId: string;
  contractIds: string[];
  bundleKey?: string;
  laneIndex?: number;
  laneCount?: number;
  obstacles?: { systemId: string; x: number; y: number; width: number; height: number }[];
  sourceSystemId?: string;
  targetSystemId?: string;
  dimmed?: boolean;
  sampleRows: number;
  status: "draft" | "attention" | "healthy" | "valid" | "warnings" | "errors" | "incomplete";
  sourceFieldId?: string;
  targetFieldId?: string;
  transformations?: string[];
  phase?: LandscapeMappingPhase | "contract";
}>;
type LandscapeMode = "systems" | "contracts" | "hybrid" | "lineage" | "scenarios";
type HybridPhaseFilter = LandscapeMappingPhase | "all";
type LandscapeValidationFilter = "all" | "errors" | "warnings" | "valid" | "incomplete";
type LandscapeFocus = "neighbors" | "upstream" | "downstream" | "all";
type Props = {
  onOpenIntegration: (integrationId: string, phase?: ScenarioPhase) => void;
  onOpenCatalog: () => void;
  onAddIntegration: (systemId: string) => void;
};

type ResolvedLandscapePath = LandscapeMappingPath & {
  senderSystemId: string;
  senderObjectId: string;
  receiverSystemId: string;
  receiverObjectId: string;
};

class ApiError extends Error {}

function csrfToken(): string {
  const raw = document.cookie.split("; ").find((item) => item.startsWith("dd_csrf="))?.slice(8);
  if (!raw) throw new Error("Your session could not be verified. Reload and try again.");
  return decodeURIComponent(raw);
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string | { message?: string };
    };
    const detail = body.detail;
    throw new ApiError(
      typeof detail === "string" ? detail : detail?.message ?? `Request failed (${response.status}).`,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function list<T>(path: string): Promise<T[]> {
  const records: T[] = [];
  let offset = 0;
  while (true) {
    const page = await api<T[]>(`${path}?limit=500&offset=${offset}`);
    records.push(...page);
    if (page.length < 500) return records;
    offset += page.length;
  }
}

function integrationPhasePaths(
  integration: Integration,
  phase: LandscapeMappingPhase,
): ResolvedLandscapePath[] {
  if (phase === "error-response" && !integration.error_response_object_id) return [];
  const graph = phase === "request"
    ? integration.graph
    : phase === "success-response"
      ? integration.response_graph
      : integration.error_response_graph ?? { version: 1, nodes: [], edges: [] };
  const response = phase !== "request";
  const senderSystemId = response ? integration.target_system_id : integration.source_system_id;
  const senderObjectId = phase === "error-response"
    ? integration.error_response_object_id!
    : response ? integration.target_object_id : integration.source_object_id;
  const receiverSystemId = response ? integration.source_system_id : integration.target_system_id;
  const receiverObjectId = response ? integration.source_object_id : integration.target_object_id;
  return deriveLandscapeMappingPaths(graph, phase).map((path) => ({
    ...path,
    senderSystemId,
    senderObjectId,
    receiverSystemId,
    receiverObjectId,
  }));
}

const HYBRID_PHASES: readonly LandscapeMappingPhase[] = [
  "request",
  "success-response",
  "error-response",
];

function phaseLabel(phase: LandscapeMappingPhase): string {
  if (phase === "success-response") return "Success Response";
  if (phase === "error-response") return "Error Response";
  return "Request";
}

function phaseDisplayName(phase: string): string {
  if (phase === "request") return "Request";
  if (phase === "success-response") return "Success Response";
  if (phase === "async-response") return "Async Response";
  return "Error Response";
}

function phaseColor(phase: LandscapeMappingPhase): string {
  if (phase === "success-response") return "#38895c";
  if (phase === "error-response") return "#bd4e45";
  return "#3478b8";
}

function interactionLabel(type: Integration["interaction_type"]): string {
  if (type === "ONE_WAY") return "One-way";
  if (type === "ASYNC_CALLBACK") return "Async callback";
  return "Request/Response";
}

type LandscapeValidation = "valid" | "warnings" | "errors" | "incomplete";

type ValidationFacts = {
  errors: boolean;
  warnings: boolean;
  incomplete: boolean;
};

function validationFactsForContract(
  index: EnterpriseArchitectureIndex | null,
  contractId: string,
): ValidationFacts {
  const phases = index?.phasesByContractId.get(contractId);
  if (!phases) return { errors: false, warnings: false, incomplete: true };
  return {
    errors: phases.some((phase) => phase.validationSummary.errorCount > 0),
    warnings: phases.some((phase) => phase.validationSummary.warningCount > 0),
    incomplete: phases.some((phase) => !phase.configured
      || phase.validationSummary.status === "Incomplete"
      || phase.validationSummary.incompleteMappingCount > 0),
  };
}

function validationForContract(
  index: EnterpriseArchitectureIndex | null,
  contractId: string,
): LandscapeValidation {
  const facts = validationFactsForContract(index, contractId);
  if (facts.errors) return "errors";
  if (facts.warnings) return "warnings";
  if (facts.incomplete) return "incomplete";
  return "valid";
}

function validationLabel(status: LandscapeValidation): string {
  if (status === "errors") return "Errors";
  if (status === "warnings") return "Warnings";
  if (status === "incomplete") return "Incomplete";
  return "Valid";
}

function validationColor(status: LandscapeValidation): string {
  if (status === "errors") return "#bd4e45";
  if (status === "warnings" || status === "incomplete") return "#b47a27";
  return "#617b70";
}

function focusedRelationships(
  integrations: readonly Integration[],
  systemId: string,
  focus: LandscapeFocus | "upstream" | "downstream",
): { systemIds: Set<string>; contractIds: Set<string> } {
  const systemIds = new Set([systemId]);
  const contractIds = new Set<string>();
  if (focus === "all") {
    for (const item of integrations) {
      systemIds.add(item.source_system_id);
      systemIds.add(item.target_system_id);
      contractIds.add(item.id);
    }
    return { systemIds, contractIds };
  }
  if (focus === "neighbors") {
    for (const item of integrations) {
      if (item.source_system_id !== systemId && item.target_system_id !== systemId) continue;
      systemIds.add(item.source_system_id);
      systemIds.add(item.target_system_id);
      contractIds.add(item.id);
    }
    return { systemIds, contractIds };
  }
  let frontier = new Set([systemId]);
  while (frontier.size) {
    const next = new Set<string>();
    for (const item of integrations) {
      const from = focus === "upstream" ? item.target_system_id : item.source_system_id;
      const to = focus === "upstream" ? item.source_system_id : item.target_system_id;
      if (!frontier.has(from) || contractIds.has(item.id)) continue;
      contractIds.add(item.id);
      if (!systemIds.has(to)) {
        systemIds.add(to);
        next.add(to);
      }
    }
    frontier = next;
  }
  return { systemIds, contractIds };
}

const nodeTypes = { system: SystemLandscapeNodeCard };
const edgeTypes = { landscapeMapping: LandscapeMappingEdge };

function fallbackPosition(index: number): { x: number; y: number } {
  const column = index % 3;
  const row = Math.floor(index / 3);
  return { x: 80 + column * 420, y: 100 + row * 260 };
}

function LandscapeCanvasToolbar({
  onAutoLayout,
  locked,
  drawerOpen,
  onToggleLock,
}: {
  onAutoLayout: () => void;
  locked: boolean;
  drawerOpen: boolean;
  onToggleLock: () => void;
}) {
  const { fitView, zoomIn, zoomOut } = useReactFlow<LandscapeNode, LandscapeEdge>();
  return (
    <Panel position={drawerOpen ? "top-left" : "top-right"} className="landscape-canvas-actions">
      <button type="button" aria-label="Zoom out" title="Zoom out" onClick={() => void zoomOut()}>−</button>
      <button type="button" aria-label="Zoom in" title="Zoom in" onClick={() => void zoomIn()}>+</button>
      <button type="button" aria-label="Fit landscape to view" title="Fit view" onClick={() => void fitView({ padding: 0.22, duration: 250 })}>
        Fit
      </button>
      <button
        type="button"
        aria-label="Auto-layout landscape"
        title="Auto-layout"
        onClick={() => {
          onAutoLayout();
          window.requestAnimationFrame(() => void fitView({ padding: 0.2, duration: 250 }));
        }}
      >
        Auto-layout
      </button>
      <button
        type="button"
        aria-label={locked ? "Unlock system positions" : "Lock system positions"}
        title={locked ? "Unlock" : "Lock"}
        aria-pressed={locked}
        onClick={onToggleLock}
      >
        {locked ? "Unlock" : "Lock"}
      </button>
    </Panel>
  );
}

function FitLandscapeOnMode({ mode }: { mode: LandscapeMode }) {
  const { fitView } = useReactFlow<LandscapeNode, LandscapeEdge>();
  React.useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void fitView({ padding: 0.22, duration: 220 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [fitView, mode]);
  return null;
}

export default function EnterpriseLandscape({
  onOpenIntegration,
  onOpenCatalog,
  onAddIntegration,
}: Props) {
  const [systems, setSystems] = React.useState<System[]>([]);
  const [integrations, setIntegrations] = React.useState<Integration[]>([]);
  const [architectureIndex, setArchitectureIndex] = React.useState<EnterpriseArchitectureIndex | null>(null);
  const [objects, setObjects] = React.useState<Map<string, CatalogObject>>(new Map());
  const [fieldsByObject, setFieldsByObject] = React.useState<Map<string, CatalogField[]>>(new Map());
  const [expandedSystemIds, setExpandedSystemIds] = React.useState<Set<string>>(new Set());
  const [landscapeMode, setLandscapeMode] = React.useState<LandscapeMode>("systems");
  const [hybridPhaseFilter, setHybridPhaseFilter] = React.useState<HybridPhaseFilter>("request");
  const [search, setSearch] = React.useState("");
  const [systemKindFilter, setSystemKindFilter] = React.useState("all");
  const [interactionFilter, setInteractionFilter] = React.useState("all");
  const [validationFilter, setValidationFilter] = React.useState<LandscapeValidationFilter>("all");
  const [directionFilter, setDirectionFilter] = React.useState<"all" | "upstream" | "downstream">("all");
  const [selectedSystemId, setSelectedSystemId] = React.useState<string | null>(null);
  const [systemFocus, setSystemFocus] = React.useState<LandscapeFocus>("neighbors");
  const [architecture, setArchitecture] = React.useState<ArchitectureAnalysis>({
    integrations: [],
    conflicts: [],
  });
  const [nodes, setNodes] = React.useState<LandscapeNode[]>([]);
  const [edges, setEdges] = React.useState<LandscapeEdge[]>([]);
  const [selectedContractIds, setSelectedContractIds] = React.useState<string[]>([]);
  const [selectedIntegrationId, setSelectedIntegrationId] = React.useState<string | null>(null);
  const [mappingSourceFields, setMappingSourceFields] = React.useState<CatalogField[]>([]);
  const [mappingTargetFields, setMappingTargetFields] = React.useState<CatalogField[]>([]);
  const [mappingSimulation, setMappingSimulation] = React.useState<SimulationResult | null>(null);
  const [mappingLoading, setMappingLoading] = React.useState(false);
  const [mappingError, setMappingError] = React.useState("");
  const [positionsLocked, setPositionsLocked] = React.useState(false);
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [architectureIndexLoading, setArchitectureIndexLoading] = React.useState(true);
  const [savingPositions, setSavingPositions] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const requestSequence = React.useRef(0);
  const callbacksRef = React.useRef({ onAddIntegration, onOpenCatalog });
  callbacksRef.current = { onAddIntegration, onOpenCatalog };
  const addIntegration = React.useCallback((systemId: string) => {
    callbacksRef.current.onAddIntegration(systemId);
  }, []);
  const openCatalog = React.useCallback(() => {
    callbacksRef.current.onOpenCatalog();
  }, []);

  const toggleSystemExpanded = React.useCallback((systemId: string) => {
    setExpandedSystemIds((current) => {
      const next = new Set(current);
      if (next.has(systemId)) next.delete(systemId);
      else next.add(systemId);
      return next;
    });
    setNodes((items) => items.map((node) => node.id === systemId
      ? { ...node, data: { ...node.data, expanded: !node.data.expanded } }
      : node));
  }, []);

  const load = React.useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setArchitectureIndexLoading(true);
    setArchitectureIndex(null);
    setError("");
    try {
      const [systemsResult, integrationsResult, architectureResult] = await Promise.allSettled([
        list<System>("/api/catalog/systems"),
        list<Integration>("/api/integrations"),
        api<ArchitectureAnalysis>("/api/integrations/architecture"),
      ]);
      const nextSystems = systemsResult.status === "fulfilled" ? systemsResult.value : [];
      const nextIntegrations = integrationsResult.status === "fulfilled" ? integrationsResult.value : [];
      const nextArchitecture = architectureResult.status === "fulfilled"
        ? architectureResult.value
        : { integrations: [], conflicts: [] };
      const rootDiagnostics = [];
      if (systemsResult.status === "rejected") {
        rootDiagnostics.push({
          code: "systems_load_failed" as const,
          message: systemsResult.reason instanceof Error ? systemsResult.reason.message : "Could not load systems.",
        });
      }
      if (integrationsResult.status === "rejected") {
        rootDiagnostics.push({
          code: "contracts_load_failed" as const,
          message: integrationsResult.reason instanceof Error ? integrationsResult.reason.message : "Could not load contracts.",
        });
      }
      const architectureLoadFailed = architectureResult.status === "rejected";
      if (architectureLoadFailed) {
        rootDiagnostics.push({
          code: "index_load_failed" as const,
          message: architectureResult.reason instanceof Error
            ? `Architecture health could not be loaded: ${architectureResult.reason.message}`
            : "Architecture health could not be loaded.",
        });
      }
      const connectedSources = new Set<string>();
      const connectedTargets = new Set<string>();
      for (const integration of nextIntegrations) {
        for (const phase of HYBRID_PHASES) {
          for (const path of integrationPhasePaths(integration, phase)) {
            connectedSources.add(
              `${path.senderSystemId}:${path.senderObjectId}:${path.sourceFieldId}`,
            );
            connectedTargets.add(
              `${path.receiverSystemId}:${path.receiverObjectId}:${path.targetFieldId}`,
            );
          }
        }
      }
      let systemObjects: CatalogObject[][] = nextSystems.map(() => []);
      const createLandscapeNodes = (
        fieldIndex: Map<string, CatalogField[]>,
        architectureData: EnterpriseArchitectureIndex | null = null,
      ) =>
        nextSystems.map((system, systemIndex) => ({
          id: system.id,
          type: "system" as const,
          position: system.position ?? fallbackPosition(systemIndex),
          data: {
            label: system.name,
            kind: system.kind,
            color: system.color || "#527ca4",
            icon: system.icon || "",
            systemId: system.id,
            objectCount: systemObjects[systemIndex]?.length ?? 0,
            integrationCount: nextIntegrations.filter(
              (integration) =>
                integration.source_system_id === system.id
                || integration.target_system_id === system.id,
            ).length,
            incomingContractCount: nextIntegrations.filter(
              (integration) => integration.target_system_id === system.id,
            ).length,
            outgoingContractCount: nextIntegrations.filter(
              (integration) => integration.source_system_id === system.id,
            ).length,
            validationIssueContractCount: nextIntegrations.filter((integration) => {
              const status = validationForContract(architectureData, integration.id);
              return status !== "valid";
            }).filter((integration) =>
              integration.source_system_id === system.id
              || integration.target_system_id === system.id,
            ).length,
            fields: (systemObjects[systemIndex] ?? []).flatMap((object) =>
              (fieldIndex.get(object.id) ?? []).map((field) => ({
                id: field.id,
                objectId: object.id,
                objectLabel: object.label,
                name: field.name,
                dataType: field.data_type,
                sourceConnected: connectedSources.has(`${system.id}:${object.id}:${field.id}`),
                targetConnected: connectedTargets.has(`${system.id}:${object.id}:${field.id}`),
              })),
            ),
            expanded: false,
            showFields: true,
            compact: false,
            selected: false,
            dimmed: false,
            onToggleExpanded: toggleSystemExpanded,
            onSelectSystem: (systemId: string) => {
              setSelectedSystemId(systemId);
              setSelectedContractIds([]);
              setSelectedIntegrationId(null);
              setSystemFocus("neighbors");
              setDirectionFilter("all");
            },
            onAddIntegration: addIntegration,
            onOpenCatalog: openCatalog,
          },
        }));
      const nextIndex = await loadEnterpriseArchitectureIndex({
        systems: nextSystems,
        contracts: nextIntegrations,
        architectureHealth: nextArchitecture.integrations,
        loadDiagnostics: rootDiagnostics,
        rootsPartial: systemsResult.status === "rejected"
          || integrationsResult.status === "rejected"
          || architectureLoadFailed,
        rootsFailed: systemsResult.status === "rejected"
          && integrationsResult.status === "rejected",
        listObjectsForSystem: (systemId) =>
          list(`/api/catalog/systems/${systemId}/objects`),
        listFieldsForObject: (objectId) =>
          list(`/api/catalog/objects/${objectId}/fields`),
        onObjectsLoaded: (loadedObjects) => {
          if (requestId !== requestSequence.current) return;
          const objectIndex = new Map<string, CatalogObject>();
          for (const object of loadedObjects) {
            objectIndex.set(object.id, { id: object.id, label: object.label });
          }
          systemObjects = nextSystems.map((system) =>
            loadedObjects
              .filter((object) => object.system_id === system.id)
              .map((object) => ({ id: object.id, label: object.label })));
          setSystems(nextSystems);
          setIntegrations(nextIntegrations);
          setArchitecture(nextArchitecture);
          setObjects(objectIndex);
          setFieldsByObject(new Map());
          setNodes(createLandscapeNodes(new Map()));
          setLoading(false);
        },
      });
      const objectIndex = new Map<string, CatalogObject>();
      for (const object of nextIndex.objectsById.values()) {
        objectIndex.set(object.id, { id: object.id, label: object.displayName });
      }
      const visibleFieldObjectIds = new Set(nextIntegrations.flatMap((integration) => [
        integration.source_object_id,
        integration.target_object_id,
        ...(integration.error_response_object_id ? [integration.error_response_object_id] : []),
      ]));
      const fieldIndex = new Map<string, CatalogField[]>();
      for (const object of nextIndex.objectsById.values()) {
        if (!visibleFieldObjectIds.has(object.id)) continue;
        fieldIndex.set(object.id, object.fieldIds.flatMap((fieldId) => {
          const field = nextIndex.fieldsById.get(fieldId);
          return field ? [{
            id: field.id,
            name: field.technicalName,
            label: field.displayName,
            data_type: field.dataType,
            required: field.required,
            nullable: field.nullable,
          }] : [];
        }));
      }
      if (requestId !== requestSequence.current) return;
      setArchitectureIndex(nextIndex);
      setObjects(objectIndex);
      setFieldsByObject(fieldIndex);
      setNodes(createLandscapeNodes(fieldIndex, nextIndex));
      setArchitectureIndexLoading(false);
    } catch (caught) {
      if (requestId === requestSequence.current) {
        const message = caught instanceof Error ? caught.message : "Could not load the landscape.";
        setArchitectureIndex(createFailedEnterpriseArchitectureIndex(message));
        setArchitectureIndexLoading(false);
        setError(message);
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [addIntegration, openCatalog, toggleSystemExpanded]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const filteredIntegrations = React.useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase();
    const systemById = new Map(systems.map((system) => [system.id, system]));
    const directionContractIds = selectedSystemId && directionFilter !== "all"
      ? focusedRelationships(integrations, selectedSystemId, directionFilter).contractIds
      : null;
    return integrations.filter((integration) => {
      const sourceSystem = systemById.get(integration.source_system_id);
      const targetSystem = systemById.get(integration.target_system_id);
      const matchesSearch = !normalizedSearch
        || integration.name.toLocaleLowerCase().includes(normalizedSearch)
        || sourceSystem?.name.toLocaleLowerCase().includes(normalizedSearch)
        || targetSystem?.name.toLocaleLowerCase().includes(normalizedSearch);
      const matchesKind = systemKindFilter === "all"
        || sourceSystem?.kind === systemKindFilter
        || targetSystem?.kind === systemKindFilter;
      const matchesInteraction = interactionFilter === "all"
        || integration.interaction_type === interactionFilter;
      const validation = validationFactsForContract(architectureIndex, integration.id);
      const matchesValidation = validationFilter === "all"
        || (validationFilter === "errors" && validation.errors)
        || (validationFilter === "warnings" && validation.warnings)
        || (validationFilter === "incomplete" && validation.incomplete)
        || (validationFilter === "valid"
          && !validation.errors && !validation.warnings && !validation.incomplete);
      const matchesDirection = directionFilter === "all"
        || !selectedSystemId
        || directionContractIds?.has(integration.id) === true;
      return matchesSearch && matchesKind && matchesInteraction && matchesValidation && matchesDirection;
    });
  }, [
    architectureIndex,
    directionFilter,
    integrations,
    interactionFilter,
    search,
    selectedSystemId,
    systemKindFilter,
    systems,
    validationFilter,
  ]);

  const visibleSystemIds = React.useMemo(() => {
    const hasFilter = Boolean(search.trim()) || systemKindFilter !== "all"
      || interactionFilter !== "all" || validationFilter !== "all"
      || (directionFilter !== "all" && Boolean(selectedSystemId));
    if (!hasFilter) return new Set(systems.map((system) => system.id));
    const normalizedSearch = search.trim().toLocaleLowerCase();
    const result = new Set<string>();
    for (const system of systems) {
      const matchesSearch = !normalizedSearch
        || system.name.toLocaleLowerCase().includes(normalizedSearch)
        || filteredIntegrations.some((integration) =>
          (integration.source_system_id === system.id || integration.target_system_id === system.id)
          && integration.name.toLocaleLowerCase().includes(normalizedSearch));
      const matchesKind = systemKindFilter === "all" || system.kind === systemKindFilter;
      if (matchesSearch && matchesKind) result.add(system.id);
    }
    for (const integration of filteredIntegrations) {
      result.add(integration.source_system_id);
      result.add(integration.target_system_id);
    }
    if (selectedSystemId) result.add(selectedSystemId);
    return result;
  }, [
    directionFilter,
    filteredIntegrations,
    interactionFilter,
    search,
    selectedSystemId,
    systemKindFilter,
    systems,
    validationFilter,
  ]);

  React.useEffect(() => {
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const healthById = new Map(
      architecture.integrations.map((item) => [item.id, item]),
    );
    const nextEdges: LandscapeEdge[] = [];
    if (landscapeMode === "systems" || landscapeMode === "contracts") {
      const obstacles = nodes.map((node) => ({
        systemId: node.id,
        x: node.position.x,
        y: node.position.y,
        width: 320,
        height: 150,
      }));
      const focusedContractIds = selectedSystemId
        ? focusedRelationships(integrations, selectedSystemId, systemFocus).contractIds
        : null;
      const bundles = new Map<string, Integration[]>();
      for (const integration of filteredIntegrations) {
        const key = `${integration.source_system_id}\u0000${integration.target_system_id}`;
        const bundle = bundles.get(key) ?? [];
        bundle.push(integration);
        bundles.set(key, bundle);
      }
      for (const [bundleKey, contracts] of bundles) {
        const [sourceSystemId, targetSystemId] = bundleKey.split("\u0000");
        const bundleStates = contracts.map((item) =>
          validationForContract(architectureIndex, item.id));
        const issueCount = contracts.filter((item) => {
          const facts = validationFactsForContract(architectureIndex, item.id);
          return facts.errors || facts.warnings || facts.incomplete;
        }).length;
        const bundleStatus: LandscapeValidation = bundleStates.includes("errors")
          ? "errors"
          : bundleStates.includes("warnings")
            ? "warnings"
            : bundleStates.includes("incomplete")
              ? "incomplete"
              : "valid";
        const isContractMode = landscapeMode === "contracts";
        const edgeContracts = isContractMode ? contracts : [contracts[0]!];
        edgeContracts.forEach((integration, laneIndex) => {
          const status = validationForContract(architectureIndex, integration.id);
          const displayedStatus = isContractMode ? status : bundleStatus;
          const color = validationColor(displayedStatus);
          const selected = isContractMode
            ? selectedContractIds.includes(integration.id)
            : contracts.some((item) => selectedContractIds.includes(item.id));
          const matchesFocus = !focusedContractIds
            || contracts.some((item) => focusedContractIds.has(item.id));
          const opacity = selectedSystemId && !matchesFocus ? 0.14 : 1;
          const label = isContractMode
            ? `${integration.name}\n${interactionLabel(integration.interaction_type)} · ${validationLabel(status)}`
            : `${contracts.length} ${contracts.length === 1 ? "contract" : "contracts"}`
              + (issueCount
                ? ` · ${issueCount} ${issueCount === 1 ? "issue" : "issues"} · ${validationLabel(bundleStatus)}`
                : ` · ${validationLabel(bundleStatus)}`);
          nextEdges.push({
            id: isContractMode
              ? `contract:${integration.id}`
              : `bundle:${sourceSystemId}:${targetSystemId}`,
            source: sourceSystemId,
            target: targetSystemId,
            sourceHandle: "system-out",
            targetHandle: "system-in",
            label: isContractMode ? label : laneIndex === 0 ? label : undefined,
            type: "landscapeMapping",
            animated: false,
            labelShowBg: true,
            labelStyle: { fill: "#344c62", fontWeight: 700, fontSize: isContractMode ? 10 : 12 },
            data: {
              integrationId: integration.id,
              contractIds: isContractMode ? [integration.id] : contracts.map((item) => item.id),
              bundleKey,
              laneIndex: isContractMode ? laneIndex : 0,
              laneCount: isContractMode ? contracts.length : 1,
              obstacles,
              sourceSystemId,
              targetSystemId,
              dimmed: opacity < 1,
              sampleRows: integration.sample_rows.length,
              status: displayedStatus,
              phase: "contract",
            },
            className: `${selected ? "landscape-edge-selected " : ""}${isContractMode ? `interaction-${integration.interaction_type.toLowerCase()}` : "landscape-bundle-edge"}`,
            style: {
              stroke: color,
              strokeWidth: selected ? 3 : isContractMode ? 2 : 2,
              opacity,
              ...(!isContractMode && bundleStatus === "incomplete" ? { strokeDasharray: "7 5" } : {}),
              ...(isContractMode && integration.interaction_type === "ASYNC_CALLBACK"
                ? { strokeDasharray: "7 5" }
                : {}),
            },
            markerEnd: { type: MarkerType.ArrowClosed, color },
          });
        });
      }
      if (landscapeMode === "systems") {
        const grouped = new Map<string, LandscapeEdge>();
        for (const edge of nextEdges) grouped.set(edge.id, edge);
        setEdges([...grouped.values()]);
      } else {
        setEdges(nextEdges);
      }
      return;
    }
    for (const integration of integrations) {
      const status = healthById.get(integration.id)?.status ?? "draft";
      const healthColor = status === "attention"
        ? "#bd4e45"
        : status === "healthy"
          ? "#39805b"
          : "#9a854e";
      const selected = selectedIntegrationId === integration.id;
      const sourceNode = nodeById.get(integration.source_system_id);
      const targetNode = nodeById.get(integration.target_system_id);
      const sourceExpanded = sourceNode?.data.expanded ?? false;
      const targetExpanded = targetNode?.data.expanded ?? false;
      const hybrid = landscapeMode === "hybrid";
      const phases: LandscapeMappingPhase[] = hybrid
        ? HYBRID_PHASES.filter((phase) =>
          (hybridPhaseFilter === "all" || phase === hybridPhaseFilter)
          && (phase !== "success-response" || integration.interaction_type !== "ONE_WAY")
          && (phase !== "error-response" || Boolean(integration.error_response_object_id)))
        : sourceExpanded || targetExpanded
          ? [
            "request",
            ...(integration.interaction_type !== "ONE_WAY" ? ["success-response" as const] : []),
          ]
          : [];
      if (!hybrid && !sourceExpanded && !targetExpanded) {
        nextEdges.push({
          id: integration.id,
          source: integration.source_system_id,
          target: integration.target_system_id,
          sourceHandle: "system-out",
          targetHandle: "system-in",
          label: `${status === "attention" ? "⚠ " : ""}${integration.name} · ${designStatusLabel(status)}`,
          type: "landscapeMapping",
          animated: status === "healthy",
          labelShowBg: true,
          labelStyle: { fill: "#344c62", fontWeight: 600, fontSize: 10 },
          data: {
            integrationId: integration.id,
            contractIds: [integration.id],
            sampleRows: integration.sample_rows.length,
            status,
          },
          className: selected ? "landscape-edge-selected" : undefined,
          style: {
            stroke: healthColor,
            strokeWidth: selected ? 4 : status === "attention" ? 2.7 : 2.2,
            ...(status === "draft" ? { strokeDasharray: "7 5" } : {}),
          },
          markerEnd: { type: MarkerType.ArrowClosed, color: healthColor },
          ...(integration.interaction_type !== "ONE_WAY"
            ? { markerStart: { type: MarkerType.ArrowClosed, color: healthColor } }
            : {}),
        });
        continue;
      }

      const resolvedPaths = phases.flatMap((phase) =>
        integrationPhasePaths(integration, phase).map((path) => ({ phase, path })));
      const paths = resolvedPaths.filter(({ path }) =>
        (fieldsByObject.get(path.senderObjectId) ?? []).some((field) => field.id === path.sourceFieldId)
        && (fieldsByObject.get(path.receiverObjectId) ?? []).some((field) => field.id === path.targetFieldId));

      if (hybrid && paths.length === 0) {
        for (const phase of phases) {
          const path = integrationPhasePaths(integration, phase)[0];
          const sourceSystemId = path?.senderSystemId ?? (
            phase === "request" ? integration.source_system_id : integration.target_system_id
          );
          const targetSystemId = path?.receiverSystemId ?? (
            phase === "request" ? integration.target_system_id : integration.source_system_id
          );
          const color = phaseColor(phase);
          nextEdges.push({
            id: `${integration.id}:${phase}:unmapped`,
            source: sourceSystemId,
            target: targetSystemId,
            sourceHandle: "system-out",
            targetHandle: "system-in",
            label: `${integration.name} · ${phaseLabel(phase)} · no mapped fields`,
            type: "landscapeMapping",
            animated: false,
            labelShowBg: true,
            labelStyle: { fill: "#344c62", fontWeight: 600, fontSize: 10 },
            data: { integrationId: integration.id, contractIds: [integration.id], sampleRows: integration.sample_rows.length, status, phase },
            className: selected ? "landscape-edge-selected" : undefined,
            style: { stroke: color, strokeWidth: selected ? 4 : 2.2 },
            markerEnd: { type: MarkerType.ArrowClosed, color },
          });
        }
        continue;
      }

      for (const [index, { phase, path }] of paths.entries()) {
        const sourceNode = nodeById.get(path.senderSystemId);
        const targetNode = nodeById.get(path.receiverSystemId);
        const sourceExpandedForPath = sourceNode?.data.expanded ?? false;
        const targetExpandedForPath = targetNode?.data.expanded ?? false;
        const sourceField = fieldsByObject.get(path.senderObjectId)
          ?.find((field) => field.id === path.sourceFieldId);
        const targetField = fieldsByObject.get(path.receiverObjectId)
          ?.find((field) => field.id === path.targetFieldId);
        if (!sourceField || !targetField) continue;
        const fieldLevel = hybrid || sourceExpandedForPath || targetExpandedForPath;
        const color = hybrid ? phaseColor(phase) : healthColor;
        nextEdges.push({
          id: `${integration.id}:${phase}:${path.senderObjectId}:${path.sourceFieldId}:${path.receiverObjectId}:${path.targetFieldId}:${index}`,
          source: path.senderSystemId,
          target: path.receiverSystemId,
          sourceHandle: sourceExpandedForPath
            ? `out:${path.senderObjectId}:${path.sourceFieldId}`
            : "system-out",
          targetHandle: targetExpandedForPath
            ? `in:${path.receiverObjectId}:${path.targetFieldId}`
            : "system-in",
          label: fieldLevel
            ? path.transformations.length
              ? `⚡ ${path.transformations.join(" → ")}`
              : "Direct"
            : `${integration.name} · ${phaseLabel(phase)}`,
          type: "landscapeMapping",
          animated: hybrid || status === "healthy",
          labelShowBg: true,
          labelStyle: { fill: "#344c62", fontWeight: 600, fontSize: 10 },
          data: {
            integrationId: integration.id,
            contractIds: [integration.id],
            sampleRows: integration.sample_rows.length,
            status,
            phase,
            sourceFieldId: path.sourceFieldId,
            targetFieldId: path.targetFieldId,
            transformations: path.transformations,
          },
          className: selected ? "landscape-edge-selected" : undefined,
          style: {
            stroke: color,
            strokeWidth: selected ? 4 : status === "attention" ? 2.7 : 2.2,
            ...(status === "draft" ? { strokeDasharray: "7 5" } : {}),
          },
          markerEnd: { type: MarkerType.ArrowClosed, color },
        });
      }
    }
    setEdges(nextEdges);
  }, [
    architecture.integrations,
    architectureIndex,
    fieldsByObject,
    filteredIntegrations,
    hybridPhaseFilter,
    integrations,
    landscapeMode,
    nodes,
    selectedContractIds,
    selectedIntegrationId,
    selectedSystemId,
    systemFocus,
    integrations,
  ]);

  React.useEffect(() => {
    if (!selectedIntegrationId) return;
    const selected = integrations.find((integration) => integration.id === selectedIntegrationId);
    if (!selected) return;
    if (landscapeMode === "contracts") {
      setMappingLoading(false);
      setMappingError("");
      setMappingSourceFields([]);
      setMappingTargetFields([]);
      setMappingSimulation(null);
      return;
    }
    let active = true;
    setMappingLoading(true);
    setMappingError("");
    setMappingSourceFields([]);
    setMappingTargetFields([]);
    setMappingSimulation(null);
    Promise.all([
      api<CatalogField[]>(`/api/catalog/objects/${selected.source_object_id}/fields`),
      api<CatalogField[]>(`/api/catalog/objects/${selected.target_object_id}/fields`),
    ]).then(async ([sourceFields, targetFields]) => {
      if (!active) return;
      setMappingSourceFields(sourceFields);
      setMappingTargetFields(targetFields);
      const simulation = await api<SimulationResult>(`/api/integrations/${selected.id}/dry-run`, {
        method: "POST",
        body: JSON.stringify({
          expectedRevision: selected.revision,
          graph: selected.graph,
          ...(selected.interaction_type !== "ONE_WAY"
            ? {
              responsePayload: [{
                rowId: "landscape-response",
                values: Object.fromEntries(targetFields.map((field) => [field.id, null])),
              }],
            }
            : {}),
          options: { includeTraceValues: true },
        }),
      });
      if (active) setMappingSimulation(simulation);
    }).catch((caught: unknown) => {
      if (!active) return;
      setMappingError(caught instanceof Error ? caught.message : "Could not load contract mappings.");
    }).finally(() => {
      if (active) setMappingLoading(false);
    });
    return () => {
      active = false;
    };
  }, [selectedIntegrationId, integrations, landscapeMode]);

  async function savePosition(systemId: string, position: { x: number; y: number }) {
    setSavingPositions(true);
    setNotice("");
    setError("");
    try {
      const response = await api<System>(`/api/catalog/systems/${systemId}`, {
        method: "PATCH",
        body: JSON.stringify({ position }),
      });
      setSystems((items) => items.map((item) => item.id === systemId ? response : item));
      setNotice("System position saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save system position.");
    } finally {
      setSavingPositions(false);
    }
  }

  const onNodeDragStop = React.useCallback(
    (_event: MouseEvent | TouchEvent, node: LandscapeNode) => {
      void savePosition(node.id, node.position);
    },
    [],
  );

  function openEdge(_event: React.MouseEvent, edge: LandscapeEdge) {
    if (landscapeMode === "systems" || landscapeMode === "contracts") {
      setSelectedSystemId(null);
      setSelectedContractIds(edge.data?.contractIds ?? [edge.data?.integrationId ?? edge.id]);
    } else {
      setSelectedIntegrationId(edge.data?.integrationId ?? edge.id);
    }
  }

  const closeMappingDrawer = React.useCallback(() => {
    setSelectedContractIds([]);
    setSelectedSystemId(null);
    setSelectedIntegrationId(null);
    setDirectionFilter("all");
  }, []);

  function setLandscapeDetailLevel(hybrid: boolean) {
    setLandscapeMode(hybrid ? "hybrid" : "systems");
    setSelectedContractIds([]);
    setSelectedSystemId(null);
    setSelectedIntegrationId(null);
    if (hybrid) setHybridPhaseFilter("request");
    const expanded = hybrid
      ? new Set(nodes.filter((node) => node.data.fields.length > 0).map((node) => node.id))
      : new Set<string>();
  const drawerOpen = Boolean(
      selectedSystem || selectedContracts.length > 0 || (selectedIntegration && hybridMode),
  );
    setExpandedSystemIds(expanded);
    setNodes((current) => current.map((node) => ({
      ...node,
      data: { ...node.data, expanded: expanded.has(node.id), showFields: true },
    })));
  }

  function setContractsMode() {
    setLandscapeMode("contracts");
    setSelectedSystemId(null);
    setSelectedIntegrationId(null);
    setSelectedContractIds([]);
    setExpandedSystemIds(new Set());
    setNodes((current) => current.map((node) => ({
      ...node,
      data: { ...node.data, expanded: false, showFields: false },
    })));
  }

  function setScenariosMode() {
    setLandscapeDetailLevel(false);
    setLandscapeMode("scenarios");
    setSelectedContractIds([]);
    setSelectedSystemId(null);
    setSelectedIntegrationId(null);
  }

  function setLineageMode() {
    setLandscapeDetailLevel(false);
    setLandscapeMode("lineage");
    setSelectedContractIds([]);
    setSelectedSystemId(null);
    setSelectedIntegrationId(null);
  }

  function selectSystem(systemId: string) {
    setSelectedSystemId(systemId);
    setSelectedContractIds([]);
    setSelectedIntegrationId(null);
    setSystemFocus("neighbors");
    setDirectionFilter("all");
  }

  function autoLayout() {
    const systemIds = nodes.map((node) => node.id);
    const outgoing = new Map(systemIds.map((id) => [id, new Set<string>()]));
    const indegree = new Map(systemIds.map((id) => [id, 0]));
    for (const edge of edges) {
      if (edge.source === edge.target || !outgoing.has(edge.source) || !outgoing.has(edge.target)) continue;
      const next = outgoing.get(edge.source);
      if (!next?.has(edge.target)) {
        next?.add(edge.target);
        indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
      }
    }
    const ranks = new Map(systemIds.map((id) => [id, 0]));
    const queue = systemIds.filter((id) => indegree.get(id) === 0);
    const visited = new Set<string>();
    while (queue.length) {
      const current = queue.shift()!;
      visited.add(current);
      for (const next of outgoing.get(current) ?? []) {
        ranks.set(next, Math.max(ranks.get(next) ?? 0, (ranks.get(current) ?? 0) + 1));
        indegree.set(next, (indegree.get(next) ?? 1) - 1);
        if (indegree.get(next) === 0) queue.push(next);
      }
    }
    const maxRank = Math.max(0, ...ranks.values());
    const unresolvedRank = maxRank + 1;
    for (const id of systemIds) {
      if (!visited.has(id)) ranks.set(id, unresolvedRank);
    }
    const byRank = new Map<number, LandscapeNode[]>();
    for (const node of nodes) {
      const rank = ranks.get(node.id) ?? 0;
      const group = byRank.get(rank) ?? [];
      group.push(node);
      byRank.set(rank, group);
    }
    const laidOut = new Map<string, { x: number; y: number }>();
    for (const [rank, group] of byRank) {
      group.forEach((node, index) => {
        laidOut.set(node.id, { x: 70 + rank * 460, y: 80 + index * 240 });
      });
    }
    setNodes((current) => current.map((node) => ({
      ...node,
      position: laidOut.get(node.id) ?? node.position,
    })));
    setNotice("Auto-layout applied to this view. Saved system positions are unchanged.");
    setError("");
  }
  const architectureById = new Map(
    architecture.integrations.map((item) => [item.id, item]),
  );
  const validationCounts = integrations.reduce((counts, integration) => {
    const facts = validationFactsForContract(architectureIndex, integration.id);
    if (facts.errors) counts.errors += 1;
    if (facts.warnings) counts.warnings += 1;
    if (facts.incomplete) counts.incomplete += 1;
    if (!facts.errors && !facts.warnings && !facts.incomplete) counts.valid += 1;
    return counts;
  }, { valid: 0, warnings: 0, errors: 0, incomplete: 0 });
  const selectedIntegration = integrations.find((item) => item.id === selectedIntegrationId);
  const selectedContracts = selectedContractIds.flatMap((id) => {
    const contract = integrations.find((item) => item.id === id);
    return contract ? [contract] : [];
  });
  const selectedSystem = systems.find((item) => item.id === selectedSystemId);
  const contractsMode = landscapeMode === "contracts";
  const systemsMode = landscapeMode === "systems";
  const hybridMode = landscapeMode === "hybrid";
  const lineageMode = landscapeMode === "lineage";
  const scenariosMode = landscapeMode === "scenarios";
  const drawerOpen = Boolean(
    selectedSystem || selectedContracts.length > 0 || (selectedIntegration && hybridMode),
  );
  const focusSystemIds = selectedSystemId
    ? systemFocus === "all"
      ? new Set(systems.map((system) => system.id))
      : focusedRelationships(integrations, selectedSystemId, systemFocus).systemIds
    : new Set<string>();
  const renderedNodes = (systemsMode || contractsMode
    ? nodes.filter((node) => visibleSystemIds.has(node.id))
    : nodes).map((node) => {
    const validationIssueContractCount = integrations.filter((integration) => {
      if (integration.source_system_id !== node.id && integration.target_system_id !== node.id) return false;
      const facts = validationFactsForContract(architectureIndex, integration.id);
      return facts.errors || facts.warnings;
    }).length;
    return {
      ...node,
      data: {
        ...node.data,
        objectCount: architectureIndex?.systemsById.get(node.id)?.objectIds.length ?? node.data.objectCount,
        incomingContractCount: integrations.filter((item) => item.target_system_id === node.id).length,
        outgoingContractCount: integrations.filter((item) => item.source_system_id === node.id).length,
        validationIssueContractCount,
        expanded: hybridMode && node.data.expanded,
        showFields: hybridMode,
        compact: systemsMode || contractsMode,
        selected: selectedSystemId === node.id,
        dimmed: Boolean(selectedSystemId && !focusSystemIds.has(node.id)),
      },
    };
  });
  const systemKinds = [...new Set(systems.map((system) => system.kind).filter(Boolean))].sort();
  const sourceSystemName = systems.find(
    (item) => item.id === selectedIntegration?.source_system_id,
  )?.name ?? "Source system";
  const targetSystemName = systems.find(
    (item) => item.id === selectedIntegration?.target_system_id,
  )?.name ?? "Target system";

  return (
    <section className="landscape-workspace">
      <header className="landscape-header">
        <div>
          <p className="eyebrow">ARCHITECTURE OVERVIEW</p>
          <h2>Enterprise landscape</h2>
          <p>{scenariosMode
            ? "Design end-to-end scenarios across contracts and review them as sequence diagrams."
            : contractsMode
            ? "Select a directed contract edge to inspect its phases, validation, and dependencies."
            : hybridMode
              ? "Legacy advanced view: inspect phase-specific field mappings and transformations."
              : "Explore systems and initiating contract relationships. Select a system or relationship for details."}</p>
        </div>
        <div className="landscape-status">
          {savingPositions ? (
            <span role="status">Saving positions…</span>
          ) : notice ? (
            <span role="status">{notice}</span>
          ) : null}
          <div className="landscape-detail-switch" role="group" aria-label="Landscape view">
            <button
              type="button"
              className={landscapeMode === "systems" ? "active" : ""}
              aria-pressed={landscapeMode === "systems"}
              onClick={() => setLandscapeDetailLevel(false)}
            >
              Systems
            </button>
            <button
              type="button"
              className={contractsMode ? "active" : ""}
              aria-pressed={contractsMode}
              onClick={setContractsMode}
            >
              Contracts
            </button>
            <button
              type="button"
              className={lineageMode ? "active" : ""}
              aria-pressed={lineageMode}
              onClick={setLineageMode}
            >
              Field Lineage
            </button>
            <button
              type="button"
              className={scenariosMode ? "active" : ""}
              aria-pressed={scenariosMode}
              onClick={setScenariosMode}
            >
              Scenarios
            </button>
            <details className="landscape-advanced-menu" open={advancedOpen} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
              <summary>Advanced</summary>
              <button
                type="button"
                className={hybridMode ? "active" : ""}
                aria-pressed={hybridMode}
                onClick={() => {
                  setLandscapeDetailLevel(true);
                  setAdvancedOpen(false);
                }}
              >
                Legacy Hybrid (advanced)
              </button>
            </details>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void load()}
            disabled={loading || architectureIndexLoading}
          >
            Refresh
          </button>
        </div>
      </header>
      <section className="landscape-kpis" aria-label="Enterprise landscape metrics">
        <div className="landscape-kpi"><span>Systems</span><strong>{systems.length}</strong></div>
        <div className="landscape-kpi"><span>Contracts</span><strong>{integrations.length}</strong></div>
        <div className={`landscape-kpi${validationCounts.errors ? " errors" : ""}`}>
          <span>Contracts with errors</span><strong>{validationCounts.errors}</strong>
        </div>
        <div className={`landscape-kpi${validationCounts.warnings ? " attention" : ""}`}>
          <span>Contracts with warnings</span><strong>{validationCounts.warnings}</strong>
        </div>
        <div className={`landscape-kpi${validationCounts.incomplete ? " attention" : ""}`}>
          <span>Incomplete contracts</span><strong>{validationCounts.incomplete}</strong>
        </div>
      </section>
      {error && <p className="editor-alert" role="alert">{error}</p>}
      {scenariosMode ? (
        // Kept mounted across Refresh so an unsaved scenario draft survives an index reload.
        <ScenarioWorkspace
          index={architectureIndex}
          onOpenContractPhase={(contractId, phase) => onOpenIntegration(contractId, phase)}
        />
      ) : loading ? (
        <div className="landscape-empty" role="status">Loading systems and contracts…</div>
      ) : lineageMode ? (
        <FieldLineageExplorer
          index={architectureIndex}
          loading={architectureIndexLoading}
          onOpenContract={onOpenIntegration}
        />
      ) : systems.length === 0 ? (
        <div className="landscape-empty">
          <span className="empty-icon">◇</span>
          <h3>Your landscape is empty</h3>
          <p>Create generic systems, objects, and fields, then add contracts to see your architecture here.</p>
          <button type="button" onClick={onOpenCatalog}>Open catalog</button>
        </div>
      ) : (
        <>
          {(systemsMode || contractsMode) && (
            <div className="landscape-filters" aria-label="Landscape search and filters">
              <label className="landscape-search">
                <span>Search</span>
                <input
                  aria-label="Search systems and contracts"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="System or contract name"
                />
              </label>
              <label>
                System kind
                <select aria-label="Filter by system kind" value={systemKindFilter} onChange={(event) => setSystemKindFilter(event.target.value)}>
                  <option value="all">All kinds</option>
                  {systemKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
                </select>
              </label>
              <label>
                Interaction
                <select aria-label="Filter by interaction pattern" value={interactionFilter} onChange={(event) => setInteractionFilter(event.target.value)}>
                  <option value="all">All patterns</option>
                  <option value="ONE_WAY">One-way</option>
                  <option value="REQUEST_RESPONSE">Request/Response</option>
                  <option value="ASYNC_CALLBACK">Async callback</option>
                </select>
              </label>
              <label>
                Validation
                <select aria-label="Filter by validation" value={validationFilter} onChange={(event) => setValidationFilter(event.target.value as LandscapeValidationFilter)}>
                  <option value="all">All</option>
                  <option value="errors">Errors</option>
                  <option value="warnings">Warnings</option>
                  <option value="valid">Valid</option>
                  <option value="incomplete">Incomplete</option>
                </select>
              </label>
              <label>
                Relative direction
                <select
                  aria-label="Filter by direction relative to selected system"
                  value={directionFilter}
                  disabled={!selectedSystemId}
                  onChange={(event) => setDirectionFilter(event.target.value as "all" | "upstream" | "downstream")}
                >
                  <option value="all">All</option>
                  <option value="upstream">Upstream</option>
                  <option value="downstream">Downstream</option>
                </select>
              </label>
            </div>
          )}
          {hybridMode ? (
            <div className="hybrid-phase-controls">
              <label>
                Display phase
                <select
                  aria-label="Hybrid Architecture phase"
                  value={hybridPhaseFilter}
                  onChange={(event) => setHybridPhaseFilter(event.target.value as HybridPhaseFilter)}
                >
                  <option value="request">Request</option>
                  <option value="success-response">Success Response</option>
                  <option value="error-response">Error Response</option>
                  <option value="all">All phases</option>
                </select>
              </label>
              <div className="hybrid-phase-legend" aria-label="Message phase colors">
                {HYBRID_PHASES.map((phase) => (
                  <span key={phase}>
                    <i style={{ backgroundColor: phaseColor(phase) }} />
                    {phaseLabel(phase)}
                  </span>
                ))}
              </div>
            </div>
          ) : !systemsMode && !contractsMode ? (
            <div className="landscape-legend" aria-label="Landscape status legend">
              <span><i className="legend-dot draft" /> Draft · no target mappings</span>
              <span><i className="legend-dot attention" /> Needs review · conflicts or contracts needing validation</span>
              <span><i className="legend-dot healthy" /> Valid · mapped without known conflicts</span>
            </div>
          ) : null}
          <div className="landscape-flow-shell">
            <ReactFlow<LandscapeNode, LandscapeEdge>
              nodes={renderedNodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={(changes) => {
                setNodes((current) => applyNodeChanges(changes, current));
              }}
              onNodeClick={(_event, node) => {
                if (landscapeMode === "systems" || landscapeMode === "contracts") selectSystem(node.id);
              }}
              onPaneClick={() => {
                setSelectedSystemId(null);
                setSelectedContractIds([]);
                setSelectedIntegrationId(null);
                setDirectionFilter("all");
              }}
              onNodeDragStop={onNodeDragStop}
              onEdgeClick={openEdge}
              onEdgeDoubleClick={openEdge}
              onEdgesChange={() => undefined}
              nodesDraggable={!positionsLocked}
              nodesConnectable={false}
              minZoom={0.25}
              maxZoom={1.8}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#dce4ec" gap={22} />
              <FitLandscapeOnMode mode={landscapeMode} />
              {renderedNodes.length >= 5 && (
                <MiniMap
                  pannable
                  zoomable
                  className="landscape-minimap"
                  style={{ width: 132, height: 82 }}
                  nodeColor={(node) => (node.data as SystemLandscapeNodeData).color}
                />
              )}
              {!lineageMode && (
                <LandscapeCanvasToolbar
                  onAutoLayout={autoLayout}
                  locked={positionsLocked}
                  drawerOpen={drawerOpen}
                  onToggleLock={() => setPositionsLocked((current) => !current)}
                />
              )}
            </ReactFlow>
            {selectedSystem && (systemsMode || contractsMode) && (
              <aside className="landscape-contract-details landscape-system-details" aria-label="System details">
                <header>
                  <div>
                    <p className="eyebrow">SYSTEM DETAILS</p>
                    <h3>{selectedSystem.name}</h3>
                  </div>
                  <button type="button" className="secondary-button" onClick={closeMappingDrawer}>
                    Close
                  </button>
                </header>
                <dl>
                  <dt>Kind</dt><dd>{selectedSystem.kind || "Not specified"}</dd>
                  <dt>Objects</dt><dd>{architectureIndex?.systemsById.get(selectedSystem.id)?.objectIds.length ?? 0}</dd>
                  <dt>Incoming contracts</dt><dd>{integrations.filter((item) => item.target_system_id === selectedSystem.id).length}</dd>
                  <dt>Outgoing contracts</dt><dd>{integrations.filter((item) => item.source_system_id === selectedSystem.id).length}</dd>
                  <dt>Contracts with issues</dt><dd>{integrations.filter((item) =>
                    (item.source_system_id === selectedSystem.id || item.target_system_id === selectedSystem.id)
                    && ["errors", "warnings"].includes(validationForContract(architectureIndex, item.id)),
                  ).length}</dd>
                </dl>
                <div className="landscape-focus-controls" role="group" aria-label="System focus">
                  {(["neighbors", "upstream", "downstream", "all"] as const).map((focus) => (
                    <button
                      type="button"
                      key={focus}
                      className={systemFocus === focus ? "active" : ""}
                      aria-pressed={systemFocus === focus}
                      onClick={() => setSystemFocus(focus)}
                    >
                      {focus === "all" ? "All" : focus[0]!.toUpperCase() + focus.slice(1)}
                    </button>
                  ))}
                </div>
              </aside>
            )}
            {selectedContracts.length > 0 && (systemsMode || contractsMode) && (
              <aside className="landscape-contract-details landscape-relationship-details" aria-label="Contract relationship details">
                <header>
                  <div>
                    <p className="eyebrow">{contractsMode ? "CONTRACT DETAILS" : "RELATIONSHIP DETAILS"}</p>
                    <h3>{selectedContracts.length === 1
                      ? selectedContracts[0]!.name
                      : `${selectedContracts.length} contracts`}</h3>
                  </div>
                  <button type="button" className="secondary-button" onClick={closeMappingDrawer}>Close</button>
                </header>
                <div className="landscape-contract-detail-list">
                  {selectedContracts.map((contract) => {
                    const sourceName = systems.find((item) => item.id === contract.source_system_id)?.name ?? "Unknown system";
                    const targetName = systems.find((item) => item.id === contract.target_system_id)?.name ?? "Unknown system";
                    const phases = architectureIndex?.phasesByContractId.get(contract.id) ?? [];
                    const diagnostics = architectureIndex?.loadDiagnostics.filter((item) =>
                      item.contractId === contract.id && item.issue,
                    ) ?? [];
                    const validationMessages = [...new Set(phases.flatMap((phase) =>
                      phase.chains.flatMap((chain) => [
                        ...(chain.validation?.status !== "Valid" && chain.validation?.issue
                          ? [`${phaseDisplayName(phase.phase)}: ${chain.validation.issue}`]
                          : []),
                        ...chain.issues.map((issue) => `${phase.phase}: ${issue.message}`),
                      ]),
                    ))];
                    const dependencies = architectureById.get(contract.id)?.upstream ?? [];
                    return (
                      <section className="landscape-contract-detail-card" key={contract.id}>
                        <h4>{contract.name}</h4>
                        <dl>
                          <dt>Initiator → receiver</dt>
                          <dd>{sourceName} · {objects.get(contract.source_object_id)?.label ?? "Source object"}
                            {" → "}
                            {targetName} · {objects.get(contract.target_object_id)?.label ?? "Target object"}
                          </dd>
                          <dt>Interaction</dt><dd>{interactionLabel(contract.interaction_type)}</dd>
                          <dt>Validation</dt>
                          <dd className={`validation-${validationForContract(architectureIndex, contract.id)}`}>
                            {validationLabel(validationForContract(architectureIndex, contract.id))}
                          </dd>
                          <dt>Dependencies</dt>
                          <dd>{dependencies.length
                            ? dependencies.map((item) => item.name).join(", ")
                            : architectureById.has(contract.id) ? "None" : "Unavailable"}</dd>
                        </dl>
                        <div className="landscape-phase-summaries">
                          {phases.map((phase) => {
                            const phaseName = phaseDisplayName(phase.phase);
                            const sender = systems.find((item) => item.id === phase.senderSystemId)?.name ?? "Unknown system";
                            const receiver = systems.find((item) => item.id === phase.receiverSystemId)?.name ?? "Unknown system";
                            const summary = phase.validationSummary;
                            return (
                              <div className="landscape-phase-summary" key={phase.phase}>
                                <strong>{phaseName}</strong>
                                <span>{sender} → {receiver}</span>
                                <span>{phase.configured ? validationLabel(
                                  summary.errorCount ? "errors"
                                    : summary.warningCount ? "warnings"
                                      : summary.status === "Incomplete" || summary.incompleteMappingCount
                                        ? "incomplete" : "valid",
                                ) : "Unconfigured"}</span>
                                {(summary.errorCount > 0 || summary.warningCount > 0 || summary.incompleteMappingCount > 0) && (
                                  <small>
                                    {summary.errorCount ? `${summary.errorCount} errors` : ""}
                                    {summary.errorCount && summary.warningCount ? " · " : ""}
                                    {summary.warningCount ? `${summary.warningCount} warnings` : ""}
                                    {summary.incompleteMappingCount ? ` · ${summary.incompleteMappingCount} incomplete mappings` : ""}
                                  </small>
                                )}
                              </div>
                            );
                          })}
                        </div>
                        {validationMessages.length > 0 && (
                          <ul className="landscape-contract-diagnostics">
                            {validationMessages.map((message) => <li key={message}>{message}</li>)}
                          </ul>
                        )}
                        {diagnostics.length > 0 && (
                          <ul className="landscape-contract-diagnostics">
                            {diagnostics.map((item, index) => (
                              <li key={`${item.phase ?? "contract"}:${index}`}>
                                {item.issue?.severity}: {item.message}
                              </li>
                            ))}
                          </ul>
                        )}
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => onOpenIntegration(contract.id)}
                        >
                          Open contract
                        </button>
                      </section>
                    );
                  })}
                </div>
              </aside>
            )}
            {selectedIntegration && hybridMode && (
              <FieldMappingDrawer
                integration={selectedIntegration}
                sourceSystemName={sourceSystemName}
                targetSystemName={targetSystemName}
                sourceFields={mappingSourceFields}
                targetFields={mappingTargetFields}
                simulation={mappingSimulation}
                loading={mappingLoading}
                error={mappingError}
                onClose={closeMappingDrawer}
                onOpenMapper={() => onOpenIntegration(selectedIntegration.id)}
              />
            )}
          </div>
          {hybridMode && integrations.length > 0 && (
            <details className="landscape-summary">
              <summary>
                <span>Contract summary</span>
                <small>
                  {integrations.length} {integrations.length === 1 ? "contract" : "contracts"}
                  {" · "}
                  {architecture.conflicts.length} validation {architecture.conflicts.length === 1 ? "issue" : "issues"}
                </small>
              </summary>
              <div className="landscape-integration-list">
                <h3>Contracts</h3>
                <div className="landscape-integration-cards">
                {integrations.map((integration) => (
                  <button
                    type="button"
                    className="landscape-integration-card"
                    key={integration.id}
                    onClick={() => onOpenIntegration(integration.id)}
                  >
                    <span className={`integration-status-dot ${architectureById.get(integration.id)?.status ?? "draft"}`} />
                    <span className="landscape-integration-copy">
                      <strong>{integration.name}</strong>
                      <small>
                        {objects.get(integration.source_object_id)?.label ?? "Source object"}
                        {" → "}
                        {objects.get(integration.target_object_id)?.label ?? "Target object"}
                        {architectureById.get(integration.id)?.reasons[0]
                          ? ` · ${designValidationReason(architectureById.get(integration.id)?.reasons[0] ?? "")}`
                          : ""}
                      </small>
                    </span>
                    <span className="integration-card-meta">
                      {designStatusLabel(architectureById.get(integration.id)?.status ?? "draft")}
                      {" · "}{integration.sample_rows.length} samples
                      {architectureById.get(integration.id)?.conflict_fields.length
                        ? ` · ${architectureById.get(integration.id)?.conflict_fields.length} validation issues`
                        : ""}
                    </span>
                    <span aria-hidden="true">›</span>
                  </button>
                ))}
                </div>
              </div>
              {architecture.conflicts.length > 0 && (
                <section className="landscape-conflicts" aria-label="Target field validation issues">
              <h3>Target field validation issues</h3>
              <p>Multiple contracts map to the same target field.</p>
              <ul>
                {architecture.conflicts.map((conflict) => (
                  <li key={`${conflict.object_id}:${conflict.field_id}`}>
                    <span><strong>{conflict.object_label} · {conflict.field_label}</strong></span>
                    <span className="conflict-integration-links">
                      {conflict.integrations.map((item) => (
                        <button type="button" key={item.id} onClick={() => onOpenIntegration(item.id)}>
                          {item.name}
                        </button>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
                </section>
              )}
            </details>
          )}
        </>
      )}
    </section>
  );
}
