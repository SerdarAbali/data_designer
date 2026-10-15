import { useState, type ReactNode } from "react";

import type { SaveStatus } from "../architecture/ArchitectureTopBar";

export type InspectorPanel = {
  id: string;
  label: string;
  count?: number;
  content: ReactNode;
};

type Props = {
  ariaLabel: string;
  eyebrow: string;
  title: ReactNode;
  identifier?: string;
  stateName?: string;
  status?: string;
  saveStatus?: SaveStatus;
  collapseLabel: string;
  closeLabel: string;
  onCollapse: () => void;
  onClose: () => void;
  panels: InspectorPanel[];
  defaultTab?: string;
  footer?: ReactNode;
};

/**
 * One responsive inspector shell for object properties, relationships and
 * traceability. Desktop width is ~360px; the body scrolls internally instead of
 * scrolling the page, and at constrained widths it becomes an overlay drawer.
 */
export default function UnifiedInspector({
  ariaLabel,
  eyebrow,
  title,
  identifier,
  stateName,
  status,
  saveStatus,
  collapseLabel,
  closeLabel,
  onCollapse,
  onClose,
  panels,
  defaultTab,
  footer,
}: Props) {
  const [tab, setTab] = useState(defaultTab ?? panels[0]?.id ?? "");
  const active = panels.some((panel) => panel.id === tab) ? tab : panels[0]?.id ?? "";

  return (
    <aside className="architecture-relationship-panel unified-inspector" aria-label={ariaLabel}>
      <header>
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        <div className="studio-inspector-actions">
          <button type="button" className="secondary-button" aria-label={collapseLabel} onClick={onCollapse}>
            ›
          </button>
          <button type="button" className="secondary-button" aria-label={closeLabel} onClick={onClose}>
            ✕
          </button>
        </div>
      </header>
      {stateName !== undefined && (
        <p className="studio-inspector-state">
          {stateName} · {status} <span>{saveStatus === "idle" ? "" : saveStatus}</span>
        </p>
      )}
      {identifier && (
        <small className="studio-object-identifier" title={identifier}>{identifier}</small>
      )}
      <nav className="unified-inspector-tabs" aria-label="Inspector sections">
        {panels.map((panel) => (
          <button
            key={panel.id}
            type="button"
            className={active === panel.id ? "active" : ""}
            aria-pressed={active === panel.id}
            onClick={() => setTab(panel.id)}
          >
            {panel.label}
            {panel.count != null ? ` (${panel.count})` : ""}
          </button>
        ))}
      </nav>
      <div className="unified-inspector-body">
        {panels.map((panel) => (
          <div key={panel.id} className="unified-inspector-panel" hidden={active !== panel.id}>
            {panel.content}
          </div>
        ))}
      </div>
      {footer && <div className="unified-inspector-footer">{footer}</div>}
    </aside>
  );
}
