export type GraphNodeType =
  | "source" | "target" | "constant" | "fx" | "concat" | "ifelse"
  | "map" | "coalesce" | "lookup" | "filter" | "validate";

export type GraphNodeDocument = {
  id: string;
  type: GraphNodeType;
  position: { x: number; y: number };
  config: Record<string, unknown>;
};

export type GraphEdgeDocument = {
  id: string;
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
};

export type GraphDocument = {
  version: 1;
  nodes: GraphNodeDocument[];
  edges: GraphEdgeDocument[];
};
