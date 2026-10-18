/**
 * Pure helpers for the Solution Landscape.
 *
 * The Landscape answers ownership and dependency questions over the canonical
 * Solution Boundaries; it never expands components, systems, interfaces or full
 * Contracts into graph nodes. Layout and ordering are pure functions of the
 * projection, so arrangement is deterministic.
 */

import type { Point } from "./solutionCanvasModel";
import type {
  SolutionLandscape,
  SolutionLandscapeNode,
  SolutionRelationshipType,
} from "./solutionModel";
import { SOLUTION_RELATIONSHIP_LABELS, SYMMETRIC_SOLUTION_RELATIONSHIPS } from "./solutionModel";

export const LANDSCAPE_LAYOUT = {
  originX: 80,
  originY: 80,
  gapX: 300,
  gapY: 200,
};

/** Deterministic grid: same ids and count always produce the same positions. */
export function landscapeLayout(ids: string[]): Map<string, Point> {
  const ordered = [...ids].sort();
  const columns = Math.max(1, Math.ceil(Math.sqrt(ordered.length || 1)));
  const positions = new Map<string, Point>();
  ordered.forEach((id, index) => {
    positions.set(id, {
      x: LANDSCAPE_LAYOUT.originX + (index % columns) * LANDSCAPE_LAYOUT.gapX,
      y: LANDSCAPE_LAYOUT.originY + Math.floor(index / columns) * LANDSCAPE_LAYOUT.gapY,
    });
  });
  return positions;
}

export function relationshipLabel(type: SolutionRelationshipType): string {
  return SOLUTION_RELATIONSHIP_LABELS[type] ?? type;
}

export function isSymmetricRelationship(type: SolutionRelationshipType): boolean {
  return SYMMETRIC_SOLUTION_RELATIONSHIPS.includes(type);
}

/** Human summary of the association roles, always textual. */
export function contractRoleSummary(node: SolutionLandscapeNode): string {
  const { owned, participating, dependency, total } = node.contract_counts;
  if (total === 0) return "No associated contracts";
  return `${owned} owned · ${participating} participating · ${dependency} dependency`;
}

export function nodeWarnings(
  landscape: SolutionLandscape,
  solutionObjectId: string,
): SolutionLandscape["warnings"] {
  return landscape.warnings.filter(
    (warning) => warning.solution_object_id === solutionObjectId,
  );
}

export function relationshipWarnings(
  landscape: SolutionLandscape,
  relationshipId: string,
): SolutionLandscape["warnings"] {
  return landscape.warnings.filter((warning) => warning.relationship_id === relationshipId);
}

export function warningLabel(code: string): string {
  switch (code) {
    case "archived_contract_association":
      return "Unavailable contract association";
    case "member_system_unavailable":
      return "Unavailable member system";
    default:
      return code.replace(/_/g, " ");
  }
}
