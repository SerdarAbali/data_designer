import { useEffect, useRef, useState, type ReactNode } from "react";

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
  actions?: ReactNode;
  manageMenu?: ReactNode;
};

const SAVE_LABELS: Record<Exclude<SaveStatus, "idle">, string> = {
  saving: "Saving…",
  saved: "Saved",
  error: "Save failed",
};

/**
 * One responsive inspector shell for object properties, relationships and
 * traceability. Uses the shared side-panel contract: sticky header, local body
 * scrolling, predictable action/footer area, bounded width, and an overlay
 * drawer at narrow widths.
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
  actions,
  manageMenu,
}: Props) {
  const [tab, setTab] = useState(defaultTab ?? panels[0]?.id ?? "");
  const [manageOpen, setManageOpen] = useState(false);
  const manageRoot = useRef<HTMLDivElement>(null);
  const manageTrigger = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);

  const active = panels.some((panel) => panel.id === tab) ? tab : panels[0]?.id ?? "";

  // Restore focus to the element that opened the inspector when it unmounts.
  useEffect(() => {
    restoreFocus.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      const previous = restoreFocus.current;
      if (previous && previous.isConnected && previous !== document.body) {
        previous.focus();
      }
    };
  }, []);

  // Manage menu: outside click, Escape, and focus return.
  useEffect(() => {
    if (!manageOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!manageRoot.current?.contains(event.target as Node)) {
        setManageOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setManageOpen(false);
        manageTrigger.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [manageOpen]);

  const saveChip =
    saveStatus && saveStatus !== "idle" ? (
      <span
        className={`side-panel-context-chip is-${saveStatus}`}
        data-save-status={saveStatus}
        role="status"
        aria-live="polite"
      >
        {SAVE_LABELS[saveStatus]}
      </span>
    ) : null;

  return (
    <aside
      className="architecture-relationship-panel unified-inspector side-panel"
      aria-label={ariaLabel}
    >
      <header className="side-panel-header unified-inspector-header">
        <div className="side-panel-heading">
          <p className="eyebrow">{eyebrow}</p>
          <h3 className="side-panel-title unified-inspector-title">{title}</h3>
          {(stateName !== undefined || status || saveChip) && (
            <div className="side-panel-context">
              {stateName !== undefined && (
                <span className="side-panel-context-chip" title="Architecture state">
                  {stateName}
                </span>
              )}
              {status && (
                <span
                  className={`side-panel-context-chip${status.toLowerCase().includes("read-only") ? " is-readonly" : ""}`}
                >
                  {status}
                </span>
              )}
              {saveChip}
            </div>
          )}
          {identifier && (
            <code className="side-panel-id" title={identifier}>
              {identifier}
            </code>
          )}
        </div>
        <div className="side-panel-controls studio-inspector-actions">
          <button
            type="button"
            className="side-panel-icon-button"
            aria-label={collapseLabel}
            title={collapseLabel}
            onClick={onCollapse}
          >
            ›
          </button>
          <button
            type="button"
            className="side-panel-icon-button"
            aria-label={closeLabel}
            title={closeLabel}
            onClick={onClose}
          >
            ✕
          </button>
        </div>
      </header>

      <nav className="side-panel-tabs unified-inspector-tabs" aria-label="Inspector sections">
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

      <div className="side-panel-scroll unified-inspector-body">
        {panels.map((panel) => (
          <div key={panel.id} className="unified-inspector-panel" hidden={active !== panel.id}>
            {panel.content}
          </div>
        ))}
      </div>

      {(actions || manageMenu) && (
        <div className="inspector-actions-row side-panel-actions">
          {actions}
          {manageMenu && (
            <div className="inspector-manage-menu" ref={manageRoot}>
              <button
                type="button"
                ref={manageTrigger}
                className="inspector-manage-trigger"
                aria-expanded={manageOpen}
                aria-haspopup="menu"
                aria-label="Manage object"
                onClick={() => setManageOpen((open) => !open)}
              >
                Manage ⌄
              </button>
              <section
                className="more-menu-panel"
                role="menu"
                aria-label="Manage object"
                hidden={!manageOpen}
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest("button")) {
                    setManageOpen(false);
                    manageTrigger.current?.focus();
                  }
                }}
              >
                {manageMenu}
              </section>
            </div>
          )}
        </div>
      )}

      {footer && <div className="unified-inspector-footer side-panel-footer">{footer}</div>}
    </aside>
  );
}
