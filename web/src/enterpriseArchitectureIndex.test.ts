import { describe, expect, it } from "vitest";
import {
  architectureIndexConcurrencyLimit,
  architectureFieldKey,
  loadEnterpriseArchitectureIndex,
  traceFieldLineage,
  type ArchitectureContractRecord,
  type ArchitectureFieldRecord,
  type ArchitectureGraphDocument,
  type ArchitectureObjectRecord,
  type ArchitectureSystemRecord,
} from "./enterpriseArchitectureIndex";

const SOURCE_FIELD = "11111111-1111-4111-8111-111111111111";
const TARGET_FIELD = "22222222-2222-4222-8222-222222222222";
const SECOND_SOURCE_FIELD = "33333333-3333-4333-8333-333333333333";
const SECOND_TARGET_FIELD = "66666666-6666-4666-8666-666666666666";

function graph(
  nodes: ArchitectureGraphDocument["nodes"] = [],
  edges: ArchitectureGraphDocument["edges"] = [],
): ArchitectureGraphDocument {
  return { version: 1, nodes, edges };
}

function node(id: string, type: string, config: Record<string, unknown> = {}) {
  return { id, type, config };
}

function edge(
  id: string,
  sourceNodeId: string,
  sourcePortId: string,
  targetNodeId: string,
  targetPortId: string,
) {
  return { id, sourceNodeId, sourcePortId, targetNodeId, targetPortId };
}

function directGraph(sourceFieldId = SOURCE_FIELD, targetFieldId = TARGET_FIELD) {
  return graph(
    [node("source", "source"), node("target", "target")],
    [edge("direct", "source", `field:${sourceFieldId}`, "target", `field:${targetFieldId}`)],
  );
}

const systems: ArchitectureSystemRecord[] = [
  { id: "system-a", name: "System A", kind: "application", description: "Source" },
  { id: "system-b", name: "System B", kind: "application", description: null },
];

const objects: ArchitectureObjectRecord[] = [
  { id: "object-a", system_id: "system-a", name: "source_record", label: "Source record" },
  { id: "object-b", system_id: "system-b", name: "target_record", label: "Target record" },
  { id: "object-free", system_id: "system-a", name: "uncontracted", label: "Uncontracted" },
];

const fields: ArchitectureFieldRecord[] = [
  {
    id: SOURCE_FIELD,
    object_id: "object-a",
    name: "common_name",
    label: "Common name",
    data_type: "string",
    required: false,
    nullable: true,
  },
  {
    id: TARGET_FIELD,
    object_id: "object-b",
    name: "common_name",
    label: "Common name",
    data_type: "string",
    required: false,
    nullable: true,
  },
  {
    id: SECOND_TARGET_FIELD,
    object_id: "object-b",
    name: "alternate_name",
    label: "Alternate name",
    data_type: "string",
    required: false,
    nullable: true,
  },
  {
    id: SECOND_SOURCE_FIELD,
    object_id: "object-free",
    name: "common_name",
    label: "Common name",
    data_type: "integer",
    required: true,
    nullable: false,
  },
];

function contract(
  overrides: Partial<ArchitectureContractRecord> = {},
): ArchitectureContractRecord {
  return {
    id: "contract-a",
    name: "A to B",
    source_system_id: "system-a",
    source_object_id: "object-a",
    target_system_id: "system-b",
    target_object_id: "object-b",
    interaction_type: "ONE_WAY",
    graph: directGraph(),
    response_graph: graph(),
    error_response_graph: graph(),
    revision: 7,
    updated_at: "2026-01-02T03:04:05Z",
    sample_rows: [],
    ...overrides,
  };
}

function catalogInput(
  contracts: readonly ArchitectureContractRecord[] = [contract()],
  options: {
    systems?: readonly ArchitectureSystemRecord[];
    objects?: readonly ArchitectureObjectRecord[];
    fields?: readonly ArchitectureFieldRecord[];
    fieldLoader?: (objectId: string) => Promise<readonly ArchitectureFieldRecord[]>;
    concurrencyLimit?: number;
  } = {},
) {
  const systemRecords = options.systems ?? systems;
  const objectRecords = options.objects ?? objects;
  const fieldRecords = options.fields ?? fields;
  return loadEnterpriseArchitectureIndex({
    systems: systemRecords,
    contracts,
    concurrencyLimit: options.concurrencyLimit,
    listObjectsForSystem: async (systemId) =>
      objectRecords.filter((item) => item.system_id === systemId),
    listFieldsForObject: options.fieldLoader ?? (async (objectId) =>
      fieldRecords.filter((item) => item.object_id === objectId)),
  });
}

describe("tenant-wide enterprise architecture index", () => {
  it("indexes tenant systems, objects, fields, and uncontracted objects by exact IDs", async () => {
    const index = await catalogInput();

    expect(index.state).toBe("complete");
    expect(index.systemsById.get("system-a")?.objectIds).toEqual(["object-a", "object-free"]);
    expect(index.objectsById.get("object-free")).toMatchObject({
      id: "object-free",
      systemId: "system-a",
      displayName: "Uncontracted",
      technicalName: "uncontracted",
      fieldIds: [SECOND_SOURCE_FIELD],
    });
    expect(index.fieldsById.get(SECOND_SOURCE_FIELD)).toMatchObject({
      systemId: "system-a",
      objectId: "object-free",
      displayName: "Common name",
      technicalName: "common_name",
      dataType: "integer",
      required: true,
      nullable: false,
    });
  });

  it("retains every supplied paginated contract and its saved-state metadata", async () => {
    const second = contract({ id: "contract-b", name: "Second" });
    const index = await catalogInput([contract(), second]);

    expect([...index.contractsById.keys()]).toEqual(["contract-a", "contract-b"]);
    expect(index.contractsById.get("contract-a")?.revision).toBe(7);
    expect(index.contractsById.get("contract-a")?.savedState?.updatedAt).toBe("2026-01-02T03:04:05Z");
  });

  it("derives Request endpoints from source to target", async () => {
    const index = await catalogInput();
    const [request] = index.phasesByContractId.get("contract-a") ?? [];

    expect(request).toMatchObject({
      phase: "request",
      senderSystemId: "system-a",
      senderObjectId: "object-a",
      receiverSystemId: "system-b",
      receiverObjectId: "object-b",
      configured: true,
    });
    expect(request?.chains[0]?.inputs[0]?.senderFieldId).toBe(SOURCE_FIELD);
    expect(request?.chains[0]?.receiverFieldId).toBe(TARGET_FIELD);
  });

  it("derives Success Response endpoints from target to source", async () => {
    const index = await catalogInput([contract({ interaction_type: "REQUEST_RESPONSE" })]);
    const response = index.phasesByContractId.get("contract-a")?.find(
      (phase) => phase.phase === "success-response",
    );

    expect(response).toMatchObject({
      senderSystemId: "system-b",
      senderObjectId: "object-b",
      receiverSystemId: "system-a",
      receiverObjectId: "object-a",
      graph: expect.objectContaining({ version: 1 }),
    });
  });

  it("represents an async response graph once with async phase identity", async () => {
    const responseGraph = directGraph(TARGET_FIELD, SOURCE_FIELD);
    const index = await catalogInput([
      contract({ interaction_type: "ASYNC_CALLBACK", response_graph: responseGraph }),
    ]);
    const phases = index.phasesByContractId.get("contract-a") ?? [];

    expect(phases.map((phase) => phase.phase)).toEqual([
      "request",
      "async-response",
      "error-response",
    ]);
    expect(phases.filter((phase) => phase.graph === index.contractsById.get("contract-a")?.responseGraph.document))
      .toHaveLength(1);
  });

  it("derives Error Response endpoints from its configured object to the source", async () => {
    const errorObject: ArchitectureObjectRecord = {
      id: "error-object",
      system_id: "system-b",
      name: "error_record",
      label: "Error record",
    };
    const errorField: ArchitectureFieldRecord = {
      id: "44444444-4444-4444-8444-444444444444",
      object_id: "error-object",
      name: "error",
      label: "Error",
      data_type: "string",
      required: false,
      nullable: true,
    };
    const errorGraph = directGraph(errorField.id, SOURCE_FIELD);
    const index = await catalogInput([
      contract({
        interaction_type: "REQUEST_RESPONSE",
        error_response_object_id: "error-object",
        error_response_graph: errorGraph,
      }),
    ], {
      objects: [...objects, errorObject],
      fields: [...fields, errorField],
    });
    const errorPhase = index.phasesByContractId.get("contract-a")?.find(
      (phase) => phase.phase === "error-response",
    );

    expect(errorPhase).toMatchObject({
      senderSystemId: "system-b",
      senderObjectId: "error-object",
      receiverSystemId: "system-a",
      receiverObjectId: "object-a",
      configured: true,
    });
  });

  it("marks an absent error response object unconfigured without degrading load state", async () => {
    const index = await catalogInput([contract({ interaction_type: "REQUEST_RESPONSE" })]);
    const errorPhase = index.phasesByContractId.get("contract-a")?.find(
      (phase) => phase.phase === "error-response",
    );

    expect(index.state).toBe("complete");
    expect(errorPhase).toMatchObject({
      configured: false,
      senderObjectId: null,
      validationSummary: { status: "Unconfigured" },
    });
    expect(index.loadDiagnostics.some((item) => item.code === "unconfigured_error_response")).toBe(true);
  });

  it("creates only the Request phase for one-way contracts", async () => {
    const index = await catalogInput();

    expect(index.phasesByContractId.get("contract-a")?.map((phase) => phase.phase)).toEqual(["request"]);
  });

  it("indexes exact graph field references without conflating same-name fields", async () => {
    const index = await catalogInput();

    expect(index.contractsByFieldId.get(SOURCE_FIELD)).toEqual(["contract-a"]);
    expect(index.contractsByFieldId.get(TARGET_FIELD)).toEqual(["contract-a"]);
    expect(index.contractsByFieldId.has(SECOND_SOURCE_FIELD)).toBe(false);
    expect(index.fieldsById.get(SOURCE_FIELD)?.id).not.toBe(index.fieldsById.get(TARGET_FIELD)?.id);
  });

  it("retains direct chains and transformation execution order", async () => {
    const transformed = graph(
      [
        node("source", "source"),
        node("first", "fx", { function: "toString" }),
        node("second", "fx", { function: "toInteger" }),
        node("target", "target"),
      ],
      [
        edge("one", "source", `field:${SOURCE_FIELD}`, "first", "input"),
        edge("two", "first", "output", "second", "input"),
        edge("three", "second", "output", "target", `field:${TARGET_FIELD}`),
      ],
    );
    const index = await catalogInput([contract({ graph: transformed })], {
      fields: [
        fields[0]!,
        { ...fields[1]!, data_type: "integer" },
        fields[2]!,
      ],
    });
    const chain = index.phasesByContractId.get("contract-a")?.[0]?.chains[0];

    expect(chain?.transformations.map((item) => item.nodeId)).toEqual(["first", "second"]);
    expect(chain?.validation?.status).toBe("Valid");
  });

  it("retains every fan-in sender in the derived chain", async () => {
    const fanIn = graph(
      [node("source", "source"), node("merge", "concat"), node("target", "target")],
      [
        edge("first-in", "source", `field:${SOURCE_FIELD}`, "merge", "input"),
        edge("second-in", "source", `field:${SECOND_SOURCE_FIELD}`, "merge", "input"),
        edge("out", "merge", "output", "target", `field:${TARGET_FIELD}`),
      ],
    );
    const index = await catalogInput([contract({ graph: fanIn })], {
      fields: [
        fields[0]!,
        fields[1]!,
        { ...fields[2]!, object_id: "object-a" },
      ],
    });
    const chain = index.phasesByContractId.get("contract-a")?.[0]?.chains[0];

    expect(chain?.inputs.map((input) => input.senderFieldId)).toEqual([SOURCE_FIELD, SECOND_SOURCE_FIELD]);
    expect(chain?.issues.some((item) => item.code === "multiple_inputs_need_review")).toBe(true);
  });

  it("reports broken and cyclic chain diagnostics", async () => {
    const broken = graph(
      [node("source", "source"), node("target", "target")],
      [edge("broken", "absent", "output", "target", `field:${TARGET_FIELD}`)],
    );
    const index = await catalogInput([contract({ graph: broken })]);

    expect(index.loadDiagnostics.some((item) =>
      item.code === "mapping_graph_issue" && item.issue?.code === "missing_transformation_node",
    )).toBe(true);

    const cyclic = graph(
      [node("source", "source"), node("loop", "fx", { function: "toString" }), node("target", "target")],
      [
        edge("into-loop", "loop", "output", "loop", "input"),
        edge("out", "loop", "output", "target", `field:${TARGET_FIELD}`),
      ],
    );
    const cycleIndex = await catalogInput([contract({ graph: cyclic })]);
    expect(cycleIndex.loadDiagnostics.some((item) => item.issue?.code === "cycle")).toBe(true);
  });

  it("diagnoses exact field IDs missing from the referenced endpoint schema", async () => {
    const unknownField = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const index = await catalogInput([contract({ graph: directGraph(unknownField, TARGET_FIELD) })]);

    expect(index.loadDiagnostics.some((item) =>
      item.code === "missing_referenced_field" && item.fieldId === unknownField,
    )).toBe(true);
    expect(index.contractsByFieldId.get(unknownField)).toEqual(["contract-a"]);
  });

  it("rolls mapping validation up independently from architecture health and lifecycle", async () => {
    const requiredReceiver: ArchitectureFieldRecord = {
      ...fields[1]!,
      required: true,
      nullable: false,
    };
    const index = await catalogInput([contract({
      graph: graph(),
    })], {
      fields: [fields[0]!, requiredReceiver, fields[2]!],
    });
    const built = index.contractsById.get("contract-a");

    expect(built?.validationStatus).toBe("Errors");
    expect(index.phasesByContractId.get("contract-a")?.[0]?.validationSummary).toMatchObject({
      status: "Errors",
      errorCount: 1,
      requiredUnmappedReceiverCount: 1,
      optionalUnmappedReceiverCount: 1,
    });
    expect(built?.architectureHealth).toBeNull();
    expect("lifecycle" in (built ?? {})).toBe(false);
  });

  it("keeps architecture health separate from mapping validation", async () => {
    const index = await loadEnterpriseArchitectureIndex({
      systems,
      contracts: [contract()],
      architectureHealth: [{
        id: "contract-a",
        status: "attention",
        reasons: ["architecture conflict"],
        conflict_fields: [{
          object_id: "object-b",
          field_id: TARGET_FIELD,
          object_label: "Target",
          field_label: "Common name",
        }],
      }],
      listObjectsForSystem: async (systemId) => objects.filter((item) => item.system_id === systemId),
      listFieldsForObject: async (objectId) => fields.filter((item) => item.object_id === objectId),
    });

    expect(index.contractsById.get("contract-a")?.validationStatus).toBe("Valid");
    expect(index.contractsById.get("contract-a")?.architectureHealth).toMatchObject({
      status: "attention",
      reasons: ["architecture conflict"],
    });
  });

  it("counts optional unmapped receivers separately from validation errors", async () => {
    const optionalTarget = { ...fields[1]!, required: false, nullable: true };
    const index = await catalogInput([contract({ graph: graph() })], {
      fields: [fields[0]!, optionalTarget, fields[2]!],
    });

    expect(index.phasesByContractId.get("contract-a")?.[0]?.validationSummary).toMatchObject({
      status: "Valid",
      requiredUnmappedReceiverCount: 0,
      optionalUnmappedReceiverCount: 2,
      errorCount: 0,
    });
  });

  it("keeps successful catalog records and reports partial field failures", async () => {
    const index = await catalogInput([contract()], {
      fieldLoader: async (objectId) => {
        if (objectId === "object-a") throw new Error("field service unavailable");
        return fields.filter((item) => item.object_id === objectId);
      },
    });

    expect(index.state).toBe("partial");
    expect(index.systemsById.has("system-a")).toBe(true);
    expect(index.objectsById.has("object-a")).toBe(true);
    expect(index.fieldsById.has(TARGET_FIELD)).toBe(true);
    expect(index.loadDiagnostics).toContainEqual(expect.objectContaining({
      code: "field_load_failed",
      objectId: "object-a",
    }));
    expect(index.phasesByContractId.get("contract-a")?.[0]?.validationSummary.status).toBe("Incomplete");
  });

  it("never exceeds its configured concurrent object and field requests", async () => {
    let active = 0;
    let maximum = 0;
    const wait = async () => {
      active += 1;
      maximum = Math.max(maximum, active);
      await new Promise((resolve) => setTimeout(resolve, 1));
      active -= 1;
    };
    const manySystems = Array.from({ length: 8 }, (_, index) => ({
      id: `s${index}`,
      name: `System ${index}`,
      kind: "application",
    }));
    const manyObjects = manySystems.map((system, index) => ({
      id: `o${index}`,
      system_id: system.id,
      name: `object${index}`,
      label: `Object ${index}`,
    }));
    const index = await loadEnterpriseArchitectureIndex({
      systems: manySystems,
      contracts: [],
      concurrencyLimit: 3,
      listObjectsForSystem: async (systemId) => {
        await wait();
        return manyObjects.filter((item) => item.system_id === systemId);
      },
      listFieldsForObject: async () => {
        await wait();
        return [];
      },
    });

    expect(architectureIndexConcurrencyLimit).toBe(6);
    expect(maximum).toBe(3);
    expect(index.objectsById.size).toBe(8);
  });

  it("does not mutate API records or graph documents and exposes immutable indexes", async () => {
    const persisted = contract();
    const originalGraph = JSON.stringify(persisted.graph);
    const index = await catalogInput([persisted]);
    const indexedGraph = index.contractsById.get("contract-a")?.requestGraph.document;

    expect(JSON.stringify(persisted.graph)).toBe(originalGraph);
    expect(Object.isFrozen(persisted.graph)).toBe(false);
    expect(indexedGraph && Object.isFrozen(indexedGraph)).toBe(true);
    expect(() => (index.systemsById as Map<string, unknown>).set("other", {})).toThrow();
    let exposedMap: ReadonlyMap<string, unknown> | null = null;
    index.systemsById.forEach((_system, _id, map) => { exposedMap = map; });
    expect(exposedMap).toBe(index.systemsById);
    expect(() => (exposedMap as Map<string, unknown> | null)?.clear()).toThrow();
  });

  it("marks malformed graphs and missing endpoint records incomplete", async () => {
    const malformed = contract({
      graph: { version: 1, nodes: [{ id: "source" }], edges: [] } as unknown as ArchitectureGraphDocument,
      target_object_id: "missing-object",
    });
    const index = await catalogInput([malformed]);

    expect(index.state).toBe("partial");
    expect(index.loadDiagnostics.some((item) => item.code === "malformed_phase_graph")).toBe(true);
    expect(index.loadDiagnostics.some((item) =>
      item.code === "missing_contract_object" && item.objectId === "missing-object",
    )).toBe(true);
    expect(index.phasesByContractId.get("contract-a")?.[0]?.validationSummary.status).toBe("Incomplete");
  });

  it("traces upstream and downstream only through exact system/object/field endpoints", async () => {
    const thirdSystem: ArchitectureSystemRecord = {
      id: "system-c",
      name: "System C",
      kind: "application",
    };
    const thirdObject: ArchitectureObjectRecord = {
      id: "object-c",
      system_id: "system-c",
      name: "third_record",
      label: "Third record",
    };
    const thirdField: ArchitectureFieldRecord = {
      id: "55555555-5555-4555-8555-555555555555",
      object_id: "object-c",
      name: "common_name",
      label: "Common name",
      data_type: "string",
      required: false,
      nullable: true,
    };
    const upstreamContract = contract({ id: "upstream", name: "A to B" });
    const downstreamContract = contract({
      id: "downstream",
      name: "B to C",
      source_system_id: "system-b",
      source_object_id: "object-b",
      target_system_id: "system-c",
      target_object_id: "object-c",
      graph: directGraph(TARGET_FIELD, thirdField.id),
    });
    const index = await catalogInput([upstreamContract, downstreamContract], {
      systems: [...systems, thirdSystem],
      objects: [...objects, thirdObject],
      fields: [...fields, thirdField],
    });

    const downstream = traceFieldLineage(
      index,
      { systemId: "system-a", objectId: "object-a", fieldId: SOURCE_FIELD },
      "downstream",
      1,
    );
    expect(downstream.hops.map((item) => item.hop.contractId)).toEqual(["upstream"]);
    expect(downstream.fields).toHaveLength(2);

    const both = traceFieldLineage(
      index,
      { systemId: "system-b", objectId: "object-b", fieldId: TARGET_FIELD },
      "both",
      2,
    );
    expect(new Set(both.hops.map((item) => item.hop.contractId))).toEqual(
      new Set(["upstream", "downstream"]),
    );
    expect(both.fields.map((item) => item.key)).toContain(
      architectureFieldKey("system-c", "object-c", thirdField.id),
    );
    expect(() => traceFieldLineage(
      index,
      { systemId: "system-c", objectId: "object-c", fieldId: TARGET_FIELD },
      "both",
      2,
    )).toThrow(/not present/);
  });

  it("deduplicates reachable fields at their shortest distance through branches", async () => {
    const branchGraph = graph(
      [node("source", "source"), node("target", "target")],
      [
        edge("branch-one", "source", `field:${SOURCE_FIELD}`, "target", `field:${TARGET_FIELD}`),
        edge("branch-two", "source", `field:${SOURCE_FIELD}`, "target", `field:${SECOND_TARGET_FIELD}`),
      ],
    );
    const index = await catalogInput([contract({ graph: branchGraph })]);
    const trace = traceFieldLineage(
      index,
      { systemId: "system-a", objectId: "object-a", fieldId: SOURCE_FIELD },
      "downstream",
      4,
    );

    expect(trace.fields).toHaveLength(3);
    expect(trace.hops).toHaveLength(2);
  });
});
