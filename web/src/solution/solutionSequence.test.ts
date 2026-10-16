import { describe, expect, it } from "vitest";

import type { SolutionDesign } from "./solutionModel";
import { buildSolutionSequence, componentParticipantId, EXTERNAL_PARTICIPANT_ID } from "./solutionSequence";

const design: SolutionDesign = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  solution: {
    solution_object_id: "sol-1",
    occurrence_id: "occ-sol",
    name: "Payments Platform",
    description: null,
    owner: null,
    position: { x: 0, y: 0 },
    members: [],
    external_systems: [],
  },
  components: [
    {
      object_id: "comp-1",
      occurrence_id: "occ-comp-1",
      solution_object_id: "sol-1",
      parent_component_object_id: null,
      name: "Payment API",
      description: null,
      responsibility: null,
      component_type: "service",
      technology: null,
      position: { x: 0, y: 0 },
      created_in_state_id: "state-1",
      interfaces: [
        {
          object_id: "iface-2",
          component_object_id: "comp-1",
          name: "Ledger Client",
          description: null,
          direction: "required",
          interface_kind: "sync",
          protocol: null,
          technology: null,
          created_in_state_id: "state-1",
          operations: [
            {
              object_id: "op-1",
              interface_object_id: "iface-2",
              name: "PostEntry",
              description: null,
              operation_kind: "operation",
              request_object_id: null,
              response_object_id: null,
              ordinal: 0,
              created_in_state_id: "state-1",
            },
          ],
        },
      ],
    },
    {
      object_id: "comp-2",
      occurrence_id: "occ-comp-2",
      solution_object_id: "sol-1",
      parent_component_object_id: null,
      name: "Ledger Service",
      description: null,
      responsibility: null,
      component_type: "service",
      technology: null,
      position: { x: 0, y: 0 },
      created_in_state_id: "state-1",
      interfaces: [
        {
          object_id: "iface-3",
          component_object_id: "comp-2",
          name: "Ledger API",
          description: null,
          direction: "provided",
          interface_kind: "sync",
          protocol: null,
          technology: null,
          created_in_state_id: "state-1",
          operations: [],
        },
      ],
    },
  ],
  repositories: [],
  deployment_nodes: [],
  trust_boundaries: [],
  links: [
    { id: "l1", source_object_id: "iface-2", target_object_id: "iface-3", relationship_type: "connects_to" },
  ],
};

describe("buildSolutionSequence", () => {
  it("emits ordered request and response messages between connected components", () => {
    const { document, stepRefs } = buildSolutionSequence(design);
    const steps = document.items.filter((item) => "kind" in item && item.kind === "actor");
    expect(steps).toHaveLength(3);
    const [request, response] = steps as { fromParticipantId: string; toParticipantId: string; phase?: string }[];
    expect(request.fromParticipantId).toBe(componentParticipantId("comp-1"));
    expect(request.toParticipantId).toBe(componentParticipantId("comp-2"));
    expect(request.phase).toBe("request");
    expect(response.fromParticipantId).toBe(componentParticipantId("comp-2"));
    expect(response.toParticipantId).toBe(componentParticipantId("comp-1"));
    expect(response.phase).toBe("success-response");
    expect(stepRefs.size).toBe(3);
    expect([...stepRefs.values()][0].operationId).toBe("op-1");
  });

  it("represents interfaces without operations as a single interface message", () => {
    const { document, stepRefs } = buildSolutionSequence(design);
    const ifaceMessage = [...stepRefs.values()].find((ref) => ref.interfaceId === "iface-3");
    expect(ifaceMessage?.operationId).toBeNull();
    expect(document.items).toHaveLength(3);
  });

  it("falls back to the external participant when there is no connection", () => {
    const unlinked: SolutionDesign = { ...design, links: [] };
    const { document } = buildSolutionSequence(unlinked);
    const steps = document.items as { fromParticipantId: string; toParticipantId: string }[];
    expect(steps.some((step) => step.fromParticipantId === EXTERNAL_PARTICIPANT_ID)).toBe(true);
  });
});
