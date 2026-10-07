import React from "react";
import NewWorkspaceModal from "./NewWorkspaceModal";

export type WorkspaceInfo = {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  systems_count: number;
  contracts_count: number;
  scenarios_count: number;
};

type WorkspaceSwitcherProps = {
  currentWorkspaceName: string;
  onSwitch: () => void;
  csrfToken: () => string;
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
}: WorkspaceSwitcherProps) {
  const detailsRef = React.useRef<HTMLDetailsElement>(null);
  const [workspaces, setWorkspaces] = React.useState<WorkspaceInfo[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [switching, setSwitching] = React.useState<string | null>(null);

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
    setLoading(true);
    setError("");
    try {
      const list = await apiWs<WorkspaceInfo[]>("/api/workspaces", csrfToken);
      setWorkspaces(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load workspaces");
    } finally {
      setLoading(false);
    }
  }

  // Load on first open
  const [hasLoaded, setHasLoaded] = React.useState(false);

  function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if ((e.currentTarget as HTMLDetailsElement).open && !hasLoaded) {
      setHasLoaded(true);
      void loadWorkspaces();
    }
  }

  async function handleSwitch(id: string) {
    if (switching) return;
    setSwitching(id);
    try {
      await apiWs<WorkspaceInfo>(`/api/workspaces/${id}/switch`, csrfToken, { method: "POST" });
      // Close dropdown
      if (detailsRef.current) detailsRef.current.open = false;
      onSwitch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Switch failed");
    } finally {
      setSwitching(null);
    }
  }

  async function handleCreate(name: string, description: string, seedDemoData: boolean) {
    setCreating(true);
    try {
      await apiWs<WorkspaceInfo>("/api/workspaces", csrfToken, {
        method: "POST",
        body: JSON.stringify({ name, description: description || null, seed_demo_data: seedDemoData }),
      });
      setShowNewModal(false);
      if (detailsRef.current) detailsRef.current.open = false;
      onSwitch();
    } finally {
      setCreating(false);
    }
  }

  async function handleForkSubmit(sourceId: string) {
    if (!forkName.trim()) {
      setForkError("Please enter a name for the fork");
      return;
    }
    setForking(true);
    setForkError("");
    try {
      await apiWs<WorkspaceInfo>(`/api/workspaces/${sourceId}/fork`, csrfToken, {
        method: "POST",
        body: JSON.stringify({ name: forkName.trim() }),
      });
      setForkingId(null);
      setForkName("");
      if (detailsRef.current) detailsRef.current.open = false;
      onSwitch();
    } catch (e) {
      setForkError(e instanceof Error ? e.message : "Fork failed");
    } finally {
      setForking(false);
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
    </>
  );
}
