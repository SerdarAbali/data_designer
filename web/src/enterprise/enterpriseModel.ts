import { api } from "../information/api";
import { enterpriseLog } from "./enterpriseLog";

export type EnterpriseObjectType =
  | "goal"
  | "requirement"
  | "capability"
  | "process"
  | "principle"
  | "role";

export type EnterpriseProcessType = "process" | "value_stream";
export type EnterprisePrincipleType = "principle" | "constraint" | "quality" | "risk";
export type EnterpriseRoleType = "organization" | "role";
export type ImpactChangeType = "added" | "removed" | "changed" | "reused";

export const ENTERPRISE_OBJECT_TYPES: EnterpriseObjectType[] = [
  "goal",
  "requirement",
  "capability",
  "process",
  "principle",
  "role",
];

export const ENTERPRISE_PROCESS_TYPES: EnterpriseProcessType[] = ["process", "value_stream"];
export const ENTERPRISE_PRINCIPLE_TYPES: EnterprisePrincipleType[] = [
  "principle",
  "constraint",
  "quality",
  "risk",
];
export const ENTERPRISE_ROLE_TYPES: EnterpriseRoleType[] = ["organization", "role"];

export const ENTERPRISE_LINK_TYPES = [
  "drives",
  "needs",
  "has_process",
  "supports",
  "satisfies",
  "governed_by",
  "owned_by",
  "depends_on",
  "impacts",
  "affects",
] as const;

export type EnterpriseLinkType = (typeof ENTERPRISE_LINK_TYPES)[number];

export type EndpointKind = EnterpriseObjectType | "system";

export const ENTERPRISE_LINK_RULES: Record<
  EnterpriseLinkType,
  { sources: EndpointKind[]; targets: EndpointKind[] }
> = {
  drives: { sources: ["goal"], targets: ["requirement"] },
  needs: { sources: ["requirement"], targets: ["capability"] },
  has_process: { sources: ["capability"], targets: ["process"] },
  supports: { sources: ["system"], targets: ["capability", "process"] },
  satisfies: { sources: ["system"], targets: ["requirement"] },
  governed_by: {
    sources: ["goal", "requirement", "capability", "process", "principle", "role"],
    targets: ["principle"],
  },
  owned_by: {
    sources: ["goal", "requirement", "capability", "process", "principle", "role"],
    targets: ["role"],
  },
  depends_on: {
    sources: ["goal", "requirement", "capability", "process", "principle", "role"],
    targets: ["goal", "requirement", "capability", "process", "principle", "role"],
  },
  impacts: {
    sources: ["goal", "requirement", "capability", "process", "principle", "role"],
    targets: ["capability", "process"],
  },
  affects: {
    sources: ["goal", "requirement", "capability", "process", "principle", "role"],
    targets: ["capability", "process"],
  },
};

export const ENTERPRISE_LABELS: Record<string, string> = {
  goal: "Goal",
  requirement: "Requirement",
  capability: "Capability",
  process: "Process",
  principle: "Principle",
  role: "Role",
  drives: "drives",
  needs: "needs",
  has_process: "has process",
  supports: "supports",
  satisfies: "satisfies",
  governed_by: "governed by",
  owned_by: "owned by",
  depends_on: "depends on",
  impacts: "impacts",
  affects: "affects",
};

export const ENTERPRISE_PLURAL_LABELS: Record<string, string> = {
  goal: "Goals",
  requirement: "Requirements",
  capability: "Capabilities",
  process: "Processes",
  principle: "Principles",
  role: "Roles",
};

export type EnterpriseObject = {
  object_id: string;
  kind: EnterpriseObjectType;
  name: string;
  description: string | null;
  owner: string | null;
  outcome_metric: string | null;
  horizon: string | null;
  process_type: string | null;
  principle_type: string | null;
  rationale: string | null;
  role_type: string | null;
  created_in_state_id: string | null;
};

export type EnterpriseApplication = { object_id: string; name: string; kind: string; description?: string | null };

export type EnterpriseLink = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  relationship_type: string;
};

export type EnterpriseModel = {
  state_id: string;
  state_type: string;
  editable: boolean;
  goals: EnterpriseObject[];
  requirements: EnterpriseObject[];
  capabilities: EnterpriseObject[];
  processes: EnterpriseObject[];
  principles: EnterpriseObject[];
  roles: EnterpriseObject[];
  applications: EnterpriseApplication[];
  links: EnterpriseLink[];
};

export type EnterpriseObjectCreate = {
  state_id: string;
  kind: EnterpriseObjectType;
  name: string;
  description?: string;
  owner?: string;
  outcome_metric?: string;
  horizon?: string;
  process_type?: EnterpriseProcessType | null;
  principle_type?: EnterprisePrincipleType | null;
  rationale?: string;
  role_type?: EnterpriseRoleType | null;
  position?: { x: number; y: number };
};

export type EnterpriseObjectUpdate = {
  state_id: string;
  name?: string;
  description?: string | null;
  owner?: string | null;
  outcome_metric?: string | null;
  horizon?: string | null;
  process_type?: EnterpriseProcessType | null;
  principle_type?: EnterprisePrincipleType | null;
  rationale?: string | null;
  role_type?: EnterpriseRoleType | null;
};

export type CapabilityMapEntry = {
  capability: EnterpriseObject;
  processes: EnterpriseObject[];
  applications: EnterpriseApplication[];
  principles: EnterpriseObject[];
  owner_role: EnterpriseObject | null;
};

export type CapabilityMap = { state_id: string; capabilities: CapabilityMapEntry[] };

export type ProcessImpactEntry = {
  process: EnterpriseObject;
  capabilities: EnterpriseObject[];
  applications: EnterpriseApplication[];
  requirements: EnterpriseObject[];
  governed_by: EnterpriseObject[];
  impacted: boolean;
};

export type ProcessImpact = { state_id: string; processes: ProcessImpactEntry[] };

export type ApplicationSupportEntry = {
  application: EnterpriseApplication;
  capabilities: EnterpriseObject[];
  processes: EnterpriseObject[];
  requirements: EnterpriseObject[];
};

export type ApplicationSupport = { state_id: string; applications: ApplicationSupportEntry[] };

export type StrategyTraceStep = {
  requirement: EnterpriseObject;
  capabilities: EnterpriseObject[];
  processes: EnterpriseObject[];
  applications: EnterpriseApplication[];
};

export type StrategyTraceChain = {
  goal: EnterpriseObject;
  steps: StrategyTraceStep[];
  gaps: string[];
};

export type StrategyTrace = {
  state_id: string;
  chains: StrategyTraceChain[];
  unlinked_requirements: EnterpriseObject[];
  gaps: string[];
};

export type ImpactChange = {
  object_id: string;
  kind: string;
  name: string;
  change: ImpactChangeType;
  changed_fields?: string[];
};

export type EnterpriseImpact = {
  state_id: string;
  baseline_state_id: string | null;
  changes: ImpactChange[];
  affected_applications: EnterpriseApplication[];
  affected_capabilities: EnterpriseObject[];
  affected_processes: EnterpriseObject[];
  unresolved_dependencies: string[];
  unresolved_constraints: string[];
  risks: EnterpriseObject[];
  gaps: string[];
};

export function modelObjects(model: EnterpriseModel): EnterpriseObject[] {
  return [
    ...model.goals,
    ...model.requirements,
    ...model.capabilities,
    ...model.processes,
    ...model.principles,
    ...model.roles,
  ];
}

export function endpointName(model: EnterpriseModel, objectId: string): string {
  const object = modelObjects(model).find((item) => item.object_id === objectId);
  if (object) return object.name;
  return model.applications.find((item) => item.object_id === objectId)?.name ?? objectId;
}

export function endpointsFor(
  model: EnterpriseModel,
  kinds: EndpointKind[],
): { id: string; name: string; kind: string }[] {
  const wanted = new Set<string>(kinds);
  const enterprise = modelObjects(model)
    .filter((item) => wanted.has(item.kind))
    .map((item) => ({ id: item.object_id, name: item.name, kind: item.kind }));
  const applications = wanted.has("system")
    ? model.applications.map((item) => ({ id: item.object_id, name: item.name, kind: item.kind }))
    : [];
  return [...enterprise, ...applications].sort((a, b) => a.name.localeCompare(b.name));
}

const base = (workspaceId: string) => `/api/workspaces/${workspaceId}/enterprise`;

async function run<T>(action: string, task: () => Promise<T>): Promise<T> {
  enterpriseLog.info(action);
  try {
    const result = await task();
    enterpriseLog.info(`${action} ok`);
    return result;
  } catch (caught) {
    enterpriseLog.error(`${action} failed`, caught);
    throw caught;
  }
}

function asArray<T>(value: T[] | undefined | null): T[] {
  return Array.isArray(value) ? value : [];
}

function normalizeModel(raw: EnterpriseModel): EnterpriseModel {
  return {
    state_id: raw?.state_id ?? "",
    state_type: raw?.state_type ?? "candidate",
    editable: raw?.editable ?? false,
    goals: asArray(raw?.goals),
    requirements: asArray(raw?.requirements),
    capabilities: asArray(raw?.capabilities),
    processes: asArray(raw?.processes),
    principles: asArray(raw?.principles),
    roles: asArray(raw?.roles),
    applications: asArray(raw?.applications),
    links: asArray(raw?.links),
  };
}

export function fetchEnterpriseModel(
  workspaceId: string,
  stateId: string,
): Promise<EnterpriseModel> {
  return run("load model", async () =>
    normalizeModel(await api<EnterpriseModel>(`${base(workspaceId)}/model?state_id=${stateId}`)),
  );
}

export function createEnterpriseObject(
  workspaceId: string,
  body: EnterpriseObjectCreate,
): Promise<EnterpriseModel> {
  return run("create object", () =>
    api<EnterpriseModel>(`${base(workspaceId)}/objects`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateEnterpriseObject(
  workspaceId: string,
  objectId: string,
  body: EnterpriseObjectUpdate,
): Promise<EnterpriseModel> {
  return run("update object", () =>
    api<EnterpriseModel>(`${base(workspaceId)}/objects/${objectId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  );
}

export function deleteEnterpriseObject(
  workspaceId: string,
  objectId: string,
  stateId: string,
): Promise<EnterpriseModel> {
  return run("delete object", () =>
    api<EnterpriseModel>(`${base(workspaceId)}/objects/${objectId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function createEnterpriseLink(
  workspaceId: string,
  body: {
    state_id: string;
    relationship_type: EnterpriseLinkType;
    source_object_id: string;
    target_object_id: string;
  },
): Promise<EnterpriseModel> {
  return run("create link", () =>
    api<EnterpriseModel>(`${base(workspaceId)}/links`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function deleteEnterpriseLink(
  workspaceId: string,
  linkId: string,
  stateId: string,
): Promise<EnterpriseModel> {
  return run("delete link", () =>
    api<EnterpriseModel>(`${base(workspaceId)}/links/${linkId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function fetchCapabilityMap(workspaceId: string, stateId: string): Promise<CapabilityMap> {
  return run("load capability map", () =>
    api<CapabilityMap>(`${base(workspaceId)}/capability-map?state_id=${stateId}`),
  );
}

export function fetchProcessImpact(workspaceId: string, stateId: string): Promise<ProcessImpact> {
  return run("load process impact", () =>
    api<ProcessImpact>(`${base(workspaceId)}/process-impact?state_id=${stateId}`),
  );
}

export function fetchApplicationSupport(
  workspaceId: string,
  stateId: string,
): Promise<ApplicationSupport> {
  return run("load application support", () =>
    api<ApplicationSupport>(`${base(workspaceId)}/application-support?state_id=${stateId}`),
  );
}

export function fetchStrategyTrace(workspaceId: string, stateId: string): Promise<StrategyTrace> {
  return run("load strategy trace", () =>
    api<StrategyTrace>(`${base(workspaceId)}/strategy-trace?state_id=${stateId}`),
  );
}

export function fetchEnterpriseImpact(
  workspaceId: string,
  stateId: string,
): Promise<EnterpriseImpact> {
  return run("load impact comparison", () =>
    api<EnterpriseImpact>(`${base(workspaceId)}/impact?state_id=${stateId}`),
  );
}
