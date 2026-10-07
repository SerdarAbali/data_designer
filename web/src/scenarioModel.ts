import type {
  ArchitectureContract,
  ArchitecturePhase,
  ArchitecturePhaseKind,
  EnterpriseArchitectureIndex,
} from "./enterpriseArchitectureIndex";

export type ScenarioCategory = "happy_path" | "alternative" | "error";
export type ScenarioPhase = ArchitecturePhaseKind;
export type ScenarioFragmentKind = "alt" | "opt" | "loop";
export type ScenarioStepKind = "contract" | "self" | "actor";
export type FieldValues = Record<string, unknown>;

export type ScenarioParticipant = {
  id: string;
  kind: "system" | "actor";
  systemId?: string | null;
  label?: string | null;
};

export type ScenarioStateEntry = {
  id: string;
  participantId: string;
  objectId: string;
  values: FieldValues;
  note?: string | null;
};

export type ScenarioStep = {
  kind: ScenarioStepKind;
  id: string;
  contractId?: string | null;
  phase?: ScenarioPhase | null;
  fromParticipantId?: string | null;
  toParticipantId?: string | null;
  label?: string | null;
  sampleValues?: FieldValues;
  expectedValues?: FieldValues;
  notes?: string | null;
};

export type ScenarioOperand = { guard: string; items: ScenarioItem[] };

export type ScenarioFragment = {
  kind: ScenarioFragmentKind;
  id: string;
  operands: ScenarioOperand[];
};

export type ScenarioItem = ScenarioStep | ScenarioFragment;

export type ScenarioAssertion = {
  id: string;
  text: string;
  stepId?: string | null;
  fieldId?: string | null;
  expected?: unknown;
};

export type ScenarioDocument = {
  version: 1;
  preconditions: string;
  trigger: string;
  participants: ScenarioParticipant[];
  contractIds: string[];
  beforeState: ScenarioStateEntry[];
  afterState: ScenarioStateEntry[];
  items: ScenarioItem[];
  assertions: ScenarioAssertion[];
  notes: string;
};

export type ScenarioRecord = {
  id: string;
  scope_integration_id: string | null;
  name: string;
  category: ScenarioCategory;
  description: string | null;
  document: ScenarioDocument;
  revision: number;
  created_at: string;
  updated_at: string;
};

export type StepOutcome = "ok" | "mismatch" | "failed" | "skipped" | "missing_reference" | "not_evaluated";

export type ScenarioEvaluation = {
  steps: {
    stepId: string;
    contractId: string | null;
    phase: ScenarioPhase | null;
    outcome: StepOutcome;
    targetValues: FieldValues;
    errors: { code?: string; message?: string; nodeId?: string | null }[];
    mismatches: { fieldId: string; expected: unknown; actual: unknown; present: boolean }[];
  }[];
  assertions: { assertionId: string; status: "passed" | "failed" | "manual" | "not_evaluated"; message: string }[];
  missingReferences: { kind: string; id: string; message: string; stepId?: string | null }[];
  summary: Record<string, number>;
};

export const SCENARIO_CATEGORIES: readonly { value: ScenarioCategory; label: string }[] = [
  { value: "happy_path", label: "Happy path" },
  { value: "alternative", label: "Alternative" },
  { value: "error", label: "Error" },
];

export function categoryLabel(category: ScenarioCategory): string {
  return SCENARIO_CATEGORIES.find((item) => item.value === category)?.label ?? category;
}

export const PHASE_LABELS: Record<ScenarioPhase, string> = {
  request: "Request",
  "success-response": "Success response",
  "error-response": "Error response",
  "async-response": "Async response",
};

export const MAX_FRAGMENT_DEPTH = 3;

export function isFragment(item: ScenarioItem): item is ScenarioFragment {
  return item.kind === "alt" || item.kind === "opt" || item.kind === "loop";
}

export function isResponsePhase(phase: ScenarioPhase | null | undefined): boolean {
  return phase === "success-response" || phase === "error-response" || phase === "async-response";
}

let idCounter = 0;
export function newScenarioId(prefix: string): string {
  idCounter += 1;
  const random = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${Date.now().toString(36)}${idCounter.toString(36)}${random}`.slice(0, 64);
}

export function emptyScenarioDocument(contractId?: string | null): ScenarioDocument {
  return {
    version: 1,
    preconditions: "",
    trigger: "",
    participants: [],
    contractIds: contractId ? [contractId] : [],
    beforeState: [],
    afterState: [],
    items: [],
    assertions: [],
    notes: "",
  };
}

export type FlatStep = {
  step: ScenarioStep;
  number: string;
  depth: number;
  parentFragmentIds: readonly string[];
};

/** Steps in document order with a human-readable number (1, 2, 3...) independent of nesting. */
export function flattenSteps(items: readonly ScenarioItem[]): FlatStep[] {
  const result: FlatStep[] = [];
  const walk = (list: readonly ScenarioItem[], depth: number, parents: readonly string[]) => {
    for (const item of list) {
      if (isFragment(item)) {
        for (const operand of item.operands) walk(operand.items, depth + 1, [...parents, item.id]);
      } else {
        result.push({ step: item, number: String(result.length + 1), depth, parentFragmentIds: parents });
      }
    }
  };
  walk(items, 0, []);
  return result;
}

export function availablePhases(contract: ArchitectureContract): ScenarioPhase[] {
  if (contract.interactionType === "ONE_WAY") return ["request"];
  if (contract.interactionType === "ASYNC_CALLBACK") return ["request", "async-response"];
  return contract.errorResponseObjectId
    ? ["request", "success-response", "error-response"]
    : ["request", "success-response"];
}

export type StepEndpoints = {
  senderSystemId: string;
  receiverSystemId: string;
  senderObjectId: string | null;
  receiverObjectId: string;
  phase: ArchitecturePhase | null;
};

/** Derive sender/receiver for a contract phase from the contract itself (never from the scenario). */
export function contractStepEndpoints(
  index: EnterpriseArchitectureIndex | null,
  contractId: string | null | undefined,
  phase: ScenarioPhase | null | undefined,
): StepEndpoints | null {
  if (!index || !contractId || !phase) return null;
  const contract = index.contractsById.get(contractId);
  if (!contract || !availablePhases(contract).includes(phase)) return null;
  const indexedPhase = index.phasesByContractId.get(contractId)?.find((item) => item.phase === phase) ?? null;
  if (phase === "request") {
    return {
      senderSystemId: contract.sourceSystemId,
      receiverSystemId: contract.targetSystemId,
      senderObjectId: contract.sourceObjectId,
      receiverObjectId: contract.targetObjectId,
      phase: indexedPhase,
    };
  }
  return {
    senderSystemId: contract.targetSystemId,
    receiverSystemId: contract.sourceSystemId,
    senderObjectId: phase === "error-response" ? contract.errorResponseObjectId : contract.targetObjectId,
    receiverObjectId: contract.sourceObjectId,
    phase: indexedPhase,
  };
}

export function systemParticipantId(systemId: string): string {
  return `sys-${systemId.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 56)}`;
}

export type Lifeline = {
  id: string;
  kind: "system" | "actor";
  systemId: string | null;
  label: string;
  missing: boolean;
  implicit: boolean;
};

export type ResolvedStep = {
  fromLifelineId: string | null;
  toLifelineId: string | null;
  endpoints: StepEndpoints | null;
  missing: string | null;
};

function contractStepSystems(
  index: EnterpriseArchitectureIndex | null,
  step: ScenarioStep,
): { senderSystemId: string; receiverSystemId: string } | null {
  return contractStepEndpoints(index, step.contractId, step.phase);
}

/**
 * Lifelines are the declared participants plus any system a contract step touches that has not
 * been declared yet, so a diagram is always drawable from contract references alone.
 */
export function deriveLifelines(
  document: ScenarioDocument,
  index: EnterpriseArchitectureIndex | null,
): Lifeline[] {
  const lifelines: Lifeline[] = document.participants.map((participant) => {
    const system = participant.systemId ? index?.systemsById.get(participant.systemId) : undefined;
    return {
      id: participant.id,
      kind: participant.kind,
      systemId: participant.systemId ?? null,
      label: participant.label?.trim() || system?.name || (participant.kind === "actor" ? "Actor" : "Unknown system"),
      missing: participant.kind === "system" && !!index && index.state !== "failed" && !system,
      implicit: false,
    };
  });
  const knownSystems = new Set(lifelines.map((item) => item.systemId).filter(Boolean));
  for (const { step } of flattenSteps(document.items)) {
    if (step.kind !== "contract") continue;
    const systems = contractStepSystems(index, step);
    if (!systems) continue;
    for (const systemId of [systems.senderSystemId, systems.receiverSystemId]) {
      if (knownSystems.has(systemId)) continue;
      knownSystems.add(systemId);
      lifelines.push({
        id: systemParticipantId(systemId),
        kind: "system",
        systemId,
        label: index?.systemsById.get(systemId)?.name ?? "Unknown system",
        missing: !index?.systemsById.has(systemId),
        implicit: true,
      });
    }
  }
  return lifelines;
}

export function resolveStep(
  step: ScenarioStep,
  lifelines: readonly Lifeline[],
  index: EnterpriseArchitectureIndex | null,
): ResolvedStep {
  if (step.kind !== "contract") {
    const ids = new Set(lifelines.map((item) => item.id));
    const from = step.fromParticipantId && ids.has(step.fromParticipantId) ? step.fromParticipantId : null;
    const to = step.kind === "self" ? from : step.toParticipantId && ids.has(step.toParticipantId) ? step.toParticipantId : null;
    return { fromLifelineId: from, toLifelineId: to, endpoints: null, missing: from && to ? null : "Participant is missing" };
  }
  const contract = step.contractId ? index?.contractsById.get(step.contractId) : undefined;
  if (!contract) {
    return { fromLifelineId: null, toLifelineId: null, endpoints: null, missing: "Contract is missing or archived" };
  }
  const endpoints = contractStepEndpoints(index, step.contractId, step.phase);
  if (!endpoints) {
    return { fromLifelineId: null, toLifelineId: null, endpoints: null, missing: "Phase is not configured for this contract" };
  }
  const bySystem = (systemId: string) => lifelines.find((item) => item.systemId === systemId)?.id ?? null;
  return {
    fromLifelineId: bySystem(endpoints.senderSystemId),
    toLifelineId: bySystem(endpoints.receiverSystemId),
    endpoints,
    missing: null,
  };
}

export type MissingReference = { stepId?: string; message: string };

/** Client-side mirror of the server reference checks, used for warnings without a round trip. */
export function detectMissingReferences(
  document: ScenarioDocument,
  index: EnterpriseArchitectureIndex | null,
): MissingReference[] {
  if (!index || index.state === "failed") return [];
  const issues: MissingReference[] = [];
  for (const contractId of document.contractIds) {
    if (!index.contractsById.has(contractId)) issues.push({ message: "A participating contract is missing or archived" });
  }
  for (const participant of document.participants) {
    if (participant.systemId && !index.systemsById.has(participant.systemId)) {
      issues.push({ message: `Participant ${participant.label || participant.id} references a missing system` });
    }
  }
  for (const entry of [...document.beforeState, ...document.afterState]) {
    if (!index.objectsById.has(entry.objectId)) {
      issues.push({ message: "A state entry references a missing object" });
      continue;
    }
    for (const fieldId of Object.keys(entry.values)) {
      if (!index.fieldsById.has(fieldId)) issues.push({ message: "A state entry references a missing field" });
    }
  }
  const lifelines = deriveLifelines(document, index);
  for (const { step } of flattenSteps(document.items)) {
    const resolved = resolveStep(step, lifelines, index);
    if (resolved.missing) {
      issues.push({ stepId: step.id, message: resolved.missing });
      continue;
    }
    if (step.kind !== "contract" || !resolved.endpoints) continue;
    const senderFields = new Set(index.objectsById.get(resolved.endpoints.senderObjectId ?? "")?.fieldIds ?? []);
    const receiverFields = new Set(index.objectsById.get(resolved.endpoints.receiverObjectId)?.fieldIds ?? []);
    if (Object.keys(step.sampleValues ?? {}).some((id) => !senderFields.has(id))) {
      issues.push({ stepId: step.id, message: "A sample value references a field that is no longer on the sender" });
    }
    if (Object.keys(step.expectedValues ?? {}).some((id) => !receiverFields.has(id))) {
      issues.push({ stepId: step.id, message: "An expected value references a field that is no longer on the receiver" });
    }
  }
  return issues;
}

type ItemList = ScenarioItem[];

// Bottom-up so items created by `visit` (for example a new wrapping block) are not revisited.
function mapLists(items: ItemList, visit: (list: ItemList) => ItemList): ItemList {
  return visit(items.map((item) =>
    isFragment(item)
      ? { ...item, operands: item.operands.map((operand) => ({ ...operand, items: mapLists(operand.items, visit) })) }
      : item));
}

export function updateItem(
  items: ItemList,
  id: string,
  update: (item: ScenarioItem) => ScenarioItem,
): ItemList {
  return mapLists(items, (list) => list.map((item) => (item.id === id ? update(item) : item)));
}

export function removeItem(items: ItemList, id: string): ItemList {
  return mapLists(items, (list) => list.filter((item) => item.id !== id));
}

/** Move an item one position within its own sibling list. */
export function moveItem(items: ItemList, id: string, delta: -1 | 1): ItemList {
  return mapLists(items, (list) => {
    const index = list.findIndex((item) => item.id === id);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= list.length) return list;
    const next = [...list];
    [next[index], next[target]] = [next[target]!, next[index]!];
    return next;
  });
}

export function insertAfter(items: ItemList, afterId: string | null, item: ScenarioItem): ItemList {
  if (afterId === null) return [...items, item];
  let inserted = false;
  const next = mapLists(items, (list) => {
    const index = list.findIndex((entry) => entry.id === afterId);
    if (index < 0) return list;
    inserted = true;
    return [...list.slice(0, index + 1), item, ...list.slice(index + 1)];
  });
  return inserted ? next : [...items, item];
}

export function appendToOperand(
  items: ItemList,
  fragmentId: string,
  operandIndex: number,
  item: ScenarioItem,
): ItemList {
  return updateItem(items, fragmentId, (fragment) => {
    if (!isFragment(fragment)) return fragment;
    return {
      ...fragment,
      operands: fragment.operands.map((operand, index) =>
        index === operandIndex ? { ...operand, items: [...operand.items, item] } : operand),
    };
  });
}

export function wrapItem(items: ItemList, id: string, kind: ScenarioFragmentKind, guard = ""): ItemList {
  return updateItem(items, id, (item) => ({
    kind,
    id: newScenarioId("block"),
    operands: kind === "alt"
      ? [{ guard, items: [item] }, { guard: "else", items: [] }]
      : [{ guard, items: [item] }],
  }));
}

export function unwrapFragment(items: ItemList, id: string): ItemList {
  return mapLists(items, (list) =>
    list.flatMap((item) => (item.id === id && isFragment(item) ? item.operands.flatMap((operand) => operand.items) : [item])));
}

export function fragmentDepth(items: readonly ScenarioItem[], id: string, depth = 0): number | null {
  for (const item of items) {
    if (item.id === id) return depth;
    if (isFragment(item)) {
      for (const operand of item.operands) {
        const found = fragmentDepth(operand.items, id, depth + 1);
        if (found !== null) return found;
      }
    }
  }
  return null;
}

/** Deep copy with fresh item IDs; assertion step references follow their renamed steps. */
export function duplicateScenarioDocument(document: ScenarioDocument): ScenarioDocument {
  const renamed = new Map<string, string>();
  const copyItems = (items: readonly ScenarioItem[]): ScenarioItem[] =>
    items.map((item) => {
      const id = newScenarioId(isFragment(item) ? "block" : "step");
      renamed.set(item.id, id);
      if (isFragment(item)) {
        return { ...item, id, operands: item.operands.map((operand) => ({ ...operand, items: copyItems(operand.items) })) };
      }
      return { ...structuredClone(item), id };
    });
  const items = copyItems(document.items);
  return {
    ...structuredClone(document),
    items,
    assertions: document.assertions.map((assertion) => ({
      ...structuredClone(assertion),
      id: newScenarioId("assert"),
      stepId: assertion.stepId ? renamed.get(assertion.stepId) ?? assertion.stepId : assertion.stepId,
    })),
  };
}

export function referencedContractIds(document: ScenarioDocument): string[] {
  const ids = new Set(document.contractIds);
  for (const { step } of flattenSteps(document.items)) if (step.contractId) ids.add(step.contractId);
  return [...ids];
}

/** Parse a user-entered sample value: JSON literals when valid, otherwise the raw string. */
export function parseSampleInput(raw: string): unknown {
  const trimmed = raw.trim();
  if (trimmed === "") return "";
  if (/^(-?\d+(\.\d+)?([eE][+-]?\d+)?|true|false|null|\{.*\}|\[.*\])$/s.test(trimmed)) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return raw;
    }
  }
  return raw;
}

export function formatSampleValue(value: unknown): string {
  if (value === undefined) return "";
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function contractLabel(index: EnterpriseArchitectureIndex | null, contractId: string | null | undefined): string {
  if (!contractId) return "";
  return index?.contractsById.get(contractId)?.name ?? "Missing contract";
}
