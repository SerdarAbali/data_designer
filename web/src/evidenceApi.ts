/**
 * Bounded HTTP client for generic architecture evidence.
 *
 * One target, one state per list so the endpoint stays bounded and evidence
 * introduced for one Candidate/Target state can never leak into another. The
 * browser never fetches a `source_reference`; references are displayed as text
 * only.
 */

import { api } from "./apiClient";
import type {
  EvidenceClassification,
  EvidenceConfidence,
  EvidenceRecord,
  EvidenceSourceType,
  EvidenceTargetKind,
  EvidenceVerificationStatus,
} from "./evidence";

export type EvidenceCreatePayload = {
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
  created_in_state_id?: string | null;
};

export type EvidenceUpdatePayload = {
  evidence_classification?: EvidenceClassification;
  source_type?: EvidenceSourceType;
  source_title?: string;
  source_reference?: string;
  source_locator?: string | null;
  summary?: string;
  confidence?: EvidenceConfidence;
  verification_status?: EvidenceVerificationStatus;
};

const base = (workspaceId: string) => `/api/workspaces/${workspaceId}/evidence`;

export function listEvidence(
  workspaceId: string,
  targetKind: EvidenceTargetKind,
  targetId: string,
  stateId: string,
): Promise<EvidenceRecord[]> {
  const params = new URLSearchParams({
    target_kind: targetKind,
    target_id: targetId,
    state_id: stateId,
  });
  return api<EvidenceRecord[]>(`${base(workspaceId)}?${params.toString()}`);
}

export function createEvidence(
  workspaceId: string,
  payload: EvidenceCreatePayload,
): Promise<EvidenceRecord> {
  return api<EvidenceRecord>(base(workspaceId), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateEvidence(
  workspaceId: string,
  evidenceId: string,
  payload: EvidenceUpdatePayload,
): Promise<EvidenceRecord> {
  return api<EvidenceRecord>(`${base(workspaceId)}/${evidenceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteEvidence(workspaceId: string, evidenceId: string): Promise<void> {
  return api<void>(`${base(workspaceId)}/${evidenceId}`, { method: "DELETE" });
}
