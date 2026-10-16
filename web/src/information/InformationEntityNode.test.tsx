// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InformationEntityNode from "./InformationEntityNode";
import {
  arrangeEntities,
  cardinalityNotation,
  chooseHandles,
  type InformationEntity,
} from "./informationModel";

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
    Handle: (props: { id?: string; style?: unknown }) =>
      React.createElement("div", {
        "data-testid": `handle-${props.id}`,
        "data-handle-style": JSON.stringify(props.style ?? null),
      }),
  };
});

const entity: InformationEntity = {
  object_id: "ent-1",
  occurrence_id: "occ-1",
  name: "Customer",
  description: null,
  owner: null,
  steward: null,
  authoritative_system_id: null,
  authoritative_system_name: null,
  classification: null,
  sensitivity: null,
  external_identifier: null,
  position: { x: 0, y: 0 },
  attributes: [
    {
      object_id: "attr-1",
      entity_object_id: "ent-1",
      name: "customer_id",
      data_type: "uuid",
      required: true,
      nullable: false,
      is_key: false,
      is_identifier: true,
      ordinal: 0,
      definition: null,
      created_in_state_id: "state-1",
      realization: null,
    },
  ],
};

afterEach(cleanup);

type NodePropsArg = Parameters<typeof InformationEntityNode>[0];

function nodeProps(data: NodePropsArg["data"]): NodePropsArg {
  return { id: entity.occurrence_id, type: "informationEntity", data, selected: false } as unknown as NodePropsArg;
}

describe("InformationEntityNode", () => {
  it("lists attributes with key badges", () => {
    render(<InformationEntityNode {...nodeProps({ entity, editable: true, selectedAttributeId: null, onSelectAttribute: vi.fn() })} />);
    expect(screen.getByText("Customer")).toBeTruthy();
    expect(screen.getByText("customer_id")).toBeTruthy();
    expect(screen.getByText("PK")).toBeTruthy();
  });

  it("invokes the attribute selection callback", () => {
    const onSelectAttribute = vi.fn();
    render(<InformationEntityNode {...nodeProps({ entity, editable: true, selectedAttributeId: null, onSelectAttribute })} />);
    fireEvent.click(screen.getByRole("button", { name: /customer_id/ }));
    expect(onSelectAttribute).toHaveBeenCalledWith("attr-1");
  });

  it("shows an inline empty state and marks unmapped attributes", () => {
    render(<InformationEntityNode {...nodeProps({ entity, editable: true, selectedAttributeId: null, onSelectAttribute: vi.fn() })} />);
    expect(screen.getByText("unmapped")).toBeTruthy();

    const empty = { ...entity, attributes: [] };
    render(<InformationEntityNode {...nodeProps({ entity: empty, editable: true, selectedAttributeId: null, onSelectAttribute: vi.fn() })} />);
    expect(screen.getByText("No attributes yet")).toBeTruthy();
  });

  it("filters visible attributes and reports when none match", () => {
    render(
      <InformationEntityNode
        {...nodeProps({
          entity,
          editable: true,
          selectedAttributeId: null,
          onSelectAttribute: vi.fn(),
          attributeFilter: "does-not-exist",
        })}
      />,
    );
    expect(screen.getByText("No attributes match the filter")).toBeTruthy();
  });

  it("anchors left/right handles in the header band and just outside the border", () => {
    render(<InformationEntityNode {...nodeProps({ entity, editable: true, selectedAttributeId: null, onSelectAttribute: vi.fn() })} />);
    const style = (id: string) =>
      JSON.parse(screen.getByTestId(`handle-${id}`).getAttribute("data-handle-style") ?? "null");
    // Left/right automatic connectors clear the attribute rows (header band).
    expect(style("s-right")).toEqual({ top: 22, right: -6 });
    expect(style("t-left")).toEqual({ top: 22, left: -6 });
    // Top/bottom handles already sit outside the rows; keep them outside the border.
    expect(style("s-top")).toEqual({ top: -6 });
    expect(style("t-bottom")).toEqual({ bottom: -6 });
  });

  it("renders cardinality notation", () => {
    expect(cardinalityNotation("one_to_one")).toEqual({ source: "1", target: "1" });
    expect(cardinalityNotation("one_to_many")).toEqual({ source: "1", target: "1..*" });
    expect(cardinalityNotation("many_to_many")).toEqual({ source: "1..*", target: "1..*" });
    expect(cardinalityNotation("one_to_many", true, false)).toEqual({ source: "0..1", target: "1..*" });
    expect(cardinalityNotation("many_to_many", false, true)).toEqual({ source: "1..*", target: "0..*" });
  });

  it("selects handles from relative entity positions", () => {
    expect(chooseHandles({ x: 0, y: 0 }, { x: 300, y: 10 })).toEqual({ source: "right", target: "left" });
    expect(chooseHandles({ x: 300, y: 0 }, { x: 0, y: 0 })).toEqual({ source: "left", target: "right" });
    expect(chooseHandles({ x: 0, y: 0 }, { x: 10, y: 300 })).toEqual({ source: "bottom", target: "top" });
    expect(chooseHandles({ x: 0, y: 300 }, { x: 0, y: 0 })).toEqual({ source: "top", target: "bottom" });
  });

  it("arranges entities left-to-right and top-to-bottom by relationship depth", () => {
    const entities = [
      { occurrence_id: "occ-b", object_id: "b" },
      { occurrence_id: "occ-a", object_id: "a" },
    ];
    const relationships = [{ source_object_id: "a", target_object_id: "b" }];
    const ltr = arrangeEntities(entities, relationships, "ltr");
    expect(ltr.get("occ-a")).toEqual({ x: 60, y: 60 });
    expect(ltr.get("occ-b")).toEqual({ x: 380, y: 60 });
    const ttb = arrangeEntities(entities, relationships, "ttb");
    expect(ttb.get("occ-a")).toEqual({ x: 60, y: 60 });
    expect(ttb.get("occ-b")).toEqual({ x: 60, y: 270 });
  });
});
