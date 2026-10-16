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
