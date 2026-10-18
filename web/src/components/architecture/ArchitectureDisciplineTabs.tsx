import React from "react";
import {
  ARCHITECTURE_DISCIPLINES,
  type ArchitectureDiscipline,
} from "../../architectureTypes";

type Props = {
  disciplines: ArchitectureDiscipline[];
  activeDiscipline: ArchitectureDiscipline;
  onSelect: (discipline: ArchitectureDiscipline) => void;
};

/**
 * Discipline selector. With two or more enabled disciplines this is a tab
 * group; with one it renders the discipline name as plain context instead of a
 * one-item tab group.
 */
export default function ArchitectureDisciplineTabs({
  disciplines,
  activeDiscipline,
  onSelect,
}: Props) {
  const enabled = ARCHITECTURE_DISCIPLINES.filter((discipline) =>
    disciplines.includes(discipline.id));

  if (enabled.length <= 1) {
    const only = enabled[0] ?? ARCHITECTURE_DISCIPLINES.find(
      (discipline) => discipline.id === activeDiscipline,
    ) ?? ARCHITECTURE_DISCIPLINES[0];
    return (
      <span
        className="architecture-discipline-context"
        aria-label={`Architecture discipline: ${only.label}`}
      >
        <span className="architecture-discipline-context-label">Discipline</span>
        <span className="architecture-discipline-context-name">{only.label}</span>
      </span>
    );
  }

  return (
    <nav className="architecture-discipline-tabs tabs" role="tablist" aria-label="Architecture disciplines">
      {enabled.map((discipline) => (
        <button
          key={discipline.id}
          type="button"
          role="tab"
          aria-selected={discipline.id === activeDiscipline}
          aria-label={discipline.label}
          title={discipline.description}
          className={`architecture-discipline-tab tab${discipline.id === activeDiscipline ? " active" : ""}`}
          onClick={() => onSelect(discipline.id)}
        >
          {discipline.label.replace(" Architecture", "")}
        </button>
      ))}
    </nav>
  );
}
