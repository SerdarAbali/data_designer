/**
 * Pure proposal-preview model.
 *
 * Derives a bounded preview from change-set operations. It never mutates
 * architecture state; geometry is frontend-only and computed elsewhere. The
 * preview uses proposal temporary IDs and canonical IDs, and every unsupported
 * operation type stays visible in the proposal panel even if it cannot be
 * previewed.
 */

import type { ProposalOperation } from "./assistantTypes";

export type PreviewBadge = "added" | "reused" | "changed";

export interface PreviewNode {
  id: string;
  label: string;
  kind: string;
  badge: PreviewBadge;
  discipline: string;
  temporary: boolean;
}

export interface PreviewEdge {
  id: string;
  source: string;
  target: string;
  relationship: string;
  badge: PreviewBadge;
  dashed: boolean;
}

export interface ProposalPreview {
  nodes: PreviewNode[];
  edges: PreviewEdge[];
  affectedDisciplines: string[];
  unsupported: string[];
}

const KIND_DISCIPLINE: Record<string, string> = {
  business_goal: "enterprise",
  business_requirement: "enterprise",
  business_capability: "enterprise",
  business_process: "enterprise",
  architecture_principle: "enterprise",
  organization_role: "enterprise",
  information_object: "information",
  information_attribute: "information",
  solution_boundary: "solution",
  component: "solution",
  interface: "solution",
  interface_operation: "solution",
  data_repository: "solution",
  deployment_node: "solution",
  trust_boundary: "solution",
};

const PREVIEWABLE = new Set([
  "create_object",
  "include_object",
  "override_object",
  "create_link",
  "record_interaction",
  "create_contract",
  "reuse_contract",
]);

function disciplineFor(kind: string): string {
  if (kind === "contract") return "integration";
  return KIND_DISCIPLINE[kind] ?? "unknown";
}

export function buildPreview(operations: ProposalOperation[]): ProposalPreview {
  const nodes = new Map<string, PreviewNode>();
  const edges: PreviewEdge[] = [];
  const unsupported: string[] = [];

  for (const operation of operations) {
    if (operation.resolution_state === "removed") continue;
    const proposed = (operation.proposed_value ?? {}) as Record<string, unknown>;
    switch (operation.domain_action) {
      case "create_object": {
        const kind = String(proposed.kind ?? operation.target_type ?? "unknown");
        const id = operation.temporary_id ?? operation.operation_id;
        nodes.set(id, {
          id,
          label: String(proposed.name ?? id),
          kind,
          badge: "added",
          discipline: disciplineFor(kind),
          temporary: true,
        });
        break;
      }
      case "include_object": {
        const id = operation.target_id ?? operation.operation_id;
        nodes.set(id, {
          id,
          label: String(proposed.name ?? operation.target_type ?? id),
          kind: String(operation.target_type ?? "unknown"),
          badge: "reused",
          discipline: disciplineFor(String(operation.target_type ?? "unknown")),
          temporary: false,
        });
        break;
      }
      case "override_object": {
        const id = operation.target_id ?? operation.operation_id;
        nodes.set(id, {
          id,
          label: String(proposed.name ?? id),
          kind: String(operation.target_type ?? "unknown"),
          badge: "changed",
          discipline: disciplineFor(String(operation.target_type ?? "unknown")),
          temporary: false,
        });
        break;
      }
      case "create_contract": {
        const id = operation.temporary_id ?? operation.operation_id;
        nodes.set(id, {
          id,
          label: String(proposed.name ?? "Contract"),
          kind: "contract",
          badge: "added",
          discipline: "integration",
          temporary: true,
        });
        break;
      }
      case "reuse_contract": {
        const id = operation.target_id ?? operation.operation_id;
        nodes.set(id, {
          id,
          label: String(proposed.name ?? "Contract"),
          kind: "contract",
          badge: "reused",
          discipline: "integration",
          temporary: false,
        });
        break;
      }
      case "create_link":
      case "record_interaction": {
        const source = String(proposed.source_ref ?? proposed.source_key ?? "");
        const target = String(proposed.target_ref ?? proposed.target_key ?? "");
        if (source && target) {
          edges.push({
            id: operation.operation_id,
            source,
            target,
            relationship: String(proposed.relationship_type ?? operation.domain_action),
            badge: operation.domain_action === "create_link" ? "added" : "changed",
            dashed: true,
          });
        }
        break;
      }
      default:
        unsupported.push(operation.domain_action);
        break;
    }
  }

  const affected = new Set<string>();
  for (const node of nodes.values()) {
    if (node.discipline !== "unknown") affected.add(node.discipline);
  }
  return {
    nodes: [...nodes.values()],
    edges,
    affectedDisciplines: [...affected].sort(),
    unsupported: [...new Set(unsupported)].sort(),
  };
}

export function isPreviewable(action: string): boolean {
  return PREVIEWABLE.has(action);
}
