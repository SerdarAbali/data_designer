import { describe, expect, it } from "vitest";
import { deriveLandscapeMappingPaths, type LandscapeGraphDocument } from "./landscapeMappingModel";

const SOURCE_FIELD = "11111111-1111-4111-8111-111111111111";
const TARGET_FIELD = "22222222-2222-4222-8222-222222222222";

function phaseGraph(operation: string): LandscapeGraphDocument {
  return {
    version: 1,
    nodes: [
      { id: "source", type: "source", config: {} },
      { id: "cast", type: "fx", config: { function: operation } },
      { id: "target", type: "target", config: {} },
    ],
    edges: [
      {
        id: "input",
        sourceNodeId: "source",
        sourcePortId: `field:${SOURCE_FIELD}`,
        targetNodeId: "cast",
        targetPortId: "input",
      },
      {
        id: "output",
        sourceNodeId: "cast",
        sourcePortId: "output",
        targetNodeId: "target",
        targetPortId: `field:${TARGET_FIELD}`,
      },
    ],
  };
}

describe("phase-specific Landscape graph resolution", () => {
  it("resolves Request and Success Response from separate persisted graph slots", () => {
    const request = deriveLandscapeMappingPaths(phaseGraph("toInt"), "request");
    const response = deriveLandscapeMappingPaths(phaseGraph("toString"), "success-response");

    expect(request).toEqual([{
      sourceFieldId: SOURCE_FIELD,
      targetFieldId: TARGET_FIELD,
      transformations: ["Convert to integer"],
      phase: "request",
    }]);
    expect(response).toEqual([{
      sourceFieldId: SOURCE_FIELD,
      targetFieldId: TARGET_FIELD,
      transformations: ["Convert to text"],
      phase: "success-response",
    }]);
    expect(request[0]?.transformations).not.toEqual(response[0]?.transformations);
  });

  it("tags Error Response paths distinctly and retains exact field IDs", () => {
    const paths = deriveLandscapeMappingPaths(phaseGraph("toString"), "error-response");
    expect(paths[0]).toMatchObject({
      sourceFieldId: SOURCE_FIELD,
      targetFieldId: TARGET_FIELD,
      phase: "error-response",
    });
  });
});
