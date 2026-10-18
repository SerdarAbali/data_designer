/**
 * Controlled vocabularies for generic architecture evidence.
 *
 * Four deliberately separate vocabularies, mirroring
 * `api/app/architecture/vocabulary.py` exactly:
 *
 * * classification - what the architecture assertion currently represents;
 * * source type    - what kind of artefact or observation supports it;
 * * confidence     - how sure the recorder is;
 * * verification   - where the assertion stands in review.
 *
 * They never reuse lifecycle, operational-status or environment values, and
 * there is no free-text classification.
 */

export type EvidenceClassification =
  | "confirmed_by_requirements_document"
  | "confirmed_by_current_implementation"
  | "confirmed_by_field_mapping"
  | "confirmed_by_user_working_knowledge"
  | "assumption"
  | "open_decision"
  | "future_scope";

export type EvidenceSourceType =
  | "document"
  | "implementation"
  | "mapping"
  | "meeting"
  | "message"
  | "test"
  | "ticket"
  | "repository"
  | "user_statement"
  | "other";

export type EvidenceConfidence = "low" | "medium" | "high";

export type EvidenceVerificationStatus =
  | "unverified"
  | "verified"
  | "disputed"
  | "superseded";

export type EvidenceTargetKind =
  | "architecture_object"
  | "architecture_relationship"
  | "integration"
  | "integration_dependency"
  | "solution_member";

export type EvidenceStateApplicability = "canonical" | "state";

export type EvidenceRecord = {
  id: string;
  tenant_id: string;
  target_kind: EvidenceTargetKind;
  target_id: string;
  evidence_classification: EvidenceClassification;
  source_type: EvidenceSourceType;
  source_title: string;
  source_reference: string;
  source_locator: string | null;
  summary: string;
  confidence: EvidenceConfidence;
  verification_status: EvidenceVerificationStatus;
  recorded_by: string;
  recorded_at: string;
  updated_at: string;
  created_in_state_id: string | null;
  state_applicability: EvidenceStateApplicability;
  state_name: string | null;
};

export const EVIDENCE_CLASSIFICATIONS: EvidenceClassification[] = [
  "confirmed_by_requirements_document",
  "confirmed_by_current_implementation",
  "confirmed_by_field_mapping",
  "confirmed_by_user_working_knowledge",
  "assumption",
  "open_decision",
  "future_scope",
];

export const EVIDENCE_SOURCE_TYPES: EvidenceSourceType[] = [
  "document",
  "implementation",
  "mapping",
  "meeting",
  "message",
  "test",
  "ticket",
  "repository",
  "user_statement",
  "other",
];

export const EVIDENCE_CONFIDENCES: EvidenceConfidence[] = ["low", "medium", "high"];

export const EVIDENCE_VERIFICATION_STATUSES: EvidenceVerificationStatus[] = [
  "unverified",
  "verified",
  "disputed",
  "superseded",
];

export const EVIDENCE_CLASSIFICATION_LABELS: Record<EvidenceClassification, string> = {
  confirmed_by_requirements_document: "Confirmed · requirements document",
  confirmed_by_current_implementation: "Confirmed · current implementation",
  confirmed_by_field_mapping: "Confirmed · field mapping",
  confirmed_by_user_working_knowledge: "Confirmed · user working knowledge",
  assumption: "Assumption",
  open_decision: "Open decision",
  future_scope: "Future scope",
};

export const EVIDENCE_SOURCE_TYPE_LABELS: Record<EvidenceSourceType, string> = {
  document: "Document",
  implementation: "Implementation",
  mapping: "Mapping",
  meeting: "Meeting",
  message: "Message",
  test: "Test",
  ticket: "Ticket",
  repository: "Repository",
  user_statement: "User statement",
  other: "Other",
};

export const EVIDENCE_CONFIDENCE_LABELS: Record<EvidenceConfidence, string> = {
  low: "Low confidence",
  medium: "Medium confidence",
  high: "High confidence",
};

export const EVIDENCE_VERIFICATION_LABELS: Record<EvidenceVerificationStatus, string> = {
  unverified: "Unverified",
  verified: "Verified",
  disputed: "Disputed",
  superseded: "Superseded",
};

/**
 * The evidence groups the inspector separates visually *and* textually. The
 * group label is always rendered, so the distinction never relies on colour.
 */
export type EvidenceGroupId = "confirmed" | "assumption" | "open_decision" | "future_scope";

export type EvidenceGroup = {
  id: EvidenceGroupId;
  label: string;
  description: string;
  classifications: EvidenceClassification[];
};

export const EVIDENCE_GROUPS: EvidenceGroup[] = [
  {
    id: "confirmed",
    label: "Confirmed facts",
    description: "Supported by a document, the current implementation, a mapping or working knowledge.",
    classifications: [
      "confirmed_by_requirements_document",
      "confirmed_by_current_implementation",
      "confirmed_by_field_mapping",
      "confirmed_by_user_working_knowledge",
    ],
  },
  {
    id: "assumption",
    label: "Assumptions",
    description: "Taken as true for now, but not yet confirmed.",
    classifications: ["assumption"],
  },
  {
    id: "open_decision",
    label: "Open decisions",
    description: "Deliberately unresolved; a decision is still due.",
    classifications: ["open_decision"],
  },
  {
    id: "future_scope",
    label: "Future scope",
    description: "Out of scope now and deferred to a later stage.",
    classifications: ["future_scope"],
  },
];

export function evidenceGroupOf(classification: EvidenceClassification): EvidenceGroupId {
  return (
    EVIDENCE_GROUPS.find((group) => group.classifications.includes(classification))?.id
    ?? "confirmed"
  );
}

/** Group a bounded evidence list into the four inspector groups, in group order. */
export function groupEvidence(
  records: EvidenceRecord[],
): { group: EvidenceGroup; records: EvidenceRecord[] }[] {
  return EVIDENCE_GROUPS.map((group) => ({
    group,
    records: records.filter((record) => group.classifications.includes(record.evidence_classification)),
  })).filter((entry) => entry.records.length > 0);
}

export function evidenceClassificationLabel(value: EvidenceClassification): string {
  return EVIDENCE_CLASSIFICATION_LABELS[value] ?? value.replace(/_/g, " ");
}

/** Human label for where the evidence applies, never relying on colour. */
export function evidenceApplicabilityLabel(record: EvidenceRecord): string {
  if (record.state_applicability === "canonical") return "All states (canonical)";
  return record.state_name ? `${record.state_name} state` : "State-scoped";
}

export function evidenceRecordedAtLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString().slice(0, 16).replace("T", " ");
}
