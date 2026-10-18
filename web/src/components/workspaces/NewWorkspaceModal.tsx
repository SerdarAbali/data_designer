import React from "react";
import { createPortal } from "react-dom";
import {
  ARCHITECTURE_DISCIPLINES,
  type ArchitectureDiscipline,
} from "../../architectureTypes";
import {
  ALL_DISCIPLINES,
  DEMO_PRESETS,
  demoPresetForDisciplines,
  normalizeDisciplines,
  presetForId,
  WORKSPACE_PRESETS,
  type DemoPreset,
  type InitialArchitectureState,
} from "../../workspace/disciplineScope";

export type { DemoPreset } from "../../workspace/disciplineScope";

type NewWorkspaceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (
    name: string,
    description: string,
    demoPreset: DemoPreset | null,
    disciplines: ArchitectureDiscipline[],
    initialState: InitialArchitectureState,
  ) => Promise<void>;
  loading?: boolean;
};

function sameDisciplines(
  a: readonly ArchitectureDiscipline[],
  b: readonly ArchitectureDiscipline[],
): boolean {
  return a.length === b.length && a.every((item) => b.includes(item));
}

export default function NewWorkspaceModal({
  isOpen,
  onClose,
  onCreate,
  loading = false,
}: NewWorkspaceModalProps) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [disciplines, setDisciplines] = React.useState<ArchitectureDiscipline[]>([
    ...ALL_DISCIPLINES,
  ]);
  const [isDemo, setIsDemo] = React.useState(false);
  const [demoPreset, setDemoPreset] = React.useState<DemoPreset | null>(null);
  const [initialState, setInitialState] = React.useState<InitialArchitectureState>("current");
  const [error, setError] = React.useState("");

  if (!isOpen) return null;

  const selectedPreset = WORKSPACE_PRESETS.find((preset) =>
    sameDisciplines(preset.disciplines, disciplines));
  const compatibleDemo = demoPresetForDisciplines(disciplines);

  function choosePreset(presetId: string) {
    const preset = presetForId(presetId);
    if (!preset) return;
    setError("");
    setDisciplines([...preset.disciplines]);
    if (isDemo) {
      if (preset.demoPreset) setDemoPreset(preset.demoPreset);
      else setIsDemo(false);
    }
  }

  function toggleDiscipline(discipline: ArchitectureDiscipline) {
    const next = disciplines.includes(discipline)
      ? disciplines.filter((item) => item !== discipline)
      : normalizeDisciplines([...disciplines, discipline]);
    if (next.length === 0) {
      setError("At least one architecture discipline must be selected.");
      return;
    }
    setError("");
    setDisciplines(next);
    // A demo only fits the scope it was generated for.
    if (isDemo && demoPresetForDisciplines(next) !== demoPreset) {
      setIsDemo(false);
      setDemoPreset(null);
    }
  }

  function chooseDemo(preset: DemoPreset) {
    setError("");
    const option = DEMO_PRESETS.find((item) => item.id === preset);
    if (option) setDisciplines([...option.disciplines]);
    setDemoPreset(preset);
    setIsDemo(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Please enter a workspace name");
      return;
    }
    if (disciplines.length === 0) {
      setError("Select at least one architecture discipline");
      return;
    }
    setError("");
    try {
      await onCreate(
        name.trim(),
        description.trim(),
        isDemo ? demoPreset : null,
        normalizeDisciplines(disciplines),
        initialState,
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    }
  }

  return createPortal(
    <div
      className="catalog-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-ws-title"
    >
      <div className="catalog-modal new-workspace-modal">
        <header>
          <div>
            <p className="eyebrow">ARCHITECTURE WORKSPACE</p>
            <h2 id="new-ws-title">Create New Workspace</h2>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={onClose}
            disabled={loading}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <form className="nw-form" onSubmit={handleSubmit}>
          <div className="nw-body">
            <label className="nw-field">
              <span className="nw-field-label">Workspace Name</span>
              <input
                type="text"
                required
                maxLength={120}
                placeholder="e.g. Retail Architecture 2026, Core Platform, Sandbox"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={loading}
                autoFocus
              />
            </label>

            <label className="nw-field">
              <span className="nw-field-label">Description (Optional)</span>
              <input
                type="text"
                maxLength={500}
                placeholder="Brief description of this environment or architecture model"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={loading}
              />
            </label>

            <fieldset className="nw-fieldset">
              <legend className="nw-field-label">Workspace Preset</legend>
              <div className="nw-presets">
                {WORKSPACE_PRESETS.map((preset) => {
                  const active = selectedPreset?.id === preset.id;
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      aria-pressed={active}
                      disabled={loading}
                      onClick={() => choosePreset(preset.id)}
                      className={`nw-preset${active ? " active" : ""}`}
                    >
                      <span className="nw-preset-label">{preset.label}</span>
                      <span className="nw-preset-desc">{preset.description}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="nw-fieldset">
              <legend className="nw-field-label">Enabled Disciplines</legend>
              <div className="nw-options">
                {ARCHITECTURE_DISCIPLINES.map((d) => {
                  const checked = disciplines.includes(d.id);
                  return (
                    <label
                      key={d.id}
                      className={`nw-option${checked ? " active" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleDiscipline(d.id)}
                        disabled={loading}
                      />
                      <span className="nw-option-body">
                        <span className="nw-option-title">{d.label}</span>
                        <span className="nw-option-desc">{d.description}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="nw-fieldset">
              <legend className="nw-field-label">Initial Architecture State</legend>
              <div className="nw-options">
                <label className="nw-option nw-option-plain">
                  <input
                    type="radio"
                    name="initial-state"
                    checked={initialState === "current" && !isDemo}
                    disabled={loading || isDemo}
                    onChange={() => setInitialState("current")}
                  />
                  <span className="nw-option-body">
                    <span className="nw-option-title">Current baseline draft</span>
                    <span className="nw-option-desc">
                      Capture the existing architecture in an editable Current state, then lock it
                      as the baseline.
                    </span>
                  </span>
                </label>
                <label className="nw-option nw-option-plain">
                  <input
                    type="radio"
                    name="initial-state"
                    checked={initialState === "candidate" && !isDemo}
                    disabled={loading || isDemo}
                    onChange={() => setInitialState("candidate")}
                  />
                  <span className="nw-option-body">
                    <span className="nw-option-title">Candidate starter</span>
                    <span className="nw-option-desc">
                      Capture the existing architecture in an editable Current state while designing
                      an editable Candidate alongside it.
                    </span>
                  </span>
                </label>
              </div>
              {isDemo && (
                <p className="nw-hint">
                  Demo content defines its own Current and Candidate states.
                </p>
              )}
            </fieldset>

            <fieldset className="nw-fieldset">
              <legend className="nw-field-label">Demo Content (Optional)</legend>
              <label className="nw-option nw-option-plain">
                <input
                  type="checkbox"
                  checked={isDemo}
                  disabled={loading || (!isDemo && !compatibleDemo)}
                  onChange={(e) => {
                    setError("");
                    if (!e.target.checked) {
                      setIsDemo(false);
                      setDemoPreset(null);
                      return;
                    }
                    chooseDemo(compatibleDemo ?? DEMO_PRESETS[0].id);
                  }}
                />
                <span className="nw-option-body">
                  <span className="nw-option-title">
                    Start with a deterministic demo
                  </span>
                </span>
              </label>
              {!isDemo && !compatibleDemo && (
                <p className="nw-hint">
                  Demo content is available for the Integration, Solution + Integration and Full
                  Architecture presets.
                </p>
              )}
              {isDemo && (
                <div className="nw-options nw-options-nested">
                  {DEMO_PRESETS.map((preset) => {
                    const active = demoPreset === preset.id;
                    return (
                      <label
                        key={preset.id}
                        className={`nw-option${active ? " active" : ""}`}
                      >
                        <input
                          type="radio"
                          name="demo-preset"
                          checked={active}
                          onChange={() => chooseDemo(preset.id)}
                          disabled={loading}
                        />
                        <span className="nw-option-body">
                          <span className="nw-option-title">{preset.label}</span>
                          <span className="nw-option-desc">{preset.description}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </fieldset>

            {error && (
              <p className="error nw-error" role="alert">
                {error}
              </p>
            )}
          </div>

          <div className="nw-actions">
            <button type="button" className="secondary-button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" disabled={loading}>
              {loading ? "Creating…" : "Create Workspace"}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
