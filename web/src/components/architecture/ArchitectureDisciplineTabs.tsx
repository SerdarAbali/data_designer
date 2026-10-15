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

export default function ArchitectureDisciplineTabs({
  disciplines,
  activeDiscipline,
  onSelect,
}: Props) {
  const enabled = ARCHITECTURE_DISCIPLINES.filter((discipline) =>
    disciplines.includes(discipline.id));

  return (
    <nav className="architecture-discipline-tabs" role="tablist" aria-label="Architecture disciplines">
      {enabled.map((discipline) => (
        <button
          key={discipline.id}
          type="button"
          role="tab"
          aria-selected={discipline.id === activeDiscipline}
          aria-label={discipline.label}
          title={discipline.description}
          className={`architecture-discipline-tab${discipline.id === activeDiscipline ? " active" : ""}`}
          onClick={() => onSelect(discipline.id)}
        >
          {discipline.label.replace(" Architecture", "")}
        </button>
      ))}
    </nav>
  );
}
