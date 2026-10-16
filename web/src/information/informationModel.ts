import { api } from "./api";

export type InformationCardinality = "one_to_one" | "one_to_many" | "many_to_many";

/**
 * The side of an entity box a connector attaches to. A four-sided handle set
 * lets the automatic router pick the shortest sensible edge between two boxes.
 */
export type InformationFlowSide = "top" | "right" | "bottom" | "left";

export type InformationPoint = { x: number; y: number };

/** Stable React Flow handle id for a given connector role and box side. */
export function handleId(kind: "source" | "target", side: InformationFlowSide): string {
  return `${kind === "source" ? "s" : "t"}-${side}`;
}

export type InformationRealization = {
  catalog_object_id: string | null;
  catalog_field_id: string | null;
  catalog_object_name: string | null;
  catalog_field_name: string | null;
};

export type InformationAttribute = {
  object_id: string;
  entity_object_id: string;
  name: string;
  data_type: string;
  required: boolean;
  nullable: boolean;
  is_key: boolean;
  is_identifier: boolean;
  ordinal: number;
  definition: string | null;
  created_in_state_id: string | null;
  realization: InformationRealization | null;
};

export type InformationEntity = {
  object_id: string;
  occurrence_id: string;
  name: string;
  description: string | null;
  owner: string | null;
  steward: string | null;
  authoritative_system_id: string | null;
  authoritative_system_name: string | null;
  classification: string | null;
  sensitivity: string | null;
  external_identifier: string | null;
  position: { x: number; y: number };
  attributes: InformationAttribute[];
};

export type InformationRelationship = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  name: string | null;
  cardinality: InformationCardinality;
  source_optional: boolean;
  target_optional: boolean;
  /** Optional manual connector endpoints; null means automatic routing. */
  source_handle: string | null;
  target_handle: string | null;
};

export type InformationModel = {
  state_id: string;
  state_type: string;
  editable: boolean;
  entities: InformationEntity[];
  relationships: InformationRelationship[];
};

export const CARDINALITY_OPTIONS: { value: InformationCardinality; label: string }[] = [
  { value: "one_to_one", label: "1 : 1" },
  { value: "one_to_many", label: "1 : 1..*" },
  { value: "many_to_many", label: "1..* : 1..*" },
];

export const DATA_TYPE_OPTIONS = [
  "string",
  "text",
  "integer",
  "decimal",
  "boolean",
  "date",
  "datetime",
  "uuid",
  "json",
];

/**
 * Cardinality shown at each endpoint of a structural entity relationship. The
 * per-endpoint optional flags (already persisted on the relationship) select
 * the minimum, giving the classic `1`, `0..1`, `1..*` and `0..*` notations.
 */
export function cardinalityNotation(
  cardinality: InformationCardinality,
  sourceOptional = false,
  targetOptional = false,
): { source: string; target: string } {
  const one = (optional: boolean) => (optional ? "0..1" : "1");
  const many = (optional: boolean) => (optional ? "0..*" : "1..*");
  switch (cardinality) {
    case "one_to_one":
      return { source: one(sourceOptional), target: one(targetOptional) };
    case "many_to_many":
      return { source: many(sourceOptional), target: many(targetOptional) };
    case "one_to_many":
    default:
      return { source: one(sourceOptional), target: many(targetOptional) };
  }
}

/**
 * Chooses a source and target handle (all four box sides) from the relative
 * position of two entity boxes so connectors leave toward the other box.
 */
export function chooseHandles(
  source: InformationPoint,
  target: InformationPoint,
): { source: InformationFlowSide; target: InformationFlowSide } {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? { source: "right", target: "left" }
      : { source: "left", target: "right" };
  }
  return dy >= 0
    ? { source: "bottom", target: "top" }
    : { source: "top", target: "bottom" };
}

/**
 * Resolves the React Flow handles for a relationship. A manually stored handle
 * always wins; a missing one falls back to automatic selection from positions,
 * so existing relationships and imports keep automatic routing.
 */
export function resolveRelationshipHandles(
  relationship: Pick<InformationRelationship, "source_handle" | "target_handle">,
  source: InformationPoint,
  target: InformationPoint,
): { sourceHandle: string; targetHandle: string } {
  const auto = chooseHandles(source, target);
  return {
    sourceHandle: relationship.source_handle ?? handleId("source", auto.source),
    targetHandle: relationship.target_handle ?? handleId("target", auto.target),
  };
}

/**
 * Automatic left-to-right or top-to-bottom arrangement. Entities are layered by
 * relationship depth (longest path from a root) and stacked within each layer,
 * preserving manual placement everywhere else.
 */
export function arrangeEntities(
  entities: { occurrence_id: string; object_id: string }[],
  relationships: { source_object_id: string; target_object_id: string }[],
  direction: "ltr" | "ttb",
): Map<string, InformationPoint> {
  const adjacency = new Map<string, string[]>();
  const level = new Map<string, number>();
  for (const entity of entities) {
    adjacency.set(entity.object_id, []);
    level.set(entity.object_id, 0);
  }
  for (const relationship of relationships) {
    if (adjacency.has(relationship.source_object_id) && level.has(relationship.target_object_id)) {
      adjacency.get(relationship.source_object_id)!.push(relationship.target_object_id);
    }
  }
  let changed = true;
  let guard = 0;
  while (changed && guard <= entities.length + 1) {
    changed = false;
    guard += 1;
    for (const [source, targets] of adjacency) {
      for (const target of targets) {
        const next = (level.get(source) ?? 0) + 1;
        if (next > (level.get(target) ?? 0)) {
          level.set(target, next);
          changed = true;
        }
      }
    }
  }

  const rows = new Map<number, number>();
  const positions = new Map<string, InformationPoint>();
  const ordered = [...entities].sort((a, b) => {
    const byLevel = (level.get(a.object_id) ?? 0) - (level.get(b.object_id) ?? 0);
    if (byLevel !== 0) return byLevel;
    return a.occurrence_id.localeCompare(b.occurrence_id);
  });
  for (const entity of ordered) {
    const lane = level.get(entity.object_id) ?? 0;
    const row = rows.get(lane) ?? 0;
    rows.set(lane, row + 1);
    positions.set(
      entity.occurrence_id,
      direction === "ltr"
        ? { x: 60 + lane * 320, y: 60 + row * 210 }
        : { x: 60 + row * 300, y: 60 + lane * 210 },
    );
  }
  return positions;
}


export function keyBadge(attribute: InformationAttribute): string | null {
  if (attribute.is_identifier) return "PK";
  if (attribute.is_key) return "UK";
  return null;
}

export function attributeSummary(attribute: InformationAttribute): string {
  const flag = attribute.is_identifier ? "PK" : attribute.is_key ? "UK" : "";
  const nullable = attribute.required ? "required" : attribute.nullable ? "optional" : "not null";
  return [attribute.data_type, nullable, flag].filter(Boolean).join(" · ");
}

function informationPath(workspaceId: string): string {
  return `/api/workspaces/${workspaceId}/information`;
}

export function fetchInformationModel(
  workspaceId: string,
  stateId: string,
): Promise<InformationModel> {
  return api<InformationModel>(
    `${informationPath(workspaceId)}/model?state_id=${encodeURIComponent(stateId)}`,
  );
}

export function createInformationEntity(
  workspaceId: string,
  body: { state_id: string; name: string; description?: string | null; position: { x: number; y: number } },
): Promise<{ entity: InformationEntity; state: import("../architectureTypes").ArchitectureState }> {
  return api(`${informationPath(workspaceId)}/entities`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateInformationEntity(
  workspaceId: string,
  entityId: string,
  body: {
    name?: string;
    description?: string | null;
    owner?: string | null;
    steward?: string | null;
    classification?: string | null;
    sensitivity?: string | null;
  },
): Promise<InformationEntity> {
  return api(`${informationPath(workspaceId)}/entities/${entityId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function createInformationAttribute(
  workspaceId: string,
  entityId: string,
  body: {
    state_id: string;
    name: string;
    data_type: string;
    required: boolean;
    nullable: boolean;
    is_key: boolean;
    is_identifier: boolean;
    definition?: string | null;
  },
): Promise<InformationAttribute> {
  return api(`${informationPath(workspaceId)}/entities/${entityId}/attributes`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateInformationAttribute(
  workspaceId: string,
  attributeId: string,
  body: Record<string, unknown>,
): Promise<InformationAttribute> {
  return api(`${informationPath(workspaceId)}/attributes/${attributeId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteInformationAttribute(
  workspaceId: string,
  attributeId: string,
  stateId: string,
): Promise<void> {
  return api(
    `${informationPath(workspaceId)}/attributes/${attributeId}?state_id=${encodeURIComponent(stateId)}`,
    { method: "DELETE" },
  );
}

export function setInformationRealization(
  workspaceId: string,
  attributeId: string,
  body: { state_id: string; catalog_field_id: string | null },
): Promise<InformationRealization> {
  return api(`${informationPath(workspaceId)}/attributes/${attributeId}/realization`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function createInformationRelationship(
  workspaceId: string,
  body: {
    state_id: string;
    source_object_id: string;
    target_object_id: string;
    cardinality: InformationCardinality;
    name?: string | null;
    source_handle?: string | null;
    target_handle?: string | null;
  },
): Promise<InformationRelationship> {
  return api(`${informationPath(workspaceId)}/relationships`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateInformationRelationship(
  workspaceId: string,
  relationshipId: string,
  stateId: string,
  body: {
    cardinality?: InformationCardinality;
    name?: string | null;
    source_object_id?: string;
    target_object_id?: string;
    source_handle?: string | null;
    target_handle?: string | null;
  },
): Promise<InformationRelationship> {
  return api(
    `${informationPath(workspaceId)}/relationships/${relationshipId}?state_id=${encodeURIComponent(stateId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

export function deleteInformationRelationship(
  workspaceId: string,
  relationshipId: string,
  stateId: string,
): Promise<void> {
  return api(
    `${informationPath(workspaceId)}/relationships/${relationshipId}?state_id=${encodeURIComponent(stateId)}`,
    {
      method: "DELETE",
    },
  );
}

// --- Completion projections --------------------------------------------------
// Read-only views derived from the canonical model, catalog and contracts.

export type InformationConcept = {
  object_id: string;
  name: string;
  description: string | null;
  owner: string | null;
};

export type InformationConceptRelationship = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  name: string | null;
  cardinality: InformationCardinality;
};

export type InformationConceptual = {
  state_id: string;
  concepts: InformationConcept[];
  relationships: InformationConceptRelationship[];
};

export type InformationRealizationStatus = "realized" | "partial" | "unmapped" | "invalid";

export type InformationContractRef = {
  id: string;
  name: string;
  direction: string;
};

export type InformationPhysicalMapping = {
  entity_object_id: string;
  entity_name: string;
  attribute_object_id: string;
  attribute_name: string;
  data_type: string;
  required: boolean;
  status: InformationRealizationStatus;
  system_id: string | null;
  system_name: string | null;
  catalog_object_id: string | null;
  catalog_object_name: string | null;
  catalog_field_id: string | null;
  catalog_field_name: string | null;
  contracts: InformationContractRef[];
};

export type InformationPhysical = {
  state_id: string;
  mappings: InformationPhysicalMapping[];
  summary: Record<string, number>;
};

export type InformationOwnershipEntry = {
  object_id: string;
  name: string;
  owner: string | null;
  steward: string | null;
  authoritative_system_id: string | null;
  authoritative_system_name: string | null;
  authoritative_in_state: boolean;
  classification: string | null;
  sensitivity: string | null;
  realization_count: number;
  systems: string[];
  issues: string[];
};

export type InformationOwnership = {
  state_id: string;
  entries: InformationOwnershipEntry[];
};

export type InformationLineageNode = {
  id: string;
  kind: string;
  name: string;
  detail: string | null;
  system_name: string | null;
  catalog_field_id: string | null;
  contract_id: string | null;
};

export type InformationLineageEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
};

export type InformationLineage = {
  state_id: string;
  nodes: InformationLineageNode[];
  edges: InformationLineageEdge[];
  gaps: string[];
};

export type InformationChangeType = "added" | "removed" | "changed" | "reused";

export type InformationImpactChange = {
  object_type: string;
  object_id: string;
  name: string;
  entity_object_id: string | null;
  entity_name: string | null;
  change: InformationChangeType;
  changed_fields: string[];
  reason: string | null;
};

export type InformationImpact = {
  state_id: string;
  baseline_state_id: string | null;
  supported: boolean;
  changes: InformationImpactChange[];
  unresolved: string[];
  summary: Record<string, number>;
};

function projectionPath(workspaceId: string, stateId: string, projection: string): string {
  return `${informationPath(workspaceId)}/${projection}?state_id=${encodeURIComponent(stateId)}`;
}

export function fetchInformationConceptual(
  workspaceId: string,
  stateId: string,
): Promise<InformationConceptual> {
  return api<InformationConceptual>(projectionPath(workspaceId, stateId, "conceptual"));
}

export function fetchInformationPhysical(
  workspaceId: string,
  stateId: string,
): Promise<InformationPhysical> {
  return api<InformationPhysical>(projectionPath(workspaceId, stateId, "physical"));
}

export function fetchInformationOwnership(
  workspaceId: string,
  stateId: string,
): Promise<InformationOwnership> {
  return api<InformationOwnership>(projectionPath(workspaceId, stateId, "ownership"));
}

export function fetchInformationLineage(
  workspaceId: string,
  stateId: string,
): Promise<InformationLineage> {
  return api<InformationLineage>(projectionPath(workspaceId, stateId, "lineage"));
}

export function fetchInformationImpact(
  workspaceId: string,
  stateId: string,
): Promise<InformationImpact> {
  return api<InformationImpact>(projectionPath(workspaceId, stateId, "impact"));
}
