import React from "react";
import type { EnterpriseArchitectureIndex } from "../../enterpriseArchitectureIndex";
import {
  archiveScenario,
  createScenario,
  evaluateScenario,
  listScenarios,
  loadArchitectureIndexFromApi,
  updateScenario,
  ScenarioApiError,
} from "../../scenarioApi";
import {
  PHASE_LABELS,
  categoryLabel,
  contractLabel,
  detectMissingReferences,
  duplicateScenarioDocument,
  emptyScenarioDocument,
  flattenSteps,
  formatSampleValue,
  type ScenarioEvaluation,
  type ScenarioPhase,
  type ScenarioRecord,
  type StepOutcome,
} from "../../scenarioModel";
import ScenarioEditor, { type ScenarioDraftState } from "./ScenarioEditor";
import SequenceDiagram from "./SequenceDiagram";

type Props = {
  /** Contract Designer passes the open contract; Landscape omits it for end-to-end scenarios. */
  scopeIntegrationId?: string | null;
  /** Landscape passes its already-loaded index; otherwise the workspace loads its own. */
  index?: EnterpriseArchitectureIndex | null;
  onOpenContractPhase: (contractId: string, phase: ScenarioPhase) => void;
};

type ViewMode = "diagram" | "steps";

function draftFromRecord(record: ScenarioRecord): ScenarioDraftState {
  return {
    name: record.name,
    category: record.category,
    description: record.description,
    document: record.document,
  };
}

function uniqueName(base: string, existing: readonly ScenarioRecord[]): string {
  const names = new Set(existing.map((item) => item.name.toLowerCase()));
  if (!names.has(base.toLowerCase())) return base.slice(0, 160);
  for (let counter = 2; counter < 1000; counter += 1) {
    const candidate = `${base} ${counter}`.slice(0, 160);
    if (!names.has(candidate.toLowerCase())) return candidate;
  }
  return `${base} ${Date.now()}`.slice(0, 160);
}

function clientValidation(draft: ScenarioDraftState): string | null {
  if (!draft.name.trim()) return "Enter a scenario name.";
  if (draft.document.assertions.some((item) => !item.text.trim())) return "Every assertion needs text.";
  const fragments: string[] = [];
  const walk = (items: ScenarioDraftState["document"]["items"]) => {
    for (const item of items) {
      if ("operands" in item) {
        if (item.kind === "alt" && item.operands.length < 2) fragments.push(item.id);
        item.operands.forEach((operand) => walk(operand.items));
      } else if (item.kind !== "contract" && !item.label?.trim()) {
        fragments.push(item.id);
      }
    }
  };
  walk(draft.document.items);
  return fragments.length ? "Every self call and message needs a label, and alt blocks need two branches." : null;
}

export default function ScenarioWorkspace({ scopeIntegrationId = null, index: providedIndex, onOpenContractPhase }: Props) {
  const [ownIndex, setOwnIndex] = React.useState<EnterpriseArchitectureIndex | null>(null);
  const [indexError, setIndexError] = React.useState<string | null>(null);
  const index = providedIndex ?? ownIndex;
  const [scenarios, setScenarios] = React.useState<ScenarioRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState<ScenarioDraftState | null>(null);
  const [dirty, setDirty] = React.useState(false);
  const [view, setView] = React.useState<ViewMode>("diagram");
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [evaluation, setEvaluation] = React.useState<ScenarioEvaluation | null>(null);

  React.useEffect(() => {
    if (providedIndex !== undefined) return;
    let cancelled = false;
    loadArchitectureIndexFromApi()
      .then((loaded) => { if (!cancelled) setOwnIndex(loaded); })
      .catch((error: unknown) => { if (!cancelled) setIndexError(error instanceof Error ? error.message : "Could not load contracts."); });
    return () => { cancelled = true; };
  }, [providedIndex]);

  const reload = React.useCallback(async (selectId?: string | null) => {
    setLoading(true);
    try {
      const records = await listScenarios(
        scopeIntegrationId ? { integrationId: scopeIntegrationId } : { scope: "landscape" },
      );
      setScenarios(records);
      const nextId = selectId !== undefined ? selectId : null;
      const selected = records.find((item) => item.id === nextId) ?? null;
      if (selected) {
        setSelectedId(selected.id);
        setDraft(draftFromRecord(selected));
        setDirty(false);
      }
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Could not load scenarios." });
    } finally {
      setLoading(false);
    }
  }, [scopeIntegrationId]);

  React.useEffect(() => {
    setSelectedId(null);
    setDraft(null);
    setDirty(false);
    void reload();
  }, [reload]);

  const selected = scenarios.find((item) => item.id === selectedId) ?? null;
  const isNew = draft !== null && selectedId === null;
  const recordScope = selected ? selected.scope_integration_id : scopeIntegrationId;

  const confirmDiscard = () => !dirty || window.confirm("Discard unsaved scenario changes?");

  const select = (record: ScenarioRecord) => {
    if (record.id === selectedId || !confirmDiscard()) return;
    setSelectedId(record.id);
    setDraft(draftFromRecord(record));
    setDirty(false);
    setEvaluation(null);
    setMessage(null);
  };

  const startNew = () => {
    if (!confirmDiscard()) return;
    setSelectedId(null);
    setDraft({
      name: uniqueName(scopeIntegrationId ? "New contract scenario" : "New end-to-end scenario", scenarios),
      category: "happy_path",
      description: null,
      document: emptyScenarioDocument(scopeIntegrationId),
    });
    setDirty(true);
    setView("steps");
    setEvaluation(null);
    setMessage(null);
  };

  const change = (next: ScenarioDraftState) => {
    setDraft(next);
    setDirty(true);
    setEvaluation(null);
  };

  const save = async () => {
    if (!draft) return;
    const problem = clientValidation(draft);
    if (problem) {
      setMessage({ kind: "error", text: problem });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const payload = { ...draft, name: draft.name.trim() };
      const saved = selected
        ? await updateScenario(selected.id, payload, selected.revision)
        : await createScenario(payload, scopeIntegrationId);
      await reload(saved.id);
      setMessage({ kind: "info", text: "Scenario saved." });
    } catch (error) {
      const text = error instanceof ScenarioApiError && error.status === 409 && selected
        ? `${error.message} Reload the scenario to see the latest version.`
        : error instanceof Error ? error.message : "Could not save the scenario.";
      setMessage({ kind: "error", text });
    } finally {
      setBusy(false);
    }
  };

  const duplicate = async () => {
    if (!draft || !confirmDiscard()) return;
    setBusy(true);
    try {
      const copy = await createScenario(
        {
          name: uniqueName(`${draft.name} (copy)`, scenarios),
          category: draft.category,
          description: draft.description,
          document: duplicateScenarioDocument(draft.document),
        },
        recordScope,
      );
      await reload(copy.id);
      setMessage({ kind: "info", text: "Scenario duplicated." });
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Could not duplicate the scenario." });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (isNew) {
      setDraft(null);
      setDirty(false);
      return;
    }
    if (!selected || !window.confirm(`Delete scenario "${selected.name}"? Contracts are not affected.`)) return;
    setBusy(true);
    try {
      await archiveScenario(selected.id);
      setSelectedId(null);
      setDraft(null);
      setDirty(false);
      await reload();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Could not delete the scenario." });
    } finally {
      setBusy(false);
    }
  };

  const evaluate = async () => {
    if (!draft) return;
    setBusy(true);
    setMessage(null);
    try {
      setEvaluation(await evaluateScenario(draft.document, recordScope));
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Could not evaluate the scenario." });
    } finally {
      setBusy(false);
    }
  };

  const outcomes = React.useMemo(
    () => new Map<string, StepOutcome>(evaluation?.steps.map((item) => [item.stepId, item.outcome]) ?? []),
    [evaluation],
  );
  const warnings = React.useMemo(
    () => (draft ? detectMissingReferences(draft.document, index) : []),
    [draft, index],
  );

  return (
    <div className={`scenario-workspace${scopeIntegrationId ? " scoped" : ""}`}>
      <aside className="scenario-list-panel" aria-label="Scenarios">
        <header>
          <h3>{scopeIntegrationId ? "Contract scenarios" : "End-to-end scenarios"}</h3>
          <button type="button" onClick={startNew} disabled={busy}>New scenario</button>
        </header>
        {loading && <p className="muted">Loading scenarios…</p>}
        {!loading && scenarios.length === 0 && !isNew && (
          <p className="muted">
            {scopeIntegrationId
              ? "No scenarios use this contract yet. Scenarios describe example interactions and never change the contract."
              : "No end-to-end scenarios yet. Combine several contracts into one documented flow."}
          </p>
        )}
        <ul>
          {isNew && (
            <li>
              <button type="button" className="scenario-list-item active">
                <span className="scenario-list-name">{draft?.name || "New scenario"}</span>
                <span className="scenario-list-meta">Unsaved</span>
              </button>
            </li>
          )}
          {scenarios.map((record) => (
            <li key={record.id}>
              <button
                type="button"
                className={`scenario-list-item${record.id === selectedId ? " active" : ""}`}
                onClick={() => select(record)}
              >
                <span className="scenario-list-name">{record.name}</span>
                <span className="scenario-list-meta">
                  <span className={`scenario-category category-${record.category}`}>{categoryLabel(record.category)}</span>
                  {scopeIntegrationId && !record.scope_integration_id && <span className="scenario-scope-badge">End-to-end</span>}
                  <span>{flattenSteps(record.document.items).length} steps</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="scenario-main">
        {indexError && <p className="error">{indexError}</p>}
        {!draft ? (
          <div className="scenario-placeholder">
            <p className="muted">Select a scenario or create a new one. Scenarios are design-time documentation: they reuse the contract mappings for sample evaluation and never run integrations.</p>
          </div>
        ) : (
          <>
            <header className="scenario-toolbar">
              <div className="scenario-title">
                <h3>{draft.name || "Untitled scenario"}{dirty && <span className="scenario-dirty" title="Unsaved changes"> •</span>}</h3>
                <span className={`scenario-category category-${draft.category}`}>{categoryLabel(draft.category)}</span>
                {!recordScope && <span className="scenario-scope-badge">End-to-end</span>}
              </div>
              <div className="scenario-view-switch" role="tablist" aria-label="Scenario view">
                <button type="button" role="tab" aria-selected={view === "diagram"} className={view === "diagram" ? "active" : ""} onClick={() => setView("diagram")}>
                  Sequence Diagram
                </button>
                <button type="button" role="tab" aria-selected={view === "steps"} className={view === "steps" ? "active" : ""} onClick={() => setView("steps")}>
                  Steps
                </button>
              </div>
              <div className="scenario-actions">
                <button type="button" className="secondary-button" onClick={evaluate} disabled={busy}>Evaluate samples</button>
                <button type="button" className="secondary-button" onClick={duplicate} disabled={busy || isNew}>Duplicate</button>
                <button type="button" className="danger-button" onClick={remove} disabled={busy}>{isNew ? "Discard" : "Delete"}</button>
                <button type="button" onClick={save} disabled={busy || !dirty}>{busy ? "Working…" : "Save"}</button>
              </div>
            </header>
            {message && <p className={message.kind === "error" ? "error scenario-message-banner" : "scenario-message-banner info"} role="status">{message.text}</p>}
            {warnings.length > 0 && (
              <div className="scenario-warnings" role="alert">
                <strong>Missing references</strong>
                <ul>{[...new Set(warnings.map((item) => item.message))].map((text) => <li key={text}>{text}</li>)}</ul>
              </div>
            )}
            {evaluation && (
              <div className="scenario-evaluation-summary">
                <strong>Sample evaluation</strong>
                <span className="outcome-ok">{evaluation.summary.ok ?? 0} ok</span>
                <span className="outcome-mismatch">{evaluation.summary.mismatch ?? 0} mismatched</span>
                <span className="outcome-failed">{evaluation.summary.failed ?? 0} failed</span>
                <span>{evaluation.summary.assertionsPassed ?? 0} assertions passed, {evaluation.summary.assertionsFailed ?? 0} failed</span>
                <span className="muted">Design-time only — nothing was sent to any system.</span>
              </div>
            )}
            {view === "diagram" ? (
              <div className="scenario-diagram-view">
                <SequenceDiagram
                  document={draft.document}
                  index={index}
                  outcomes={outcomes}
                  onOpenContractPhase={onOpenContractPhase}
                />
                <ScenarioSummary draft={draft} index={index} evaluation={evaluation} />
              </div>
            ) : (
              <ScenarioEditor
                draft={draft}
                onChange={change}
                index={index}
                scopeIntegrationId={recordScope}
                evaluation={evaluation}
                onOpenContractPhase={onOpenContractPhase}
              />
            )}
          </>
        )}
      </section>
    </div>
  );
}

function ScenarioSummary({
  draft,
  index,
  evaluation,
}: {
  draft: ScenarioDraftState;
  index: EnterpriseArchitectureIndex | null;
  evaluation: ScenarioEvaluation | null;
}) {
  const { document } = draft;
  const fieldName = (id: string) => index?.fieldsById.get(id)?.displayName ?? "Missing field";
  const objectName = (id: string) => index?.objectsById.get(id)?.displayName ?? "Missing object";
  const stateList = (entries: typeof document.beforeState) => entries.length === 0
    ? <p className="muted">None recorded.</p>
    : (
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <strong>{objectName(entry.objectId)}</strong>
            {Object.entries(entry.values).map(([fieldId, value]) => (
              <span key={fieldId} className="scenario-kv">{fieldName(fieldId)} = {formatSampleValue(value)}</span>
            ))}
            {entry.note && <em> — {entry.note}</em>}
          </li>
        ))}
      </ul>
    );
  const assertionStatus = new Map(evaluation?.assertions.map((item) => [item.assertionId, item.status]) ?? []);
  const contracts = [...new Set([
    ...document.contractIds,
    ...flattenSteps(document.items).map((item) => item.step.contractId).filter((id): id is string => !!id),
  ])];
  const phases = [...new Set(flattenSteps(document.items).map((item) => item.step.phase).filter(Boolean))] as ScenarioPhase[];
  return (
    <div className="scenario-summary">
      {draft.description && <p>{draft.description}</p>}
      <dl>
        <dt>Preconditions</dt>
        <dd>{document.preconditions || <span className="muted">—</span>}</dd>
        <dt>Trigger</dt>
        <dd>{document.trigger || <span className="muted">—</span>}</dd>
        <dt>Contracts</dt>
        <dd>{contracts.length ? contracts.map((id) => contractLabel(index, id)).join(", ") : <span className="muted">—</span>}</dd>
        <dt>Phases</dt>
        <dd>{phases.length ? phases.map((phase) => PHASE_LABELS[phase]).join(", ") : <span className="muted">—</span>}</dd>
      </dl>
      <div className="scenario-two-column">
        <div>
          <h5>Before state</h5>
          {stateList(document.beforeState)}
        </div>
        <div>
          <h5>After state</h5>
          {stateList(document.afterState)}
        </div>
      </div>
      <h5>Assertions</h5>
      {document.assertions.length === 0 ? <p className="muted">None.</p> : (
        <ul className="scenario-assertion-list">
          {document.assertions.map((assertion) => (
            <li key={assertion.id} className={`status-${assertionStatus.get(assertion.id) ?? "pending"}`}>
              {assertion.text}
              {assertion.fieldId && <span className="scenario-kv">{fieldName(assertion.fieldId)} = {formatSampleValue(assertion.expected)}</span>}
              {assertionStatus.get(assertion.id) && <span className="scenario-assertion-tag">{assertionStatus.get(assertion.id)!.replace("_", " ")}</span>}
            </li>
          ))}
        </ul>
      )}
      {document.notes && (
        <>
          <h5>Notes</h5>
          <p className="scenario-notes">{document.notes}</p>
        </>
      )}
    </div>
  );
}
