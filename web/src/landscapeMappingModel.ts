import {
  deriveMappingChains,
  fieldIdFromPort,
  type MappingGraphDocument,
  type MappingGraphEdge,
  type MappingGraphField,
  type MappingGraphNode,
} from "./mappingGraphModel";

export type LandscapeMappingPhase = "request" | "success-response" | "error-response";

export type LandscapeGraphDocument = MappingGraphDocument & {
  version: number;
  nodes: MappingGraphNode[];
  edges: MappingGraphEdge[];
};

export type LandscapeMappingPath = {
  sourceFieldId: string;
  targetFieldId: string;
  transformations: string[];
  phase: LandscapeMappingPhase;
};

export function deriveLandscapeMappingPaths(
  graph: LandscapeGraphDocument,
  phase: LandscapeMappingPhase,
): LandscapeMappingPath[] {
  const fieldIds = new Set<string>();
  for (const edge of graph.edges) {
    const senderId = fieldIdFromPort(edge.sourcePortId);
    const receiverId = fieldIdFromPort(edge.targetPortId);
    if (senderId) fieldIds.add(senderId);
    if (receiverId) fieldIds.add(receiverId);
  }
  const fields: MappingGraphField[] = [...fieldIds].map((id) => ({ id, data_type: "unknown" }));
  const chains = deriveMappingChains({ graph, senderFields: fields, receiverFields: fields });
  return chains.flatMap((chain) => chain.receiverFieldId
    && !chain.issues.some((item) => item.severity === "Error")
    ? chain.inputs.flatMap((input) => input.senderFieldId
      ? [{
        sourceFieldId: input.senderFieldId,
        targetFieldId: chain.receiverFieldId!,
        transformations: chain.transformations.map((item) => item.label),
        phase,
      }]
      : [])
    : []);
}
