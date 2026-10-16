import { describe, expect, it } from "vitest";

import type {
  IntegrationContractSummary,
  IntegrationEndpointRef,
  IntegrationFlowPhase,
  IntegrationLandscape,
  IntegrationMessageFlow,
  IntegrationSequence,
} from "./integrationDesignModel";
import {
  flowStages,
  integrationTopology,
  interfaceRelation,
  layeredLayout,
  phaseDirection,
  resilienceItems,
  sequenceGroups,
} from "./integrationViews";

function endpoint(overrides: Partial<IntegrationEndpointRef>): IntegrationEndpointRef {
  return {
    system_id: "sys-a",
    system_name: "System A",
    object_id: "obj-a",
    object_name: "Object A",
    system_kind: "application",
    is_runtime: false,
    ...overrides,
  };
}

function contractShape(overrides: Partial<IntegrationContractSummary>): IntegrationContractSummary {
  return {
    id: "c1",
    name: "Contract",
    description: null,
    interaction_type: "REQUEST_RESPONSE",
    pattern: "request_reply",
    implementation_status: "built",
    revision: 1,
    updated_at: null,
    status: "built",
    source: endpoint({}),
    target: endpoint({
      system_id: "sys-b",
      system_name: "System B",
      object_id: "obj-b",
      object_name: "Object B",
    }),
    producer_interface: null,
    consumer_interface: null,
    has_request_graph: true,
    has_response_graph: false,
    has_error_graph: false,
    specification: {},
    target_fields_mapped: 0,
    target_fields_total: 0,
    scenario_count: 0,
    ...overrides,
  };
}

const direct = contractShape({ id: "direct", name: "Direct" });
const mediated = contractShape({
  id: "mediated",
  name: "Mediated",
  pattern: "publish_subscribe",
  target: endpoint({
    system_id: "sys-runtime",
    system_name: "Integration Runtime",
    object_id: "obj-runtime",
    object_name: "Queue",
    system_kind: "middleware",
    is_runtime: true,
  }),
  producer_interface: {
    object_id: "iface-1",
    name: "Customer Event",
    direction: "provided",
    interface_kind: "async",
    protocol: "AMQP",
    technology: null,
  },
});

const landscape: IntegrationLandscape = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  contracts: [direct, mediated],
  interfaces: [],
};

describe("integrationTopology", () => {
  it("reuses canonical ids and marks runtime-mediated contracts", () => {
    const topology = integrationTopology(landscape);
    expect(topology.mediatedContractIds).toEqual(["mediated"]);
    const runtime = topology.nodes.find((node) => node.refId === "sys-runtime");
    expect(runtime?.kind).toBe("runtime");
    expect(runtime?.runtime).toBe(true);
    const directContract = topology.nodes.find((node) => node.refId === "direct");
    expect(directContract?.kind).toBe("contract");
    expect(directContract?.mediated).toBe(false);
  });

  it("connects source to target directly and routes mediated contracts through the runtime", () => {
    const topology = integrationTopology(landscape);
    const relations = new Set(topology.edges.map((edge) => edge.relation));
    expect(relations.has("produces")).toBe(true);
    expect(relations.has("delivers")).toBe(true);
    expect(relations.has("mediated by")).toBe(true);
    expect(relations.has("provides")).toBe(true);
    expect(relations.has("publishes")).toBe(true);
  });

  it("deduplicates shared systems into a single node", () => {
    const topology = integrationTopology(landscape);
    const systemNodes = topology.nodes.filter((node) => node.id === "system:sys-a");
    expect(systemNodes).toHaveLength(1);
  });
});

describe("interfaceRelation", () => {
  it("reflects the modelled direction", () => {
    expect(
      interfaceRelation({
        object_id: "i",
        name: "I",
        direction: "provided",
        interface_kind: null,
        protocol: null,
        technology: null,
      }),
    ).toBe("provides");
    expect(
      interfaceRelation({
        object_id: "i",
        name: "I",
        direction: "required",
        interface_kind: null,
        protocol: null,
        technology: null,
      }),
    ).toBe("requires");
  });
});

describe("layeredLayout", () => {
  it("places a directed chain in increasing columns", () => {
    const positions = layeredLayout(["a", "b", "c"], [
      { source: "a", target: "b" },
      { source: "b", target: "c" },
    ]);
    expect(positions.get("a")!.x).toBeLessThan(positions.get("b")!.x);
    expect(positions.get("b")!.x).toBeLessThan(positions.get("c")!.x);
  });
});

describe("flowStages", () => {
  const request: IntegrationFlowPhase = {
    phase: "request",
    configured: true,
    node_count: 4,
    transformation_count: 2,
    transformations: [
      {
        node_id: "n1",
        type: "validate",
        label: "validate: required",
        role: "validation",
        position: { x: 200, y: 0 },
      },
      {
        node_id: "n2",
        type: "fx",
        label: "fx: upper",
        role: "transformation",
        position: { x: 300, y: 0 },
      },
    ],
    source_field_count: 1,
    target_field_count: 1,
    mapped_target_count: 1,
    target_fields: ["a"],
    unmapped_required_fields: [],
  };
  const response: IntegrationFlowPhase = {
    ...request,
    phase: "success-response",
  };
  const flow: IntegrationMessageFlow = {
    contract: contractShape({
      specification: { routing: "Route by region", retry: { max_attempts: 3, backoff: "exponential" } },
    }),
    routing: "Route by region",
    trigger_config: {},
    channel_kind: "api",
    channel_label: "API endpoint",
    phases: [request, response],
  };

  it("orders request stages from producer system to consumer system", () => {
    const stages = flowStages(flow, request);
    expect(stages[0].role).toBe("system");
    expect(stages[0].label).toBe("System A");
    expect(stages[stages.length - 1].role).toBe("system");
    expect(stages[stages.length - 1].label).toBe("System B");
    expect(stages.some((stage) => stage.role === "channel")).toBe(true);
  });

  it("reverses stages for response phases", () => {
    const stages = flowStages(flow, response);
    expect(stages[0].label).toBe("System B");
    expect(stages[stages.length - 1].label).toBe("System A");
    expect(phaseDirection("success-response")).toBe("response");
  });

  it("annotates metadata-only routing and retry as explicit stages", () => {
    const stages = flowStages(flow, request);
    const routing = stages.find((stage) => stage.id === "metadata:routing:request");
    expect(routing?.metadata).toBe(true);
    expect(routing?.detail).toBe("Route by region");
    const retry = stages.find((stage) => stage.id === "metadata:retry:request");
    expect(retry?.detail).toContain("3 attempts");
  });

  it("labels the idempotency stage with the resolved field name, never a raw id", () => {
    const idempotent: IntegrationMessageFlow = {
      ...flow,
      contract: contractShape({
        specification: {
          routing: "Route by region",
          idempotent: true,
          idempotency_key_field_id: "11111111-1111-1111-1111-111111111111",
        },
        idempotency_key_field_name: "customer_id",
      }),
    };
    const stage = flowStages(idempotent, request).find(
      (item) => item.id === "metadata:idempotency:request",
    );
    expect(stage?.detail).toBe("customer_id");
  });

  it("routes mediated flows through the modelled runtime without duplicating it", () => {
    const mediatedFlow: IntegrationMessageFlow = {
      ...flow,
      contract: mediated,
    };
    const stages = flowStages(mediatedFlow, request);
    const runtimeStages = stages.filter((stage) => stage.role === "runtime");
    expect(runtimeStages).toHaveLength(1);
    expect(runtimeStages[0].label).toBe("Integration Runtime");
    expect(runtimeStages[0].detail).toContain("mediated path");
    const channel = stages.find((stage) => stage.role === "channel");
    expect(channel?.detail).toContain("via Integration Runtime");
  });
});

describe("resilienceItems", () => {
  it("never invents behaviour ownership", () => {
    const items = resilienceItems(
      contractShape({
        specification: {
          retry: { max_attempts: 2, backoff: "linear" },
          timeout_ms: 1000,
          idempotent: true,
        },
      }),
    );
    expect(items.every((item) => item.responsibility === "undefined")).toBe(true);
    expect(items.find((item) => item.key === "retry")?.value).toBe("2 attempts");
    expect(items.find((item) => item.key === "timeout")?.value).toBe("1000 ms");
    expect(items.find((item) => item.key === "idempotency")?.value).toBe("Idempotent");
  });

  it("surfaces the resolved idempotency key field name instead of a raw UUID", () => {
    const items = resilienceItems(
      contractShape({
        specification: {
          idempotent: true,
          idempotency_key_field_id: "11111111-1111-1111-1111-111111111111",
        },
        idempotency_key_field_name: "customer_id",
      }),
    );
    expect(items.find((item) => item.key === "idempotency_key")?.value).toBe("customer_id");
  });
});

describe("sequenceGroups", () => {
  it("groups scenarios by category in a stable order", () => {
    const sequence: IntegrationSequence = {
      contract_id: "c1",
      contract_name: "Contract",
      revision: 1,
      scenarios: [
        {
          id: "s1",
          name: "Happy",
          category: "happy_path",
          status: "passing",
          revision: 1,
          outdated: false,
          step_count: 1,
          participants: [],
          interactions: [],
        },
        {
          id: "s2",
          name: "Boom",
          category: "error",
          status: "failing",
          revision: 1,
          outdated: true,
          step_count: 1,
          participants: [],
          interactions: [],
        },
      ],
    };
    const groups = sequenceGroups(sequence);
    expect(groups.map((group) => group.key)).toEqual(["happy_path", "error"]);
    expect(groups[1].items[0].outdated).toBe(true);
  });
});
