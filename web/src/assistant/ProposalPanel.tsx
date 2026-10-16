/**
 * Architecture Assistant proposal panel.
 *
 * Renders one authoritative helper change set (fetched from the helper API) with
 * bounded, collapsible sections and closed resolution controls. It never renders
 * unbounded JSON and offers no Approve, Apply, or Undo action.
 */

import React from "react";

import { fetchChangeSet, resolveChangeSet, validateChangeSet } from "./assistantApi";
import { buildPreview } from "./assistantPreview";
import type { ChangeSetDetail, ProposalDecision, ProposalOperation } from "./assistantTypes";

const SCALAR_FIELDS: Record<string, string[]> = {
  create_contract: ["name", "purpose", "implementation_status"],
  configure_resilience: ["name"],
  create_object: ["name", "description"],
  create_link: ["cardinality", "source_optional", "target_optional"],
  record_interaction: ["cardinality", "source_optional", "target_optional"],
  create_scenario: ["name"],
  define_conformance_expectation: ["coverage_min", "expected_success"],
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  validation_failed: "Validation failed",
  validated: "Validated",
  stale: "Stale",
  approved: "Approved (external, read-only)",
  applied: "Applied (read-only history)",
  undone: "Undone (read-only history)",
  failed: "Failed",
};

export interface ProposalPanelProps {
  workspaceId: string | null;
  changeSetId: string | null;
  onClose?: () => void;
}

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
        onResolve({
          operation_id: decision.operation_id,
          kind: decision.kind,
          field,
          value,
        });
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
          onClick={() =>
            onResolve({ operation_id: decision.operation_id, kind: "remove_operation" })
          }
        >
          Remove operation
        </button>
      </div>
    </li>
  );
}

function operationLabel(operation: ProposalOperation): string {
  const proposed = (operation.proposed_value ?? {}) as Record<string, unknown>;
  return String(proposed.name ?? operation.temporary_id ?? operation.target_id ?? operation.operation_id);
}

export function ProposalPanel({ workspaceId, changeSetId, onClose }: ProposalPanelProps) {
  const [detail, setDetail] = React.useState<ChangeSetDetail | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    setDetail(null);
    setError("");
    if (!workspaceId || !changeSetId) return;
    let cancelled = false;
    void fetchChangeSet(workspaceId, changeSetId)
      .then((value) => {
        if (!cancelled) setDetail(value);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load proposal");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, changeSetId]);

  if (!changeSetId) return null;
  if (error) {
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
  const ready = Boolean(validation.ready_for_approval);
  const unresolved = detail.unresolved_details ?? [];
  const ordered = [...detail.operations].sort((a, b) => a.ordinal - b.ordinal);

  async function applyResolution(resolution: Record<string, unknown>) {
    if (!workspaceId || !changeSetId) return;
    setBusy(true);
    try {
      setDetail(await resolveChangeSet(workspaceId, changeSetId, [resolution]));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Resolution failed");
    } finally {
      setBusy(false);
    }
  }

  async function requestValidation() {
    if (!workspaceId || !changeSetId) return;
    setBusy(true);
    try {
      setDetail(await validateChangeSet(workspaceId, changeSetId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Validation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="proposal-panel" data-testid="proposal-panel" data-status={detail.status}>
      <header className="proposal-header">
        <h3>Proposal</h3>
        <span className="proposal-status" data-status={detail.status}>
          {STATUS_LABELS[detail.status] ?? detail.status}
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
        <button type="button" onClick={() => void requestValidation()} disabled={busy}>
          Validate
        </button>
        <span className="proposal-ready" data-ready={ready}>
          {ready ? "Ready for review" : "Decisions required"}
        </span>
      </div>

      <Section title={`Reused objects (${detail.reused_objects.length})`}>
        <ul>
          {detail.reused_objects.map((item) => (
            <li key={`${item.target_type}:${item.target_id}`} data-badge="reused">
              {item.target_type} · {item.target_id}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Proposed objects (${detail.proposed_objects.length})`}>
        <ul>
          {detail.proposed_objects.map((item) => (
            <li key={String(item.temporary_id)} data-badge="added">
              {item.target_type} · {item.temporary_id}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Unresolved decisions (${unresolved.length})`} >
        {unresolved.length === 0 ? (
          <p>No open decisions.</p>
        ) : (
          <ul className="proposal-decisions" data-testid="proposal-decisions">
            {unresolved.map((decision) => (
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
          {detail.validated_at
            ? `Validated ${detail.validated_at}`
            : "Not validated"}
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
