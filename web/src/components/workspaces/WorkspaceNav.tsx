import type { ArchitectureDiscipline } from "../../architectureTypes";
import {
  workspaceTabDefinitions,
  type WorkspaceScopeView,
} from "../../workspace/disciplineScope";

type WorkspaceNavProps = {
  disciplines: ArchitectureDiscipline[] | null | undefined;
  activeView: WorkspaceScopeView;
  onNavigate: (view: WorkspaceScopeView) => void;
  /** True while a transition is in flight; tabs stay enabled but are inert. */
  busy?: boolean;
};

/**
 * Discipline-scoped shell navigation. Only enabled surfaces render: Contracts
 * requires Integration, Catalog is always relevant, and Canvas hosts every
 * discipline workbench.
 */
export default function WorkspaceNav({
  disciplines,
  activeView,
  onNavigate,
  busy = false,
}: WorkspaceNavProps) {
  const tabs = workspaceTabDefinitions(disciplines);
  return (
    <nav className="workspace-nav" aria-label="Primary navigation">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={activeView === tab.id ? "nav-tab active" : "nav-tab"}
          aria-pressed={activeView === tab.id}
          disabled={busy}
          onClick={() => onNavigate(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
