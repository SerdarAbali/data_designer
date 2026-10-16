import { describe, expect, it } from "vitest";

import type { ArchitectureState } from "../../architectureTypes";
import type {
  CapabilityMap,
  EnterpriseImpact,
  EnterpriseModel,
  ProcessImpact,
  StrategyTrace,
} from "../enterpriseModel";
import {
  applicationSupportGraph,
  applicationSupportMatrix,
  capabilityClusters,
  processFlows,
  strategyTraceGraph,
} from "./enterpriseCanvasModel";

const goal = {
  object_id: "goal-1", kind: "goal" as const, name: "Grow revenue", description: "Grow.",
  owner: "CFO", outcome_metric: "+10%", horizon: "FY27", process_type: null, principle_type: null,
  rationale: null, role_type: null, created_in_state_id: null,
};
const requirement = {
  object_id: "req-1", kind: "requirement" as const, name: "Real-time payments", description: null,
  owner: null, outcome_metric: null, horizon: null, process_type: null, principle_type: null,
  rationale: null, role_type: null, created_in_state_id: null,
};
const capability = {
  object_id: "cap-1", kind: "capability" as const, name: "Payment processing", description: null,
  owner: null, outcome_metric: null, horizon: null, process_type: null, principle_type: null,
  rationale: null, role_type: null, created_in_state_id: null,
};
const processObject = {
  object_id: "proc-1", kind: "process" as const, name: "Card settlement", description: null,
  owner: "Payments Ops", outcome_metric: null, horizon: null, process_type: "process", principle_type: null,
  rationale: null, role_type: null, created_in_state_id: null,
};
const role = {
  object_id: "role-1", kind: "role" as const, name: "Payments Team", description: null,
  owner: null, outcome_metric: null, horizon: null, process_type: null, principle_type: null,
  rationale: null, role_type: "role", created_in_state_id: null,
};

const application = { object_id: "sys-1", name: "Core Banking", kind: "system" };
const solution = { object_id: "sol-1", name: "Customer Onboarding", kind: "solution_boundary" };

function makeModel(links: EnterpriseModel["links"]): EnterpriseModel {
  return {
    state_id: "state-1",
    state_type: "candidate",
    editable: true,
    goals: [goal],
    requirements: [requirement],
    capabilities: [capability],
    processes: [processObject],
    principles: [],
    roles: [role],
    applications: [application, solution],
    links,
  };
}

const fullLinks: EnterpriseModel["links"] = [
  { id: "l1", source_object_id: "goal-1", target_object_id: "req-1", relationship_type: "drives" },
  { id: "l2", source_object_id: "req-1", target_object_id: "cap-1", relationship_type: "needs" },
  { id: "l3", source_object_id: "cap-1", target_object_id: "proc-1", relationship_type: "has_process" },
  { id: "l4", source_object_id: "sys-1", target_object_id: "cap-1", relationship_type: "supports" },
];

const model = makeModel(fullLinks);

const strategyTrace: StrategyTrace = {
  state_id: "state-1",
  chains: [
    {
      goal,
      steps: [{ requirement, capabilities: [capability], processes: [processObject], applications: [application] }],
      gaps: [],
    },
  ],
  unlinked_requirements: [],
  gaps: [],
};

function stateWithNodes(nodes: ArchitectureState["nodes"], manual = false): ArchitectureState {
  return {
    id: "state-1",
    workspace_id: "ws-1",
    name: "Candidate",
    state_type: "candidate",
    nodes,
    relationships: [],
    created_at: "",
    updated_at: "",
  };
}

describe("strategyTraceGraph", () => {
  it("lays out the stored chain into columns with edges from links", () => {
    const graph = strategyTraceGraph(model, strategyTrace, null);
    const kinds = new Set(graph.nodes.map((node) => node.kind));
    expect(kinds).toEqual(new Set(["goal", "requirement", "capability", "process", "application"]));
    expect(graph.edges.map((edge) => edge.type).sort()).toEqual(
      ["drives", "needs", "has_process", "supports"].sort(),
    );
  });

  it("marks a missing link as a gap without fabricating an edge", () => {
    const incomplete = strategyTraceGraph(
      makeModel([{ id: "l1", source_object_id: "goal-1", target_object_id: "req-1", relationship_type: "drives" }]),
      { state_id: "state-1", chains: [{ goal, steps: [{ requirement, capabilities: [], processes: [], applications: [] }], gaps: [] }], unlinked_requirements: [], gaps: [] },
      null,
    );
    const req = incomplete.nodes.find((node) => node.objectId === "req-1")!;
    expect(req.gap).toBe("no linked capability");
    expect(incomplete.edges.some((edge) => edge.type === "needs")).toBe(false);
  });

  it("auto-lays out when saved positions are column-inconsistent", () => {
    const state = stateWithNodes([
      { occurrence_id: "occ-goal", object_id: "goal-1", position: { x: 80, y: 60 } },
      { occurrence_id: "occ-req", object_id: "req-1", position: { x: 80, y: 260 } },
      { occurrence_id: "occ-cap", object_id: "cap-1", position: { x: 420, y: 60 } },
      { occurrence_id: "occ-proc", object_id: "proc-1", position: { x: 420, y: 260 } },
    ]);
    const graph = strategyTraceGraph(model, strategyTrace, state);
    expect(graph.useSavedLayout).toBe(false);
  });

  it("honors a user-authored (manual) layout", () => {
    const state = stateWithNodes([
      {
        occurrence_id: "occ-goal", object_id: "goal-1", position: { x: 999, y: 999 },
        display_metadata: { enterprise_manual: true },
      },
      { occurrence_id: "occ-req", object_id: "req-1", position: { x: 80, y: 260 } },
    ]);
    const graph = strategyTraceGraph(model, strategyTrace, state);
    expect(graph.useSavedLayout).toBe(true);
  });

  it("forces the automatic layout when requested", () => {
    const state = stateWithNodes([
      { occurrence_id: "occ-goal", object_id: "goal-1", position: { x: 80, y: 60 }, display_metadata: { enterprise_manual: true } },
      { occurrence_id: "occ-req", object_id: "req-1", position: { x: 80, y: 260 } },
    ]);
    const graph = strategyTraceGraph(model, strategyTrace, state, { forceAuto: true });
    expect(graph.useSavedLayout).toBe(false);
  });
});

describe("capabilityClusters", () => {
  const capabilityMap: CapabilityMap = {
    state_id: "state-1",
    capabilities: [
      { capability, processes: [processObject], applications: [application], principles: [], owner_role: role },
    ],
  };
  const impact: EnterpriseImpact = {
    state_id: "state-1", baseline_state_id: "state-current",
    changes: [{ object_id: "cap-1", kind: "capability", name: "Payment processing", change: "reused" }],
    affected_applications: [], affected_capabilities: [], affected_processes: [],
    unresolved_dependencies: [], unresolved_constraints: [], risks: [], gaps: [],
  };

  it("groups by owner role and computes coverage flags", () => {
    const clusters = capabilityClusters(model, capabilityMap, impact);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].label).toBe("Payments Team");
    const cap = clusters[0].capabilities[0];
    expect(cap.flags.lacksRequirements).toBe(false);
    expect(cap.change).toBe("reused");
  });

  it("flags capabilities missing processes, applications, owners and requirements", () => {
    const bare: CapabilityMap = {
      state_id: "state-1",
      capabilities: [{ capability, processes: [], applications: [], principles: [], owner_role: null }],
    };
    const clusters = capabilityClusters(model, bare, null);
    expect(clusters[0].label).toBe("Unowned");
    const cap = clusters[0].capabilities[0];
    expect(cap.flags.lacksProcesses).toBe(true);
    expect(cap.flags.lacksApplications).toBe(true);
    expect(cap.flags.lacksOwner).toBe(true);
    expect(cap.flags.lacksRequirements).toBe(false);
  });
});

describe("processFlows", () => {
  const processImpact: ProcessImpact = {
    state_id: "state-1",
    processes: [
      { process: processObject, capabilities: [capability], applications: [application], requirements: [requirement], governed_by: [], impacted: true },
    ],
  };

  it("resolves the connected objects and flags impact", () => {
    const flows = processFlows(model, processImpact, null);
    expect(flows).toHaveLength(1);
    expect(flows[0].capabilities.map((item) => item.name)).toEqual(["Payment processing"]);
    expect(flows[0].applications.map((item) => item.name)).toEqual(["Core Banking"]);
    expect(flows[0].impacted).toBe(true);
  });
});

describe("applicationSupportGraph", () => {
  it("preserves stored relationship direction including a nonstandard support edge", () => {
    const links: EnterpriseModel["links"] = [
      { id: "l1", source_object_id: "sys-1", target_object_id: "cap-1", relationship_type: "supports" },
      { id: "l2", source_object_id: "proc-1", target_object_id: "sol-1", relationship_type: "supports" },
    ];
    const graph = applicationSupportGraph(makeModel(links));
    const nonstandard = graph.edges.find((edge) => edge.id === "l2")!;
    expect(nonstandard.source).toBe("proc-1");
    expect(nonstandard.target).toBe("sol-1");
    expect(graph.nodes.some((node) => node.id === "sol-1")).toBe(true);
  });
});

describe("applicationSupportMatrix", () => {
  it("marks supported capabilities and satisfied requirements", () => {
    const matrix = applicationSupportMatrix({
      state_id: "state-1",
      applications: [
        { application, capabilities: [capability], processes: [], requirements: [requirement] },
      ],
    });
    expect(matrix.supported.get("sys-1")?.has("cap-1")).toBe(true);
    expect(matrix.satisfied.get("sys-1")?.has("req-1")).toBe(true);
  });
});
