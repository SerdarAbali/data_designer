import { describe, expect, it } from "vitest";

import { buildPreview, describeProposalOperation, isPreviewable } from "./assistantPreview";
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

describe("slice 7 refinement previews", () => {
  it("previews every refinement operation family readably", () => {
    const operations: ProposalOperation[] = [
      operation({
        operation_id: "op-1",
        domain_action: "set_lifecycle",
        target_id: "11111111-1111-1111-1111-111111111111",
        target_type: "catalog_system",
        before_value: { lifecycle_stage: "planned" },
        proposed_value: {
          kind: "catalog_system",
          field: "lifecycle_stage",
          value: "active",
          changes: { lifecycle_stage: "active" },
          system_name: "CRM",
        },
      }),
      operation({
        operation_id: "op-2",
        domain_action: "set_operational_status",
        target_id: "22222222-2222-2222-2222-222222222222",
        target_type: "contract",
        before_value: { operational_status: null },
        proposed_value: {
          kind: "contract",
          field: "operational_status",
          value: "live",
          changes: { operational_status: "live" },
        },
      }),
      operation({
        operation_id: "op-3",
        domain_action: "set_environment_scope",
        target_id: "33333333-3333-3333-3333-333333333333",
        target_type: "contract",
        proposed_value: {
          kind: "contract",
          field: "environment_scope",
          value: "production",
          changes: { environment_scope: "production" },
        },
      }),
      operation({
        operation_id: "op-4",
        domain_action: "set_contract_mediator",
        target_id: "44444444-4444-4444-4444-444444444444",
        target_type: "contract",
        before_value: { mediator_system_id: null, mediator_responsibility: null },
        proposed_value: {
          kind: "contract",
          contract_name: "Onboarding",
          mediator_system_id: "55555555-5555-5555-5555-555555555555",
          mediator_system_name: "FRENDS",
        },
      }),
      operation({
        operation_id: "op-5",
        domain_action: "attach_evidence",
        target_type: "evidence",
        target_id: "66666666-6666-6666-6666-666666666666",
        proposed_value: {
          target_kind: "integration",
          evidence_classification: "assumption",
          source_type: "meeting",
          source_title: "Design review",
          confidence: "medium",
        },
      }),
      operation({
        operation_id: "op-6",
        domain_action: "associate_contract_with_solution",
        target_type: "solution_integration",
        target_id: "77777777-7777-7777-7777-777777777777",
        proposed_value: {
          solution_object_id: "77777777-7777-7777-7777-777777777777",
          integration_id: "88888888-8888-8888-8888-888888888888",
          contract_name: "Onboarding",
          role: "participating",
        },
      }),
      operation({
        operation_id: "op-7",
        domain_action: "create_solution_relationship",
        target_type: "solution_relationship",
        target_id: "99999999-9999-9999-9999-999999999999",
        proposed_value: {
          source_object_id: "99999999-9999-9999-9999-999999999999",
          target_object_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          source_name: "Alpha",
          target_name: "Beta",
          relationship_type: "depends_on",
        },
      }),
    ];

    for (const item of operations) {
      expect(isPreviewable(item.domain_action)).toBe(true);
      const line = describeProposalOperation(item);
      expect(line.length).toBeGreaterThan(0);
    }

    expect(describeProposalOperation(operations[0])).toBe(
      "Lifecycle · CRM · planned → active",
    );
    expect(describeProposalOperation(operations[1])).toContain("Unspecified → live");
    expect(describeProposalOperation(operations[3])).toContain("None → FRENDS");
    expect(describeProposalOperation(operations[4])).toContain("assumption");
    expect(describeProposalOperation(operations[4])).toContain("Design review");
    expect(describeProposalOperation(operations[5])).toContain("Participating");
    expect(describeProposalOperation(operations[6])).toBe(
      "Relationship · Alpha → Beta · Depends on",
    );

    const preview = buildPreview(operations);
    expect(preview.unsupported).toEqual([]);
    // Solutions relate through an edge, not through expanded graph nodes.
    expect(preview.edges.map((edge) => edge.relationship)).toEqual([
      "Participating",
      "Depends on",
    ]);
  });

  it("never marks a refinement operation as unsupported", () => {
    const preview = buildPreview([
      operation({ operation_id: "op-1", domain_action: "attach_evidence" }),
    ]);
    expect(preview.unsupported).toEqual([]);
  });
});
