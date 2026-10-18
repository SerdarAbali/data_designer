import { useCallback, useEffect, useState } from "react";

import {
  EVIDENCE_CLASSIFICATIONS,
  EVIDENCE_CONFIDENCES,
  EVIDENCE_SOURCE_TYPES,
  EVIDENCE_VERIFICATION_STATUSES,
  evidenceApplicabilityLabel,
  evidenceClassificationLabel,
  evidenceGroupOf,
  evidenceRecordedAtLabel,
  groupEvidence,
  type EvidenceClassification,
  type EvidenceConfidence,
  type EvidenceRecord,
  type EvidenceSourceType,
  type EvidenceTargetKind,
  type EvidenceVerificationStatus,
} from "../../evidence";
import {
  createEvidence,
  deleteEvidence,
  listEvidence,
  updateEvidence,
} from "../../evidenceApi";
import {
  EVIDENCE_CONFIDENCE_LABELS,
  EVIDENCE_SOURCE_TYPE_LABELS,
  EVIDENCE_VERIFICATION_LABELS,
} from "../../evidence";

type Props = {
  workspaceId: string;
  stateId: string | null;
  targetKind: EvidenceTargetKind;
  targetId: string | null;
  /** Current is read-only, so evidence is display-only there. */
  readOnly: boolean;
};

type FormState = {
  evidence_classification: EvidenceClassification;
  source_type: EvidenceSourceType;
  source_title: string;
  source_reference: string;
  source_locator: string;
  summary: string;
  confidence: EvidenceConfidence;
  verification_status: EvidenceVerificationStatus;
};

const EMPTY_FORM: FormState = {
  evidence_classification: "confirmed_by_requirements_document",
  source_type: "document",
  source_title: "",
  source_reference: "",
  source_locator: "",
  summary: "",
  confidence: "medium",
  verification_status: "unverified",
};

function formFrom(record: EvidenceRecord): FormState {
  return {
    evidence_classification: record.evidence_classification,
    source_type: record.source_type,
    source_title: record.source_title,
    source_reference: record.source_reference,
    source_locator: record.source_locator ?? "",
    summary: record.summary,
    confidence: record.confidence,
    verification_status: record.verification_status,
  };
}

function validate(form: FormState): string {
  if (!form.source_title.trim()) return "A source title is required.";
  if (!form.source_reference.trim()) return "A source reference is required.";
  if (!form.summary.trim()) return "A summary is required.";
  if (form.source_title.length > 300) return "The source title must be 300 characters or fewer.";
  if (form.source_reference.length > 2000) return "The source reference must be 2000 characters or fewer.";
  if (form.source_locator.length > 2000) return "The source locator must be 2000 characters or fewer.";
  if (form.summary.length > 2000) return "The summary must be 2000 characters or fewer.";
  return "";
}

/**
 * The reusable Evidence section. It is subordinate to the selected architecture
 * fact: the fact supplies the target, and the panel only ever lists, creates,
 * edits or deletes the evidence attached to it. References are shown as text and
 * never fetched.
 */
export default function EvidencePanel({ workspaceId, stateId, targetKind, targetId, readOnly }: Props) {
  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!targetId || !stateId) {
      setRecords([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setRecords(await listEvidence(workspaceId, targetKind, targetId, stateId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load evidence.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, targetKind, targetId, stateId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setFormOpen(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError("");
  }, [targetId]);

  if (!targetId) {
    return <div className="inspector-empty">Select an architecture fact to see its evidence.</div>;
  }
  const resolvedTargetId: string = targetId;

  function startCreate() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError("");
    setFormOpen(true);
  }

  function startEdit(record: EvidenceRecord) {
    setEditingId(record.id);
    setForm(formFrom(record));
    setFormError("");
    setFormOpen(true);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = validate(form);
    if (message) {
      setFormError(message);
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      const payload = {
        evidence_classification: form.evidence_classification,
        source_type: form.source_type,
        source_title: form.source_title.trim(),
        source_reference: form.source_reference.trim(),
        source_locator: form.source_locator.trim() ? form.source_locator.trim() : null,
        summary: form.summary.trim(),
        confidence: form.confidence,
        verification_status: form.verification_status,
      };
      if (editingId) {
        await updateEvidence(workspaceId, editingId, payload);
      } else {
        await createEvidence(workspaceId, {
          ...payload,
          target_kind: targetKind,
          target_id: resolvedTargetId,
          created_in_state_id: null,
        });
      }
      setFormOpen(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
      await load();
    } catch (cause) {
      setFormError(cause instanceof Error ? cause.message : "Could not save this evidence.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(record: EvidenceRecord) {
    if (!window.confirm("Delete this evidence record? This is not reversible.")) return;
    setError("");
    try {
      await deleteEvidence(workspaceId, record.id);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this evidence.");
    }
  }

  const groups = groupEvidence(records);

  return (
    <section className="evidence-panel" aria-label="Architecture evidence">
      <header className="evidence-panel-head">
        <p className="eyebrow">EVIDENCE</p>
        <p className="evidence-headline">
          {records.length === 0
            ? "No evidence recorded"
            : `${records.length} record${records.length === 1 ? "" : "s"}`}
        </p>
      </header>

      {loading && (
        <p className="evidence-status" role="status">
          Loading evidence…
        </p>
      )}
      {error && (
        <p className="evidence-error" role="alert">
          {error}
        </p>
      )}

      {!loading && !error && records.length === 0 && (
        <div className="inspector-empty">
          Nothing recorded yet. Evidence keeps the source, confidence and verification
          status of this fact.
        </div>
      )}

      {groups.map(({ group, records: items }) => (
        <div key={group.id} className="evidence-group">
          <div className="evidence-group-head">
            <strong>{group.label}</strong>
            <span className="item-count">{items.length}</span>
          </div>
          <p className="evidence-group-help">{group.description}</p>
          <ul className="evidence-list">
            {items.map((record) => (
              <li key={record.id} className={`evidence-item evidence-${evidenceGroupOf(record.evidence_classification)}`}>
                <p className="evidence-item-title">
                  <span className="evidence-classification">
                    {evidenceClassificationLabel(record.evidence_classification)}
                  </span>
                  <span className={`evidence-verification evidence-verification-${record.verification_status}`}>
                    {EVIDENCE_VERIFICATION_LABELS[record.verification_status]}
                  </span>
                </p>
                <p className="evidence-item-summary">{record.summary}</p>
                <dl className="evidence-item-meta">
                  <div>
                    <dt>Source</dt>
                    <dd>
                      {record.source_title}
                      <em> · {EVIDENCE_SOURCE_TYPE_LABELS[record.source_type]}</em>
                    </dd>
                  </div>
                  <div>
                    <dt>Reference</dt>
                    <dd className="evidence-reference">{record.source_reference}</dd>
                  </div>
                  {record.source_locator && (
                    <div>
                      <dt>Locator</dt>
                      <dd className="evidence-reference">{record.source_locator}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Confidence</dt>
                    <dd>{EVIDENCE_CONFIDENCE_LABELS[record.confidence]}</dd>
                  </div>
                  <div>
                    <dt>Applies to</dt>
                    <dd>{evidenceApplicabilityLabel(record)}</dd>
                  </div>
                  <div>
                    <dt>Recorded</dt>
                    <dd>
                      {evidenceRecordedAtLabel(record.recorded_at)}
                      <em> · by {record.recorded_by}</em>
                    </dd>
                  </div>
                </dl>
                {!readOnly && (
                  <div className="evidence-item-actions">
                    <button type="button" className="secondary-button" onClick={() => startEdit(record)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="secondary-button evidence-danger"
                      onClick={() => void remove(record)}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {!readOnly && !formOpen && (
        <button type="button" className="secondary-button" onClick={startCreate}>
          + Add evidence
        </button>
      )}

      {!readOnly && formOpen && (
        <form className="evidence-form" onSubmit={(event) => void submit(event)}>
          <p className="evidence-form-title">{editingId ? "Edit evidence" : "Add evidence"}</p>
          <label className="inspector-field-label">
            Classification
            <select
              value={form.evidence_classification}
              onChange={(event) =>
                setForm({ ...form, evidence_classification: event.target.value as EvidenceClassification })
              }
              disabled={saving}
            >
              {EVIDENCE_CLASSIFICATIONS.map((value) => (
                <option key={value} value={value}>
                  {evidenceClassificationLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <label className="inspector-field-label">
            Source type
            <select
              value={form.source_type}
              onChange={(event) => setForm({ ...form, source_type: event.target.value as EvidenceSourceType })}
              disabled={saving}
            >
              {EVIDENCE_SOURCE_TYPES.map((value) => (
                <option key={value} value={value}>
                  {EVIDENCE_SOURCE_TYPE_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          <label className="inspector-field-label">
            Source title
            <input
              value={form.source_title}
              maxLength={300}
              onChange={(event) => setForm({ ...form, source_title: event.target.value })}
              disabled={saving}
              required
            />
          </label>
          <label className="inspector-field-label">
            Source reference
            <input
              value={form.source_reference}
              maxLength={2000}
              placeholder="URL, document id, ticket id or repository path"
              onChange={(event) => setForm({ ...form, source_reference: event.target.value })}
              disabled={saving}
              required
            />
          </label>
          <label className="inspector-field-label">
            Source locator (optional)
            <input
              value={form.source_locator}
              maxLength={2000}
              placeholder="Page, section or line"
              onChange={(event) => setForm({ ...form, source_locator: event.target.value })}
              disabled={saving}
            />
          </label>
          <label className="inspector-field-label">
            Summary
            <textarea
              value={form.summary}
              maxLength={2000}
              rows={3}
              onChange={(event) => setForm({ ...form, summary: event.target.value })}
              disabled={saving}
              required
            />
          </label>
          <label className="inspector-field-label">
            Confidence
            <select
              value={form.confidence}
              onChange={(event) => setForm({ ...form, confidence: event.target.value as EvidenceConfidence })}
              disabled={saving}
            >
              {EVIDENCE_CONFIDENCES.map((value) => (
                <option key={value} value={value}>
                  {EVIDENCE_CONFIDENCE_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          <label className="inspector-field-label">
            Verification status
            <select
              value={form.verification_status}
              onChange={(event) =>
                setForm({ ...form, verification_status: event.target.value as EvidenceVerificationStatus })
              }
              disabled={saving}
            >
              {EVIDENCE_VERIFICATION_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {EVIDENCE_VERIFICATION_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          {formError && (
            <p className="error" role="alert">
              {formError}
            </p>
          )}
          <div className="evidence-form-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setFormOpen(false);
                setEditingId(null);
                setFormError("");
              }}
              disabled={saving}
            >
              Cancel
            </button>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "Saving…" : editingId ? "Save evidence" : "Add evidence"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
