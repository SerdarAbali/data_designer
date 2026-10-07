import {
  loadEnterpriseArchitectureIndex,
  type ArchitectureContractRecord,
  type ArchitectureFieldRecord,
  type ArchitectureObjectRecord,
  type ArchitectureSystemRecord,
  type EnterpriseArchitectureIndex,
} from "./enterpriseArchitectureIndex";
import { emptyScenarioDocument, type ScenarioDocument } from "./scenarioModel";

const empty = { version: 1, nodes: [], edges: [] };

export async function scenarioTestIndex(): Promise<EnterpriseArchitectureIndex> {
  const systems: ArchitectureSystemRecord[] = [
    { id: "crm", name: "CRM", kind: "app" },
    { id: "erp", name: "ERP", kind: "app" },
    { id: "wms", name: "WMS", kind: "app" },
  ];
  const objects: ArchitectureObjectRecord[] = [
    { id: "crm-customer", system_id: "crm", name: "customer", label: "Customer" },
    { id: "erp-account", system_id: "erp", name: "account", label: "Account" },
    { id: "erp-error", system_id: "erp", name: "error", label: "Error" },
    { id: "wms-site", system_id: "wms", name: "site", label: "Site" },
  ];
  const field = (id: string, objectId: string): ArchitectureFieldRecord => ({
    id, object_id: objectId, name: id, label: id, data_type: "string", required: false, nullable: true,
  });
  const fields = [
    field("f-crm-name", "crm-customer"),
    field("f-erp-code", "erp-account"),
    field("f-erp-message", "erp-error"),
    field("f-wms-code", "wms-site"),
  ];
  const contracts: ArchitectureContractRecord[] = [
    {
      id: "c-push", name: "Customer push",
      source_system_id: "crm", source_object_id: "crm-customer",
      target_system_id: "erp", target_object_id: "erp-account",
      interaction_type: "REQUEST_RESPONSE", graph: empty, response_graph: empty,
      error_response_graph: empty, error_response_object_id: "erp-error",
    },
    {
      id: "c-site", name: "Site sync",
      source_system_id: "erp", source_object_id: "erp-account",
      target_system_id: "wms", target_object_id: "wms-site",
      interaction_type: "ONE_WAY", graph: empty, response_graph: empty,
    },
  ];
  return loadEnterpriseArchitectureIndex({
    systems,
    contracts,
    listObjectsForSystem: async (systemId) => objects.filter((item) => item.system_id === systemId),
    listFieldsForObject: async (objectId) => fields.filter((item) => item.object_id === objectId),
  });
}

export function sampleScenario(): ScenarioDocument {
  return {
    ...emptyScenarioDocument("c-push"),
    participants: [{ id: "user", kind: "actor", label: "Sales rep" }, { id: "crm", kind: "system", systemId: "crm" }],
    items: [
      { kind: "actor", id: "s0", fromParticipantId: "user", toParticipantId: "crm", label: "Save" },
      { kind: "contract", id: "s1", contractId: "c-push", phase: "request", sampleValues: { "f-crm-name": "acme" } },
      {
        kind: "alt",
        id: "f1",
        operands: [
          { guard: "accepted", items: [{ kind: "contract", id: "s2", contractId: "c-push", phase: "success-response" }] },
          {
            guard: "rejected",
            items: [
              { kind: "contract", id: "s3", contractId: "c-push", phase: "error-response" },
              { kind: "self", id: "s4", fromParticipantId: "crm", label: "Log" },
            ],
          },
        ],
      },
      {
        kind: "loop",
        id: "f2",
        operands: [{ guard: "each site", items: [{ kind: "contract", id: "s5", contractId: "c-site", phase: "request" }] }],
      },
    ],
    assertions: [{ id: "a1", text: "Code set", stepId: "s1", fieldId: "f-erp-code", expected: "ACME" }],
  };
}
