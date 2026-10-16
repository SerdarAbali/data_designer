// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { Position } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InformationRelationshipEdge, {
  type InformationRelationshipFlowEdge,
} from "./InformationRelationshipEdge";
import type { InformationRelationship } from "./informationModel";

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
    BaseEdge: (props: { path: string }) =>
      React.createElement("div", { "data-testid": "edge-path", "data-d": props.path }),
    EdgeLabelRenderer: (props: { children?: unknown }) =>
      React.createElement("div", null, props.children as never),
    // Mirror React Flow's contract (path + label point) without geometry math.
    getSmoothStepPath: (o: { sourceX: number; sourceY: number; targetX: number; targetY: number }) => [
      `M ${o.sourceX},${o.sourceY} L ${o.targetX},${o.targetY}`,
      (o.sourceX + o.targetX) / 2,
      (o.sourceY + o.targetY) / 2,
    ],
  };
});

const relationship: InformationRelationship = {
  id: "rel-1",
  source_object_id: "ent-a",
  target_object_id: "ent-b",
  name: "has consent",
  cardinality: "one_to_many",
  source_optional: false,
  target_optional: true,
  source_handle: null,
  target_handle: null,
};

function renderEdge(overrides: Record<string, unknown> = {}) {
  const props = {
    id: "rel-1",
    source: "occ-a",
    target: "occ-b",
    sourceX: 100,
    sourceY: 50,
    targetX: 400,
    targetY: 50,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    selected: false,
    sourceHandleId: "s-right",
    targetHandleId: "t-left",
    data: { relationship },
    ...overrides,
  };
  return render(
    <InformationRelationshipEdge
      {...(props as unknown as EdgeProps<InformationRelationshipFlowEdge>)}
    />,
  );
}

afterEach(cleanup);

describe("InformationRelationshipEdge", () => {
  it("offsets cardinality labels outside the border for right/left handles", () => {
    const { container } = renderEdge();
    const transforms = [...container.querySelectorAll<HTMLElement>(".information-edge-endpoint")].map(
      (el) => el.style.transform,
    );
    // Right handle -> outside the right border; left handle -> outside the left border.
    expect(transforms).toEqual([
      "translate(-50%, -50%) translate(132px, 50px)",
      "translate(-50%, -50%) translate(368px, 50px)",
    ]);
    // The connector starts at the handle centre (outside/border), not inside the card.
    expect(container.querySelector('[data-testid="edge-path"]')?.getAttribute("data-d")).toBe(
      "M 100,50 L 400,50",
    );
  });

  it("offsets cardinality labels above/below for top/bottom handles", () => {
    const { container } = renderEdge({
      sourceX: 200,
      sourceY: 100,
      targetX: 200,
      targetY: 400,
      sourcePosition: Position.Top,
      targetPosition: Position.Bottom,
      sourceHandleId: "s-top",
      targetHandleId: "t-bottom",
    });
    const transforms = [...container.querySelectorAll<HTMLElement>(".information-edge-endpoint")].map(
      (el) => el.style.transform,
    );
    expect(transforms).toEqual([
      "translate(-50%, -50%) translate(200px, 68px)",
      "translate(-50%, -50%) translate(200px, 432px)",
    ]);
    // A "many" endpoint still draws the crow's-foot marker outside the border.
    expect(container.querySelectorAll("svg.information-crowfoot")).toHaveLength(1);
  });

  it("keeps the relationship name clear of the endpoint labels", () => {
    const { container } = renderEdge({
      sourceX: 200,
      sourceY: 100,
      targetX: 260,
      targetY: 140,
      sourcePosition: Position.Top,
      targetPosition: Position.Left,
      sourceHandleId: "s-top",
      targetHandleId: "t-left",
    });
    const label = container.querySelector<HTMLElement>(".information-edge-label");
    // Path midpoint (230,120) is inside the 34px clearance of the target label, so
    // the name is re-centred between the two cardinality labels instead.
    expect(label?.style.transform).toBe("translate(-50%, -50%) translate(214px, 104px)");
  });
});
