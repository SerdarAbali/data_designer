import React from "react";
import CatalogInspector from "./components/catalog/CatalogInspector";
import ArchitectureCanvas from "./ArchitectureCanvas";
import IntegrationWorkspace from "./IntegrationWorkspace";
import type { ScenarioPhase } from "./scenarioModel";
import WorkspaceSwitcher from "./components/workspaces/WorkspaceSwitcher";
import type { WorkspaceInfo } from "./architectureTypes";
import ArchiveImpactDialog, { type ReferencingIntegration } from "./components/catalog/ArchiveImpactDialog";
import ArchitectureImportDialog from "./components/import/ArchitectureImportDialog";
import type { NavigationGuard } from "./contextSaveQueue";
import useStudioTheme from "./useStudioTheme";
import { ApiError, api, csrfToken, list } from "./apiClient";
import { AssistantLauncher, AssistantPanel } from "./assistant/AssistantPanel";
import {
  DEFAULT_CANVAS_SCOPE,
  resolveAssistantScope,
  type CanvasScope,
} from "./assistant/assistantModel";

type System = {
  id: string;
  name: string;
  kind: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  position: { x: number; y: number } | null;
  metadata: Record<string, unknown>;
};

type CatalogObject = {
  id: string;
  system_id: string;
  name: string;
  label: string;
  description: string | null;
  external_identifier: string | null;
  origin: string;
  position: number;
  metadata: Record<string, unknown>;
};

type CatalogField = {
  id: string;
  object_id: string;
  name: string;
  label: string;
  description: string | null;
  data_type: string;
  required: boolean;
  nullable: boolean;
  default_value: unknown;
  external_identifier: string | null;
  position: number;
  origin: string;
  metadata: Record<string, unknown>;
};

type Props = {
  onLogout: () => void;
  email: string;
  tenantName: string;
  loggingOut: boolean;
};

type CatalogModal = "object" | "field" | null;

function ReorderButtons({
  disabled,
  onMove,
}: {
  disabled: boolean;
  onMove: (direction: -1 | 1) => void;
}) {
  return (
    <span className="reorder-buttons">
      <button type="button" className="quiet-button" disabled={disabled} onClick={() => onMove(-1)}>Move up</button>
      <button type="button" className="quiet-button" disabled={disabled} onClick={() => onMove(1)}>Move down</button>
    </span>
  );
}

function objectMetadata(value: FormDataEntryValue | null): Record<string, unknown> {
  const text = String(value ?? "{}").trim() || "{}";
  const parsed: unknown = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Metadata must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

function valueOrNull(value: FormDataEntryValue | null): string | null {
  const result = String(value ?? "").trim();
  return result || null;
}

function jsonDefault(value: FormDataEntryValue | null): unknown {
  const text = String(value ?? "").trim();
  return text ? JSON.parse(text) : null;
}

function toFormData(event: React.FormEvent<HTMLFormElement>): FormData {
  event.preventDefault();
  return new FormData(event.currentTarget);
}

function metadataText(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

function ErrorNotice({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p className="error catalog-error" role="alert">
      {message}
    </p>
  );
}

export default function CatalogWorkspace({
  onLogout,
  email,
  tenantName,
  loggingOut,
}: Props) {
  const { theme, toggleTheme } = useStudioTheme();
  const [transitioning, setTransitioning] = React.useState(false);
  const [studioSearch, setStudioSearch] = React.useState("");
  const canvasGuard = React.useRef<NavigationGuard>(async () => true);
  const contractGuard = React.useRef<NavigationGuard>(async () => true);
  const registerCanvasGuard = React.useCallback((guard: NavigationGuard) => {
    canvasGuard.current = guard;
  }, []);
  const registerContractGuard = React.useCallback((guard: NavigationGuard) => {
    contractGuard.current = guard;
  }, []);
  const [activeView, setActiveView] = React.useState<"canvas" | "catalog" | "integrations">("canvas");
  const [assistantOpen, setAssistantOpen] = React.useState(false);
  const [assistantScope, setAssistantScope] = React.useState<CanvasScope>(DEFAULT_CANVAS_SCOPE);
  const [architectureRefreshToken, setArchitectureRefreshToken] = React.useState(0);
  const [appliedHighlights, setAppliedHighlights] = React.useState<string[]>([]);
  const [architectureStates, setArchitectureStates] = React.useState<
    { id: string; name: string; state_type: string }[]
  >([]);
  const [activeWorkspace, setActiveWorkspace] = React.useState<WorkspaceInfo | null>(null);
  const [integrationToOpen, setIntegrationToOpen] = React.useState("");
  const [integrationPhaseToOpen, setIntegrationPhaseToOpen] = React.useState<
    ScenarioPhase | "scenarios" | undefined
  >();
  const [quickAddSystemId, setQuickAddSystemId] = React.useState("");
  const [catalogSearch, setCatalogSearch] = React.useState("");
  const [expandedSystemId, setExpandedSystemId] = React.useState("");
  const [expandedObjectId, setExpandedObjectId] = React.useState("");
  const [catalogTreeWidth, setCatalogTreeWidth] = React.useState(300);
  const [catalogModal, setCatalogModal] = React.useState<CatalogModal>(null);
  const [systems, setSystems] = React.useState<System[]>([]);
  const [objects, setObjects] = React.useState<CatalogObject[]>([]);
  const [objectFieldCounts, setObjectFieldCounts] = React.useState<Record<string, number>>({});
  const [fields, setFields] = React.useState<CatalogField[]>([]);
  const [systemId, setSystemId] = React.useState("");
  const [objectId, setObjectId] = React.useState("");
  const [fieldId, setFieldId] = React.useState("");
  const [loadingSystems, setLoadingSystems] = React.useState(true);
  const [loadingObjects, setLoadingObjects] = React.useState(false);
  const [loadingFields, setLoadingFields] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [importOpen, setImportOpen] = React.useState(false);
  const [importNotice, setImportNotice] = React.useState("");
  const [archiveImpactState, setArchiveImpactState] = React.useState<{
    path: string;
    itemName: string;
    itemType: "system" | "object" | "field";
    integrations: ReferencingIntegration[];
    refresh: () => Promise<void>;
  } | null>(null);
  const [archiveCascading, setArchiveCascading] = React.useState(false);
  const systemsRequest = React.useRef(0);
  const objectsRequest = React.useRef(0);
  const fieldsRequest = React.useRef(0);
  const workspaceRequest = React.useRef(0);
  const catalogMutation = React.useRef<Promise<boolean> | null>(null);
  const selectedSystem = systems.find((system) => system.id === systemId) ?? null;
  const selectedObject = objects.find((object) => object.id === objectId) ?? null;
  const selectedField = fields.find((field) => field.id === fieldId) ?? null;

  const refreshSystems = React.useCallback(async (preferId?: string) => {
    const requestId = ++systemsRequest.current;
    setLoadingSystems(true);
    try {
      const nextSystems = await list<System>("/api/catalog/systems");
      if (requestId !== systemsRequest.current) return;
      setSystems(nextSystems);
      setExpandedSystemId((current) =>
        current && nextSystems.some((system) => system.id === current)
          ? current
          : preferId || nextSystems[0]?.id || "",
      );
      setSystemId((current) => {
        const wanted = preferId ?? current;
        return nextSystems.some((system) => system.id === wanted)
          ? wanted
          : (nextSystems[0]?.id ?? "");
      });
    } catch (caught) {
      if (requestId === systemsRequest.current) {
        setError(caught instanceof Error ? caught.message : "Could not load systems.");
      }
    } finally {
      if (requestId === systemsRequest.current) setLoadingSystems(false);
    }
  }, []);

  const refreshWorkspace = React.useCallback(async () => {
    const requestId = ++workspaceRequest.current;
    try {
      const workspaces = await list<WorkspaceInfo>("/api/workspaces");
      if (requestId !== workspaceRequest.current) return;
      const active = workspaces.find((w) => w.is_active) ?? workspaces[0] ?? null;
      setActiveWorkspace(active);
    } catch (err) {
      if (requestId === workspaceRequest.current) {
        setError(err instanceof Error ? err.message : "Could not load the workspace.");
        throw err;
      }
    }
  }, []);

  React.useEffect(() => {
    void refreshWorkspace().catch(() => {});
  }, [refreshWorkspace]);

  React.useEffect(() => {
    const workspaceId = activeWorkspace?.id;
    if (!workspaceId) {
      setArchitectureStates([]);
      return;
    }
    let cancelled = false;
    void list<{ id: string; name: string; state_type: string }>(
      `/api/workspaces/${workspaceId}/states`,
    )
      .then((states) => {
        if (!cancelled) setArchitectureStates(states);
      })
      .catch(() => {
        if (!cancelled) setArchitectureStates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace?.id, architectureRefreshToken]);

  React.useEffect(() => {
    setAppliedHighlights([]);
  }, [activeWorkspace?.id]);

  const refreshObjects = React.useCallback(async (currentSystemId: string, preferId?: string) => {
    const requestId = ++objectsRequest.current;
    if (!currentSystemId) {
      setObjects([]);
      setObjectId("");
      setLoadingObjects(false);
      return;
    }
    setLoadingObjects(true);
    try {
      const nextObjects = await list<CatalogObject>(
        `/api/catalog/systems/${currentSystemId}/objects`,
      );
      if (requestId !== objectsRequest.current) return;
      setObjects(nextObjects);
      const counts = await Promise.all(nextObjects.map(async (object) => [
        object.id,
        (await list<CatalogField>(`/api/catalog/objects/${object.id}/fields`)).length,
      ] as const));
      if (requestId !== objectsRequest.current) return;
      setObjectFieldCounts(Object.fromEntries(counts));
      setObjectId((current) =>
        preferId && nextObjects.some((object) => object.id === preferId)
          ? preferId
          : nextObjects.some((object) => object.id === current) ? current : "",
      );
    } catch (caught) {
      if (requestId === objectsRequest.current) {
        setError(caught instanceof Error ? caught.message : "Could not load objects.");
      }
    } finally {
      if (requestId === objectsRequest.current) setLoadingObjects(false);
    }
  }, []);

  const refreshFields = React.useCallback(async (currentObjectId: string, preferId?: string) => {
    const requestId = ++fieldsRequest.current;
    if (!currentObjectId) {
      setFields([]);
      setFieldId("");
      setLoadingFields(false);
      return;
    }
    setLoadingFields(true);
    try {
      const nextFields = await list<CatalogField>(
        `/api/catalog/objects/${currentObjectId}/fields`,
      );
      if (requestId !== fieldsRequest.current) return;
      setFields(nextFields);
      setFieldId((current) =>
        preferId && nextFields.some((field) => field.id === preferId)
          ? preferId
          : nextFields.some((field) => field.id === current) ? current : "",
      );
    } catch (caught) {
      if (requestId === fieldsRequest.current) {
        setError(caught instanceof Error ? caught.message : "Could not load fields.");
      }
    } finally {
      if (requestId === fieldsRequest.current) setLoadingFields(false);
    }
  }, []);

  React.useEffect(() => {
    void refreshSystems();
  }, [refreshSystems]);

  React.useEffect(() => {
    setObjects([]);
    setObjectFieldCounts({});
    setObjectId("");
    setFields([]);
    setFieldId("");
    void refreshObjects(systemId);
  }, [systemId, refreshObjects]);

  React.useEffect(() => {
    setFields([]);
    setFieldId("");
    void refreshFields(objectId);
  }, [objectId, refreshFields]);

  async function runMutation(action: () => Promise<void>): Promise<boolean> {
    setError("");
    setSaving(true);
    const operation = (async () => {
      try {
        await action();
        return true;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The change could not be saved.");
        return false;
      } finally {
        setSaving(false);
      }
    })();
    catalogMutation.current = operation;
    return operation;
  }

  async function beforeNavigate() {
    if (catalogMutation.current && !await catalogMutation.current) return false;
    if (!await canvasGuard.current()) return false;
    return contractGuard.current();
  }

  async function navigate(view: typeof activeView) {
    if (view === activeView || transitioning) return;
    if (await beforeNavigate()) setActiveView(view);
  }

  async function switchWorkspace() {
    ++systemsRequest.current;
    ++objectsRequest.current;
    ++fieldsRequest.current;
    setSystems([]);
    setObjects([]);
    setFields([]);
    setObjectFieldCounts({});
    setSystemId("");
    setObjectId("");
    setFieldId("");
    setExpandedSystemId("");
    setExpandedObjectId("");
    setIntegrationToOpen("");
    setIntegrationPhaseToOpen(undefined);
    setQuickAddSystemId("");
    setCatalogModal(null);
    setArchiveImpactState(null);
    setError("");
    setActiveView("canvas");
    catalogMutation.current = null;
    await refreshWorkspace();
    await refreshSystems();
  }

  async function exportWorkspace() {
    if (!activeWorkspace) return;
    if (!await beforeNavigate()) return;
    await runMutation(async () => {
      const bundle = await api<object>(`/api/workspaces/${activeWorkspace.id}/export`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${activeWorkspace.name.replace(/[^a-z0-9]/gi, "_")}.dd.json`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  async function createSystem(event: React.FormEvent<HTMLFormElement>) {
    const formElement = event.currentTarget;
    const form = toFormData(event);
    const succeeded = await runMutation(async () => {
      const created = await api<System>("/api/catalog/systems", {
        method: "POST",
        body: JSON.stringify({
          name: String(form.get("name") ?? ""),
          kind: String(form.get("kind") ?? ""),
        }),
      });
      await refreshSystems(created.id);
    });
    if (succeeded) formElement.reset();
  }

  async function saveSystem(event: React.FormEvent<HTMLFormElement>) {
    const form = toFormData(event);
    if (!selectedSystem) return;
    await runMutation(async () => {
      // Position X/Y are hidden from the compact system editor; keep the
      // landscape position unless an explicit catalog-purpose field supplies it.
      const rawX = form.get("x");
      const rawY = form.get("y");
      const x = Number(rawX);
      const y = Number(rawY);
      const position = rawX !== null && rawY !== null && Number.isFinite(x) && Number.isFinite(y)
        ? { x, y }
        : selectedSystem.position ?? { x: 0, y: 0 };
      await api<System>(`/api/catalog/systems/${selectedSystem.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: String(form.get("name") ?? ""),
          kind: String(form.get("kind") ?? ""),
          description: valueOrNull(form.get("description")),
          icon: valueOrNull(form.get("icon")),
          color: valueOrNull(form.get("color")),
          position,
          metadata: objectMetadata(form.get("metadata")),
        }),
      });
      await refreshSystems(selectedSystem.id);
    });
  }

  async function createObject(event: React.FormEvent<HTMLFormElement>) {
    const formElement = event.currentTarget;
    const form = toFormData(event);
    if (!selectedSystem) return;
    const succeeded = await runMutation(async () => {
      const created = await api<CatalogObject>(
        `/api/catalog/systems/${selectedSystem.id}/objects`,
        {
          method: "POST",
          body: JSON.stringify({
            name: String(form.get("name") ?? ""),
            label: String(form.get("label") || form.get("name") || ""),
            description: valueOrNull(form.get("description")),
            metadata: objectMetadata(form.get("metadata")),
          }),
        },
      );
      await refreshObjects(selectedSystem.id, created.id);
      setExpandedSystemId(selectedSystem.id);
      setExpandedObjectId(created.id);
      setFieldId("");
    });
    if (succeeded) {
      formElement.reset();
      setCatalogModal(null);
    }
  }

  async function saveObject(event: React.FormEvent<HTMLFormElement>) {
    const form = toFormData(event);
    if (!selectedObject) return;
    const succeeded = await runMutation(async () => {
      await api<CatalogObject>(`/api/catalog/objects/${selectedObject.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: String(form.get("name") ?? ""),
          label: String(form.get("label") || form.get("name") || ""),
          description: valueOrNull(form.get("description")),
          external_identifier: valueOrNull(form.get("external_identifier")),
          position: Number(form.get("position")),
          metadata: objectMetadata(form.get("metadata")),
        }),
      });
      await refreshObjects(selectedObject.system_id);
    });
  }

  async function createField(event: React.FormEvent<HTMLFormElement>) {
    const formElement = event.currentTarget;
    const form = toFormData(event);
    if (!selectedObject) return;
    const succeeded = await runMutation(async () => {
      const created = await api<CatalogField>(
        `/api/catalog/objects/${selectedObject.id}/fields`,
        {
          method: "POST",
          body: JSON.stringify({
            name: String(form.get("name") ?? ""),
            label: String(form.get("label") || form.get("name") || ""),
            data_type: String(form.get("data_type") ?? ""),
            required: form.get("required") === "on",
            nullable: form.get("nullable") === "on" || !form.has("nullable"),
            default_value: jsonDefault(form.get("default_value")),
            description: valueOrNull(form.get("description")),
            external_identifier: valueOrNull(form.get("external_identifier")),
            metadata: objectMetadata(form.get("metadata")),
          }),
        },
      );
      await refreshFields(selectedObject.id, created.id);
      setExpandedObjectId(selectedObject.id);
    });
    if (succeeded) {
      formElement.reset();
      setCatalogModal(null);
    }
  }

  async function saveField(event: React.FormEvent<HTMLFormElement>) {
    const form = toFormData(event);
    if (!selectedField) return;
    await runMutation(async () => {
      await api<CatalogField>(`/api/catalog/fields/${selectedField.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: String(form.get("name") ?? ""),
          label: String(form.get("label") ?? ""),
          data_type: String(form.get("data_type") ?? ""),
          required: form.get("required") === "on",
          nullable: form.get("nullable") === "on",
          default_value: jsonDefault(form.get("default_value")),
          description: valueOrNull(form.get("description")),
          external_identifier: valueOrNull(form.get("external_identifier")),
          position: Number(form.get("position")),
          origin: String(form.get("origin") ?? "manual"),
          metadata: objectMetadata(form.get("metadata")),
        }),
      });
      await refreshFields(selectedField.object_id);
    });
  }

  async function archiveItem(
    path: string,
    itemName: string,
    refresh: () => Promise<void>,
    itemType: "system" | "object" | "field" = "system",
  ) {
    if (!window.confirm(`Archive ${itemName}? It can be restored through the API.`)) return;
    setError("");
    setSaving(true);
    try {
      await api<void>(path, { method: "DELETE" });
      await refresh();
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        caught.status === 409 &&
        caught.detail &&
        typeof caught.detail === "object" &&
        (caught.detail as { code?: string }).code === "catalog_item_in_use"
      ) {
        const rawDetail = caught.detail as {
          code: string;
          message: string;
          integrations: ReferencingIntegration[];
        };
        setArchiveImpactState({
          path,
          itemName,
          itemType,
          integrations: rawDetail.integrations ?? [],
          refresh,
        });
      } else {
        setError(caught instanceof Error ? caught.message : "Archive failed.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function reorder(
    items: { id: string; position: number }[],
    index: number,
    direction: -1 | 1,
    pathForId: (id: string) => string,
    refresh: () => Promise<void>,
  ) {
    const otherIndex = index + direction;
    if (otherIndex < 0 || otherIndex >= items.length) return;
    const current = items[index];
    const other = items[otherIndex];
    await runMutation(async () => {
      try {
        await api(pathForId(current.id), {
          method: "PATCH",
          body: JSON.stringify({ position: other.position }),
        });
        await api(pathForId(other.id), {
          method: "PATCH",
          body: JSON.stringify({ position: current.position }),
        });
      } finally {
        await refresh();
      }
    });
  }

  function startCatalogResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = catalogTreeWidth;
    const move = (moveEvent: PointerEvent) => {
      const next = Math.min(480, Math.max(220, startWidth + moveEvent.clientX - startX));
      setCatalogTreeWidth(next);
    };
    const finish = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
  }

  const assistantViewScope = resolveAssistantScope(assistantScope, activeView);

  return (
    <main className={`workspace studio-workspace view-${activeView}`} aria-busy={transitioning}>
      <header className="workspace-header">
        <button type="button" className="studio-home" aria-label="Home - architecture canvas" title="Data Designer" onClick={() => void navigate("canvas")}>D</button>
          <WorkspaceSwitcher
            currentWorkspaceName={activeWorkspace?.name ?? tenantName}
            csrfToken={csrfToken}
            beforeSwitch={beforeNavigate}
            onTransitionChange={setTransitioning}
            onSwitch={switchWorkspace}
            onDisciplinesUpdated={() => {
              void refreshWorkspace().catch(() => {});
            }}
          />
          <nav className="workspace-nav" aria-label="Workspace">
            <button
              type="button"
              className={activeView === "canvas" ? "nav-tab active" : "nav-tab"}
              aria-pressed={activeView === "canvas"}
              onClick={() => void navigate("canvas")}
            >
              Canvas
            </button>
            {(!activeWorkspace || activeWorkspace.disciplines.includes("integration")) && (
              <button
                type="button"
                className={activeView === "integrations" ? "nav-tab active" : "nav-tab"}
                aria-pressed={activeView === "integrations"}
                onClick={() => {
                  setQuickAddSystemId("");
                  void navigate("integrations");
                }}
              >
                Contracts
              </button>
            )}
            {(!activeWorkspace || activeWorkspace.disciplines.some((d) => d === "enterprise" || d === "information")) && (
              <button
                type="button"
                className={activeView === "catalog" ? "nav-tab active" : "nav-tab"}
                aria-pressed={activeView === "catalog"}
                onClick={() => void navigate("catalog")}
              >
                Catalog
              </button>
            )}
          </nav>
          <label className="studio-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" aria-label="Search workspace" placeholder={activeView === "canvas" ? "Find on canvas…" : activeView === "integrations" ? "Find contract…" : "Search catalog…"} value={studioSearch} onChange={(event) => {
              setStudioSearch(event.target.value);
              setCatalogSearch(event.target.value);
            }} />
          </label>
          <button type="button" className="studio-icon-button" aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} onClick={toggleTheme}>{theme === "light" ? "☾" : "☀"}</button>
          <AssistantLauncher open={assistantOpen} onOpen={() => setAssistantOpen(true)} />
          <button type="button" className="studio-share" onClick={() => void exportWorkspace()} disabled={saving || transitioning || !activeWorkspace} title="Export this workspace as a shareable bundle">Share</button>
          <details className="workspace-account">
            <summary aria-label="Account menu">
              <span className="account-avatar" aria-hidden="true">{email.slice(0, 1).toUpperCase()}</span>
              <span>{email}<small>{tenantName}</small></span>
              <span className="account-chevron" aria-hidden="true">⌄</span>
            </summary>
            <div className="account-menu">
              <strong>{email}</strong>
              <small>{tenantName} · Internal workspace</small>
              <button type="button" className="secondary-button" onClick={onLogout} disabled={loggingOut}>
                {loggingOut ? "Signing out…" : "Sign out"}
              </button>
            </div>
          </details>
      </header>

      {error && activeView !== "catalog" && <ErrorNotice message={error} />}
      <div className="studio-canvas-host" hidden={activeView !== "canvas"}>
        <ArchitectureCanvas
          key={activeWorkspace?.id ?? "loading"}
          workspace={activeWorkspace}
          visible={activeView === "canvas"}
          refreshToken={architectureRefreshToken}
          highlightObjectIds={appliedHighlights}
          onAssistantScopeChange={setAssistantScope}
          search={activeView === "canvas" ? studioSearch : ""}
          registerNavigationGuard={registerCanvasGuard}
          onOpenCatalog={() => void navigate("catalog")}
          onAddIntegration={(systemId) => {
            void beforeNavigate().then((allowed) => {
              if (!allowed) return;
              setQuickAddSystemId(systemId);
              setIntegrationToOpen("");
              setIntegrationPhaseToOpen(undefined);
              setActiveView("integrations");
            });
          }}
          onOpenIntegration={(id, phase) => {
            void beforeNavigate().then((allowed) => {
              if (!allowed) return;
              setQuickAddSystemId("");
              setIntegrationToOpen(id);
              setIntegrationPhaseToOpen(phase);
              setActiveView("integrations");
            });
          }}
        />
      </div>
      {activeView === "integrations" ? (
        <IntegrationWorkspace
          key={activeWorkspace?.id}
          registerNavigationGuard={registerContractGuard}
          search={studioSearch}
          onBack={() => void navigate("canvas")}
          initialIntegrationId={quickAddSystemId ? undefined : integrationToOpen || undefined}
          initialContractView={quickAddSystemId ? undefined : integrationPhaseToOpen}
          newIntegrationSystemId={quickAddSystemId || undefined}
        />
      ) : activeView === "canvas" ? null : (
      <>
      <ErrorNotice message={error} />

      <div
        className="catalog-grid"
        style={{ gridTemplateColumns: `${catalogTreeWidth}px 10px minmax(0, 1fr)` }}
      >
        <section className="catalog-panel systems-panel" aria-labelledby="systems-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CATALOG</p>
              <h2 id="systems-heading">Systems</h2>
            </div>
            <span className="item-count">{systems.length}</span>
          </div>
          <div className="import-entry">
            <button
              type="button"
              className="secondary-button"
              disabled={!activeWorkspace}
              onClick={() => {
                setImportNotice("");
                setImportOpen(true);
              }}
            >
              Import from Excel or CSV
            </button>
            {importNotice && (
              <p role="status" className="muted">
                {importNotice}
              </p>
            )}
          </div>
          <label className="catalog-search">
            <span className="sr-only">Filter catalog tree</span>
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={catalogSearch}
              onChange={(event) => setCatalogSearch(event.target.value)}
              placeholder="Search systems, objects, fields"
            />
          </label>
          <details className="add-system">
            <summary><span aria-hidden="true">＋</span> Add system</summary>
            <form className="compact-form" onSubmit={createSystem}>
              <label>
                Name
                <input name="name" required maxLength={160} placeholder="e.g. Billing platform" />
              </label>
              <label>
                Kind
                <input name="kind" required maxLength={100} defaultValue="application" />
              </label>
              <button type="submit" disabled={saving}>{saving ? "Adding…" : "Create system"}</button>
            </form>
          </details>
          {loadingSystems ? (
            <p className="muted" role="status">Loading systems…</p>
          ) : systems.length === 0 ? (
            <p className="empty-state">No systems yet. Create any system to get started.</p>
          ) : (
            <ul className="catalog-tree">
              {systems.filter((system) => {
                const query = catalogSearch.trim().toLowerCase();
                if (!query) return true;
                if (`${system.name} ${system.kind}`.toLowerCase().includes(query)) return true;
                if (system.id !== systemId) return false;
                return objects.some((object) =>
                  `${object.name} ${object.label}`.toLowerCase().includes(query)
                  || (object.id === objectId && fields.some((field) =>
                    `${field.name} ${field.label} ${field.data_type}`.toLowerCase().includes(query),
                  )),
                );
              }).map((system) => (
                <li key={system.id}>
                  <div className={`tree-row${system.id === systemId ? " selected" : ""}`}>
                    <button
                      type="button"
                      className="tree-toggle"
                      aria-label={`${expandedSystemId === system.id ? "Collapse" : "Expand"} ${system.name}`}
                      aria-expanded={expandedSystemId === system.id && system.id === systemId}
                      onClick={() => {
                        setSystemId(system.id);
                        setObjectId("");
                        setFieldId("");
                        setExpandedObjectId("");
                        setExpandedSystemId((current) => current === system.id ? "" : system.id);
                      }}
                    >
                      <span className="tree-chevron" aria-hidden="true">
                        {expandedSystemId === system.id || system.id === systemId ? "⌄" : "›"}
                      </span>
                      <span className="system-swatch" style={{ backgroundColor: system.color || "#527ca4" }}>
                        {system.icon || system.name.slice(0, 1).toUpperCase()}
                      </span>
                      <span className="list-copy"><strong>{system.name}</strong><small>{system.kind}</small></span>
                    </button>
                  </div>
                  {expandedSystemId === system.id && system.id === systemId && (
                    <ul className="tree-children">
                      {objects.filter((object) => object.system_id === system.id).filter((object) => {
                        const query = catalogSearch.trim().toLowerCase();
                        return !query
                          || `${object.name} ${object.label}`.toLowerCase().includes(query)
                          || (object.id === objectId && fields.some((field) =>
                            `${field.name} ${field.label} ${field.data_type}`.toLowerCase().includes(query),
                          ));
                      }).map((object) => (
                        <li key={object.id}>
                          <button
                            type="button"
                            className={`tree-entity${object.id === objectId ? " selected" : ""}`}
                            onClick={() => {
                              setObjectId(object.id);
                              setFieldId("");
                              setExpandedSystemId(system.id);
                              setExpandedObjectId(object.id);
                            }}
                          >
                            <span aria-hidden="true">▦</span>{object.label}
                          </button>
                          {object.id === objectId && expandedObjectId === object.id && (
                            <ul className="tree-children field-tree">
                              {fields.filter((field) => {
                                const query = catalogSearch.trim().toLowerCase();
                                return !query || `${field.name} ${field.label} ${field.data_type}`.toLowerCase().includes(query);
                              }).map((field) => (
                                <li key={field.id}>
                                  <button
                                    type="button"
                                    className={`tree-entity${field.id === fieldId ? " selected" : ""}`}
                                    onClick={() => setFieldId(field.id)}
                                  >
                                    <span className="tree-field-mark" aria-hidden="true">•</span>
                                    <span>{field.label}</span><small>{field.data_type}</small>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <div
          className="catalog-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize catalog tree"
          onPointerDown={startCatalogResize}
        />

        <CatalogInspector
          key={fieldId || objectId || systemId || "catalog"}
          workspaceId={activeWorkspace?.id ?? ""}
          system={!objectId ? selectedSystem : null}
          object={objectId && !fieldId ? selectedObject : null}
          field={fieldId ? selectedField : null}
          objects={objects}
          fields={fields}
          fieldCounts={objectFieldCounts}
          loadingObjects={loadingObjects}
          loadingFields={loadingFields}
          saving={saving}
          onSaveSystem={saveSystem}
          onSaveObject={saveObject}
          onSaveField={saveField}
          onCreateObject={createObject}
          onCreateField={createField}
          onSelectObject={(id) => {
            setObjectId(id);
            setFieldId("");
            setExpandedObjectId(id);
          }}
          onSelectField={setFieldId}
          onAddObject={() => setCatalogModal("object")}
          onAddField={() => setCatalogModal("field")}
          modal={catalogModal}
          onCloseModal={() => setCatalogModal(null)}
          onArchive={(kind) => {
            if (kind === "system" && selectedSystem) {
              void archiveItem(`/api/catalog/systems/${selectedSystem.id}`, selectedSystem.name, () => refreshSystems(), "system");
            } else if (kind === "object" && selectedObject) {
              void archiveItem(`/api/catalog/objects/${selectedObject.id}`, selectedObject.label, () => refreshObjects(selectedSystem?.id ?? ""), "object");
            } else if (kind === "field" && selectedField) {
              void archiveItem(`/api/catalog/fields/${selectedField.id}`, selectedField.label, () => refreshFields(selectedObject?.id ?? ""), "field");
            }
          }}
        />
      </div>
      </>
      )}
      {archiveImpactState && (
        <ArchiveImpactDialog
          itemName={archiveImpactState.itemName}
          itemType={archiveImpactState.itemType}
          integrations={archiveImpactState.integrations}
          loading={archiveCascading}
          onCancel={() => setArchiveImpactState(null)}
          onOpenIntegration={(id) => {
            setArchiveImpactState(null);
            setIntegrationToOpen(id);
            setIntegrationPhaseToOpen(undefined);
            setQuickAddSystemId("");
            setActiveView("integrations");
          }}
          onConfirmCascade={async () => {
            setArchiveCascading(true);
            try {
              await api<void>(`${archiveImpactState.path}?cascade=true`, { method: "DELETE" });
              await archiveImpactState.refresh();
              setArchiveImpactState(null);
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : "Cascade archive failed.");
              setArchiveImpactState(null);
            } finally {
              setArchiveCascading(false);
            }
          }}
        />
      )}
      {importOpen && activeWorkspace && (
        <ArchitectureImportDialog
          workspaceId={activeWorkspace.id}
          onClose={() => setImportOpen(false)}
          onCommitted={(message) => {
            setImportNotice(message);
            void refreshSystems();
          }}
          onOpenCanvas={() => {
            setImportOpen(false);
            void navigate("canvas");
          }}
        />
      )}
      <AssistantPanel
        workspaceId={activeWorkspace?.id ?? null}
        workspaceName={activeWorkspace?.name ?? tenantName}
        disciplines={activeWorkspace?.disciplines ?? []}
        discipline={assistantViewScope.discipline}
        states={architectureStates}
        stateId={assistantViewScope.stateId}
        workbenchView={assistantViewScope.workbenchView}
        selectionIds={assistantViewScope.selectionIds}
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        onProposalApplied={(result) => {
          setAppliedHighlights(result.affected_objects);
          setArchitectureRefreshToken((value) => value + 1);
        }}
        onProposalUndone={() => {
          setAppliedHighlights([]);
          setArchitectureRefreshToken((value) => value + 1);
        }}
        onProposalHighlightsCleared={() => setAppliedHighlights([])}
      />
    </main>
  );
}
