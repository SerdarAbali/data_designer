/**
 * Architecture Assistant proposal panel.
 *
 * Renders one authoritative helper change set (fetched from the helper API) with
 * bounded, collapsible sections, closed resolution controls, and the explicit
 * user-controlled Validate / Approve / Apply / Undo lifecycle. Approve, Apply,
 * and Undo are invoked only by the authenticated browser through the existing
 * helper-action API; the model has no tool that performs them. It never renders
 * unbounded JSON and never shows optimistic success before the backend confirms.
 */

import React from "react";

import {
  applyChangeSet,
  approveChangeSet,
  fetchChangeSet,
  recordProposalEvent,
  resolveChangeSet,
  undoChangeSet,
  validateChangeSet,
} from "./assistantApi";
import { buildPreview } from "./assistantPreview";
import {
  LIFECYCLE_LABELS,
  canApply,
  canApprove,
  canUndo,
  canValidate,
  hasRequiredUnresolved,
  humanizeId,
  operationCounts,
  proposalLifecycle,
} from "./assistantModel";
import type {
  ApplyResult,
  ChangeSetDetail,
  ProposalDecision,
  ProposalOperation,
  UndoResult,
} from "./assistantTypes";

const SCALAR_FIELDS: Record<string, string[]> = {
  create_contract: ["name", "purpose", "implementation_status"],
  configure_resilience: ["name"],
  create_object: ["name", "description"],
  create_link: ["cardinality", "source_optional", "target_optional"],
  record_interaction: ["cardinality", "source_optional", "target_optional"],
  create_scenario: ["name"],
  define_conformance_expectation: ["coverage_min", "expected_success"],
};

const APPLY_COUNT_GROUPS: { key: string; label: string }[] = [
  { key: "create_object", label: "Objects to create" },
  { key: "include_object", label: "Objects to reuse" },
  { key: "override_object", label: "Objects to change" },
  { key: "create_link", label: "Relationships" },
  { key: "record_interaction", label: "Memberships" },
  { key: "set_realization", label: "Realizations" },
  { key: "reuse_contract", label: "Contracts reused" },
  { key: "create_contract", label: "Contracts to create" },
  { key: "create_mapping", label: "Mappings" },
  { key: "create_transformation", label: "Transformations" },
  { key: "configure_resilience", label: "Resilience" },
  { key: "create_scenario", label: "Scenarios" },
  { key: "define_conformance_expectation", label: "Conformance expectations" },
];

export interface ProposalPanelProps {
  workspaceId: string | null;
  workspaceName?: string;
  conversationId?: string | null;
  changeSetId: string | null;
  onApplied?: (result: ApplyResult) => void;
  onUndone?: () => void;
  onClearHighlights?: () => void;
  onClose?: () => void;
}

type PendingAction = "approve" | "apply" | "undo" | null;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="proposal-section" open>
      <summary>{title}</summary>
      <div className="proposal-section-body">{children}</div>
    </details>
  );
}

function DecisionControl({
  decision,
  onResolve,
}: {
  decision: ProposalDecision;
  onResolve: (resolution: Record<string, unknown>) => void;
}) {
  const [value, setValue] = React.useState("");
  const [field, setField] = React.useState(SCALAR_FIELDS.create_object[0]);
  const [intent, setIntent] = React.useState("independent");
  const options = decision.options.filter((option) => option.object_id);

  const submit = () => {
    switch (decision.kind) {
      case "choose_catalog_field":
        onResolve({ operation_id: decision.operation_id, kind: decision.kind, catalog_field_id: value });
        break;
      case "choose_canonical_object":
        onResolve({ operation_id: decision.operation_id, kind: decision.kind, object_id: value });
        break;
      case "create_new_architecture_object":
        onResolve({
          operation_id: decision.operation_id,
          kind: decision.kind,
          name: value || decision.question.slice(0, 60),
        });
        break;
      case "set_scalar":
        onResolve({ operation_id: decision.operation_id, kind: decision.kind, field, value });
        break;
      case "choose_contract_intent":
        onResolve({ operation_id: decision.operation_id, kind: decision.kind, proposal_intent: intent });
        break;
      default:
        onResolve({ operation_id: decision.operation_id, kind: "remove_operation" });
    }
  };

  return (
    <li className="proposal-decision" data-kind={decision.kind}>
      <p className="proposal-question">
        {decision.question} <em>{decision.required ? "required" : "optional"}</em>
      </p>
      <p className="proposal-explanation">{decision.explanation}</p>
      <div className="proposal-decision-controls">
        {decision.kind === "choose_canonical_object" && options.length > 0 ? (
          <select
            aria-label={`Choose object for ${decision.operation_id}`}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          >
            <option value="">Select…</option>
            {options.map((option) => (
              <option key={option.key} value={String(option.object_id)}>
                {option.label || option.key}
              </option>
            ))}
          </select>
        ) : null}
        {decision.kind === "set_scalar" ? (
          <select aria-label="Scalar field" value={field} onChange={(event) => setField(event.target.value)}>
            {(SCALAR_FIELDS.create_object ?? []).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        ) : null}
        {decision.kind === "choose_contract_intent" ? (
          <select aria-label="Contract intent" value={intent} onChange={(event) => setIntent(event.target.value)}>
            <option value="independent">independent</option>
            <option value="alternative">alternative</option>
            <option value="proposed_replacement">proposed_replacement</option>
          </select>
        ) : null}
        {!(decision.kind === "choose_canonical_object" && options.length > 0) &&
        decision.kind !== "choose_contract_intent" ? (
          <input
            aria-label={`Resolution value for ${decision.operation_id}`}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={decision.kind === "choose_catalog_field" ? "Catalog field id" : "value"}
          />
        ) : null}
        <button type="button" onClick={submit} data-testid={`resolve-${decision.operation_id}`}>
          Apply decision
        </button>
        <button
          type="button"
          onClick={() => onResolve({ operation_id: decision.operation_id, kind: "remove_operation" })}
        >
          Remove operation
        </button>
      </div>
    </li>
  );
}

function operationLabel(operation: ProposalOperation): string {
  const proposed = (operation.proposed_value ?? {}) as Record<string, unknown>;
  const name = proposed.name;
  if (name) return String(name);
  return (
    humanizeId(operation.temporary_id) ||
    humanizeId(operation.target_id) ||
    operation.operation_id
  );
}

function errorCode(caught: unknown): string {
  const detail = (caught as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object" && "code" in detail) {
    const code = (detail as { code?: unknown }).code;
    if (typeof code === "string") return code.replace(/[^a-z0-9_]/gi, "").slice(0, 40);
  }
  return "action_failed";
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "The action failed.";
}

export function ProposalPanel({
  workspaceId,
  workspaceName,
  conversationId,
  changeSetId,
  onApplied,
  onUndone,
  onClearHighlights,
  onClose,
}: ProposalPanelProps) {
  const [detail, setDetail] = React.useState<ChangeSetDetail | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [applying, setApplying] = React.useState(false);
  const [applyFailed, setApplyFailed] = React.useState(false);
  const [applyResult, setApplyResult] = React.useState<ApplyResult | null>(null);
  const [undoResult, setUndoResult] = React.useState<UndoResult | null>(null);
  const [undoConflict, setUndoConflict] = React.useState(false);
  const [pending, setPending] = React.useState<PendingAction>(null);

  React.useEffect(() => {
    setDetail(null);
    setError("");
    setApplyResult(null);
    setUndoResult(null);
    setApplyFailed(false);
    setUndoConflict(false);
    setPending(null);
    onClearHighlights?.();
    if (!workspaceId || !changeSetId) return;
    let cancelled = false;
    void fetchChangeSet(workspaceId, changeSetId)
      .then((value) => {
        if (!cancelled) setDetail(value);
      })
      .catch((caught) => {
        if (!cancelled) setError(errorMessage(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, changeSetId]);

  async function emitEvent(action: string, reasonCode?: string) {
    if (!workspaceId || !conversationId || !changeSetId) return;
    try {
      await recordProposalEvent(workspaceId, conversationId, changeSetId, action, reasonCode);
    } catch {
      /* conversation events are best-effort; helper records stay authoritative */
    }
  }

  async function runValidate() {
    if (!workspaceId || !changeSetId || busy) return;
    setBusy(true);
    setError("");
    try {
      setDetail(await validateChangeSet(workspaceId, changeSetId));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function runApprove() {
    if (!workspaceId || !changeSetId || busy) return;
    setBusy(true);
    setError("");
    setPending(null);
    await emitEvent("approval_started");
    try {
      setDetail(await approveChangeSet(workspaceId, changeSetId));
      await emitEvent("approved");
    } catch (caught) {
      const code = errorCode(caught);
      setError(errorMessage(caught));
      await emitEvent("approval_failed", code);
    } finally {
      setBusy(false);
    }
  }

  async function runApply() {
    if (!workspaceId || !changeSetId || busy) return;
    setBusy(true);
    setApplying(true);
    setError("");
    setApplyFailed(false);
    setPending(null);
    await emitEvent("apply_started");
    try {
      const result = await applyChangeSet(workspaceId, changeSetId);
      setApplyResult(result);
      setDetail(result.change_set);
      setApplying(false);
      await emitEvent("applied");
      onApplied?.(result);
    } catch (caught) {
      const code = errorCode(caught);
      setApplying(false);
      setApplyFailed(true);
      setError(errorMessage(caught));
      await emitEvent("apply_failed", code);
    } finally {
      setBusy(false);
    }
  }

  async function runUndo() {
    if (!workspaceId || !changeSetId || busy) return;
    setBusy(true);
    setError("");
    setUndoConflict(false);
    setPending(null);
    await emitEvent("undo_started");
    try {
      const result = await undoChangeSet(workspaceId, changeSetId);
      setUndoResult(result);
      setDetail(result.change_set);
      await emitEvent("undone");
      onUndone?.();
    } catch (caught) {
      const detailValue = (caught as { detail?: { conflicts?: UndoResult["conflicts"] } })?.detail;
      setUndoConflict(true);
      setError(errorMessage(caught));
      if (detailValue?.conflicts) {
        setUndoResult({
          change_set: detail ?? ({} as ChangeSetDetail),
          status: "conflict",
          undone_operation_count: 0,
          undone_operations: [],
          preserved_objects: [],
          warnings: [],
          conflicts: detailValue.conflicts,
        });
      }
      await emitEvent("undo_conflict", errorCode(caught));
    } finally {
      setBusy(false);
    }
  }

  async function applyResolution(resolution: Record<string, unknown>) {
    if (!workspaceId || !changeSetId || busy) return;
    setBusy(true);
    try {
      setDetail(await resolveChangeSet(workspaceId, changeSetId, [resolution]));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!changeSetId) return null;
  if (error && !detail) {
    return (
      <section className="proposal-panel" data-testid="proposal-panel">
        <p className="assistant-error" role="alert">
          {error}
        </p>
      </section>
    );
  }
  if (!detail) {
    return (
      <section className="proposal-panel" data-testid="proposal-panel">
        <p>Loading proposal…</p>
      </section>
    );
  }

  const preview = buildPreview(detail.operations);
  const validation = detail.validation_summary ?? {};
  const counts = operationCounts(detail.operations);
  const lifecycle = proposalLifecycle(detail, { applying, applyFailed, undoConflict });
  const ordered = [...detail.operations].sort((a, b) => a.ordinal - b.ordinal);
  const unresolvedRequired = hasRequiredUnresolved(detail);

  return (
    <section className="proposal-panel" data-testid="proposal-panel" data-status={detail.status}>
      <header className="proposal-header">
        <h3>Proposal</h3>
        <span className="proposal-status" data-lifecycle={lifecycle}>
          {LIFECYCLE_LABELS[lifecycle]}
        </span>
        {onClose ? (
          <button type="button" onClick={onClose} aria-label="Close proposal">
            Close
          </button>
        ) : null}
      </header>

      <p className="proposal-summary">{detail.summary}</p>
      <p className="proposal-meta">
        {detail.helper_name} · {detail.state_type ?? "unknown state"} · hash{" "}
        {(detail.proposal_hash ?? "").slice(0, 12) || "—"}
      </p>

      <div className="proposal-actions">
        <button
          type="button"
          onClick={() => void runValidate()}
          disabled={busy || !canValidate(detail)}
        >
          Validate
        </button>
        <button
          type="button"
          data-testid="approve-button"
          onClick={() => setPending("approve")}
          disabled={busy || !canApprove(detail)}
        >
          Approve
        </button>
        <button
          type="button"
          data-testid="apply-button"
          onClick={() => setPending("apply")}
          disabled={busy || !canApply(detail)}
        >
          Apply
        </button>
        <button
          type="button"
          data-testid="undo-button"
          onClick={() => setPending("undo")}
          disabled={busy || !canUndo(detail)}
        >
          Undo
        </button>
        <span className="proposal-ready" data-ready={!unresolvedRequired}>
          {unresolvedRequired ? "Decisions required" : "Ready for review"}
        </span>
      </div>

      {error ? (
        <p className="assistant-error" role="alert" data-testid="proposal-error">
          {error}
        </p>
      ) : null}

      {pending ? (
        <div className="proposal-dialog" role="dialog" aria-modal="true" data-testid="confirm-dialog">
          <h4>
            {pending === "approve" ? "Approve proposal?" : pending === "apply" ? "Apply proposal?" : "Undo proposal?"}
          </h4>
          {pending === "approve" ? (
            <>
              <p>
                Approving records your approval only. It does <strong>not</strong> apply any changes to
                the architecture.
              </p>
              <ul className="proposal-confirm-list">
                <li>Operations: {Object.values(counts).reduce((sum, value) => sum + value, 0)}</li>
                <li>Reused objects: {detail.reused_objects.length}</li>
                <li>New objects: {detail.proposed_objects.length}</li>
                <li>Contracts: {counts.create_contract ?? 0} new · {counts.reuse_contract ?? 0} reused</li>
                <li>Scenarios: {counts.create_scenario ?? 0}</li>
                <li>Target state: {detail.state_type ?? "unknown"}</li>
                <li>Affected disciplines: {preview.affectedDisciplines.join(", ") || "—"}</li>
                <li>Hash: {(detail.proposal_hash ?? "").slice(0, 12)}</li>
              </ul>
              {unresolvedRequired ? <p className="proposal-warning">Required decisions remain.</p> : null}
            </>
          ) : null}
          {pending === "apply" ? (
            <>
              <p>Apply writes the approved operations into the target state.</p>
              <ul className="proposal-confirm-list">
                <li>Workspace: {workspaceName ?? "this workspace"}</li>
                <li>Target state: {detail.state_type ?? "unknown"}</li>
                {APPLY_COUNT_GROUPS.filter((group) => counts[group.key]).map((group) => (
                  <li key={group.key}>
                    {group.label}: {counts[group.key]}
                  </li>
                ))}
                <li>Affected workbenches: {preview.affectedDisciplines.join(", ") || "—"}</li>
              </ul>
              {detail.warnings.length > 0 ? (
                <p className="proposal-warning">{detail.warnings.length} warning(s) remain.</p>
              ) : null}
            </>
          ) : null}
          {pending === "undo" ? (
            <>
              <p>
                Undo is all-or-nothing. It removes only the data this change set created; reused
                Catalog records and canonical objects are preserved. Later edits or external
                references can block undo, in which case nothing is undone.
              </p>
            </>
          ) : null}
          <div className="proposal-dialog-actions">
            <button
              type="button"
              data-testid="confirm-action"
              onClick={() =>
                void (pending === "approve" ? runApprove() : pending === "apply" ? runApply() : runUndo())
              }
              disabled={busy}
            >
              Confirm {pending}
            </button>
            <button type="button" onClick={() => setPending(null)} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {applyResult ? (
        <Section title="Apply results">
          <ul className="proposal-results" data-testid="apply-results">
            <li>Applied operations: {applyResult.applied_operation_count}</li>
            <li>Affected workbenches: {applyResult.affected_workbenches.join(", ") || "—"}</li>
            <li>Audit reference: {applyResult.audit_event_ref ?? "—"}</li>
          </ul>
          {onClearHighlights ? (
            <button type="button" onClick={onClearHighlights} data-testid="clear-highlights">
              Clear highlights
            </button>
          ) : null}
          <p className="proposal-meta">Created / reused objects</p>
          <ul>
            {applyResult.applied_operations.map((operation) => (
              <li key={operation.operation_id}>
                <code>{operation.domain_action}</code> · {operation.role ?? "applied"} ·{" "}
                {operation.applied_id}
              </li>
            ))}
          </ul>
          {applyResult.contract_revisions.length > 0 ? (
            <>
              <p className="proposal-meta">Contracts</p>
              <ul>
                {applyResult.contract_revisions.map((revision) => (
                  <li key={revision.contract_id}>
                    {revision.contract_id} · revision {revision.revision} · {revision.role}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {Object.keys(applyResult.resolution_map).length > 0 ? (
            <>
              <p className="proposal-meta">Temporary-ID resolution</p>
              <ul>
                {Object.entries(applyResult.resolution_map).map(([temp, real]) => (
                  <li key={temp}>
                    <code>{temp}</code> → {real}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </Section>
      ) : null}

      {undoConflict && undoResult?.conflicts?.length ? (
        <Section title="Undo conflict">
          <p className="proposal-warning" data-testid="undo-conflict">
            No changes were undone. Undo was refused because of the following conflicts.
          </p>
          <ul>
            {undoResult.conflicts.map((conflict, index) => (
              <li key={index}>
                {conflict.code ?? "conflict"}
                {conflict.operation_id ? ` · ${conflict.operation_id}` : ""}: {conflict.message}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {undoResult && !undoConflict ? (
        <Section title="Undo result">
          <p data-testid="undo-result">
            Undone operations: {undoResult.undone_operation_count}. Preserved objects:{" "}
            {undoResult.preserved_objects.length}.
          </p>
        </Section>
      ) : null}

      <Section title={`Reused objects (${detail.reused_objects.length})`}>
        <ul>
          {detail.reused_objects.map((item) => (
            <li key={`${item.target_type}:${item.target_id}`} data-badge="reused">
              {item.name || humanizeId(item.target_id) || item.target_type}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Proposed objects (${detail.proposed_objects.length})`}>
        <ul>
          {detail.proposed_objects.map((item) => (
            <li key={String(item.temporary_id)} data-badge="added">
              {item.name || item.temporary_id || item.target_type}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Unresolved decisions (${(detail.unresolved_details ?? []).length})`}>
        {(detail.unresolved_details ?? []).length === 0 ? (
          <p>No open decisions.</p>
        ) : (
          <ul className="proposal-decisions" data-testid="proposal-decisions">
            {(detail.unresolved_details ?? []).map((decision) => (
              <DecisionControl
                key={decision.decision_id}
                decision={decision}
                onResolve={(resolution) => void applyResolution(resolution)}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Assumptions (${detail.assumptions.length})`}>
        <ul>
          {detail.assumptions.map((item, index) => (
            <li key={index}>{String(item)}</li>
          ))}
        </ul>
      </Section>

      <Section title={`Warnings (${detail.warnings.length})`}>
        <ul>
          {detail.warnings.map((item, index) => (
            <li key={index}>{String(item)}</li>
          ))}
        </ul>
      </Section>

      <Section title="Validation">
        <p data-testid="validation-summary">
          {detail.validated_at ? `Validated ${detail.validated_at}` : "Not validated"}
          {typeof validation.valid === "number" ? ` · ${validation.valid} valid` : ""}
          {typeof validation.invalid === "number" ? ` · ${validation.invalid} invalid` : ""}
          {typeof validation.unresolved === "number" ? ` · ${validation.unresolved} unresolved` : ""}
        </p>
        {Array.isArray(validation.issues) && validation.issues.length > 0 ? (
          <ul className="proposal-issues">
            {(validation.issues as { message?: string; code?: string }[]).slice(0, 20).map((issue, index) => (
              <li key={index}>{issue.message ?? issue.code}</li>
            ))}
          </ul>
        ) : null}
      </Section>

      <Section title={`Affected disciplines (${preview.affectedDisciplines.length})`}>
        <p>{preview.affectedDisciplines.join(", ") || "—"}</p>
        <p className="proposal-preview-counts" data-testid="preview-counts">
          {preview.nodes.length} preview nodes · {preview.edges.length} preview edges
        </p>
        {preview.unsupported.length > 0 ? (
          <p className="proposal-meta">Not previewable: {preview.unsupported.join(", ")}</p>
        ) : null}
      </Section>

      <Section title={`Operations (${ordered.length})`}>
        <ol className="proposal-operations" data-testid="proposal-operations">
          {ordered.map((operation) => (
            <li
              key={operation.operation_id}
              data-action={operation.domain_action}
              data-resolution={operation.resolution_state}
            >
              <code>{operation.domain_action}</code> · {operationLabel(operation)} ·{" "}
              {operation.validation_status}
              {operation.depends_on.length > 0 ? (
                <span className="proposal-deps"> ← {operation.depends_on.join(", ")}</span>
              ) : null}
            </li>
          ))}
        </ol>
      </Section>
    </section>
  );
}
