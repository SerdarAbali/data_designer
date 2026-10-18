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
  "set_lifecycle",
  "set_operational_status",
  "set_environment_scope",
  "set_contract_mediator",
  "attach_evidence",
  "associate_contract_with_solution",
  "create_solution_relationship",
]);

/** Human labels for the Slice 7 fact operations. */
export const FACT_ACTION_LABELS: Record<string, string> = {
  set_lifecycle: "Lifecycle",
  set_operational_status: "Operational status",
  set_environment_scope: "Environment scope",
};

export const ASSOCIATION_ROLE_LABELS: Record<string, string> = {
  owned: "Owned",
  participating: "Participating",
  dependency: "Dependency",
};

export const SOLUTION_RELATIONSHIP_LABELS: Record<string, string> = {
  depends_on: "Depends on",
  uses: "Uses",
  provides_to: "Provides to",
  replaces: "Replaces",
  transitions_to: "Transitions to",
  shares_information_with: "Shares information with",
};

function factValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Unspecified";
  return String(value).replace(/_/g, " ");
}

/**
 * One readable line per proposal operation. Purely presentational: identity is
 * always the operation id and the raw values, never a display label.
 */
export function describeProposalOperation(operation: ProposalOperation): string {
  const proposed = (operation.proposed_value ?? {}) as Record<string, unknown>;
  const before = (operation.before_value ?? {}) as Record<string, unknown>;
  const target = humanizeTarget(operation, proposed);

  if (FACT_ACTION_LABELS[operation.domain_action]) {
    const field = String(proposed.field ?? "");
    const value = (proposed.changes as Record<string, unknown> | undefined)?.[field];
    const previous = before[field];
    return `${FACT_ACTION_LABELS[operation.domain_action]} · ${target} · ${factValue(previous)} → ${factValue(value)}`;
  }
  if (operation.domain_action === "set_contract_mediator") {
    const mediator = String(proposed.mediator_system_name ?? proposed.mediator_system_id ?? "—");
    const previous = before.mediator_system_id ? String(before.mediator_system_id) : "None";
    return `Mediator · ${target} · ${previous} → ${mediator}`;
  }
  if (operation.domain_action === "attach_evidence") {
    return [
      "Evidence",
      String(proposed.target_kind ?? ""),
      String(proposed.evidence_classification ?? "").replace(/_/g, " "),
      `${String(proposed.source_type ?? "")} · ${String(proposed.source_title ?? "")}`,
      `confidence ${String(proposed.confidence ?? "")}`,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  if (operation.domain_action === "associate_contract_with_solution") {
    const role = ASSOCIATION_ROLE_LABELS[String(proposed.role ?? "owned")] ?? proposed.role;
    return `Association · ${target} ← ${String(proposed.contract_name ?? proposed.integration_id ?? "")} · ${role}`;
  }
  if (operation.domain_action === "create_solution_relationship") {
    const type = SOLUTION_RELATIONSHIP_LABELS[String(proposed.relationship_type ?? "")] ?? proposed.relationship_type;
    return `Relationship · ${String(proposed.source_name ?? proposed.source_object_id ?? "")} → ${String(proposed.target_name ?? proposed.target_object_id ?? "")} · ${type}`;
  }
  if (operation.domain_action === "create_contract" || operation.domain_action === "reuse_contract") {
    return `Contract · ${String(proposed.name ?? target)}`;
  }
  return `${operation.domain_action} · ${target}`;
}

function humanizeTarget(operation: ProposalOperation, proposed: Record<string, unknown>): string {
  const name = proposed.name ?? proposed.system_name ?? proposed.contract_name;
  if (name) return String(name);
  return (
    humanizeId(operation.target_id) ||
    humanizeId(operation.temporary_id) ||
    operation.target_type ||
    operation.operation_id
  );
}

function humanizeId(value: string | null | undefined): string {
  if (!value) return "";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

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
      case "set_lifecycle":
      case "set_operational_status":
      case "set_environment_scope": {
        const id = operation.target_id ?? operation.operation_id;
        const kind = String(proposed.kind ?? operation.target_type ?? "unknown");
        nodes.set(id, {
          id,
          label: humanizeTarget(operation, proposed),
          kind,
          badge: "changed",
          discipline: kind === "contract" ? "integration" : "catalog",
          temporary: false,
        });
        break;
      }
      case "set_contract_mediator": {
        const id = operation.target_id ?? operation.operation_id;
        nodes.set(id, {
          id,
          label: String(proposed.contract_name ?? id),
          kind: "contract",
          badge: "changed",
          discipline: "integration",
          temporary: false,
        });
        break;
      }
      case "attach_evidence": {
        const id = String(proposed.target_id ?? operation.target_id ?? operation.operation_id);
        nodes.set(id, {
          id,
          label: String(proposed.target_kind ?? "evidence"),
          kind: String(proposed.target_kind ?? "evidence"),
          badge: "changed",
          discipline: "evidence",
          temporary: false,
        });
        break;
      }
      case "associate_contract_with_solution": {
        const source = String(proposed.solution_object_id ?? operation.target_id ?? "");
        const target = String(proposed.integration_id ?? "");
        if (source && target) {
          edges.push({
            id: operation.operation_id,
            source,
            target,
            relationship: ASSOCIATION_ROLE_LABELS[String(proposed.role ?? "owned")] ?? "owns",
            badge: "added",
            dashed: true,
          });
        }
        break;
      }
      case "create_solution_relationship": {
        const source = String(proposed.source_object_id ?? "");
        const target = String(proposed.target_object_id ?? "");
        if (source && target) {
          edges.push({
            id: operation.operation_id,
            source,
            target,
            relationship:
              SOLUTION_RELATIONSHIP_LABELS[String(proposed.relationship_type ?? "")] ??
              String(proposed.relationship_type ?? ""),
            badge: "added",
            dashed: false,
          });
        }
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
