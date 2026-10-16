import { api } from "../information/api";
import type { ArchitecturePhaseKind } from "../architecturePhases";
import { integrationLog } from "./integrationLog";

export { PHASE_LABELS } from "../architecturePhases";

export type IntegrationPattern =
  | "point_to_point"
  | "request_reply"
  | "publish_subscribe"
  | "event_streaming"
  | "message_queue"
  | "file_transfer"
  | "batch"
  | "api_gateway"
  | "orchestration"
  | "other";

export type ImplementationStatus = "draft" | "in_progress" | "built" | "verified";
export type AuthType = "none" | "api_key" | "basic" | "oauth2" | "jwt" | "mtls" | "saml" | "custom";
export type BackoffStrategy = "none" | "linear" | "exponential";
export type OrchestrationRole = "orchestration" | "choreography" | "participant" | "none";
export type ConformanceStatus = "passing" | "failing" | "not_run" | "outdated";
export type FlowNodeRole = "validation" | "routing" | "transformation" | "constant";
export type ChannelKind = "api" | "event" | "file";
export type FlowPhaseName = ArchitecturePhaseKind;

export const INTEGRATION_PATTERNS: IntegrationPattern[] = [
  "point_to_point",
  "request_reply",
  "publish_subscribe",
  "event_streaming",
  "message_queue",
  "file_transfer",
  "batch",
  "api_gateway",
  "orchestration",
  "other",
];

export const IMPLEMENTATION_STATUSES: ImplementationStatus[] = [
  "draft",
  "in_progress",
  "built",
  "verified",
];

export const AUTH_TYPES: AuthType[] = [
  "none",
  "api_key",
  "basic",
  "oauth2",
  "jwt",
  "mtls",
  "saml",
  "custom",
];

export const BACKOFF_STRATEGIES: BackoffStrategy[] = ["none", "linear", "exponential"];
export const ORCHESTRATION_ROLES: OrchestrationRole[] = [
  "orchestration",
  "choreography",
  "participant",
  "none",
];

export const PATTERN_LABELS: Record<IntegrationPattern, string> = {
  point_to_point: "Point to point",
  request_reply: "Request / reply",
  publish_subscribe: "Publish / subscribe",
  event_streaming: "Event streaming",
  message_queue: "Message queue",
  file_transfer: "File transfer",
  batch: "Batch",
  api_gateway: "API gateway",
  orchestration: "Orchestration",
  other: "Other",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  in_progress: "In progress",
  built: "Built",
  verified: "Verified",
  attention: "Attention",
};

export const INTERACTION_TYPE_LABELS: Record<string, string> = {
  ONE_WAY: "One way",
  REQUEST_RESPONSE: "Request / response",
  ASYNC_CALLBACK: "Async callback",
};

export const CONFORMANCE_LABELS: Record<ConformanceStatus, string> = {
  passing: "Passing",
  failing: "Failing",
  not_run: "Not run",
  outdated: "Outdated",
};

export const CONFORMANCE_ORDER: ConformanceStatus[] = ["passing", "failing", "outdated", "not_run"];

export type IntegrationOperatingSpec = {
  retry: { max_attempts: number; backoff: BackoffStrategy };
  timeout_ms: number | null;
  idempotent: boolean;
  idempotency_key_field_id: string | null;
  security: { auth_type: AuthType; notes: string };
  routing: string;
  orchestration_role: OrchestrationRole;
  error_handling: string;
};

export type IntegrationOperation = {
  object_id: string;
  name: string;
  operation_kind: string;
  description: string | null;
};

export type IntegrationInterfaceRef = {
  object_id: string;
  name: string;
  direction: string | null;
  interface_kind: string | null;
  protocol: string | null;
  technology: string | null;
};

export type IntegrationInterfaceSummary = IntegrationInterfaceRef & {
  description: string | null;
  component_object_id: string | null;
  component_name: string | null;
  operations: IntegrationOperation[];
  contract_ids: string[];
};

export type IntegrationEndpointRef = {
  system_id: string;
  system_name: string;
  object_id: string;
  object_name: string;
  system_kind?: string | null;
  is_runtime?: boolean;
};

export type IntegrationContractSummary = {
  id: string;
  name: string;
  description: string | null;
  interaction_type: string;
  pattern: IntegrationPattern | null;
  implementation_status: string;
  revision: number;
  updated_at: string | null;
  status: string;
  source: IntegrationEndpointRef;
  target: IntegrationEndpointRef;
  producer_interface: IntegrationInterfaceRef | null;
  consumer_interface: IntegrationInterfaceRef | null;
  has_request_graph: boolean;
  has_response_graph: boolean;
  has_error_graph: boolean;
  specification: Partial<IntegrationOperatingSpec>;
  idempotency_key_field_name?: string | null;
  target_fields_mapped: number;
  target_fields_total: number;
  scenario_count: number;
};

export type IntegrationLandscape = {
  state_id: string;
  state_type: string;
  editable: boolean;
  contracts: IntegrationContractSummary[];
  interfaces: IntegrationInterfaceSummary[];
};

export type IntegrationFlowTransformation = {
  node_id: string;
  type: string;
  label: string;
  role: FlowNodeRole;
  position: { x: number; y: number } | null;
};

export type IntegrationFlowPhase = {
  phase: FlowPhaseName;
  configured: boolean;
  node_count: number;
  transformation_count: number;
  transformations: IntegrationFlowTransformation[];
  source_field_count: number;
  target_field_count: number;
  mapped_target_count: number;
  target_fields: string[];
  unmapped_required_fields: string[];
};

export type IntegrationMessageFlow = {
  contract: IntegrationContractSummary;
  routing: string;
  trigger_config: Record<string, unknown>;
  channel_kind: ChannelKind | null;
  channel_label: string | null;
  phases: IntegrationFlowPhase[];
};

export type IntegrationContractDetail = {
  contract: IntegrationContractSummary;
  source_interface: IntegrationInterfaceSummary | null;
  target_interface: IntegrationInterfaceSummary | null;
  phases: IntegrationFlowPhase[];
};

export type IntegrationCoverage = { mapped: number; total: number; ratio: number };

export type IntegrationScenarioStatus = {
  id: string;
  name: string;
  category: string;
  revision: number;
  updated_at: string | null;
  status: ConformanceStatus;
  step_count: number;
  message: string;
};

export type IntegrationConformance = {
  contract_id: string;
  contract_name: string;
  revision: number;
  updated_at: string | null;
  request_coverage: IntegrationCoverage;
  response_coverage: IntegrationCoverage;
  error_coverage: IntegrationCoverage;
  scenarios: IntegrationScenarioStatus[];
  summary: Record<string, number>;
};

export type IntegrationSequenceParticipant = {
  id: string;
  label: string;
  kind: string;
  system_id: string | null;
  system_name: string | null;
  is_runtime: boolean;
};

export type IntegrationSequenceInteraction = {
  id: string;
  kind: string;
  phase: string | null;
  from_id: string | null;
  to_id: string | null;
  label: string;
  contract_step: boolean;
};

export type IntegrationScenarioSequence = {
  id: string;
  name: string;
  category: string;
  status: ConformanceStatus;
  revision: number;
  outdated: boolean;
  step_count: number;
  participants: IntegrationSequenceParticipant[];
  interactions: IntegrationSequenceInteraction[];
};

export type IntegrationSequence = {
  contract_id: string;
  contract_name: string;
  revision: number;
  scenarios: IntegrationScenarioSequence[];
};

const base = (workspaceId: string) => `/api/workspaces/${workspaceId}/integration-design`;

export function emptySpec(): IntegrationOperatingSpec {
  return {
    retry: { max_attempts: 0, backoff: "none" },
    timeout_ms: null,
    idempotent: false,
    idempotency_key_field_id: null,
    security: { auth_type: "none", notes: "" },
    routing: "",
    orchestration_role: "none",
    error_handling: "",
  };
}

function normalizeContract(raw: IntegrationContractSummary): IntegrationContractSummary {
  return {
    ...raw,
    pattern: raw?.pattern ?? null,
    implementation_status: raw?.implementation_status ?? "draft",
    status: raw?.status ?? "draft",
    producer_interface: raw?.producer_interface ?? null,
    consumer_interface: raw?.consumer_interface ?? null,
    specification: raw?.specification ?? {},
    target_fields_mapped: raw?.target_fields_mapped ?? 0,
    target_fields_total: raw?.target_fields_total ?? 0,
    scenario_count: raw?.scenario_count ?? 0,
  };
}

function normalizePhase(raw: IntegrationFlowPhase): IntegrationFlowPhase {
  return {
    ...raw,
    configured: Boolean(raw?.configured),
    node_count: raw?.node_count ?? 0,
    transformation_count: raw?.transformation_count ?? 0,
    transformations: (raw?.transformations ?? []).map((item) => ({
      node_id: item.node_id,
      type: item.type,
      label: item.label,
      role: item.role ?? "transformation",
      position: item.position ?? null,
    })),
    source_field_count: raw?.source_field_count ?? 0,
    target_field_count: raw?.target_field_count ?? 0,
    mapped_target_count: raw?.mapped_target_count ?? 0,
    target_fields: raw?.target_fields ?? [],
    unmapped_required_fields: raw?.unmapped_required_fields ?? [],
  };
}

export async function fetchIntegrationLandscape(
  workspaceId: string,
  stateId: string,
): Promise<IntegrationLandscape> {
  const raw = await api<IntegrationLandscape>(`${base(workspaceId)}/landscape?state_id=${stateId}`);
  const landscape: IntegrationLandscape = {
    state_id: raw?.state_id ?? "",
    state_type: raw?.state_type ?? "candidate",
    editable: Boolean(raw?.editable),
    contracts: (raw?.contracts ?? []).map(normalizeContract),
    interfaces: (raw?.interfaces ?? []).map((item) => ({
      ...item,
      operations: item?.operations ?? [],
      contract_ids: item?.contract_ids ?? [],
    })),
  };
  integrationLog.info("landscape loaded", {
    workspaceId,
    stateId,
    contracts: landscape.contracts.length,
    interfaces: landscape.interfaces.length,
  });
  return landscape;
}

export async function fetchIntegrationContractDetail(
  workspaceId: string,
  integrationId: string,
  stateId: string,
): Promise<IntegrationContractDetail> {
  const raw = await api<IntegrationContractDetail>(
    `${base(workspaceId)}/contracts/${integrationId}?state_id=${stateId}`,
  );
  const detail: IntegrationContractDetail = {
    contract: normalizeContract(raw.contract),
    source_interface: raw.source_interface ?? null,
    target_interface: raw.target_interface ?? null,
    phases: (raw.phases ?? []).map(normalizePhase),
  };
  integrationLog.info("contract loaded", {
    integrationId,
    revision: detail.contract.revision,
    interfaces: [detail.source_interface?.name, detail.target_interface?.name].filter(Boolean),
  });
  return detail;
}

export async function fetchIntegrationMessageFlow(
  workspaceId: string,
  integrationId: string,
  stateId: string,
): Promise<IntegrationMessageFlow> {
  const raw = await api<IntegrationMessageFlow>(
    `${base(workspaceId)}/contracts/${integrationId}/flow?state_id=${stateId}`,
  );
  const flow: IntegrationMessageFlow = {
    contract: normalizeContract(raw.contract),
    routing: raw.routing ?? "",
    trigger_config: raw.trigger_config ?? {},
    channel_kind: raw.channel_kind ?? null,
    channel_label: raw.channel_label ?? null,
    phases: (raw.phases ?? []).map(normalizePhase),
  };
  integrationLog.info("message flow generated", {
    integrationId,
    phases: flow.phases.map((phase) => phase.phase),
    routing: flow.routing,
  });
  return flow;
}

export async function fetchIntegrationConformance(
  workspaceId: string,
  integrationId: string,
  stateId: string,
): Promise<IntegrationConformance> {
  const raw = await api<IntegrationConformance>(
    `${base(workspaceId)}/contracts/${integrationId}/conformance?state_id=${stateId}`,
  );
  const conformance: IntegrationConformance = {
    contract_id: raw.contract_id,
    contract_name: raw.contract_name,
    revision: raw.revision,
    updated_at: raw.updated_at ?? null,
    request_coverage: raw.request_coverage,
    response_coverage: raw.response_coverage,
    error_coverage: raw.error_coverage,
    scenarios: raw.scenarios ?? [],
    summary: raw.summary ?? {},
  };
  integrationLog.info("conformance loaded", {
    integrationId,
    revision: conformance.revision,
    scenarios: conformance.scenarios.length,
    summary: conformance.summary,
  });
  return conformance;
}

export async function fetchIntegrationSequence(
  workspaceId: string,
  integrationId: string,
  stateId: string,
): Promise<IntegrationSequence> {
  const raw = await api<IntegrationSequence>(
    `${base(workspaceId)}/contracts/${integrationId}/sequence?state_id=${stateId}`,
  );
  const sequence: IntegrationSequence = {
    contract_id: raw.contract_id,
    contract_name: raw.contract_name,
    revision: raw.revision,
    scenarios: (raw.scenarios ?? []).map((scenario) => ({
      ...scenario,
      status: scenario.status ?? "not_run",
      outdated: Boolean(scenario.outdated),
      step_count: scenario.step_count ?? 0,
      participants: scenario.participants ?? [],
      interactions: scenario.interactions ?? [],
    })),
  };
  integrationLog.info("sequence loaded", {
    integrationId,
    revision: sequence.revision,
    scenarios: sequence.scenarios.length,
  });
  return sequence;
}

export type SaveIntegrationSpecPayload = {
  expected_revision: number;
  pattern: IntegrationPattern | null;
  implementation_status: ImplementationStatus;
  producer_interface_id: string | null;
  consumer_interface_id: string | null;
  specification: IntegrationOperatingSpec;
};

export async function saveIntegrationSpec(
  integrationId: string,
  payload: SaveIntegrationSpecPayload,
): Promise<IntegrationContractSummary> {
  const saved = await api<{ revision: number } & Record<string, unknown>>(
    `/api/integrations/${integrationId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
  integrationLog.info("contract saved", {
    integrationId,
    revision: saved.revision,
    pattern: payload.pattern,
    implementation_status: payload.implementation_status,
  });
  return normalizeContract(saved as unknown as IntegrationContractSummary);
}

export function specFromContract(contract: IntegrationContractSummary): IntegrationOperatingSpec {
  const spec = contract.specification ?? {};
  const retry = spec.retry ?? { max_attempts: 0, backoff: "none" as BackoffStrategy };
  const security = spec.security ?? { auth_type: "none" as AuthType, notes: "" };
  return {
    retry: {
      max_attempts: retry.max_attempts ?? 0,
      backoff: retry.backoff ?? "none",
    },
    timeout_ms: spec.timeout_ms ?? null,
    idempotent: Boolean(spec.idempotent),
    idempotency_key_field_id: spec.idempotency_key_field_id ?? null,
    security: {
      auth_type: security.auth_type ?? "none",
      notes: security.notes ?? "",
    },
    routing: spec.routing ?? "",
    orchestration_role: spec.orchestration_role ?? "none",
    error_handling: spec.error_handling ?? "",
  };
}
