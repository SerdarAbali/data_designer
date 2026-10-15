import React from "react";
import type { ArchitectureState } from "../../architectureTypes";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

type Props = {
  states: ArchitectureState[];
  activeStateId: string;
  onSelectState: (stateId: string) => void;
  disciplines: React.ReactNode;
  addMenu: React.ReactNode;
  options: React.ReactNode;
  saveStatus: SaveStatus;
};

export default function ArchitectureTopBar({
  states, activeStateId, onSelectState, disciplines, addMenu, options, saveStatus,
}: Props) {
  const active = states.find((state) => state.id === activeStateId);
  return (
    <header className="architecture-topbar" aria-label="Architecture canvas toolbar">
      <label className={`studio-state-selector state-${active?.state_type ?? "current"}`}>
        <span className="state-dot" aria-hidden="true" />
        <select aria-label="Architecture state" value={activeStateId} onChange={(event) => onSelectState(event.target.value)}>
          {states.length === 0 && <option value="">Loading state…</option>}
          {states.map((state) => (
            <option key={state.id} value={state.id}>
              {state.state_type === "current" ? "Current" : `${state.state_type === "target" ? "Target" : "Candidate"} · ${state.name}`}
            </option>
          ))}
        </select>
      </label>
      {disciplines}
      <span className={`architecture-save-status ${saveStatus}`} role="status" aria-live="polite">
        {saveStatus === "saving" ? "Saving…" : saveStatus === "saved" ? "Saved" : saveStatus === "error" ? "Save failed" : active?.state_type === "current" ? "Read-only" : ""}
      </span>
      {addMenu}
      {options}
    </header>
  );
}
