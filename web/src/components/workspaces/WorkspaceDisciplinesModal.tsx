import React from "react";
import { createPortal } from "react-dom";
import {
  ARCHITECTURE_DISCIPLINES,
  type ArchitectureDiscipline,
  type WorkspaceInfo,
} from "../../architectureTypes";

type WorkspaceDisciplinesModalProps = {
  isOpen: boolean;
  workspace: WorkspaceInfo | null;
  onClose: () => void;
  onUpdate: (workspaceId: string, name: string, disciplines: ArchitectureDiscipline[]) => Promise<void>;
  loading?: boolean;
};

export default function WorkspaceDisciplinesModal({
  isOpen,
  workspace,
  onClose,
  onUpdate,
  loading = false,
}: WorkspaceDisciplinesModalProps) {
  const [name, setName] = React.useState(workspace?.name ?? "");
  const [disciplines, setDisciplines] = React.useState<ArchitectureDiscipline[]>(
    workspace?.disciplines || ["enterprise", "information", "solution", "integration"],
  );
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (isOpen && workspace) {
      setName(workspace.name);
      setDisciplines(workspace.disciplines);
      setError("");
    }
  }, [isOpen, workspace]);

  if (!isOpen || !workspace) return null;

  function toggleDiscipline(d: ArchitectureDiscipline) {
    if (disciplines.includes(d)) {
      if (disciplines.length === 1) {
        setError("At least one discipline must remain active.");
        return;
      }
      setError("");
      setDisciplines(disciplines.filter((item) => item !== d));
    } else {
      setError("");
      setDisciplines([...disciplines, d]);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace || loading) return;
    if (!name.trim()) {
      setError("Please enter a workspace name.");
      return;
    }
    if (disciplines.length === 0) {
      setError("Please select at least one discipline.");
      return;
    }
    setError("");
    try {
      await onUpdate(workspace.id, name.trim(), disciplines);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update workspace");
    }
  }

  return createPortal(
    <div
      className="catalog-modal-backdrop workspace-settings-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ws-disc-title"
    >
      <div className="catalog-modal workspace-settings-modal">
        <header>
          <div>
            <p className="eyebrow">WORKSPACE</p>
            <h2 id="ws-disc-title">Workspace Settings</h2>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={onClose}
            disabled={loading}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <form onSubmit={handleSubmit} className="editor-form">
          <div className="workspace-settings-body">
          <label>
            Workspace name
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              required
              disabled={loading}
            />
          </label>
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--color-muted)" }}>
            Enable or disable architecture disciplines for this workspace. Architecture objects are shared and will not be lost if a discipline is toggled off.
          </p>

          <div style={{ display: "grid", gap: "8px" }}>
            {ARCHITECTURE_DISCIPLINES.map((d) => {
              const checked = disciplines.includes(d.id);
              return (
                <label
                  key={d.id}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    padding: "10px 12px",
                    borderRadius: "6px",
                    border: checked ? "1px solid var(--color-accent)" : "1px solid var(--color-border)",
                    background: checked ? "var(--color-accent-soft)" : "var(--color-surface)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleDiscipline(d.id)}
                    disabled={loading}
                    style={{ marginTop: "3px", width: "auto", flexShrink: 0 }}
                  />
                  <div>
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: "0.88rem",
                        color: checked ? "var(--color-accent)" : "var(--color-ink)",
                      }}
                    >
                      {d.label}
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>
                      {d.description}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>

          {error && (
            <p className="error" role="alert" style={{ margin: 0, fontSize: "0.85rem" }}>
              {error}
            </p>
          )}
          </div>

          <div className="catalog-modal-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button type="submit" disabled={loading}>
              {loading ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
