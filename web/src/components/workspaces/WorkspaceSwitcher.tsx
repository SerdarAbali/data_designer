import React from "react";
import NewWorkspaceModal from "./NewWorkspaceModal";
import WorkspaceDisciplinesModal from "./WorkspaceDisciplinesModal";
import type { ArchitectureDiscipline, WorkspaceInfo } from "../../architectureTypes";

type WorkspaceSwitcherProps = {
  currentWorkspaceName: string;
  onSwitch: () => void | Promise<void>;
  csrfToken: () => string;
  onDisciplinesUpdated?: () => void;
  beforeSwitch?: () => Promise<boolean>;
  onTransitionChange?: (active: boolean) => void;
};

async function apiWs<T>(path: string, csrf: () => string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrf());
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = body.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message?: unknown }).message)
          : "Request failed";
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export default function WorkspaceSwitcher({
  currentWorkspaceName,
  onSwitch,
  csrfToken,
  onDisciplinesUpdated,
  beforeSwitch,
  onTransitionChange,
}: WorkspaceSwitcherProps) {
  const detailsRef = React.useRef<HTMLDetailsElement>(null);
  const lastOpen = React.useRef(false);
  const [workspaces, setWorkspaces] = React.useState<WorkspaceInfo[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [switching, setSwitching] = React.useState<string | null>(null);
  const workspacesRequest = React.useRef(0);

  // New workspace modal
  const [showNewModal, setShowNewModal] = React.useState(false);
  const [creating, setCreating] = React.useState(false);

  // Fork state
  const [forkingId, setForkingId] = React.useState<string | null>(null);
  const [forkName, setForkName] = React.useState("");
  const [forking, setForking] = React.useState(false);
  const [forkError, setForkError] = React.useState("");

  // Export state
  const [exportingId, setExportingId] = React.useState<string | null>(null);

  const activeWorkspace = workspaces.find((w) => w.is_active);

  async function loadWorkspaces() {
    const requestId = ++workspacesRequest.current;
    setLoading(true);
    setError("");
    try {
      const list = await apiWs<WorkspaceInfo[]>("/api/workspaces", csrfToken);
      if (requestId !== workspacesRequest.current) return;
      setWorkspaces(list);
    } catch (e) {
      if (requestId === workspacesRequest.current) {
        setError(e instanceof Error ? e.message : "Could not load workspaces");
      }
    } finally {
      if (requestId === workspacesRequest.current) setLoading(false);
    }
  }

  function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    const open = e.currentTarget.open;
    if (open && !lastOpen.current) {
      void loadWorkspaces();
    }
    lastOpen.current = open;
  }

  async function handleSwitch(id: string) {
    if (switching) return;
    setSwitching(id);
    onTransitionChange?.(true);
    try {
      if (beforeSwitch && !await beforeSwitch()) return;
      await apiWs<WorkspaceInfo>(`/api/workspaces/${id}/switch`, csrfToken, { method: "POST" });
      await loadWorkspaces();
      // Close dropdown
      if (detailsRef.current) detailsRef.current.open = false;
      await onSwitch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Switch failed");
    } finally {
      setSwitching(null);
      onTransitionChange?.(false);
    }
  }

  // Disciplines modal
  const [editingDisciplinesWs, setEditingDisciplinesWs] = React.useState<WorkspaceInfo | null>(null);
  const [updatingDisciplines, setUpdatingDisciplines] = React.useState(false);

  async function handleCreate(
    name: string,
    description: string,
    seedDemoData: boolean,
    disciplines: ArchitectureDiscipline[],
  ) {
    setCreating(true);
    onTransitionChange?.(true);
    try {
      if (beforeSwitch && !await beforeSwitch()) throw new Error("Resolve the pending save before creating a workspace.");
      await apiWs<WorkspaceInfo>("/api/workspaces", csrfToken, {
        method: "POST",
        body: JSON.stringify({
          name,
          description: description || null,
          seed_demo_data: seedDemoData,
          disciplines,
        }),
      });
      await loadWorkspaces();
      setShowNewModal(false);
      if (detailsRef.current) detailsRef.current.open = false;
      await onSwitch();
    } finally {
      setCreating(false);
      onTransitionChange?.(false);
    }
  }

  async function handleUpdateDisciplines(
    workspaceId: string,
    name: string,
    disciplines: ArchitectureDiscipline[],
  ) {
    setUpdatingDisciplines(true);
    try {
      if (beforeSwitch && !await beforeSwitch()) throw new Error("Resolve the pending save before changing workspace settings.");
      const updated = await apiWs<WorkspaceInfo>(`/api/workspaces/${workspaceId}`, csrfToken, {
        method: "PATCH",
        body: JSON.stringify({ name, disciplines }),
      });
      setWorkspaces((list) => list.map((ws) => ws.id === updated.id ? updated : ws));
      onDisciplinesUpdated?.();
      setEditingDisciplinesWs(null);
    } finally {
      setUpdatingDisciplines(false);
    }
  }

  async function handleForkSubmit(sourceId: string) {
    if (!forkName.trim()) {
      setForkError("Please enter a name for the fork");
      return;
    }
    setForking(true);
    onTransitionChange?.(true);
    setForkError("");
    try {
      if (beforeSwitch && !await beforeSwitch()) throw new Error("Resolve the pending save before forking a workspace.");
      await apiWs<WorkspaceInfo>(`/api/workspaces/${sourceId}/fork`, csrfToken, {
        method: "POST",
        body: JSON.stringify({ name: forkName.trim() }),
      });
      await loadWorkspaces();
      setForkingId(null);
      setForkName("");
      if (detailsRef.current) detailsRef.current.open = false;
      await onSwitch();
    } catch (e) {
      setForkError(e instanceof Error ? e.message : "Fork failed");
    } finally {
      setForking(false);
      onTransitionChange?.(false);
    }
  }

  async function handleExport(ws: WorkspaceInfo) {
    if (exportingId) return;
    setExportingId(ws.id);
    try {
      const bundle = await apiWs<object>(`/api/workspaces/${ws.id}/export`, csrfToken);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${ws.name.replace(/[^a-z0-9]/gi, "_")}.dd.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportingId(null);
    }
  }

  // Close dropdown on outside click
  React.useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (detailsRef.current && !detailsRef.current.contains(e.target as Node)) {
        detailsRef.current.open = false;
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const active = activeWorkspace ?? { name: currentWorkspaceName, systems_count: 0, contracts_count: 0, scenarios_count: 0 };

  return (
    <>
      <details ref={detailsRef} className="workspace-switcher" onToggle={handleToggle}>
        <summary aria-label="Switch workspace" className="ws-switcher-trigger">
          <span className="ws-switcher-icon" aria-hidden="true">⊞</span>
          <span className="ws-switcher-label">
            <span className="ws-switcher-name">{active.name}</span>
            <small>
              {active.systems_count}s · {active.contracts_count}c · {active.scenarios_count}sc
            </small>
          </span>
          <span className="account-chevron" aria-hidden="true">⌄</span>
        </summary>

        <div className="ws-switcher-dropdown">
          <p className="ws-switcher-section-label">WORKSPACES</p>

          {loading && (
            <p className="ws-switcher-loading">Loading…</p>
          )}
          {error && (
            <p className="ws-switcher-error" role="alert">{error}</p>
          )}

          {!loading && workspaces.map((ws) => (
            <div key={ws.id} className="ws-switcher-entry">
              {forkingId === ws.id ? (
                <div className="ws-fork-inline">
                  <input
                    type="text"
                    className="ws-fork-input"
                    placeholder="Fork name…"
                    value={forkName}
                    onChange={(e) => setForkName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void handleForkSubmit(ws.id);
                      if (e.key === "Escape") { setForkingId(null); setForkName(""); setForkError(""); }
                    }}
                    autoFocus
                    disabled={forking}
                  />
                  {forkError && <p className="ws-fork-error">{forkError}</p>}
                  <div className="ws-fork-actions">
                    <button type="button" className="ws-fork-confirm" onClick={() => void handleForkSubmit(ws.id)} disabled={forking}>
                      {forking ? "Forking…" : "Fork"}
                    </button>
                    <button type="button" className="ws-fork-cancel" onClick={() => { setForkingId(null); setForkName(""); setForkError(""); }} disabled={forking}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    className={`ws-switcher-row${ws.is_active ? " ws-active" : ""}`}
                    onClick={() => !ws.is_active && void handleSwitch(ws.id)}
                    disabled={switching === ws.id || ws.is_active}
                  >
                    <span className="ws-active-dot" aria-hidden="true">{ws.is_active ? "●" : "○"}</span>
                    <span className="ws-row-info">
                      <span className="ws-row-name">{ws.name}</span>
                      <small>{ws.systems_count}s · {ws.contracts_count}c · {ws.scenarios_count}sc</small>
                    </span>
                    {switching === ws.id && <span className="ws-switching-spinner" aria-hidden="true">…</span>}
                  </button>
                  <div className="ws-row-actions">
                    <button
                      type="button"
                      className="ws-action-btn"
                      title="Workspace Settings"
                      onClick={() => {
                        if (detailsRef.current) detailsRef.current.open = false;
                        setEditingDisciplinesWs(ws);
                      }}
                    >
                      ⚙ Settings
                    </button>
                    <button
                      type="button"
                      className="ws-action-btn"
                      title="Fork this workspace"
                      onClick={() => { setForkingId(ws.id); setForkName(`${ws.name} (fork)`); setForkError(""); }}
                    >
                      ⑂ Fork
                    </button>
                    <button
                      type="button"
                      className="ws-action-btn"
                      title="Export workspace bundle"
                      onClick={() => void handleExport(ws)}
                      disabled={exportingId === ws.id}
                    >
                      {exportingId === ws.id ? "…" : "↓ Export"}
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}

          <div className="ws-switcher-footer">
            <button
              type="button"
              className="ws-new-btn"
              onClick={() => {
                if (detailsRef.current) detailsRef.current.open = false;
                setShowNewModal(true);
              }}
            >
              + New Workspace
            </button>
          </div>
        </div>
      </details>

      <NewWorkspaceModal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        onCreate={handleCreate}
        loading={creating}
      />

      <WorkspaceDisciplinesModal
        isOpen={Boolean(editingDisciplinesWs)}
        workspace={editingDisciplinesWs}
        onClose={() => setEditingDisciplinesWs(null)}
        onUpdate={handleUpdateDisciplines}
        loading={updatingDisciplines}
      />
    </>
  );
}
