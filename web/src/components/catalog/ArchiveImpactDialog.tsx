import React from "react";

export type ReferencingIntegration = {
  id?: string;
  name?: string;
};

type ArchiveImpactDialogProps = {
  itemName: string;
  itemType: "system" | "object" | "field";
  integrations: ReferencingIntegration[];
  onConfirmCascade: () => Promise<void>;
  onCancel: () => void;
  onOpenIntegration?: (integrationId: string) => void;
  loading?: boolean;
};

export default function ArchiveImpactDialog({
  itemName,
  itemType,
  integrations,
  onConfirmCascade,
  onCancel,
  onOpenIntegration,
  loading = false,
}: ArchiveImpactDialogProps) {
  return (
    <div className="catalog-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="impact-title">
      <div className="catalog-modal impact-dialog-modal">
        <header>
          <div>
            <p className="eyebrow" style={{ color: "#b91c1c" }}>DEPENDENCY IMPACT</p>
            <h2 id="impact-title">Archive {itemName}?</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onCancel} disabled={loading} aria-label="Close">
            ✕
          </button>
        </header>

        <p style={{ margin: "0 0 14px", color: "#374151", fontSize: "0.9rem", lineHeight: 1.5 }}>
          This {itemType} cannot be archived alone because it is actively used by{" "}
          <strong>{integrations.length}</strong> integration contract{integrations.length > 1 ? "s" : ""}:
        </p>

        <div
          style={{
            maxHeight: "180px",
            overflowY: "auto",
            background: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            padding: "8px 12px",
            marginBottom: "16px",
          }}
        >
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {integrations.map((item, idx) => (
              <li
                key={item.id ?? idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 0",
                  borderBottom: idx < integrations.length - 1 ? "1px solid #f3f4f6" : "none",
                  fontSize: "0.85rem",
                }}
              >
                <span style={{ fontWeight: 600, color: "#1f2937" }}>
                  ⇄ {item.name || "Unnamed contract"}
                </span>
                {item.id && onOpenIntegration && (
                  <button
                    type="button"
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--color-accent, #2563eb)",
                      cursor: "pointer",
                      padding: "2px 6px",
                      fontSize: "0.78rem",
                      fontWeight: 600,
                    }}
                    onClick={() => onOpenIntegration(item.id!)}
                    disabled={loading}
                  >
                    View contract →
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div
          style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "8px",
            padding: "10px 12px",
            marginBottom: "18px",
            fontSize: "0.82rem",
            color: "#991b1b",
            lineHeight: 1.4,
          }}
        >
          <strong>Cascade Archiving:</strong> Archiving will safely archive <em>{itemName}</em> and{" "}
          <strong>all {integrations.length} referencing contract{integrations.length > 1 ? "s" : ""}</strong> together in a single transaction.
        </div>

        <div className="catalog-modal-actions">
          <button type="button" className="secondary-button" onClick={onCancel} disabled={loading}>
            Cancel
          </button>
          <button
            type="button"
            style={{
              background: "#dc2626",
              color: "white",
              fontWeight: 650,
            }}
            onClick={onConfirmCascade}
            disabled={loading}
          >
            {loading ? "Archiving…" : "Archive with Referencing Contracts"}
          </button>
        </div>
      </div>
    </div>
  );
}

