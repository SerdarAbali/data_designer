/**
 * Canonical integration/contract phase vocabulary.
 *
 * The same four phases were previously declared in the architecture index, the
 * scenario model, the integration design model and the mapper edge. They now
 * come from here so a phase label or predicate can only change in one place.
 */
export type ArchitecturePhaseKind =
  | "request"
  | "success-response"
  | "async-response"
  | "error-response";

export const ARCHITECTURE_PHASES: ArchitecturePhaseKind[] = [
  "request",
  "success-response",
  "error-response",
  "async-response",
];

export const PHASE_LABELS: Record<ArchitecturePhaseKind, string> = {
  request: "Request",
  "success-response": "Success response",
  "error-response": "Error response",
  "async-response": "Async response",
};

/** Success and async phases share the single response graph. */
export function isSharedResponseGraphPhase(phase: string | null | undefined): boolean {
  return phase === "success-response" || phase === "async-response";
}

export function isErrorResponsePhase(phase: string | null | undefined): boolean {
  return phase === "error-response";
}

/** True for every phase that reads/writes the response side of a contract. */
export function isResponsePhase(phase: string | null | undefined): boolean {
  return isSharedResponseGraphPhase(phase) || isErrorResponsePhase(phase);
}
