export type ArchitectureDiscipline =
  | "enterprise"
  | "information"
  | "solution"
  | "integration";

export const ARCHITECTURE_DISCIPLINES: {
  id: ArchitectureDiscipline;
  label: string;
  description: string;
}[] = [
  {
    id: "enterprise",
    label: "Enterprise Architecture",
    description: "Business scope, requirements, constraints, and affected landscape",
  },
  {
    id: "information",
    label: "Information Architecture",
    description: "Information objects, logical attributes, ownership, and authoritative sources",
  },
  {
    id: "solution",
    label: "Solution Architecture",
    description: "Solution boundaries, systems, components, responsibilities, and candidate designs",
  },
  {
    id: "integration",
    label: "Integration Architecture",
    description: "Interfaces, contracts, schemas, mappings, transformations, and tests",
  },
];

export type ArchitectureStateType = "current" | "candidate" | "target";

export type ArchitectureObjectKind =
  | "business_requirement"
  | "business_capability"
  | "information_object"
  | "solution_boundary"
  | "component"
  | "interface";

export type ArchitectureObject = {
  id: string;
  kind: ArchitectureObjectKind;
  name: string;
  description?: string | null;
  owner?: string | null;
  authoritative_system_id?: string | null;
};

export type SemanticRelationshipType =
  | "Uses"
  | "Provides"
  | "Consumes"
  | "Reads"
  | "Writes"
  | "Publishes"
  | "Depends on"
  | "Implements"
  | "Transforms"
  | "Replaces"
  | "Impacts"
  | "Contains"
  | "Authoritative source";

export const SEMANTIC_RELATIONSHIP_TYPES: SemanticRelationshipType[] = [
  "Uses",
  "Provides",
  "Consumes",
  "Reads",
  "Writes",
  "Publishes",
  "Depends on",
  "Implements",
  "Transforms",
  "Replaces",
  "Impacts",
  "Contains",
  "Authoritative source",
];

export type ArchitectureStateNode = {
  occurrence_id: string;
  object_id: string; // references a canonical architecture object or catalog system
  position: { x: number; y: number };
  discipline?: ArchitectureDiscipline | null;
  parent_occurrence_id?: string | null;
  width?: number | null;
  height?: number | null;
  display_metadata?: Record<string, unknown>;
  candidate_overrides?: Record<string, unknown>;
};

export type ArchitectureStateRelationship = {
  id: string;
  source_id: string; // object_id or occurrence_id
  target_id: string; // object_id or occurrence_id
  type: SemanticRelationshipType | string;
  name?: string | null;
  integration_id?: string | null;
  candidate_overrides?: Record<string, unknown>;
  display_metadata?: Record<string, unknown>;
};

export type ArchitectureState = {
  id: string;
  workspace_id: string;
  name: string;
  state_type: ArchitectureStateType;
  description?: string | null;
  nodes: ArchitectureStateNode[];
  relationships: ArchitectureStateRelationship[];
  created_at: string;
  updated_at: string;
};

export type WorkspaceInfo = {
  id: string;
  name: string;
  description?: string | null;
  disciplines: ArchitectureDiscipline[];
  created_at: string;
  is_active: boolean;
  systems_count: number;
  contracts_count: number;
  scenarios_count: number;
  demo_preset?: string | null;
  demo_version?: string | null;
  demo_generated_at?: string | null;
};
