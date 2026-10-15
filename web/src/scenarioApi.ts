import {
  loadEnterpriseArchitectureIndex,
  type ArchitectureContractRecord,
  type ArchitectureSystemRecord,
  type EnterpriseArchitectureIndex,
} from "./enterpriseArchitectureIndex";
import type {
  ScenarioCategory,
  ScenarioDocument,
  ScenarioEvaluation,
  ScenarioRecord,
} from "./scenarioModel";
import { ApiError, api as request, list } from "./apiClient";

export class ScenarioApiError extends Error {
  status: number;
  issues: readonly { message: string; stepId?: string | null }[];

  constructor(message: string, status: number, issues: ScenarioApiError["issues"] = []) {
    super(message);
    this.status = status;
    this.issues = issues;
  }
}

function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first = detail[0] as { msg?: string; loc?: unknown[] };
  const message = (first.msg ?? "Invalid scenario").replace(/^Value error, /, "");
  return detail.length > 1 ? `${message} (+${detail.length - 1} more)` : message;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await request<T>(path, init);
  } catch (caught) {
    if (caught instanceof ApiError) {
      const detail = caught.detail;
      const structured = detail as
        | { message?: string; issues?: ScenarioApiError["issues"] }
        | undefined;
      throw new ScenarioApiError(
        validationMessage(detail) ?? structured?.message ?? caught.message,
        caught.status,
        Array.isArray(structured?.issues) ? structured.issues : [],
      );
    }
    throw caught;
  }
}

/** Load the same architecture index the Landscape builds, for views that do not already have it. */
export async function loadArchitectureIndexFromApi(): Promise<EnterpriseArchitectureIndex> {
  const [systems, contracts] = await Promise.all([
    list<ArchitectureSystemRecord>("/api/catalog/systems"),
    list<ArchitectureContractRecord>("/api/integrations"),
  ]);
  return loadEnterpriseArchitectureIndex({
    systems,
    contracts,
    listObjectsForSystem: (systemId) => list(`/api/catalog/systems/${systemId}/objects`),
    listFieldsForObject: (objectId) => list(`/api/catalog/objects/${objectId}/fields`),
  });
}

export type ScenarioListScope = "all" | "contract" | "landscape";

export function listScenarios(options: {
  scope?: ScenarioListScope;
  integrationId?: string;
} = {}): Promise<ScenarioRecord[]> {
  const params = new URLSearchParams({ scope: options.scope ?? "all" });
  if (options.integrationId) params.set("integration_id", options.integrationId);
  return api(`/api/scenarios?${params.toString()}`);
}

export type ScenarioDraft = {
  name: string;
  category: ScenarioCategory;
  description: string | null;
  document: ScenarioDocument;
};

export function createScenario(
  draft: ScenarioDraft,
  scopeIntegrationId: string | null,
): Promise<ScenarioRecord> {
  return api("/api/scenarios", {
    method: "POST",
    body: JSON.stringify({ ...draft, scope_integration_id: scopeIntegrationId }),
  });
}

export function updateScenario(
  id: string,
  draft: ScenarioDraft,
  expectedRevision: number,
): Promise<ScenarioRecord> {
  return api(`/api/scenarios/${id}`, {
    method: "PUT",
    body: JSON.stringify({ ...draft, expected_revision: expectedRevision }),
  });
}

export function archiveScenario(id: string): Promise<void> {
  return api(`/api/scenarios/${id}`, { method: "DELETE" });
}

export function evaluateScenario(
  document: ScenarioDocument,
  scopeIntegrationId: string | null,
): Promise<ScenarioEvaluation> {
  return api("/api/scenarios/evaluate", {
    method: "POST",
    body: JSON.stringify({ document, scope_integration_id: scopeIntegrationId }),
  });
}
