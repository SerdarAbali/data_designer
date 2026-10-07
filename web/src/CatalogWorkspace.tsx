import React from "react";
import CatalogInspector from "./components/catalog/CatalogInspector";
import InspectorTabs, { type InspectorTab } from "./components/catalog/InspectorTabs";
import EnterpriseLandscape from "./EnterpriseLandscape";
import IntegrationWorkspace from "./IntegrationWorkspace";
import type { ScenarioPhase } from "./scenarioModel";
import WorkspaceSwitcher from "./components/workspaces/WorkspaceSwitcher";
import ArchiveImpactDialog, { type ReferencingIntegration } from "./components/catalog/ArchiveImpactDialog";

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

class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
  }
}

function csrfToken(): string {
  const token = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("dd_csrf="))
    ?.slice("dd_csrf=".length);
  if (!token) {
    throw new Error("Your session could not be verified. Reload and try again.");
  }
  return decodeURIComponent(token);
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((issue) => {
        if (issue && typeof issue === "object" && "msg" in issue) {
          return String(issue.msg);
        }
        return JSON.stringify(issue);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    const record = detail as {
      message?: unknown;
      code?: unknown;
      integrations?: { name?: string }[];
    };
    const message =
      typeof record.message === "string"
        ? record.message
        : typeof record.code === "string"
          ? record.code
          : JSON.stringify(detail);
    if (record.integrations?.length) {
      return `${message}: ${record.integrations.map((item) => item.name ?? "contract").join(", ")}`;
    }
    return message;
  }
  return "The request could not be completed.";
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiRequestError(detailMessage(body.detail), response.status, body.detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function apiList<T>(path: string): Promise<T[]> {
  const records: T[] = [];
  let offset = 0;
  while (true) {
    const page = await api<T[]>(`${path}?limit=500&offset=${offset}`);
    records.push(...page);
    if (page.length < 500) return records;
    offset += page.length;
  }
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
  const [activeView, setActiveView] = React.useState<"catalog" | "integrations" | "landscape">("catalog");
  const [integrationToOpen, setIntegrationToOpen] = React.useState("");
  const [integrationPhaseToOpen, setIntegrationPhaseToOpen] = React.useState<ScenarioPhase | undefined>();
  const [quickAddSystemId, setQuickAddSystemId] = React.useState("");
  const [catalogSearch, setCatalogSearch] = React.useState("");
  const [expandedSystemId, setExpandedSystemId] = React.useState("");
  const [expandedObjectId, setExpandedObjectId] = React.useState("");
  const [inspectorTab, setInspectorTab] = React.useState<InspectorTab>("general");
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
  const selectedSystem = systems.find((system) => system.id === systemId) ?? null;
  const selectedObject = objects.find((object) => object.id === objectId) ?? null;
  const selectedField = fields.find((field) => field.id === fieldId) ?? null;

  React.useEffect(() => {
    setInspectorTab("general");
  }, [systemId, objectId, fieldId]);

  const refreshSystems = React.useCallback(async (preferId?: string) => {
    const requestId = ++systemsRequest.current;
    setLoadingSystems(true);
    try {
      const nextSystems = await apiList<System>("/api/catalog/systems");
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
      const nextObjects = await apiList<CatalogObject>(
        `/api/catalog/systems/${currentSystemId}/objects`,
      );
      if (requestId !== objectsRequest.current) return;
      setObjects(nextObjects);
      const counts = await Promise.all(nextObjects.map(async (object) => [
        object.id,
        (await apiList<CatalogField>(`/api/catalog/objects/${object.id}/fields`)).length,
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
      const nextFields = await apiList<CatalogField>(
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
    try {
      await action();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The change could not be saved.");
      return false;
    } finally {
      setSaving(false);
    }
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
      const x = Number(form.get("x"));
      const y = Number(form.get("y"));
      await api<System>(`/api/catalog/systems/${selectedSystem.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: String(form.get("name") ?? ""),
          kind: String(form.get("kind") ?? ""),
          description: valueOrNull(form.get("description")),
          icon: valueOrNull(form.get("icon")),
          color: valueOrNull(form.get("color")),
          position: { x: Number.isFinite(x) ? x : 0, y: Number.isFinite(y) ? y : 0 },
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
        caught instanceof ApiRequestError &&
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

  return (
    <main className="workspace">
      <header className="workspace-header">
        <div className="workspace-brand">
          <span className="brand-mark" aria-hidden="true">D</span>
          <div>
          <p className="eyebrow">INTERNAL DATA ARCHITECTURE</p>
          <h1>Data Designer</h1>
          <p className="workspace-subtitle">
            {activeView === "catalog"
              ? "Build your dynamic System → Object → Field catalog."
              : activeView === "integrations"
                ? "Design contracts and evaluate sample data using dynamic catalog fields."
                : "Explore systems and their contract pathways."}
          </p>
          </div>
        </div>
        <WorkspaceSwitcher
          currentWorkspaceName={tenantName}
          csrfToken={csrfToken}
          onSwitch={() => {
            // Reset catalog state and reload everything for the newly active workspace
            setSystems([]);
            setObjects([]);
            setFields([]);
            setObjectFieldCounts({});
            setSystemId("");
            setObjectId("");
            setFieldId("");
            setExpandedSystemId("");
            setExpandedObjectId("");
            setError("");
            void refreshSystems();
          }}
        />
        <div className="workspace-header-actions">
          <nav className="workspace-nav" aria-label="Workspace">
            <button
              type="button"
              className={activeView === "catalog" ? "nav-tab active" : "nav-tab"}
              aria-pressed={activeView === "catalog"}
              onClick={() => setActiveView("catalog")}
            >
              Catalog
            </button>
            <button
              type="button"
              className={activeView === "integrations" ? "nav-tab active" : "nav-tab"}
              aria-pressed={activeView === "integrations"}
              onClick={() => {
                setQuickAddSystemId("");
                setActiveView("integrations");
              }}
            >
              Contracts
            </button>
            <button
              type="button"
              className={activeView === "landscape" ? "nav-tab active" : "nav-tab"}
              aria-pressed={activeView === "landscape"}
              onClick={() => setActiveView("landscape")}
            >
              Landscape
            </button>
          </nav>
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
        </div>
      </header>

      {activeView === "integrations" ? (
        <IntegrationWorkspace
          onBack={() => setActiveView("landscape")}
          initialIntegrationId={quickAddSystemId ? undefined : integrationToOpen || undefined}
          initialContractView={quickAddSystemId ? undefined : integrationPhaseToOpen}
          newIntegrationSystemId={quickAddSystemId || undefined}
        />
      ) : activeView === "landscape" ? (
        <EnterpriseLandscape
          onOpenCatalog={() => setActiveView("catalog")}
          onAddIntegration={(systemId) => {
            setQuickAddSystemId(systemId);
            setIntegrationToOpen("");
            setIntegrationPhaseToOpen(undefined);
            setActiveView("integrations");
          }}
          onOpenIntegration={(id, phase) => {
            setQuickAddSystemId("");
            setIntegrationToOpen(id);
            setIntegrationPhaseToOpen(phase);
            setActiveView("integrations");
          }}
        />
      ) : (
      <>
      <ErrorNotice message={error} />

      <div className="catalog-grid">
        <section className="catalog-panel systems-panel" aria-labelledby="systems-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CATALOG</p>
              <h2 id="systems-heading">Systems</h2>
            </div>
            <span className="item-count">{systems.length}</span>
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

        <CatalogInspector
          system={!objectId ? selectedSystem : null}
          object={objectId && !fieldId ? selectedObject : null}
          field={fieldId ? selectedField : null}
          objects={objects}
          fields={fields}
          fieldCounts={objectFieldCounts}
          loadingObjects={loadingObjects}
          loadingFields={loadingFields}
          saving={saving}
          tab={inspectorTab}
          onTabChange={setInspectorTab}
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
        {selectedSystem && selectedObject && selectedField && selectedSystem.id === "" && (
        <>
        <section className="catalog-panel detail-panel" aria-labelledby="system-detail-heading">
          {selectedSystem ? (
            <>
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">SYSTEM DESIGNER</p>
                  <h2 id="system-detail-heading">{selectedSystem.name}</h2>
                </div>
                <button
                  type="button"
                  className="danger-button"
                  disabled={saving}
                  onClick={() =>
                    void archiveItem(
                      `/api/catalog/systems/${selectedSystem.id}`,
                      selectedSystem.name,
                      async () => {
                        await refreshSystems();
                      },
                    )
                  }
                >
                  Archive
                </button>
              </div>
              <form className="editor-form" onSubmit={saveSystem} key={selectedSystem.id}>
                <InspectorTabs value={inspectorTab} onChange={setInspectorTab} />
                <div className="inspector-tab-panel" hidden={inspectorTab !== "general"}>
                  <label>
                    System name
                    <input name="name" required maxLength={160} defaultValue={selectedSystem.name} />
                  </label>
                  <label>
                    Description
                    <textarea name="description" rows={3} defaultValue={selectedSystem.description ?? ""} />
                  </label>
                </div>
                <div className="inspector-tab-panel" hidden={inspectorTab !== "schema"}>
                <div className="form-row">
                  <label>
                    Kind
                    <input name="kind" required maxLength={100} defaultValue={selectedSystem.kind} />
                  </label>
                  <label>
                    Icon
                    <input name="icon" maxLength={100} defaultValue={selectedSystem.icon ?? ""} />
                  </label>
                  <label>
                    Color
                    <input name="color" maxLength={40} placeholder="#527ca4" defaultValue={selectedSystem.color ?? ""} />
                  </label>
                </div>
                <div className="form-row system-position">
                  <label>
                    Landscape X
                    <input type="number" name="x" defaultValue={selectedSystem.position?.x ?? 0} />
                  </label>
                  <label>
                    Landscape Y
                    <input type="number" name="y" defaultValue={selectedSystem.position?.y ?? 0} />
                  </label>
                  <span className="muted">Position is used by the landscape view.</span>
                </div>
                </div>
                <div className="inspector-tab-panel" hidden={inspectorTab !== "metadata"}>
                  <label>
                    Metadata (JSON)
                    <textarea name="metadata" rows={8} spellCheck={false} defaultValue={metadataText(selectedSystem.metadata)} />
                  </label>
                </div>
                <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save system"}</button>
              </form>

              <div className="subsection-heading">
                <div>
                  <p className="eyebrow">SYSTEM CONTENTS</p>
                  <h3>Objects</h3>
                </div>
                <span className="item-count">{objects.length}</span>
              </div>
              <form className="compact-form object-create" onSubmit={createObject}>
                <h3>Add an object</h3>
                <div className="form-row">
                  <label>
                    Name
                    <input name="name" required maxLength={160} placeholder="e.g. Customer" />
                  </label>
                  <label>
                    Label
                    <input name="label" required maxLength={160} placeholder="Display label" />
                  </label>
                </div>
                <div className="form-row">
                  <label>
                    Description
                    <input name="description" maxLength={2000} />
                  </label>
                  <label>
                    Metadata (JSON)
                    <input name="metadata" defaultValue="{}" />
                  </label>
                </div>
                <button type="submit" disabled={saving}>Add object</button>
              </form>
              {loadingObjects ? (
                <p className="muted" role="status">Loading objects…</p>
              ) : objects.length === 0 ? (
                <p className="empty-state">This system has no objects yet.</p>
              ) : (
                <ul className="object-list">
                  {objects.map((object, index) => (
                    <li className={object.id === objectId ? "object-row selected" : "object-row"} key={object.id}>
                      <button type="button" className="object-select" onClick={() => setObjectId(object.id)}>
                        <span className="object-glyph">▦</span>
                        <span><strong>{object.label}</strong><small>{object.name}</small></span>
                      </button>
                      <ReorderButtons
                        disabled={saving}
                        onMove={(direction) =>
                          void reorder(
                            objects,
                            index,
                            direction,
                            (id) => `/api/catalog/objects/${id}`,
                            () => refreshObjects(selectedSystem.id),
                          )
                        }
                      />
                    </li>
                  ))}
                </ul>
              )}
              {selectedObject && (
                <form className="editor-form object-editor" onSubmit={saveObject} key={selectedObject.id}>
                  <div className="subsection-heading">
                    <div>
                      <p className="eyebrow">OBJECT DETAILS</p>
                      <h3>{selectedObject.label}</h3>
                    </div>
                    <button
                      type="button"
                      className="danger-button"
                      disabled={saving}
                      onClick={() =>
                        void archiveItem(
                          `/api/catalog/objects/${selectedObject.id}`,
                          selectedObject.label,
                          () => refreshObjects(selectedSystem.id),
                        )
                      }
                    >
                      Archive
                    </button>
                  </div>
                  <InspectorTabs value={inspectorTab} onChange={setInspectorTab} />
                  <div className="inspector-tab-panel" hidden={inspectorTab !== "general"}>
                  <div className="form-row">
                    <label>
                      Name
                      <input name="name" required maxLength={160} defaultValue={selectedObject.name} />
                    </label>
                    <label>
                      Label
                      <input name="label" required maxLength={160} defaultValue={selectedObject.label} />
                    </label>
                  </div>
                  <label>
                    Description
                    <textarea name="description" rows={2} defaultValue={selectedObject.description ?? ""} />
                  </label>
                  </div>
                  <div className="inspector-tab-panel" hidden={inspectorTab !== "schema"}>
                  <div className="form-row">
                    <label>
                      External identifier
                      <input
                        name="external_identifier"
                        defaultValue={selectedObject.external_identifier ?? ""}
                      />
                    </label>
                    <label>
                      Position
                      <input name="position" type="number" min={0} defaultValue={selectedObject.position} />
                    </label>
                  </div>
                  </div>
                  <div className="inspector-tab-panel" hidden={inspectorTab !== "metadata"}>
                  <label>
                    Metadata (JSON)
                    <textarea name="metadata" rows={8} spellCheck={false} defaultValue={metadataText(selectedObject.metadata)} />
                  </label>
                  </div>
                  <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save object"}</button>
                </form>
              )}
            </>
          ) : (
            <div className="empty-workspace">
              <span className="empty-icon">◇</span>
              <h2>{loadingSystems ? "Loading catalog…" : "Create or select a system"}</h2>
              <p>Objects and fields belong to a system, and will be available for contract design as soon as they are saved.</p>
            </div>
          )}
        </section>

        <section className="catalog-panel field-panel" aria-labelledby="field-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">FIELD DESIGNER</p>
              <h2 id="field-heading">{selectedObject ? selectedObject.label : "Fields"}</h2>
            </div>
            <span className="item-count">{fields.length}</span>
          </div>
          {!selectedObject ? (
            <p className="empty-state">Select or create an object to manage its fields.</p>
          ) : (
            <>
              <p className="field-parent">
                In <strong>{selectedSystem?.name}</strong> / <strong>{selectedObject.name}</strong>
              </p>
              <form className="compact-form" onSubmit={createField}>
                <h3>Add a field</h3>
                <div className="form-row">
                  <label>
                    Name
                    <input name="name" required maxLength={160} placeholder="e.g. customer_id" />
                  </label>
                  <label>
                    Label
                    <input name="label" required maxLength={160} placeholder="Customer ID" />
                  </label>
                </div>
                <label>
                  Data type
                  <input name="data_type" required maxLength={100} placeholder="string, integer, or any generic type" />
                </label>
                <div className="check-row">
                  <label><input name="required" type="checkbox" /> Required</label>
                  <label><input name="nullable" type="checkbox" defaultChecked /> Nullable</label>
                </div>
                <label>
                  Default value (JSON, blank for none)
                  <input name="default_value" placeholder='"value", 0, true' />
                </label>
                <label>
                  Metadata (JSON)
                  <textarea name="metadata" rows={2} defaultValue="{}" />
                </label>
                <button type="submit" disabled={saving}>Add field</button>
              </form>

              {loadingFields ? (
                <p className="muted" role="status">Loading fields…</p>
              ) : fields.length === 0 ? (
                <p className="empty-state">No fields yet. Add generic field metadata for this object.</p>
              ) : (
                <ul className="field-list">
                  {fields.map((field, index) => (
                    <li key={field.id} className={field.id === fieldId ? "field-row selected" : "field-row"}>
                      <button type="button" className="field-select" onClick={() => setFieldId(field.id)}>
                        <span className="field-type">{field.data_type}</span>
                        <span><strong>{field.label}</strong><small>{field.name}</small></span>
                        <span className="field-badges">
                          {field.required && <small className="badge">Required</small>}
                          {!field.nullable && <small className="badge">Not null</small>}
                        </span>
                      </button>
                      <ReorderButtons
                        disabled={saving}
                        onMove={(direction) =>
                          void reorder(
                            fields,
                            index,
                            direction,
                            (id) => `/api/catalog/fields/${id}`,
                            () => refreshFields(selectedObject.id),
                          )
                        }
                      />
                    </li>
                  ))}
                </ul>
              )}

              {selectedField && (
                <form className="editor-form field-editor" onSubmit={saveField} key={selectedField.id}>
                  <div className="subsection-heading">
                    <div>
                      <p className="eyebrow">FIELD DETAILS</p>
                      <h3>{selectedField.label}</h3>
                    </div>
                    <button
                      type="button"
                      className="danger-button"
                      disabled={saving}
                      onClick={() =>
                        void archiveItem(
                          `/api/catalog/fields/${selectedField.id}`,
                          selectedField.label,
                          () => refreshFields(selectedObject.id),
                        )
                      }
                    >
                      Archive
                    </button>
                  </div>
                  <InspectorTabs value={inspectorTab} onChange={setInspectorTab} />
                  <div className="inspector-tab-panel" hidden={inspectorTab !== "general"}>
                  <div className="form-row">
                    <label>
                      Name
                      <input name="name" required maxLength={160} defaultValue={selectedField.name} />
                    </label>
                    <label>
                      Label
                      <input name="label" required maxLength={160} defaultValue={selectedField.label} />
                    </label>
                  </div>
                  <label>
                    Description
                    <textarea name="description" rows={3} defaultValue={selectedField.description ?? ""} />
                  </label>
                  </div>
                  <div className="inspector-tab-panel" hidden={inspectorTab !== "schema"}>
                  <label>
                    Data type
                    <input name="data_type" required maxLength={100} defaultValue={selectedField.data_type} />
                  </label>
                  <div className="check-row">
                    <label><input name="required" type="checkbox" defaultChecked={selectedField.required} /> Required</label>
                    <label><input name="nullable" type="checkbox" defaultChecked={selectedField.nullable} /> Nullable</label>
                  </div>
                  <div className="form-row">
                    <label>
                      Default value (JSON, blank for none)
                      <input
                        name="default_value"
                        defaultValue={selectedField.default_value == null ? "" : JSON.stringify(selectedField.default_value)}
                      />
                    </label>
                    <label>
                      Position
                      <input name="position" type="number" min={0} defaultValue={selectedField.position} />
                    </label>
                  </div>
                  <div className="form-row">
                    <label>
                      External identifier
                      <input name="external_identifier" defaultValue={selectedField.external_identifier ?? ""} />
                    </label>
                    <label>
                      Origin
                      <input name="origin" defaultValue={selectedField.origin} />
                    </label>
                  </div>
                  </div>
                  <div className="inspector-tab-panel" hidden={inspectorTab !== "metadata"}>
                  <label>
                    Metadata (JSON)
                    <textarea name="metadata" rows={8} spellCheck={false} defaultValue={metadataText(selectedField.metadata)} />
                  </label>
                  </div>
                  <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save field"}</button>
                </form>
              )}
            </>
          )}
        </section>
        </>
        )}
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
    </main>
  );
}
