import { api } from "../information/api";
import { solutionLog } from "./solutionLog";

export type SolutionDirection = "provided" | "required";
export type SolutionOperationKind = "operation" | "event" | "command" | "query";
export type SolutionInterfaceKind = "sync" | "async";

export const SOLUTION_COMPONENT_TYPES = [
  "application",
  "service",
  "data",
  "ui",
  "integration",
  "infrastructure",
] as const;

export type SolutionOperation = {
  object_id: string;
  interface_object_id: string;
  name: string;
  description: string | null;
  operation_kind: SolutionOperationKind;
  request_object_id: string | null;
  response_object_id: string | null;
  ordinal: number;
  created_in_state_id: string | null;
};

export type SolutionInterface = {
  object_id: string;
  component_object_id: string | null;
  name: string;
  description: string | null;
  direction: SolutionDirection;
  interface_kind: SolutionInterfaceKind | null;
  protocol: string | null;
  technology: string | null;
  created_in_state_id: string | null;
  operations: SolutionOperation[];
};

export type SolutionComponent = {
  object_id: string;
  occurrence_id: string;
  solution_object_id: string | null;
  parent_component_object_id: string | null;
  name: string;
  description: string | null;
  responsibility: string | null;
  component_type: string | null;
  technology: string | null;
  position: { x: number; y: number };
  created_in_state_id: string | null;
  interfaces: SolutionInterface[];
};

export type SolutionRepository = {
  object_id: string;
  solution_object_id: string | null;
  name: string;
  description: string | null;
  owner: string | null;
  repository_type: string | null;
  technology: string | null;
  created_in_state_id: string | null;
};

export type SolutionDeploymentNode = {
  object_id: string;
  solution_object_id: string | null;
  name: string;
  description: string | null;
  technology: string | null;
  environment: string | null;
  hosting: string | null;
  created_in_state_id: string | null;
};

export type SolutionTrustBoundary = {
  object_id: string;
  solution_object_id: string | null;
  name: string;
  description: string | null;
  security_level: string | null;
  created_in_state_id: string | null;
};

export type SolutionMember = { system_id: string; name: string; kind: string };

export type SolutionContext = {
  solution_object_id: string;
  occurrence_id: string;
  name: string;
  description: string | null;
  owner: string | null;
  position: { x: number; y: number };
  members: SolutionMember[];
  external_systems: SolutionMember[];
};

export type SolutionLink = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  relationship_type: string;
};

export type SolutionDesign = {
  state_id: string;
  state_type: string;
  editable: boolean;
  solution: SolutionContext;
  components: SolutionComponent[];
  repositories: SolutionRepository[];
  deployment_nodes: SolutionDeploymentNode[];
  trust_boundaries: SolutionTrustBoundary[];
  links: SolutionLink[];
};

export type SolutionSummary = {
  object_id: string;
  occurrence_id: string;
  name: string;
  description: string | null;
  component_count: number;
  member_count: number;
};

// --- Solution Boundary <-> Contract association ------------------------------

export type SolutionContractRole = "owned" | "participating" | "dependency";

export const SOLUTION_CONTRACT_ROLES: SolutionContractRole[] = [
  "owned",
  "participating",
  "dependency",
];

export const SOLUTION_CONTRACT_ROLE_LABELS: Record<SolutionContractRole, string> = {
  owned: "Owned by this solution",
  participating: "Participating",
  dependency: "Dependency",
};

export type SolutionContractEndpoint = {
  system_id: string;
  system_name: string;
  object_id: string;
  object_name: string;
  system_kind?: string | null;
  is_runtime?: boolean;
};

export type SolutionContractMediator = {
  system_id: string;
  system_name: string;
  is_runtime?: boolean;
  responsibility?: string | null;
  explicit?: boolean;
};

export type SolutionContractFact = {
  value: string | null;
  canonical: string | null;
  override: string | null;
  overridden: boolean;
};

/** The bounded Contract projection the Solution inspector may display. */
export type SolutionContractSummary = {
  id: string;
  name: string;
  interaction_type: string;
  implementation_status: string;
  source: SolutionContractEndpoint;
  target: SolutionContractEndpoint;
  mediator: SolutionContractMediator | null;
  explicit_mediator: boolean;
  mediated: boolean;
  mediation_source: "explicit" | "legacy_endpoint_heuristic" | "none";
  evidence_count: number;
  lifecycle_stage: SolutionContractFact;
  operational_status: SolutionContractFact;
  environment_scope: SolutionContractFact;
};

export type SolutionIntegration = {
  id: string;
  tenant_id: string;
  solution_object_id: string;
  integration_id: string;
  role: SolutionContractRole;
  description: string | null;
  created_in_state_id: string | null;
  state_applicability: "canonical" | "state";
  state_name: string | null;
  created_at: string;
  updated_at: string;
  contract: SolutionContractSummary;
};

const base = (workspaceId: string) => `/api/workspaces/${workspaceId}/solution`;

async function run<T>(action: string, task: () => Promise<T>): Promise<T> {
  solutionLog.info(action);
  try {
    const result = await task();
    solutionLog.info(`${action} ok`);
    return result;
  } catch (caught) {
    solutionLog.error(`${action} failed`, caught);
    throw caught;
  }
}

export function listSolutions(workspaceId: string, stateId: string): Promise<SolutionSummary[]> {
  return run("list solutions", () =>
    api<SolutionSummary[]>(`${base(workspaceId)}/solutions?state_id=${stateId}`),
  );
}

export function fetchSolutionDesign(
  workspaceId: string,
  solutionId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("load design", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/design?state_id=${stateId}`),
  );
}

export function createSolution(
  workspaceId: string,
  body: { state_id: string; name: string; description?: string; owner?: string; position?: { x: number; y: number } },
): Promise<SolutionDesign> {
  return run("create solution", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateSolution(
  workspaceId: string,
  solutionId: string,
  stateId: string,
  patch: { name?: string; description?: string | null; owner?: string | null },
): Promise<SolutionDesign> {
  return run("update solution", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}?state_id=${stateId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function addSolutionMember(
  workspaceId: string,
  solutionId: string,
  body: { state_id: string; system_id: string },
): Promise<SolutionDesign> {
  return run("add member", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/members`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function removeSolutionMember(
  workspaceId: string,
  solutionId: string,
  systemId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("remove member", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/members/${systemId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function createComponent(
  workspaceId: string,
  solutionId: string,
  body: {
    state_id: string;
    name: string;
    description?: string;
    responsibility?: string;
    component_type?: string;
    technology?: string;
    parent_component_object_id?: string | null;
    position: { x: number; y: number };
  },
): Promise<SolutionDesign> {
  return run("create component", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/components`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateComponent(
  workspaceId: string,
  componentId: string,
  patch: {
    state_id: string;
    name?: string;
    description?: string | null;
    responsibility?: string | null;
    component_type?: string | null;
    technology?: string | null;
  },
): Promise<SolutionDesign> {
  return run("update component", () =>
    api<SolutionDesign>(`${base(workspaceId)}/components/${componentId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteComponent(
  workspaceId: string,
  componentId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("delete component", () =>
    api<SolutionDesign>(`${base(workspaceId)}/components/${componentId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function createInterface(
  workspaceId: string,
  componentId: string,
  body: {
    state_id: string;
    name: string;
    description?: string;
    direction: SolutionDirection;
    interface_kind?: SolutionInterfaceKind | null;
    protocol?: string;
    technology?: string;
  },
): Promise<SolutionDesign> {
  return run("create interface", () =>
    api<SolutionDesign>(`${base(workspaceId)}/components/${componentId}/interfaces`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateInterface(
  workspaceId: string,
  interfaceId: string,
  patch: {
    state_id: string;
    name?: string;
    description?: string | null;
    direction?: SolutionDirection;
    interface_kind?: SolutionInterfaceKind | null;
    protocol?: string | null;
    technology?: string | null;
  },
): Promise<SolutionDesign> {
  return run("update interface", () =>
    api<SolutionDesign>(`${base(workspaceId)}/interfaces/${interfaceId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteInterface(
  workspaceId: string,
  interfaceId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("delete interface", () =>
    api<SolutionDesign>(`${base(workspaceId)}/interfaces/${interfaceId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function createOperation(
  workspaceId: string,
  interfaceId: string,
  body: { state_id: string; name: string; operation_kind: SolutionOperationKind; description?: string },
): Promise<SolutionDesign> {
  return run("create operation", () =>
    api<SolutionDesign>(`${base(workspaceId)}/interfaces/${interfaceId}/operations`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateOperation(
  workspaceId: string,
  operationId: string,
  patch: {
    state_id: string;
    name?: string;
    description?: string | null;
    operation_kind?: SolutionOperationKind;
  },
): Promise<SolutionDesign> {
  return run("update operation", () =>
    api<SolutionDesign>(`${base(workspaceId)}/operations/${operationId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteOperation(
  workspaceId: string,
  operationId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("delete operation", () =>
    api<SolutionDesign>(`${base(workspaceId)}/operations/${operationId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function createRepository(
  workspaceId: string,
  solutionId: string,
  body: {
    state_id: string;
    name: string;
    description?: string;
    owner?: string;
    repository_type?: string;
    technology?: string;
  },
): Promise<SolutionDesign> {
  return run("create repository", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/repositories`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function createDeploymentNode(
  workspaceId: string,
  solutionId: string,
  body: {
    state_id: string;
    name: string;
    description?: string;
    technology?: string;
    environment?: string;
    hosting?: string;
  },
): Promise<SolutionDesign> {
  return run("create deployment node", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/deployment-nodes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function createTrustBoundary(
  workspaceId: string,
  solutionId: string,
  body: { state_id: string; name: string; description?: string; security_level?: string },
): Promise<SolutionDesign> {
  return run("create trust boundary", () =>
    api<SolutionDesign>(`${base(workspaceId)}/solutions/${solutionId}/trust-boundaries`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function linkComponentRepository(
  workspaceId: string,
  componentId: string,
  body: { state_id: string; target_object_id: string | null },
): Promise<SolutionDesign> {
  return run("link repository", () =>
    api<SolutionDesign>(`${base(workspaceId)}/components/${componentId}/repository`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export function linkComponentDeployment(
  workspaceId: string,
  componentId: string,
  body: { state_id: string; target_object_id: string | null },
): Promise<SolutionDesign> {
  return run("link deployment", () =>
    api<SolutionDesign>(`${base(workspaceId)}/components/${componentId}/deployment`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export function linkInterfaceTrustBoundary(
  workspaceId: string,
  interfaceId: string,
  body: { state_id: string; target_object_id: string | null },
): Promise<SolutionDesign> {
  return run("link trust boundary", () =>
    api<SolutionDesign>(`${base(workspaceId)}/interfaces/${interfaceId}/trust-boundary`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export function linkInterfaceConnection(
  workspaceId: string,
  interfaceId: string,
  body: { state_id: string; target_object_id: string | null },
): Promise<SolutionDesign> {
  return run("link interface connection", () =>
    api<SolutionDesign>(`${base(workspaceId)}/interfaces/${interfaceId}/connection`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export function linkTrustBoundaryContainment(
  workspaceId: string,
  sourceObjectId: string,
  body: { state_id: string; target_object_id: string | null },
): Promise<SolutionDesign> {
  return run("link trust containment", () =>
    api<SolutionDesign>(`${base(workspaceId)}/containment/${sourceObjectId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export function updateRepository(
  workspaceId: string,
  repositoryId: string,
  patch: {
    state_id: string;
    name?: string;
    description?: string | null;
    owner?: string | null;
    repository_type?: string | null;
    technology?: string | null;
  },
): Promise<SolutionDesign> {
  return run("update repository", () =>
    api<SolutionDesign>(`${base(workspaceId)}/repositories/${repositoryId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteRepository(
  workspaceId: string,
  repositoryId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("delete repository", () =>
    api<SolutionDesign>(`${base(workspaceId)}/repositories/${repositoryId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function updateDeploymentNode(
  workspaceId: string,
  deploymentId: string,
  patch: {
    state_id: string;
    name?: string;
    description?: string | null;
    technology?: string | null;
    environment?: string | null;
    hosting?: string | null;
  },
): Promise<SolutionDesign> {
  return run("update deployment node", () =>
    api<SolutionDesign>(`${base(workspaceId)}/deployment-nodes/${deploymentId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteDeploymentNode(
  workspaceId: string,
  deploymentId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("delete deployment node", () =>
    api<SolutionDesign>(`${base(workspaceId)}/deployment-nodes/${deploymentId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

export function updateTrustBoundary(
  workspaceId: string,
  trustId: string,
  patch: { state_id: string; name?: string; description?: string | null; security_level?: string | null },
): Promise<SolutionDesign> {
  return run("update trust boundary", () =>
    api<SolutionDesign>(`${base(workspaceId)}/trust-boundaries/${trustId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteTrustBoundary(
  workspaceId: string,
  trustId: string,
  stateId: string,
): Promise<SolutionDesign> {
  return run("delete trust boundary", () =>
    api<SolutionDesign>(`${base(workspaceId)}/trust-boundaries/${trustId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}

// --- Solution Boundary <-> Contract associations ------------------------------

function contractBase(workspaceId: string, solutionId: string): string {
  return `${base(workspaceId)}/solutions/${solutionId}/contracts`;
}

export function listSolutionContracts(
  workspaceId: string,
  solutionId: string,
  stateId: string,
): Promise<SolutionIntegration[]> {
  return run("list solution contracts", () =>
    api<SolutionIntegration[]>(`${contractBase(workspaceId, solutionId)}?state_id=${stateId}`),
  );
}

export function createSolutionContract(
  workspaceId: string,
  solutionId: string,
  body: {
    state_id: string;
    integration_id: string;
    role: SolutionContractRole;
    description?: string | null;
  },
): Promise<SolutionIntegration> {
  return run("associate contract", () =>
    api<SolutionIntegration>(contractBase(workspaceId, solutionId), {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateSolutionContract(
  workspaceId: string,
  solutionId: string,
  associationId: string,
  patch: { role?: SolutionContractRole; description?: string | null },
): Promise<SolutionIntegration> {
  return run("update contract association", () =>
    api<SolutionIntegration>(`${contractBase(workspaceId, solutionId)}/${associationId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
}

export function deleteSolutionContract(
  workspaceId: string,
  solutionId: string,
  associationId: string,
): Promise<void> {
  return run("remove contract association", () =>
    api<void>(`${contractBase(workspaceId, solutionId)}/${associationId}`, { method: "DELETE" }),
  );
}

export type AssociableContract = { id: string; name: string };

/**
 * Contracts that can be associated with a solution. The bounded integration list
 * is used rather than the full Integration Landscape, so the Solution workbench
 * never depends on the Integration discipline being enabled.
 */
export function listAssociableContracts(workspaceId: string): Promise<AssociableContract[]> {
  return run("list associable contracts", async () => {
    const rows = await api<{ id: string; name: string }[]>(
      `/api/integrations?limit=500&offset=0`,
    );
    return rows
      .map((row) => ({ id: row.id, name: row.name }))
      .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
  });
}

// --- Solution Landscape -------------------------------------------------------

export type SolutionRelationshipType =
  | "depends_on"
  | "uses"
  | "provides_to"
  | "replaces"
  | "transitions_to"
  | "shares_information_with";

export const SOLUTION_RELATIONSHIP_TYPES: SolutionRelationshipType[] = [
  "depends_on",
  "uses",
  "provides_to",
  "replaces",
  "transitions_to",
  "shares_information_with",
];

export const SOLUTION_RELATIONSHIP_LABELS: Record<SolutionRelationshipType, string> = {
  depends_on: "Depends on",
  uses: "Uses",
  provides_to: "Provides to",
  replaces: "Replaces",
  transitions_to: "Transitions to",
  shares_information_with: "Shares information with",
};

/** Stored in one canonical direction, presented symmetrically. */
export const SYMMETRIC_SOLUTION_RELATIONSHIPS: SolutionRelationshipType[] = [
  "shares_information_with",
];

export type SolutionLandscapeSystem = {
  system_id: string;
  name: string;
  kind: string;
  external: boolean;
};

export type SolutionLandscapeContractCounts = {
  owned: number;
  participating: number;
  dependency: number;
  total: number;
};

export type SolutionLandscapeContractAssociation = {
  association_id: string;
  role: SolutionContractRole;
  description: string | null;
  state_applicability: "canonical" | "state";
  state_name: string | null;
  contract_id: string;
  contract_name: string | null;
  available: boolean;
  implementation_status: string | null;
  lifecycle_stage: SolutionContractFact;
  operational_status: SolutionContractFact;
  environment_scope: SolutionContractFact;
  evidence_count: number;
};

export type SolutionLandscapeWarning = {
  code: string;
  message: string;
  solution_object_id: string | null;
  relationship_id: string | null;
  association_id: string | null;
  integration_id: string | null;
};

export type SolutionLandscapeNode = {
  solution_object_id: string;
  occurrence_id: string | null;
  name: string;
  description: string | null;
  owner: string | null;
  lifecycle_stage: string | null;
  operational_status: string | null;
  component_count: number;
  member_count: number;
  external_system_count: number;
  members: SolutionLandscapeSystem[];
  external_systems: SolutionLandscapeSystem[];
  contract_counts: SolutionLandscapeContractCounts;
  contracts: SolutionLandscapeContractAssociation[];
  evidence_count: number;
  relationships_in: number;
  relationships_out: number;
};

export type SolutionLandscapeEdge = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  relationship_type: SolutionRelationshipType;
  description: string | null;
  created_in_state_id: string | null;
  state_applicability: "canonical" | "state";
  state_name: string | null;
  evidence_count: number;
};

export type SolutionLandscape = {
  state_id: string;
  state_type: string;
  editable: boolean;
  solutions: SolutionLandscapeNode[];
  relationships: SolutionLandscapeEdge[];
  warnings: SolutionLandscapeWarning[];
};

export type SolutionRelationship = {
  id: string;
  tenant_id: string;
  source_object_id: string;
  target_object_id: string;
  relationship_type: SolutionRelationshipType;
  description: string | null;
  created_in_state_id: string | null;
  state_applicability: "canonical" | "state";
  state_name: string | null;
  evidence_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export function fetchSolutionLandscape(
  workspaceId: string,
  stateId: string,
): Promise<SolutionLandscape> {
  return run("load solution landscape", () =>
    api<SolutionLandscape>(`${base(workspaceId)}/landscape?state_id=${stateId}`),
  );
}

export function createSolutionRelationship(
  workspaceId: string,
  body: {
    state_id: string;
    source_object_id: string;
    target_object_id: string;
    relationship_type: SolutionRelationshipType;
    description?: string | null;
  },
): Promise<SolutionRelationship> {
  return run("create solution relationship", () =>
    api<SolutionRelationship>(`${base(workspaceId)}/relationships`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function updateSolutionRelationship(
  workspaceId: string,
  relationshipId: string,
  stateId: string,
  patch: { relationship_type?: SolutionRelationshipType; description?: string | null },
): Promise<SolutionRelationship> {
  return run("update solution relationship", () =>
    api<SolutionRelationship>(
      `${base(workspaceId)}/relationships/${relationshipId}?state_id=${stateId}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  );
}

export function deleteSolutionRelationship(
  workspaceId: string,
  relationshipId: string,
  stateId: string,
): Promise<void> {
  return run("remove solution relationship", () =>
    api<void>(`${base(workspaceId)}/relationships/${relationshipId}?state_id=${stateId}`, {
      method: "DELETE",
    }),
  );
}
