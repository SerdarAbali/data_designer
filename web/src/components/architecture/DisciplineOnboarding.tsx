import { useState } from "react";

import type { ArchitectureDiscipline } from "../../architectureTypes";
import { disciplineGuidance, disciplineLabel } from "../../workspace/disciplineScope";

type Props = {
  workspaceId: string;
  discipline: ArchitectureDiscipline;
};

function storageKey(workspaceId: string, discipline: ArchitectureDiscipline): string {
  return `dd_discipline_onboarding:${workspaceId}:${discipline}`;
}

function isDismissed(workspaceId: string, discipline: ArchitectureDiscipline): boolean {
  try {
    return localStorage.getItem(storageKey(workspaceId, discipline)) === "dismissed";
  } catch {
    return false;
  }
}

/**
 * Compact, discipline-specific first-use guidance shown above the active
 * workbench. Dismissal is remembered per workspace and discipline.
 */
export default function DisciplineOnboarding({ workspaceId, discipline }: Props) {
  const [dismissed, setDismissed] = useState(() => isDismissed(workspaceId, discipline));
  const guidance = disciplineGuidance(discipline);
  if (dismissed || guidance.steps.length === 0) return null;

  function dismiss() {
    try {
      localStorage.setItem(storageKey(workspaceId, discipline), "dismissed");
    } catch {
      /* storage unavailable */
    }
    setDismissed(true);
  }

  return (
    <aside
      className="discipline-onboarding"
      role="note"
      aria-label={`${disciplineLabel(discipline)} first steps`}
    >
      <div className="discipline-onboarding-body">
        <strong>{guidance.title}</strong>
        <ol>
          {guidance.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
      <button
        type="button"
        className="discipline-onboarding-dismiss"
        aria-label="Dismiss guidance"
        onClick={dismiss}
      >
        Dismiss
      </button>
    </aside>
  );
}
