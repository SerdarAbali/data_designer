// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InformationEntityNode from "./InformationEntityNode";
import { cardinalityNotation, type InformationEntity } from "./informationModel";

vi.mock("@xyflow/react", () => ({
  Position: { Left: "left", Right: "right" },
  Handle: () => null,
}));

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

  it("renders cardinality notation", () => {
    expect(cardinalityNotation("one_to_one")).toEqual({ source: "1", target: "1" });
    expect(cardinalityNotation("one_to_many")).toEqual({ source: "1", target: "N" });
    expect(cardinalityNotation("many_to_many")).toEqual({ source: "N", target: "M" });
  });
});
