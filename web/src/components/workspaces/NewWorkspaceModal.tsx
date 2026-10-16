import React from "react";
import {
  ARCHITECTURE_DISCIPLINES,
  type ArchitectureDiscipline,
} from "../../architectureTypes";

export type DemoPreset = "full" | "solution_integration" | "integration_only";

const DEMO_PRESETS: { id: DemoPreset; label: string; description: string; disciplines: ArchitectureDiscipline[] }[] = [
  {
    id: "full",
    label: "Full Architecture",
    description: "Enterprise, Information, Solution and Integration.",
    disciplines: ["enterprise", "information", "solution", "integration"],
  },
  {
    id: "solution_integration",
    label: "Solution + Integration",
    description: "Solution designs and integration contracts only.",
    disciplines: ["solution", "integration"],
  },
  {
    id: "integration_only",
    label: "Integration Only",
    description: "Catalog schemas, contracts, mappings and tests only.",
    disciplines: ["integration"],
  },
];

type NewWorkspaceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (
    name: string,
    description: string,
    demoPreset: DemoPreset | null,
    disciplines: ArchitectureDiscipline[],
  ) => Promise<void>;
  loading?: boolean;
};

const fieldStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid var(--color-border-strong)",
  fontSize: "0.9rem",
};

export default function NewWorkspaceModal({
  isOpen,
  onClose,
  onCreate,
  loading = false,
}: NewWorkspaceModalProps) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [isDemo, setIsDemo] = React.useState(false);
  const [demoPreset, setDemoPreset] = React.useState<DemoPreset>("full");
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

  function chooseDemoPreset(preset: DemoPreset) {
    setError("");
    setDemoPreset(preset);
    const spec = DEMO_PRESETS.find((item) => item.id === preset);
    if (spec) setDisciplines(spec.disciplines);
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
      await onCreate(name.trim(), description.trim(), isDemo ? demoPreset : null, disciplines);
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
          <label style={{ display: "grid", gap: "6px", fontSize: "0.85rem", fontWeight: 600, color: "var(--color-ink)" }}>
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
              style={fieldStyle}
            />
          </label>

          <label style={{ display: "grid", gap: "6px", fontSize: "0.85rem", fontWeight: 600, color: "var(--color-ink)" }}>
            Description (Optional)
            <input
              type="text"
              maxLength={500}
              placeholder="Brief description of this environment or architecture model"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
              style={fieldStyle}
            />
          </label>

          <div>
            <p style={{ margin: "0 0 8px", fontSize: "0.85rem", fontWeight: 600, color: "var(--color-ink)" }}>
              Initial Content
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div
                role="button"
                aria-pressed={!isDemo}
                onClick={() => { setError(""); setIsDemo(false); }}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: !isDemo ? "2px solid var(--discipline-integration)" : "1px solid var(--color-border)",
                  background: !isDemo ? "var(--color-accent-soft)" : "var(--color-surface)",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontWeight: 650, fontSize: "0.88rem", color: !isDemo ? "var(--color-accent)" : "var(--color-ink)", marginBottom: "4px" }}>
                  Blank Workspace
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                  Start empty with no systems. A clean slate for new modelling.
                </div>
              </div>

              <div
                role="button"
                aria-pressed={isDemo}
                onClick={() => { setError(""); setIsDemo(true); chooseDemoPreset(demoPreset); }}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: isDemo ? "2px solid var(--discipline-integration)" : "1px solid var(--color-border)",
                  background: isDemo ? "var(--color-accent-soft)" : "var(--color-surface)",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontWeight: 650, fontSize: "0.88rem", color: isDemo ? "var(--color-accent)" : "var(--color-ink)", marginBottom: "4px" }}>
                  Demo Workspace
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>
                  Deterministic customer-onboarding demo for the selected scope.
                </div>
              </div>
            </div>
          </div>

          {isDemo && (
            <div>
              <p style={{ margin: "0 0 8px", fontSize: "0.85rem", fontWeight: 600, color: "var(--color-ink)" }}>
                Demo Scope
              </p>
              <div style={{ display: "grid", gap: "8px" }}>
                {DEMO_PRESETS.map((preset) => {
                  const active = demoPreset === preset.id;
                  return (
                    <label
                      key={preset.id}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "10px",
                        padding: "8px 12px",
                        borderRadius: "6px",
                        border: active ? "1px solid var(--color-accent)" : "1px solid var(--color-border)",
                        background: active ? "var(--color-accent-soft)" : "var(--color-surface)",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="radio"
                        name="demo-preset"
                        checked={active}
                        onChange={() => chooseDemoPreset(preset.id)}
                        disabled={loading}
                        style={{ marginTop: "3px" }}
                      />
                      <div>
                        <div style={{ fontWeight: 600, fontSize: "0.85rem", color: active ? "var(--color-accent)" : "var(--color-ink)" }}>
                          {preset.label}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{preset.description}</div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <p style={{ margin: 0, fontSize: "0.85rem", fontWeight: 600, color: "var(--color-ink)" }}>
                Architecture Disciplines
              </p>
              {!isDemo && (
                <div style={{ display: "flex", gap: "6px" }}>
                  <button type="button" className="quiet-button" style={{ fontSize: "0.75rem", padding: "2px 6px" }} onClick={() => setDisciplines(["enterprise", "information", "solution", "integration"])}>
                    All 4
                  </button>
                  <button type="button" className="quiet-button" style={{ fontSize: "0.75rem", padding: "2px 6px" }} onClick={() => setDisciplines(["solution", "integration"])}>
                    Solution
                  </button>
                  <button type="button" className="quiet-button" style={{ fontSize: "0.75rem", padding: "2px 6px" }} onClick={() => setDisciplines(["integration"])}>
                    Integration Only
                  </button>
                </div>
              )}
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
                      cursor: isDemo ? "not-allowed" : "pointer",
                      opacity: isDemo && !checked ? 0.5 : 1,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleDiscipline(d.id)}
                      disabled={loading || isDemo}
                      style={{ marginTop: "3px" }}
                    />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.85rem", color: checked ? "var(--color-accent)" : "var(--color-ink)" }}>
                        {d.label}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{d.description}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {error && (
            <p className="error" role="alert" style={{ margin: 0, fontSize: "0.85rem" }}>
              {error}
            </p>
          )}

          <div className="catalog-modal-actions" style={{ marginTop: "8px" }}>
            <button type="button" className="secondary-button" onClick={onClose} disabled={loading}>
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
