import { api } from "./api";

export type InformationCardinality = "one_to_one" | "one_to_many" | "many_to_many";

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
  { value: "one_to_many", label: "1 : N" },
  { value: "many_to_many", label: "N : M" },
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

export function cardinalityNotation(
  cardinality: InformationCardinality,
): { source: string; target: string } {
  switch (cardinality) {
    case "one_to_one":
      return { source: "1", target: "1" };
    case "many_to_many":
      return { source: "N", target: "M" };
    case "one_to_many":
    default:
      return { source: "1", target: "N" };
  }
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
  body: { cardinality?: InformationCardinality; name?: string | null },
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
