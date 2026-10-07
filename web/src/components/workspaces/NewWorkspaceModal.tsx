import React from "react";

type NewWorkspaceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string, description: string, seedDemoData: boolean) => Promise<void>;
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
  const [error, setError] = React.useState("");

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Please enter a workspace name");
      return;
    }
    setError("");
    try {
      await onCreate(name.trim(), description.trim(), seedDemoData);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    }
  }

  return (
    <div className="catalog-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="new-ws-title">
      <div className="catalog-modal" style={{ width: "min(100%, 540px)" }}>
        <header>
          <div>
            <p className="eyebrow">ARCHITECTURE WORKSPACE</p>
            <h2 id="new-ws-title">Create New Workspace</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose} disabled={loading} aria-label="Close">
            ✕
          </button>
        </header>

        <form onSubmit={handleSubmit} className="editor-form" style={{ display: "grid", gap: "16px" }}>
          <label style={{ display: "grid", gap: "6px", fontSize: "0.85rem", fontWeight: 600, color: "#374151" }}>
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
                border: "1px solid #d1d5db",
                fontSize: "0.9rem",
              }}
            />
          </label>

          <label style={{ display: "grid", gap: "6px", fontSize: "0.85rem", fontWeight: 600, color: "#374151" }}>
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
                border: "1px solid #d1d5db",
                fontSize: "0.9rem",
              }}
            />
          </label>

          <div>
            <p style={{ margin: "0 0 8px", fontSize: "0.85rem", fontWeight: 600, color: "#374151" }}>
              Initial Content
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div
                onClick={() => setSeedDemoData(false)}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: !seedDemoData ? "2px solid #2563eb" : "1px solid #e5e7eb",
                  background: !seedDemoData ? "#eff6ff" : "white",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ fontWeight: 650, fontSize: "0.88rem", color: !seedDemoData ? "#1e40af" : "#1f2937", marginBottom: "4px" }}>
                  ✨ Blank Canvas
                </div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                  Start completely empty with 0 systems. Clean slate for new modeling.
                </div>
              </div>

              <div
                onClick={() => setSeedDemoData(true)}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: seedDemoData ? "2px solid #2563eb" : "1px solid #e5e7eb",
                  background: seedDemoData ? "#eff6ff" : "white",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ fontWeight: 650, fontSize: "0.88rem", color: seedDemoData ? "#1e40af" : "#1f2937", marginBottom: "4px" }}>
                  📦 Sample Demo Model
                </div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
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

