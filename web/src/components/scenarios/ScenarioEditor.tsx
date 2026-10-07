import React from "react";
import type { EnterpriseArchitectureIndex } from "../../enterpriseArchitectureIndex";
import {
  MAX_FRAGMENT_DEPTH,
  PHASE_LABELS,
  SCENARIO_CATEGORIES,
  appendToOperand,
  availablePhases,
  contractLabel,
  contractStepEndpoints,
  deriveLifelines,
  flattenSteps,
  formatSampleValue,
  fragmentDepth,
  insertAfter,
  isFragment,
  moveItem,
  newScenarioId,
  parseSampleInput,
  removeItem,
  unwrapFragment,
  updateItem,
  wrapItem,
  type FieldValues,
  type Lifeline,
  type ScenarioCategory,
  type ScenarioDocument,
  type ScenarioEvaluation,
  type ScenarioFragment,
  type ScenarioFragmentKind,
  type ScenarioItem,
  type ScenarioPhase,
  type ScenarioStateEntry,
  type ScenarioStep,
  type ScenarioStepKind,
} from "../../scenarioModel";

export type ScenarioDraftState = {
  name: string;
  category: ScenarioCategory;
  description: string | null;
  document: ScenarioDocument;
};

type Props = {
  draft: ScenarioDraftState;
  onChange: (draft: ScenarioDraftState) => void;
  index: EnterpriseArchitectureIndex | null;
  scopeIntegrationId: string | null;
  evaluation: ScenarioEvaluation | null;
  onOpenContractPhase: (contractId: string, phase: ScenarioPhase) => void;
};

type EditorContext = {
  index: EnterpriseArchitectureIndex | null;
  document: ScenarioDocument;
  lifelines: Lifeline[];
  numbers: Map<string, string>;
  contractOptions: { id: string; name: string }[];
  evaluation: ScenarioEvaluation | null;
  setItems: (update: (items: ScenarioItem[]) => ScenarioItem[]) => void;
  ensureParticipant: (lifelineId: string) => void;
  onOpenContractPhase: Props["onOpenContractPhase"];
};

function fieldsOfObject(index: EnterpriseArchitectureIndex | null, objectId: string | null | undefined) {
  if (!index || !objectId) return [];
  return (index.objectsById.get(objectId)?.fieldIds ?? [])
    .map((id) => index.fieldsById.get(id))
    .filter((field): field is NonNullable<typeof field> => !!field);
}

function objectLabel(index: EnterpriseArchitectureIndex | null, objectId: string | null | undefined): string {
  if (!objectId) return "—";
  const object = index?.objectsById.get(objectId);
  if (!object) return "Missing object";
  return `${index?.systemsById.get(object.systemId)?.name ?? "?"} · ${object.displayName}`;
}

function FieldValuesEditor({
  index,
  objectId,
  values,
  onChange,
  actual,
  placeholder,
  ariaPrefix,
}: {
  index: EnterpriseArchitectureIndex | null;
  objectId: string | null | undefined;
  values: FieldValues;
  onChange: (values: FieldValues) => void;
  actual?: FieldValues;
  placeholder?: string;
  ariaPrefix: string;
}) {
  const fields = fieldsOfObject(index, objectId);
  const known = new Set(fields.map((field) => field.id));
  const stale = Object.keys(values).filter((id) => !known.has(id));
  if (fields.length === 0 && stale.length === 0) {
    return <p className="muted">No fields available for {objectLabel(index, objectId)}.</p>;
  }
  const setValue = (fieldId: string, raw: string) => {
    const next = { ...values };
    if (raw === "") delete next[fieldId];
    else next[fieldId] = parseSampleInput(raw);
    onChange(next);
  };
  return (
    <table className="scenario-values-table">
      <thead>
        <tr>
          <th>Field</th>
          <th>Value</th>
          {actual && <th>Evaluated</th>}
        </tr>
      </thead>
      <tbody>
        {fields.map((field) => {
          const has = Object.prototype.hasOwnProperty.call(values, field.id);
          const actualValue = actual?.[field.id];
          const mismatch = actual && has && JSON.stringify(actualValue) !== JSON.stringify(values[field.id]);
          return (
            <tr key={field.id} className={mismatch ? "mismatch" : undefined}>
              <td>
                <span className="scenario-field-name">{field.displayName}</span>
                <span className="scenario-field-type">{field.dataType}{field.required ? " · required" : ""}</span>
              </td>
              <td>
                <input
                  aria-label={`${ariaPrefix} ${field.displayName}`}
                  value={has ? formatSampleValue(values[field.id]) : ""}
                  placeholder={placeholder}
                  onChange={(event) => setValue(field.id, event.target.value)}
                />
              </td>
              {actual && (
                <td className="scenario-actual">
                  {Object.prototype.hasOwnProperty.call(actual, field.id) ? formatSampleValue(actualValue) : "—"}
                </td>
              )}
            </tr>
          );
        })}
        {stale.map((fieldId) => (
          <tr key={fieldId} className="stale">
            <td>
              <span className="scenario-field-name">Missing field</span>
              <span className="scenario-field-type">Archived or moved</span>
            </td>
            <td>
              <span>{formatSampleValue(values[fieldId])}</span>{" "}
              <button type="button" className="quiet-button" onClick={() => setValue(fieldId, "")}>Remove</button>
            </td>
            {actual && <td />}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StateEditor({
  title,
  entries,
  onChange,
  index,
  document,
}: {
  title: string;
  entries: ScenarioStateEntry[];
  onChange: (entries: ScenarioStateEntry[]) => void;
  index: EnterpriseArchitectureIndex | null;
  document: ScenarioDocument;
}) {
  const systemParticipants = document.participants.filter((item) => item.kind === "system");
  const objectsFor = (participantId: string) => {
    const systemId = systemParticipants.find((item) => item.id === participantId)?.systemId;
    const system = systemId ? index?.systemsById.get(systemId) : undefined;
    return (system?.objectIds ?? []).map((id) => index!.objectsById.get(id)!).filter(Boolean);
  };
  const update = (id: string, patch: Partial<ScenarioStateEntry>) =>
    onChange(entries.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)));
  const add = () => {
    const participant = systemParticipants[0];
    if (!participant) return;
    const object = objectsFor(participant.id)[0];
    if (!object) return;
    onChange([...entries, { id: newScenarioId("state"), participantId: participant.id, objectId: object.id, values: {} }]);
  };
  return (
    <section className="scenario-section">
      <header className="scenario-section-header">
        <h4>{title}</h4>
        <button
          type="button"
          className="secondary-button"
          onClick={add}
          disabled={systemParticipants.length === 0}
          title={systemParticipants.length === 0 ? "Add a system participant first" : undefined}
        >
          Add system data
        </button>
      </header>
      {entries.length === 0 && <p className="muted">No data recorded.</p>}
      {entries.map((entry) => (
        <div key={entry.id} className="scenario-state-entry">
          <div className="scenario-inline-fields">
            <label>
              System
              <select
                value={entry.participantId}
                onChange={(event) => {
                  const object = objectsFor(event.target.value)[0];
                  update(entry.id, { participantId: event.target.value, objectId: object?.id ?? entry.objectId, values: {} });
                }}
              >
                {systemParticipants.map((participant) => (
                  <option key={participant.id} value={participant.id}>
                    {participant.label || index?.systemsById.get(participant.systemId ?? "")?.name || participant.id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Object
              <select value={entry.objectId} onChange={(event) => update(entry.id, { objectId: event.target.value, values: {} })}>
                {!objectsFor(entry.participantId).some((object) => object.id === entry.objectId) && (
                  <option value={entry.objectId}>{objectLabel(index, entry.objectId)}</option>
                )}
                {objectsFor(entry.participantId).map((object) => (
                  <option key={object.id} value={object.id}>{object.displayName}</option>
                ))}
              </select>
            </label>
            <button type="button" className="danger-button" onClick={() => onChange(entries.filter((item) => item.id !== entry.id))}>
              Remove
            </button>
          </div>
          <FieldValuesEditor
            index={index}
            objectId={entry.objectId}
            values={entry.values}
            onChange={(values) => update(entry.id, { values })}
            ariaPrefix={`${title}`}
          />
          <input
            className="scenario-note-input"
            aria-label={`${title} note`}
            placeholder="Note (optional)"
            value={entry.note ?? ""}
            onChange={(event) => update(entry.id, { note: event.target.value || null })}
          />
        </div>
      ))}
    </section>
  );
}

function StepEditor({ step, context }: { step: ScenarioStep; context: EditorContext }) {
  const { index } = context;
  const patch = (changes: Partial<ScenarioStep>) =>
    context.setItems((items) => updateItem(items, step.id, (item) => ({ ...(item as ScenarioStep), ...changes })));
  const endpoints = contractStepEndpoints(index, step.contractId, step.phase);
  const result = context.evaluation?.steps.find((item) => item.stepId === step.id);
  const contract = step.contractId ? index?.contractsById.get(step.contractId) : undefined;

  if (step.kind !== "contract") {
    return (
      <div className="scenario-step-editor">
        <div className="scenario-inline-fields">
          <label>
            {step.kind === "self" ? "Participant" : "From"}
            <select
              value={step.fromParticipantId ?? ""}
              onChange={(event) => {
                context.ensureParticipant(event.target.value);
                patch({ fromParticipantId: event.target.value, ...(step.kind === "self" ? { toParticipantId: event.target.value } : {}) });
              }}
            >
              <option value="" disabled>Select…</option>
              {context.lifelines.map((lifeline) => <option key={lifeline.id} value={lifeline.id}>{lifeline.label}</option>)}
            </select>
          </label>
          {step.kind === "actor" && (
            <label>
              To
              <select
                value={step.toParticipantId ?? ""}
                onChange={(event) => {
                  context.ensureParticipant(event.target.value);
                  patch({ toParticipantId: event.target.value });
                }}
              >
                <option value="" disabled>Select…</option>
                {context.lifelines.map((lifeline) => <option key={lifeline.id} value={lifeline.id}>{lifeline.label}</option>)}
              </select>
            </label>
          )}
          <label className="grow">
            Message
            <input value={step.label ?? ""} onChange={(event) => patch({ label: event.target.value })} placeholder="Describe the interaction" />
          </label>
        </div>
        <label>
          Notes
          <textarea rows={2} value={step.notes ?? ""} onChange={(event) => patch({ notes: event.target.value || null })} />
        </label>
      </div>
    );
  }

  const phases = contract ? availablePhases(contract) : [];
  return (
    <div className="scenario-step-editor">
      <div className="scenario-inline-fields">
        <label>
          Contract
          <select
            value={step.contractId ?? ""}
            onChange={(event) => {
              const next = index?.contractsById.get(event.target.value);
              const nextPhases = next ? availablePhases(next) : [];
              patch({
                contractId: event.target.value,
                phase: nextPhases.includes(step.phase as ScenarioPhase) ? step.phase : nextPhases[0] ?? "request",
                sampleValues: {},
                expectedValues: {},
              });
            }}
          >
            {!context.contractOptions.some((option) => option.id === step.contractId) && (
              <option value={step.contractId ?? ""}>{contractLabel(index, step.contractId)}</option>
            )}
            {context.contractOptions.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </select>
        </label>
        <label>
          Phase
          <select
            value={step.phase ?? ""}
            onChange={(event) => patch({ phase: event.target.value as ScenarioPhase, sampleValues: {}, expectedValues: {} })}
          >
            {!phases.includes(step.phase as ScenarioPhase) && step.phase && (
              <option value={step.phase}>{PHASE_LABELS[step.phase]} (not configured)</option>
            )}
            {phases.map((phase) => <option key={phase} value={phase}>{PHASE_LABELS[phase]}</option>)}
          </select>
        </label>
        <label className="grow">
          Label
          <input value={step.label ?? ""} onChange={(event) => patch({ label: event.target.value || null })} placeholder="Optional business description" />
        </label>
        {endpoints && step.contractId && step.phase && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => context.onOpenContractPhase(step.contractId!, step.phase!)}
          >
            Open phase
          </button>
        )}
      </div>
      {endpoints ? (
        <>
          <p className="muted scenario-step-route">
            {objectLabel(index, endpoints.senderObjectId)} → {objectLabel(index, endpoints.receiverObjectId)}
            {endpoints.phase && <> · Mapping: {endpoints.phase.validationSummary.status}</>}
          </p>
          <div className="scenario-values-grid">
            <div>
              <h5>Sample values (sender)</h5>
              <FieldValuesEditor
                index={index}
                objectId={endpoints.senderObjectId}
                values={step.sampleValues ?? {}}
                onChange={(values) => patch({ sampleValues: values })}
                ariaPrefix="Sample"
              />
            </div>
            <div>
              <h5>Expected response (receiver)</h5>
              <FieldValuesEditor
                index={index}
                objectId={endpoints.receiverObjectId}
                values={step.expectedValues ?? {}}
                onChange={(values) => patch({ expectedValues: values })}
                actual={result && result.outcome !== "missing_reference" ? result.targetValues : undefined}
                placeholder="Expected"
                ariaPrefix="Expected"
              />
            </div>
          </div>
          {result && result.errors.length > 0 && (
            <ul className="scenario-errors">
              {result.errors.map((error, errorIndex) => <li key={errorIndex}>{error.message ?? error.code}</li>)}
            </ul>
          )}
        </>
      ) : (
        <p className="error">This contract or phase is missing, archived, or not configured.</p>
      )}
      <label>
        Notes
        <textarea rows={2} value={step.notes ?? ""} onChange={(event) => patch({ notes: event.target.value || null })} />
      </label>
    </div>
  );
}

function newStep(kind: ScenarioStepKind, context: EditorContext): ScenarioStep {
  const id = newScenarioId("step");
  if (kind === "contract") {
    // Prefer a participating contract that no step uses yet, so building a flow needs fewer edits.
    const used = new Set(flattenSteps(context.document.items).map(({ step }) => step.contractId));
    const contractId = (context.contractOptions.find((option) => !used.has(option.id)) ?? context.contractOptions[0])?.id ?? null;
    return { kind, id, contractId, phase: "request", sampleValues: {}, expectedValues: {} };
  }
  const first = context.lifelines[0]?.id ?? null;
  const second = context.lifelines.find((lifeline) => lifeline.id !== first)?.id ?? first;
  if (first) context.ensureParticipant(first);
  if (kind === "actor" && second) context.ensureParticipant(second);
  return kind === "self"
    ? { kind, id, fromParticipantId: first, toParticipantId: first, label: "Internal processing" }
    : { kind, id, fromParticipantId: first, toParticipantId: second, label: "Message" };
}

function AddStepButtons({ context, onAdd }: { context: EditorContext; onAdd: (step: ScenarioStep) => void }) {
  return (
    <div className="scenario-add-step">
      <button
        type="button"
        className="secondary-button"
        disabled={context.contractOptions.length === 0}
        onClick={() => onAdd(newStep("contract", context))}
      >
        + Contract step
      </button>
      <button type="button" className="secondary-button" disabled={context.lifelines.length === 0} onClick={() => onAdd(newStep("self", context))}>
        + Self call
      </button>
      <button type="button" className="secondary-button" disabled={context.lifelines.length === 0} onClick={() => onAdd(newStep("actor", context))}>
        + Actor / free message
      </button>
    </div>
  );
}

function ItemControls({ item, context, siblings }: { item: ScenarioItem; context: EditorContext; siblings: ScenarioItem[] }) {
  const position = siblings.findIndex((entry) => entry.id === item.id);
  const depth = fragmentDepth(context.document.items, item.id) ?? 0;
  const [wrapKind, setWrapKind] = React.useState<"" | ScenarioFragmentKind>("");
  return (
    <div className="scenario-item-controls">
      <button type="button" className="quiet-button" aria-label="Move up" disabled={position <= 0} onClick={() => context.setItems((items) => moveItem(items, item.id, -1))}>↑</button>
      <button type="button" className="quiet-button" aria-label="Move down" disabled={position >= siblings.length - 1} onClick={() => context.setItems((items) => moveItem(items, item.id, 1))}>↓</button>
      {!isFragment(item) && (
        <button
          type="button"
          className="quiet-button"
          onClick={() => context.setItems((items) => insertAfter(items, item.id, { ...structuredClone(item), id: newScenarioId("step") }))}
        >
          Duplicate
        </button>
      )}
      {depth < MAX_FRAGMENT_DEPTH && (
        <select
          aria-label="Wrap in block"
          className="scenario-wrap-select"
          value={wrapKind}
          onChange={(event) => {
            const kind = event.target.value as ScenarioFragmentKind;
            setWrapKind("");
            if (kind) context.setItems((items) => wrapItem(items, item.id, kind));
          }}
        >
          <option value="">Wrap in…</option>
          <option value="alt">alt</option>
          <option value="opt">opt</option>
          <option value="loop">loop</option>
        </select>
      )}
      {isFragment(item) && (
        <button type="button" className="quiet-button" onClick={() => context.setItems((items) => unwrapFragment(items, item.id))}>
          Unwrap
        </button>
      )}
      <button
        type="button"
        className="danger-button"
        onClick={() => context.setItems((items) => removeItem(items, item.id))}
      >
        Delete
      </button>
    </div>
  );
}

function FragmentEditor({ fragment, context, siblings }: { fragment: ScenarioFragment; context: EditorContext; siblings: ScenarioItem[] }) {
  const setFragment = (update: (fragment: ScenarioFragment) => ScenarioFragment) =>
    context.setItems((items) => updateItem(items, fragment.id, (item) => update(item as ScenarioFragment)));
  return (
    <div className={`scenario-fragment-card kind-${fragment.kind}`}>
      <div className="scenario-item-header">
        <select
          aria-label="Block type"
          value={fragment.kind}
          onChange={(event) => {
            const kind = event.target.value as ScenarioFragmentKind;
            setFragment((current) => {
              if (kind === "alt") {
                return { ...current, kind, operands: current.operands.length >= 2 ? current.operands : [...current.operands, { guard: "else", items: [] }] };
              }
              return { ...current, kind, operands: [{ guard: current.operands[0]?.guard ?? "", items: current.operands.flatMap((operand) => operand.items) }] };
            });
          }}
        >
          <option value="alt">alt — alternatives</option>
          <option value="opt">opt — optional</option>
          <option value="loop">loop — repeated</option>
        </select>
        <ItemControls item={fragment} context={context} siblings={siblings} />
      </div>
      {fragment.operands.map((operand, operandIndex) => (
        <div key={operandIndex} className="scenario-operand">
          <div className="scenario-inline-fields">
            <label className="grow">
              Guard
              <input
                value={operand.guard}
                placeholder={fragment.kind === "loop" ? "for each order line" : "condition"}
                onChange={(event) => setFragment((current) => ({
                  ...current,
                  operands: current.operands.map((entry, entryIndex) => (entryIndex === operandIndex ? { ...entry, guard: event.target.value } : entry)),
                }))}
              />
            </label>
            {fragment.kind === "alt" && fragment.operands.length > 2 && (
              <button
                type="button"
                className="quiet-button"
                onClick={() => setFragment((current) => ({
                  ...current,
                  operands: current.operands.filter((_, entryIndex) => entryIndex !== operandIndex),
                }))}
              >
                Remove branch
              </button>
            )}
          </div>
          <ItemList items={operand.items} context={context} />
          <AddStepButtons
            context={context}
            onAdd={(step) => context.setItems((items) => appendToOperand(items, fragment.id, operandIndex, step))}
          />
        </div>
      ))}
      {fragment.kind === "alt" && (
        <button
          type="button"
          className="quiet-button"
          onClick={() => setFragment((current) => ({ ...current, operands: [...current.operands, { guard: "", items: [] }] }))}
        >
          + Branch
        </button>
      )}
    </div>
  );
}

function stepSummary(step: ScenarioStep, context: EditorContext): string {
  if (step.kind === "contract") {
    return `${contractLabel(context.index, step.contractId)} · ${step.phase ? PHASE_LABELS[step.phase] : "?"}`;
  }
  const name = (id: string | null | undefined) => context.lifelines.find((item) => item.id === id)?.label ?? "?";
  return step.kind === "self"
    ? `${name(step.fromParticipantId)} ↺ ${step.label ?? ""}`
    : `${name(step.fromParticipantId)} → ${name(step.toParticipantId)}: ${step.label ?? ""}`;
}

function ItemList({ items, context }: { items: ScenarioItem[]; context: EditorContext }) {
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  if (items.length === 0) return <p className="muted scenario-empty-list">No steps yet.</p>;
  return (
    <ol className="scenario-item-list">
      {items.map((item) => {
        if (isFragment(item)) {
          return <li key={item.id}><FragmentEditor fragment={item} context={context} siblings={items} /></li>;
        }
        const open = expanded.has(item.id);
        const outcome = context.evaluation?.steps.find((entry) => entry.stepId === item.id)?.outcome;
        return (
          <li key={item.id} className={`scenario-step-card kind-${item.kind}${outcome ? ` outcome-${outcome}` : ""}`}>
            <div className="scenario-item-header">
              <button
                type="button"
                className="scenario-step-toggle"
                aria-expanded={open}
                onClick={() => setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(item.id)) next.delete(item.id);
                  else next.add(item.id);
                  return next;
                })}
              >
                <span className="scenario-step-number">{context.numbers.get(item.id)}</span>
                <span className={`scenario-kind-badge kind-${item.kind}${item.phase ? ` phase-${item.phase}` : ""}`}>
                  {item.kind === "contract" ? "Contract" : item.kind === "self" ? "Self" : "Message"}
                </span>
                <span className="scenario-step-summary">{stepSummary(item, context)}</span>
                {outcome && <span className={`scenario-outcome-badge outcome-${outcome}`}>{outcome.replace("_", " ")}</span>}
              </button>
              <ItemControls item={item} context={context} siblings={items} />
            </div>
            {open && <StepEditor step={item} context={context} />}
          </li>
        );
      })}
    </ol>
  );
}

export default function ScenarioEditor({ draft, onChange, index, scopeIntegrationId, evaluation, onOpenContractPhase }: Props) {
  const document = draft.document;
  const setDocument = (update: Partial<ScenarioDocument>) => onChange({ ...draft, document: { ...document, ...update } });
  const lifelines = React.useMemo(() => deriveLifelines(document, index), [document, index]);
  const numbers = React.useMemo(
    () => new Map(flattenSteps(document.items).map((item) => [item.step.id, item.number])),
    [document.items],
  );
  const allContracts = React.useMemo(
    () => [...(index?.contractsById.values() ?? [])].map((item) => ({ id: item.id, name: item.name })).sort((a, b) => a.name.localeCompare(b.name)),
    [index],
  );
  const contractOptions = scopeIntegrationId
    ? allContracts.filter((item) => item.id === scopeIntegrationId)
    : allContracts.filter((item) => document.contractIds.includes(item.id));

  // Keep a ref to the latest draft so participant materialisation and item edits compose.
  const latest = React.useRef(draft);
  latest.current = draft;
  const commit = (next: ScenarioDraftState) => {
    latest.current = next;
    onChange(next);
  };

  const context: EditorContext = {
    index,
    document,
    lifelines,
    numbers,
    contractOptions,
    evaluation,
    onOpenContractPhase,
    setItems: (update) => {
      const current = latest.current;
      commit({ ...current, document: { ...current.document, items: update(current.document.items) } });
    },
    ensureParticipant: (lifelineId) => {
      const current = latest.current;
      const lifeline = deriveLifelines(current.document, index).find((item) => item.id === lifelineId);
      if (!lifeline?.implicit) return;
      commit({
        ...current,
        document: {
          ...current.document,
          participants: [...current.document.participants, { id: lifeline.id, kind: "system", systemId: lifeline.systemId }],
        },
      });
    },
  };

  const systems = [...(index?.systemsById.values() ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const evaluationAssertions = new Map(evaluation?.assertions.map((item) => [item.assertionId, item]) ?? []);
  const contractSteps = flattenSteps(document.items).filter((item) => item.step.kind === "contract");

  return (
    <div className="scenario-editor">
      <section className="scenario-section">
        <h4>Scenario</h4>
        <div className="scenario-inline-fields">
          <label className="grow">
            Name
            <input value={draft.name} maxLength={160} onChange={(event) => onChange({ ...draft, name: event.target.value })} />
          </label>
          <label>
            Category
            <select value={draft.category} onChange={(event) => onChange({ ...draft, category: event.target.value as ScenarioCategory })}>
              {SCENARIO_CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
        </div>
        <label>
          Description
          <input value={draft.description ?? ""} maxLength={2000} onChange={(event) => onChange({ ...draft, description: event.target.value || null })} />
        </label>
        <div className="scenario-two-column">
          <label>
            Preconditions
            <textarea rows={3} value={document.preconditions} onChange={(event) => setDocument({ preconditions: event.target.value })} />
          </label>
          <label>
            Trigger
            <textarea rows={3} value={document.trigger} onChange={(event) => setDocument({ trigger: event.target.value })} />
          </label>
        </div>
      </section>

      <section className="scenario-section">
        <header className="scenario-section-header">
          <h4>Participants</h4>
          <div className="scenario-add-step">
            <select
              aria-label="Add system participant"
              value=""
              onChange={(event) => {
                if (!event.target.value) return;
                setDocument({
                  participants: [
                    ...document.participants,
                    { id: newScenarioId("p"), kind: "system", systemId: event.target.value },
                  ],
                });
              }}
            >
              <option value="">+ System…</option>
              {systems
                .filter((system) => !document.participants.some((item) => item.systemId === system.id))
                .map((system) => <option key={system.id} value={system.id}>{system.name}</option>)}
            </select>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setDocument({
                participants: [...document.participants, { id: newScenarioId("actor"), kind: "actor", label: "User" }],
              })}
            >
              + Actor
            </button>
          </div>
        </header>
        <ul className="scenario-participants">
          {lifelines.map((lifeline) => {
            const used = flattenSteps(document.items).some(({ step }) => step.fromParticipantId === lifeline.id || step.toParticipantId === lifeline.id)
              || [...document.beforeState, ...document.afterState].some((entry) => entry.participantId === lifeline.id);
            const participant = document.participants.find((item) => item.id === lifeline.id);
            return (
              <li key={lifeline.id} className={lifeline.missing ? "missing" : undefined}>
                <span className={`scenario-kind-badge kind-${lifeline.kind}`}>{lifeline.kind === "actor" ? "Actor" : "System"}</span>
                {participant?.kind === "actor" ? (
                  <input
                    aria-label="Actor name"
                    value={participant.label ?? ""}
                    onChange={(event) => setDocument({
                      participants: document.participants.map((item) => (item.id === participant.id ? { ...item, label: event.target.value } : item)),
                    })}
                  />
                ) : (
                  <span>{lifeline.label}{lifeline.missing ? " (missing)" : ""}</span>
                )}
                {lifeline.implicit ? (
                  <span className="muted">from contract steps</span>
                ) : (
                  <button
                    type="button"
                    className="quiet-button"
                    disabled={used}
                    title={used ? "Used by steps or state data" : undefined}
                    onClick={() => setDocument({ participants: document.participants.filter((item) => item.id !== lifeline.id) })}
                  >
                    Remove
                  </button>
                )}
              </li>
            );
          })}
          {lifelines.length === 0 && <li className="muted">Add a system or actor, or add contract steps.</li>}
        </ul>
        {!scopeIntegrationId && (
          <>
            <h5>Participating contracts</h5>
            <div className="scenario-contract-picker">
              {allContracts.map((contract) => (
                <label key={contract.id} className="scenario-checkbox">
                  <input
                    type="checkbox"
                    checked={document.contractIds.includes(contract.id)}
                    disabled={document.contractIds.includes(contract.id) && contractSteps.some(({ step }) => step.contractId === contract.id)}
                    onChange={(event) => setDocument({
                      contractIds: event.target.checked
                        ? [...document.contractIds, contract.id]
                        : document.contractIds.filter((id) => id !== contract.id),
                    })}
                  />
                  {contract.name}
                </label>
              ))}
              {document.contractIds
                .filter((id) => !allContracts.some((contract) => contract.id === id))
                .map((id) => (
                  <label key={id} className="scenario-checkbox missing">
                    <input
                      type="checkbox"
                      checked
                      onChange={() => setDocument({ contractIds: document.contractIds.filter((entry) => entry !== id) })}
                    />
                    Missing contract
                  </label>
                ))}
              {allContracts.length === 0 && <p className="muted">No contracts exist yet.</p>}
            </div>
          </>
        )}
      </section>

      <StateEditor
        title="Before state"
        entries={document.beforeState}
        onChange={(beforeState) => setDocument({ beforeState })}
        index={index}
        document={document}
      />

      <section className="scenario-section">
        <h4>Message steps</h4>
        {!scopeIntegrationId && document.contractIds.length === 0 && (
          <p className="muted">Select participating contracts to add contract steps.</p>
        )}
        <ItemList items={document.items} context={context} />
        <AddStepButtons context={context} onAdd={(step) => context.setItems((items) => insertAfter(items, null, step))} />
      </section>

      <StateEditor
        title="After state"
        entries={document.afterState}
        onChange={(afterState) => setDocument({ afterState })}
        index={index}
        document={document}
      />

      <section className="scenario-section">
        <header className="scenario-section-header">
          <h4>Assertions</h4>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setDocument({ assertions: [...document.assertions, { id: newScenarioId("assert"), text: "" }] })}
          >
            Add assertion
          </button>
        </header>
        {document.assertions.length === 0 && <p className="muted">No assertions yet.</p>}
        {document.assertions.map((assertion) => {
          const step = contractSteps.find((item) => item.step.id === assertion.stepId)?.step;
          const receiver = step ? contractStepEndpoints(index, step.contractId, step.phase)?.receiverObjectId : null;
          const fields = fieldsOfObject(index, receiver);
          const status = evaluationAssertions.get(assertion.id);
          const update = (changes: Partial<typeof assertion>) => setDocument({
            assertions: document.assertions.map((item) => (item.id === assertion.id ? { ...item, ...changes } : item)),
          });
          return (
            <div key={assertion.id} className="scenario-assertion">
              <div className="scenario-inline-fields">
                <label className="grow">
                  Assertion
                  <input value={assertion.text} placeholder="What must be true" onChange={(event) => update({ text: event.target.value })} />
                </label>
                <label>
                  Step
                  <select value={assertion.stepId ?? ""} onChange={(event) => update({ stepId: event.target.value || null, fieldId: null })}>
                    <option value="">Manual check</option>
                    {contractSteps.map(({ step: option, number }) => (
                      <option key={option.id} value={option.id}>{number}. {stepSummary(option, context)}</option>
                    ))}
                  </select>
                </label>
                {assertion.stepId && (
                  <label>
                    Field
                    <select value={assertion.fieldId ?? ""} onChange={(event) => update({ fieldId: event.target.value || null })}>
                      <option value="">—</option>
                      {fields.map((field) => <option key={field.id} value={field.id}>{field.displayName}</option>)}
                    </select>
                  </label>
                )}
                {assertion.fieldId && (
                  <label>
                    Equals
                    <input
                      value={formatSampleValue(assertion.expected ?? "")}
                      onChange={(event) => update({ expected: parseSampleInput(event.target.value) })}
                    />
                  </label>
                )}
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => setDocument({ assertions: document.assertions.filter((item) => item.id !== assertion.id) })}
                >
                  Remove
                </button>
              </div>
              {status && <p className={`scenario-assertion-status status-${status.status}`}>{status.status.replace("_", " ")} — {status.message}</p>}
            </div>
          );
        })}
      </section>

      <section className="scenario-section">
        <h4>Notes</h4>
        <textarea rows={4} aria-label="Scenario notes" value={document.notes} onChange={(event) => setDocument({ notes: event.target.value })} />
      </section>
    </div>
  );
}
