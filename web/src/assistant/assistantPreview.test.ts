import { describe, expect, it } from "vitest";

import { buildPreview, isPreviewable } from "./assistantPreview";
import type { ProposalOperation } from "./assistantTypes";

function operation(partial: Partial<ProposalOperation> & { operation_id: string; domain_action: string }): ProposalOperation {
  return {
    ordinal: 0,
    target_type: "architecture_object",
    target_id: null,
    temporary_id: null,
    proposed_value: {},
    depends_on: [],
    validation_status: "pending",
    validation_issues: [],
    resolution_state: "active",
    ...partial,
  };
}

describe("proposal preview model", () => {
  it("builds ghost nodes, reused nodes, and dashed edges", () => {
    const preview = buildPreview([
      operation({
        operation_id: "op-1",
        domain_action: "create_object",
        temporary_id: "tmp:customer",
        proposed_value: { kind: "information_object", name: "Customer" },
      }),
      operation({
        operation_id: "op-2",
        domain_action: "include_object",
        target_id: "11111111-1111-1111-1111-111111111111",
        target_type: "component",
        proposed_value: { name: "CRM" },
      }),
      operation({
        operation_id: "op-3",
        domain_action: "create_link",
        proposed_value: {
          relationship_type: "references",
          source_ref: "tmp:customer",
          target_ref: "22222222-2222-2222-2222-222222222222",
        },
      }),
    ]);

    const badges = preview.nodes.map((node) => node.badge).sort();
    expect(badges).toEqual(["added", "reused"]);
    expect(preview.nodes.find((node) => node.badge === "added")?.temporary).toBe(true);
    expect(preview.edges).toHaveLength(1);
    expect(preview.edges[0].dashed).toBe(true);
    expect(preview.affectedDisciplines).toContain("information");
    expect(preview.affectedDisciplines).toContain("solution");
  });

  it("lists unsupported operations and skips removed ones", () => {
    const preview = buildPreview([
      operation({ operation_id: "op-1", domain_action: "create_mapping" }),
      operation({ operation_id: "op-2", domain_action: "create_object", resolution_state: "removed" }),
    ]);
    expect(preview.unsupported).toContain("create_mapping");
    expect(preview.nodes).toHaveLength(0);
    expect(isPreviewable("create_object")).toBe(true);
    expect(isPreviewable("create_mapping")).toBe(false);
  });
});
