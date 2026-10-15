import React from "react";
import {
  ARCHITECTURE_DISCIPLINES,
  type ArchitectureDiscipline,
} from "../../architectureTypes";

type NewWorkspaceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (
    name: string,
    description: string,
    seedDemoData: boolean,
    disciplines: ArchitectureDiscipline[],
  ) => Promise<void>;
  loading?: boolean;
};

export default function NewWorkspaceModal({
  isOpen,
  onClose,
  onCreate,
  loading = false,
}: NewWorkspaceModalProps) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [seedDemoData, setSeedDemoData] = React.useState(false);
  const [disciplines, setDisciplines] = React.useState<ArchitectureDiscipline[]>([
    "enterprise",
    "information",
    "solution",
    "integration",
  ]);
  const [error, setError] = React.useState("");

  if (!isOpen) return null;

  function toggleDiscipline(d: ArchitectureDiscipline) {
    if (disciplines.includes(d)) {
      if (disciplines.length === 1) {
        setError("At least one architecture discipline must be selected.");
        return;
      }
      setError("");
      setDisciplines(disciplines.filter((item) => item !== d));
    } else {
      setError("");
      setDisciplines([...disciplines, d]);
    }
  }

  function applyPreset(preset: "all" | "solution_integration" | "integration_only") {
    setError("");
    if (preset === "all") {
      setDisciplines(["enterprise", "information", "solution", "integration"]);
    } else if (preset === "solution_integration") {
      setDisciplines(["solution", "integration"]);
    } else if (preset === "integration_only") {
      setDisciplines(["integration"]);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Please enter a workspace name");
      return;
    }
    if (disciplines.length === 0) {
      setError("Select at least one architecture discipline");
      return;
    }
    setError("");
    try {
      await onCreate(name.trim(), description.trim(), seedDemoData, disciplines);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    }
  }

  return (
    <div
      className="catalog-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-ws-title"
    >
      <div className="catalog-modal" style={{ width: "min(100%, 580px)" }}>
        <header>
          <div>
            <p className="eyebrow">ARCHITECTURE WORKSPACE</p>
            <h2 id="new-ws-title">Create New Workspace</h2>
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

        <form
          onSubmit={handleSubmit}
          className="editor-form"
          style={{ display: "grid", gap: "16px" }}
        >
          <label
            style={{
              display: "grid",
              gap: "6px",
              fontSize: "0.85rem",
              fontWeight: 600,
              color: "var(--color-ink)",
            }}
          >
            Workspace Name
            <input
              type="text"
              required
              maxLength={120}
              placeholder="e.g. Retail Architecture 2026, Core Platform, Sandbox"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={loading}
              autoFocus
              style={{
                padding: "8px 12px",
                borderRadius: "8px",
                border: "1px solid var(--color-border-strong)",
                fontSize: "0.9rem",
              }}
            />
          </label>

          <label
            style={{
              display: "grid",
              gap: "6px",
              fontSize: "0.85rem",
              fontWeight: 600,
              color: "var(--color-ink)",
            }}
          >
            Description (Optional)
            <input
              type="text"
              maxLength={500}
              placeholder="Brief description of this environment or architecture model"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
              style={{
                padding: "8px 12px",
                borderRadius: "8px",
                border: "1px solid var(--color-border-strong)",
                fontSize: "0.9rem",
              }}
            />
          </label>

          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "8px",
              }}
            >
              <p
                style={{
                  margin: 0,
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  color: "var(--color-ink)",
                }}
              >
                Architecture Disciplines
              </p>
              <div style={{ display: "flex", gap: "6px" }}>
                <button
                  type="button"
                  className="quiet-button"
                  style={{ fontSize: "0.75rem", padding: "2px 6px" }}
                  onClick={() => applyPreset("all")}
                >
                  All 4
                </button>
                <button
                  type="button"
                  className="quiet-button"
                  style={{ fontSize: "0.75rem", padding: "2px 6px" }}
                  onClick={() => applyPreset("solution_integration")}
                >
                  Solution
                </button>
                <button
                  type="button"
                  className="quiet-button"
                  style={{ fontSize: "0.75rem", padding: "2px 6px" }}
                  onClick={() => applyPreset("integration_only")}
                >
                  Integration Only
                </button>
              </div>
            </div>

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
                      padding: "8px 12px",
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
                      style={{ marginTop: "3px" }}
                    />
                    <div>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: "0.85rem",
                          color: checked ? "var(--color-accent)" : "var(--color-ink)",
                        }}
                      >
                        {d.label}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                        {d.description}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          <div>
            <p
              style={{
                margin: "0 0 8px",
                fontSize: "0.85rem",
                fontWeight: 600,
                color: "var(--color-ink)",
              }}
            >
              Initial Content
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div
                onClick={() => setSeedDemoData(false)}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: !seedDemoData ? "2px solid var(--discipline-integration)" : "1px solid var(--color-border)",
                  background: !seedDemoData ? "var(--color-accent-soft)" : "var(--color-surface)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div
                  style={{
                    fontWeight: 650,
                    fontSize: "0.88rem",
                    color: !seedDemoData ? "var(--color-accent)" : "var(--color-ink)",
                    marginBottom: "4px",
                  }}
                >
                  ✨ Blank Canvas
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                  Start completely empty with 0 systems. Clean slate for new modeling.
                </div>
              </div>

              <div
                onClick={() => setSeedDemoData(true)}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: seedDemoData ? "2px solid var(--discipline-integration)" : "1px solid var(--color-border)",
                  background: seedDemoData ? "var(--color-accent-soft)" : "var(--color-surface)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div
                  style={{
                    fontWeight: 650,
                    fontSize: "0.88rem",
                    color: seedDemoData ? "var(--color-accent)" : "var(--color-ink)",
                    marginBottom: "4px",
                  }}
                >
                  📦 Sample Demo Model
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                  Preloaded with demo CRM, ERP, and advertising systems to explore.
                </div>
              </div>
            </div>
          </div>

          {error && (
            <p className="error" role="alert" style={{ margin: 0, fontSize: "0.85rem" }}>
              {error}
            </p>
          )}

          <div className="catalog-modal-actions" style={{ marginTop: "8px" }}>
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button type="submit" disabled={loading}>
              {loading ? "Creating…" : "Create Workspace"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
