import React from "react";
import type { ArchitectureState } from "../../architectureTypes";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

type Props = {
  states: ArchitectureState[];
  activeStateId: string;
  onSelectState: (stateId: string) => void;
  disciplines: React.ReactNode;
  options: React.ReactNode;
  saveStatus: SaveStatus;
};

export default function ArchitectureTopBar({
  states, activeStateId, onSelectState, disciplines, options, saveStatus,
}: Props) {
  const active = states.find((state) => state.id === activeStateId);
  const stateType = active?.state_type ?? "current";
  return (
    <header className="architecture-topbar" aria-label="Architecture state and discipline">
      <div className="architecture-context-group">
        <div className={`studio-state-selector state-${stateType}`} role="group" aria-label="Architecture state">
          <span className="state-dot" aria-hidden="true" />
          <span className="state-type-label">{stateType.charAt(0).toUpperCase() + stateType.slice(1)}</span>
          {stateType === "current" && <span className="state-readonly-hint" title="Current state is read-only — duplicate it to model changes">Read-only</span>}
          <select aria-label="Architecture state" value={activeStateId} onChange={(event) => onSelectState(event.target.value)}>
            {states.length === 0 && <option value="">Loading state…</option>}
            {states.map((state) => (
              <option key={state.id} value={state.id}>
                {state.state_type === "current" ? "Current" : `${state.state_type === "target" ? "Target" : "Candidate"} · ${state.name}`}
              </option>
            ))}
          </select>
        </div>
        <span className="context-divider" aria-hidden="true">│</span>
        {disciplines}
      </div>
      <div className="architecture-view-options">{options}</div>
    </header>
  );
}
